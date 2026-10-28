from pathlib import PurePosixPath
from uuid import uuid4

import fitz
from fastapi import APIRouter, File, HTTPException, UploadFile

from services.document_chunker import chunk_document


router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
UPLOAD_READ_CHUNK_SIZE = 64 * 1024
PDF_PAGE_SEPARATOR = "\n\f\n"


async def _read_upload_limited(upload: UploadFile) -> bytes:
    """Read an upload incrementally and reject it immediately above the cap."""

    data = bytearray()
    while True:
        chunk = await upload.read(
            min(UPLOAD_READ_CHUNK_SIZE, MAX_UPLOAD_SIZE_BYTES + 1 - len(data))
        )
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="The uploaded file exceeds the 10 MiB limit.",
            )
    return bytes(data)


def _safe_filename(filename: str | None) -> str:
    normalized = (filename or "").replace("\\", "/")
    basename = PurePosixPath(normalized).name
    safe_name = "".join(
        character
        for character in basename
        if ord(character) >= 32 and ord(character) != 127
    ).strip()
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="A valid filename is required.")
    return safe_name


def _extract_pdf(data: bytes) -> tuple[str, int, list[str]]:
    if b"%PDF-" not in data[:1024]:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF.")

    try:
        document = fitz.open(stream=data, filetype="pdf")
        with document:
            if document.needs_pass and not document.authenticate(""):
                raise HTTPException(
                    status_code=400,
                    detail="The PDF is encrypted and cannot be extracted without a password.",
                )

            page_count = document.page_count
            page_texts = [page.get_text("text") for page in document]
    except HTTPException:
        raise
    except (fitz.FileDataError, fitz.EmptyFileError, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="The uploaded PDF is malformed or unreadable.",
        ) from exc

    text = PDF_PAGE_SEPARATOR.join(page_texts)
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="The PDF contains no extractable text.",
        )
    return text, page_count, page_texts


def _extract_text(data: bytes) -> str:
    if b"%PDF-" in data[:1024]:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is a PDF, not a TXT document.",
        )
    if b"\x00" in data:
        raise HTTPException(status_code=400, detail="The TXT file contains invalid text data.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="The TXT file must use UTF-8 encoding.",
        ) from exc


@router.post("/extract")
async def extract_document(file: UploadFile = File(...)):
    try:
        filename = _safe_filename(file.filename)
        extension = PurePosixPath(filename).suffix.lower()
        if extension not in {".pdf", ".txt"}:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Upload a PDF or TXT file.",
            )

        data = await _read_upload_limited(file)
        if not data:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        page_texts = None
        if extension == ".pdf":
            text, page_count, page_texts = _extract_pdf(data)
            file_type = "pdf"
        else:
            text = _extract_text(data)
            page_count = None
            file_type = "txt"

        document_id = str(uuid4())
        chunks = chunk_document(
            text,
            file_type=file_type,
            page_texts=page_texts,
        )

        return {
            "document_id": document_id,
            "filename": filename,
            "file_type": file_type,
            "file_size_bytes": len(data),
            "page_count": page_count,
            "character_count": len(text),
            "text": text,
            "chunks": chunks,
        }
    finally:
        await file.close()
