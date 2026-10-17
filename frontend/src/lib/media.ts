import { api, viaProxy, type Uuid } from "./api";

/** Signed download URLs, cached until a minute before they expire. */
const held = new Map<string, { url: string; expires: number }>();

const MARGIN_MS = 60_000;

export async function downloadUrl(project: Uuid, key: string): Promise<string> {
  const id = `${project}/${key}`;
  const existing = held.get(id);
  if (existing && existing.expires - MARGIN_MS > Date.now()) return existing.url;

  const access = await api.blobAccess(project, key, "download");
  const url = viaProxy(access.url);
  held.set(id, { url, expires: new Date(access.expires_at).getTime() });
  return url;
}

export function forget(project: Uuid, key: string): void {
  held.delete(`${project}/${key}`);
}
