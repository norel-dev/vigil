import { useRef } from "react";
import type { Viewer, ViewerProps } from "./viewer";
import { Undecodable } from "./Frame";
import { Transport, useTransport } from "./Transport";
import { bytes } from "../lib/format";

/**
 * A recording.
 *
 * Audio is the one format that is entirely transport: there is nothing to look
 * at, so the controls are not an overlay on the thing but the whole of it. It
 * gets its own frame rather than the shared stage for that reason — a picture
 * frame around a strip of controls sits a recording inside an empty gallery.
 */
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
            {stored.content_type ?? "type unstated"} · {bytes(stored.size)}
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
