/** API client. Requests go to `/api` with the key as a bearer token. */

export type Uuid = string;
export type ProjectRole = "viewer" | "editor" | "admin" | "owner";
export type DataType = "table" | "blob";

export interface CurrentUser {
  id: Uuid;
  email: string;
  is_platform_admin: boolean;
  project_roles: Record<Uuid, ProjectRole>;
}

export interface Project {
  id: Uuid;
  name: string;
  description: string | null;
  creation_date: string;
}

export interface Membership {
  user_id: Uuid;
  email: string;
  role: ProjectRole;
}

export interface CatalogueEntry {
  name: string;
  data_type: DataType;
  description: string | null;
}

export interface Table {
  id: Uuid;
  name: string;
  project_id: Uuid;
  datastore_name: string;
  description: string | null;
  creation_date: string;
}

export interface ColumnDefinition {
  name: string;
  type: string;
  nullable: boolean;
  /** Part of the (possibly composite) primary key. Must not be nullable. */
  primary_key: boolean;
}

export interface QueryResponse {
  data: unknown[][];
  metadata: { columns?: string[] } & Record<string, unknown>;
  latency: number;
}

export interface Blob {
  id: Uuid;
  key: string;
  project_id: Uuid;
  datastore_name: string;
  content_type: string | null;
  description: string | null;
  creation_date: string;
}

export interface StoredBlob {
  key: string;
  size: number;
  etag: string | null;
  last_modified: string | null;
  content_type: string | null;
}

export interface BlobView {
  blob: Blob;
  stored: StoredBlob | null;
}

export interface PresignedAccess {
  url: string;
  method: string;
  expires_at: string;
}

export interface CreatedBlob {
  blob: Blob;
  upload: PresignedAccess;
}

/** An API error. `status` is 0 when the server couldn't be reached. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

/** Flatten FastAPI's error `detail` (string or validation list) into a message. */
function readDetail(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const where = Array.isArray(item?.loc) ? item.loc.slice(1).join(".") : "";
        return where ? `${where}: ${item.msg}` : String(item.msg);
      })
      .join(" · ");
  }
  return `request failed (${status})`;
}

let key = "";
export function setKey(value: string): void {
  key = value;
}

async function call<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${key}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "api unreachable");
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let parsed: unknown = null;
  try {
    if (text) parsed = JSON.parse(text) as unknown;
  } catch {
    // Usually means the /api proxy isn't configured and we got index.html.
    throw new ApiError(response.status, "unexpected non-json response from /api");
  }

  if (!response.ok) throw new ApiError(response.status, readDetail(response.status, parsed));
  return parsed as T;
}

/** Encode a blob key for the URL, keeping its slashes. */
function keyPath(key: string): string {
  return key.split("/").map(encodeURIComponent).join("/");
}

export const api = {
  me: () => call<CurrentUser>("GET", "/users/me"),

  listProjects: () => call<Project[]>("GET", "/projects/"),
  createProject: (name: string, description: string | null) =>
    call<Project>("POST", "/projects/", { name, description }),
  listMembers: (project: Uuid) =>
    call<Membership[]>("GET", `/projects/${project}/members`),
  grantMembership: (project: Uuid, email: string, role: ProjectRole) =>
    call<Membership>("PUT", `/projects/${project}/members`, { email, role }),
  removeMembership: (project: Uuid, user: Uuid) =>
    call<void>("DELETE", `/projects/${project}/members/${user}`),

  catalogue: () => call<CatalogueEntry[]>("GET", "/datastores/catalogue"),

  listTables: (project: Uuid) => call<Table[]>("GET", `/projects/${project}/tables/`),
  createTable: (
    project: Uuid,
    body: { name: string; datastore: string; columns: ColumnDefinition[]; description: string | null },
  ) => call<Table>("POST", `/projects/${project}/tables/`, body),
  deleteTable: (project: Uuid, table: string) =>
    call<void>("DELETE", `/projects/${project}/tables/${encodeURIComponent(table)}`),
  query: (project: Uuid, table: string, query: string) =>
    call<QueryResponse>("POST", `/projects/${project}/tables/${encodeURIComponent(table)}/query`, {
      query,
    }),

  listBlobs: (project: Uuid) => call<Blob[]>("GET", `/projects/${project}/blobs/`),
  readBlob: (project: Uuid, key: string) =>
    call<BlobView>("GET", `/projects/${project}/blobs/${keyPath(key)}`),
  createBlob: (
    project: Uuid,
    body: { key: string; datastore: string; content_type: string | null; description: string | null },
  ) => call<CreatedBlob>("POST", `/projects/${project}/blobs/`, body),
  deleteBlob: (project: Uuid, key: string) =>
    call<void>("DELETE", `/projects/${project}/blobs/${keyPath(key)}`),
  blobAccess: (project: Uuid, key: string, operation: "download" | "upload") =>
    call<PresignedAccess>("POST", `/projects/${project}/blobs/${keyPath(key)}/access`, {
      operation,
    }),
};

/**
 * Route a signed URL through the `/blob` proxy. The signature is for
 * `minio:9000`, so path and query must be kept unchanged.
 */
export function viaProxy(signed: string): string {
  const url = new URL(signed);
  return `/blob${url.pathname}${url.search}`;
}

/** Upload a file to a signed URL. */
export async function uploadTo(access: PresignedAccess, file: File): Promise<void> {
  const response = await fetch(viaProxy(access.url), {
    method: access.method,
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });
  if (!response.ok) {
    throw new ApiError(
      response.status,
      response.status === 403
        ? "upload url expired; try again"
        : `upload failed (${response.status})`,
    );
  }
}
