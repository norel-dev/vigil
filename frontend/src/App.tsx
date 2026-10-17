import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  setKey,
  type BlobView,
  type CatalogueEntry,
  type CurrentUser,
  type Membership,
  type Project,
  type Table,
  type Uuid,
} from "./lib/api";
import { rightsIn } from "./lib/authz";
import { Gate } from "./components/Gate";
import { Canvas, Cmdline, Statusline, Tabline, type Mode, type Tab } from "./components/Shell";
import { Palette, type PaletteItem } from "./components/Palette";
import { Rail, railRows, type RailRow } from "./components/Rail";
import { WorkspacePane } from "./components/WorkspacePane";
import { MembersPane } from "./components/MembersPane";
import { TablePane, type TableActions } from "./components/TablePane";
import { BlobPane } from "./components/BlobPane";
import { Empty, Loading, Problem } from "./components/bits";
import {
  ConfirmDialog,
  GrantDialog,
  NewTableDialog,
  NewWorkspaceDialog,
  UploadDialog,
} from "./components/dialogs";
import { latency as fmtLatency } from "./lib/format";
import { ancestors, branchPaths, build, flatten, type Node } from "./lib/tree";

const KEY_STORE = "dataplatform.key";

type Selection =
  | { kind: "workspace" }
  | { kind: "members" }
  | { kind: "table"; name: string }
  | { kind: "blob"; key: string };

/** An open tab. */
interface Buffer {
  id: string;
  workspaceId: Uuid;
  selection: Selection;
}

/** Cached data for one workspace. */
interface WorkspaceData {
  tables: Table[] | null;
  blobViews: BlobView[] | null;
  members: Membership[] | null;
  loading: boolean;
}

const EMPTY: WorkspaceData = { tables: null, blobViews: null, members: null, loading: true };

interface Confirm {
  title: string;
  body: string;
  verb: string;
  run: () => Promise<void>;
}

type Overlay =
  | null
  | { kind: "palette" }
  | { kind: "new-workspace" }
  | { kind: "new-table" }
  | { kind: "upload" }
  | { kind: "grant" }
  | ({ kind: "confirm" } & Confirm);

let bufferSeed = 0;
const nextBufferId = () => `buf-${(bufferSeed += 1)}`;

/** Whether two selections name the same object. */
const sameSelection = (a: Selection, b: Selection) =>
  a.kind === b.kind &&
  (a.kind !== "table" || a.name === (b as { name: string }).name) &&
  (a.kind !== "blob" || a.key === (b as { key: string }).key);

