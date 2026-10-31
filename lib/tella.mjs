// Tella Public API client: list recordings, export one, download the MP4.
// Docs: https://docs.tella.com  (Bearer API key, 100 req/min per org)
import { download, fail, log, ok, sleep } from "./util.mjs";

const BASE = () => (process.env.TELLA_API_BASE || "https://api.tella.com/v1").replace(/\/$/, "");

function key() {
  const k = process.env.TELLA_API_KEY;
  if (!k) fail("TELLA_API_KEY is not set. Add it to .env, or download the MP4 from Tella and use: vedit import <project> <file>");
  return k;
}

async function api(method, path, body) {
  const res = await fetch(BASE() + path, {
    method,
    headers: { Authorization: `Bearer ${key()}`, "Content-Type": "application/json", Accept: "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json;
  try {
    json = text ? JSON.parse(text) : {};
  } catch {
    json = { raw: text };
  }
  if (!res.ok) fail(`Tella API ${method} ${path} → ${res.status}: ${json.message || json.error || text.slice(0, 200)}`);
  return json;
}

// Response shapes can be wrapped ({ data: ... }, { export: ... }); search for fields defensively.
function pick(obj, keys) {
  if (!obj || typeof obj !== "object") return undefined;
  for (const k of keys) if (obj[k] !== undefined && obj[k] !== null) return obj[k];
  for (const v of Object.values(obj)) {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      const r = pick(v, keys);
      if (r !== undefined) return r;
    }
  }
  return undefined;
}

export async function listVideos() {
  const j = await api("GET", "/videos");
  const items = Array.isArray(j) ? j : j.data || j.videos || j.items || [];
  return items.map((v) => ({
    id: v.id,
    title: v.title || v.name || "(untitled)",
    duration: v.duration ?? v.durationSeconds,
    createdAt: v.createdAt || v.created_at,
  }));
}

/** Export a Tella video to MP4 and download it to `dest`. */
export async function pullVideo(videoId, dest, { resolution = "1080p" } = {}) {
  log(`Requesting ${resolution} export of Tella video ${videoId}…`);
  const started = await api("POST", `/videos/${encodeURIComponent(videoId)}/exports`, { resolution, granularity: "video" });
  const exportId = pick(started, ["exportId", "id"]);
  if (!exportId) fail(`Unexpected export response: ${JSON.stringify(started).slice(0, 300)}`);

  const deadline = Date.now() + 30 * 60_000;
  let delay = 3000;
  while (Date.now() < deadline) {
    // Export IDs can contain slashes: encode as a single path segment.
    const s = await api("GET", `/videos/${encodeURIComponent(videoId)}/exports/${encodeURIComponent(exportId)}`);
    const status = String(pick(s, ["status", "state"]) || "").toLowerCase();
    const url = pick(s, ["downloadUrl", "download_url", "url"]);
    const progress = pick(s, ["progress"]);
    if (url && typeof url === "string" && url.startsWith("http")) {
      log("Export ready, downloading…");
      await download(url, dest);
      ok(`Saved Tella recording → ${dest}`);
      return dest;
    }
    if (["failed", "error", "cancelled", "canceled"].includes(status)) fail(`Tella export ${status}`);
    process.stdout.write(`\r  export ${status || "processing"}${progress != null ? ` ${Math.round(progress <= 1 ? progress * 100 : progress)}%` : ""}   `);
    await sleep(delay);
    delay = Math.min(delay * 1.5, 15000);
  }
  fail("Timed out waiting for the Tella export (30 min)");
}
