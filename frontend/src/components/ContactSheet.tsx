import { useEffect, useState } from "react";
import type { BlobView, Uuid } from "../lib/api";
import { downloadUrl } from "../lib/media";
import { bytes } from "../lib/format";
import { resolve } from "../viewers/registry";

/** Thumbnail grid of blobs. Blobs without uploaded bytes get a dashed frame. */
export function ContactSheet(props: {
  project: Uuid;
  views: BlobView[];
  openKey: string | null;
  onOpen: (key: string) => void;
}) {
  return (
    <div className="dp-sheet">
      {props.views.map((view) => (
        <Shot
          key={view.blob.key}
          project={props.project}
          view={view}
          on={view.blob.key === props.openKey}
          onOpen={() => props.onOpen(view.blob.key)}
        />
      ))}
    </div>
  );
}

function Shot(props: { project: Uuid; view: BlobView; on: boolean; onOpen: () => void }) {
  const { blob, stored } = props.view;
  const viewer = resolve(stored?.content_type ?? blob.content_type, blob.key);
  const Thumb = viewer.thumb;
  const [url, setUrl] = useState<string | null>(null);
  const [broken, setBroken] = useState(false);

  const showable = stored !== null && Thumb !== undefined;

  useEffect(() => {
    if (!showable) return;
    let live = true;
    downloadUrl(props.project, blob.key)
      .then((signed) => live && setUrl(signed))
      .catch(() => live && setBroken(true));
    return () => {
      live = false;
    };
  }, [props.project, blob.key, showable]);

  return (
    <button
      className={`dp-shot${props.on ? " is-on" : ""}`}
      onClick={props.onOpen}
      aria-current={props.on ? "true" : undefined}
    >
      <span className={`dp-shot-stage${stored === null ? " is-hollow" : ""}`}>
        {stored === null ? (
          <span className="dp-shot-glyph">not uploaded</span>
        ) : broken ? (
          <span className="dp-shot-glyph">no preview</span>
        ) : !showable || Thumb === undefined ? (
          <span className="dp-shot-glyph">{viewer.kind}</span>
        ) : url === null ? (
          <span className="dp-shot-glyph">loading…</span>
        ) : (
          <Thumb url={url} stored={stored} blob={blob} onBroken={() => setBroken(true)} />
        )}
      </span>
      <span className="dp-shot-caption">
        <span className="dp-shot-key" title={blob.key}>
          {blob.key}
        </span>
        <span className="dp-shot-meta">
          {stored ? `${bytes(stored.size)} · ` : ""}{viewer.kind}
        </span>
      </span>
    </button>
  );
}
