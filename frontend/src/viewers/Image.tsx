import type { Viewer } from "./viewer";
import { Frame } from "./Frame";

/**
 * A picture. The only format the console has always been able to show, and
 * still the only one that needs no controls: it is all there at once.
 */
export const image: Viewer = {
  kind: "image",
  types: ["image/"],
  extensions: ["png", "jpg", "jpeg", "gif", "webp", "avif", "svg", "bmp", "ico", "tif", "tiff"],

  render: ({ url, stored, blob }) => (
    <Frame kind="image" stored={stored}>
      <img src={url} alt={blob.description ?? blob.key} />
    </Frame>
  ),

  thumb: ({ url, blob, onBroken }) => (
    <img src={url} alt={blob.description ?? blob.key} onError={onBroken} />
  ),
};
