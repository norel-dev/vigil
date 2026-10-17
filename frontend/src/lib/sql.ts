/** SQL builders for the table forms. */

/** A plain SQL identifier. */
export function isIdentifier(value: string): boolean {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(value);
}

/** Form value to SQL literal: blank → NULL, numbers as-is, else quoted. */
export function literal(value: string): string {
  const trimmed = value.trim();
  if (trimmed === "") return "NULL";
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) return trimmed;
  return `'${value.replace(/'/g, "''")}'`;
}

export function insertStatement(
  table: string,
  fields: { column: string; value: string }[],
): string {
  const used = fields.filter((field) => field.value.trim() !== "");
  if (used.length === 0) return `INSERT INTO ${table} DEFAULT VALUES`;
  const columns = used.map((field) => field.column).join(", ");
  const values = used.map((field) => literal(field.value)).join(", ");
  return `INSERT INTO ${table} (${columns}) VALUES (${values})`;
}

export function addColumnStatement(table: string, name: string, type: string): string {
  return `ALTER TABLE ${table} ADD COLUMN ${name || "«name»"} ${type || "«type»"}`;
}

export function selectStatement(table: string, limit: number): string {
  return `SELECT * FROM ${table} LIMIT ${limit}`;
}

/** Approximate CREATE TABLE preview; the server generates the real statement. */
export function createTableSketch(
  name: string,
  columns: { name: string; type: string; nullable: boolean; primary_key: boolean }[],
): string {
  const lines = columns.map((column) => {
    const label = column.name || "«name»";
    const type = column.type || "«type»";
    return `  ${label} ${type}${column.nullable ? "" : " NOT NULL"}`;
  });

  // Always a table-level PRIMARY KEY clause, matching what the server emits.
  const key = columns.filter((column) => column.primary_key).map((column) => column.name || "«name»");
  if (key.length > 0) lines.push(`  PRIMARY KEY (${key.join(", ")})`);

  const body = lines.join(",\n");
  return `CREATE TABLE ${name || "«name»"} (\n${body || "  «no columns yet»"}\n)`;
}

/** First keyword of a statement, lowercased. */
export function verbOf(statement: string): string {
  const first = statement.trim().split(/\s+/)[0] ?? "";
  return first.toLowerCase() || "—";
}

/** Whether a statement returns rows. */
export function isRead(statement: string): boolean {
  return /^\s*(select|with|values)\b/i.test(statement);
}
