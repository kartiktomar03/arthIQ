from dataclasses import dataclass
import math
import re
from threading import Lock
from time import perf_counter

from .embedding_service import EmbeddingUnavailable
from .models import QueryFailure, RetrievalDiagnostics, RetrievalSource
from .relationship_graph import RelationshipGraph, UnresolvedJoin
from .schema_context import TABLE_ALIASES, TERMS, SchemaContext, SchemaSnapshot
from .schema_indexer import SchemaIndexer
from .vector_store import VectorUnavailable

GENERIC_COLUMNS = {"id", "name", "status", "price"}
QUALIFIED_COLUMN = re.compile(r"(?<![\w.])(?:shop\.)?([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)(?![\w.])")


def terms(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    normalized = [
        word[:-3] + "y" if word.endswith("ies") else
        word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith(("us", "ss")) else word
        for word in words
    ]
    return " " + " ".join(normalized) + " "


def contains(normalized: str, candidate: str) -> bool:
    return terms(candidate) in normalized


@dataclass(frozen=True)
class Retrieval:
    context: SchemaContext
    diagnostics: RetrievalDiagnostics
    selected: tuple[str, ...]


class SchemaRetriever:
    def __init__(self, indexer: SchemaIndexer, top_k: int, min_similarity: float, lock=None):
        self.indexer = indexer
        self.top_k = top_k
        self.min_similarity = min_similarity
        self.lock = lock or Lock()

    def index(self, snapshot: SchemaSnapshot, force: bool = False) -> tuple[str, int]:
        with self.lock:
            version, documents = self.indexer.ensure(snapshot, force)
            return version, len(documents)

    def retrieve(self, question: str, snapshot: SchemaSnapshot) -> Retrieval:
        start = perf_counter()
        try:
            with self.lock:
                return self._retrieve(question, snapshot, start)
        except (EmbeddingUnavailable, VectorUnavailable) as error:
            code = "embedding_unavailable" if isinstance(error, EmbeddingUnavailable) else "vector_unavailable"
            raise QueryFailure(503, code, str(error), self._failed(start)) from None
        except UnresolvedJoin as error:
            raise QueryFailure(422, "schema_clarification", str(error), self._failed(start)) from None

    @staticmethod
    def _failed(start: float) -> RetrievalDiagnostics:
        return RetrievalDiagnostics(mode="rag", status="failed", duration_ms=round((perf_counter() - start) * 1000, 2))

    def _retrieve(self, question: str, snapshot: SchemaSnapshot, start: float) -> Retrieval:
        if not snapshot.catalog:
            self.indexer.ensure(snapshot)
            raise QueryFailure(
                503, "empty_catalog", "No shop tables are visible to the analytics role.", self._failed(start),
            )
        normalized = terms(question)
        matched_terms = tuple(
            term for term in (TERMS if snapshot.glossary is None else snapshot.glossary)
            if any(contains(normalized, name) for name in (term.name, *term.aliases))
        )
        if any(contains(normalized, word) for word in ("best", "performance", "top", "highest", "lowest")) and not (
            matched_terms or any(contains(normalized, word) for word in ("price", "count", "number", "quantity", "units", "most orders"))
        ):
            raise UnresolvedJoin("Specify how to rank the results, for example by revenue, price, or order count.")
        for term in matched_terms:
            if not term.is_available(snapshot):
                raise UnresolvedJoin(f"The permitted schema lacks the fields or join needed to calculate {term.name}.")
        metric_tables = {table for term in matched_terms for table in term.requirements}

        version, documents = self.indexer.ensure(snapshot)
        vector, = self.indexer.embedder.encode([question])
        try:
            hits = self.indexer.store.search(self.indexer.datasource, version, vector, min(40, max(12, self.top_k * 8)))
        except Exception:
            raise VectorUnavailable("Schema search could not read the local vector index.") from None
        by_key = {doc.key: doc for doc in documents}
        semantic = {}
        dense = dict.fromkeys(snapshot.catalog, -1.0)
        for hit in hits:
            document = by_key.get(hit.document_id)
            if document is not None and math.isfinite(hit.score):
                semantic[hit.document_id] = hit.score
                if document.source_type in {"table", "column"}:
                    dense[document.table] = max(dense[document.table], hit.score)

        lexical = {}
        qualified_columns = set(QUALIFIED_COLUMN.findall(question.lower()))
        no_orders = contains(normalized, "never ordered")
        for table, columns in snapshot.catalog.items():
            names = (table, *(TABLE_ALIASES if snapshot.aliases is None else snapshot.aliases).get(table, ()))
            entity_text = re.sub(r"\border item\b", " ", normalized) if table == "orders" else normalized
            score = max((2.0 if name == table else 1.2 for name in names if contains(entity_text, name)), default=0.0)
            for column in columns:
                if (table, column) in qualified_columns:
                    score = max(score, 3.0)
                elif column not in GENERIC_COLUMNS and not column.endswith("_id") and contains(normalized, column):
                    score = max(score, 1.5)
            if table in metric_tables:
                score = max(score, 2.5)
            if snapshot.schema == "shop" and no_orders and table == "order_items" and "products" in snapshot.catalog:
                score = max(score, 2.5)
            if score:
                lexical[table] = score

        ranked = sorted(snapshot.catalog, key=lambda table: (
            -(lexical.get(table, 0.0) + 0.65 * max(0.0, dense[table])), table,
        ))
        if lexical:
            selected = [table for table in ranked if table in lexical][:self.top_k]
            if not metric_tables <= set(selected):
                raise UnresolvedJoin("The retrieval limit is too small for the requested metric definition.")
        else:
            plausible = sorted(
                (table for table in ranked if dense[table] >= self.min_similarity),
                key=lambda table: (-dense[table], table),
            )
            if not plausible or (len(plausible) > 1 and dense[plausible[0]] - dense[plausible[1]] < 0.035):
                raise UnresolvedJoin("Mention a shop entity or metric, such as products, customer orders, or revenue.")
            selected = plausible[:1]

        tables, edges = RelationshipGraph(snapshot).expand(selected)
        if any(score >= 2 and table not in tables for table, score in lexical.items()):
            raise UnresolvedJoin("The retrieval limit cannot include every requested table. Narrow the question.")
        context = SchemaContext(
            {table: snapshot.catalog[table] for table in sorted(tables)},
            {table: snapshot.primary_keys[table] for table in tables if table in snapshot.primary_keys},
            edges, matched_terms, snapshot.schema,
        )
        # Context always comes from the live catalog. Vector payloads only carry ranking IDs.
        evidence = sorted(
            (doc for doc in documents if doc.table in tables and doc.key in semantic),
            key=lambda doc: (-semantic[doc.key], doc.key),
        )[:12]
        sources = [
            RetrievalSource(
                document_id=doc.key, table=doc.table, source_type=doc.source_type,
                score=round(semantic[doc.key], 4),
            )
            for doc in evidence
        ]
        diagnostics = RetrievalDiagnostics(
            mode="rag", status="ok", tables=sorted(tables), document_count=len(sources),
            seed_tables=selected,
            expanded=tables != set(selected), join_count=len(edges),
            relationships=[edge.describe() for edge in edges],
            duration_ms=round((perf_counter() - start) * 1000, 2),
            datasource_id=self.indexer.datasource, schema_version=version, sources=sources,
        )
        return Retrieval(context, diagnostics, tuple(selected))
