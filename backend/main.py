import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from time import perf_counter
from typing import Protocol

import asyncpg
import groq
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .olist import reader_pool
from .schema_indexer import SchemaIndexer
from .datasources import DEMO, OLIST
from .catalog import Catalog
from .config import Settings
from .database import AnalyticsDatabase
from .llm import GroqSQLGenerator, SQLGenerator
from .models import QueryFailure, QueryRequest, QueryResponse, RetrievalDiagnostics
from .schema_context import SchemaContext, SchemaSnapshot
from .schema_retriever import SchemaRetriever
from .rag import create_retriever
from .sql_policy import ApprovedQuery, validate_sql
from .presentation import present
from .workspace import routes


class QueryDatabase(Protocol):
    async def catalog(self) -> Catalog: ...
    async def schema_snapshot(self) -> SchemaSnapshot: ...
    async def execute(self, query: ApprovedQuery) -> QueryResponse: ...


def create_app(
    database: QueryDatabase | None = None,
    generator: SQLGenerator | None = None,
    retriever: SchemaRetriever | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = Settings()
        async with AsyncExitStack() as stack:
            db = database
            llm = generator
            if db is None and settings.analytics_dsn and settings.analytics_dsn.get_secret_value():
                pool = await stack.enter_async_context(asyncpg.create_pool(
                    settings.analytics_dsn.get_secret_value(), min_size=0, max_size=2,
                    timeout=3, command_timeout=5,
                ))
                db = AnalyticsDatabase(
                    pool, settings.query_timeout_ms, settings.max_rows, settings.max_response_bytes
                )
            if llm is None and settings.groq_api_key and settings.groq_api_key.get_secret_value():
                client = await stack.enter_async_context(groq.AsyncGroq(
                    api_key=settings.groq_api_key.get_secret_value(), timeout=15, max_retries=0,
                ))
                llm = GroqSQLGenerator(client, settings.groq_model)
            app.state.database = db
            app.state.datasource = settings.schema_datasource_id
            app.state.workspace = None
            if settings.workspace_dsn and settings.workspace_dsn.get_secret_value():
                async def verify_workspace_role(conn):
                    if await conn.fetchval("SELECT current_user") != "querypilot_workspace":
                        raise QueryFailure(503, "workspace_role", "Use the dedicated workspace login.")
                app.state.workspace = await stack.enter_async_context(asyncpg.create_pool(
                    settings.workspace_dsn.get_secret_value(), min_size=0, max_size=2,
                    timeout=3, command_timeout=5, init=verify_workspace_role,
                ))
            app.state.generator = llm
            app.state.retriever = None
            if settings.schema_mode == "rag":
                if retriever is None:
                    store, schema_retriever = create_retriever(settings)
                    stack.callback(store.close)
                    app.state.retriever = schema_retriever
                else:
                    app.state.retriever = retriever
            app.state.slots = asyncio.Semaphore(2)
            app.state.olist = None
            app.state.olist_retriever = None
            if settings.olist_analytics_dsn and settings.olist_analytics_dsn.get_secret_value():
                pool = await stack.enter_async_context(reader_pool(settings.olist_analytics_dsn.get_secret_value()))
                app.state.olist = AnalyticsDatabase(pool, settings.query_timeout_ms, settings.max_rows,
                                                   settings.max_response_bytes, OLIST)
                base = app.state.retriever
                if base:
                    if base.indexer.datasource == OLIST.id:
                        raise ValueError("Demo and Olist vector namespaces must differ.")
                    index = SchemaIndexer(base.indexer.embedder, base.indexer.store, OLIST.id)
                    app.state.olist_retriever = SchemaRetriever(index, base.top_k, base.min_similarity, base.lock)
            yield

    app = FastAPI(title="QueryPilot AI", lifespan=lifespan)

    @app.exception_handler(QueryFailure)
    async def query_failure(_request: Request, error: QueryFailure):
        content = {"error": {"code": error.code, "message": str(error)}}
        if error.retrieval is not None:
            content["retrieval"] = error.retrieval.model_dump(mode="json")
        return JSONResponse(
            status_code=error.status,
            content=content,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_question(request: Request, _error: RequestValidationError):
        return await query_failure(
            request, QueryFailure(422, "invalid_question", "Enter a question between 1 and 1000 characters.")
        )

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.post("/api/query", response_model=QueryResponse)
    async def query(body: QueryRequest, request: Request):
        if body.datasource_id in (None, DEMO.id):
            profile, db, schema_retriever = DEMO, app.state.database, app.state.retriever
        elif body.datasource_id == OLIST.id:
            profile, db, schema_retriever = OLIST, app.state.olist, app.state.olist_retriever
            if db is None:
                raise QueryFailure(503, "datasource_unconfigured", "Configure OLIST_ANALYTICS_DSN locally.")
        else:
            raise QueryFailure(422, "unknown_datasource", "Unknown analytics datasource.")
        llm = request.app.state.generator
        if db is None or llm is None:
            raise QueryFailure(503, "configuration_required", "Set ANALYTICS_DSN and GROQ_API_KEY on the server.")

        slots = request.app.state.slots
        if slots.locked():
            raise QueryFailure(429, "server_busy", "Two queries are already in progress. Try again shortly.")
        async with slots:
            context: Catalog | SchemaContext
            if schema_retriever is None:
                if profile == DEMO:
                    catalog = await db.catalog()
                    context = catalog
                else:
                    snapshot = await db.schema_snapshot()
                    context = SchemaContext(snapshot.catalog, snapshot.primary_keys, snapshot.foreign_keys,
                                            tuple(t for t in profile.terms() if t.is_available(snapshot)), profile.namespace)
                    catalog = context.catalog
                diagnostics = RetrievalDiagnostics(mode="full", status="skipped", tables=sorted(catalog))
            else:
                started = perf_counter()
                try:
                    snapshot = await db.schema_snapshot()
                except QueryFailure as error:
                    error.retrieval = RetrievalDiagnostics(
                        mode="rag", status="failed", duration_ms=round((perf_counter() - started) * 1000, 2),
                    )
                    raise
                retrieval = await asyncio.to_thread(schema_retriever.retrieve, body.question, snapshot)
                context = retrieval.context
                catalog = context.catalog
                diagnostics = retrieval.diagnostics
            try:
                proposal = await llm.generate(body.question, context)
                if not proposal.sql:
                    raise QueryFailure(422, "unanswerable", "The available shop data could not answer this question.")
                result = await db.execute(validate_sql(proposal.sql, catalog, profile.namespace))
            except QueryFailure as error:
                error.retrieval = diagnostics
                raise
            try:
                analysis = present(result, profile)
            except Exception:
                analysis = None
            return result.model_copy(update={"datasource_id": profile.id, "retrieval": diagnostics, "analysis": analysis})

    routes(app, query)
    return app


app = create_app()
