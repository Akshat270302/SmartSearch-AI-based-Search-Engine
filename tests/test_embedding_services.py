import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

os.environ.setdefault("GEMINI_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import main
from services.embedding_service import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingError,
    embed_chunks,
)
from services.vector_store import InMemoryDocumentVectorStore, VectorStoreError


def chunk(index, text, page_number=None):
    return {
        "chunk_index": index,
        "text": text,
        "page_number": page_number,
        "start_char": index * 10,
        "end_char": index * 10 + len(text),
    }


class EmbeddingServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.models.embed_content.return_value = SimpleNamespace(
            embeddings=[
                SimpleNamespace(values=[0.1, 0.2]),
                SimpleNamespace(values=[0.3, 0.4]),
            ]
        )

    def test_generates_ordered_embeddings_with_configured_model(self):
        chunks = [chunk(0, "First"), chunk(1, "Second")]
        embedded = embed_chunks(chunks, client=self.client, model="test-embedding")

        self.assertEqual([item["chunk"] for item in embedded], chunks)
        self.assertEqual(
            [item["embedding"] for item in embedded],
            [[0.1, 0.2], [0.3, 0.4]],
        )
        self.client.models.embed_content.assert_called_once_with(
            model="test-embedding", contents=["First", "Second"]
        )

    def test_uses_documented_default_model(self):
        self.client.models.embed_content.return_value = SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1, 0.2])]
        )
        embed_chunks([chunk(0, "Text")], client=self.client)
        self.client.models.embed_content.assert_called_once_with(
            model=DEFAULT_EMBEDDING_MODEL, contents=["Text"]
        )

    def test_embedding_model_can_be_configured_through_environment(self):
        self.client.models.embed_content.return_value = SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1])]
        )
        with patch.dict(os.environ, {"GEMINI_EMBEDDING_MODEL": "env-model"}):
            embed_chunks([chunk(0, "Text")], client=self.client)
        self.client.models.embed_content.assert_called_once_with(
            model="env-model", contents=["Text"]
        )

    def test_large_chunk_lists_are_batched_without_reordering(self):
        chunks = [chunk(index, f"Text {index}") for index in range(101)]

        def embed_content(*, model, contents):
            return SimpleNamespace(
                embeddings=[
                    SimpleNamespace(values=[float(text.rsplit(" ", 1)[1])])
                    for text in contents
                ]
            )

        self.client.models.embed_content.side_effect = embed_content
        embedded = embed_chunks(chunks, client=self.client)

        self.assertEqual(len(embedded), 101)
        self.assertEqual(
            [item["chunk"]["chunk_index"] for item in embedded],
            list(range(101)),
        )
        self.assertEqual(embedded[-1]["embedding"], [100.0])
        self.assertEqual(self.client.models.embed_content.call_count, 2)

    def test_skips_empty_text_and_preserves_whitespace_chunk_association(self):
        chunks = [chunk(0, "First"), chunk(1, ""), chunk(2, " \n "), chunk(3, "Third")]
        self.client.models.embed_content.return_value = SimpleNamespace(
            embeddings=[
                SimpleNamespace(values=[0.1, 0.2]),
                SimpleNamespace(values=[0.3, 0.4]),
                SimpleNamespace(values=[0.5, 0.6]),
            ]
        )
        embedded = embed_chunks(chunks, client=self.client)

        self.assertEqual(
            [item["chunk"]["chunk_index"] for item in embedded], [0, 2, 3]
        )
        self.client.models.embed_content.assert_called_once_with(
            model=DEFAULT_EMBEDDING_MODEL, contents=["First", " \n ", "Third"]
        )

    def test_empty_input_does_not_call_api(self):
        self.assertEqual(embed_chunks([], client=self.client), [])
        self.assertEqual(embed_chunks([chunk(0, "")], client=self.client), [])
        self.client.models.embed_content.assert_not_called()

    def test_embedding_api_failures_are_wrapped_without_response_details(self):
        self.client.models.embed_content.side_effect = RuntimeError("private detail")
        with self.assertRaisesRegex(EmbeddingError, "request failed") as context:
            embed_chunks([chunk(0, "Text")], client=self.client)
        self.assertNotIn("private detail", str(context.exception))

    def test_rejects_missing_key_without_constructing_client(self):
        with patch("services.embedding_service.load_dotenv"), patch.dict(
            os.environ, {"GEMINI_API_KEY": ""}
        ), patch("services.embedding_service.genai.Client") as client_factory:
            with self.assertRaisesRegex(EmbeddingError, "GEMINI_API_KEY"):
                embed_chunks([chunk(0, "Text")])
        client_factory.assert_not_called()

    def test_rejects_malformed_embeddings_and_dimension_mismatch(self):
        self.client.models.embed_content.return_value = SimpleNamespace(embeddings=[])
        with self.assertRaises(EmbeddingError):
            embed_chunks([chunk(0, "Text")], client=self.client)

        self.client.models.embed_content.return_value = SimpleNamespace(
            embeddings=[SimpleNamespace(values=[1]), SimpleNamespace(values=[1, 2])]
        )
        with self.assertRaisesRegex(EmbeddingError, "inconsistent dimensions"):
            embed_chunks([chunk(0, "One"), chunk(1, "Two")], client=self.client)


class ChromaVectorStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryDocumentVectorStore()
        self.document_prefix = uuid4().hex

    def test_creates_collection_and_stores_pdf_and_txt_metadata(self):
        document_id = f"{self.document_prefix}-pdf"
        collection = self.store.create_document_collection(document_id)
        self.assertEqual(collection.name, f"doc-{document_id}")

        records = [
            {"chunk": chunk(0, "PDF text", 3), "embedding": [0.1, 0.2]},
            {"chunk": chunk(1, "TXT text", None), "embedding": [0.3, 0.4]},
        ]
        ids = self.store.insert_chunks(document_id, records, filename="notes.txt")
        self.assertEqual(
            ids,
            [
                f"{document_id}-chunk-00000000",
                f"{document_id}-chunk-00000001",
            ],
        )
        stored = self.store.get_document_records(document_id)

        self.assertEqual([record["id"] for record in stored], ids)
        self.assertEqual([record["text"] for record in stored], ["PDF text", "TXT text"])
        self.assertEqual(stored[0]["metadata"]["document_id"], document_id)
        self.assertEqual(stored[0]["metadata"]["chunk_index"], 0)
        self.assertEqual(stored[0]["metadata"]["page_number"], 3)
        self.assertEqual(stored[0]["metadata"]["start_char"], 0)
        self.assertEqual(stored[0]["metadata"]["end_char"], 8)
        self.assertEqual(stored[0]["metadata"]["filename"], "notes.txt")
        self.assertIsNone(stored[1]["metadata"]["page_number"])

    def test_chunk_ids_are_unique_and_documents_are_isolated(self):
        records = [{"chunk": chunk(0, "Text"), "embedding": [0.1, 0.2]}]
        first_id = f"{self.document_prefix}-one"
        second_id = f"{self.document_prefix}-two"
        first_ids = self.store.insert_chunks(first_id, records, filename="one.txt")
        second_ids = self.store.insert_chunks(second_id, records, filename="two.txt")

        self.assertEqual(len(first_ids), len(set(first_ids)))
        self.assertEqual(len(second_ids), len(set(second_ids)))
        self.assertNotEqual(first_ids, second_ids)
        self.assertEqual(self.store.get_document_records(first_id)[0]["text"], "Text")
        self.assertEqual(self.store.get_document_records(second_id)[0]["text"], "Text")
        self.assertNotEqual(
            self.store._collection_name(first_id),
            self.store._collection_name(second_id),
        )

    def test_deletes_only_requested_collection(self):
        records = [{"chunk": chunk(0, "Text"), "embedding": [0.1]}]
        first_id = f"{self.document_prefix}-one"
        second_id = f"{self.document_prefix}-two"
        self.store.insert_chunks(first_id, records, filename="one.txt")
        self.store.insert_chunks(second_id, records, filename="two.txt")

        self.assertTrue(self.store.delete_document_collection(first_id))
        self.assertFalse(self.store.delete_document_collection(first_id))
        self.assertEqual(len(self.store.get_document_records(second_id)), 1)

    def test_rejects_reinserting_an_existing_stable_chunk_id(self):
        records = [{"chunk": chunk(0, "Text"), "embedding": [0.1]}]
        document_id = f"{self.document_prefix}-repeat"
        self.store.insert_chunks(document_id, records, filename="notes.txt")

        with self.assertRaisesRegex(VectorStoreError, "already exist"):
            self.store.insert_chunks(document_id, records, filename="notes.txt")

    def test_delete_does_not_remove_a_collection_owned_by_another_document(self):
        owner_id = f"{self.document_prefix}/same"
        other_id = f"{self.document_prefix}?same"
        self.store.create_document_collection(owner_id)

        self.assertFalse(self.store.delete_document_collection(other_id))
        self.assertTrue(self.store.document_collection_exists(owner_id))

    def test_rejects_duplicate_indices_and_inconsistent_dimensions(self):
        duplicated = [
            {"chunk": chunk(0, "One"), "embedding": [0.1]},
            {"chunk": chunk(0, "Two"), "embedding": [0.2]},
        ]
        with self.assertRaisesRegex(VectorStoreError, "invalid"):
            self.store.insert_chunks("doc-duplicate", duplicated, filename="x.txt")

        mismatched = [
            {"chunk": chunk(0, "One"), "embedding": [0.1]},
            {"chunk": chunk(1, "Two"), "embedding": [0.2, 0.3]},
        ]
        with self.assertRaisesRegex(VectorStoreError, "dimensions"):
            self.store.insert_chunks("doc-dimensions", mismatched, filename="x.txt")


