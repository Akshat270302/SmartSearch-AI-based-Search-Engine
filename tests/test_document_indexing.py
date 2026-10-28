import os
import sys
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

import fitz
from fastapi.testclient import TestClient

os.environ.setdefault("GEMINI_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import main
from routers import documents
from services.embedding_service import EmbeddingError
from services.vector_store import VectorStoreError


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


def mock_embeddings(chunks):
    return [
        {
            "chunk": chunk,
            "embedding": [float(chunk["chunk_index"] + 1), 0.0],
        }
        for chunk in chunks
    ]


class DocumentIndexingTests(unittest.TestCase):
    def setUp(self):
        self.created_document_ids = []

    def tearDown(self):
        for document_id in self.created_document_ids:
            documents.document_vector_store.delete_document_collection(document_id)

    def upload(self, filename, content):
        response = client.post(
            "/documents/extract",
            files={"file": (filename, content, "application/octet-stream")},
        )
        if response.status_code == 200:
            self.created_document_ids.append(response.json()["document_id"])
        return response

    def retrieve(self, document_id, *, top_k=10):
        with patch("routers.documents.embed_query", return_value=[1.0, 0.0]):
            return client.post(
                "/documents/retrieve",
                json={
                    "document_id": document_id,
                    "query": "find relevant text",
                    "top_k": top_k,
                },
            )

    def test_txt_extraction_is_embedded_stored_and_retrievable(self):
        text = "TXT retrieval phrase. " * 80
        with patch(
            "routers.documents.embed_chunks", side_effect=mock_embeddings
        ) as embed:
            response = self.upload("notes.txt", text.encode("utf-8"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload),
            {
                "document_id",
                "filename",
                "file_type",
                "file_size_bytes",
                "page_count",
                "character_count",
                "text",
                "chunks",
            },
        )
        self.assertTrue(UUID(payload["document_id"]))
        self.assertEqual(payload["filename"], "notes.txt")
        embed.assert_called_once_with(payload["chunks"])

        stored = documents.document_vector_store.get_document_records(
            payload["document_id"]
        )
        stored_by_index = {
            record["metadata"]["chunk_index"]: record for record in stored
        }
        self.assertEqual(len(stored), len(payload["chunks"]))
        for chunk in payload["chunks"]:
            record = stored_by_index[chunk["chunk_index"]]
            self.assertEqual(record["text"], chunk["text"])
            self.assertEqual(
                record["embedding"], [float(chunk["chunk_index"] + 1), 0.0]
            )
            self.assertIsNone(record["metadata"]["page_number"])

        retrieval = self.retrieve(payload["document_id"])
        self.assertEqual(retrieval.status_code, 200)
        self.assertEqual(
            [item["chunk_index"] for item in retrieval.json()["results"]],
            list(range(len(payload["chunks"]))),
        )
        self.assertTrue(
            all(item["page_number"] is None for item in retrieval.json()["results"])
        )

    def test_pdf_extraction_stores_and_retrieves_one_based_page_metadata(self):
        content = make_pdf("First page reference.", "", "Third page reference.")
        with patch(
            "routers.documents.embed_chunks", side_effect=mock_embeddings
        ) as embed:
            response = self.upload("report.pdf", content)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page_count"], 3)
        self.assertEqual([item["page_number"] for item in payload["chunks"]], [1, 3])
        embed.assert_called_once_with(payload["chunks"])

        retrieval = self.retrieve(payload["document_id"])
        self.assertEqual(retrieval.status_code, 200)
        results = retrieval.json()["results"]
        self.assertEqual([item["page_number"] for item in results], [1, 3])
        self.assertEqual(
            [item["chunk_index"] for item in results],
            [item["chunk_index"] for item in payload["chunks"]],
        )
        self.assertTrue(all(item["document_id"] == payload["document_id"] for item in results))
        self.assertTrue(all(item["filename"] == "report.pdf" for item in results))

    def test_whitespace_only_txt_keeps_existing_empty_chunk_behavior(self):
        with patch("routers.documents.embed_chunks") as embed:
            response = self.upload("blank.txt", b" \n\t ")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["chunks"], [])
        embed.assert_not_called()
        self.assertFalse(
            documents.document_vector_store.document_collection_exists(
                payload["document_id"]
            )
        )

    def test_embedding_failure_returns_error_without_creating_collection(self):
        document_id = str(uuid4())
        with (
            patch("routers.documents.uuid4", return_value=UUID(document_id)),
            patch(
                "routers.documents.embed_chunks",
                side_effect=EmbeddingError("secret provider details"),
            ),
        ):
            response = self.upload("notes.txt", b"Text to index")

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret provider details", response.text)
        self.assertFalse(
            documents.document_vector_store.document_collection_exists(document_id)
        )

    def test_partial_vector_failure_rolls_back_only_the_new_collection(self):
        document_id = str(uuid4())
        store = documents.document_vector_store
        original_insert = store.insert_chunks

        def insert_part_then_fail(target_id, embedded_chunks, *, filename):
            original_insert(
                target_id,
                embedded_chunks[:1],
                filename=filename,
            )
            raise VectorStoreError("private storage detail")

        with (
            patch("routers.documents.uuid4", return_value=UUID(document_id)),
            patch("routers.documents.embed_chunks", side_effect=mock_embeddings),
            patch.object(store, "insert_chunks", side_effect=insert_part_then_fail),
        ):
            response = self.upload("notes.txt", b"Text to index")

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private storage detail", response.text)
        self.assertFalse(store.document_collection_exists(document_id))


if __name__ == "__main__":
    unittest.main()
