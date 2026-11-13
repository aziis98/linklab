import IconChevronDown from "~icons/tabler/chevron-down";
import { createPortal } from "preact/compat";
import { useEffect, useLayoutEffect, useId, useRef, useState } from "preact/hooks";

interface Option {
  value: string;
  label: string;
  disabled?: boolean;
}
interface Props {
  label: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
  disabled?: boolean;
}

/** Themed listbox with keyboard navigation and a viewport-positioned popup. */
export function Dropdown({ label, value, options, onChange, disabled }: Props) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [position, setPosition] = useState<{
    left: number;
    top?: number;
    bottom?: number;
    width: number;
    maxHeight: number;
  }>({ left: 0, top: 0, width: 160, maxHeight: 240 });
  const chosen = options.find((o) => o.value === value);
  function close(restore = false) {
    setOpen(false);
    if (restore) trigger.current?.focus();
  }
  function show() {
    if (disabled) return;
    const rect = trigger.current!.getBoundingClientRect();
    const width = Math.max(160, rect.width);
    const below = innerHeight - rect.bottom - 12,
      above = rect.top - 12;
    const opensAbove =
      below < Math.min(240, options.length * 30 + 10) && above > below;
    setPosition({
      left: Math.max(8, Math.min(rect.left, innerWidth - width - 8)),
      ...(opensAbove
        ? { bottom: innerHeight - rect.top + 4 }
        : { top: rect.bottom + 4 }),
      width,
      maxHeight: Math.max(1, Math.min(240, opensAbove ? above : below)),
    });
    const selected = options.findIndex((o) => o.value === value && !o.disabled);
    setActive(
      selected < 0
        ? Math.max(
            0,
            options.findIndex((o) => !o.disabled),
          )
        : selected,
    );
    setOpen(true);
  }
  function choose(index: number) {
    if (!options[index] || options[index].disabled) return;
    onChange(options[index].value);
    close(true);
  }
  function key(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      close(true);
      return;
    }
    if (e.key === "Tab") {
      close();
      trigger.current?.focus();
      return;
    }
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      choose(active);
      return;
    }
    let next = active;
    if (e.key === "Home") next = 0;
    else if (e.key === "End") next = options.length - 1;
    else if (e.key === "ArrowDown") next = (active + 1) % options.length;
    else if (e.key === "ArrowUp")
      next = (active + options.length - 1) % options.length;
    else if (e.key.length === 1) {
      next = options.findIndex(
        (o, i) =>
          i > active && o.label.toLowerCase().startsWith(e.key.toLowerCase()),
      );
      if (next < 0)
        next = options.findIndex((o) =>
          o.label.toLowerCase().startsWith(e.key.toLowerCase()),
        );
    } else return;
    e.preventDefault();
    if (next < 0) return;
    const direction = e.key === "ArrowUp" || e.key === "End" ? -1 : 1;
    for (let i = 0; i < options.length && options[next].disabled; i++)
      next = (next + direction + options.length) % options.length;
    setActive(next);
  }
  useLayoutEffect(() => {
    if (!open) return;
    menu.current?.focus();
    function outside(e: PointerEvent) {
      const target = e.target as Node;
      if (!trigger.current?.contains(target) && !menu.current?.contains(target))
        close();
    }
    function reposition(e: Event) {
      if (e.target instanceof Node && menu.current?.contains(e.target)) return;
      close();
    }
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [open]);
  useEffect(() => {
    menu.current
      ?.querySelector<HTMLElement>(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, open]);
  return (
    <>
      <button
        type="button"
        ref={trigger}
        class="dropdown__trigger btn"
        aria-label={label}
        title={label}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => (open ? close() : show())}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            show();
          }
        }}
      >
        <span>{chosen?.label ?? label}</span>
        <span aria-hidden="true" class="dropdown__chevron">
          <IconChevronDown width="12" height="12" />
        </span>
      </button>
      {open &&
        createPortal(
          <div
            id={id}
            ref={menu}
            class="dropdown__menu"
            role="listbox"
            tabIndex={-1}
            aria-label={label}
            aria-activedescendant={`${id}-${active}`}
            onKeyDown={key}
            style={position}
          >
            {options.map((option, index) => (
              <div
                key={option.value}
                id={`${id}-${index}`}
                role="option"
                aria-selected={option.value === value}
                aria-disabled={option.disabled || undefined}
                data-index={index}
                data-active={index === active || undefined}
                class="dropdown__option"
                onPointerMove={() => setActive(index)}
                onClick={() => choose(index)}
              >
                <span>{option.label}</span>
                <span aria-hidden="true">
                  {option.value === value ? "✓" : ""}
                </span>
              </div>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}
