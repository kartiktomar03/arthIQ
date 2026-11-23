SCHEMA = "shop"
TABLES = ("customers", "categories", "products", "orders", "order_items")

Catalog = dict[str, dict[str, str]]

CATALOG_SQL = """
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = $1 AND table_name = ANY($2::text[])
  AND pg_catalog.has_column_privilege(
      pg_catalog.format('%I.%I', table_schema, table_name),
      column_name::text, 'SELECT')
ORDER BY table_name, ordinal_position
"""

# The relationship hints describe the seeded data contract.
RELATIONSHIPS = (
    ("products", "category_id", "categories", "id"),
    ("orders", "customer_id", "customers", "id"),
    ("order_items", "order_id", "orders", "id"),
    ("order_items", "product_id", "products", "id"),
)


def describe(catalog: Catalog) -> str:
    lines = [
        f"{SCHEMA}.{table}: " + ", ".join(f"{column} ({kind})" for column, kind in columns.items())
        for table, columns in catalog.items()
    ]
    for source, key, target, primary in RELATIONSHIPS:
        if key in catalog.get(source, {}) and primary in catalog.get(target, {}):
            lines.append(f"Join {source}.{key} = {target}.{primary}")
    return "\n".join(lines)
