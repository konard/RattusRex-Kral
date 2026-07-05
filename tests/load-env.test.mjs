import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

import { loadEnv, parseEnv } from "../scripts/load-env.mjs";
import { resolveDatabaseUrl } from "../scripts/dev.mjs";

test("parseEnv handles comments, quotes and export prefixes", () => {
  const parsed = parseEnv(
    [
      "# comment",
      "",
      "DATABASE_URL=postgresql://postgres:pw@localhost:5432/EpohaTruda",
      'QUOTED="value with spaces"',
      "SINGLE='single quoted'",
      "export EXPORTED=exported-value",
      "WITH_COMMENT=plain # trailing comment"
    ].join("\n")
  );

  assert.equal(parsed.DATABASE_URL, "postgresql://postgres:pw@localhost:5432/EpohaTruda");
  assert.equal(parsed.QUOTED, "value with spaces");
  assert.equal(parsed.SINGLE, "single quoted");
  assert.equal(parsed.EXPORTED, "exported-value");
  assert.equal(parsed.WITH_COMMENT, "plain");
});

test("loadEnv applies missing keys but preserves existing ones", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kral-env-"));
  fs.writeFileSync(path.join(dir, ".env"), "MISSING=from-file\nEXISTING=from-file\n");

  const env = { EXISTING: "from-shell" };
  const applied = loadEnv(dir, env);

  assert.equal(env.MISSING, "from-file");
  assert.equal(applied.MISSING, "from-file");
  assert.equal(env.EXISTING, "from-shell");
  assert.equal(applied.EXISTING, undefined);
});

test("loadEnv returns empty object when no .env file exists", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kral-env-"));
  assert.deepEqual(loadEnv(dir, {}), {});
});

test("resolveDatabaseUrl requires explicit configuration", () => {
  assert.throws(
    () => resolveDatabaseUrl({}),
    /DATABASE_URL is not set/
  );
});

test("resolveDatabaseUrl returns explicit configuration", () => {
  const databaseUrl = "postgresql://postgres:pw@localhost:5432/EpohaTruda";
  assert.equal(resolveDatabaseUrl({ DATABASE_URL: databaseUrl }), databaseUrl);
});
