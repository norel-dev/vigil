import {
  useCallback,
  useEffect,
  useState,
  type CSSProperties,
  type ReactNode,
  type RefObject,
} from "react";
import { timecode } from "../lib/format";

/**
 * Custom play/seek controls shared by audio and video, so they look the same
 * in every browser. The seek bar is a native range input for accessibility.
 */

export interface Playback {
  ready: boolean;
  playing: boolean;
  current: number;
  duration: number;
  /** Seconds buffered. */
  buffered: number;
  muted: boolean;
  /** The browser can't decode the media. */
  failed: boolean;
}

const IDLE: Playback = {
  ready: false,
  playing: false,
  current: 0,
  duration: NaN,
  buffered: 0,
  muted: false,
  failed: false,
};

export function useTransport(ref: RefObject<HTMLMediaElement | null>) {
  const [state, setState] = useState<Playback>(IDLE);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const read = () => {
      // Duration may be NaN or Infinity until known; the seek bar disables itself.
      const duration = element.duration;
      let buffered = 0;
      for (let i = 0; i < element.buffered.length; i += 1) {
        if (
          element.buffered.start(i) <= element.currentTime &&
          element.buffered.end(i) >= element.currentTime
        ) {
          buffered = element.buffered.end(i);
          break;
        }
      }
      setState({
        ready: Number.isFinite(duration) && duration > 0,
        playing: !element.paused && !element.ended,
        current: element.currentTime,
        duration,
        buffered,
        muted: element.muted,
        failed: false,
      });
    };

    const fail = () => setState((prior) => ({ ...prior, failed: true, playing: false }));

    const events = [
      "loadedmetadata",
      "durationchange",
      "timeupdate",
      "progress",
      "play",
      "pause",
      "ended",
      "seeked",
      "volumechange",
    ];
    for (const name of events) element.addEventListener(name, read);
    element.addEventListener("error", fail);
    read();

    return () => {
      for (const name of events) element.removeEventListener(name, read);
      element.removeEventListener("error", fail);
    };
  }, [ref]);

  const toggle = useCallback(() => {
    const element = ref.current;
    if (!element) return;
    // `play()` rejects on autoplay policy or decode failure.
    if (element.paused) void element.play().catch(() => setState((p) => ({ ...p, failed: true })));
    else element.pause();
  }, [ref]);

  const seek = useCallback(
    (to: number) => {
      const element = ref.current;
      if (element) element.currentTime = to;
    },
    [ref],
  );

  const mute = useCallback(() => {
    const element = ref.current;
    if (element) element.muted = !element.muted;
  }, [ref]);

  return { ...state, toggle, seek, mute };
}

export function Transport(props: {
  playback: ReturnType<typeof useTransport>;
  /** Used in the seek bar's aria-label. */
  label: string;
  children?: ReactNode;
}) {
  const { playback: p } = props;
  const span = p.ready ? p.duration : 0;
  const done = span > 0 ? p.current / span : 0;
  const ahead = span > 0 ? Math.min(p.buffered / span, 1) : 0;

  return (
    <div className="dp-transport">
      <button
        className="dp-transport-key"
        onClick={p.toggle}
        disabled={p.failed}
        aria-label={p.playing ? "pause" : "play"}
      >
        <span aria-hidden="true">{p.playing ? "❚❚" : "▶"}</span>
      </button>

      <span className="dp-transport-time">{timecode(p.current)}</span>

      <span
        className="dp-transport-bar"
        style={
          {
            "--done": `${done * 100}%`,
            "--ahead": `${ahead * 100}%`,
          } as CSSProperties
        }
      >
        <input
          type="range"
          min={0}
          max={p.ready ? p.duration : 1}
          step="any"
          value={p.current}
          disabled={!p.ready}
          aria-label={`seek within ${props.label}`}
          aria-valuetext={p.ready ? `${timecode(p.current)} of ${timecode(p.duration)}` : "length unknown"}
          onChange={(event) => p.seek(Number(event.target.value))}
        />
      </span>

      <span className="dp-transport-time is-total">{timecode(p.duration)}</span>

      <button
        className="dp-transport-key is-quiet"
        onClick={p.mute}
        disabled={p.failed}
        aria-label={p.muted ? "unmute" : "mute"}
        aria-pressed={p.muted}
      >
        <span aria-hidden="true">{p.muted ? "🔇" : "🔊"}</span>
      </button>

      {props.children}
    </div>
  );
}

