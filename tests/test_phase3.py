import asyncio
import os
import secrets
import socket
import subprocess
from pathlib import Path

import asyncpg
import httpx
import pytest

from backend.conversation_state import resolve
from backend.main import create_app
from backend.models import ExecutionMetadata, QueryFailure, QueryResponse
from backend.presentation import present
from tests.test_api import StubDatabase, StubLLM, request
from tests.test_policy import TOP_PRODUCTS


@pytest.mark.parametrize("types,rows,chart", [
    (["numeric"], [["12.10"]], "kpi"),
    (["varchar","numeric"], [["Kitchen","247.00"]], "bar"),
    (["date","int4"], [["2025-01-01",2]], "line"),
    (["varchar","int4","int4"], [["Kitchen",2,3]], "bar"),
    (["text","numeric"], [["Kitchen","123456789012345678.12"]], "table"),
    (["int4"], [], "table"),
])
def test_presentation(types,rows,chart):
    columns = ["c"+str(i) for i in range(len(types))]
    result = QueryResponse(sql="SELECT "+", ".join(columns)+" FROM shop.orders",columns=columns,
        column_types=types, rows=rows, execution=ExecutionMetadata(duration_ms=1,row_count=len(rows),truncated=True))
    analysis = present(result)
    assert analysis.charts[0] == chart
    assert "\n" in analysis.formatted_sql
    assert "subset" in analysis.summary
    assert result.rows == rows


def test_followups_and_reset():
    state = {"base":"Show revenue by category for completed orders in January", "group":"category",
             "values":[], "datasource":"demo"}
    question, state = resolve("Now show only Kitchen.",state,"demo")
    assert "January" in question and state["values"] == ["Kitchen"]
    _, state = resolve("Compare it with Outdoor.",state,"demo")
    assert state["values"] == ["Kitchen","Outdoor"]
    _, state = resolve("Show only Outdoor.",state,"demo")
    assert state["values"] == ["Outdoor"]
    assert resolve("Count customers",state,"demo")[1]["values"] == []
    with pytest.raises(QueryFailure):
        resolve("Compare it with Outdoor.",{},"demo")


def test_grounded_currency_summary():
    result=QueryResponse(sql=TOP_PRODUCTS, columns=["product","revenue"], column_types=["varchar","numeric"],
        rows=[["A","12.30"],["B","0.10"]],execution=ExecutionMetadata(duration_ms=1,row_count=2,truncated=False))
    analysis=present(result)
    assert "$12.40" in analysis.summary and "completed orders" in analysis.summary
    assert analysis.units == ["","USD"]


def test_summary_failure_preserves_rows(monkeypatch):
    def unavailable(_):
        raise ValueError("summary unavailable")
    monkeypatch.setenv("SCHEMA_MODE","full")
    monkeypatch.setattr("backend.main.present",unavailable)
    response,=request(create_app(StubDatabase(),StubLLM(TOP_PRODUCTS)),
                      ("POST","/api/query",{"json":{"question":"Top products by revenue"}}))
    assert response.status_code==200
    assert response.json()["rows"] and response.json()["sql"]
    assert response.json()["analysis"] is None


