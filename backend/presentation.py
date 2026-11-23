from decimal import Decimal
import sqlglot
from sqlglot import exp
from .models import Analysis, QueryResponse

NUMERIC = {"int2", "int4", "int8", "numeric", "float4", "float8"}


def present(result: QueryResponse, profile=None) -> Analysis:
    tree = sqlglot.parse_one(result.sql, read="postgres")
    projections = tree.expressions
    where = tree.args.get("where")
    predicates = list(where.this.flatten()) if where and isinstance(where.this, exp.And) else [where.this] if where else []
    completed = any(
        isinstance(eq, exp.EQ) and
        isinstance(eq.this, exp.Column) and eq.this.name == "status"
        and isinstance(eq.expression, exp.Literal) and eq.expression.this == "completed"
        for eq in predicates
    )
    units = []
    for projection in projections:
        aggregate = projection.unalias()
        revenue = isinstance(aggregate, exp.Sum) and isinstance(aggregate.this, exp.Mul) and all(
            isinstance(arg, exp.Column) for arg in (aggregate.this.this, aggregate.this.expression)
        ) and {aggregate.this.this.name, aggregate.this.expression.name} == {"quantity", "unit_price"} and completed
        unit = "USD" if revenue and (profile is None or profile.id == "demo_shop") else ""
        if profile and isinstance(aggregate, (exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Column)):
            col = aggregate if isinstance(aggregate, exp.Column) else aggregate.this
            if isinstance(col, exp.Column):
                owners = {t.alias_or_name:t.name for t in tree.find_all(exp.Table)}
                if col.name in profile.money_columns.get(owners.get(col.table), ()):
                    unit = profile.currency
        units.append(unit)
    kinds = ["number" if t in NUMERIC else "date" if t in {"date", "timestamp", "timestamptz"}
             else "label" if t in {"text", "varchar", "bpchar"} else "other" for t in result.column_types]
    metrics = [i for i, kind in enumerate(kinds) if kind == "number"]
    charts = ["table"]
    summary = f"The query returned {len(result.rows)} rows."
    if not result.rows:
        summary = "No rows matched the query." if not result.execution.truncated else "No rows fit within the display limit."
    elif len(kinds) == 1 and metrics and len(result.rows) == 1:
        charts.insert(0, "kpi")
        summary = f"{result.columns[0].replace('_', ' ').title()} is {result.rows[0][0]}."
    elif kinds and kinds[0] in {"label", "date"} and metrics == list(range(1, len(kinds))) and metrics:
        if len({units[i] for i in metrics}) == 1 and all(row[i] is not None and abs(Decimal(str(row[i]))) < 2**53 and
               Decimal(str(float(row[i]))) == Decimal(str(row[i])) for row in result.rows for i in metrics):
            charts.insert(0, "bar")
            if kinds[0] == "date":
                charts.insert(0, "line")
        if len(metrics) == 1:
            metric = result.columns[1].replace("_", " ")
            summary = f"Displayed {metric} by {result.columns[0].replace('_', ' ')}: " + ", ".join(
                f"{row[0]} ({row[1]})" for row in result.rows[:5]
            ) + "."
            if units[1] == "USD" and all(row[1] is not None for row in result.rows):
                total = sum(Decimal(str(row[1])) for row in result.rows)
                summary = ", ".join(f"{row[0]} generated ${Decimal(str(row[1])):,.2f}" for row in result.rows[:5]) + "."
                summary += f" The displayed amounts sum to ${total:,.2f} from completed orders at purchase prices."
    if result.execution.truncated:
        summary += " Only the displayed subset is described."
    return Analysis(summary=summary, charts=charts, units=units, formatted_sql=sqlglot.transpile(
        result.sql, read="postgres", write="postgres", pretty=True)[0])
