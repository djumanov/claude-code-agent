// Epidemic Sound Partner API client: search tracks and download an MP3.
// Requires a partner agreement → Developer Portal credentials.
// Docs + OpenAPI spec: https://developers.epidemicsound.com/docs/
//
// Flow: access key id/secret → POST /v0/partner-token → partner bearer token.
// Premium tracks also need a *user* token for a subscribed user (EPIDEMIC_USER_ID).
// If your portal's spec differs from the paths below, adjust them here.
import { download, fail, log, ok } from "./util.mjs";

const BASE = () => (process.env.EPIDEMIC_API_BASE || "https://partner-content-api.epidemicsound.com").replace(/\/$/, "");
let partnerToken;
let userToken;

async function post(path, body, token) {
  const res = await fetch(BASE() + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token && { Authorization: `Bearer ${token}` }) },
    body: JSON.stringify(body),
  });
  const j = await res.json().catch(() => ({}));
  if (!res.ok) fail(`Epidemic Sound ${path} → ${res.status}: ${j.message || JSON.stringify(j).slice(0, 200)}`);
  return j;
}

async function getPartnerToken() {
  if (partnerToken) return partnerToken;
  const { EPIDEMIC_ACCESS_KEY_ID: accessKeyId, EPIDEMIC_ACCESS_KEY_SECRET: accessKeySecret } = process.env;
  if (!accessKeyId || !accessKeySecret)
    fail("EPIDEMIC_ACCESS_KEY_ID / EPIDEMIC_ACCESS_KEY_SECRET not set. Without Partner API access, download the track on epidemicsound.com and use: vedit music add <project> <file>");
  const j = await post("/v0/partner-token", { accessKeyId, accessKeySecret });
  partnerToken = j.accessToken || j.access_token || j.token;
  if (!partnerToken) fail("Epidemic Sound did not return a partner token");
  return partnerToken;
}

async function getToken() {
  const userId = process.env.EPIDEMIC_USER_ID;
  if (!userId) return getPartnerToken(); // free-tier tracks only
  if (userToken) return userToken;
  const j = await post("/v0/token", { userId }, await getPartnerToken());
  userToken = j.accessToken || j.access_token || j.token;
  return userToken || getPartnerToken();
}

async function get(path, params = {}) {
  const url = new URL(BASE() + path);
  for (const [k, v] of Object.entries(params)) if (v != null) url.searchParams.set(k, v);
  const res = await fetch(url, { headers: { Authorization: `Bearer ${await getToken()}` } });
  const j = await res.json().catch(() => ({}));
  if (!res.ok) fail(`Epidemic Sound ${path} → ${res.status}: ${j.message || JSON.stringify(j).slice(0, 200)}`);
  return j;
}

export async function searchTracks(term, { limit = 15, mood, genre } = {}) {
  const j = await get("/v0/tracks/search", { term, limit, moods: mood, genres: genre });
  const tracks = j.tracks || j.data || j.items || [];
  return tracks.map((t) => ({
    id: t.id,
    title: t.title,
    artist: (t.mainArtists || t.artists || []).map((a) => a.name || a).join(", ") || t.artist || "",
    bpm: t.bpm,
    length: t.length ?? t.durationMs / 1000,
    moods: (t.moods || []).map((m) => m.name || m).join(", "),
    previewOnly: t.isPreviewOnly,
  }));
}

export async function trackInfo(trackId) {
  try {
    const t = await get(`/v0/tracks/${encodeURIComponent(trackId)}`);
    const a = (t.mainArtists || t.artists || []).map((x) => x.name || x).join(", ");
    return { title: t.title, artist: a };
  } catch {
    return {};
  }
}

/** Download a track as high-quality MP3 to `dest`. */
export async function pullTrack(trackId, dest) {
  log(`Fetching download link for Epidemic Sound track ${trackId}…`);
  const j = await get(`/v0/tracks/${encodeURIComponent(trackId)}/download`, { format: "mp3", quality: "high" });
  const url = j.url || j.downloadUrl || j.link;
  if (!url) fail(`No download URL returned (premium track without a subscribed EPIDEMIC_USER_ID?): ${JSON.stringify(j).slice(0, 200)}`);
  await download(url, dest);
  ok(`Saved music → ${dest}`);
  return dest;
}
