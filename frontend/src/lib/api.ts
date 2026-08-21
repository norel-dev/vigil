/**
 * The API, as the console needs it.
 *
 * Everything goes through `/api`, which the dev server forwards to the
 * platform. The key travels as a bearer token on every request; nothing else
 * about the caller is sent.
 */

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

/** An error the platform reported, carrying what it actually said. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

/** Turn FastAPI's two error shapes into one sentence. */
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
  return `the platform answered ${status} and said nothing more`;
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
    throw new ApiError(0, "the platform did not answer — check that the api is running on :8000");
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const parsed = text ? (JSON.parse(text) as unknown) : null;

  if (!response.ok) throw new ApiError(response.status, readDetail(response.status, parsed));
  return parsed as T;
}

/** Blob keys carry slashes as part of the name, and the route reads them as one. */
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
 * Point a signed URL at the dev-server proxy.
 *
 * The signature was cut against `minio:9000`, a name only the compose network
 * resolves. The proxy sends the request to the store on localhost while still
 * addressing it as `minio:9000`, so the path and query — which carry the whole
 * signature — are kept exactly as they were handed over.
 */
export function viaProxy(signed: string): string {
  const url = new URL(signed);
  return `/blob${url.pathname}${url.search}`;
}

/** Send the bytes. The signature covers one PUT of one key, and nothing else. */
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
        ? "the upload url was refused — it is good for fifteen minutes, so ask for a new one"
        : `the store refused the upload with ${response.status}`,
    );
  }
}
