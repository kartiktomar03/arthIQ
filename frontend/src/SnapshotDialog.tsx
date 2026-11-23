import { useEffect, useRef, useState, type FormEvent } from 'react'

export function SnapshotDialog({initialTitle, entry, deleting, dashboard, rename, onSave, onCancel}: {
  initialTitle: string
  entry?: boolean
  deleting?: boolean
  dashboard?: boolean
  rename: boolean
  onSave: (title: string) => Promise<void>
  onCancel: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const locked = useRef(false)
  const [title, setTitle] = useState(initialTitle.slice(0, 100))
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    const element = dialog.current!
    element.showModal()
    return () => element.close()
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (locked.current || !title.trim()) return
    locked.current = true
    setPending(true)
    setError('')
    try {
      await onSave(title.trim())
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not save the snapshot.')
      locked.current = false
      setPending(false)
    }
  }
  return <dialog ref={dialog} aria-labelledby="snapshot-heading" onCancel={event => {
    event.preventDefault()
    if (!locked.current) onCancel()
  }}>
    <form onSubmit={submit}>
      <h2 id="snapshot-heading">{entry ? (deleting?'Delete Entry?':'Rename Entry') : deleting ? 'Delete saved item?' : rename ? 'Rename saved item' : dashboard ? 'Create Chapter' : 'Bookmark this Page'}</h2>
      {deleting ? <p>{entry ? <>Delete “{initialTitle}” and its query history? Saved bookmarks and chapters will remain available.</> : <>Delete {initialTitle} from your saved library?</>}</p> : <><label htmlFor="snapshot-title">Title</label>
      <input id="snapshot-title" autoFocus required maxLength={100} value={title}
        disabled={pending} onChange={event => setTitle(event.target.value)} /></>}
      {error && <p role="alert">{error}</p>}
      <button disabled={pending || !title.trim()}>{pending ? 'Working…' : deleting ? 'Confirm delete' : 'Save'}</button>
      <button type="button" disabled={pending} onClick={onCancel}>Cancel</button>
    </form>
  </dialog>
}

