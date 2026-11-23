import {lazy,Suspense,useState,type FormEvent} from 'react'
import {createRoot} from 'react-dom/client'
import {ask, QueryError, type QueryResult, type RetrievalDiagnostics} from './api'
import {Leaf,Engraving,number} from './Spread'
import {api,Library,type Item} from './library'
import {ConversationIndex} from './ConversationIndex'
import {SnapshotDialog} from './SnapshotDialog'
import {SQLViewer} from './SQLViewer'
import './styles.css'

const Chart=lazy(()=>import('./Analysis').then(m=>({default:m.InsightCard})))
const examples=['Show total revenue by category.','Which products generate the most revenue?','Who are our top spending customers?','How many completed orders do we have?']
const descriptions:Record<string,string>={categories:'Groups of products',products:'Items in the catalog',orders:'Purchase records and completion status',order_items:'Purchased quantities and prices',customers:'Shop customers'}

function SchemaExplorer({d}:{d:RetrievalDiagnostics}){
  return <details><summary>References · Schema retrieval</summary>
    <p>Retrieval {d.status==='ok'?'completed':d.status==='failed'?'failed':'skipped (full schema)'}</p>
    {d.tables.map(t=><p key={t}><b>{t.replaceAll('_',' ')}</b> — {descriptions[t] || 'Retrieved database table'}</p>)}
    {d.relationships?.map(edge=><code className="edge" key={edge}>{edge.replace(' = ',' ↔ ')}</code>)}
    <details><summary>Retrieval diagnostics</summary><p>{d.document_count} documents · {d.join_count} joins · {d.duration_ms} ms</p><p>Intermediate tables added: {d.expanded?'Yes':'No'}</p></details>
  </details>
}
type Turn={r:QueryResult,q:string,id:string,source:string}
function Evidence({r}:{r:QueryResult}){
  return <><Suspense fallback={<p>Loading visualization…</p>}><Chart result={r}/></Suspense>
    <h3>Result data</h3><small>{r.execution.row_count} rows · {r.execution.duration_ms} ms {r.execution.truncated?'· Limited subset':''}</small>
{r.rows.length?<div className="scroll"><table><thead><tr>{r.columns.map((c,i)=><th key={i}>{c.replaceAll('_',' ')} {r.analysis?.units[i]}</th>)}</tr></thead>
    <tbody>{r.rows.map((row,i)=><tr key={i}>{row.map((v,j)=><td key={j} className={(r.column_types?.[j]?.match(/int|numeric|float|decimal/) || typeof v==='number' || r.analysis?.units[j]==='USD')?'numeric':''}>{v===null?'NULL':String(v)}</td>)}</tr>)}</tbody></table></div>:<p>No rows returned.</p>}</>
}
type Chapter={id:string,title:string,items:Turn[],date?:string}
type View='contents'|'analysis'|'chapter'
function App(){
  const [view,setView]=useState<View>('contents'),[side,setSide]=useState(1)
  const [question,setQuestion]=useState(''),[current,setCurrent]=useState<Turn|null>(null)
  const [items,setItems]=useState<Item[]>([])
  const [posting,setPosting]=useState(false)
  const [history,setHistory]=useState<Item[]>([]),[title,setTitle]=useState('New Entry')
  const [error,setError]=useState(''),[failure,setFailure]=useState<RetrievalDiagnostics>(),[loading,setLoading]=useState(false)
  const [conversation,setConversation]=useState(()=>localStorage.getItem('qp.conversation')??'new'),[version,setVersion]=useState(0)
  const [saving,setSaving]=useState<Turn|null>(null),[notice,setNotice]=useState('')
  const [bookmarks,setBookmarks]=useState<Record<string,string>>({})
  const [chapter,setChapter]=useState<Chapter|null>(null),[saved,setSaved]=useState<Turn|null>(null)
  const [manage,setManage]=useState<{item:Item,mode:'rename'|'delete'}|null>(null)
  const shown=saved||current
  const contents=()=>{setView('contents');setSide(0)}
  function change(id:string){
    if(id!==conversation){setCurrent(null);setHistory([])}
    setConversation(id);localStorage.setItem('qp.conversation',id);setVersion(0)
    setChapter(null);setSaved(null);setQuestion('');setError('');setFailure(undefined);setNotice('')
    setSide(1);setView('contents')
  }
  function open(r:QueryResult,q:string,id:string,source='Fresh result'){
    const turn={r,q,id,source}
    setChapter(null)
    if(source.startsWith('Saved'))setSaved(turn)
    else {setCurrent(turn);setSaved(null)}
    setView('analysis');setSide(0);setError('');setFailure(undefined)
    if(source==='Fresh result')setVersion(v=>v+1)
  }
  function selectPage(i:number){
    if(!chapter)return
    setSaved(chapter.items[i]);setView('analysis');setSide(0)
  }
  const index=chapter&&saved?chapter.items.indexOf(saved):history.findIndex(t=>t.id===shown?.id)
  const count=chapter&&saved?chapter.items.length:saved?1:history.length
  async function navigate(i:number){
    if(chapter){selectPage(i);return}
    if(!history[i])return
    setLoading(true)
    try{const t=await api('query-runs/'+history[i].id);open(t.result,t.question,history[i].id,'History · '+new Date(t.created_at).toLocaleString())}
    catch(e){setError(String(e))}finally{setLoading(false)}
  }
  async function submit(e:FormEvent){
    e.preventDefault()
    if(!question.trim()||loading)return
    setLoading(true);setError('');setFailure(undefined)
    try{
      let id=conversation
      if(id==='new'){
        id=(await api('conversations','POST')).id
        setConversation(id);localStorage.setItem('qp.conversation',id)
      }
      if(id){const data=await api('conversations/'+id+'/query','POST',{question:question.trim()})
        if(data.title){
          setTitle(data.title)
          setItems(rows=>rows.some(row=>row.id===id)
            ?rows.map(row=>row.id===id?{...row,title:data.title,untitled:false}:row)
            :[{id,title:data.title,untitled:false},...rows])
        }
        open(data.result,data.question,data.id)}
      else open(await ask(question.trim()),question.trim(),'')
      setQuestion('')
    }catch(err){setError(err instanceof Error?err.message:'Query failed');if(err instanceof QueryError)setFailure(err.retrieval)}
    finally{setLoading(false)}
  }
  const composer=<form className="composer" onSubmit={submit}><label htmlFor="question">Business question</label>
    <textarea aria-describedby="composer-help" id="question" maxLength={1000} readOnly={loading} value={question}
      placeholder={current?'Ask a follow-up question…':'Ask a question about your business…'} onChange={e=>setQuestion(e.target.value)}
      onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();e.currentTarget.form?.requestSubmit()}}}/>
    <div className="formfoot"><small id="composer-help">Enter to run · Shift+Enter for a new line{!question.trim()&&<span className="empty-hint">Type a question to enable Run query.</span>}</small><button className="solid" disabled={loading||!question.trim()}>{loading?'Running…':'Run query'}</button></div></form>
  const labels=view==='contents'?['Contents','New entry']:view==='chapter'?['Chapter overview','Chapter contents']:['Observation','Evidence']
  const active=()=>{setSaved(null);setChapter(null);setSide(current?0:1);setView(current?'analysis':'contents')}
  const historyDate=history.find(t=>t.id===shown?.id)?.created_at
  return <><header><img className="wordmark" src="/brand/wordmark.svg" alt="अर्थIQ / ArthIQ"/><span className="imprint">The Living Ledger</span>
    <nav aria-label="Book navigation"><button disabled={loading} onClick={contents} aria-current={view==='contents'?'page':undefined}>Contents</button>
    {current&&<button disabled={loading} onClick={active}>Active conversation</button>}
    {chapter&&<button onClick={()=>{setView('chapter');setSide(0)}}>Chapter</button>}</nav></header>
    <main><div className="mobilebar"><span>{labels[side]}</span><button onClick={()=>setSide(1-side)}>{labels[1-side]} →</button></div>
    <div className="book" data-side={side} hidden={view!=='contents'}>
      <Leaf running="The business journal" label="Contents" page={1}><div className="kicker">Reader’s index</div><h1>Table of<br/><em>Contents.</em></h1>
      <ConversationIndex {...{conversation,version,busy:loading,setTitle,items,setItems}} change={id=>{
        if(id===conversation&&current){active();return}
        change(id)
      }}/>
      <Library key={conversation} {...{conversation,open,version,onHistory:setHistory,busy:loading,
        onManage:(item:Item,mode:'rename'|'delete')=>setManage({item,mode}),
        openDashboard:(items:Turn[],name:string,id:string,date?:string)=>{setChapter({id,title:name,items,date});setSaved(null);setView('chapter');setSide(0);setError('')}
      }}/></Leaf>
      <Leaf running="Opening entry" label="New entry" page={2}><Engraving/><h2>Every Number<br/><em>Has a Story.</em></h2>
        {view==='contents'&&composer}<div className="examples">{examples.map(q=><button key={q} onClick={()=>{setQuestion(q);document.getElementById('question')?.focus()}}>{q}</button>)}</div>
        <small>{current?.r.retrieval?.datasource_id || 'PostgreSQL'} · {title}</small></Leaf>
    </div>
    {view==='analysis'&&shown&&<section className="book" data-side={side} aria-label="Query results">
      <Leaf running="Analysis entry" label="Analysis" page={Math.max(index,0)*2+3}><div className="kicker">The question</div>
        <h1 className="question user-question">{shown.q}</h1><h3>Observation</h3><p className="observation">{shown.r.analysis?.summary || 'See the returned rows for this analysis.'}</p>
        <p className="context">{shown.source}{shown.source==='Fresh result'&&historyDate?' · '+new Date(historyDate).toLocaleString():''}
        {shown.r.analysis?.units.map((u,i)=>u&&<span key={i}><br/>{shown.r.columns[i]} · {u}</span>)}</p>
        <SQLViewer result={shown.r}/>{shown.r.retrieval&&<SchemaExplorer d={shown.r.retrieval}/>}
        <div className="arrows"><button disabled={loading||index<=0} onClick={()=>navigate(index-1)}>← Previous entry</button>
        <button disabled={loading||index<0||index+1>=count} onClick={()=>navigate(index+1)}>Next entry →</button></div>
      </Leaf><Leaf running={'Figure '+number(Math.max(index,0)+1)} label="Results" page={Math.max(index,0)*2+4}>
        {!saved&&<button className="ribbon" aria-describedby={!shown.id?"bookmark-reason":undefined} data-unavailable={!shown.id} disabled={!shown.id||posting||!!bookmarks[shown.id]} onClick={()=>{setSaving(shown);setNotice('')}}>{!shown.id?'Bookmark unavailable':posting?'Saving bookmark…':bookmarks[shown.id]?'Bookmarked':'Bookmark this Page'}</button>}
        {!shown.id&&!saved&&<small id="bookmark-reason">Single questions have no saved run. Use New Entry to bookmark an analysis.</small>}
        <div className="kicker">{shown.r.retrieval?.datasource_id || 'Query evidence'}</div><h2>Results</h2>
        <Evidence key={shown.id||shown.q} r={shown.r}/>
      </Leaf></section>}
    {view==='chapter'&&chapter&&<div className="book" data-side={side}>
      <Leaf running="Collected work" label="Collection" page={1}><div className="chapterseal" aria-hidden="true">§</div><div className="kicker">Saved chapter</div>
      <h1>{chapter.title}</h1><p className="observation">{chapter.items.length} collected analyses, in conversation order.</p>
      {chapter.date&&<small>Created {new Date(chapter.date).toLocaleString()}</small>}
      <div className="arrows"><button className="solid" onClick={()=>selectPage(0)}>Open chapter →</button>
      <button onClick={()=>setManage({item:chapter,mode:'rename'})}>Rename</button><button onClick={()=>setManage({item:chapter,mode:'delete'})}>Delete</button></div></Leaf>
      <Leaf running="Chapter contents" label="Chapter index" page={2}><h2>Inside this <em>chapter.</em></h2><div className="chapterpages">
      {chapter.items.map((t,i)=><button key={i} onClick={()=>selectPage(i)}><span className={'tab t'+i%3}>{number(i+1)}</span><span><strong>{t.q}</strong><span>{t.r.analysis?.summary}</span></span><i>↗</i></button>)}</div></Leaf></div>}
    {view==='analysis'&&!saved&&composer}
    {loading&&<p role="status">Loading analysis…</p>}{error&&<p role="alert">{error}</p>}{failure&&<SchemaExplorer d={failure}/>}
    {notice&&<p role="status">{notice}</p>}
    {saving&&<SnapshotDialog initialTitle={saving.q} rename={false} onCancel={()=>setSaving(null)} onSave={async title=>{
      setPosting(true)
      try {const card=await api('dashboards','POST',{title,run_id:saving.id})
      setBookmarks(v=>({...v,[saving.id]:card.id}));setSaving(null);setNotice('Page bookmarked.');setVersion(v=>v+1)
      } finally {setPosting(false)}
    }}/>}
    {manage&&<SnapshotDialog initialTitle={manage.item.title} rename={manage.mode==='rename'} deleting={manage.mode==='delete'} onCancel={()=>setManage(null)} onSave={async name=>{
      const id=manage.item.id
      if(manage.mode==='delete'){
        await api('dashboards/'+id,'DELETE')
        setBookmarks(v=>Object.fromEntries(Object.entries(v).filter(([,card])=>card!==id)))
        if(chapter?.id===id){setChapter(null);setSaved(null);contents()}
      }else{
        await api('dashboards/'+id,'PATCH',{title:name})
        if(chapter?.id===id)setChapter({...chapter,title:name})
      }
      setManage(null);setVersion(v=>v+1);setNotice(manage.mode==='delete'?'Saved item deleted.':'Title updated.')
    }}/>}
    </main></>
}
createRoot(document.getElementById('root')!).render(<App/>)

