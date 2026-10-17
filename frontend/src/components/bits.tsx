import type { ReactNode } from "react";

/** Section header. */
export function Head(props: {
  title: string;
  count?: number;
  desc?: string;
  note?: string;
  children?: ReactNode;
}) {
  return (
    <div className="vg-sect-head">
      <span className="vg-sect-title">{props.title}</span>
      {props.count !== undefined && <span className="vg-sect-count">[{props.count}]</span>}
      {props.desc && <span className="vg-sect-desc">{props.desc}</span>}
      <span className="vg-sect-fill" />
      {props.note && <span className="vg-sect-note">{props.note}</span>}
      {props.children && <span className="vg-sect-right">{props.children}</span>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="vg-empty">{children}</div>;
}

export function Loading() {
  return (
    <div className="vg-empty" aria-busy="true">
      loading…
    </div>
  );
}


export function Problem({ children }: { children: ReactNode }) {
  return (
    <div className="vg-error" role="alert">
      {children}
    </div>
  );
}

export function Field(props: {
  label: string;
  gloss?: string;
  htmlFor?: string;
  /** Keep the label's case (e.g. a column name). */
  identifier?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="dp-field">
      <label
        className={`dp-field-label${props.identifier ? " is-identifier" : ""}`}
        htmlFor={props.htmlFor}
      >
        {props.label}
      </label>
      {props.children}
      {props.gloss && <span className="dp-field-gloss">{props.gloss}</span>}
    </div>
  );
}

/** Read-only SQL preview. */
export function Sketch({ statement, prompt = ":" }: { statement: string; prompt?: string }) {
  return (
    <div className="dp-sketch">
      <span className="dp-sketch-prompt" aria-hidden="true">
        {prompt}
      </span>
      <code className="dp-sketch-body">{statement}</code>
    </div>
  );
}

/** Key–value row. */
export function KV({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="vg-kv">
      <span className="vg-kv-k">{k}</span>
      <span className="vg-kv-v">{children}</span>
    </div>
  );
}

/** Stat tile; clickable when `onOpen` is given. */
export function Fact({
  label,
  value,
  meta,
  onOpen,
  title,
}: {
  label: string;
  value: ReactNode;
  meta?: string;
  onOpen?: () => void;
  title?: string;
}) {
  const body = (
    <>
      <div className="vg-fact-label">{label}</div>
      <div className="vg-fact-value">{value}</div>
      {meta && <div className="vg-fact-meta">{meta}</div>}
    </>
  );

  if (!onOpen) return <div className="vg-fact">{body}</div>;

  return (
    <button type="button" className="vg-fact dp-fact-link" onClick={onOpen} title={title}>
      {body}
    </button>
  );
}
