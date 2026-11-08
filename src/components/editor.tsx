import { useRef } from 'preact/hooks'

interface Props {
  value: string
  onChange: (value: string) => void
  onRun?: () => void
}

const INDENT = '    '

/** Plain textarea with soft wrapping. Tab indents; Ctrl/Cmd+Enter runs. */
export function Editor({ value, onChange, onRun }: Props) {
  const ta = useRef<HTMLTextAreaElement>(null)

  const onKeyDown = (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      onRun?.()
      return
    }

    if (e.key !== 'Tab' || e.ctrlKey || e.metaKey || e.altKey) return
    e.preventDefault()
    const el = e.currentTarget as HTMLTextAreaElement
    const { selectionStart: a, selectionEnd: b } = el
    onChange(el.value.slice(0, a) + INDENT + el.value.slice(b))
    requestAnimationFrame(() => {
      el.selectionStart = el.selectionEnd = a + INDENT.length
    })
  }

  return (
    <textarea
      class="editor"
      ref={ta}
      value={value}
      wrap="soft"
      spellcheck={false}
      autocomplete="off"
      autocapitalize="off"
      onInput={(e) => onChange(e.currentTarget.value)}
      onKeyDown={onKeyDown}
    />
  )
}
