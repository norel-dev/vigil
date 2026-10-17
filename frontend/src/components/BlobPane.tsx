import { useEffect, useState } from "react";
import { ApiError, api, uploadTo, type BlobView, type Uuid } from "../lib/api";
import { downloadUrl, forget } from "../lib/media";
import { Head, KV, Loading, Problem } from "./bits";
import { bytes, stamp } from "../lib/format";
import { resolve } from "../viewers/registry";
import type { Rights } from "../lib/authz";

/** A blob: preview and metadata. A blob may exist before its bytes are uploaded. */
export function BlobPane(props: {
  project: Uuid;
  view: BlobView;
  rights: Rights;
  onDeleted: () => void;
  onReplaced: () => void;
  onAskDelete: (confirm: { title: string; body: string; verb: string; run: () => Promise<void> }) => void;
}) {
  const { blob, stored } = props.view;
  // Prefer the stored content type; it's what the browser will use.
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
          {blob.description && <div className="vg-subtitle">{blob.description}</div>}
        </div>
        <div className="vg-head-side">
          <div className="vg-row-flex">
            <span className={`vg-chip${stored ? " is-high" : ""}`}>
              <span className="vg-chip-dot" />
              {stored ? bytes(stored.size) : "not uploaded"}
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
                download
              </a>
            )}
            <label
              className="vg-btn"
              style={{ cursor: props.rights.can("blob.upload") ? "pointer" : "not-allowed" }}
            >
              {replacing ? "uploading…" : stored ? "replace" : "upload"}
              <input
                type="file"
                hidden
                disabled={!props.rights.can("blob.upload") || replacing}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void replace(file);
                  event.target.value = "";
                }}
              />
            </label>
            <button
              className="vg-btn is-danger"
              disabled={!props.rights.can("blob.delete")}
              onClick={() =>
                props.onAskDelete({
                  title: `Delete ${blob.key}`,
                  body: "This permanently deletes the file.",
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
        <Head title="Contents" />
        {problem && <Problem>{problem}</Problem>}
        {stored === null ? (
          <div className="vg-withheld">no file uploaded yet</div>
        ) : url === null && !problem ? (
          <Loading />
        ) : url === null ? null : (
          <Contents url={url} stored={stored} blob={blob} />
        )}
      </section>

      <section>
        <Head title="Details" />
        <div className="vg-cols is-even">
          <div>
            <KV k="key">{blob.key}</KV>
            <KV k="datastore">{blob.datastore_name}</KV>
            <KV k="declared type">{blob.content_type ?? "—"}</KV>
            <KV k="created">{stamp(blob.creation_date)}</KV>
          </div>
          <div>
            <KV k="stored type">{stored?.content_type ?? "—"}</KV>
            <KV k="size">{stored ? `${stored.size} B` : "—"}</KV>
            <KV k="etag">{stored?.etag ?? "—"}</KV>
            <KV k="modified">{stamp(stored?.last_modified)}</KV>
          </div>
        </div>
      </section>
    </div>
  );
}
