import type { Viewer } from "./viewer";
import { Frame } from "./Frame";

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
