import { claimsName, claimsType, type Viewer } from "./viewer";
import { image } from "./Image";
import { video } from "./Video";
import { audio } from "./Audio";
import { pdf } from "./Pdf";
import { html, markdown, text } from "./Source";
import { unknown } from "./Unknown";

/**
 * Which viewer draws which bytes.
 *
 * This list is the whole of the console's knowledge about formats, and adding
 * one is adding a file and a line here — no pane that already draws five
 * formats correctly has to be opened to make it draw a sixth.
 *
 * Order is load-bearing in one direction only: a viewer claiming an exact type
 * must come before one claiming the family it belongs to, or `text/` would
 * swallow `text/html` on its way past. Specific first, general last.
 */
const viewers: readonly Viewer[] = [image, video, audio, pdf, html, markdown, text];

/**
 * Pick a viewer for these bytes.
 *
 * The stored type is asked first and the key second, in that order and never
 * mixed, because they are two different kinds of claim. The store's type is
 * what the browser will actually act on when it fetches the url; the name is a
 * guess, and only worth making when the type said nothing that matched — which
 * is the common case, since `application/octet-stream` is what most uploads
 * are labelled by whatever put them there.
 *
 * Always returns a viewer. A blob the console cannot draw is still a blob it
 * has something true to say about.
 */
export function resolve(contentType: string | null | undefined, key: string): Viewer {
  return (
    viewers.find((viewer) => claimsType(viewer, contentType)) ??
    viewers.find((viewer) => claimsName(viewer, key)) ??
    unknown
  );
}
