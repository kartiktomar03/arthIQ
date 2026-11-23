"""Administrator-approved local connection profiles. The registry contains no credentials."""
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .schema_context import BusinessTerm, REVENUE, TABLE_ALIASES

ROOT = Path(__file__).resolve().parents[1]
Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,62}$")]


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list, max_length=40)
    definition: str = Field(min_length=1, max_length=1000)
    requirements: dict[Identifier, list[Identifier]] = Field(min_length=1)


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Identifier
    name: str = Field(min_length=1, max_length=80)
    database: Identifier
    role: Identifier
    namespace: Identifier
    currency: str = Field(default="", pattern=r"^([A-Z]{3})?$")
    money_columns: dict[Identifier, list[Identifier]] = {}
    aliases: dict[Identifier, list[str]] = {}
    metrics: list[Metric] = Field(default_factory=list, max_length=100)

    @field_validator("namespace")
    @classmethod
    def business_schema(cls, value):
        if value.startswith("pg_") or value in {"information_schema", "qp_app"}:
            raise ValueError("Choose a business schema.")
        return value

    def terms(self):
        if self.id == DEMO.id:
            return (REVENUE,)
        return tuple(BusinessTerm(m.name, tuple(m.aliases), m.definition,
                                  {t: tuple(cols) for t, cols in m.requirements.items()}, ())
                     for m in self.metrics)

DEMO = Profile(id="demo_shop", name="Demo Shop", database="querypilot_ai",
               role="querypilot_analytics", namespace="shop", currency="USD", aliases=TABLE_ALIASES)


OLIST = Profile.model_validate_json((ROOT / "database/olist/datasource.json").read_bytes())
OLIST_TABLES = ("customers", "orders", "order_items", "order_payments", "order_reviews",
                "products", "sellers", "geolocation", "product_category_name_translation")
