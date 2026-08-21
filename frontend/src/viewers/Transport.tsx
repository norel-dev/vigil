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
 * The transport: play, seek, and the running time.
 *
 * Audio and video are the same problem wearing different clothes — one has a
 * picture and one does not, but both are a position in a duration — so both
 * drive this. It is built rather than borrowed because `controls` draws the
 * browser's chrome, which is a different shape, weight and colour in every
 * browser and belongs to none of them here.
 *
 * The seek bar is a range input and not a styled div. A div would need its own
 * arrow keys, its own Home and End, its own focus ring and its own
 * `role="slider"` with the value mirrored into ARIA by hand; the input has all
 * of that already and is the same control a screen reader has met before.
 */

export interface Playback {
  ready: boolean;
  playing: boolean;
  current: number;
  duration: number;
  /** How far the browser has fetched ahead of the playhead, in seconds. */
  buffered: number;
  muted: boolean;
  /** Set when the browser will not decode these bytes at all. */
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
      // A live or still-unparsed stream reports its length as Infinity or NaN.
      // Both mean the same thing to a reader — nobody knows yet — and both are
      // carried through as-is so the bar can disable itself rather than lie.
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
    // Keyed on the ref alone: effects run after mount, so the element is always
    // there by now, and it outlives any change of source.
  }, [ref]);

  const toggle = useCallback(() => {
    const element = ref.current;
    if (!element) return;
    // `play()` rejects when autoplay policy or a decode failure blocks it. That
    // is a refusal rather than a crash, so it is caught and shown as one.
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
  /** Named in the seek bar's label, so a page of them is not a page of "seek". */
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

