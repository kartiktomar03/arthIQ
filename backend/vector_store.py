from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from qdrant_client import QdrantClient, models

COLLECTION = "authorized_schema"


@dataclass(frozen=True)
class VectorHit:
    document_id: str
    score: float


class VectorStore(Protocol):
    def count(self, datasource: str, version: str) -> int: ...
    def upsert(self, datasource: str, version: str, documents, vectors: list[list[float]]) -> None: ...
    def delete_stale(self, datasource: str, version: str) -> None: ...
    def search(self, datasource: str, version: str, vector: list[float], limit: int) -> list[VectorHit]: ...


class VectorUnavailable(RuntimeError):
    pass


def match(field: str, value: str) -> models.FieldCondition:
    from qdrant_client import models

    return models.FieldCondition(key=field, match=models.MatchValue(value=value))


def version_filter(datasource: str, version: str) -> models.Filter:
    from qdrant_client import models

    return models.Filter(must=[match("datasource_id", datasource), match("schema_version", version)])


class QdrantSchemaStore:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self.client = None

    def _client(self) -> QdrantClient:
        if self.client is None:
            from qdrant_client import QdrantClient

            options = {"location": ":memory:"} if self.path == ":memory:" else {"path": self.path}
            self.client = QdrantClient(**options, force_disable_check_same_thread=True)
        return self.client

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def count(self, datasource: str, version: str) -> int:
        client = self._client()
        if not client.collection_exists(COLLECTION):
            return 0
        return client.count(COLLECTION, count_filter=version_filter(datasource, version), exact=True).count

    def upsert(self, datasource: str, version: str, documents, vectors: list[list[float]]) -> None:
        from qdrant_client import models

        client = self._client()
        if not client.collection_exists(COLLECTION):
            client.create_collection(COLLECTION, vectors_config=models.VectorParams(
                size=len(vectors[0]), distance=models.Distance.COSINE,
            ))
        points = [
            models.PointStruct(
                id=document.point_id(datasource, version),
                vector=vector,
                payload={
                    "datasource_id": datasource, "schema_version": version,
                    "document_id": document.key, "table": document.table,
                    "source_type": document.source_type,
                },
            )
            for document, vector in zip(documents, vectors, strict=True)
        ]
        client.upsert(COLLECTION, points=points, wait=True)

    def delete_stale(self, datasource: str, version: str) -> None:
        from qdrant_client import models

        client = self._client()
        if not client.collection_exists(COLLECTION):
            return
        client.delete(
            COLLECTION, wait=True,
            points_selector=models.FilterSelector(filter=models.Filter(
                must=[match("datasource_id", datasource)],
                must_not=[match("schema_version", version)],
            )),
        )

    def search(self, datasource: str, version: str, vector: list[float], limit: int) -> list[VectorHit]:
        hits = self._client().query_points(
            COLLECTION, query=vector, query_filter=version_filter(datasource, version),
            limit=limit, with_payload=True,
        ).points
        return [VectorHit(point.payload["document_id"], point.score) for point in hits if point.payload]
