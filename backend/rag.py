"""Schema index lifecycle and a local maintenance command."""

import argparse
import asyncio

import asyncpg

from .config import Settings
from .database import AnalyticsDatabase
from .embedding_service import EmbeddingUnavailable, MiniLMEmbedder
from .models import QueryFailure
from .schema_indexer import SchemaIndexer
from .schema_retriever import SchemaRetriever
from .vector_store import QdrantSchemaStore, VectorUnavailable


def create_retriever(settings: Settings) -> tuple[QdrantSchemaStore, SchemaRetriever]:
    store = QdrantSchemaStore(settings.qdrant_path)
    indexer = SchemaIndexer(
        MiniLMEmbedder(settings.embedding_local_files_only), store, settings.schema_datasource_id,
    )
    return store, SchemaRetriever(indexer, settings.schema_top_k, settings.schema_min_similarity)


async def index_schema(settings: Settings, force: bool) -> tuple[str, int]:
    if not settings.analytics_dsn or not settings.analytics_dsn.get_secret_value():
        raise QueryFailure(503, "configuration_required", "Set ANALYTICS_DSN before indexing.")
    store, retriever = create_retriever(settings)
    try:
        async with asyncpg.create_pool(
            settings.analytics_dsn.get_secret_value(), min_size=0, max_size=1,
            timeout=3, command_timeout=5,
        ) as pool:
            db = AnalyticsDatabase(pool, settings.query_timeout_ms, settings.max_rows, settings.max_response_bytes)
            snapshot = await db.schema_snapshot()
        return await asyncio.to_thread(retriever.index, snapshot, force)
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reindex", action="store_true", help="Regenerate current schema embeddings.")
    args = parser.parse_args()
    try:
        version, count = asyncio.run(index_schema(Settings(), args.reindex))
    except (QueryFailure, EmbeddingUnavailable, VectorUnavailable) as error:
        parser.exit(1, f"{error}\n")
    print(f"Indexed {count} authorized schema documents. Version {version[:12]}.")


if __name__ == "__main__":
    main()
