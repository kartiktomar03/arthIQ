# अर्थIQ (ArthIQ)

**Every Number Has a Story.**

ArthIQ turns a business question into a chart, a result table and the SQL behind both. Its Living Ledger workspace lets a reader follow a conversation, bookmark an individual analysis or collect selected results into a chapter.

## How a question becomes an answer

```text
React + TypeScript → FastAPI → PostgreSQL catalog discovery
  → Schema RAG (CPU MiniLM + local Qdrant + foreign-key paths)
  → Groq SQL proposal → SQLGlot validation → read-only PostgreSQL
  → bounded rows, exact decimals, executed SQL and retrieval evidence
```

Groq receives the question and authorized schema context. The retrieval index contains schema metadata and business definitions. PostgreSQL computes the answer. Workspace writes use a separate login and store conversations and historical results. The Vite frontend uses Recharts for compatible visualizations.

## Datasets and evidence

| Datasource | Contents | Metric definition |
| --- | --- | --- |
| Demo Shop (default) | Five seeded tables in `querypilot_ai.shop` | Revenue in USD sums quantity × purchase price for completed orders. |
| Olist (optional API integration) | 1,550,922 records across nine tables in `arthiq_olist.olist` | Delivered merchandise value in BRL sums each delivered item price once, excluding freight. Distinct customers use `customer_unique_id`. |

**Verified baseline — 6/6 PASS.** Live questions matched independent PostgreSQL reference SQL for 99,441 orders, 96,478 delivered orders, 96,096 distinct customers, 112,650 item rows, 3,095 unique sellers and BRL 13,221,498.11 in delivered merchandise value. [Executed SQL and results](evaluation/olist-live-results.txt) · [Reference SQL](database/olist/reference.sql)

**Owner-reported exploratory testing.** The project owner estimated approximately 26–27 correct answers across 30 manually tried questions. This informal observation has no independently reproduced question set or scoring protocol.

## Screenshots

These captures show the actual React interface using browser-test fixtures.

![Living Ledger opening spread with contents and question composer](docs/screenshots/empty-1440.png)

[Analysis with chart and result table](docs/screenshots/conversation-1440.png) · [Saved chapter with two selected pages](docs/screenshots/dashboard-1440.png)

## Local setup on Windows

Use PowerShell 7, Python 3.11–3.14, PostgreSQL (19 for the Olist scripts), Node.js 22.12+ and npm. Run commands from the repository root. Use one API worker with local Qdrant. Python dependency ranges are in `requirements*.txt`; the frontend has an npm lockfile.

### 1. Install the backend and create a dedicated database

Use a development PostgreSQL cluster where the two project role names are reserved for QueryPilot. Start PostgreSQL locally and create a database named `querypilot_ai` using pgAdmin or the optional `createdb` command below. Substitute your local administrator username if it differs from `postgres`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "torch>=2.11,<3" --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# Optional when createdb is on PATH. Skip if you created the database in pgAdmin.
createdb -h 127.0.0.1 -U postgres -W querypilot_ai
```

### 2. Bootstrap and seed

Enter DSNs in the form `postgresql://USER:PASSWORD@127.0.0.1:5432/querypilot_ai`. Percent-encode reserved characters in DSN passwords. Enter raw passwords when prompted for the two role passwords.

```powershell
$env:QP_ADMIN_DSN = Read-Host "Administrator DSN" -MaskInput
$env:QP_MIGRATION_PASSWORD = Read-Host "Migration role password" -MaskInput
$env:QP_ANALYTICS_PASSWORD = Read-Host "Analytics role password" -MaskInput
try {
    .\.venv\Scripts\python.exe -m database.setup bootstrap
    if ($LASTEXITCODE -ne 0) { throw "Database bootstrap failed." }
} finally {
    Remove-Item Env:QP_ADMIN_DSN, Env:QP_MIGRATION_PASSWORD, Env:QP_ANALYTICS_PASSWORD
}

$env:QP_MIGRATION_DSN = Read-Host "querypilot_migrator DSN" -MaskInput
try {
    .\.venv\Scripts\python.exe -m database.setup seed
    if ($LASTEXITCODE -ne 0) { throw "Database seed failed." }
} finally {
    Remove-Item Env:QP_MIGRATION_DSN
}
```

