import type { ComponentType } from "react";
import type { Blob, StoredBlob } from "../lib/api";

/**
 * What it takes to show a blob.
 *
 * The console used to decide this with a chain of conditionals in the pane
 * that drew the result, which meant every new format was a change to working
 * code that already drew five other formats correctly. A viewer is that
 * decision turned inside out: each format states for itself what bytes it can
 * show, and the pane asks rather than tests.
 *
 * Nothing here imports a viewer. Viewers import this, the registry imports
 * both, and the panes import only the registry — so a format can be added
 * without opening any file that already works.
 */

export interface ViewerProps {
  /** Signed, proxied, and good for one read of one key for a few minutes. */
  url: string;
  /** Never null: a viewer is only ever asked to show bytes that exist. */
  stored: StoredBlob;
  blob: Blob;
}

/**
 * What a thumbnail needs beyond what the full view needs: a way to say it
 * could not draw. The contact sheet frames a refusal differently from an
 * empty blob, and only the element that failed knows which happened.
 */
export interface ThumbProps extends ViewerProps {
  onBroken: () => void;
}

export interface Viewer {
  /**
   * One lowercase word for what this is. It is printed in captions and on the
   * contact sheet, so it is the viewer's name for itself rather than a label
   * held somewhere else and kept in step by hand.
   */
  readonly kind: string;

  /**
   * Content types this viewer draws. An entry ending in `/` matches any
   * subtype, so `image/` claims `image/avif` without being told about it.
   */
  readonly types: readonly string[];

  /**
   * Key extensions to fall back on. The recorded type is whatever the project
   * said it was and is often nothing useful, so the name is the second source.
   */
  readonly extensions: readonly string[];

  /** The full view, shown in the blob pane. */
  readonly render: ComponentType<ViewerProps>;

  /**
   * A thumbnail for the contact sheet, where one can be drawn from the bytes
   * themselves. Formats that would only produce a grey rectangle leave this
   * unset and get their name in the frame instead, which says more.
   */
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
  // A dot in a directory segment is not an extension: `v1.2/notes` has none.
  if (dot === -1 || name.indexOf("/", dot) !== -1) return false;
  return viewer.extensions.includes(name.slice(dot + 1));
}
