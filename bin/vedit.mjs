#!/usr/bin/env node
// vedit — Tella → FFmpeg → HyperFrames → FFmpeg video pipeline.
import fs from "node:fs";
import path from "node:path";
import {
  ROOT, PROJECTS, UserError, fail, findMedia, loadProject, log, ok, projectDir, run, saveProject, warn,
  VIDEO_EXTS, AUDIO_EXTS,
} from "../lib/util.mjs";
import * as ff from "../lib/ffmpeg.mjs";
import * as tella from "../lib/tella.mjs";
import * as es from "../lib/epidemic.mjs";
import { writeHyperframesProject } from "../lib/compose.mjs";

const HELP = `vedit — video editing pipeline (Tella + Epidemic Sound + HyperFrames + FFmpeg)

Setup
  vedit doctor                         Check FFmpeg, Node, HyperFrames, API keys

Projects
  vedit new <project> [--title "…"]    Create projects/<project>/ with project.json

Footage (Tella)
  vedit tella list                     List your Tella recordings (needs TELLA_API_KEY)
  vedit tella pull <project> <videoId> [--4k]   Export + download into raw/
  vedit import <project> <file>        Use a video you downloaded manually

Music (Epidemic Sound)
  vedit music search "<terms>" [--mood x] [--genre y]   Search (Partner API)
  vedit music pull <project> <trackId> Download a track into music/
  vedit music add <project> <file> [--credit "Track – Artist"]   Use a downloaded file

Edit
  vedit prep <project>                 FFmpeg: trim dead air, 1080p30, clean + level voice
  vedit compose <project>              Write the HyperFrames composition (build/hf)
  vedit preview <project>              Open HyperFrames live preview of the composition
  vedit render <project> [--draft]     HyperFrames: render picture → build/visual.mp4
  vedit finish <project>               FFmpeg: voice + ducked music, -14 LUFS → out/
  vedit build <project> [--draft]      prep → compose → render → finish in one go
`;

function parseArgs(argv) {
  const pos = [];
  const flags = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const [k, v] = a.slice(2).split("=");
      if (v !== undefined) flags[k] = v;
      else if (argv[i + 1] && !argv[i + 1].startsWith("--")) flags[k] = argv[++i];
      else flags[k] = true;
    } else pos.push(a);
  }
  return { pos, flags };
}

const DEFAULT_PROJECT = (name, title) => ({
  title: title || name.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
  subtitle: "",
  speaker: { name: "", role: "" },
  outroTitle: "Thanks for watching",
  cta: "Subscribe for more",
  intro: 3,
  outro: 4,
  fps: 30,
  brand: { bg: "#0b0b12", ink: "#ffffff", accent: "#7c5cff", font: "Inter" },
  lowerThird: { at: 1, duration: 5 },
  prep: { trimSilence: true, denoise: true },
  music: { file: null, volume: 0.18, duck: true, credit: "" },
  tella: { videoId: null },
  output: { quality: "delivery", vertical: true, thumbnail: true, loudness: -14 },
});

