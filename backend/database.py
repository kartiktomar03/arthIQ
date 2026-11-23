from dataclasses import replace
from .datasources import DEMO, OLIST_TABLES, Profile
import asyncio
import json
from datetime import date, datetime
from decimal import Decimal
from time import perf_counter

import asyncpg

from .catalog import CATALOG_SQL, SCHEMA, TABLES, Catalog
from .models import ExecutionMetadata, QueryFailure, QueryResponse
from .schema_context import SchemaSnapshot
from .schema_discovery import KEY_SQL, build_snapshot
from .sql_policy import ApprovedQuery


class AnalyticsDatabase:
    def __init__(self, pool: asyncpg.Pool, timeout_ms: int, max_rows: int, max_bytes: int, profile: Profile = DEMO):
        self.profile = profile
        self.pool = pool
        self.timeout_ms = timeout_ms
        self.max_rows = max_rows
        self.max_bytes = max_bytes

    async def catalog(self) -> Catalog:
        return (await self._discover(include_keys=False)).catalog

    async def schema_snapshot(self) -> SchemaSnapshot:
        return await self._discover(include_keys=True)

    async def _discover(self, include_keys: bool) -> SchemaSnapshot:
        try:
            async with self.pool.acquire(timeout=3) as conn:
                async with conn.transaction(readonly=True, isolation="repeatable_read"):
                    if await conn.fetchval("SELECT current_user WHERE current_database()=$1 AND session_user=current_user", self.profile.database) != self.profile.role:
                        raise QueryFailure(503, "database_role", "Use the dedicated analytics login.")
                    names = list(TABLES if self.profile == DEMO else OLIST_TABLES)
                    columns = await conn.fetch(CATALOG_SQL, self.profile.namespace, names, timeout=3)
                    keys = await conn.fetch(KEY_SQL, self.profile.namespace, names, timeout=3) if include_keys else []
        except (TimeoutError, OSError, asyncpg.PostgresError, asyncpg.InterfaceError):
            raise QueryFailure(503, "database_unavailable", "Could not read the analytics catalog.") from None

        catalog: Catalog = {}
        for column in columns:
            catalog.setdefault(column["table_name"], {})[column["column_name"]] = column["data_type"]
        if not catalog and not include_keys:
            raise QueryFailure(503, "empty_catalog", "No shop tables are visible. Check the seed and analytics grants.")
        return replace(build_snapshot(catalog, keys), schema=self.profile.namespace,
                       glossary=self.profile.terms(), aliases=self.profile.aliases)

    async def execute(self, query: ApprovedQuery) -> QueryResponse:
        try:
            async with self.pool.acquire(timeout=3) as conn:
                start = perf_counter()
                async with asyncio.timeout(self.timeout_ms / 1000 + 0.5):
                    async with conn.transaction(readonly=True):
                        await conn.execute("SET LOCAL search_path = pg_catalog")
                        await conn.execute(
                            "SELECT pg_catalog.set_config('statement_timeout', $1, true), "
                            "pg_catalog.set_config('lock_timeout', $2, true)",
                            f"{self.timeout_ms}ms", f"{min(self.timeout_ms, 500)}ms",
                        )
                        if await conn.fetchval("SELECT current_user WHERE current_database()=$1 AND session_user=current_user", self.profile.database) != self.profile.role:
                            raise QueryFailure(503, "database_role", "Use the dedicated analytics login.")
                        statement = await conn.prepare(query.sql)
                        attributes = statement.get_attributes()
                        columns = [attribute.name for attribute in attributes]
                        types = [getattr(getattr(a, "type", None), "name", "unknown") for a in attributes]
                        rows, truncated = await self._collect(await statement.cursor(), columns)
        except (TimeoutError, asyncpg.QueryCanceledError, asyncpg.LockNotAvailableError):
            raise QueryFailure(504, "query_timeout", "Database time limit reached. Try a narrower question.") from None
        except (OSError, asyncpg.PostgresConnectionError, asyncpg.InterfaceError):
            raise QueryFailure(503, "database_unavailable", "Could not connect to the analytics database.") from None
        except asyncpg.PostgresError:
            raise QueryFailure(422, "query_failed", "PostgreSQL could not run the approved query. Try rephrasing.") from None

        return QueryResponse(
            sql=query.sql,
            columns=columns,
            column_types=types,
            rows=rows,
            execution=ExecutionMetadata(
                duration_ms=round((perf_counter() - start) * 1000, 2),
                row_count=len(rows),
                truncated=truncated,
            ),
        )

    async def _collect(self, cursor, columns: list[str]) -> tuple[list, bool]:
        rows = []
        used = json_size(columns)
        while True:
            batch_size = min(16, self.max_rows + 1 - len(rows))
            batch = await cursor.fetch(batch_size)
            for record in batch:
                row = [json_value(value) for value in record]
                used += json_size(row) + 1
                if len(rows) == self.max_rows or used > self.max_bytes:
                    return rows, True
                rows.append(row)
            if len(batch) < batch_size:
                return rows, False


def json_size(value: list) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
