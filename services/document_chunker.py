import re


DEFAULT_CHUNK_SIZE = 1_000
DEFAULT_CHUNK_OVERLAP = 150

_PARAGRAPH_BOUNDARY = re.compile(r"\n[ \t]*\n+")
_SENTENCE_BOUNDARY = re.compile(r"[.!?]+[\"')\]]*\s+")
_WHITESPACE_BOUNDARY = re.compile(r"\s+")


def _find_preferred_end(text: str, start: int, limit: int, chunk_size: int) -> int:
    """Prefer a nearby paragraph, sentence, or whitespace boundary."""

    lookback = min(200, max(1, chunk_size // 5))
    lower_bound = max(start + 1, limit - lookback)
    paragraph_lower_bound = max(start + 1, limit - max(lookback, chunk_size // 2))

    for pattern, boundary_start in (
        (_PARAGRAPH_BOUNDARY, paragraph_lower_bound),
        (_SENTENCE_BOUNDARY, lower_bound),
        (_WHITESPACE_BOUNDARY, lower_bound),
    ):
        window = text[boundary_start:limit]
        matches = list(pattern.finditer(window))
        if matches:
            boundary = boundary_start + matches[-1].end()
            if boundary > start:
                return boundary

    return limit


def _chunk_text(
    text: str,
    *,
    page_number: int | None,
    chunk_index_start: int,
    chunk_size: int,
    overlap: int,
) -> list[dict]:
    if not text or not text.strip():
        return []

    chunks = []
    start = 0
    while start < len(text):
        limit = min(start + chunk_size, len(text))
        end = limit if limit == len(text) else _find_preferred_end(
            text, start, limit, chunk_size
        )

        chunk_text = text[start:end]
        if chunk_text:
            chunks.append(
                {
                    "chunk_index": chunk_index_start + len(chunks),
                    "text": chunk_text,
                    "page_number": page_number,
                    "start_char": start,
                    "end_char": end,
                }
            )

        if end >= len(text):
            break
        next_start = max(start + 1, end - overlap)
        start = next_start if chunk_text else end

    return chunks


def chunk_document(
    text: str,
    *,
    file_type: str,
    page_texts: list[str] | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict]:
    """Chunk extracted text with page-aware offsets for PDFs.

    PDF offsets are relative to each original page's extracted text. TXT offsets
    are relative to the complete text file. Blank PDF pages retain their place
    in page numbering but produce no chunks. PDF chunks never cross page
    boundaries, so overlap does not extend from one page into another.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be nonnegative and less than chunk_size")

    normalized_type = file_type.lower()
    if normalized_type == "txt":
        return _chunk_text(
            text,
            page_number=None,
            chunk_index_start=0,
            chunk_size=chunk_size,
            overlap=overlap,
        )
    if normalized_type != "pdf":
        raise ValueError("file_type must be 'pdf' or 'txt'")
    if page_texts is None:
        raise ValueError("page_texts are required for PDF chunking")

    chunks = []
    for page_number, page_text in enumerate(page_texts, start=1):
        chunks.extend(
            _chunk_text(
                page_text,
                page_number=page_number,
                chunk_index_start=len(chunks),
                chunk_size=chunk_size,
                overlap=overlap,
            )
        )
    return chunks
