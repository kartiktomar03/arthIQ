"""Provision roles and seed a dedicated local QueryPilot database."""

import argparse
import asyncio
import os
from pathlib import Path

import asyncpg

SQL_DIR = Path(__file__).resolve().parent
MIGRATOR = "querypilot_migrator"
ANALYTICS = "querypilot_analytics"
ROLE_PASSWORDS = {
    MIGRATOR: "QP_MIGRATION_PASSWORD",
    ANALYTICS: "QP_ANALYTICS_PASSWORD",
}


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Set {name} before running setup.")
    return value


async def bootstrap(conn: asyncpg.Connection) -> None:
    if not await conn.fetchval(
        "SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user"
    ):
        raise ValueError("Bootstrap requires the dedicated cluster's PostgreSQL administrator.")
    passwords = {role: required(env) for role, env in ROLE_PASSWORDS.items()}
    if passwords[MIGRATOR] == passwords[ANALYTICS]:
        raise ValueError("Use distinct passwords for the migration and analytics roles.")

    async with conn.transaction():
        for role, password in passwords.items():
            if not await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = $1)", role
            ):
                await conn.execute(f"CREATE ROLE {role}")
            quoted_password = await conn.fetchval("SELECT pg_catalog.quote_literal($1::text)", password)
            await conn.execute(
                f"ALTER ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                f"NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {quoted_password}"
            )
        await conn.execute("""
            REVOKE ALL ON DATABASE querypilot_ai FROM PUBLIC;
            GRANT CONNECT ON DATABASE querypilot_ai TO querypilot_migrator, querypilot_analytics;
            REVOKE CREATE ON SCHEMA public FROM PUBLIC;
            CREATE SCHEMA IF NOT EXISTS shop AUTHORIZATION querypilot_migrator;
            REVOKE ALL ON SCHEMA shop FROM PUBLIC;
            GRANT USAGE ON SCHEMA shop TO querypilot_analytics;
            ALTER ROLE querypilot_analytics IN DATABASE querypilot_ai
                SET default_transaction_read_only = on;
            ALTER ROLE querypilot_analytics IN DATABASE querypilot_ai SET search_path = pg_catalog;
        """)


async def setup(action: str) -> None:
    dsn = required("QP_ADMIN_DSN" if action == "bootstrap" else "QP_MIGRATION_DSN")
    conn = await asyncpg.connect(dsn, timeout=5, command_timeout=15)
    try:
        if await conn.fetchval("SELECT current_database()") != "querypilot_ai":
            raise ValueError("Setup requires a dedicated database named querypilot_ai.")
        if action == "bootstrap":
            await bootstrap(conn)
        else:
            if await conn.fetchval("SELECT current_user") != MIGRATOR:
                raise ValueError("Use querypilot_migrator for migration and seed.")
            for script in ("001_shop.sql", "seed.sql"):
                await conn.execute((SQL_DIR / script).read_text(encoding="utf-8"))
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bootstrap", "seed"))
    try:
        asyncio.run(setup(parser.parse_args().action))
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    except (OSError, TimeoutError, asyncpg.PostgresError, asyncpg.InterfaceError) as error:
        parser.exit(1, f"Database setup failed ({type(error).__name__}). Check the connection and role.\n")
    print("Database setup completed.")


if __name__ == "__main__":
    main()
