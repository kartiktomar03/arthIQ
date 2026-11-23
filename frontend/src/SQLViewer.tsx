import type {QueryResult} from './api'
export function SQLViewer({result}:{result:QueryResult}) {
  return <details><summary>Behind the Numbers · SQL</summary>
    <button onClick={()=>void navigator.clipboard.writeText(result.sql)}>Copy executed SQL</button>
    <pre>{(result.analysis?.formatted_sql || result.sql).split('\n').map((line,i)=><div key={i}>
      <span aria-hidden="true">{i+1}  </span>{line.split(/\b(SELECT|FROM|WHERE|JOIN|GROUP BY|ORDER BY|LIMIT|SUM|COUNT|AS|ON)\b/g)
      .map((part,j)=>j%2?<strong key={j}>{part}</strong>:part)}</div>)}</pre>
  </details>
}
