import { useEffect, useRef, useState } from 'preact/hooks'
import IconChevronDown from '~icons/tabler/chevron-down'
import IconFileCode from '~icons/tabler/file-code'
import IconFilePlus from '~icons/tabler/file-plus'
import IconTrash from '~icons/tabler/trash'
import { relativeTime, type FileEntry } from '@/files'
import { Renamable } from './renamable'

interface Props {
  files: FileEntry[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onRename: (id: string, name: string) => void
  onDelete: (id: string) => void
}

const MENU_ID = 'file-switcher-menu'

/**
 * Combo box in the app bar: the current file name doubles as a rename field,
 * and a separate caret button owns opening the recent-files list.
 */
export function FileSwitcher({
  files,
  activeId,
  onSelect,
  onNew,
  onRename,
  onDelete,
}: Props) {
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(-1)
  const root = useRef<HTMLDivElement>(null)
  const toggle = useRef<HTMLButtonElement>(null)
  const items = useRef<(HTMLButtonElement | null)[]>([])

  const active = files.find((f) => f.id === activeId) ?? null
  const recent = [...files].sort((a, b) => b.editedAt - a.editedAt)
  const count = recent.length

  useEffect(() => {
    if (!open) return
    const onDocDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onDocDown)
    return () => document.removeEventListener('pointerdown', onDocDown)
  }, [open])

  useEffect(() => {
    if (open) items.current[cursor]?.focus()
  }, [open, cursor])

  const openAt = (i: number) => {
    setOpen(true)
    setCursor(i)
  }

  /** Closing via keyboard hands focus back to the caret button. */
  const close = (restoreFocus = false) => {
    setOpen(false)
    if (restoreFocus) toggle.current?.focus()
  }

  const commit = (i: number) => {
    const file = recent[i]
    if (file) onSelect(file.id)
    close(true)
  }

  const onListKeyDown = (e: KeyboardEvent) => {
    const moves: Record<string, number> = {
      ArrowDown: 1,
      ArrowUp: -1,
      Home: -count,
      End: count,
    }
    if (e.key in moves) {
      e.preventDefault()
      setCursor((i) => Math.min(count - 1, Math.max(0, i + moves[e.key])))
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      commit(cursor)
    } else if (e.key === 'Escape' || e.key === 'Tab') {
      close(e.key === 'Escape')
    }
  }

  const onToggleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      openAt(0)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      openAt(count - 1)
    }
  }

  return (
    <div class="switcher" ref={root}>
      {active ? (
        <Renamable
          value={active.name}
          onCommit={(name) => onRename(active.id, name)}
        />
      ) : (
        <span class="switcher__none">no file</span>
      )}

      <button
        type="button"
        class="switcher__toggle"
        ref={toggle}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={MENU_ID}
        aria-label="Recent files"
        title="Recent files"
        onClick={() => (open ? close() : openAt(0))}
        onKeyDown={onToggleKeyDown}
      >
        <IconChevronDown class="icon switcher__caret" width="12" height="12" />
      </button>

      {open && (
        <div
          class="switcher__menu"
          id={MENU_ID}
          role="listbox"
          aria-label="Recent files"
          onKeyDown={onListKeyDown}
        >
          <div class="switcher__label">Recent</div>

          {recent.map((file, i) => (
            <div
              key={file.id}
              role="option"
              class="switcher__row"
              aria-selected={file.id === activeId}
              data-active={i === cursor || undefined}
            >
              <button
                type="button"
                class="switcher__item-btn"
                ref={(el) => {
                  items.current[i] = el
                }}
                tabIndex={-1}
                title={new Date(file.editedAt).toLocaleString()}
                onClick={() => commit(i)}
              >
                <IconFileCode class="icon" width="14" height="14" />
                <span class="text">
                  <span class="name u-mono">{file.name}</span>
                  <span class="meta">{relativeTime(file.editedAt)}</span>
                </span>
              </button>
              <button
                type="button"
                class="switcher__delete-btn"
                title={`Delete ${file.name}`}
                aria-label={`Delete ${file.name}`}
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(file.id)
                }}
              >
                <IconTrash class="icon" width="13" height="13" />
              </button>
            </div>
          ))}

          {count === 0 && <div class="switcher__label">nothing yet</div>}

          <div class="switcher__sep" role="separator" />

          <button
            type="button"
            class="switcher__item"
            tabIndex={-1}
            onClick={() => {
              onNew()
              close(true)
            }}
          >
            <IconFilePlus class="icon" width="14" height="14" />
            <span class="text">
              <span class="name">New file…</span>
            </span>
          </button>
        </div>
      )}
    </div>
  )
}
