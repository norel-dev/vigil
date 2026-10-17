import { claimsName, claimsType, type Viewer } from "./viewer";
import { image } from "./Image";
import { video } from "./Video";
import { audio } from "./Audio";
import { pdf } from "./Pdf";
import { html, markdown, text } from "./Source";
import { unknown } from "./Unknown";

/** All viewers. Order matters: exact types before families (`text/html` before `text/`). */
const viewers: readonly Viewer[] = [image, video, audio, pdf, html, markdown, text];

/** Pick a viewer by content type, then by file extension, else the fallback. */
export function resolve(contentType: string | null | undefined, key: string): Viewer {
  return (
    viewers.find((viewer) => claimsType(viewer, contentType)) ??
    viewers.find((viewer) => claimsName(viewer, key)) ??
    unknown
  );
}
