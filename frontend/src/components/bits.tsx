import type { ReactNode } from "react";

/**
 * Section header — the most-used component in the system.
 *
 * The description is required, not optional: §9 of the design system says
 * every panel explains itself in one plain-English line. It is the only sans
 * in the header because it is the only sentence.
 */
export function Head(props: {
  title: string;
  count?: number;
  desc: string;
  note?: string;
  children?: ReactNode;
}) {
  return (
    <div className="vg-sect-head">
      <span className="vg-sect-title">{props.title}</span>
      {props.count !== undefined && <span className="vg-sect-count">[{props.count}]</span>}
      <span className="vg-sect-desc">{props.desc}</span>
      <span className="vg-sect-fill" />
      {props.note && <span className="vg-sect-note">{props.note}</span>}
      {props.children && <span className="vg-sect-right">{props.children}</span>}
    </div>
  );
}

/** An empty state that names its cause. Never "no data". */
export function Empty({ children }: { children: ReactNode }) {
  return <div className="vg-empty">{children}</div>;
}

/** Loading is a lowercase sentence in the empty box, not a spinner. */
export function Loading({ what }: { what: string }) {
  return (
    <div className="vg-empty" aria-busy="true">
      reading {what}…
    </div>
  );
}

/** The platform's own words, in rust, inside a rust hairline. */
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
  /** The label is a column name rather than a word, so it keeps its own case. */
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

/**
 * A statement, shown before it runs.
 *
 * This is the console's signature: no form changes a table without printing
 * the SQL it composed. The prompt marks it as a statement rather than a label,
 * and it is never editable here — the well above the results is where a reader
 * writes their own.
 */
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

/** Key–value row: the value is right-aligned so values form a clean edge. */
export function KV({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="vg-kv">
      <span className="vg-kv-k">{k}</span>
      <span className="vg-kv-v">{children}</span>
    </div>
  );
}

/**
 * One reading off the band under a title.
 *
 * A fact that stands for a place you can go says so by being pressable. It is
 * the same tile either way — the band keeps one rhythm whether or not a given
 * reading leads anywhere.
 */
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
  /** Where this reading leads, if it leads anywhere. */
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