`seed.sql` resets the five demo tables to the same data on every run. Run it only against the dedicated demo database. The bootstrap changes database privileges and sets the analytics role defaults. The API uses only `querypilot_analytics`; keep the admin and migration passwords out of its environment.

### 3. Configure the workspace and backend

Run the workspace migration once on the dedicated demo database. In the interactive psql session, set the workspace password using the PostgreSQL command shown below, then exit with `\q`.

```powershell
psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -U postgres -d querypilot_ai -f database/002_workspace.sql
psql -X -h 127.0.0.1 -U postgres -d querypilot_ai
```
```text
\password querypilot_workspace
\q
```

Copy `.env.example` to `.env` on first setup. Set these values locally:

| Variable | Purpose |
| --- | --- |
| `ANALYTICS_DSN` | Demo Shop reader, `querypilot_analytics` |
| `WORKSPACE_DSN` | Conversation and snapshot metadata, `querypilot_workspace` |
| `GROQ_API_KEY`, `GROQ_MODEL` | Hosted SQL generation and a model supporting JSON output |
| `OLIST_ANALYTICS_DSN` | Optional Olist reader, `arthiq_olist_analytics`, at `127.0.0.1:5432/arthiq_olist` |
| `QUERY_TIMEOUT_MS`, `MAX_ROWS`, `MAX_RESPONSE_BYTES` | Execution and response limits |
| `SCHEMA_MODE`, `SCHEMA_TOP_K`, `SCHEMA_MIN_SIMILARITY`, `SCHEMA_DATASOURCE_ID`, `QDRANT_PATH`, `EMBEDDING_LOCAL_FILES_ONLY` | Retrieval settings and local index/model cache |

### 4. Start the application

```powershell
.\.venv\Scripts\python.exe -m backend.rag
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The first index run needs the CPU model weights. Open a second terminal from the project root:

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run dev
```

Open [the local workspace](http://127.0.0.1:5173) and ask **Which are the top 5 products by total revenue?** Open the evidence page to inspect the SQL. Bookmark the result or select several runs for a chapter.

### Optional Olist verification

Acquire the dataset separately and follow the [Olist import guide](database/olist/README.md). The importer compares source and database rows and checks reader privileges. For an existing import, stop the API to release the local Qdrant lock, then run:

```powershell
.\database\olist\Verify-Olist.ps1
```

The launcher checks the reader password interactively and runs the six live comparisons. For API use, supply `"datasource_id": "olist"` on `POST /api/query` or conversation creation. Existing conversations retain their source.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run test:snapshots
```

The build includes the TypeScript check. Browser tests use headless Edge on Windows. Set `QP_TEST_ANALYTICS_DSN` locally to exercise the seeded Demo Shop regression. The workspace integration test uses a disposable PostgreSQL cluster and accepts `QP_PG_BIN` for the binaries. Automated tests mock Groq. The separate [retrieval evaluation](evaluation/RESULTS.md) uses a fixture SQL provider.

## Security and limitations

- Run on localhost. The workspace currently has one local owner. Multi-user authentication and tenant isolation are outside v1.0.
- SQLGlot allows a limited SELECT grammar over retrieved authorized tables and columns. Execution enforces a restricted role, read-only transaction, statement deadlines and row/byte limits. Unsupported constructs include CTEs, window functions and subqueries.
- A valid query can still answer the wrong business question. Review the metric definition, joins, executed SQL and truncation indicator before relying on a result.
- Keep administrator and migration credentials outside the running app. Store reader credentials locally. Questions and retrieved schema context go to the configured Groq service.
- The dataset, credentials, persistent vector index and local workspace database are provisioned separately. A local Qdrant directory supports one owning process at a time.
