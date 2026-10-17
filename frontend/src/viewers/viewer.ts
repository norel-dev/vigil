import type { ComponentType } from "react";
import type { Blob, StoredBlob } from "../lib/api";

/** A per-format blob viewer. Add a format with a new file and a registry entry. */

export interface ViewerProps {
  /** Short-lived signed download url. */
  url: string;
  stored: StoredBlob;
  blob: Blob;
}

export interface ThumbProps extends ViewerProps {
  onBroken: () => void;
}

export interface Viewer {
  /** Short label shown in captions, e.g. "image". */
  readonly kind: string;

  /** Content types handled. A trailing `/` matches any subtype. */
  readonly types: readonly string[];

  /** File extensions to fall back on when the type doesn't match. */
  readonly extensions: readonly string[];

  readonly render: ComponentType<ViewerProps>;

  /** Optional thumbnail; without one the grid shows `kind`. */
  readonly thumb?: ComponentType<ThumbProps>;
}

export function claimsType(viewer: Viewer, contentType: string | null | undefined): boolean {
  const type = (contentType ?? "").toLowerCase().split(";")[0].trim();
  if (!type) return false;
  return viewer.types.some((claim) => (claim.endsWith("/") ? type.startsWith(claim) : type === claim));
}

export function claimsName(viewer: Viewer, key: string): boolean {
  const name = key.toLowerCase();
  const dot = name.lastIndexOf(".");
  // Ignore dots in directory segments (`v1.2/notes`).
  if (dot === -1 || name.indexOf("/", dot) !== -1) return false;
  return viewer.extensions.includes(name.slice(dot + 1));
}
