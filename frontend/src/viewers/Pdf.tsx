import type { Viewer, ViewerProps } from "./viewer";
import { Frame } from "./Frame";

/**
 * A document, drawn by the browser's own viewer.
 *
 * Every current browser ships a pdf reader with pages, search, zoom and print
 * already in it, reached by pointing a frame at the file. Shipping a second
 * one — pdf.js and its worker are a larger download than the whole console —
 * would buy a consistent toolbar and nothing a reader here needs.
 *
 * The frame is not sandboxed, and that is deliberate rather than overlooked.
 * A browser decides what to do with a response by its `Content-Type` header,
 * not by the name it was fetched under, and the store sends the type the
 * registry routed on — so bytes that could execute as markup are bytes the
 * registry sent to the source viewer instead, and never arrive here. Sandbox
 * attributes, meanwhile, stop several browsers' pdf readers from opening at
 * all, which would trade a risk this path does not carry for a blank panel.
 */
function Document({ url, stored, blob }: ViewerProps) {
  return (
    <Frame kind="pdf" stored={stored} bare>
      <iframe
        className="dp-page"
        src={url}
        title={blob.description ?? blob.key}
        // The reader is the browser's, so its own referrer rules apply; the
        // signed url is the whole authorization and should not travel onward.
        referrerPolicy="no-referrer"
      />
    </Frame>
  );
}

export const pdf: Viewer = {
  kind: "pdf",
  types: ["application/pdf"],
  extensions: ["pdf"],
  render: Document,
};
