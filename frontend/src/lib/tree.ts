/** Builds a folder tree from slash-separated blob keys (folders are display-only). */

export interface Branch<T> {
  kind: "branch";
  /** e.g. `survey/day1`. */
  path: string;
  name: string;
  depth: number;
  children: Node<T>[];
  /** Leaf count at any depth. */
  count: number;
}

export interface Leaf<T> {
  kind: "leaf";
  /** The full key. */
  path: string;
  name: string;
  depth: number;
  item: T;
}

export type Node<T = unknown> = Branch<T> | Leaf<T>;

interface Draft<T> {
  branches: Map<string, Draft<T>>;
  leaves: { name: string; item: T }[];
}

function draft<T>(): Draft<T> {
  return { branches: new Map(), leaves: [] };
}

/** Build the tree. Branches first, then leaves, each sorted by name. */
export function build<T>(items: { key: string; item: T }[]): Node<T>[] {
  const root = draft<T>();

  for (const { key, item } of items) {
    const segments = key.split("/").filter((segment) => segment !== "");
    if (segments.length === 0) continue;
    let at = root;
    for (const segment of segments.slice(0, -1)) {
      let next = at.branches.get(segment);
      if (!next) {
        next = draft<T>();
        at.branches.set(segment, next);
      }
      at = next;
    }
    at.leaves.push({ name: segments[segments.length - 1], item });
  }

  const walk = (node: Draft<T>, prefix: string, depth: number): Node<T>[] => {
    const branches: Node<T>[] = [...node.branches.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, child]) => {
        const path = prefix ? `${prefix}/${name}` : name;
        const children = walk(child, path, depth + 1);
        return {
          kind: "branch" as const,
          path,
          name,
          depth,
          children,
          count: children.reduce(
            (total, item) => total + (item.kind === "branch" ? item.count : 1),
            0,
          ),
        };
      });

    const leaves: Node<T>[] = node.leaves
      .sort((a, b) => a.name.localeCompare(b.name))
      .map(({ name, item }) => ({
        kind: "leaf" as const,
        path: prefix ? `${prefix}/${name}` : name,
        name,
        depth,
        item,
      }));

    return [...branches, ...leaves];
  };

  return walk(root, "", 0);
}

/**
 * Visible rows. Without a query, respects expansion; with one, shows matching
 * leaves and their parent branches regardless of expansion.
 */
export function flatten<T>(
  nodes: Node<T>[],
  expanded: ReadonlySet<string>,
  query: string,
): Node<T>[] {
  const needle = query.trim().toLowerCase();
  const rows: Node<T>[] = [];

  const walk = (list: Node<T>[]) => {
    for (const node of list) {
      if (node.kind === "leaf") {
        if (needle === "" || node.path.toLowerCase().includes(needle)) rows.push(node);
        continue;
      }
      const kept = needle === "" ? node.children : keptUnder(node, needle);
      if (needle !== "" && kept.length === 0) continue;
      rows.push(node);
      if (needle !== "" || expanded.has(node.path)) walk(kept);
    }
  };

  walk(nodes);
  return rows;
}

function keptUnder<T>(branch: Branch<T>, needle: string): Node<T>[] {
  const kept: Node<T>[] = [];
  for (const child of branch.children) {
    if (child.kind === "leaf") {
      if (child.path.toLowerCase().includes(needle)) kept.push(child);
    } else if (keptUnder<T>(child, needle).length > 0) {
      kept.push(child);
    }
  }
  return kept;
}

/** All branch paths in the tree. */
export function branchPaths<T>(nodes: Node<T>[]): string[] {
  const paths: string[] = [];
  const walk = (list: Node<T>[]) => {
    for (const node of list) {
      if (node.kind === "branch") {
        paths.push(node.path);
        walk(node.children as Node<T>[]);
      }
    }
  };
  walk(nodes);
  return paths;
}

/** Branch paths above a key. */
export function ancestors(key: string): string[] {
  const segments = key.split("/").filter((segment) => segment !== "");
  return segments.slice(0, -1).map((_, index) => segments.slice(0, index + 1).join("/"));
}

export interface Run {
  text: string;
  hit: boolean;
}

/**
 * Split a node's name into matched/unmatched runs for highlighting.
 * Matches against the full path, so `day1/ket` highlights across segments.
 */
export function runs(path: string, name: string, query: string): Run[] {
  const needle = query.trim().toLowerCase();
  if (needle === "") return [{ text: name, hit: false }];

  const start = path.length - name.length;
  const haystack = path.toLowerCase();
  const hits: [number, number][] = [];
  for (let at = haystack.indexOf(needle); at !== -1; at = haystack.indexOf(needle, at + 1)) {
    hits.push([at, at + needle.length]);
  }

  const out: Run[] = [];
  let cursor = 0;
  for (const [from, to] of hits) {
    // Clip the hit to the window this segment occupies in the whole path.
    const a = Math.max(from - start, 0);
    const b = Math.min(to - start, name.length);
    if (b <= a || b <= cursor) continue;
    if (a > cursor) out.push({ text: name.slice(cursor, a), hit: false });
    out.push({ text: name.slice(Math.max(a, cursor), b), hit: true });
    cursor = b;
  }
  if (cursor < name.length) out.push({ text: name.slice(cursor), hit: false });
  return out.length > 0 ? out : [{ text: name, hit: false }];
}
