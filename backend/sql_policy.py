from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.qualify import qualify

from .catalog import Catalog, SCHEMA
from .models import QueryFailure

# Exact node classes deliberately define a small supported PostgreSQL grammar.
ALLOWED_NODES = {
    exp.Select, exp.From, exp.Table, exp.Identifier, exp.Column, exp.Alias,
    exp.Join, exp.Where, exp.Group, exp.Having, exp.Order, exp.Ordered, exp.Limit,
    exp.Literal, exp.Boolean, exp.Null, exp.Star, exp.Distinct, exp.Paren,
    exp.And, exp.Or, exp.Not, exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
    exp.Is, exp.In, exp.Between, exp.Like, exp.ILike,
    exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Neg,
    exp.Sum, exp.Count, exp.Avg, exp.Min, exp.Max, exp.TableAlias,
}


@dataclass(frozen=True)
class ApprovedQuery:
    sql: str


def reject(message: str) -> QueryFailure:
    return QueryFailure(422, "sql_rejected", message)


def validate_sql(sql: str, catalog: Catalog, schema: str = SCHEMA) -> ApprovedQuery:
    if not sql.strip() or len(sql) > 8000:
        raise reject("SQL is empty or exceeds the maximum length.")
    try:
        statements = sqlglot.parse(sql, read="postgres")
        if len(statements) != 1 or type(statements[0]) is not exp.Select:
            raise reject("Only one SELECT statement is allowed.")
        query = statements[0]
        for node in query.walk():
            if type(node) not in ALLOWED_NODES or (isinstance(node, exp.Select) and node is not query):
                raise reject("SQL contains an unsupported operation.")
            if isinstance(node, exp.Identifier) and not node.args.get("quoted"):
                node.set("this", node.name.lower())
            if isinstance(node, exp.Star) and (
                type(node.parent) is not exp.Count or node.parent.this is not node or any(node.args.values())
            ):
                raise reject("List the output columns explicitly. COUNT(*) is allowed.")

        tables = list(query.find_all(exp.Table))
        if not tables:
            raise reject("The query must read an authorized shop table.")
        for table in tables:
            if table.catalog or table.db not in ("", schema) or table.name not in catalog:
                raise reject("The query references an unauthorized table.")
            table.set("db", exp.to_identifier(schema))
        for join in query.find_all(exp.Join):
            if not join.args.get("on") or join.args.get("method") or join.args.get("kind") == "CROSS":
                raise reject("Joins require an explicit ON condition.")

        limit = query.args.get("limit")
        if limit and (not isinstance(limit.expression, exp.Literal) or not limit.expression.is_int
                      or not 0 <= int(limit.expression.this) <= 10000):
            raise reject("LIMIT must be a nonnegative integer up to 10000.")

        qualified = qualify(
            query, dialect="postgres", schema={schema: catalog},
            infer_schema=False, validate_qualify_columns=True,
        )
        return ApprovedQuery(qualified.sql(dialect="postgres", comments=False))
    except (SqlglotError, RecursionError, ValueError):
        raise reject("SQL could not be parsed or contains unknown or ambiguous columns.") from None
