import { useRef } from "react";
import type { Viewer, ViewerProps } from "./viewer";
import { Undecodable } from "./Frame";
import { Transport, useTransport } from "./Transport";
import { bytes } from "../lib/format";

/** Audio player. */
function Deck({ url, stored, blob }: ViewerProps) {
  const ref = useRef<HTMLAudioElement | null>(null);
  const playback = useTransport(ref);

  return (
    <div className="dp-media">
      <div className="dp-deck">
        <audio ref={ref} src={url} preload="metadata" />
        <div className="dp-deck-name">
          <span className="dp-deck-key">{blob.key.split("/").pop()}</span>
          <span className="dp-deck-meta">
            {stored.content_type ?? "unknown type"} · {bytes(stored.size)}
          </span>
        </div>
        {playback.failed ? (
          <Undecodable stored={stored} />
        ) : (
          <Transport playback={playback} label={blob.key} />
        )}
      </div>
    </div>
  );
}

export const audio: Viewer = {
  kind: "audio",
  types: ["audio/"],
  extensions: ["mp3", "wav", "ogg", "oga", "flac", "m4a", "aac", "opus", "weba"],
  render: Deck,
};