class ExistingEndpointCompatibilityTests(unittest.TestCase):
    def test_extraction_and_existing_routes_remain_independent(self):
        paths = main.app.openapi()["paths"]
        self.assertIn("/documents/extract", paths)
        self.assertIn("/search", paths)
        self.assertIn("/ask", paths)
        self.assertIn("/ask/stream", paths)
        self.assertIn("/ask/stream/context", paths)
        self.assertFalse(hasattr(main, "embed_chunks"))
        self.assertFalse(hasattr(main, "InMemoryDocumentVectorStore"))

        from fastapi.testclient import TestClient

        with patch("routers.documents.embed_chunks") as generate_embeddings:
            generate_embeddings.side_effect = lambda chunks: [
                {"chunk": item, "embedding": [0.1]}
                for item in chunks
            ]
            response = TestClient(main.app).post(
                "/documents/extract",
                files={"file": ("notes.txt", b"Extracted text", "text/plain")},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "Extracted text")
        generate_embeddings.assert_called_once()

    def test_search_and_grounded_answer_routes_still_call_their_services(self):
        results = [{"title": "Example", "url": "https://example.test", "snippet": "Evidence"}]
        filters = {"time_range": "all", "category": None, "engine": None, "warnings": []}
        with (
            patch.object(
                main,
                "resolve_filters",
                new_callable=AsyncMock,
                return_value=({}, filters),
            ),
            patch.object(
                main,
                "fetch_search_results",
                new_callable=AsyncMock,
                return_value=results,
            ) as search_provider,
            patch.object(
                main,
                "generate_grounded_answer",
                return_value={"summary": "Grounded answer", "citations": []},
            ) as answer_generator,
        ):
            from fastapi.testclient import TestClient

            client = TestClient(main.app)
            search_response = client.get("/search", params={"q": "test"})
            answer_response = client.get("/ask", params={"q": "test"})

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()["results"], results)
        self.assertEqual(answer_response.status_code, 200)
        self.assertEqual(answer_response.json()["summary"], "Grounded answer")
        self.assertEqual(search_provider.await_count, 2)
        answer_generator.assert_called_once_with("test", results)


if __name__ == "__main__":
    unittest.main()
