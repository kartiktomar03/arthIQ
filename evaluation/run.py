"""Compare the production query pipeline with a deterministic fixture SQL provider."""

import argparse
import asyncio
from collections import Counter
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
from statistics import mean
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

import asyncpg
import httpx

from backend.config import Settings
from backend.database import AnalyticsDatabase
from backend.llm import schema_prompt
from backend.main import create_app
from backend.models import QueryFailure, SQLProposal
from backend.rag import create_retriever
from backend.schema_context import SchemaContext, SchemaSnapshot
from evaluation.cases import CASES


def mean_or_none(values):
    return round(mean(values), 3) if values else None


def edge_pairs(edges):
    return {frozenset((edge.source, edge.target)) for edge in edges}


def comparable_rows(rows):
    def normalize(value):
        if isinstance(value, str):
            try:
                decimal = Decimal(value)
                if decimal.is_finite():
                    return decimal.quantize(Decimal("0.000001"))
            except InvalidOperation:
                pass
        return value

    return [tuple(normalize(value) for value in row) for row in rows]


def matches(case, response):
    payload = response.json()
    if case.sql is None:
        return response.status_code == 422 and payload["error"]["code"] in {"unanswerable", "schema_clarification"}
    if response.status_code != 200 or payload["execution"]["truncated"]:
        return False
    actual, expected = comparable_rows(payload["rows"]), comparable_rows(case.expected)
    return actual == expected if case.ordered else Counter(actual) == Counter(expected)


class FixtureGenerator:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.cases = {case.question: case for case in CASES}
        self.context = None
        self.prompt_size = 0

    async def generate(self, question, context):
        self.context = context
        self.prompt_size = len(schema_prompt(context))
        case = self.cases[question]
        if isinstance(context, SchemaContext):
            tables = set(context.catalog)
            edges = edge_pairs(context.relationships)
        else:
            tables = set(context)
            edges = edge_pairs(self.snapshot.foreign_keys)
        required_edges = set(map(frozenset, case.joins))
        return SQLProposal(sql=case.sql if set(case.tables) <= tables and required_edges <= edges else None)


