# vedit: notes for Claude

Video pipeline CLI (Node 22, ESM, no runtime deps besides `hyperframes` + `gsap`).

- Entry: `bin/vedit.mjs`. Steps: `prep` → `compose` → `render` → `finish` (`build` runs all).
- Project state lives in `projects/<name>/project.json`. Media: `raw/` (Tella), `music/` (Epidemic Sound), `build/` (intermediates), `out/` (deliverables).
- `compose` regenerates `projects/<name>/build/hf/index.html` from `lib/compose.mjs`. It's a normal HyperFrames project, so for bespoke motion graphics edit that file directly (use the HyperFrames skills) and then run `vedit render` + `vedit finish`, not `compose`.
- The video in the composition is **muted on purpose**. Voice and music are mixed by FFmpeg in `finish` (voice delayed by `intro` seconds, music sidechain-ducked). Don't add `<audio>` to the composition for the voiceover.
- GSAP is vendored into `build/hf/assets/` so renders don't need CDN access. Keep `<script src="assets/gsap.min.js">`.
- Timeline must be registered as `window.__timelines["main"]`, root `data-composition-id="main"`.
- Check changes with: `node bin/vedit.mjs build <project> --draft` and inspect frames with ffmpeg.
