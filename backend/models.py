from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


class QueryRequest(BaseModel):
    datasource_id: str | None = None
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class SQLProposal(BaseModel):
    sql: str | None = Field(max_length=8000)
    reason: str | None = Field(default=None, max_length=500)


class ExecutionMetadata(BaseModel):
    duration_ms: float
    row_count: int
    truncated: bool


class RetrievalSource(BaseModel):
    document_id: str
    table: str
    source_type: Literal["table", "column", "relationship", "business_term"]
    score: float


class RetrievalDiagnostics(BaseModel):
    mode: Literal["rag", "full"]
    status: Literal["ok", "failed", "skipped"]
    tables: list[str] = Field(default_factory=list)
    seed_tables: list[str] = Field(default_factory=list)
    document_count: int = 0
    expanded: bool = False
    join_count: int = 0
    relationships: list[str] = Field(default_factory=list)
    duration_ms: float = 0
    datasource_id: str | None = None
    schema_version: str | None = None
    sources: list[RetrievalSource] = Field(default_factory=list)


class Analysis(BaseModel):
    units: list[str] = Field(default_factory=list)
    summary: str
    charts: list[str]
    formatted_sql: str


class QueryResponse(BaseModel):
    datasource_id: str = "demo_shop"
    sql: str
    columns: list[str]
    rows: list[list[str | int | float | bool | None]]
    execution: ExecutionMetadata
    retrieval: RetrievalDiagnostics | None = None
    analysis: Analysis | None = None
    column_types: list[str] = Field(default_factory=list)


class QueryFailure(Exception):
    def __init__(self, status: int, code: str, message: str, retrieval: RetrievalDiagnostics | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.retrieval = retrieval
