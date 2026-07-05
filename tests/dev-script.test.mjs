import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));

test("dev launcher requires DATABASE_URL before starting a backend", () => {
  const result = spawnSync(process.execPath, ["scripts/dev.mjs"], {
    cwd: projectRoot,
    env: {
      ...process.env,
      DATABASE_URL: "",
      VITE_API_TARGET: "http://127.0.0.1:9"
    },
    encoding: "utf8",
    timeout: 3000
  });

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /DATABASE_URL is not set/);
  assert.doesNotMatch(
    `${result.stdout}\n${result.stderr}`,
    /default development database|postgresql:\/\/postgres:/i
  );
});
