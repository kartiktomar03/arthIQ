from collections import defaultdict

from .catalog import Catalog
from .schema_context import ForeignKey, SchemaSnapshot

# pg_constraint supplies ordered pairs for composite keys. Access to a key is
# still decided against the SELECT-visible columns, never catalog visibility alone.
KEY_SQL = """
SELECT c.oid, c.contype::text AS contype, src.relname AS source, dst.relname AS target,
       a.attname AS source_column, b.attname AS target_column, k.ordinality
FROM pg_catalog.pg_constraint AS c
JOIN pg_catalog.pg_class AS src ON src.oid = c.conrelid
JOIN pg_catalog.pg_namespace AS src_ns ON src_ns.oid = src.relnamespace
LEFT JOIN pg_catalog.pg_class AS dst ON dst.oid = c.confrelid
LEFT JOIN pg_catalog.pg_namespace AS dst_ns ON dst_ns.oid = dst.relnamespace
CROSS JOIN LATERAL pg_catalog.unnest(c.conkey) WITH ORDINALITY AS k(attnum, ordinality)
JOIN pg_catalog.pg_attribute AS a ON a.attrelid = src.oid AND a.attnum = k.attnum
LEFT JOIN pg_catalog.pg_attribute AS b
       ON b.attrelid = dst.oid AND b.attnum = c.confkey[k.ordinality::integer]
WHERE src_ns.nspname = $1 AND src.relname = ANY($2::text[])
  AND (c.contype = 'p' OR
       (c.contype = 'f' AND dst_ns.nspname = $1 AND dst.relname = ANY($2::text[])))
ORDER BY c.oid, k.ordinality
"""


def build_snapshot(catalog: Catalog, rows) -> SchemaSnapshot:
    constraints = defaultdict(list)
    for row in rows:
        constraints[row["oid"]].append(row)

    primary = {}
    foreign = set()
    for constraint in constraints.values():
        parts = sorted(constraint, key=lambda part: part["ordinality"])
        first = parts[0]
        source, target = first["source"], first["target"]
        source_columns = tuple(part["source_column"] for part in parts)
        if not all(name in catalog.get(source, {}) for name in source_columns):
            continue
        if first["contype"] == "p":
            primary[source] = source_columns
        else:
            target_columns = tuple(part["target_column"] for part in parts)
            if all(name in catalog.get(target, {}) for name in target_columns):
                foreign.add(ForeignKey(source, target, tuple(zip(source_columns, target_columns))))
    return SchemaSnapshot(catalog, primary, tuple(sorted(foreign)))
