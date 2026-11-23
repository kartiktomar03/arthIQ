"""Dedicated, optional Olist connection. No request supplies connection parameters."""
import asyncpg
from .datasources import OLIST
from .models import QueryFailure
from urllib.parse import urlsplit

READER_SQL = """
SELECT session_user=current_user AND current_user=$1 AND current_database()=$2
AND NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
AND NOT EXISTS (SELECT FROM pg_auth_members WHERE member=r.oid)
AND NOT has_database_privilege(current_database(),'CREATE,TEMP')
AND NOT EXISTS (SELECT FROM pg_namespace WHERE has_schema_privilege(oid,'CREATE'))
AND NOT EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
 WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
 AND c.relkind IN ('r','p','v','m','f') AND
 (c.relowner=r.oid OR has_table_privilege(c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
 OR has_any_column_privilege(c.oid,'INSERT,UPDATE,REFERENCES')))
FROM pg_roles r WHERE rolname=current_user
"""


async def verify_reader(conn):
    if not await conn.fetchval(READER_SQL, OLIST.role, OLIST.database):
        raise QueryFailure(403, "unsafe_datasource", "The dedicated Olist reader failed privilege verification.")


def reader_pool(dsn):
    try:
        url = urlsplit(dsn)
        valid = (url.scheme in {"postgresql","postgres"} and url.hostname == "127.0.0.1"
                 and url.port in (None,5432) and url.username == OLIST.role
                 and url.path == "/"+OLIST.database and not url.query and not url.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise QueryFailure(503, "invalid_datasource", "Check the local Olist reader configuration.")
    return asyncpg.create_pool(dsn, min_size=0, max_size=1, setup=verify_reader,
                               timeout=3, command_timeout=5)
