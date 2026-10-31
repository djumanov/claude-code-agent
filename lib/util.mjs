import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const PROJECTS = path.join(ROOT, "projects");

try {
  process.loadEnvFile(path.join(ROOT, ".env"));
} catch {
  /* .env is optional */
}

export const log = (...a) => console.log("\x1b[36m›\x1b[0m", ...a);
export const ok = (...a) => console.log("\x1b[32m✓\x1b[0m", ...a);
export const warn = (...a) => console.warn("\x1b[33m!\x1b[0m", ...a);

export class UserError extends Error {}
export const fail = (msg) => {
  throw new UserError(msg);
};

/** Run a command, streaming output unless quiet. Resolves { code, stdout, stderr }. */
export function run(cmd, args, { quiet = false, cwd = ROOT, allowFail = false } = {}) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { cwd, stdio: quiet ? ["ignore", "pipe", "pipe"] : "inherit" });
    let stdout = "";
    let stderr = "";
    p.stdout?.on("data", (d) => (stdout += d));
    p.stderr?.on("data", (d) => (stderr += d));
    p.on("error", (e) => reject(e.code === "ENOENT" ? new UserError(`'${cmd}' is not installed or not on PATH`) : e));
    p.on("close", (code) => {
      if (code !== 0 && !allowFail) {
        const tail = stderr.split("\n").slice(-15).join("\n");
        reject(new UserError(`${cmd} exited with code ${code}${tail ? `\n${tail}` : ""}`));
      } else resolve({ code, stdout, stderr });
    });
  });
}

export function projectDir(name) {
  if (!name) fail("Missing project name. Usage: vedit <command> <project>");
  if (!/^[\w.-]+$/.test(name)) fail(`Invalid project name '${name}' (use letters, numbers, - _ .)`);
  return path.join(PROJECTS, name);
}

export function loadProject(name) {
  const dir = projectDir(name);
  const file = path.join(dir, "project.json");
  if (!fs.existsSync(file)) fail(`Project '${name}' not found. Create it with: vedit new ${name}`);
  const cfg = JSON.parse(fs.readFileSync(file, "utf8"));
  return { name, dir, file, cfg, p: (...s) => path.join(dir, ...s) };
}

export function saveProject(proj) {
  fs.writeFileSync(proj.file, JSON.stringify(proj.cfg, null, 2) + "\n");
}

/** First file in dir whose extension is in exts, or null. */
export function findMedia(dir, exts) {
  if (!fs.existsSync(dir)) return null;
  const f = fs
    .readdirSync(dir)
    .filter((n) => !n.startsWith(".") && exts.includes(path.extname(n).toLowerCase()))
    .sort()[0];
  return f ? path.join(dir, f) : null;
}

export const VIDEO_EXTS = [".mp4", ".mov", ".webm", ".mkv", ".m4v"];
export const AUDIO_EXTS = [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"];

export async function download(url, dest, headers = {}) {
  const res = await fetch(url, { headers });
  if (!res.ok) fail(`Download failed (${res.status}) from ${new URL(url).host}`);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const tmp = dest + ".part";
  await fs.promises.writeFile(tmp, Buffer.from(await res.arrayBuffer()));
  fs.renameSync(tmp, dest);
  return dest;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export const escapeHtml = (s = "") =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
