import type { Viewer } from "./viewer";
import { Empty } from "../components/bits";
import { bytes } from "../lib/format";

/** Fallback viewer for formats nothing else handles. */
export const unknown: Viewer = {
  kind: "file",
  types: [],
  extensions: [],
  render: ({ stored }) => (
    <Empty>
      no preview for <code className="dp-inline-code">{stored.content_type ?? "unknown type"}</code>{" "}
      ({bytes(stored.size)})
    </Empty>
  ),
};