const cmds = {
  async doctor() {
    const node = process.versions.node;
    (Number(node.split(".")[0]) >= 22 ? ok : warn)(`Node ${node}${Number(node.split(".")[0]) < 22 ? " (HyperFrames needs 22+)" : ""}`);
    const v = await ff.checkFfmpeg();
    v ? ok(v) : warn("FFmpeg not found — install it (see SETUP.md step 1)");
    const hf = await run("npx", ["--no-install", "hyperframes", "--version"], { quiet: true, allowFail: true }).catch(() => ({ code: 1 }));
    hf.code === 0 ? ok(`HyperFrames ${hf.stdout.trim()}`) : warn("HyperFrames not installed locally — run: npm install");
    (process.env.TELLA_API_KEY ? ok : warn)(`TELLA_API_KEY ${process.env.TELLA_API_KEY ? "set" : "not set (manual mode: vedit import)"}`);
    const esSet = process.env.EPIDEMIC_ACCESS_KEY_ID && process.env.EPIDEMIC_ACCESS_KEY_SECRET;
    (esSet ? ok : warn)(`Epidemic Sound Partner API ${esSet ? "credentials set" : "not set (manual mode: vedit music add)"}`);
    if (hf.code === 0) await run("npx", ["hyperframes", "doctor"], { allowFail: true });
  },

  async new([name], flags) {
    const dir = projectDir(name);
    if (fs.existsSync(path.join(dir, "project.json"))) fail(`Project '${name}' already exists`);
    for (const d of ["raw", "music", "build", "out"]) fs.mkdirSync(path.join(dir, d), { recursive: true });
    fs.writeFileSync(path.join(dir, "project.json"), JSON.stringify(DEFAULT_PROJECT(name, flags.title), null, 2) + "\n");
    ok(`Created ${path.relative(ROOT, dir)}/  — edit project.json for title, speaker, brand colors`);
  },

  async import([name, file]) {
    const proj = loadProject(name);
    if (!file || !fs.existsSync(file)) fail(`File not found: ${file}`);
    const dest = proj.p("raw", "recording" + path.extname(file).toLowerCase());
    fs.copyFileSync(file, dest);
    ok(`Imported → ${path.relative(ROOT, dest)}`);
  },

  async tella([sub, ...rest], flags) {
    if (sub === "list") {
      const vids = await tella.listVideos();
      if (!vids.length) return log("No videos found.");
      for (const v of vids) console.log(`${v.id}\t${v.title}${v.duration ? `\t${Math.round(v.duration)}s` : ""}`);
    } else if (sub === "pull") {
      const [name, videoId] = rest;
      const proj = loadProject(name);
      const id = videoId || proj.cfg.tella?.videoId;
      if (!id) fail("Usage: vedit tella pull <project> <videoId>   (find IDs with: vedit tella list, or in the Tella share URL)");
      await tella.pullVideo(id, proj.p("raw", "recording.mp4"), { resolution: flags["4k"] ? "4k" : "1080p" });
      proj.cfg.tella = { ...proj.cfg.tella, videoId: id };
      saveProject(proj);
    } else fail("Usage: vedit tella list | vedit tella pull <project> <videoId>");
  },

  async music([sub, ...rest], flags) {
    if (sub === "search") {
      const term = rest.join(" ");
      if (!term) fail('Usage: vedit music search "upbeat corporate"');
      const tracks = await es.searchTracks(term, { mood: flags.mood, genre: flags.genre });
      if (!tracks.length) return log("No tracks found.");
      for (const t of tracks)
        console.log(`${t.id}\t${t.title} — ${t.artist}${t.bpm ? `\t${t.bpm} BPM` : ""}${t.length ? `\t${Math.round(t.length)}s` : ""}${t.previewOnly ? "\t(premium)" : ""}`);
    } else if (sub === "pull") {
      const [name, trackId] = rest;
      if (!trackId) fail("Usage: vedit music pull <project> <trackId>");
      const proj = loadProject(name);
      const dest = proj.p("music", `${trackId}.mp3`);
      await es.pullTrack(trackId, dest);
      const info = await es.trackInfo(trackId);
      proj.cfg.music = { ...proj.cfg.music, file: path.relative(proj.dir, dest), trackId, credit: info.title ? `${info.title} – ${info.artist}` : proj.cfg.music?.credit || "" };
      saveProject(proj);
    } else if (sub === "add") {
      const [name, file] = rest;
      const proj = loadProject(name);
      if (!file || !fs.existsSync(file)) fail(`File not found: ${file}`);
      const dest = proj.p("music", path.basename(file));
      if (path.resolve(file) !== dest) fs.copyFileSync(file, dest);
      proj.cfg.music = { ...proj.cfg.music, file: path.relative(proj.dir, dest), credit: flags.credit || proj.cfg.music?.credit || "" };
      saveProject(proj);
      ok(`Music set → ${path.relative(ROOT, dest)}`);
    } else fail('Usage: vedit music search "<terms>" | music pull <project> <trackId> | music add <project> <file>');
  },

  async prep([name]) {
    const proj = loadProject(name);
    const raw = findMedia(proj.p("raw"), VIDEO_EXTS);
    if (!raw) fail(`No video in ${proj.p("raw")}. Use 'vedit tella pull' or 'vedit import' first.`);
    log(`Prepping ${path.basename(raw)}`);
    await ff.prep(raw, proj.p("build", "main.mp4"), { fps: proj.cfg.fps, ...proj.cfg.prep });
  },

  async compose([name]) {
    const proj = loadProject(name);
    const main = proj.p("build", "main.mp4");
    if (!fs.existsSync(main)) fail("build/main.mp4 missing — run: vedit prep " + name);
    const info = await ff.probe(main);
    const hf = writeHyperframesProject(proj, main, info);
    ok(`Composition written → ${path.relative(ROOT, hf)}/index.html (${(proj.cfg.intro + info.duration + proj.cfg.outro).toFixed(1)}s)`);
    log(`Check it with: vedit preview ${name}   (then: vedit render ${name})`);
  },

  async preview([name]) {
    const proj = loadProject(name);
    await run("npx", ["hyperframes", "preview"], { cwd: proj.p("build", "hf") });
  },

  async render([name], flags) {
    const proj = loadProject(name);
    const hf = proj.p("build", "hf");
    if (!fs.existsSync(path.join(hf, "index.html"))) fail("No composition — run: vedit compose " + name);
    const quality = flags.draft ? "draft" : proj.cfg.output?.quality || "delivery";
    log(`Rendering with HyperFrames (quality: ${quality})…`);
    await run("npx", [
      "hyperframes", "render", hf,
      "-o", proj.p("build", "visual.mp4"),
      "--quality", quality,
      "--fps", String(proj.cfg.fps ?? 30),
      "--video-frame-format", "png", // crisp screen-recording text
    ]);
    ok("Rendered build/visual.mp4");
  },

  async finish([name]) {
    const proj = loadProject(name);
    const visual = proj.p("build", "visual.mp4");
    const voice = proj.p("build", "main.mp4");
    if (!fs.existsSync(visual)) fail("build/visual.mp4 missing — run: vedit render " + name);
    let music = proj.cfg.music?.file ? proj.p(proj.cfg.music.file) : findMedia(proj.p("music"), AUDIO_EXTS);
    if (music && !fs.existsSync(music)) fail(`Music file not found: ${music}`);
    if (!music) warn("No music in project — finishing with voice only");
    const out = proj.p("out", `${name}.mp4`);
    await ff.finish({
      visual, voice, music, output: out,
      introSeconds: Number(proj.cfg.intro ?? 3),
      musicVolume: proj.cfg.music?.volume ?? 0.18,
      duck: proj.cfg.music?.duck !== false,
      loudness: proj.cfg.output?.loudness ?? -14,
    });
    if (proj.cfg.output?.vertical) await ff.vertical(out, proj.p("out", `${name}-vertical.mp4`));
    if (proj.cfg.output?.thumbnail !== false) await ff.thumbnail(out, proj.p("out", `${name}-thumb.jpg`), Math.min(1.5, Number(proj.cfg.intro ?? 3) / 2) || 1);
  },

  async build([name], flags) {
    for (const step of ["prep", "compose", "render", "finish"]) {
      console.log(`\n\x1b[1m── ${step} ──\x1b[0m`);
      await cmds[step]([name], flags);
    }
    console.log(`\n\x1b[1mDone →\x1b[0m ${path.relative(ROOT, loadProject(name).p("out"))}/`);
  },
};

const { pos, flags } = parseArgs(process.argv.slice(2));
const [cmd, ...args] = pos;
if (!cmd || flags.help || cmd === "help" || !cmds[cmd]) {
  console.log(HELP);
  process.exit(cmd && !cmds[cmd] && cmd !== "help" ? 1 : 0);
}
fs.mkdirSync(PROJECTS, { recursive: true });
cmds[cmd](args, flags).catch((err) => {
  console.error(`\x1b[31m✗\x1b[0m ${err instanceof UserError ? err.message : err.stack}`);
  process.exit(1);
});
