"""Run exactly the six Olist acceptance questions through the production query endpoint."""
import argparse
import asyncio
from decimal import Decimal, InvalidOperation
from getpass import getpass
import os
from time import perf_counter
from urllib.parse import quote

import asyncpg
import httpx

from backend.config import Settings
from backend.datasources import OLIST, OLIST_TABLES, ROOT
from backend.main import create_app
from backend.models import QueryFailure
from backend.olist import reader_pool

CASES = (
    ("orders", "What is the total number of orders?", 99441),
    ("delivered_orders", "How many orders have order_status delivered?", 96478),
    ("distinct_customers", "How many distinct customers are there?", 96096),
    ("order_items", "How many order item rows are there?", 112650),
    ("unique_sellers", "How many unique sellers are there?", 3095),
    ("delivered_item_price_brl", "What is the total delivered merchandise value in BRL?", Decimal("13221498.11")),
)


async def verify():
    settings = Settings()
    if not settings.olist_analytics_dsn:
        raise SystemExit("OLIST_ANALYTICS_DSN is missing. Use --prompt for a local, hidden password prompt.")
    if settings.schema_mode != "rag":
        raise SystemExit("Use SCHEMA_MODE=rag to verify the production retrieval pipeline.")
    async with reader_pool(settings.olist_analytics_dsn.get_secret_value()) as pool:
        async with pool.acquire(timeout=5) as conn, conn.transaction(readonly=True):
            identity = await conn.fetchrow("SELECT current_database() AS db, session_user AS login, current_setting('transaction_read_only') AS ro")
            readable = await conn.fetch("""
                SELECT n.nspname, c.relname FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                WHERE c.relkind IN ('r','p','v','m','f') AND n.nspname !~ '^pg_'
                AND n.nspname <> 'information_schema' AND has_schema_privilege(n.oid,'USAGE')
                AND has_any_column_privilege(c.oid,'SELECT')
            """)
            if {(r[0],r[1]) for r in readable} != {("olist",t) for t in OLIST_TABLES}:
                raise SystemExit("Reader visibility differs from the approved nine tables.")
            print(f"Connected: {identity['db']} | {identity['login']} | read-only={identity['ro']} | 9 approved tables", flush=True)
            reference = await conn.fetchrow((ROOT/"database/olist/reference.sql").read_text(),timeout=5)
    app = create_app()
    passed = 0
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),base_url="http://localhost"
    ) as client:
        for metric, question, expected in CASES:
            start = perf_counter()
            response = await client.post("/api/query",json={"question":question,"datasource_id":OLIST.id})
            data = response.json()
            ref = Decimal(str(reference[metric]))
            rows = data.get("rows", [])
            scalar = None
            if len(rows) == 1 and len(rows[0]) == 1:
                try:
                    scalar = Decimal(str(rows[0][0]))
                except InvalidOperation:
                    pass
            valid = (response.is_success and data["datasource_id"] == OLIST.id
                     and data["retrieval"]["datasource_id"] == OLIST.id
                     and data["retrieval"]["status"] == "ok"
                     and not data["execution"]["truncated"] and len(rows)==1 and len(rows[0])==1
                     and scalar == ref == expected
                     and (metric != "delivered_item_price_brl" or data["analysis"]["units"] == ["BRL"]))
            passed += valid
            outcome = "PASS" if valid else "FAIL"
            actual = scalar if scalar is not None else data.get("error",{}).get("code","unexpected result shape")
            print("Executed SQL:", data.get("sql", "(none)"), flush=True)
            print(f"{metric}: {outcome} | expected={expected} | reference={ref} | generated={actual} | {perf_counter()-start:.2f}s",flush=True)
    return passed == len(CASES)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt",action="store_true",help="Prompt locally if the reader DSN is missing.")
    args = parser.parse_args()
    if args.prompt and not Settings().olist_analytics_dsn:
        password = getpass("Existing arthiq_olist_analytics password: ")
        os.environ["OLIST_ANALYTICS_DSN"] = (
            f"postgresql://{OLIST.role}:{quote(password,safe='')}@127.0.0.1:5432/{OLIST.database}")
        del password
    try:
        ok = asyncio.run(verify())
    except (QueryFailure, asyncpg.PostgresError, OSError) as exc:
        raise SystemExit(f"Olist verification stopped ({type(exc).__name__}). Check the local reader connection.") from None
    raise SystemExit(0 if ok else 1)
