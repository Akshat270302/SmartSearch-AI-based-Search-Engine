"""Ephemeral Chroma storage for document chunk embeddings."""

import math

import chromadb


MAX_VECTOR_INSERT_BATCH_SIZE = 5_000


class VectorStoreError(RuntimeError):
    """Raised when document vectors cannot be safely stored or read."""


class DocumentCollectionNotFoundError(VectorStoreError):
    """Raised when the requested document has no vector collection."""


class InMemoryDocumentVectorStore:
    """Store document vectors in Chroma's in-memory client only."""

    def __init__(self, client=None):
        self._client = client if client is not None else chromadb.Client()

    @staticmethod
    def _collection_name(document_id: str) -> str:
        if not isinstance(document_id, str) or not document_id.strip():
            raise VectorStoreError("A nonempty document_id is required.")
        # UUID-based extraction IDs become valid, document-scoped Chroma names.
        safe_id = "".join(
            char.lower() if char.isalnum() or char in "-_" else "-"
            for char in document_id
        )
        return f"doc-{safe_id}"[:63]

    def create_document_collection(self, document_id: str):
        name = self._collection_name(document_id)
        try:
            collection = self._client.get_or_create_collection(
                name=name,
                metadata={"document_id": document_id},
            )
            if (collection.metadata or {}).get("document_id") != document_id:
                raise VectorStoreError(
                    "The collection name is already associated with another document."
                )
            return collection
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("Could not create the document vector collection.") from exc

    def insert_chunks(
        self,
        document_id: str,
        embedded_chunks: list[dict],
        *,
        filename: str,
    ) -> list[str]:
        """Insert ordered embedding records returned by ``embed_chunks``."""

        if not embedded_chunks:
            return []
        ids, documents, embeddings, metadatas = [], [], [], []
        seen_indices = set()
        for record in embedded_chunks:
            try:
                chunk = record["chunk"]
                text = chunk["text"]
                index = chunk["chunk_index"]
                vector = record["embedding"]
                if not isinstance(text, str) or not text:
                    raise ValueError("empty chunk text")
                if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                    raise ValueError("invalid chunk index")
                if index in seen_indices:
                    raise ValueError("duplicate chunk index")
                seen_indices.add(index)
                if not isinstance(vector, (list, tuple)) or not vector:
                    raise ValueError("empty embedding")
                if any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    for value in vector
                ):
                    raise ValueError("invalid embedding")
                metadata = {
                    "document_id": document_id,
                    "chunk_index": index,
                    "start_char": int(chunk["start_char"]),
                    "end_char": int(chunk["end_char"]),
                    "filename": str(filename),
                }
                page_number = chunk.get("page_number")
                if page_number is not None:
                    if (
                        isinstance(page_number, bool)
                        or not isinstance(page_number, int)
                        or page_number < 1
                    ):
                        raise ValueError("invalid page number")
                    metadata["page_number"] = page_number
                ids.append(f"{document_id}-chunk-{index:08d}")
                documents.append(text)
                embeddings.append([float(value) for value in vector])
                metadatas.append(metadata)
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise VectorStoreError("Chunk or embedding data is invalid.") from exc

        if len({len(vector) for vector in embeddings}) != 1:
            raise VectorStoreError(
                "Embedding dimensions must match within a document collection."
            )
        try:
            collection = self.create_document_collection(document_id)
            existing_ids = set(collection.get(ids=ids)["ids"])
            if existing_ids:
                raise VectorStoreError(
                    "One or more chunk IDs already exist in this document collection."
                )
            batch_size = min(
                MAX_VECTOR_INSERT_BATCH_SIZE,
                self._client.get_max_batch_size(),
            )
            for start in range(0, len(ids), batch_size):
                end = start + batch_size
                collection.add(
                    ids=ids[start:end],
                    embeddings=embeddings[start:end],
                    documents=documents[start:end],
                    metadatas=metadatas[start:end],
                )
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("Could not insert document chunks into Chroma.") from exc
        return ids

    def get_document_records(self, document_id: str) -> list[dict]:
        """Return stored chunk records, normalizing omitted TXT page values to None."""

        try:
            collection = self._client.get_collection(self._collection_name(document_id))
            stored = collection.get(include=["documents", "metadatas", "embeddings"])
        except Exception as exc:
            raise VectorStoreError("Could not read the document vector collection.") from exc
        records = []
        for index, record_id in enumerate(stored["ids"]):
            metadata = stored["metadatas"][index]
            records.append(
                {
                    "id": record_id,
                    "text": stored["documents"][index],
                    "embedding": stored["embeddings"][index].tolist()
                    if hasattr(stored["embeddings"][index], "tolist")
                    else list(stored["embeddings"][index]),
                    "metadata": {
                        **metadata,
                        "page_number": metadata.get("page_number"),
                    },
                }
            )
        return records

    def document_collection_exists(self, document_id: str) -> bool:
        """Check for the requested document without creating a collection."""

        try:
            collection = self._client.get_collection(
                self._collection_name(document_id)
            )
        except chromadb.errors.NotFoundError:
            return False
        except Exception as exc:
            raise VectorStoreError(
                "Could not inspect the document vector collection."
            ) from exc
        stored_document_id = (collection.metadata or {}).get("document_id")
        return stored_document_id == document_id

    def query_document(
        self,
        document_id: str,
        query_embedding: list[float],
        *,
        top_k: int = 5,
    ) -> list[dict]:
        """Return nearest chunks and their stored metadata in Chroma order.

        Chroma's existing collection distance metric is used without changing
        collection configuration. Returned ``distance`` values are lower for
        closer matches under the collection's metric.
        """

        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise VectorStoreError("top_k must be a positive integer.")
        if (
            not isinstance(query_embedding, (list, tuple))
            or not query_embedding
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in query_embedding
            )
        ):
            raise VectorStoreError("The query embedding is invalid.")

        try:
            collection = self._client.get_collection(
                self._collection_name(document_id)
            )
        except chromadb.errors.NotFoundError as exc:
            raise DocumentCollectionNotFoundError(
                "The document vector collection was not found."
            ) from exc
        except Exception as exc:
            raise VectorStoreError(
                "Could not access the document vector collection."
            ) from exc

        stored_document_id = (collection.metadata or {}).get("document_id")
        if stored_document_id != document_id:
            raise DocumentCollectionNotFoundError(
                "The document vector collection was not found."
            )

        try:
            if collection.count() == 0:
                return []
            result = collection.query(
                query_embeddings=[[float(value) for value in query_embedding]],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise VectorStoreError("Could not retrieve document chunks from Chroma.") from exc

        ids = (result.get("ids") or [[]])[0] or []
        documents = (result.get("documents") or [[]])[0] or []
        metadatas = (result.get("metadatas") or [[]])[0] or []
        distances = (result.get("distances") or [[]])[0] or []
        if not ids:
            return []
        if not (
            len(ids) == len(documents) == len(metadatas) == len(distances)
        ):
            raise VectorStoreError("Chroma returned incomplete retrieval records.")

        records = []
        for text, metadata, distance in zip(documents, metadatas, distances):
            record = {
                key: metadata[key]
                for key in (
                    "chunk_index",
                    "page_number",
                    "start_char",
                    "end_char",
                    "document_id",
                    "filename",
                )
                if key in metadata
            }
            # Phase 3 omits null page values because Chroma metadata cannot
            # store null; missing page_number represents a TXT chunk.
            record.setdefault("page_number", None)
            record["text"] = text
            record["distance"] = float(distance)
            records.append(record)
        return records

    def delete_document_collection(self, document_id: str) -> bool:
        """Delete one document's collection; return False if it did not exist."""

        name = self._collection_name(document_id)
        try:
            collection = self._client.get_collection(name)
        except chromadb.errors.NotFoundError:
            return False
        except Exception as exc:
            raise VectorStoreError(
                "Could not inspect the document vector collection before deletion."
            ) from exc
        if (collection.metadata or {}).get("document_id") != document_id:
            return False
        try:
            self._client.delete_collection(name)
            return True
        except Exception as exc:
            raise VectorStoreError("Could not delete the document vector collection.") from exc
