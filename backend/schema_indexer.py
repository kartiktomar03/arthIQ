from dataclasses import dataclass
from hashlib import sha256
import json
from uuid import NAMESPACE_URL, uuid5

from .catalog import SCHEMA
from .embedding_service import Embedder, EmbeddingUnavailable
from .schema_context import SchemaSnapshot, TABLE_ALIASES, TERMS
from .vector_store import VectorStore, VectorUnavailable


@dataclass(frozen=True)
class SchemaDocument:
    key: str
    table: str
    source_type: str
    text: str

    def point_id(self, datasource: str, version: str) -> str:
        return str(uuid5(NAMESPACE_URL, json.dumps([datasource, version, self.key])))


def documents_for(snapshot: SchemaSnapshot) -> tuple[SchemaDocument, ...]:
    docs = []
    for table, columns in sorted(snapshot.catalog.items()):
        aliases = ", ".join((TABLE_ALIASES if snapshot.aliases is None else snapshot.aliases).get(table, ()))
        fields = ", ".join(f"{name} {kind}" for name, kind in sorted(columns.items()))
        primary = ", ".join(snapshot.primary_keys.get(table, ()))
        docs.append(SchemaDocument(
            f"table:{table}", table, "table", f"{snapshot.schema}.{table}. Terms: {aliases}. Columns: {fields}. Primary key: {primary}",
        ))
        for name, kind in sorted(columns.items()):
            docs.append(SchemaDocument(
                f"column:{table}.{name}", table, "column",
                f"{snapshot.schema}.{table}.{name.replace('_', ' ')} is {kind}. Table terms: {aliases}.",
            ))
    for number, key in enumerate(sorted(set(snapshot.foreign_keys))):
        docs.append(SchemaDocument(
            f"relation:{number}", key.source, "relationship",
            f"Foreign key from {key.source} to {key.target}: {key.describe()}",
        ))
    for term in (TERMS if snapshot.glossary is None else snapshot.glossary):
        if term.is_available(snapshot):
            docs.append(SchemaDocument(
                f"term:{term.name}", ("order_items" if snapshot.schema == SCHEMA else next(iter(term.requirements))), "business_term",
                f"{', '.join(term.aliases)}. {term.definition}",
            ))
    return tuple(docs)


class SchemaIndexer:
    def __init__(self, embedder: Embedder, store: VectorStore, datasource: str):
        self.embedder = embedder
        self.store = store
        self.datasource = datasource
        self._ready: str | None = None

    def ensure(self, snapshot: SchemaSnapshot, force: bool = False) -> tuple[str, tuple[SchemaDocument, ...]]:
        documents = documents_for(snapshot)
        digest = sha256(json.dumps([snapshot.fingerprint(), self.embedder.identity, [
            (doc.key, doc.text) for doc in documents
        ]], ensure_ascii=False).encode()).hexdigest()

        if not force and self._ready == digest:
            return digest, documents
        try:
            if force or self.store.count(self.datasource, digest) != len(documents):
                for offset in range(0, len(documents), 16):
                    batch = documents[offset:offset + 16]
                    vectors = self.embedder.encode([doc.text for doc in batch])
                    self.store.upsert(self.datasource, digest, batch, vectors)
            self.store.delete_stale(self.datasource, digest)
        except EmbeddingUnavailable:
            raise
        except Exception:
            raise VectorUnavailable("The local schema index is unavailable. Check its path and process lock.") from None
        self._ready = digest
        return digest, documents
