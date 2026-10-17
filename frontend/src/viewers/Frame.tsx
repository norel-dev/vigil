import type { ReactNode } from "react";
import type { StoredBlob } from "../lib/api";
import { bytes } from "../lib/format";

/** Media stage with a caption (kind, stored type, size). */
export function Frame(props: {
  kind: string;
  stored: StoredBlob;
  /** Drop the stage border, for edge-to-edge content. */
  bare?: boolean;
  children: ReactNode;
}) {
  return (
    <figure className="dp-media" style={{ margin: 0 }}>
      <div className={`dp-media-stage${props.bare ? " is-bare" : ""}`}>{props.children}</div>
      <figcaption className="vg-caption">
        <span className="n">{props.kind}</span>
        <span>{props.stored.content_type ?? "unknown type"}</span>
        <span className="src">{bytes(props.stored.size)}</span>
      </figcaption>
    </figure>
  );
}

/** Shown when the browser can't decode the media (e.g. H.265 .mov in Chrome). */
export function Undecodable({ stored }: { stored: StoredBlob }) {
  return (
    <div className="vg-withheld">
      this browser can't play{" "}
      <code className="dp-inline-code">{stored.content_type ?? "this file"}</code>
    </div>
  );
}
