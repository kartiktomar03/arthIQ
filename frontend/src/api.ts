type Cell = string | number | boolean | null

export interface RetrievalDiagnostics {
  datasource_id?:string
  mode: 'rag' | 'full'
  status: 'ok' | 'failed' | 'skipped'
  tables: string[]
  document_count: number
  expanded: boolean
  join_count: number
  relationships?: string[]
  duration_ms: number
}

export interface QueryResult {
  analysis?: { summary:string, charts:string[], formatted_sql:string, units:string[] }
  column_types?:string[]
  sql: string
  columns: string[]
  rows: Cell[][]
  execution: {
    duration_ms: number
    row_count: number
    truncated: boolean
  }
  retrieval?: RetrievalDiagnostics
}

export class QueryError extends Error {
  constructor(message: string, readonly retrieval?: RetrievalDiagnostics, readonly code?:string) {
    super(message)
  }
}

export async function ask(question: string): Promise<QueryResult> {
  const response = await fetch('/api/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload) {
    throw new QueryError(payload?.error?.message ?? 'The query service could not respond.', payload?.retrieval)
  }
  return payload
}
