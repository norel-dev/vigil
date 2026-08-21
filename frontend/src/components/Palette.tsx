import { useEffect, useMemo, useRef, useState } from "react";

export interface PaletteItem {
  id: string;
  /** `cmd` for something to do, anything else for somewhere to go. */
  kind: string;
  label: string;
  hint: string;
  run: () => void;
}

/**
 * The command palette.
 *
 * It and the command line read the same registry, so the two can never
 * disagree about what exists. Commands come first because they are what the
 * palette is for; objects follow, so that typing a table's name is also a way
 * of reaching it.
 */
export function Palette(props: { items: PaletteItem[]; onDismiss: () => void }) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return props.items;
    return props.items.filter(
      (item) =>
        item.label.toLowerCase().includes(needle) || item.hint.toLowerCase().includes(needle),
    );
  }, [props.items, query]);

  useEffect(() => setCursor(0), [query]);

  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>(".vg-palette-row.is-selected")
      ?.scrollIntoView({ block: "nearest" });
  }, [cursor, matches]);

  const commands = matches.filter((item) => item.kind === "cmd");
  const objects = matches.filter((item) => item.kind !== "cmd");
  const ordered = [...commands, ...objects];

  return (
    <div
      className="vg-overlay is-heavy"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) props.onDismiss();
      }}
    >
      <div className="vg-palette" role="dialog" aria-modal="true" aria-label="command palette">
        <div className="vg-palette-input-row">
          <span className="vg-palette-cursor" aria-hidden="true">
            ▌
          </span>
          <input
            className="vg-palette-input"
            autoFocus
            spellCheck={false}
            aria-label="type a command or search"
            placeholder="type a command or search…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown" || (event.key === "n" && event.ctrlKey)) {
                event.preventDefault();
                setCursor((at) => Math.min(at + 1, ordered.length - 1));
              } else if (event.key === "ArrowUp" || (event.key === "p" && event.ctrlKey)) {
                event.preventDefault();
                setCursor((at) => Math.max(at - 1, 0));
              } else if (event.key === "Enter") {
                event.preventDefault();
                const chosen = ordered[cursor];
                if (chosen) {
                  props.onDismiss();
                  chosen.run();
                }
              } else if (event.key === "Escape") {
                event.preventDefault();
                props.onDismiss();
              }
            }}
          />
        </div>

        <div ref={listRef} style={{ maxHeight: "46vh", overflowY: "auto" }}>
          {ordered.length === 0 && (
            <div className="vg-palette-section" style={{ padding: "14px" }}>
              nothing here answers to “{query}” — commands match on their name, objects on theirs
            </div>
          )}
          {commands.length > 0 && <div className="vg-palette-section">commands [{commands.length}]</div>}
          {commands.map((item, index) => (
            <Row key={item.id} item={item} selected={index === cursor} onRun={props.onDismiss} />
          ))}
          {objects.length > 0 && <div className="vg-palette-section">objects [{objects.length}]</div>}
          {objects.map((item, index) => (
            <Row
              key={item.id}
              item={item}
              selected={commands.length + index === cursor}
              onRun={props.onDismiss}
            />
          ))}
        </div>

        <div className="vg-palette-foot">
          <span>
            <kbd>↑↓</kbd> navigate
          </span>
          <span>
            <kbd>↵</kbd> run
          </span>
          <span>
            <kbd>esc</kbd> dismiss
          </span>
        </div>
      </div>
    </div>
  );
}

function Row({
  item,
  selected,
  onRun,
}: {
  item: PaletteItem;
  selected: boolean;
  onRun: () => void;
}) {
  return (
    <div
      className={`vg-palette-row${selected ? " is-selected" : ""}`}
      role="option"
      aria-selected={selected}
      onMouseDown={(event) => {
        event.preventDefault();
        onRun();
        item.run();
      }}
    >
      <span className="vg-palette-key">{item.kind === "cmd" ? ":" : "→"}</span>
      <span className="vg-palette-desc">
        {item.label} <em>{item.hint}</em>
      </span>
      <span className="vg-palette-tag">{item.kind}</span>
      <span className="vg-palette-tag">{selected ? "↵" : ""}</span>
    </div>
  );
}
