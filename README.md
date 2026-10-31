# vedit: video editing system

Record in **Tella**, score with **Epidemic Sound**, add motion graphics with **HyperFrames**, and finish with **FFmpeg**. One command per step, or one command for everything:

```bash
vedit new my-video --title "My Video"
vedit tella pull my-video <tellaVideoId>        # or: vedit import my-video rec.mp4
vedit music add my-video track.mp3 --credit "Song – Artist"
vedit build my-video
# → projects/my-video/out/my-video.mp4, -vertical.mp4, -thumb.jpg
```

What `build` does:
1. **prep** (FFmpeg): trims dead air, conforms to 1080p30, denoises and levels the voice.
2. **compose** (HyperFrames): generates an HTML + GSAP composition with an intro card, a lower-third, and an outro/CTA in your brand colors.
3. **render** (HyperFrames): renders the composition to MP4.
4. **finish** (FFmpeg): mixes in the music, ducks it under the voice, normalizes to −14 LUFS, and exports a 9:16 copy and a thumbnail.

**→ Start with [SETUP.md](SETUP.md) for the step-by-step setup.**

```
bin/vedit.mjs      CLI
lib/ffmpeg.mjs     prep, audio mix, vertical + thumbnail exports
lib/compose.mjs    HyperFrames composition generator
lib/tella.mjs      Tella Public API (list, export, download)
lib/epidemic.mjs   Epidemic Sound Partner API (search, download)
projects/<name>/   project.json, raw/, music/, build/, out/   (git-ignored)
```
