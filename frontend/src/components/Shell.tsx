import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Project } from "../lib/api";
import { clock } from "../lib/format";

/**
 * The shell: a fixed frame with exactly one scrolling region.
 *
 * A buffer here is an open object — a table, a blob, or a workspace's overview
 * — exactly as a buffer in an editor is an open file. Two buffers may belong to
 * two different workspaces at once, so which workspace a buffer is in is a
 * property of the buffer rather than of the window, and it is stated where the
 * rest of the window's state is stated: the statusline.
 *
 * A buffer is also a place the reader put themselves, in the way a browser tab
 * is. Picking an object out of the rail re-points the buffer in hand; it never
 * mints one and never sends the reader off to some other buffer that happens to
 * hold the same thing. A second buffer is only ever born by being asked for —
 * `+`, `:new tab`, a modifier-click — which is why two of them may show the
 * same object at once.
 */

export type Mode = "normal" | "command" | "busy";

export interface Tab {
  id: string;
  label: string;
  title: string;
  /** Shown as the buffer's kind sigil, in the way vim shows a filetype. */
  kind: "workspace" | "members" | "table" | "blob";
  loading: boolean;
}

const SIGIL: Record<Tab["kind"], string> = {
  workspace: "◫",
  members: "◌",
  table: "▦",
  blob: "◈",
};

