import { useEffect, useState } from "react";
import type { Viewer, ViewerProps } from "./viewer";
import { Frame } from "./Frame";
import { bytes } from "../lib/format";
import { Loading, Problem } from "../components/bits";

/**
 * PDF viewer using the browser's built-in reader in an iframe.
 *
 * If the store serves the file as something other than application/pdf (e.g.
 * octet-stream), the browser would download it instead of displaying it, so
 * we fetch the bytes, check the signature, and display them via an object URL.
 */

/** Max size to fetch into memory for relabelling. */
const INLINE_LIMIT = 32 * 1024 * 1024;

const SERVED_AS_PDF = "application/pdf";

function useRenderable({ url, stored }: ViewerProps) {
  const served = (stored.content_type ?? "").toLowerCase().split(";")[0].trim();
  const direct = served === SERVED_AS_PDF;

  const [made, setMade] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [oversize, setOversize] = useState(false);

  useEffect(() => {
    // Reset state; the component is reused across blobs.
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
        if (!response.ok) throw new Error(`download failed (${response.status})`);
        const buffer = await response.arrayBuffer();

        // Only relabel bytes that really are a pdf.
        const head = new TextDecoder("ascii").decode(buffer.slice(0, 5));
        if (head !== "%PDF-") throw new Error("not a valid pdf");

        // `window.Blob` to avoid confusion with the API's Blob type.
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
      <div className="vg-withheld">too large to preview ({bytes(stored.size)})</div>
    );
  }
  if (problem) return <Problem>{problem}</Problem>;
  if (src === null) return <Loading />;

  return (
    <Frame kind="pdf" stored={stored} bare>
      <iframe
        className="dp-page"
        src={src}
        title={blob.description ?? blob.key}
        // Don't leak the signed url.
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
