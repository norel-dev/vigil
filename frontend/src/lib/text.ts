/**
 * Bytes, read as text.
 *
 * Everything else the console shows is handed to an element as a URL and
 * fetched by the browser, progressively and without the page ever holding it.
 * Source is the exception: to print it, the console has to have it. So this is
 * the one path that pulls a whole blob into memory, and the only one that
 * needs a ceiling.
 */

/**
 * Above this, printing is refused rather than attempted. The limit is about
 * the document, not the download — a megabyte of source is some twenty
 * thousand lines, which is past the point where a reader is reading and into
 * the point where they want the file.
 */
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
  /** True when the bytes were not valid UTF-8, so what is shown is approximate. */
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
  if (!response.ok) throw new Error(`the store refused the read with ${response.status}`);
  const buffer = await response.arrayBuffer();

  // Decode twice rather than trusting the first result: a strict pass tells us
  // whether this was text at all, and a lenient one gives us something to show
  // when it was not. Saying so is the point — a file printed with replacement
  // characters and no warning reads as a corrupt file rather than as a binary.
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
