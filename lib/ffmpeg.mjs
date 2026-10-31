// Everything FFmpeg does in the pipeline: probing, clean-up of the raw
// recording, and the final audio mix / delivery encodes.
import fs from "node:fs";
import path from "node:path";
import { run, log, ok, warn, fail } from "./util.mjs";

export async function probe(file) {
  const { stdout } = await run(
    "ffprobe",
    ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", file],
    { quiet: true },
  );
  const j = JSON.parse(stdout);
  const v = j.streams.find((s) => s.codec_type === "video");
  const a = j.streams.find((s) => s.codec_type === "audio");
  return {
    duration: Number(j.format.duration),
    width: v?.width,
    height: v?.height,
    hasVideo: !!v,
    hasAudio: !!a,
  };
}

/** Find where speech starts/ends so dead air at the head and tail can be cut. */
export async function detectSpeechBounds(file, duration, { noise = "-35dB", minSilence = 0.6 } = {}) {
  const { stderr } = await run(
    "ffmpeg",
    ["-hide_banner", "-nostats", "-i", file, "-af", `silencedetect=noise=${noise}:d=${minSilence}`, "-f", "null", "-"],
    { quiet: true },
  );
  const starts = [...stderr.matchAll(/silence_start: ([\d.]+)/g)].map((m) => Number(m[1]));
  const ends = [...stderr.matchAll(/silence_end: ([\d.]+)/g)].map((m) => Number(m[1]));
  let start = 0;
  let end = duration;
  if (starts.length && starts[0] < 0.1 && ends.length) start = Math.max(0, ends[0] - 0.25);
  const lastStart = starts.at(-1);
  if (lastStart !== undefined && lastStart > start && (ends.length < starts.length || ends.at(-1) >= duration - 0.1)) {
    end = Math.min(duration, lastStart + 0.4);
  }
  if (end - start < 1) return { start: 0, end: duration }; // all silent: don't trim
  return { start, end };
}

/**
 * Normalize a raw screen recording into a predictable edit master:
 * 1920x1080 (letterboxed if needed), constant 30 fps, H.264 + AAC 48 kHz,
 * cleaned-up and loudness-normalized voice.
 */
export async function prep(input, output, opts = {}) {
  const { width = 1920, height = 1080, fps = 30, trimSilence = true, denoise = true, trim } = opts;
  const info = await probe(input);
  if (!info.hasVideo) fail(`${input} has no video stream`);

  let start = trim?.start ?? 0;
  let end = trim?.end ?? info.duration;
  if (!trim && trimSilence && info.hasAudio) {
    ({ start, end } = await detectSpeechBounds(input, info.duration));
    if (start > 0 || end < info.duration) log(`Trimming dead air: ${start.toFixed(2)}s → ${end.toFixed(2)}s`);
  }

  const vf = [
    `scale=${width}:${height}:force_original_aspect_ratio=decrease`,
    `pad=${width}:${height}:(ow-iw)/2:(oh-ih)/2:color=black`,
    `fps=${fps}`,
    "format=yuv420p",
  ].join(",");
  const af = [
    "highpass=f=80",
    denoise && "afftdn=nf=-25",
    "loudnorm=I=-16:TP=-1.5:LRA=11",
    "aresample=48000",
  ]
    .filter(Boolean)
    .join(",");

  const args = ["-y", "-hide_banner", "-loglevel", "error", "-stats"];
  args.push("-ss", String(start), "-to", String(end), "-i", input);
  if (!info.hasAudio) args.push("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest");
  args.push("-vf", vf);
  if (info.hasAudio) args.push("-af", af);
  args.push(
    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
    "-c:a", "aac", "-b:a", "192k", "-ac", "2",
    "-movflags", "+faststart",
    output,
  );
  fs.mkdirSync(path.dirname(output), { recursive: true });
  await run("ffmpeg", args);
  const out = await probe(output);
  ok(`Prepped ${path.basename(output)} (${out.duration.toFixed(1)}s, ${out.width}x${out.height})`);
  return out;
}

/**
 * Final mix: HyperFrames-rendered picture + voice (offset by the intro) +
 * looped music bed that ducks under the voice, loudness-normalized for web.
 */
export async function finish({ visual, voice, music, output, introSeconds, musicVolume = 0.18, duck = true, fadeOut = 3, loudness = -14 }) {
  const { duration: total } = await probe(visual);
  const delayMs = Math.round(introSeconds * 1000);
  const T = total.toFixed(3);

  const args = ["-y", "-hide_banner", "-loglevel", "error", "-stats", "-i", visual, "-i", voice];
  if (music) args.push("-stream_loop", "-1", "-i", music);

  const g = [`[1:a]adelay=${delayMs}|${delayMs},apad=whole_dur=${T},atrim=0:${T}[vo]`];
  if (music) {
    g.push(
      `[2:a]atrim=0:${T},asetpts=N/SR/TB,aformat=sample_rates=48000:channel_layouts=stereo,` +
        `volume=${musicVolume},afade=t=in:d=1.5,afade=t=out:st=${Math.max(0, total - fadeOut).toFixed(3)}:d=${fadeOut}[mus]`,
    );
    if (duck) {
      g.push(`[vo]asplit=2[vo1][vosc]`);
      g.push(`[mus][vosc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=450:makeup=1[bed]`);
      g.push(`[vo1][bed]amix=inputs=2:duration=first:normalize=0[mix]`);
    } else {
      g.push(`[vo][mus]amix=inputs=2:duration=first:normalize=0[mix]`);
    }
  } else {
    g.push(`[vo]anull[mix]`);
  }
  g.push(`[mix]loudnorm=I=${loudness}:TP=-1:LRA=11,aresample=48000[aout]`);

  args.push(
    "-filter_complex", g.join(";"),
    "-map", "0:v", "-map", "[aout]",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
    "-t", T, "-movflags", "+faststart",
    output,
  );
  fs.mkdirSync(path.dirname(output), { recursive: true });
  await run("ffmpeg", args);
  ok(`Final video: ${output}`);
}

/** 9:16 version for Shorts/Reels/TikTok: full frame over a blurred fill. */
export async function vertical(input, output) {
  const vf =
    "split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:2,eq=brightness=-0.08[bg];" +
    "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p";
  await run("ffmpeg", [
    "-y", "-hide_banner", "-loglevel", "error", "-stats", "-i", input,
    "-filter_complex", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
    "-c:a", "copy", "-movflags", "+faststart", output,
  ]);
  ok(`Vertical video: ${output}`);
}

export async function thumbnail(input, output, at = 1.5) {
  await run("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", "-ss", String(at), "-i", input, "-frames:v", "1", "-q:v", "2", output]);
  ok(`Thumbnail: ${output}`);
}

export async function checkFfmpeg() {
  try {
    const { stdout } = await run("ffmpeg", ["-version"], { quiet: true });
    const { stdout: f } = await run("ffmpeg", ["-hide_banner", "-filters"], { quiet: true });
    const missing = ["loudnorm", "sidechaincompress", "silencedetect", "afftdn"].filter((x) => !f.includes(` ${x} `));
    if (missing.length) warn(`FFmpeg is missing filters: ${missing.join(", ")} — install a full build`);
    return stdout.split("\n")[0];
  } catch {
    return null;
  }
}
