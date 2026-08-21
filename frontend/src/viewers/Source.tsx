import { useEffect, useState } from "react";
import type { Viewer, ViewerProps } from "./viewer";
import { TEXT_LIMIT, TooLarge, readSource, type Source } from "../lib/text";
import { bytes } from "../lib/format";
import { Loading, Problem } from "../components/bits";

/**
 * Bytes, printed.
 *
 * Three formats end up here and only one of them is a surprise. Plain text is
 * obvious and markdown is text with punctuation, but html arrives as source on
 * purpose: a blob is bytes someone uploaded to a project, and rendering it
 * would run a stranger's markup inside a page holding an api key. The console
 * shows what is in the file instead, which for reading a stored document is
 * usually what was wanted anyway.
 *
 * This is the only viewer that has to hold the whole blob to do its job — the
 * others hand a url to an element and let the browser stream it — so it is the
 * only one with a ceiling on what it will attempt.
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
        // Abort is this effect tearing down, not a failure to report.
        if (stop.signal.aborted) return;
        if (error instanceof TooLarge) setOversize(true);
        else setProblem(error instanceof Error ? error.message : String(error));
      });
    return () => stop.abort();
  }, [url, stored.size]);

  if (oversize) {
    return (
      <div className="vg-withheld">
        this holds {bytes(stored.size)}, past the {bytes(TEXT_LIMIT)} the console will print. the
        limit is about reading rather than bandwidth — use <strong>open bytes</strong> above to take
        the file itself.
      </div>
    );
  }
  if (problem) return <Problem>{problem}</Problem>;
  if (source === null) return <Loading what="the bytes" />;

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
        <div className="dp-source-warn">
          these bytes are not valid utf-8. what is printed below is a best effort and the characters
          it could not read are shown as <code className="dp-inline-code">�</code>.
        </div>
      )}
      <pre className={`dp-source-body${wrap ? " is-wrapped" : ""}`}>{source.text}</pre>
    </div>
  );
}

/**
 * Every printed format is the same component with a different name on it. The
 * name is what the caption and the contact sheet say, so `notes.md` reads as
 * markdown rather than as a generic file that happened to be legible.
 */
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
  "shown as source — the console does not run markup it did not write",
);

export const markdown = printing("markdown", ["text/markdown", "text/x-markdown"], ["md", "markdown", "mdown"]);

export const text = printing(
  "text",
  ["text/", "application/json", "application/xml", "application/x-yaml", "application/yaml"],
  ["txt", "text", "log", "json", "csv", "tsv", "xml", "yaml", "yml", "toml", "ini", "sql"],
);
