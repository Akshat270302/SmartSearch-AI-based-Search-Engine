import os
import sys
import unittest
from uuid import UUID

import fitz
from fastapi.testclient import TestClient

os.environ.setdefault("GEMINI_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import main
from services.document_chunker import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    chunk_document,
)


client = TestClient(main.app)


def make_pdf(*page_texts):
    document = fitz.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


class DocumentExtractionTests(unittest.TestCase):
    def upload(self, filename, content, content_type="application/octet-stream"):
        return client.post(
            "/documents/extract",
            files={"file": (filename, content, content_type)},
        )

    def assert_chunk_coverage(self, source, chunks):
        self.assertTrue(chunks)
        self.assertEqual(chunks[0]["start_char"], 0)
        self.assertEqual(chunks[-1]["end_char"], len(source))
        self.assertEqual(
            [chunk["chunk_index"] for chunk in chunks],
            list(range(len(chunks))),
        )

        for chunk in chunks:
            self.assertGreater(chunk["end_char"], chunk["start_char"])
            self.assertLessEqual(len(chunk["text"]), DEFAULT_CHUNK_SIZE)
            self.assertEqual(
                chunk["text"], source[chunk["start_char"]:chunk["end_char"]]
            )

        reconstructed = chunks[0]["text"]
        for previous, current in zip(chunks, chunks[1:]):
            overlap = previous["end_char"] - current["start_char"]
            self.assertEqual(overlap, DEFAULT_CHUNK_OVERLAP)
            self.assertEqual(
                previous["text"][-overlap:], current["text"][:overlap]
            )
            reconstructed += current["text"][overlap:]
        self.assertEqual(reconstructed, source)

    def test_extracts_utf8_txt_and_reports_matching_character_count(self):
        expected = "Café\nDocument text"
        response = self.upload(
            "C:\\uploads\\notes.txt",
            b"\xef\xbb\xbf" + expected.encode("utf-8"),
            "application/pdf",  # Content type is not trusted for detection.
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["filename"], "notes.txt")
        self.assertEqual(payload["file_type"], "txt")
        self.assertIsNone(payload["page_count"])
        self.assertEqual(payload["text"], expected)
        self.assertEqual(payload["character_count"], len(expected))
        self.assertEqual(payload["file_size_bytes"], len(b"\xef\xbb\xbf" + expected.encode("utf-8")))
        self.assertTrue(UUID(payload["document_id"]))
        self.assertEqual(
            set(payload),
            {
                "document_id", "filename", "file_type", "file_size_bytes",
                "page_count", "character_count", "text", "chunks",
            },
        )
        self.assertEqual(len(payload["chunks"]), 1)
        self.assertEqual(
            payload["chunks"][0],
            {
                "chunk_index": 0,
                "text": expected,
                "page_number": None,
                "start_char": 0,
                "end_char": len(expected),
            },
        )

    def test_extracts_all_pdf_pages_and_preserves_blank_page_boundary(self):
        content = make_pdf("First page text", "", "Third page text")
        response = self.upload("report.PDF", content, "text/plain")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["file_type"], "pdf")
        self.assertEqual(payload["page_count"], 3)
        self.assertIn("First page text", payload["text"])
        self.assertIn("Third page text", payload["text"])
        self.assertEqual(payload["text"].count("\f"), 2)
        self.assertEqual(payload["character_count"], len(payload["text"]))
        self.assertEqual([chunk["page_number"] for chunk in payload["chunks"]], [1, 3])
        self.assertEqual([chunk["chunk_index"] for chunk in payload["chunks"]], [0, 1])

    def test_whitespace_only_text_has_no_empty_chunks(self):
        response = self.upload("whitespace.txt", b" \n\t ")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], " \n\t ")
        self.assertEqual(response.json()["chunks"], [])

    def test_long_txt_chunks_overlap_in_order_and_respect_limits(self):
        first_paragraph = "A sentence with some words. " * 30
        second_paragraph = "Another sentence follows here. " * 45
        source = first_paragraph + "\n\n" + second_paragraph
        chunks = chunk_document(source, file_type="txt")

        self.assertGreater(len(chunks), 1)
        self.assertEqual(
            [chunk["chunk_index"] for chunk in chunks],
            list(range(len(chunks))),
        )
        self.assertTrue(all(len(chunk["text"]) <= DEFAULT_CHUNK_SIZE for chunk in chunks))
        self.assertTrue(all(chunk["page_number"] is None for chunk in chunks))
        for chunk in chunks:
            self.assertEqual(
                chunk["text"], source[chunk["start_char"]:chunk["end_char"]]
            )
            self.assertEqual(
                chunk["end_char"] - chunk["start_char"], len(chunk["text"])
            )

        reconstructed = chunks[0]["text"]
        for previous, current in zip(chunks, chunks[1:]):
            overlap = previous["end_char"] - current["start_char"]
            self.assertEqual(overlap, DEFAULT_CHUNK_OVERLAP)
            self.assertEqual(
                previous["text"][-overlap:], current["text"][:overlap]
            )
            reconstructed += current["text"][overlap:]
        self.assertEqual(reconstructed, source)

    def test_chunking_prefers_paragraph_and_sentence_boundaries(self):
        paragraph = "A" * 698 + ". "
        source = paragraph + "\n\n" + "B" * 1_200
        chunks = chunk_document(source, file_type="txt")

        self.assertGreater(len(chunks), 1)
        self.assertTrue(chunks[0]["text"].endswith("\n\n"))

        sentences = "A complete sentence. " * 60
        sentence_chunks = chunk_document(sentences, file_type="txt")
        self.assertTrue(sentence_chunks[0]["text"].rstrip().endswith("."))

    def test_pdf_chunks_keep_page_local_offsets_and_skip_blank_pages(self):
        pages = ["A" * 1_500, " \n", "B" * 1_250]
        chunks = chunk_document(
            "\n\f\n".join(pages),
            file_type="pdf",
            page_texts=pages,
        )

        self.assertEqual({chunk["page_number"] for chunk in chunks}, {1, 3})
        self.assertEqual(
            [chunk["chunk_index"] for chunk in chunks],
            list(range(len(chunks))),
        )
        for chunk in chunks:
            page_text = pages[chunk["page_number"] - 1]
            self.assertEqual(
                chunk["text"], page_text[chunk["start_char"]:chunk["end_char"]]
            )
            self.assertLessEqual(len(chunk["text"]), DEFAULT_CHUNK_SIZE)

    def test_empty_and_whitespace_only_text_produce_no_chunks(self):
        self.assertEqual(chunk_document("", file_type="txt"), [])
        self.assertEqual(chunk_document(" \n\t", file_type="txt"), [])

    def test_mixed_txt_with_leading_whitespace_preserves_full_coverage(self):
        source = " " * 1_200 + "Leading content. " * 100
        chunks = chunk_document(source, file_type="txt")

        self.assert_chunk_coverage(source, chunks)

    def test_mixed_txt_with_interior_whitespace_preserves_full_coverage(self):
        source = "Prefix content. " * 15 + " " * 2_500 + "Suffix content. " * 80
        chunks = chunk_document(source, file_type="txt")

        self.assert_chunk_coverage(source, chunks)

    def test_mixed_txt_with_trailing_whitespace_preserves_full_coverage(self):
        source = "Text before trailing whitespace. " * 20 + " " * 1_500
        chunks = chunk_document(source, file_type="txt")

        self.assert_chunk_coverage(source, chunks)

    def test_rejects_unsupported_extension(self):
        response = self.upload("notes.docx", b"text")

        self.assertEqual(response.status_code, 400)

    def test_rejects_empty_upload(self):
        response = self.upload("empty.txt", b"")

        self.assertEqual(response.status_code, 400)

    def test_rejects_upload_over_ten_mib_while_reading(self):
        response = self.upload("large.txt", b"a" * (10 * 1024 * 1024 + 1))

        self.assertEqual(response.status_code, 413)

    def test_rejects_malformed_pdf(self):
        response = self.upload("broken.pdf", b"%PDF-1.7\nnot a real PDF")

        self.assertEqual(response.status_code, 400)

    def test_rejects_pdf_bytes_renamed_as_txt(self):
        response = self.upload("renamed.txt", make_pdf("Not text"))

        self.assertEqual(response.status_code, 400)

    def test_rejects_invalid_utf8_text(self):
        response = self.upload("invalid.txt", b"valid prefix\xffinvalid")

        self.assertEqual(response.status_code, 400)
        self.assertIn("UTF-8", response.json()["detail"])

    def test_pdf_without_extractable_text_returns_422(self):
        response = self.upload("blank.pdf", make_pdf(""))

        self.assertEqual(response.status_code, 422)
        self.assertIn("no extractable text", response.json()["detail"])

    def test_rejects_encrypted_pdf_that_requires_a_password(self):
        document = fitz.open()
        document.new_page().insert_text((72, 72), "Protected text")
        content = document.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="owner-password",
            user_pw="user-password",
        )
        document.close()

        response = self.upload("protected.pdf", content)

        self.assertEqual(response.status_code, 400)
        self.assertIn("encrypted", response.json()["detail"])

    def test_root_and_search_routes_remain_registered(self):
        route_methods = {
            (route.path, method)
            for route in main.app.routes
            for method in getattr(route, "methods", set())
        }

        self.assertIn(("/search", "GET"), route_methods)
        self.assertEqual(client.get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
