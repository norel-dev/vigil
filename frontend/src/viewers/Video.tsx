import { useEffect, useRef, useState } from "react";
import type { Viewer, ViewerProps } from "./viewer";
import { Frame, Undecodable } from "./Frame";
import { Transport, useTransport } from "./Transport";

/**
 * Moving pictures.
 *
 * The picture itself is the largest control on the panel: clicking it toggles
 * play, the way it does everywhere else a video has ever been shown. The
 * transport underneath is the same one the audio viewer uses, because a video
 * is an audio file that happens to have something to look at.
 *
 * Fullscreen is kept — it is the one thing the native controls do that cannot
 * be rebuilt, since only a user gesture on an element may request it.
 */
function Screen({ url, stored, blob }: ViewerProps) {
  const ref = useRef<HTMLVideoElement | null>(null);
  const stage = useRef<HTMLDivElement | null>(null);
  const playback = useTransport(ref);
  const [full, setFull] = useState(false);

  // Escape and the browser's own chrome can leave fullscreen without going
  // through the button, so the label follows the document rather than the click.
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
  // Muted, unplayed, and showing its first frame: the sheet is a page of
  // stills, and a grid of things all playing at once is a page nobody reads.
  thumb: ({ url, onBroken }) => <video src={url} muted preload="metadata" onError={onBroken} />,
};
