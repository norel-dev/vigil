/**
 * Statement building.
 *
 * The console never runs a statement the reader has not been shown. Every
 * form that changes a table composes its SQL here and prints it back before
 * the button is pressed, because the platform does not parse the statement
 * either — the database engine refuses or accepts it, and a reader who never
 * saw the text cannot understand the refusal.
 */

/** A bare SQL identifier, which is all the platform accepts for a table name. */
export function isIdentifier(value: string): boolean {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(value);
}

/**
 * Render one typed value.
 *
 * An empty field means no value rather than an empty string: a blank cell in
 * a form is far more often "I have nothing for this" than "the text here is
 * zero characters long". Anything that reads as a number is written as one;
 * everything else is quoted, with quotes inside it doubled.
 */
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

/**
 * Preview a table that does not exist yet.
 *
 * Creating a table is not a statement the caller writes — the platform builds
 * it, and generates the name the datastore will really hold it under. This is
 * shown so the shape being asked for is legible, and is labelled as a sketch
 * rather than as the statement that will run.
 */
export function createTableSketch(
  name: string,
  columns: { name: string; type: string; nullable: boolean; primary_key: boolean }[],
): string {
  const lines = columns.map((column) => {
    const label = column.name || "«name»";
    const type = column.type || "«type»";
    return `  ${label} ${type}${column.nullable ? "" : " NOT NULL"}`;
  });

  // A key of one column is written the same way as a key of several, because
  // that is the one form the platform emits for both. Writing PRIMARY KEY
  // against a lone column here would print a shape the reader will not get.
  const key = columns.filter((column) => column.primary_key).map((column) => column.name || "«name»");
  if (key.length > 0) lines.push(`  PRIMARY KEY (${key.join(", ")})`);

  const body = lines.join(",\n");
  return `CREATE TABLE ${name || "«name»"} (\n${body || "  «no columns yet»"}\n)`;
}

/** What a statement is going to do, in one lowercase word, for the statusline. */
export function verbOf(statement: string): string {
  const first = statement.trim().split(/\s+/)[0] ?? "";
  return first.toLowerCase() || "—";
}

/** Whether a statement returns rows, so an empty result can be explained. */
export function isRead(statement: string): boolean {
  return /^\s*(select|with|values)\b/i.test(statement);
}