class Evaluation:
    def __init__(self):
        self.recall = []
        self.recall_expanded = []
        self.join_coverage = []
        self.prompt_sizes = []
        self.retrieval_times = []
        self.latencies = []
        self.failures = []
        self.correct = 0
        self.negative_correct = 0
        self.extra_tables = []

    def add_context(self, case, selected, tables, edges):
        if case.tables:
            expected = set(case.tables)
            if selected is not None:
                self.recall.append(len(expected & set(selected)) / len(expected))
            self.recall_expanded.append(len(expected & set(tables)) / len(expected))
            self.extra_tables.append(len(set(tables) - expected))
        if case.joins:
            required = set(map(frozenset, case.joins))
            self.join_coverage.append(len(required & edges) / len(required))

    def report(self):
        latency = sorted(self.latencies)
        total_positive = sum(case.sql is not None for case in CASES)
        return {
            "table_recall_at_k": mean_or_none(self.recall),
            "context_table_recall_after_expansion": mean_or_none(self.recall_expanded),
            "mean_extra_context_tables": mean_or_none(self.extra_tables),
            "required_join_coverage": mean_or_none(self.join_coverage),
            "correct_positive_results": self.correct if latency else None,
            "positive_cases": total_positive,
            "correct_negative_handling": self.negative_correct if latency else None,
            "negative_cases": len(CASES) - total_positive,
            "mean_retrieval_ms": mean_or_none(self.retrieval_times),
            "mean_end_to_end_ms": mean_or_none(latency),
            "p95_end_to_end_ms": round(latency[(95 * len(latency) + 99) // 100 - 1], 3) if latency else None,
            "mean_schema_prompt_characters": mean_or_none(self.prompt_sizes),
            "failures": self.failures,
        }


async def compare(db, snapshot, retriever, mode):
    metrics = Evaluation()
    generator = FixtureGenerator(snapshot)
    with patch.dict(os.environ, {"SCHEMA_MODE": mode}):
        app = create_app(db, generator, retriever)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://eval") as client:
                for case in CASES:
                    generator.context = None
                    started = perf_counter()
                    response = await client.post("/api/query", json={"question": case.question})
                    metrics.latencies.append((perf_counter() - started) * 1000)
                    payload = response.json()
                    diagnostics = payload.get("retrieval", {})
                    if mode == "rag" and diagnostics:
                        metrics.retrieval_times.append(diagnostics["duration_ms"])
                    if generator.context is not None:
                        metrics.prompt_sizes.append(generator.prompt_size)
                    if isinstance(generator.context, SchemaContext):
                        metrics.add_context(
                            case, diagnostics["seed_tables"], diagnostics["tables"],
                            edge_pairs(generator.context.relationships),
                        )
                    elif mode == "full" and generator.context is not None:
                        metrics.add_context(case, None, generator.context, edge_pairs(snapshot.foreign_keys))
                    elif mode == "rag":
                        metrics.add_context(case, [], [], set())

                    if matches(case, response):
                        if case.sql:
                            metrics.correct += 1
                        else:
                            metrics.negative_correct += 1
                    else:
                        metrics.failures.append({
                            "question": case.question, "status": response.status_code,
                            "error_code": payload.get("error", {}).get("code"),
                        })
    return metrics.report()


def memory_mib():
    try:
        import psutil

        memory = psutil.Process().memory_info()
        if hasattr(memory, "peak_wset"):
            return round(memory.peak_wset / 1048576, 1)
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(rss / (1048576 if sys.platform == "darwin" else 1024), 1)
    except (ImportError, AttributeError):
        return None


def index(retriever, snapshot):
    before = memory_mib()
    start = perf_counter()
    _, docs = retriever.index(snapshot)
    return {
        "documents": docs,
        "elapsed_ms": round((perf_counter() - start) * 1000, 2),
        "process_peak_rss_before_mib": before,
        "process_peak_rss_after_mib": memory_mib(),
    }


def stress(retriever, snapshot, count):
    domains = ("warehouse", "supplier", "billing", "shipping", "inventory", "returns", "promotions", "tax")
    expanded = SchemaSnapshot(
        {**snapshot.catalog, **{
            f"{domains[i % len(domains)]}_record_{i:03}": {
                "record_id": "integer", "record_state": "varchar", "record_reference": "varchar",
                "record_date": "date", "settled_amount": "numeric",
            } for i in range(count)
        }},
        snapshot.primary_keys, snapshot.foreign_keys,
    )
    indexing = index(retriever, expanded)
    metrics = Evaluation()
    for case in CASES:
        try:
            got = retriever.retrieve(case.question, expanded)
        except QueryFailure as error:
            metrics.retrieval_times.append(error.retrieval.duration_ms)
            metrics.add_context(case, [], [], set())
            if case.sql is not None:
                metrics.failures.append({"question": case.question, "error_code": error.code})
        else:
            metrics.retrieval_times.append(got.diagnostics.duration_ms)
            metrics.prompt_sizes.append(len(schema_prompt(got.context)))
            metrics.add_context(case, got.selected, got.context.catalog, edge_pairs(got.context.relationships))
    return {
        "synthetic_metadata_tables": count,
        "indexing": indexing,
        "full_schema_prompt_characters": len(schema_prompt(expanded.catalog)),
        "retrieval_only": metrics.report(),
    }


async def evaluate(settings, stress_tables):
    if not settings.analytics_dsn or not settings.analytics_dsn.get_secret_value():
        raise QueryFailure(503, "configuration_required", "Set ANALYTICS_DSN to the seeded demo before evaluation.")
    async with asyncpg.create_pool(
        settings.analytics_dsn.get_secret_value(), min_size=0, max_size=2, timeout=5, command_timeout=5,
    ) as pool:
        db = AnalyticsDatabase(pool, settings.query_timeout_ms, settings.max_rows, settings.max_response_bytes)
        snapshot = await db.schema_snapshot()
        with TemporaryDirectory(prefix="querypilot-eval-") as tmp:
            store, retriever = create_retriever(settings.model_copy(update={"qdrant_path": Path(tmp)}))
            try:
                baseline = await compare(db, snapshot, None, "full")
                indexing = await asyncio.to_thread(index, retriever, snapshot)
                rag = await compare(db, snapshot, retriever, "rag")
                report = {"cases": len(CASES), "top_k": settings.schema_top_k, "llm": "fixture", "indexing": indexing,
                          "baseline": baseline, "rag": rag}
                if stress_tables:
                    report["stress"] = await asyncio.to_thread(stress, retriever, snapshot, stress_tables)
                return report
            finally:
                store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stress-tables", type=int, choices=range(0, 201), metavar="0..200", default=0)
    args = parser.parse_args()
    try:
        report = asyncio.run(evaluate(Settings(), args.stress_tables))
    except QueryFailure as error:
        parser.exit(1, f"{error.code}: {error}\n")
    except Exception as error:
        parser.exit(1, f"Evaluation could not run ({type(error).__name__}). Check PostgreSQL, the model cache and dependencies.\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
