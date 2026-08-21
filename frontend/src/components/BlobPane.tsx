import { useEffect, useState } from "react";
import { ApiError, api, uploadTo, type BlobView, type Uuid } from "../lib/api";
import { downloadUrl, forget } from "../lib/media";
import { Head, KV, Loading, Problem } from "./bits";
import { bytes, stamp } from "../lib/format";
import { resolve } from "../viewers/registry";

/**
 * One blob, looked at.
 *
 * The API reports the record and the stored bytes as two separate things,
 * because a blob's record can exist before its data does. This view keeps them
 * separate too: a blob that was recorded and never filled is a normal state,
 * and it is told plainly rather than rendered as a broken image.
 */
export function BlobPane(props: {
  project: Uuid;
  view: BlobView;
  canWrite: boolean;
  onDeleted: () => void;
  onReplaced: () => void;
  onAskDelete: (confirm: { title: string; body: string; verb: string; run: () => Promise<void> }) => void;
}) {
  const { blob, stored } = props.view;
  // The store's type first and the recorded one only as a fallback: the two
  // are asked separately and can disagree, and the browser acts on the store's.
  const viewer = resolve(stored?.content_type ?? blob.content_type, blob.key);
  const Contents = viewer.render;
  const [url, setUrl] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [replacing, setReplacing] = useState(false);

  useEffect(() => {
    setUrl(null);
    setProblem(null);
    if (stored === null) return;
    let live = true;
    downloadUrl(props.project, blob.key)
      .then((signed) => live && setUrl(signed))
      .catch((error) =>
        live && setProblem(error instanceof ApiError ? error.message : String(error)),
      );
    return () => {
      live = false;
    };
  }, [props.project, blob.key, stored]);

  const replace = async (file: File) => {
    setReplacing(true);
    setProblem(null);
    try {
      const access = await api.blobAccess(props.project, blob.key, "upload");
      await uploadTo(access, file);
      forget(props.project, blob.key);
      props.onReplaced();
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : String(error));
    } finally {
      setReplacing(false);
    }
  };

  return (
    <div className="vg-stack">
      <header className="vg-head">
        <div>
          <div className="vg-eyebrow">
            <span>blob</span>
            <span className="id">· {blob.datastore_name}</span>
          </div>
          <h1 className="vg-title is-small vg-break">{blob.key}</h1>
          <div className="vg-subtitle">
            {blob.description ?? "no description was given when this blob was recorded"}
          </div>
        </div>
        <div className="vg-head-side">
          <div className="vg-row-flex">
            <span className={`vg-chip${stored ? " is-high" : ""}`}>
              <span className="vg-chip-dot" />
              {stored ? `filled · ${bytes(stored.size)}` : "recorded · no bytes"}
            </span>
          </div>
          <div className="vg-head-meta">
            <span>{blob.datastore_name}</span>
            <span>·</span>
            <span>{viewer.kind}</span>
            <span>·</span>
            <span>changed {stamp(stored?.last_modified)}</span>
          </div>
          <div className="vg-row-flex">
            {stored && url && (
              <a className="vg-btn" href={url} target="_blank" rel="noreferrer">
                open bytes
              </a>
            )}
            <label className="vg-btn" style={{ cursor: props.canWrite ? "pointer" : "not-allowed" }}>
              {replacing ? "uploading…" : stored ? "replace" : "upload bytes"}
              <input
                type="file"
                hidden
                disabled={!props.canWrite || replacing}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void replace(file);
                  event.target.value = "";
                }}
              />
            </label>
            <button
              className="vg-btn is-danger"
              disabled={!props.canWrite}
              onClick={() =>
                props.onAskDelete({
                  title: "Delete this blob",
                  body: `Deleting removes the bytes from ${blob.datastore_name} and the platform's record of them together. There is no signed url for deleting, because nothing handed to a client could guarantee both halves went.`,
                  verb: "delete blob",
                  run: async () => {
                    await api.deleteBlob(props.project, blob.key);
                    forget(props.project, blob.key);
                    props.onDeleted();
                  },
                })
              }
            >
              delete
            </button>
          </div>
        </div>
      </header>

      <section>
        <Head
          title="Contents"
          desc="the bytes themselves, fetched through a signed url that is good for one read of this one key and stops working shortly after it is issued."
        />
        {problem && <Problem>{problem}</Problem>}
        {stored === null ? (
          <div className="vg-withheld">
            this blob was recorded but nothing has been uploaded under its key. that is a normal
            state, not a broken one — use <strong>upload bytes</strong> above to fill it.
          </div>
        ) : url === null && !problem ? (
          <Loading what="a signed url" />
        ) : url === null ? null : (
          <Contents url={url} stored={stored} blob={blob} />
        )}
      </section>

      <section>
        <Head
          title="Record"
          desc="what the platform holds about this blob, as against what the store holds. the two are asked separately, so one can be true while the other is not."
        />
        <div className="vg-cols is-even">
          <div>
            <div className="vg-pick-title" style={{ padding: "0 0 8px 0" }}>
              what the platform recorded
            </div>
            <KV k="key">{blob.key}</KV>
            <KV k="datastore">{blob.datastore_name}</KV>
            <KV k="declared">{blob.content_type ?? "unstated"}</KV>
            <KV k="recorded">{stamp(blob.creation_date)}</KV>
          </div>
          <div>
            <div className="vg-pick-title" style={{ padding: "0 0 8px 0" }}>
              what the store holds
            </div>
            <KV k="stored type">{stored?.content_type ?? "nothing stored"}</KV>
            <KV k="size">{stored ? `${stored.size} B` : "—"}</KV>
            <KV k="etag">{stored?.etag ?? "—"}</KV>
            <KV k="modified">{stamp(stored?.last_modified)}</KV>
          </div>
        </div>
        <div className="vg-note">
          The declared type is recorded as the project told it; the platform never sees the bytes to
          check. Where the two disagree, the store's is the one the browser acts on.
        </div>
      </section>
    </div>
  );
}
