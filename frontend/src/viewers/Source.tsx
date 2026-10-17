import { useEffect, useState } from "react";
import type { Viewer, ViewerProps } from "./viewer";
import { TEXT_LIMIT, TooLarge, readSource, type Source } from "../lib/text";
import { bytes } from "../lib/format";
import { Loading, Problem } from "../components/bits";

/**
 * Text viewer. HTML is shown as source on purpose: rendering uploaded markup
 * would run it in a page holding the api key. Size-limited, since the whole
 * file is loaded into memory.
 */
function Printed({ url, stored, note }: ViewerProps & { note?: string }) {
  const [source, setSource] = useState<Source | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [oversize, setOversize] = useState(false);
  const [wrap, setWrap] = useState(true);

  useEffect(() => {
    const stop = new AbortController();
    setSource(null);
    setProblem(null);
    setOversize(false);
    readSource(url, stored.size, stop.signal)
      .then(setSource)
      .catch((error) => {
        if (stop.signal.aborted) return;
        if (error instanceof TooLarge) setOversize(true);
        else setProblem(error instanceof Error ? error.message : String(error));
      });
    return () => stop.abort();
  }, [url, stored.size]);

  if (oversize) {
    return (
      <div className="vg-withheld">
        too large to preview ({bytes(stored.size)}, limit {bytes(TEXT_LIMIT)})
      </div>
    );
  }
  if (problem) return <Problem>{problem}</Problem>;
  if (source === null) return <Loading />;

  return (
    <div className="dp-source">
      <div className="dp-source-bar">
        <span className="dp-source-count">
          {source.lines.toLocaleString()} {source.lines === 1 ? "line" : "lines"} ·{" "}
          {bytes(stored.size)}
        </span>
        {note && <span className="dp-source-note">{note}</span>}
        <span className="vg-sect-fill" />
        <div className="vg-btn-group">
          <button className={`vg-btn${wrap ? " is-on" : ""}`} onClick={() => setWrap(true)}>
            wrap
          </button>
          <button className={`vg-btn${wrap ? "" : " is-on"}`} onClick={() => setWrap(false)}>
            off
          </button>
        </div>
      </div>
      {source.lossy && (
        <div className="dp-source-warn">not valid utf-8; some characters may be wrong</div>
      )}
      <pre className={`dp-source-body${wrap ? " is-wrapped" : ""}`}>{source.text}</pre>
    </div>
  );
}

/** A text viewer with its own kind label. */
function printing(
  kind: string,
  types: readonly string[],
  extensions: readonly string[],
  note?: string,
): Viewer {
  return { kind, types, extensions, render: (props) => <Printed {...props} note={note} /> };
}

export const html = printing(
  "html",
  ["text/html", "application/xhtml+xml"],
  ["html", "htm", "xhtml"],
  "shown as source",
);

export const markdown = printing("markdown", ["text/markdown", "text/x-markdown"], ["md", "markdown", "mdown"]);

export const text = printing(
  "text",
  ["text/", "application/json", "application/xml", "application/x-yaml", "application/yaml"],
  ["txt", "text", "log", "json", "csv", "tsv", "xml", "yaml", "yml", "toml", "ini", "sql"],
);
