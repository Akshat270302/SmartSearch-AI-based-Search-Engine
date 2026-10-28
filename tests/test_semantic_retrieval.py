import os
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

os.environ.setdefault("GEMINI_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import main
from routers import documents
from services.embedding_service import EmbeddingError, embed_query
from services.vector_store import (
    DocumentCollectionNotFoundError,
    InMemoryDocumentVectorStore,
    VectorStoreError,
)


client = TestClient(main.app)


def chunk(index, text, page_number, start_char):
    return {
        "chunk_index": index,
        "text": text,
        "page_number": page_number,
        "start_char": start_char,
        "end_char": start_char + len(text),
    }


class QueryEmbeddingTests(unittest.TestCase):
    def test_query_uses_existing_chunk_embedding_path(self):
        expected = [0.25, 0.75]
        with patch(
            "services.embedding_service.embed_chunks",
            return_value=[
                {"chunk": {"chunk_index": 0, "text": "question"}, "embedding": expected}
            ],
        ) as embed_chunks_mock:
            result = embed_query("question")

        self.assertEqual(result, expected)
        embed_chunks_mock.assert_called_once_with(
            [{"chunk_index": 0, "text": "question"}], client=None, model=None
        )

    def test_query_embedding_rejects_empty_and_whitespace_queries(self):
        for query in ("", " \n\t "):
            with self.subTest(query=repr(query)):
                with self.assertRaisesRegex(EmbeddingError, "must not be empty"):
                    embed_query(query)


class SemanticVectorStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryDocumentVectorStore()
        self.document_id = f"retrieve-{uuid4().hex}"

    def test_returns_relevant_chunks_in_order_with_original_metadata(self):
        self.store.insert_chunks(
            self.document_id,
            [
                {
                    "chunk": chunk(0, "PDF page text", 2, 0),
                    "embedding": [1.0, 0.0],
                },
                {
                    "chunk": chunk(1, "TXT chunk text", None, 13),
                    "embedding": [0.0, 1.0],
                },
            ],
            filename="source.txt",
        )
        other_document_id = f"other-{uuid4().hex}"
        self.store.insert_chunks(
            other_document_id,
            [
                {
                    "chunk": chunk(0, "Other document", 1, 0),
                    "embedding": [0.9, 0.1],
                }
            ],
            filename="other.pdf",
        )

        results = self.store.query_document(
            self.document_id, [0.9, 0.1], top_k=5
        )

        self.assertEqual([item["chunk_index"] for item in results], [0, 1])
        self.assertEqual([item["text"] for item in results], ["PDF page text", "TXT chunk text"])
        self.assertEqual([item["document_id"] for item in results], [self.document_id] * 2)
        self.assertEqual(results[0]["page_number"], 2)
        self.assertEqual(results[0]["start_char"], 0)
        self.assertEqual(results[0]["end_char"], 13)
        self.assertEqual(results[0]["filename"], "source.txt")
        self.assertIsNone(results[1]["page_number"])
        self.assertEqual(
            [item["distance"] for item in results],
            sorted(item["distance"] for item in results),
        )

    def test_returns_empty_for_an_existing_empty_collection(self):
        self.store.create_document_collection(self.document_id)

        self.assertEqual(
            self.store.query_document(self.document_id, [0.2, 0.8], top_k=5), []
        )

    def test_missing_collection_has_a_specific_error(self):
        with self.assertRaises(DocumentCollectionNotFoundError):
            self.store.query_document(self.document_id, [0.2, 0.8])


class SemanticRetrievalEndpointTests(unittest.TestCase):
    def setUp(self):
        self.request_payload = {
            "document_id": "requested-document",
            "query": "Which page mentions retrieval?",
            "top_k": 3,
        }
        self.results = [
            {
                "chunk_index": 7,
                "text": "Semantic retrieval is described here.",
                "page_number": 4,
                "start_char": 200,
                "end_char": 238,
                "document_id": "requested-document",
                "filename": "guide.pdf",
                "distance": 0.12,
            }
        ]

    def test_embeds_query_and_returns_document_scoped_results(self):
        with (
            patch.object(
                documents.document_vector_store,
                "document_collection_exists",
                return_value=True,
            ),
            patch.object(documents, "embed_query", return_value=[0.1, 0.9]) as embed,
            patch.object(
                documents.document_vector_store,
                "query_document",
                return_value=self.results,
            ) as retrieve,
        ):
            response = client.post("/documents/retrieve", json=self.request_payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "document_id": "requested-document",
                "query": "Which page mentions retrieval?",
                "results": self.results,
            },
        )
        embed.assert_called_once_with("Which page mentions retrieval?")
        retrieve.assert_called_once_with(
            "requested-document", [0.1, 0.9], top_k=3
        )

    def test_empty_collection_result_is_a_successful_empty_list(self):
        with (
            patch.object(
                documents.document_vector_store,
                "document_collection_exists",
                return_value=True,
            ),
            patch.object(documents, "embed_query", return_value=[0.1, 0.9]),
            patch.object(
                documents.document_vector_store,
                "query_document",
                return_value=[],
            ),
        ):
            response = client.post("/documents/retrieve", json=self.request_payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_empty_query_and_invalid_top_k_are_rejected(self):
        for overrides in (
            {"document_id": " \t "},
            {"query": " \n "},
            {"query": ""},
            {"top_k": 0},
            {"top_k": 21},
            {"top_k": True},
        ):
            with self.subTest(overrides=overrides):
                response = client.post(
                    "/documents/retrieve",
                    json={**self.request_payload, **overrides},
                )
                self.assertEqual(response.status_code, 422)

        response = client.post(
            "/documents/retrieve",
            json={"query": "Which page mentions retrieval?"},
        )
        self.assertEqual(response.status_code, 422)

    def test_missing_document_returns_404_before_embedding(self):
        with (
            patch.object(
                documents.document_vector_store,
                "document_collection_exists",
                return_value=False,
            ),
            patch.object(documents, "embed_query") as embed,
        ):
            response = client.post("/documents/retrieve", json=self.request_payload)

        self.assertEqual(response.status_code, 404)
        embed.assert_not_called()

    def test_embedding_failures_return_502_without_details(self):
        with (
            patch.object(
                documents.document_vector_store,
                "document_collection_exists",
                return_value=True,
            ),
            patch.object(
                documents,
                "embed_query",
                side_effect=EmbeddingError("secret API detail"),
            ),
        ):
            response = client.post("/documents/retrieve", json=self.request_payload)

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret API detail", response.text)

    def test_vector_store_failures_return_a_generic_500(self):
        with (
            patch.object(
                documents.document_vector_store,
                "document_collection_exists",
                return_value=True,
            ),
            patch.object(documents, "embed_query", return_value=[0.1, 0.9]),
            patch.object(
                documents.document_vector_store,
                "query_document",
                side_effect=VectorStoreError("private Chroma details"),
            ),
        ):
            response = client.post("/documents/retrieve", json=self.request_payload)

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private Chroma details", response.text)


if __name__ == "__main__":
    unittest.main()
