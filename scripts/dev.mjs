import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const commands = [
  {
    name: "back",
    color: "\x1b[36m",
    command: "python",
    args: ["-m", "uvicorn", "backend.main:app", "--reload"],
    cwd: rootDir,
  },
  {
    name: "front",
    color: "\x1b[35m",
    command: process.execPath,
    args: [
      path.join(rootDir, "frontend", "node_modules", "vite", "bin", "vite.js"),
      "--host",
      "127.0.0.1",
      "--port",
      "5173",
    ],
    cwd: path.join(rootDir, "frontend"),
  },
];

const reset = "\x1b[0m";
const children = new Map();
let shuttingDown = false;

function prefix(name, color, chunk) {
  const text = chunk.toString();
  for (const line of text.split(/\r?\n/)) {
    if (line.length > 0) {
      process.stdout.write(`${color}[${name}]${reset} ${line}\n`);
    }
  }
}

function spawnCommand(config) {
  const child = spawn(config.command, config.args, {
    cwd: config.cwd,
    env: process.env,
    shell: process.platform === "win32" && config.command !== process.execPath,
    stdio: ["ignore", "pipe", "pipe"],
  });

  children.set(child.pid, child);
  child.stdout.on("data", (chunk) => prefix(config.name, config.color, chunk));
  child.stderr.on("data", (chunk) => prefix(config.name, config.color, chunk));

  child.on("exit", (code, signal) => {
    children.delete(child.pid);
    if (!shuttingDown) {
      shutdown(code ?? (signal ? 1 : 0));
    }
  });

  return child;
}

function killTree(child) {
  if (!child.pid || child.exitCode !== null) {
    return Promise.resolve();
  }

  if (process.platform === "win32") {
    return new Promise((resolve) => {
      const killer = spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
      });
      killer.on("exit", resolve);
      killer.on("error", resolve);
    });
  }

  child.kill("SIGINT");
  return Promise.resolve();
}

async function shutdown(exitCode = 0) {
  if (shuttingDown) {
    return;
  }

  shuttingDown = true;
  await Promise.all([...children.values()].map(killTree));
  process.exit(exitCode);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
process.on("SIGHUP", () => shutdown(0));

for (const command of commands) {
  spawnCommand(command);
}