export function App() {
  /* -- Identity ------------------------------------------------------------ */
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [gateProblem, setGateProblem] = useState<string | null>(null);
  const [gatePending, setGatePending] = useState(true);

  /* -- The platform's contents --------------------------------------------- */
  const [projects, setProjects] = useState<Project[]>([]);
  const [catalogue, setCatalogue] = useState<CatalogueEntry[]>([]);
  const [data, setData] = useState<Record<Uuid, WorkspaceData>>({});
  const [problem, setProblem] = useState<string | null>(null);

  /* -- Buffers ------------------------------------------------------------- */
  const [buffers, setBuffers] = useState<Buffer[]>([]);
  const [activeBufferId, setActiveBufferId] = useState<string | null>(null);

  /* -- Chrome -------------------------------------------------------------- */
  const [overlay, setOverlay] = useState<Overlay>(null);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [cmdValue, setCmdValue] = useState("");
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [railCursor, setRailCursor] = useState(0);
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [compact, setCompact] = useState(false);
  const [last, setLast] = useState<{ verb: string; latency: string } | null>(null);
  const [rows, setRows] = useState<number | null>(null);
  const [reachable, setReachable] = useState(true);
  const tableActions = useRef<TableActions | null>(null);
  const findRef = useRef<HTMLInputElement | null>(null);

  const say = useCallback((text: string, error = false) => {
    setMessage({ text, error });
    window.setTimeout(() => setMessage((current) => (current?.text === text ? null : current)), 6000);
  }, []);

  const report = useCallback((error: unknown): string => {
    const text = error instanceof ApiError ? error.message : String(error);
    setReachable(!(error instanceof ApiError && error.status === 0));
    return text;
  }, []);

  /* -- Signing in ---------------------------------------------------------- */

  const signIn = useCallback(
    async (value: string) => {
      setGatePending(true);
      setGateProblem(null);
      setKey(value);
      try {
        const user = await api.me();
        window.localStorage.setItem(KEY_STORE, value);
        setMe(user);
        setReachable(true);
      } catch (error) {
        setKey("");
        setGateProblem(
          error instanceof ApiError && error.status === 401
            ? "invalid api key"
            : report(error),
        );
      } finally {
        setGatePending(false);
      }
    },
    [report],
  );

  useEffect(() => {
    const held = window.localStorage.getItem(KEY_STORE);
    if (held) void signIn(held);
    else setGatePending(false);
  }, [signIn]);

  const signOut = useCallback(() => {
    window.localStorage.removeItem(KEY_STORE);
    setKey("");
    setMe(null);
    setProjects([]);
    setData({});
    setBuffers([]);
    setActiveBufferId(null);
    setGateProblem(null);
  }, []);

  /* -- Loading ------------------------------------------------------------- */

  const loadWorkspace = useCallback(
    async (id: Uuid) => {
      setData((all) => ({ ...all, [id]: { ...(all[id] ?? EMPTY), loading: true } }));
      let tables: Table[] = [];
      let views: BlobView[] = [];
      try {
        const [tableList, blobList] = await Promise.all([api.listTables(id), api.listBlobs(id)]);
        tables = tableList;
        // Fetch stored-object info too, to know which blobs have bytes.
        views = await Promise.all(
          blobList.map((blob) =>
            api.readBlob(id, blob.key).catch(() => ({ blob, stored: null }) as BlobView),
          ),
        );
        setProblem(null);
        setReachable(true);
      } catch (error) {
        setProblem(report(error));
      }
      // Listing members may be forbidden; don't fail the whole load.
      let members: Membership[] = [];
      try {
        members = await api.listMembers(id);
      } catch {
        members = [];
      }
      setData((all) => ({ ...all, [id]: { tables, blobViews: views, members, loading: false } }));
    },
    [report],
  );

  const loadPlatform = useCallback(async () => {
    try {
      const [list, entries] = await Promise.all([api.listProjects(), api.catalogue()]);
      setProjects(list);
      setCatalogue(entries);
      setReachable(true);
      setProblem(null);
      return list;
    } catch (error) {
      setProblem(report(error));
      return [] as Project[];
    }
  }, [report]);

  // Open the first workspace on sign-in.
  const opened = useRef(false);
  useEffect(() => {
    if (!me) return;
    void loadPlatform().then((list) => {
      if (opened.current || list.length === 0) return;
      opened.current = true;
      const first: Buffer = {
        id: nextBufferId(),
        workspaceId: list[0].id,
        selection: { kind: "workspace" },
      };
      setBuffers([first]);
      setActiveBufferId(first.id);
    });
  }, [me, loadPlatform]);

  /* -- The active buffer --------------------------------------------------- */

  const buffer = buffers.find((item) => item.id === activeBufferId) ?? null;
  const workspaceId = buffer?.workspaceId ?? null;
  const project = projects.find((item) => item.id === workspaceId) ?? null;
  const here = (workspaceId ? data[workspaceId] : undefined) ?? EMPTY;

  // Load workspaces lazily, when a tab needs one.
  useEffect(() => {
    for (const open of buffers) {
      if (!data[open.workspaceId]) void loadWorkspace(open.workspaceId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buffers, loadWorkspace]);

  const rights = useMemo(() => rightsIn(me, workspaceId), [me, workspaceId]);
  const role = rights.role;

  /* -- Buffers: navigating, opening, closing -------------------------------- */

  /** Show something in the active tab. */
  const goTo = useCallback(
    (ws: Uuid, selection: Selection) => {
      if (!activeBufferId || buffers.length === 0) {
        const first: Buffer = { id: nextBufferId(), workspaceId: ws, selection };
        setBuffers([first]);
        setActiveBufferId(first.id);
        return;
      }
      setBuffers(
        buffers.map((item) =>
          item.id === activeBufferId ? { ...item, workspaceId: ws, selection } : item,
        ),
      );
    },
    [buffers, activeBufferId],
  );

  /**
   * Open something in a new tab after the active one.
   * The id is created outside the state updater so the updater stays pure.
   */
  const openInNewBuffer = useCallback(
    (ws: Uuid, selection: Selection) => {
      const fresh: Buffer = { id: nextBufferId(), workspaceId: ws, selection };
      const at = buffers.findIndex((item) => item.id === activeBufferId);
      setBuffers(
        at === -1
          ? [...buffers, fresh]
          : [...buffers.slice(0, at + 1), fresh, ...buffers.slice(at + 1)],
      );
      setActiveBufferId(fresh.id);
    },
    [buffers, activeBufferId],
  );

  const duplicateBuffer = useCallback(() => {
    if (!buffer) return;
    openInNewBuffer(buffer.workspaceId, buffer.selection);
  }, [buffer, openInNewBuffer]);

  /** Point every tab showing a deleted object back to the workspace overview. */
  const forgetSelection = useCallback((ws: Uuid, gone: Selection) => {
    setBuffers((open) =>
      open.map((item) =>
        item.workspaceId === ws && sameSelection(item.selection, gone)
          ? { ...item, selection: { kind: "workspace" } }
          : item,
      ),
    );
  }, []);

  const closeBuffer = useCallback(
    (id: string) => {
      if (buffers.length <= 1) return;
      const at = buffers.findIndex((item) => item.id === id);
      const left = buffers.filter((item) => item.id !== id);
      setBuffers(left);
      // Focus the tab to the right, or the last one.
      if (activeBufferId === id) {
        setActiveBufferId(left[Math.min(at, left.length - 1)]?.id ?? null);
      }
    },
    [buffers, activeBufferId],
  );

  const switchWorkspace = useCallback(
    (id: Uuid) => {
      if (!data[id]) void loadWorkspace(id);
      goTo(id, { kind: "workspace" });
    },
    [data, loadWorkspace, goTo],
  );

  /* -- The rail ------------------------------------------------------------ */

  const tree: Node<BlobView>[] = useMemo(
    () => build((here.blobViews ?? []).map((view) => ({ key: view.blob.key, item: view }))),
    [here.blobViews],
  );

  // Branches start expanded.
  const expanded = useMemo(() => {
    const open = new Set(branchPaths(tree));
    for (const path of collapsed) open.delete(path);
    return open;
  }, [tree, collapsed]);

  const visible = useMemo(() => flatten(tree, expanded, query), [tree, expanded, query]);

  const rail: RailRow[] = useMemo(
    () => railRows(here.tables ?? [], visible),
    [here.tables, visible],
  );

  const blobTotal = here.blobViews?.length ?? 0;
  const blobShown = visible.filter((node) => node.kind === "leaf").length;

  const openId = !buffer
    ? ""
    : buffer.selection.kind === "workspace"
      ? "overview"
      : buffer.selection.kind === "members"
        ? "members"
        : buffer.selection.kind === "table"
          ? `table:${buffer.selection.name}`
          : `blob:${buffer.selection.key}`;

  // Opening a blob reveals the branch it hangs from.
  useEffect(() => {
    if (buffer?.selection.kind !== "blob") return;
    const key = buffer.selection.key;
    setCollapsed((current) => {
      const above = ancestors(key);
      if (!above.some((path) => current.has(path))) return current;
      const next = new Set(current);
      for (const path of above) next.delete(path);
      return next;
    });
  }, [buffer?.selection]);

  useEffect(() => {
    const at = rail.findIndex((item) => item.id === openId);
    if (at >= 0) setRailCursor(at);
  }, [openId, rail]);

  useEffect(() => {
    setRailCursor((at) => Math.min(at, Math.max(rail.length - 1, 0)));
  }, [rail.length]);

  const openRow = useCallback(
    (row: RailRow, newTab = false) => {
      if (!workspaceId) return;
      const show = newTab ? openInNewBuffer : goTo;
      if (row.kind === "overview") show(workspaceId, { kind: "workspace" });
      else if (row.kind === "members") show(workspaceId, { kind: "members" });
      else if (row.kind === "table") show(workspaceId, { kind: "table", name: row.table.name });
      else if (row.kind === "leaf") show(workspaceId, { kind: "blob", key: row.key });
      else {
        setCollapsed((current) => {
          const next = new Set(current);
          if (next.has(row.path)) next.delete(row.path);
          else next.add(row.path);
          return next;
        });
      }
    },
    [workspaceId, goTo, openInNewBuffer],
  );

  /** The open blob, re-fetched when selected. */
  const [openBlob, setOpenBlob] = useState<BlobView | null>(null);
  useEffect(() => {
    if (buffer?.selection.kind !== "blob" || !workspaceId) {
      setOpenBlob(null);
      return;
    }
    const key = buffer.selection.key;
    let live = true;
    setOpenBlob(null);
    api
      .readBlob(workspaceId, key)
      .then((view) => live && setOpenBlob(view))
      .catch((error) => live && setProblem(report(error)));
    return () => {
      live = false;
    };
  }, [buffer?.selection, workspaceId, report]);

  // Clear query stats when leaving a table.
  useEffect(() => {
    if (buffer?.selection.kind !== "table") {
      setLast(null);
      setRows(null);
    }
  }, [buffer?.selection]);

  /* -- The command registry ------------------------------------------------ */

  const commands: PaletteItem[] = useMemo(() => {
    const list: PaletteItem[] = [
      {
        id: "new-workspace",
        kind: "cmd",
        label: ":new workspace",
        hint: "create a workspace",
        run: () => setOverlay({ kind: "new-workspace" }),
      },
      {
        id: "new-table",
        kind: "cmd",
        label: ":new table",
        hint: "create a table in this workspace",
        run: () =>
          rights.can("table.create")
            ? setOverlay({ kind: "new-table" })
            : say("requires owner", true),
      },
      {
        id: "upload",
        kind: "cmd",
        label: ":upload",
        hint: "upload a file",
        run: () =>
          rights.can("blob.create")
            ? setOverlay({ kind: "upload" })
            : say("requires owner", true),
      },
      {
        id: "add-column",
        kind: "cmd",
        label: ":add column",
        hint: "add a column to this table",
        run: () =>
          !rights.can("table.write")
            ? say("requires editor", true)
            : tableActions.current
              ? tableActions.current.addColumn()
              : say("open a table first", true),
      },
      {
        id: "insert-row",
        kind: "cmd",
        label: ":insert row",
        hint: "insert a row into this table",
        run: () =>
          !rights.can("table.write")
            ? say("requires editor", true)
            : tableActions.current
              ? tableActions.current.insertRow()
              : say("open a table first", true),
      },
      {
        id: "find",
        kind: "cmd",
        label: ":find",
        hint: "search blobs",
        run: () => findRef.current?.focus(),
      },
      {
        id: "new-tab",
        kind: "cmd",
        label: ":new tab",
        hint: "duplicate this tab",
        run: () => (buffer ? duplicateBuffer() : say("nothing open", true)),
      },
      {
        id: "close",
        kind: "cmd",
        label: ":close",
        hint: "close this tab",
        run: () =>
          buffers.length > 1 && activeBufferId
            ? closeBuffer(activeBufferId)
            : say("can't close the last tab", true),
      },
      {
        id: "grant",
        kind: "cmd",
        label: ":grant access",
        hint: "add a member",
        run: () =>
          rights.can("project.manage_members")
            ? setOverlay({ kind: "grant" })
            : say("requires admin", true),
      },
      {
        id: "members",
        kind: "cmd",
        label: ":members",
        hint: "workspace members",
        run: () =>
          workspaceId ? goTo(workspaceId, { kind: "members" }) : say("no workspace open", true),
      },
      {
        id: "reload",
        kind: "cmd",
        label: ":reload",
        hint: "reload this workspace",
        run: () => {
          void loadPlatform();
          if (workspaceId) void loadWorkspace(workspaceId);
          say("reloading…");
        },
      },
      {
        id: "density",
        kind: "cmd",
        label: ":density",
        hint: "toggle compact mode",
        run: () => setCompact((on) => !on),
      },
      {
        id: "signout",
        kind: "cmd",
        label: ":sign out",
        hint: "sign out",
        run: signOut,
      },
    ];

    for (const item of projects) {
      list.push({
        id: `p:${item.id}`,
        kind: "workspace",
        label: item.name,
        hint: item.description ?? "workspace",
        run: () => switchWorkspace(item.id),
      });
    }
    if (workspaceId) {
      for (const table of here.tables ?? []) {
        list.push({
          id: `t:${table.id}`,
          kind: "table",
          label: table.name,
          hint: table.description ?? table.datastore_name,
          run: () => goTo(workspaceId, { kind: "table", name: table.name }),
        });
      }
      for (const view of here.blobViews ?? []) {
        list.push({
          id: `b:${view.blob.id}`,
          kind: "blob",
          label: view.blob.key,
          hint: view.blob.description ?? (view.stored ? "blob" : "not uploaded"),
          run: () => goTo(workspaceId, { kind: "blob", key: view.blob.key }),
        });
      }
    }
    return list;
  }, [
    projects,
    here.tables,
    here.blobViews,
    workspaceId,
    rights,
    buffers.length,
    activeBufferId,
    say,
    signOut,
    loadPlatform,
    loadWorkspace,
    closeBuffer,
    goTo,
    buffer,
    duplicateBuffer,
    switchWorkspace,
  ]);

  const runTyped = useCallback(() => {
    const typed = cmdValue.trim().toLowerCase();
    setCmdOpen(false);
    setCmdValue("");
    if (!typed) return;

    const asNumber = Number(typed);
    if (Number.isInteger(asNumber) && asNumber >= 1 && asNumber <= buffers.length) {
      setActiveBufferId(buffers[asNumber - 1].id);
      return;
    }

    const found =
      commands.find((item) => item.label.replace(/^:/, "") === typed) ??
      commands.find((item) => item.label.replace(/^:/, "").startsWith(typed)) ??
      commands.find((item) => item.kind !== "cmd" && item.label.toLowerCase() === typed);

    if (found) found.run();
    else say(`unknown command: ${typed}`, true);
  }, [cmdValue, commands, buffers, say]);

  /* -- One keyboard dispatcher --------------------------------------------- */

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        !!target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOverlay((current) => (current?.kind === "palette" ? null : { kind: "palette" }));
        return;
      }
      if (event.key === "Escape") {
        setOverlay(null);
        setCmdOpen(false);
        return;
      }
      if (typing || overlay || !me) return;

      if (event.key === ":") {
        event.preventDefault();
        setCmdOpen(true);
        return;
      }
      if (event.key === "f" || event.key === "/") {
        event.preventDefault();
        findRef.current?.focus();
        findRef.current?.select();
        return;
      }
      if (event.key === "j" || event.key === "ArrowDown") {
        event.preventDefault();
        setRailCursor((at) => Math.min(at + 1, rail.length - 1));
        return;
      }
      if (event.key === "k" || event.key === "ArrowUp") {
        event.preventDefault();
        setRailCursor((at) => Math.max(at - 1, 0));
        return;
      }
      if (event.key === "Enter") {
        const item = rail[railCursor];
        if (item) {
          event.preventDefault();
          // Shift+Enter opens in a new tab.
          openRow(item, event.shiftKey);
        }
        return;
      }
      if (/^[1-9]$/.test(event.key)) {
        const target = buffers[Number(event.key) - 1];
        if (target) {
          event.preventDefault();
          setActiveBufferId(target.id);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rail, railCursor, buffers, overlay, me, openRow]);

  /* -- Render -------------------------------------------------------------- */

  if (!me) {
    return <Gate onSubmit={signIn} pending={gatePending} problem={gateProblem} />;
  }

  const tabs: Tab[] = buffers.map((item) => {
    const of = projects.find((entry) => entry.id === item.workspaceId);
    const loading = data[item.workspaceId]?.loading ?? true;
    if (item.selection.kind === "workspace") {
      return {
        id: item.id,
        kind: "workspace",
        label: of?.name ?? "workspace",
        title: of?.description ?? of?.name ?? "workspace",
        loading,
      };
    }
    if (item.selection.kind === "members") {
      return {
        id: item.id,
        kind: "members",
        label: "members",
        title: `${of?.name ?? "workspace"} · members`,
        loading,
      };
    }
    if (item.selection.kind === "table") {
      return {
        id: item.id,
        kind: "table",
        label: item.selection.name,
        title: `${of?.name ?? "workspace"} · table ${item.selection.name}`,
        loading,
      };
    }
    const key = item.selection.key;
    return {
      id: item.id,
      kind: "blob",
      label: key.split("/").pop() ?? key,
      title: `${of?.name ?? "workspace"} · ${key}`,
      loading,
    };
  });

  const context = !buffer
    ? "nothing open"
    : buffer.selection.kind === "workspace"
      ? "overview"
      : buffer.selection.kind === "members"
        ? "members"
        : buffer.selection.kind === "table"
          ? `table ${buffer.selection.name}`
          : buffer.selection.key;

  const mode: Mode = cmdOpen ? "command" : here.loading ? "busy" : "normal";

  return (
    <div
      className="vg-app"
      data-density={compact ? "compact" : "comfortable"}
    >
      <Tabline
        tabs={tabs}
        activeId={activeBufferId}
        email={me.email}
        onPick={setActiveBufferId}
        onClose={closeBuffer}
        onNew={() =>
          buffer ? duplicateBuffer() : setOverlay({ kind: "new-workspace" })
        }
        onPalette={() => setOverlay({ kind: "palette" })}
        onSignOut={signOut}
      />

      <Canvas>
        {problem && (
          <div style={{ paddingTop: 20 }}>
            <Problem>{problem}</Problem>
          </div>
        )}

        {!project || !buffer ? (
          <div style={{ paddingTop: 60, maxWidth: 720 }}>
            <Empty>
              no workspaces yet
              <div style={{ marginTop: 16 }}>
                <button className="vg-btn is-primary" onClick={() => setOverlay({ kind: "new-workspace" })}>
                  create a workspace
                </button>
              </div>
            </Empty>
          </div>
        ) : (
          <div className="vg-split" style={{ paddingTop: 20 }}>
            <Rail
              rows={rail}
              cursor={railCursor}
              openId={openId}
              rights={rights}
              tableCount={here.tables?.length ?? 0}
              blobTotal={blobTotal}
              blobShown={blobShown}
              query={query}
              expanded={expanded}
              findRef={findRef}
              onQuery={setQuery}
              onOpen={openRow}
              onNewTable={() => setOverlay({ kind: "new-table" })}
              onNewBlob={() => setOverlay({ kind: "upload" })}
            />

            <div style={{ minWidth: 0 }}>
              {buffer.selection.kind === "workspace" && (
                <WorkspacePane
                  project={project}
                  role={role ?? "no role"}
                  tables={here.tables ?? []}
                  blobViews={here.blobViews}
                  members={here.members}
                  rights={rights}
                  onOpenTable={(name) => goTo(project.id, { kind: "table", name })}
                  onOpenBlob={(key) => goTo(project.id, { kind: "blob", key })}
                  onNewTable={() => setOverlay({ kind: "new-table" })}
                  onNewBlob={() => setOverlay({ kind: "upload" })}
                  onOpenMembers={() => goTo(project.id, { kind: "members" })}
                />
              )}

              {buffer.selection.kind === "members" && (
                <MembersPane
                  project={project}
                  role={role ?? "no role"}
                  members={here.members}
                  rights={rights}
                  onGrant={() => setOverlay({ kind: "grant" })}
                  onRemove={(member) =>
                    setOverlay({
                      kind: "confirm",
                      title: `Remove ${member.email}`,
                      body: `They will lose access to ${project.name}.`,
                      verb: "remove",
                      run: async () => {
                        await api.removeMembership(project.id, member.user_id);
                        await loadWorkspace(project.id);
                        say(`removed ${member.email}`);
                      },
                    })
                  }
                />
              )}

              {buffer.selection.kind === "table" &&
                (() => {
                  const name = (buffer.selection as { name: string }).name;
                  const table = (here.tables ?? []).find((item) => item.name === name);
                  if (!table) return <Loading />;
                  return (
                    <TablePane
                      key={`${project.id}/${table.name}`}
                      project={project.id}
                      table={table}
                      rights={rights}
                      registerActions={(actions) => {
                        tableActions.current = actions;
                      }}
                      onRan={(verb, seconds, returned) => {
                        setLast({ verb, latency: fmtLatency(seconds) });
                        setRows(returned);
                        setReachable(true);
                      }}
                      onDeleted={() => {
                        forgetSelection(project.id, { kind: "table", name: table.name });
                        void loadWorkspace(project.id);
                        say(`deleted ${table.name}`);
                      }}
                      onAskDelete={(confirm) => setOverlay({ kind: "confirm", ...confirm })}
                    />
                  );
                })()}

              {buffer.selection.kind === "blob" &&
                (openBlob === null ? (
                  <Loading />
                ) : (
                  <BlobPane
                    key={`${project.id}/${openBlob.blob.key}`}
                    project={project.id}
                    view={openBlob}
                    rights={rights}
                    onDeleted={() => {
                      forgetSelection(project.id, { kind: "blob", key: openBlob.blob.key });
                      void loadWorkspace(project.id);
                      say(`deleted ${openBlob.blob.key}`);
                    }}
                    onReplaced={() => {
                      void loadWorkspace(project.id);
                      say("file replaced");
                    }}
                    onAskDelete={(confirm) => setOverlay({ kind: "confirm", ...confirm })}
                  />
                ))}
            </div>
          </div>
        )}
      </Canvas>

      <Cmdline
        open={cmdOpen}
        value={cmdValue}
        message={message}
        onChange={setCmdValue}
        onRun={runTyped}
        onDismiss={() => setCmdOpen(false)}
      />

      <Statusline
        mode={mode}
        projects={projects}
        workspaceId={workspaceId}
        onPickWorkspace={switchWorkspace}
        onNewWorkspace={() => setOverlay({ kind: "new-workspace" })}
        context={context}
        role={role ?? "no role"}
        last={last}
        rows={rows}
        reachable={reachable}
      />

      {overlay?.kind === "palette" && (
        <Palette items={commands} onDismiss={() => setOverlay(null)} />
      )}
      {overlay?.kind === "new-workspace" && (
        <NewWorkspaceDialog
          onDismiss={() => setOverlay(null)}
          onCreated={async (id) => {
            setOverlay(null);
            await loadPlatform();
            switchWorkspace(id);
            say("workspace created");
          }}
        />
      )}
      {overlay?.kind === "new-table" && project && (
        <NewTableDialog
          project={project.id}
          catalogue={catalogue}
          onDismiss={() => setOverlay(null)}
          onCreated={async (name) => {
            setOverlay(null);
            await loadWorkspace(project.id);
            goTo(project.id, { kind: "table", name });
            say(`created ${name}`);
          }}
        />
      )}
      {overlay?.kind === "upload" && project && (
        <UploadDialog
          project={project.id}
          catalogue={catalogue}
          onDismiss={() => setOverlay(null)}
          onUploaded={async (key) => {
            setOverlay(null);
            await loadWorkspace(project.id);
            goTo(project.id, { kind: "blob", key });
            say(`uploaded ${key}`);
          }}
        />
      )}
      {overlay?.kind === "grant" && project && (
        <GrantDialog
          project={project.id}
          rights={rights}
          members={here.members ?? []}
          onDismiss={() => setOverlay(null)}
          onGranted={async () => {
            setOverlay(null);
            await loadWorkspace(project.id);
            say("access granted");
          }}
        />
      )}
      {overlay?.kind === "confirm" && (
        <ConfirmDialog
          title={overlay.title}
          body={overlay.body}
          verb={overlay.verb}
          onDismiss={() => setOverlay(null)}
          run={async () => {
            await overlay.run();
            setOverlay(null);
          }}
        />
      )}
    </div>
  );
}
