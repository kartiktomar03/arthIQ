from dataclasses import dataclass, field
from hashlib import sha256
import json

from .catalog import Catalog, SCHEMA


@dataclass(frozen=True, order=True)
class ForeignKey:
    source: str
    target: str
    columns: tuple[tuple[str, str], ...]

    def describe(self) -> str:
        return " AND ".join(
            f"{self.source}.{left} = {self.target}.{right}" for left, right in self.columns
        )


@dataclass(frozen=True)
class SchemaSnapshot:
    catalog: Catalog
    primary_keys: dict[str, tuple[str, ...]] = field(default_factory=dict)
    foreign_keys: tuple[ForeignKey, ...] = ()

    schema: str = SCHEMA
    glossary: tuple | None = None
    aliases: dict | None = None

    def fingerprint(self) -> str:
        canonical = (
            self.catalog, self.primary_keys,
            [(key.source, key.target, key.columns) for key in sorted(set(self.foreign_keys))],
        )
        return sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class BusinessTerm:
    name: str
    aliases: tuple[str, ...]
    definition: str
    requirements: dict[str, tuple[str, ...]]
    relationships: tuple[ForeignKey, ...]

    def is_available(self, snapshot: SchemaSnapshot) -> bool:
        return all(
            set(columns) <= snapshot.catalog.get(table, {}).keys()
            for table, columns in self.requirements.items()
        ) and set(self.relationships) <= set(snapshot.foreign_keys)


REVENUE = BusinessTerm(
    "revenue",
    ("revenue", "sales value", "sales amount", "dollar sales", "turnover", "sales",
     "total spending", "spending", "amount spent", "total spent", "total spend", "customer spend"),
    "Revenue is SUM(order_items.quantity * order_items.unit_price) for completed orders only. "
    "Filter orders.status = 'completed'. Use the price at purchase and report USD. "
    "Customer spending is this same completed-order amount grouped by customer.",
    {"orders": ("id", "status"), "order_items": ("order_id", "quantity", "unit_price")},
    (ForeignKey("order_items", "orders", (("order_id", "id"),)),),
)
TERMS = (REVENUE,)
TABLE_ALIASES = {
    "customers": ("customer", "buyer", "shopper", "client", "region", "signup", "joined"),
    "categories": ("category", "categories", "department"),
    "products": ("product", "catalog", "merchandise", "sku", "list price", "catalog price"),
    "orders": ("order", "purchase", "transaction", "completed", "pending", "cancelled", "canceled"),
    "order_items": ("order item", "line item", "line items", "quantity", "units", "unit price"),
}


@dataclass(frozen=True)
class SchemaContext:
    catalog: Catalog
    primary_keys: dict[str, tuple[str, ...]]
    relationships: tuple[ForeignKey, ...]
    terms: tuple[BusinessTerm, ...]

    schema: str = SCHEMA

    def describe(self) -> str:
        lines = []
        for table, columns in self.catalog.items():
            fields = ", ".join(f"{name} ({data_type})" for name, data_type in columns.items())
            primary = ", ".join(self.primary_keys.get(table, ()))
            lines.append(f"{self.schema}.{table}: {fields}" + (f"; PK ({primary})" if primary else ""))
        lines.extend(f"Join {edge.describe()}" for edge in self.relationships)
        lines.extend(term.definition for term in self.terms)
        return "\n".join(lines)
