import { useEffect, useRef, type ReactNode } from "react";

/**
 * Overlays — the only place shadows exist in this system.
 *
 * Two of them. The terminal modal, with its corner brackets, is for things
 * that read as a running operation. The plain dialog, quieter and serif-titled,
 * is for ordinary forms and choices. Everything the console asks for is a form,
 * so the dialog does most of the work.
 */

function useOverlay(onDismiss: () => void) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Give the first control focus, so a form can be filled without reaching
    // for the mouse at all.
    const first = ref.current?.querySelector<HTMLElement>(
      "input:not([type=hidden]), textarea, select, button",
    );
    first?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onDismiss();
        return;
      }
      // Keep tabbing inside the overlay: an invisible page behind it should
      // not be reachable.
      if (event.key !== "Tab" || !ref.current) return;
      const focusable = Array.from(
        ref.current.querySelectorAll<HTMLElement>(
          "a[href], button:not([disabled]), input:not([type=hidden]), textarea, select, [tabindex]:not([tabindex='-1'])",
        ),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onDismiss]);

  return ref;
}

export function Dialog(props: {
  eyebrow: string;
  title: string;
  onDismiss: () => void;
  width?: number;
  children: ReactNode;
}) {
  const ref = useOverlay(props.onDismiss);
  return (
    <div
      className="vg-overlay is-heavy"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) props.onDismiss();
      }}
    >
      <div
        className="vg-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={props.title}
        ref={ref}
        style={props.width ? { width: props.width, maxWidth: "100%" } : undefined}
      >
        <div className="vg-dialog-head">
          <div>
            <div className="vg-dialog-eyebrow">{props.eyebrow}</div>
            <div className="vg-dialog-title">{props.title}</div>
          </div>
          <button className="vg-close" onClick={props.onDismiss} aria-label="dismiss">
            ×
          </button>
        </div>
        {props.children}
      </div>
    </div>
  );
}

export function Modal(props: {
  kind: string;
  title: string;
  onDismiss: () => void;
  width?: number;
  children: ReactNode;
}) {
  const ref = useOverlay(props.onDismiss);
  return (
    <div
      className="vg-overlay is-heavy"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) props.onDismiss();
      }}
    >
      <div
        className="vg-modal"
        role="dialog"
        aria-modal="true"
        aria-label={props.title}
        ref={ref}
        style={props.width ? { width: props.width, maxWidth: "100%" } : undefined}
      >
        <div className="vg-modal-head">
          <span className="vg-modal-kind">{props.kind}</span>
          <span className="vg-modal-title">{props.title}</span>
          <button className="vg-close" onClick={props.onDismiss} aria-label="dismiss">
            ×
          </button>
        </div>
        <div className="vg-modal-body">{props.children}</div>
      </div>
    </div>
  );
}
