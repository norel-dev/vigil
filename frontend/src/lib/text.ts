/** Fetch a blob as text for the source viewer. */

/** Max size the source viewer will load. */
export const TEXT_LIMIT = 1024 * 1024;

export class TooLarge extends Error {
  readonly size: number;

  constructor(size: number) {
    super("too large to print");
    this.name = "TooLarge";
    this.size = size;
  }
}

export interface Source {
  text: string;
  /** The bytes were not valid UTF-8. */
  lossy: boolean;
  lines: number;
}

export async function readSource(
  url: string,
  size: number,
  signal?: AbortSignal,
): Promise<Source> {
  if (size > TEXT_LIMIT) throw new TooLarge(size);

  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`download failed (${response.status})`);
  const buffer = await response.arrayBuffer();

  // Strict decode to detect invalid UTF-8, then fall back to lenient.
  let lossy = false;
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(buffer);
  } catch {
    lossy = true;
    text = new TextDecoder("utf-8").decode(buffer);
  }

  return { text, lossy, lines: text.length === 0 ? 0 : text.split("\n").length };
}
