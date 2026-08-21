import type { ReactNode } from "react";
import type { StoredBlob } from "../lib/api";
import { bytes } from "../lib/format";

/**
 * The stage and its caption.
 *
 * Every viewer that shows something rather than prints it says the same three
 * things underneath: what kind of thing this is, what the store calls it, and
 * how big it is. The caption is the store's account of the bytes, which is why
 * it names the stored type and not the declared one — the reader can compare
 * the two in the Record below, and this is the half that the browser acted on.
 */
export function Frame(props: {
  kind: string;
  stored: StoredBlob;
  /** Left off where the stage draws its own edge-to-edge surface, as a page does. */
  bare?: boolean;
  children: ReactNode;
}) {
  return (
    <figure className="dp-media" style={{ margin: 0 }}>
      <div className={`dp-media-stage${props.bare ? " is-bare" : ""}`}>{props.children}</div>
      <figcaption className="vg-caption">
        <span className="n">{props.kind}</span>
        <span>{props.stored.content_type ?? "type unstated"}</span>
        <span className="src">{bytes(props.stored.size)}</span>
      </figcaption>
    </figure>
  );
}

/**
 * What to say when the browser holds the bytes and still cannot play them.
 *
 * This is the common case for QuickTime: a `.mov` carrying H.265 is a valid
 * file that Safari plays and Chrome will not touch. Nothing is wrong with the
 * blob, so it is not reported as damage.
 */
export function Undecodable({ stored }: { stored: StoredBlob }) {
  return (
    <div className="vg-withheld">
      this browser will not decode{" "}
      <code className="dp-inline-code">{stored.content_type ?? "these bytes"}</code>. the file is
      intact — another browser or a local player may well open it. use{" "}
      <strong>open bytes</strong> above to fetch it.
    </div>
  );
}
