import asyncio
from pathlib import PurePosixPath
from uuid import uuid4

import fitz
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator

from gemini_service import generate_document_answer
from services.document_chunker import chunk_document
from services.embedding_service import EmbeddingError, embed_chunks, embed_query
from services.vector_store import (
    DocumentCollectionNotFoundError,
    InMemoryDocumentVectorStore,
    VectorStoreError,
)


router = APIRouter(prefix="/documents", tags=["documents"])
document_vector_store = InMemoryDocumentVectorStore()

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
UPLOAD_READ_CHUNK_SIZE = 64 * 1024
PDF_PAGE_SEPARATOR = "\n\f\n"


class DocumentRetrievalRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=4_000)
    top_k: int = Field(default=5, ge=1, le=20, strict=True)

    @field_validator("document_id", "query")
    @classmethod
    def reject_whitespace_only_values(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field must not be empty or whitespace-only.")
        return value


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

        if chunks:
            try:
                collection_exists = await asyncio.to_thread(
                    document_vector_store.document_collection_exists,
                    document_id,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail="Could not prepare document vector storage.",
                ) from exc
            if collection_exists:
                raise HTTPException(
                    status_code=409,
                    detail="A document collection already exists for this ID.",
                )

            try:
                embedded_chunks = await asyncio.to_thread(
                    embed_chunks,
                    chunks,
                )
                if len(embedded_chunks) != len(chunks):
                    raise EmbeddingError(
                        "The embedding service returned an incomplete chunk set."
                    )
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail="Could not generate embeddings for the extracted document.",
                ) from exc

            try:
                stored_ids = await asyncio.to_thread(
                    document_vector_store.insert_chunks,
                    document_id,
                    embedded_chunks,
                    filename=filename,
                )
                if len(stored_ids) != len(embedded_chunks):
                    raise VectorStoreError(
                        "The vector store accepted an incomplete chunk set."
                    )
            except Exception as exc:
                try:
                    await asyncio.to_thread(
                        document_vector_store.delete_document_collection,
                        document_id,
                    )
                except Exception:
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Document indexing failed and temporary storage "
                            "could not be cleaned up."
                        ),
                    ) from None
                raise HTTPException(
                    status_code=500,
                    detail="Could not store the extracted document chunks.",
                ) from exc

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


def _retrieve_document_chunks(request: DocumentRetrievalRequest) -> list[dict]:
    try:
        collection_exists = document_vector_store.document_collection_exists(
            request.document_id
        )
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not access the document collection.",
        ) from exc
    if not collection_exists:
        raise HTTPException(
            status_code=404,
            detail="The requested document collection was not found.",
        )

    try:
        query_embedding = embed_query(request.query)
    except EmbeddingError as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not embed the retrieval query. Check Gemini availability and configuration.",
        ) from exc

    try:
        results = document_vector_store.query_document(
            request.document_id,
            query_embedding,
            top_k=request.top_k,
        )
    except DocumentCollectionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="The requested document collection was not found.",
        ) from exc
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve chunks from the document collection.",
        ) from exc
    return results


@router.post("/retrieve")
def retrieve_document_chunks(request: DocumentRetrievalRequest):
    results = _retrieve_document_chunks(request)

    return {
        "document_id": request.document_id,
        "query": request.query,
        "results": results,
    }


@router.post("/ask")
def ask_document(request: DocumentRetrievalRequest):
    retrieved_chunks = _retrieve_document_chunks(request)
    if not retrieved_chunks:
        answer = (
            "The document has no indexed passages, so the available document "
            "context is insufficient to answer the question."
        )
    else:
        try:
            answer = generate_document_answer(request.query, retrieved_chunks)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="Could not generate an answer from the document context.",
            ) from exc
        if not isinstance(answer, str) or not answer.strip():
            raise HTTPException(
                status_code=502,
                detail="Could not generate an answer from the document context.",
            )

    source_fields = (
        "filename",
        "page_number",
        "chunk_index",
        "document_id",
    )
    sources = [
        {key: chunk[key] for key in source_fields if key in chunk}
        for chunk in retrieved_chunks
    ]
    return {
        "document_id": request.document_id,
        "query": request.query,
        "answer": answer.strip(),
        "sources": sources,
    }
