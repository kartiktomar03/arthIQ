import re
from .models import QueryFailure


def resolve(question, previous, datasource):
    base = {"base": question, "values": [], "datasource": datasource}
    follow = re.fullmatch(r"(?:now\s+)?(?:show\s+)?only\s+(.+?)\s*[.!?]?", question, re.I)
    compare = re.fullmatch(r"compare (?:it|that) (?:with|to) (.+?)\s*[.!?]?", question, re.I)
    if follow or compare:
        if not previous or previous.get("datasource") != datasource or not previous.get("group"):
            raise QueryFailure(422, "clarification", "Specify the metric and grouping to filter.")
        values = list(previous["values"]) if compare else []
        if compare and not values:
            raise QueryFailure(422, "clarification", "Which two values should be compared?")
        values.append((follow or compare)[1].strip())
        base = {**previous, "values": list(dict.fromkeys(values))}
        effective = f"{base['base']} Restrict {base['group']} to these values: {', '.join(base['values'])}."
        if len(effective) > 1000:
            raise QueryFailure(422, "clarification", "Restate the question with fewer filter values.")
        return effective, base
    override = re.match(r"^(?:now|instead)[, ]+(show|list|count|calculate)\s+(.+)$", question, re.I)
    if override and not re.search(r"\b(it|that|those|them|same)\b", override[2], re.I):
        base["base"] = f"{override[1]} {override[2]}"
        return base["base"], base
    if re.match(r"(now|compare it|instead|what about|and)\b", question, re.I):
        raise QueryFailure(422, "clarification", "Restate the metric, grouping and requested change.")
    return question, base
