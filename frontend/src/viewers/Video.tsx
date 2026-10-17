import { useEffect, useRef, useState } from "react";
import type { Viewer, ViewerProps } from "./viewer";
import { Frame, Undecodable } from "./Frame";
import { Transport, useTransport } from "./Transport";

/** Video player. Click the picture to play/pause. */
function Screen({ url, stored, blob }: ViewerProps) {
  const ref = useRef<HTMLVideoElement | null>(null);
  const stage = useRef<HTMLDivElement | null>(null);
  const playback = useTransport(ref);
  const [full, setFull] = useState(false);

  // Track fullscreen changes made outside the button (e.g. Escape).
  useEffect(() => {
    const sync = () => setFull(document.fullscreenElement === stage.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  const fullscreen = () => {
    const box = stage.current;
    if (!box) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void box.requestFullscreen().catch(() => undefined);
  };

  if (playback.failed) {
    return (
      <Frame kind="video" stored={stored}>
        <Undecodable stored={stored} />
      </Frame>
    );
  }

  return (
    <Frame kind="video" stored={stored} bare>
      <div className="dp-player" ref={stage}>
        <video
          ref={ref}
          src={url}
          preload="metadata"
          playsInline
          onClick={playback.toggle}
          aria-label={blob.description ?? blob.key}
        >
          <track kind="captions" />
        </video>
        <Transport playback={playback} label={blob.key}>
          <button
            className="dp-transport-key is-quiet"
            onClick={fullscreen}
            aria-label={full ? "leave fullscreen" : "fullscreen"}
          >
            <span aria-hidden="true">{full ? "⤡" : "⤢"}</span>
          </button>
        </Transport>
      </div>
    </Frame>
  );
}

export const video: Viewer = {
  kind: "video",
  types: ["video/"],
  extensions: ["mp4", "mov", "m4v", "webm", "ogv", "avi", "mkv"],
  render: Screen,
  // First frame only, muted.
  thumb: ({ url, onBroken }) => <video src={url} muted preload="metadata" onError={onBroken} />,
};
