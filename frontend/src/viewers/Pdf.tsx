import { useEffect, useState } from "react";
import type { Viewer, ViewerProps } from "./viewer";
import { Frame } from "./Frame";
import { bytes } from "../lib/format";
import { Loading, Problem } from "../components/bits";

/**
 * A document, drawn by the browser's own viewer.
 *
 * Every current browser ships a pdf reader with pages, search, zoom and print
 * already in it, reached by pointing a frame at the file. Shipping a second one
 * — pdf.js and its worker are a larger download than the whole console — would
 * buy a consistent toolbar and nothing a reader here needs.
 *
 * There is a catch, and it is the whole of the code below. The registry picks
 * this viewer from the stored type *or* from the key, but a browser decides
 * what to do with a response from its `Content-Type` header alone. A pdf the
 * store labelled `application/octet-stream` — which is what most uploads are
 * labelled by whatever put them there — is routed here by its name and then
 * downloaded rather than drawn, because octet-stream is the header that means
 * "save this". The name got a vote the browser was never going to count.
 *
 * So when the header already says pdf, the frame is pointed at the url and the
 * browser streams it. When it does not, the bytes are fetched once, checked for
 * the pdf signature, and handed back through a blob url carrying the type we
 * know to be true.
 */

/** Past this the document is not fetched into memory; it is offered as a file. */
const INLINE_LIMIT = 32 * 1024 * 1024;

const SERVED_AS_PDF = "application/pdf";

function useRenderable({ url, stored }: ViewerProps) {
  const served = (stored.content_type ?? "").toLowerCase().split(";")[0].trim();
  const direct = served === SERVED_AS_PDF;

  const [made, setMade] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [oversize, setOversize] = useState(false);

  useEffect(() => {
    // Reset first and unconditionally. This component is reused as the reader
    // moves from one blob to the next, so a verdict reached about the last one
    // outlives it unless it is cleared here.
    setMade(null);
    setProblem(null);
    setOversize(false);

    if (direct) return;
    if (stored.size > INLINE_LIMIT) {
      setOversize(true);
      return;
    }

    const stop = new AbortController();
    let objectUrl: string | null = null;

    void (async () => {
      try {
        const response = await fetch(url, { signal: stop.signal });
        if (!response.ok) throw new Error(`the store refused the read with ${response.status}`);
        const buffer = await response.arrayBuffer();

        // Check the signature before re-labelling. Relabelling on the strength
        // of a file name would let anything at all be declared a pdf by being
        // called one, and the point of this path is that the name was never
        // evidence.
        const head = new TextDecoder("ascii").decode(buffer.slice(0, 5));
        if (head !== "%PDF-") {
          throw new Error(
            "this is named like a pdf and does not begin like one, so it is not shown as a document.",
          );
        }

        // `window.Blob` because a blob in this codebase is usually the record,
        // not the browser type.
        objectUrl = URL.createObjectURL(new window.Blob([buffer], { type: SERVED_AS_PDF }));
        if (stop.signal.aborted) URL.revokeObjectURL(objectUrl);
        else setMade(objectUrl);
      } catch (error) {
        if (stop.signal.aborted) return;
        setProblem(error instanceof Error ? error.message : String(error));
      }
    })();

    return () => {
      stop.abort();
      // The frame is gone, and this url is the last reference to the bytes.
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url, direct, stored.size]);

  return { src: direct ? url : made, problem, oversize };
}

function Document(props: ViewerProps) {
  const { stored, blob } = props;
  const { src, problem, oversize } = useRenderable(props);

  if (oversize) {
    return (
      <div className="vg-withheld">
        this holds {bytes(stored.size)}, and the store labels it{" "}
        <code className="dp-inline-code">{stored.content_type ?? "nothing"}</code> rather than{" "}
        <code className="dp-inline-code">application/pdf</code>. drawing it here would mean fetching
        all of it first, so it is offered as a file instead — use <strong>open bytes</strong> above.
      </div>
    );
  }
  if (problem) return <Problem>{problem}</Problem>;
  if (src === null) return <Loading what="the document" />;

  return (
    <Frame kind="pdf" stored={stored} bare>
      <iframe
        className="dp-page"
        src={src}
        title={blob.description ?? blob.key}
        // The reader is the browser's, so its own referrer rules apply; the
        // signed url is the whole authorization and should not travel onward.
        referrerPolicy="no-referrer"
      />
    </Frame>
  );
}

export const pdf: Viewer = {
  kind: "pdf",
  types: [SERVED_AS_PDF],
  extensions: ["pdf"],
  render: Document,
};
