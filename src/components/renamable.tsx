import { useEffect, useRef, useState } from 'preact/hooks'

interface Props {
  value: string
  onCommit: (name: string) => void
}

/** Read-only name that turns into an input on click. */
export function Renamable({ value, onCommit }: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const input = useRef<HTMLInputElement>(null)

  // keep the draft in sync when the name changes from elsewhere
  useEffect(() => setDraft(value), [value])

  useEffect(() => {
    if (editing) input.current?.select()
  }, [editing])

  const commit = () => {
    const name = draft.trim()
    if (name && name !== value) onCommit(name)
    else setDraft(value)
    setEditing(false)
  }

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      commit()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setDraft(value)
      setEditing(false)
      input.current?.blur()
    }
  }

  if (!editing) {
    return (
      <button
        type="button"
        class="rename"
        title="Click to rename"
        onClick={() => setEditing(true)}
      >
        {value}
      </button>
    )
  }

  return (
    <input
      ref={input}
      class="rename rename--input"
      value={draft}
      spellcheck={false}
      autocomplete="off"
      aria-label="File name"
      onInput={(e) => setDraft(e.currentTarget.value)}
      onBlur={commit}
      onKeyDown={onKeyDown}
    />
  )
}
