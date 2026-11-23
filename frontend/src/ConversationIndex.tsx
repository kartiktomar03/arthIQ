import {useEffect,useRef,useState,type Dispatch,type SetStateAction} from 'react'
import {api,type Item} from './library'
import {SnapshotDialog} from './SnapshotDialog'

type Props={
  conversation:string
  items:Item[]
  setItems:Dispatch<SetStateAction<Item[]>>
  version:number
  busy:boolean
  change:(id:string)=>void
  setTitle:(title:string)=>void
}

const displayTitle=(item:Item)=>(item.untitled ?? item.title==='New conversation')?'New Entry':item.title

export function ConversationIndex({conversation,version,busy,change,setTitle,items,setItems}:Props){
  const [filter,setFilter]=useState('')
  const [menu,setMenu]=useState<string|null>(null)
  const [editor,setEditor]=useState<{item:Item,deleting:boolean}|null>(null)
  const [loading,setLoading]=useState(true),[creating,setCreating]=useState(false)
  const [error,setError]=useState(''),[revision,invalidate]=useState(0)
  const [notice,setNotice]=useState('')
  const generation=useRef(0)
  const trigger=useRef<HTMLButtonElement|null>(null)
  useEffect(()=>{
    const request=++generation.current
    setLoading(true);setError('')
    api('conversations').then((rows:Item[])=>{
      if(request!==generation.current)return
      setItems(rows)
      const active=rows.find(row=>row.id===conversation)
      setTitle(active?displayTitle(active):conversation===''?'Single question':'New Entry')
    }).catch(e=>{if(request===generation.current)setError(e.message)})
      .finally(()=>{if(request===generation.current)setLoading(false)})
    return ()=>{generation.current++}
  },[conversation,version,revision,setTitle,setItems])

  async function create(){
    setCreating(true);setNotice('');setError('')
    try{
      const {id}=await api('conversations','POST')
      generation.current++
      setItems(old=>[{id,title:'New conversation'},...old.filter(row=>row.id!==id)])
      setFilter('');setMenu(null);change(id)
    }catch(e){setError(String(e))}finally{setCreating(false)}
  }
  function closeEditor(){
    setEditor(null)
    requestAnimationFrame(()=>trigger.current?.focus())
  }
  async function save(title:string){
    if(!editor)return
    const {item,deleting}=editor
    await api('conversations/'+item.id,deleting?'DELETE':'PATCH',deleting?undefined:{title})
    generation.current++
    if(deleting){
      setItems(old=>old.filter(row=>row.id!==item.id))
      if(item.id===conversation)change('new')
    }else{
      setItems(old=>old.map(row=>row.id===item.id?{...row,title,untitled:false}:row))
      if(item.id===conversation)setTitle(title)
    }
    closeEditor();invalidate(n=>n+1);setNotice(deleting?'Entry deleted.':'Entry renamed.')
  }
  const matches=(item:Item)=>displayTitle(item).toLowerCase().includes(filter.trim().toLowerCase())
  const visible=items.filter(item=>matches(item)||item.id===conversation)
  return <fieldset disabled={busy||creating} className="conversation-index"><legend>Conversation index</legend>
    <button onClick={create}>{creating?'Creating…':'New Entry'}</button>
    <h3>Recent entries</h3><input aria-label="Filter entries" placeholder="Search entries…" value={filter} onChange={e=>setFilter(e.target.value)}/>
    {loading&&<small role="status">Loading entries…</small>}
    {error&&<div role="alert">{error} <button onClick={()=>invalidate(n=>n+1)}>Retry list</button></div>}
    {items.some(row=>row.id===conversation&&!matches(row))&&<small>Active entry is shown outside the filter.</small>}
    <nav aria-label="Recent Entries">
      {!visible.length&&!loading&&!error&&<small>{filter?'No matching entries.':'No conversations yet.'}</small>}
      {visible.map((item,i)=><div className="entry-row" key={item.id} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setMenu(v=>v===item.id?null:v)}}
        onKeyDown={e=>{if(e.key==='Escape'){setMenu(null);trigger.current?.focus()}}}>
        <button className="entry-name" title={displayTitle(item)} aria-current={conversation===item.id?'page':undefined} onClick={()=>{setMenu(null);change(item.id)}}>
          <small>{String(i+1).padStart(2,'0')}</small><span>{displayTitle(item)}</span></button>
        <button className="entry-more" aria-label={'Actions for '+displayTitle(item)} aria-expanded={menu===item.id}
          onClick={e=>{trigger.current=e.currentTarget;setMenu(menu===item.id?null:item.id)}}>⋯</button>
        {menu===item.id&&<div className="entry-actions" role="group" aria-label="Entry actions">
          {['Rename Entry','Delete Entry'].map((label,index)=><button key={label} onClick={()=>{setMenu(null);setEditor({item,deleting:index===1})}}>{label}</button>)}
        </div>}
      </div>)}
    </nav>
    <button className="quiet" onClick={()=>change('')}>Single question</button>
    {editor&&<SnapshotDialog entry initialTitle={editor.item.title} deleting={editor.deleting} rename={!editor.deleting} onSave={save} onCancel={closeEditor}/>}
    {notice&&<small role="status">{notice}</small>}
  </fieldset>
}
