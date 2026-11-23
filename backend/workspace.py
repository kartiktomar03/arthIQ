import json
import re
from textwrap import shorten
import sqlglot
from sqlglot import exp
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated
from .conversation_state import resolve
from .models import QueryFailure, QueryRequest

OWNER = "localhost"


def question_title(question: str) -> str:
    text = " ".join(question.split()).rstrip("?.!") or question.strip()
    subject = re.sub(r"^(?:please\s+)?(?:show me|show|list|give me)\s+", "", text, flags=re.I) or text
    title = subject[:1].upper() + subject[1:]
    if len(title) <= 72:
        return title
    shortened = shorten(title, width=72, placeholder="…")
    return shortened if shortened != "…" else title[:71] + "…"


class NewConversation(BaseModel):
    datasource_id: str = "demo_shop"


class Title(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class EntryTitle(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Save(Title):
    run_id: UUID


class DashboardSelection(Title):
    run_ids: list[UUID] = Field(min_length=1, max_length=20)


def required(row):
    if row is None:
        raise QueryFailure(404, "missing", "The requested record was not found.")
    return row


def routes(app, query):
    def pool():
        if app.state.workspace is None:
            raise QueryFailure(503, "workspace_configuration", "Configure WORKSPACE_DSN to use saved conversations.")
        return app.state.workspace

    @app.post("/api/conversations")
    async def create(body: NewConversation = NewConversation()):
        source = body.datasource_id
        if source not in {"olist","demo_shop"}:
            raise QueryFailure(422, "unknown_datasource", "Unknown analytics datasource.")
        if source == "olist" and app.state.olist is None:
            raise QueryFailure(503, "datasource_unconfigured", "Configure OLIST_ANALYTICS_DSN locally.")
        uid = uuid4()
        await pool().execute("INSERT INTO qp_app.conversations(id,owner,title,state) VALUES($1,$2,'New conversation',$3)", uid, OWNER, json.dumps({"source_id":source}))
        return {"id": uid}

    @app.get("/api/conversations")
    async def conversations():
        return [dict(r) for r in await pool().fetch("SELECT id,title,COALESCE(state->>'source_id','demo_shop') AS datasource_id,(title='New conversation' AND NOT (state ? 'title_set')) AS untitled FROM qp_app.conversations WHERE owner=$1 ORDER BY created_at DESC,id DESC", OWNER)]

    @app.get("/api/conversations/{uid}")
    async def history(uid: UUID):
        required(await pool().fetchval("SELECT id FROM qp_app.conversations WHERE id=$1 AND owner=$2", uid, OWNER))
        return [dict(r) for r in await pool().fetch(
            "SELECT r.id,question,r.created_at FROM qp_app.runs r JOIN qp_app.conversations c ON c.id=r.conversation_id "
            "WHERE c.id=$1 AND owner=$2 ORDER BY r.created_at,r.id", uid, OWNER)]

    @app.patch("/api/conversations/{uid}")
    async def rename_entry(uid: UUID, body: EntryTitle):
        row = required(await pool().fetchrow(
            "UPDATE qp_app.conversations SET title=$3,state=state || jsonb_build_object('title_set',true) WHERE id=$1 AND owner=$2 RETURNING id,title",
            uid, OWNER, body.title))
        return dict(row)

    @app.delete("/api/conversations/{uid}")
    async def remove(uid: UUID):
        required(await pool().fetchval("DELETE FROM qp_app.conversations WHERE id=$1 AND owner=$2 RETURNING id", uid, OWNER))
        return {"deleted": True}

    @app.post("/api/conversations/{uid}/query")
    async def turn(uid: UUID, body: QueryRequest, request: Request):
        async with pool().acquire() as conn, conn.transaction():
            record = required(await conn.fetchrow("SELECT state,title FROM qp_app.conversations WHERE id=$1 AND owner=$2 FOR UPDATE", uid, OWNER))
            previous = json.loads(record["state"])
            source = previous.get("source_id", "demo_shop")
            if body.datasource_id is not None and body.datasource_id != source:
                raise QueryFailure(409, "datasource_mismatch", "Start a new entry to change datasource.")
            effective, state = resolve(body.question, previous, app.state.datasource if source == "demo_shop" else source)
            state["source_id"] = source
            result = await query(QueryRequest(question=effective,datasource_id=source), request)
            tree = sqlglot.parse_one(result.sql, read="postgres")
            state["metrics"] = [node.sql(dialect="postgres") for node in tree.find_all(exp.AggFunc)]
            state["filters"] = tree.args["where"].this.sql(dialect="postgres") if tree.args.get("where") else ""
            state["grouping"] = [node.sql(dialect="postgres") for node in tree.args["group"].expressions] if tree.args.get("group") else []
            if result.column_types and result.column_types[0] in {"text","varchar","bpchar","date"}:
                state["group"] = result.columns[0]
            title = record["title"]
            if title == "New conversation" and not previous.get("title_set"):
                first = await conn.fetchval(
                    "SELECT question FROM qp_app.runs WHERE conversation_id=$1 ORDER BY created_at,id LIMIT 1", uid)
                title = question_title(first or body.question)
            state["title_set"] = True
            run = uuid4()
            await conn.execute("INSERT INTO qp_app.runs(id,conversation_id,question,result) VALUES($1,$2,$3,$4)",
                               run, uid, body.question, result.model_dump_json())
            await conn.execute("UPDATE qp_app.conversations SET state=$2,title=$3 WHERE id=$1", uid, json.dumps(state),
                               title)
            return {"id":run, "question":body.question, "result":result, "title":title}

    @app.get("/api/query-runs/{uid}")
    async def read_run(uid: UUID):
        r = required(await pool().fetchrow("SELECT question,result,r.created_at FROM qp_app.runs r JOIN qp_app.conversations c ON c.id=r.conversation_id WHERE r.id=$1 AND c.owner=$2", uid, OWNER))
        return {**dict(r), "result": json.loads(r["result"])}

    @app.post("/api/dashboards")
    async def save(body: Save):
        uid = uuid4()
        required(await pool().fetchval("INSERT INTO qp_app.cards(id,owner,title,snapshot,generated_at) "
            "SELECT $1,$2,$3,jsonb_build_object('run_id',r.id,'question',r.question,'result',r.result),r.created_at FROM qp_app.runs r "
            "JOIN qp_app.conversations c ON c.id=r.conversation_id WHERE r.id=$4 AND c.owner=$2 RETURNING id",
            uid, OWNER, body.title, body.run_id))
        return {"id":uid}

    @app.post("/api/conversations/{uid}/dashboards")
    async def save_dashboard(uid: UUID, body: DashboardSelection):
        if len(set(body.run_ids)) != len(body.run_ids):
            raise QueryFailure(422, "duplicate_runs", "Select each analysis only once.")
        card_id = uuid4()
        # One statement both verifies membership and freezes every selected result.
        required(await pool().fetchval("""
            INSERT INTO qp_app.cards(id, owner, title, snapshot, generated_at)
            SELECT $1, $2, $3, jsonb_build_object('analyses', jsonb_agg(
                jsonb_build_object('run_id', r.id, 'question', r.question,
                                   'result', r.result, 'generated_at', r.created_at)
                ORDER BY r.created_at, r.id)), clock_timestamp()
            FROM qp_app.runs r JOIN qp_app.conversations c ON c.id = r.conversation_id
            WHERE c.id = $4 AND c.owner = $2 AND r.id = ANY($5::uuid[])
            HAVING count(*) = cardinality($5::uuid[])
            RETURNING id
        """, card_id, OWNER, body.title, uid, body.run_ids))
        return {"id": card_id}

    @app.get("/api/dashboards")
    async def cards():
        return [dict(r) for r in await pool().fetch("SELECT id,title,generated_at,COALESCE(snapshot->'result'->>'datasource_id',snapshot->'analyses'->0->'result'->>'datasource_id','demo_shop') AS datasource_id FROM qp_app.cards WHERE owner=$1 ORDER BY generated_at DESC", OWNER)]

    @app.get("/api/dashboards/{uid}")
    async def card(uid: UUID):
        r = required(await pool().fetchrow("SELECT snapshot,generated_at FROM qp_app.cards WHERE id=$1 AND owner=$2", uid, OWNER))
        return {**json.loads(r["snapshot"]), "generated_at":r["generated_at"]}

    @app.patch("/api/dashboards/{uid}")
    async def rename(uid: UUID, body: Title):
        required(await pool().fetchval("UPDATE qp_app.cards SET title=$3 WHERE id=$1 AND owner=$2 RETURNING id", uid, OWNER, body.title))
        return {"id":uid}

    @app.delete("/api/dashboards/{uid}")
    async def delete(uid: UUID):
        required(await pool().fetchval("DELETE FROM qp_app.cards WHERE id=$1 AND owner=$2 RETURNING id", uid, OWNER))
        return {"deleted":True}
