import { useEffect, useRef, useState } from 'react'
import { QueryError, type QueryResult } from './api'
import { SnapshotDialog } from './SnapshotDialog'
export async function api(path:string, method='GET', body?:unknown) {
  const r=await fetch('/api/'+path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)})
  const data=await r.json()
  if(!r.ok) throw new QueryError(data.error?.message || 'Request failed.', data.retrieval, data.error?.code)
  return data
}
export type Item={id:string,title:string,untitled?:boolean,question?:string,created_at?:string,generated_at?:string}
export function Library({conversation,open,openDashboard,onHistory,onManage,version,busy}:{openDashboard:(items:{r:QueryResult,q:string,id:string,source:string}[],title:string,id:string,date?:string)=>void,onHistory:(items:Item[])=>void,onManage:(item:Item,mode:"rename"|"delete")=>void,conversation:string,
 open:(r:QueryResult,q:string,id:string,source?:string)=>void,version:number,busy:boolean}) {
  const [cards,setCards]=useState<Item[]>([]),[turns,setTurns]=useState<Item[]>([])
  const [error,setError]=useState(''),[revision,refresh]=useState(0)
  const loaded=useRef<string|null>(null)
  const [editor,setEditor]=useState<{runIds:string[],id:string,title:string}|null>(null)
  const [selection,setSelection]=useState<string[]>([])
  const [notice,setNotice]=useState('')
  useEffect(()=>{let active=true
    setError('')
    api('dashboards').then(c=>{if(active)setCards(c)}).catch(e=>{if(active)setError(e.message)})
    Promise.resolve(conversation && conversation!=='new'?api('conversations/'+conversation):[]).then(async h=>{
      if(!active)return
      setTurns(h);onHistory(h)
      if(loaded.current!==conversation){
        const last=h[h.length-1]
        if(last && version===0){const item=await api('query-runs/'+last.id);if(!active)return;open(item.result,item.question,last.id,'History · '+new Date(item.created_at).toLocaleString())}
        loaded.current=conversation
      }
    }).catch(e=>{if(active)setError(e.message)})
    return ()=>{active=false}
  },[conversation,version,revision])
  async function action(fn:()=>Promise<void>){try{await fn();refresh(r=>r+1)}catch(e){setError(String(e))}}
  return <fieldset disabled={busy}><legend>Conversations and saved analyses</legend>
    {turns.length>0&&<h3>Page history</h3>}
    {turns.length>0&&<small>Select up to 20 pages for a chapter.</small>}
    {turns.map(t=><div className="history-row" key={t.id}><label><input type="checkbox" aria-label={'Select '+t.question} checked={selection.includes(t.id)}
      disabled={!selection.includes(t.id)&&selection.length>=20} onChange={e=>setSelection(e.target.checked?[...selection,t.id]:selection.filter(id=>id!==t.id))}/></label>
      <button onClick={()=>action(async()=>{const r=await api('query-runs/'+t.id);open(r.result,r.question,t.id,'History · '+new Date(r.created_at).toLocaleString())})} title={t.question}>{t.question}</button></div>)}
    {turns.length>0&&<div className="dashboard-action"><small aria-live="polite">{selection.length} of 20 selected</small><button disabled={!selection.length} onClick={()=>setEditor({id:conversation,title:'Collected pages',runIds:[...selection]})}>Create Chapter</button></div>}
    <h3>Bookmarks &amp; chapters</h3>{!cards.length&&<small>No bookmarked pages yet.</small>}
    {cards.map(c=><div className="snapshot" key={c.id}>Saved · {new Date(c.generated_at!).toLocaleString()} <button onClick={()=>action(async()=>{
      const r=await api('dashboards/'+c.id);if(r.analyses){
        openDashboard(r.analyses.map((a:{result:QueryResult,question:string,generated_at:string})=>({r:a.result,q:a.question,id:'',source:'Saved chapter · '+new Date(a.generated_at).toLocaleString()})),c.title,c.id,c.generated_at)
      }else open(r.result,r.question,'','Saved bookmark · '+new Date(r.generated_at).toLocaleString())
    })}>{c.title}</button> <button onClick={()=>onManage(c,'rename')}>Rename</button> <button onClick={()=>onManage(c,'delete')}>Delete</button></div>)}
    {editor && <SnapshotDialog dashboard initialTitle={editor.title} rename={false} onCancel={()=>setEditor(null)}
      onSave={async title=>{
        await api('conversations/'+editor.id+'/dashboards','POST',{title,run_ids:editor.runIds});setSelection([])
        
        setNotice('Chapter created.')
        setEditor(null)
        refresh(r=>r+1)
      }}/>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="status">{error}</p>}
  </fieldset>
}