export function Tabline(props: {
  tabs: Tab[];
  activeId: string | null;
  email: string;
  onPick: (id: string) => void;
  onClose: (id: string) => void;
  onNew: () => void;
  onPalette: () => void;
  onSignOut: () => void;
}) {
  return (
    <header className="vg-tabline">
      <button type="button" className="vg-brand" onClick={props.onNew} title="duplicate this buffer">
        <img src="/mark.svg" alt="" width="14" height="14" />
        <span>dataplatform</span>
        <span className="vg-brand-version">v0.1</span>
      </button>

      <div className="vg-tabs" role="tablist" aria-label="open buffers">
        {props.tabs.map((tab, index) => {
          const active = tab.id === props.activeId;
          return (
            <button
              key={tab.id}
              className={`vg-tab${active ? " is-active" : ""}`}
              role="tab"
              aria-selected={active}
              onClick={() => props.onPick(tab.id)}
              onAuxClick={(event) => {
                // Middle click closes, the way it closes a tab everywhere else.
                if (event.button === 1) {
                  event.preventDefault();
                  props.onClose(tab.id);
                }
              }}
              title={tab.title}
            >
              {index < 9 && <span className="vg-tab-num">{index + 1}</span>}
              <span className="dp-tab-sigil" aria-hidden="true">
                {SIGIL[tab.kind]}
              </span>
              <span className="dp-tab-name">{tab.label}</span>
              {tab.loading && <span className="vg-tab-mod">●</span>}
              {active && props.tabs.length > 1 && (
                <span
                  className="vg-tab-x"
                  role="button"
                  aria-label={`close ${tab.label}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    props.onClose(tab.id);
                  }}
                >
                  ×
                </span>
              )}
            </button>
          );
        })}
        <button
          className="vg-tab vg-tab-new"
          onClick={props.onNew}
          title="duplicate this buffer, then take one of the two somewhere else" aria-label="duplicate this buffer">
          +
        </button>
      </div>

      <div className="vg-tabline-right">
        <button className="vg-tool" onClick={props.onPalette}>
          <span className="vg-key">⌘K</span>
          <span>:cmd</span>
        </button>
        <button className="vg-tool" onClick={props.onSignOut} title="forget this key">
          <span className="dp-tool-who">{props.email}</span>
        </button>
      </div>
    </header>
  );
}

export function Cmdline(props: {
  open: boolean;
  value: string;
  message: { text: string; error: boolean } | null;
  onChange: (value: string) => void;
  onRun: () => void;
  onDismiss: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (props.open) ref.current?.focus();
  }, [props.open]);

  return (
    <div className="vg-cmdline">
      <span className="vg-cmdline-prompt">:</span>
      {props.open ? (
        <input
          ref={ref}
          className="vg-cmdline-field"
          value={props.value}
          spellCheck={false}
          autoComplete="off"
          aria-label="command"
          placeholder="type a command…"
          onChange={(event) => props.onChange(event.target.value)}
          onBlur={props.onDismiss}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              props.onRun();
            }
          }}
        />
      ) : (
        <>
          <span>
            <span className="vg-cmdline-cursor">█</span>
          </span>
          {props.message && (
            <span className={`vg-cmdline-msg${props.message.error ? " is-error" : ""}`}>
              {props.message.text}
            </span>
          )}
          <span className="vg-cmdline-hint">
            <span>
              <kbd>:</kbd>command
            </span>
            <span>
              <kbd>f</kbd>find
            </span>
            <span>
              <kbd>j k</kbd>rail
            </span>
            <span>
              <kbd>↵</kbd>open
            </span>
            <span>
              <kbd>1-9</kbd>buffer
            </span>
            <span>
              <kbd>⌘K</kbd>palette
            </span>
          </span>
        </>
      )}
    </div>
  );
}

/**
 * The workspace segment.
 *
 * Which workspace you are in is window state, not document state, so it lives
 * in the statusline rather than in a tab. It is a control: the popover it opens
 * is the whole of how a reader moves between workspaces with the mouse.
 */
function WorkspaceSegment(props: {
  projects: Project[];
  activeId: string | null;
  onPick: (id: string) => void;
  onNew: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = props.projects.find((item) => item.id === props.activeId);

  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as globalThis.Node)) setOpen(false);
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("mousedown", away);
    window.addEventListener("keydown", key, true);
    return () => {
      window.removeEventListener("mousedown", away);
      window.removeEventListener("keydown", key, true);
    };
  }, [open]);

  return (
    <div className="dp-seg-host" ref={ref}>
      <button
        type="button"
        className="vg-seg is-action"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
        title="switch workspace"
      >
        <span className="dp-seg-ws">{active ? active.name : "no workspace"}</span>
        <span className="vg-seg-twist" aria-hidden="true">
          ▲
        </span>
      </button>

      {open && (
        <div className="vg-popover dp-wspicker" role="menu" aria-label="workspaces">
          <div className="vg-pick-title">workspaces you may reach</div>
          <div className="dp-wspicker-list">
            {props.projects.length === 0 ? (
              <div className="vg-tree-empty">
                you are not a member of any workspace, and none has been created yet.
              </div>
            ) : (
              props.projects.map((project) => (
                <button
                  key={project.id}
                  className={`vg-pick${project.id === props.activeId ? " is-on" : ""}`}
                  role="menuitem"
                  onClick={() => {
                    setOpen(false);
                    props.onPick(project.id);
                  }}
                >
                  <span className="dp-pick-row">
                    <span className="dp-pick-name">{project.name}</span>
                    <span className="vg-pick-count dp-pick-tail">
                      {project.id === props.activeId ? "open" : ""}
                    </span>
                  </span>
                </button>
              ))
            )}
          </div>
          <div className="dp-wspicker-foot">
            <button
              className="vg-btn is-ghost"
              onClick={() => {
                setOpen(false);
                props.onNew();
              }}
            >
              + workspace
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function Statusline(props: {
  mode: Mode;
  projects: Project[];
  workspaceId: string | null;
  onPickWorkspace: (id: string) => void;
  onNewWorkspace: () => void;
  context: string;
  role: string;
  last: { verb: string; latency: string } | null;
  rows: number | null;
  reachable: boolean;
}) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const badge =
    props.mode === "busy" ? "is-busy" : props.mode === "command" ? "is-input" : "is-default";

  return (
    <footer className="vg-statusline">
      <span className={`vg-seg vg-mode ${badge}`}>{props.mode}</span>
      <WorkspaceSegment
        projects={props.projects}
        activeId={props.workspaceId}
        onPick={props.onPickWorkspace}
        onNew={props.onNewWorkspace}
      />
      <span className="vg-seg vg-seg-primary dp-seg-context">
        <span>{props.context}</span>
      </span>
      <span className="vg-seg vg-seg-muted dp-seg-optional">{props.role}</span>
      <span className="vg-seg vg-seg-spacer" />
      {props.last && (
        <span className="vg-seg vg-seg-muted dp-seg-optional">
          {props.last.verb} · {props.last.latency}
        </span>
      )}
      {props.rows !== null && (
        <span className="vg-seg vg-seg-muted">
          {props.rows} {props.rows === 1 ? "row" : "rows"}
        </span>
      )}
      <span className="vg-seg dp-seg-optional">{clock(now)}</span>
      {props.reachable ? (
        <span className="vg-seg vg-seg-ok">
          <span className="vg-pulse" />
          connected
        </span>
      ) : (
        <span className="vg-seg vg-seg-alert">api unreachable</span>
      )}
    </footer>
  );
}

export function Canvas({ children }: { children: ReactNode }) {
  return (
    <main className="vg-canvas">
      <div className="vg-canvas-inner dp-canvas-inner">{children}</div>
    </main>
  );
}
