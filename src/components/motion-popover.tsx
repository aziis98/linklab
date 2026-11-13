import type { ComponentChildren } from "preact";
import { createPortal } from "preact/compat";
import { useEffect, useId, useRef, useState } from "preact/hooks";
import IconChevronDown from "~icons/tabler/chevron-down";
import IconPlayerPlay from "~icons/tabler/player-play";
import IconPlayerPause from "~icons/tabler/player-pause";

export function MotionPopover({ state, disabled, onToggle, children }: {
  state: string; disabled: boolean; onToggle: () => void; children: ComponentChildren;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 48, right: 12 });
  function close(restore = false) {
    setOpen(false);
    if (restore) trigger.current?.focus();
  }
  useEffect(() => {
    if (state === "unavailable" || state === "error") setOpen(true);
  }, [state]);
  useEffect(() => {
    if (!open) return;
    function place() {
      const rect = trigger.current!.getBoundingClientRect();
      setPosition({ top: rect.bottom + 8, right: Math.max(8, innerWidth - rect.right) });
    }
    function outside(event: PointerEvent) {
      const target = event.target as Element;
      if (!panel.current?.contains(target) && !trigger.current?.contains(target) && !target.closest('[role="listbox"]')) close();
    }
    function key(event: KeyboardEvent) {
      if (event.target instanceof Element && event.target.closest('[role="listbox"]')) return;
      if (event.key === "Escape" && !event.defaultPrevented) { event.preventDefault(); close(true); }
    }
    place();
    panel.current?.focus();
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", key);
    window.addEventListener("resize", place);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", key);
      window.removeEventListener("resize", place);
    };
  }, [open]);
  const playing = state === "playing";
  const label = playing ? "Pause wander" : state === "paused" ? "Resume wander" : state === "starting" ? "Starting…" : "Wander";
  return <>
    <div class="motion-split">
      <button class={`btn motion-split__action ${playing ? "btn--active" : ""}`} aria-label="Toggle wander" aria-pressed={playing} disabled={disabled || state === "busy" || state === "starting"} onClick={onToggle}>
        {playing ? <IconPlayerPause width="14" height="14" /> : <IconPlayerPlay width="14" height="14" />}{label}
      </button>
      <button ref={trigger} class="btn motion-split__menu" aria-label="Wander settings" aria-expanded={open} aria-controls={id} aria-haspopup="dialog" disabled={disabled} onClick={() => setOpen(!open)}><IconChevronDown width="14" height="14" /></button>
    </div>
    {createPortal(<div ref={panel} id={id} class="motion-popover" role="dialog" aria-label="Motion exploration" tabIndex={-1} hidden={!open} style={position}>
      <div class="motion-popover__heading"><strong>Motion exploration</strong><button class="btn btn--icon" aria-label="Close motion settings" onClick={() => close(true)}>×</button></div>
      {children}
    </div>, document.body)}
  </>;
}
