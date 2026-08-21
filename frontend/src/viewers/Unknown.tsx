import type { Viewer } from "./viewer";
import { Empty } from "../components/bits";
import { bytes } from "../lib/format";

/**
 * The last resort, and the reason the registry never returns nothing.
 *
 * It claims no type and no extension — the registry falls back to it rather
 * than matching it — so it cannot accidentally take a format a real viewer
 * would have handled. What it says is the truth about this blob and not a
 * general apology: the size and the type are named, because between them they
 * are usually enough for a reader to know what they are holding.
 */
export const unknown: Viewer = {
  kind: "file",
  types: [],
  extensions: [],
  render: ({ stored }) => (
    <Empty>
      this holds {bytes(stored.size)} of{" "}
      <code className="dp-inline-code">{stored.content_type ?? "an unstated type"}</code>, which the
      browser has nothing to show it with. open the bytes to download them.
    </Empty>
  ),
};