def test_postgres_workspace(tmp_path, monkeypatch):
    bin_dir = Path(os.environ.get("QP_PG_BIN","C:/Program Files/PostgreSQL/19/bin"))
    if not (bin_dir/"initdb.exe").exists():
        pytest.skip("Set QP_PG_BIN to PostgreSQL Windows binaries for disposable integration test.")
    pw = secrets.token_hex(24)
    password_file=tmp_path/"password"
    password_file.write_text(pw)
    cluster=tmp_path/"cluster"
    subprocess.run([bin_dir/"initdb.exe","-D",cluster,"-U","admin","-A","scram-sha-256",
                    "--pwfile",password_file,"--locale=C","--no-sync"],check=True,capture_output=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port=sock.getsockname()[1]
    ctl=[bin_dir/"pg_ctl.exe","-D",cluster]
    subprocess.run([*ctl,"-l",tmp_path/"pg.log","-o",f"-h 127.0.0.1 -p {port}","-w","start"],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
    async def check():
        kwargs=dict(user="admin",password=pw,host="127.0.0.1",port=port)
        conn=await asyncpg.connect(database="postgres",**kwargs)
        await conn.execute("CREATE DATABASE querypilot_ai")
        await conn.close()
        conn=await asyncpg.connect(database="querypilot_ai",**kwargs)
        await conn.execute(Path("database/002_workspace.sql").read_text())
        workspace_pw=secrets.token_hex(24)
        await conn.execute(f"ALTER ROLE querypilot_workspace PASSWORD '{workspace_pw}'")
        await conn.close()
        monkeypatch.setenv("WORKSPACE_DSN",f"postgresql://querypilot_workspace:{workspace_pw}@127.0.0.1:{port}/querypilot_ai")
        monkeypatch.setenv("SCHEMA_MODE","full")
        app=create_app(StubDatabase(),StubLLM(TOP_PRODUCTS))
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            a,b=[(await client.post("/api/conversations")).json()["id"] for _ in range(2)]
            response=await client.post(f"/api/conversations/{a}/query",json={"question":"Top products by revenue"})
            assert response.status_code==200,response.text
            assert response.json()["title"]=="Top products by revenue"
            assert (await client.get("/api/conversations")).json()[-1]["title"]==response.json()["title"]
            assert (await client.patch(f"/api/conversations/{b}",json={"title":"New conversation"})).status_code==200
            run=response.json()["id"]
            assert (await client.get(f"/api/conversations/{b}")).json()==[]
            assert (await client.get(f"/api/conversations/{a}")).json()[0]["id"]==run
            assert [row["id"] for row in (await client.get("/api/conversations")).json()]==[b,a]
            assert (await client.patch(f"/api/conversations/{a}",json={"title":"  "})).status_code==422
            assert (await client.patch(f"/api/conversations/{a}",json={"title":"  Sales notebook  "})).json()=={"id":a,"title":"Sales notebook"}
            card=(await client.post("/api/dashboards",json={"run_id":run,"title":"Revenue"})).json()["id"]
            await client.patch(f"/api/dashboards/{card}",json={"title":"Saved revenue"})
            assert (await client.get("/api/dashboards")).json()[0]["title"]=="Saved revenue"
            other=(await client.post(f"/api/conversations/{b}/query",json={"question":"Count products"})).json()["id"]
            manual=(await client.get("/api/conversations")).json()[0]
            assert manual["title"]=="New conversation" and not manual["untitled"]
            second=(await client.post(f"/api/conversations/{a}/query",json={"question":"Show product revenue"})).json()
            assert (await client.get("/api/conversations")).json()[-1]["title"]=="Sales notebook"
            assert [r["id"] for r in (await client.get(f"/api/conversations/{a}")).json()]==[run,second["id"]]
            endpoint=f"/api/conversations/{a}/dashboards"
            for ids,status in [([],422),([run,run],422),([run,other],404)]:
                assert (await client.post(endpoint,json={"title":"Invalid","run_ids":ids})).status_code==status
            assert len((await client.get("/api/dashboards")).json())==1
            group=(await client.post(endpoint,json={"title":"Report","run_ids":[second["id"],run]})).json()["id"]
            assert (await client.patch(f"/api/dashboards/{group}",json={"title":"Renamed"})).status_code==200
            await client.delete(f"/api/conversations/{a}")
            assert (await client.patch(f"/api/conversations/{a}",json={"title":"Missing"})).status_code==404
            assert [r["id"] for r in (await client.get("/api/conversations")).json()]==[b]
            assert (await client.get(f"/api/query-runs/{run}")).status_code==404
            assert (await client.get(f"/api/dashboards/{card}")).json()["result"]==response.json()["result"]
            items=(await client.get(f"/api/dashboards/{group}")).json()["analyses"]
            assert [item["run_id"] for item in items]==[run,second["id"]]
            assert [item["result"] for item in items]==[response.json()["result"],second["result"]]
            assert all(item["generated_at"] for item in items)
            await client.delete(f"/api/dashboards/{group}")
            await client.delete(f"/api/dashboards/{card}")
            assert (await client.get("/api/dashboards")).json()==[]
    try:
        asyncio.run(check())
    finally:
        subprocess.run([*ctl,"-m","fast","-w","stop"],check=True,capture_output=True)


def test_question_title():
    from backend.workspace import question_title
    assert question_title("Please show me   total revenue by category?") == "Total revenue by category"
    title = question_title("Compare " + "customer spending across regions " * 5)
    assert len(title) <= 72 and title.endswith("…")
