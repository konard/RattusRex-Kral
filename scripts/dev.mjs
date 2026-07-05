import { spawn } from "node:child_process";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadEnv } from "./load-env.mjs";

const projectRoot = new URL("..", import.meta.url);
const projectRootPath = fileURLToPath(projectRoot);

const children = new Set();
let shuttingDown = false;

export function applyProjectEnv(env = process.env) {
  // Load variables from a project-level `.env` file so that `npm run dev`
  // picks up DATABASE_URL without requiring it to be exported manually.
  const loadedEnv = loadEnv(projectRootPath, env);
  for (const key of Object.keys(loadedEnv)) {
    console.log(`[dev] Loaded ${key} from .env`);
  }
  return loadedEnv;
}

export function resolveApiTarget(env = process.env) {
  return env.VITE_API_TARGET ?? "http://127.0.0.1:8000";
}

export function resolveDatabaseUrl(env = process.env) {
  if (!env.DATABASE_URL) {
    throw new Error(
      "DATABASE_URL is not set. Create a .env file from .env.example or export DATABASE_URL."
    );
  }
  return env.DATABASE_URL;
}

function prefixOutput(label, stream) {
  let buffer = "";

  stream.on("data", (chunk) => {
    buffer += chunk.toString();
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.length > 0) {
        console.log(`[${label}] ${line}`);
      }
    }
  });

  stream.on("end", () => {
    if (buffer.length > 0) {
      console.log(`[${label}] ${buffer}`);
    }
  });
}

function spawnProcess(label, command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: projectRootPath,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        ...options.env
      },
      shell: options.shell ?? false,
      stdio: ["ignore", "pipe", "pipe"]
    });

    let settled = false;

    child.once("spawn", () => {
      settled = true;
      children.add(child);
      prefixOutput(label, child.stdout);
      prefixOutput(label, child.stderr);
      resolve(child);
    });

    child.once("error", (error) => {
      if (!settled) {
        reject(error);
      }
    });

    child.once("exit", (code, signal) => {
      children.delete(child);
      if (!shuttingDown) {
        const reason = signal ? `signal ${signal}` : `exit code ${code}`;
        console.error(`[${label}] stopped with ${reason}`);
        shutdown(code && code > 0 ? code : 1);
      }
    });
  });
}

function shutdown(code = 0) {
  if (shuttingDown) {
    return;
  }

  shuttingDown = true;
  for (const child of children) {
    child.kill();
  }
  process.exitCode = code;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function canReachBackend(apiTarget) {
  return new Promise((resolve) => {
    const target = new URL("/", apiTarget);
    const request = http.request(
      {
        hostname: target.hostname,
        port: target.port,
        path: target.pathname,
        method: "GET",
        timeout: 500
      },
      (response) => {
        response.resume();
        resolve(response.statusCode !== undefined && response.statusCode < 500);
      }
    );

    request.on("error", () => resolve(false));
    request.on("timeout", () => {
      request.destroy();
      resolve(false);
    });
    request.end();
  });
}

async function waitForBackend(child, apiTarget) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (await canReachBackend(apiTarget)) {
      return;
    }

    if (child.exitCode !== null) {
      throw new Error("FastAPI exited before it became reachable.");
    }

    await sleep(500);
  }

  throw new Error(`FastAPI did not become reachable at ${apiTarget}.`);
}

async function startBackend() {
  const localPython = process.platform === "win32"
    ? path.join(projectRootPath, ".venv", "Scripts", "python.exe")
    : path.join(projectRootPath, ".venv", "bin", "python");
  const candidates = process.env.PYTHON
    ? [process.env.PYTHON]
    : process.platform === "win32"
      ? [localPython, "py", "python"]
      : [localPython, "python3", "python"];
  const args = ["-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"];
  const databaseUrl = resolveDatabaseUrl();
  const env = {
    DATABASE_URL: databaseUrl
  };
  let lastError;

  for (const command of candidates) {
    try {
      return await spawnProcess("api", command, args, { env });
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError ?? new Error("Python was not found.");
}

async function main() {
  applyProjectEnv();

  process.on("SIGINT", () => shutdown(0));
  process.on("SIGTERM", () => shutdown(0));

  const apiTarget = resolveApiTarget();
  if (await canReachBackend(apiTarget)) {
    console.log(`[dev] Using existing FastAPI server at ${apiTarget}`);
  } else {
    console.log(`[dev] Starting FastAPI at ${apiTarget}`);
    const backend = await startBackend();
    await waitForBackend(backend, apiTarget);
  }

  console.log("[dev] Starting Vite");
  await spawnProcess("vite", "vite", ["--host", "0.0.0.0"], {
    shell: process.platform === "win32"
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(`[dev] ${error.message}`);
    shutdown(1);
  });
}
