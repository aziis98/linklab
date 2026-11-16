import { useCallback, useEffect, useRef, useState } from 'preact/hooks'
import type { ComponentChildren } from 'preact'

const KEY = 'linklab.split.v1'
const MIN = 15
const MAX = 85
const DEFAULT = 40

interface Props {
  initial?: number
  left: ComponentChildren
  right: ComponentChildren
}

/** Two-pane horizontal split with a draggable, keyboard-operable separator. */
export function Split({ initial, left, right }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const sep = useRef<HTMLDivElement>(null)
  const [pct, setPct] = useState(
    () => Number(localStorage.getItem(KEY)) || initial || DEFAULT,
  )
  const [dragging, setDragging] = useState(false)

  useEffect(() => {
    localStorage.setItem(KEY, String(pct))
  }, [pct])

  const clamp = (v: number) => Math.min(MAX, Math.max(MIN, v))

  const fromClientX = useCallback((x: number) => {
    const rect = host.current?.getBoundingClientRect()
    if (rect) setPct(clamp(((x - rect.left) / rect.width) * 100))
  }, [])

  // Suppress the browser's own drag/selection so sweeping the pointer across the
  // editor can't select text or start a native drag mid-resize.
  useEffect(() => {
    if (!dragging) return
    const swallow = (e: Event) => e.preventDefault()
    const noSelect = () => document.getSelection()?.removeAllRanges()
    window.addEventListener('dragstart', swallow)
    window.addEventListener('selectstart', swallow)
    window.addEventListener('pointermove', swallow, { passive: false })
    noSelect()
    return () => {
      window.removeEventListener('dragstart', swallow)
      window.removeEventListener('selectstart', swallow)
      window.removeEventListener('pointermove', swallow)
    }
  }, [dragging])

  const onPointerDown = (e: PointerEvent) => {
    if (e.button !== 0) return
    e.preventDefault()
    sep.current?.setPointerCapture(e.pointerId)
    // preventDefault above suppresses the implicit focus, so ask for it
    // explicitly — otherwise the keyboard resize affordance is unreachable.
    sep.current?.focus({ preventScroll: true })
    setDragging(true)
    fromClientX(e.clientX)
  }

  const onPointerMove = (e: PointerEvent) => {
    if (dragging) fromClientX(e.clientX)
  }

  const endDrag = (e: PointerEvent) => {
    if (sep.current?.hasPointerCapture(e.pointerId)) {
      sep.current.releasePointerCapture(e.pointerId)
    }
    setDragging(false)
  }

  const onKeyDown = (e: KeyboardEvent) => {
    const step = e.shiftKey ? 10 : 2
    const moves: Record<string, number> = {
      ArrowLeft: -step,
      ArrowRight: step,
    }
    if (e.key in moves) {
      e.preventDefault()
      setPct((v) => clamp(v + moves[e.key]))
    } else if (e.key === 'Home') {
      e.preventDefault()
      setPct(MIN)
    } else if (e.key === 'End') {
      e.preventDefault()
      setPct(MAX)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      setPct(initial || DEFAULT)
    }
  }

  return (
    <div
      class="split"
      ref={host}
      style={{ '--split': `${pct}%` }}
      data-dragging={dragging || undefined}
    >
      {left}
      <div
        class="splitter"
        ref={sep}
        role="separator"
        tabIndex={0}
        aria-orientation="vertical"
        aria-label="Resize panes"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={MIN}
        aria-valuemax={MAX}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onLostPointerCapture={() => setDragging(false)}
        onKeyDown={onKeyDown}
      />
      {right}
    </div>
  )
}
