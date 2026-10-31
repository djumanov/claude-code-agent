# Setup guide: step by step

This guide takes you from nothing installed to a finished, mixed MP4. Plan for about 20 minutes the first time.

## How the pieces fit

```
 Tella ──(record)──► raw/recording.mp4 ─┐
                                        ▼
                          FFmpeg  "prep"     trim dead air · 1080p30 · denoise · level voice
                                        ▼
                          HyperFrames "compose + render"
                                     intro card · lower-third · outro/CTA  (HTML + GSAP → MP4)
                                        ▼
 Epidemic Sound ──► music/track.mp3 ──► FFmpeg "finish"
                                     music ducks under voice · −14 LUFS · 9:16 copy · thumbnail
                                        ▼
                               out/<project>.mp4  (+ -vertical.mp4, -thumb.jpg)
```

| Tool | Job in this system |
|---|---|
| **Tella** | Record your screen and camera. Clean up takes in Tella's own editor. |
| **FFmpeg** | Normalizes the raw recording, then does the final audio mix and delivery encodes. |
| **HyperFrames** | Renders branded motion graphics (intro, lower-third, outro) around your recording. Compositions are HTML + GSAP. |
| **Epidemic Sound** | Licensed background music. The mix lowers it automatically whenever you speak. |

---

## Step 1: Install the prerequisites

You need **Node.js 22+**, **FFmpeg**, and **Google Chrome**. HyperFrames uses Chrome to render frames.

**macOS** (with [Homebrew](https://brew.sh)):
```bash
brew install node ffmpeg
brew install --cask google-chrome
```

**Windows** (PowerShell, using winget). WSL2 with the Linux steps also works.
```powershell
winget install OpenJS.NodeJS.LTS Gyan.FFmpeg Google.Chrome
```

**Ubuntu/Debian:**
```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs ffmpeg
```

Check the versions:
```bash
node -v      # v22 or newer
ffmpeg -version
```

## Step 2: Get the system and install dependencies

```bash
git clone https://github.com/djumanov/claude-code-agent.git video-system
cd video-system
npm install            # installs HyperFrames + GSAP locally
npm link               # optional: makes the `vedit` command available everywhere
```

If you skip `npm link`, run commands as `node bin/vedit.mjs …` or `npm run vedit -- …`.

## Step 3: Connect Tella (optional, recommended)

1. Record your video at [tella.com](https://www.tella.com) as usual.
2. In Tella, go to **Settings → API** and create an API key.
3. Copy the env template and paste in the key:
   ```bash
   cp .env.example .env
   ```
   ```
   TELLA_API_KEY=tella_xxxxxxxxx
   ```

**Without an API key:** in Tella, open the video, click **Download → MP4 (1080p)**, then run `vedit import <project> ~/Downloads/your-video.mp4`.

## Step 4: Connect Epidemic Sound

The **Partner API** is only for companies with a partner agreement. Most creators will use **manual mode**.

**Manual mode (most people):**
1. Log in at [epidemicsound.com](https://www.epidemicsound.com) with an active subscription.
2. Find a track and click **Download → MP3** (or WAV).
3. Run `vedit music add <project> ~/Downloads/track.mp3 --credit "Track Name – Artist"`.
4. Clear your channel in your Epidemic Sound account settings so you don't get copyright claims on YouTube.

**Partner API mode (if you have Developer Portal credentials):** add these to `.env`:
```
EPIDEMIC_ACCESS_KEY_ID=...
EPIDEMIC_ACCESS_KEY_SECRET=...
EPIDEMIC_USER_ID=...        # the subscribed user; needed for premium tracks
```
Then `vedit music search "upbeat tech"` and `vedit music pull <project> <trackId>` work.
> The search and user-token paths in `lib/epidemic.mjs` follow the documented `/v0/partner-token` → `/v0/tracks/{id}/download` flow. Check them against the OpenAPI spec in your Developer Portal and adjust that one file if anything differs.

## Step 5: Check everything

```bash
vedit doctor
```
FFmpeg, Node, HyperFrames, and Chrome should all show ✓. whisper, TTS, MusicGen, and Docker are optional.

## Step 6: Make your first video

```bash
# 1. Create a project
vedit new launch-demo --title "Introducing Acme 2.0"

# 2. Brand it: edit projects/launch-demo/project.json (see table below)

# 3. Bring in footage (pick one)
vedit tella list                          # find the video ID
vedit tella pull launch-demo <videoId>
#   or: vedit import launch-demo ~/Downloads/recording.mp4

# 4. Add music (pick one)
vedit music add launch-demo ~/Downloads/track.mp3 --credit "Sunrise – Artist"
#   or: vedit music pull launch-demo <trackId>

# 5. Quick draft to check timing
vedit build launch-demo --draft

# 6. Final quality
vedit build launch-demo
```

You end up with:
```
projects/launch-demo/out/
  launch-demo.mp4            16:9 master, −14 LUFS (YouTube/LinkedIn)
  launch-demo-vertical.mp4   9:16 for Shorts/Reels/TikTok
  launch-demo-thumb.jpg      thumbnail frame from the intro
```

### Running the steps one at a time

```bash
vedit prep launch-demo       # raw → build/main.mp4
vedit compose launch-demo    # writes build/hf/index.html (HyperFrames project)
vedit preview launch-demo    # live preview in the browser; tweak, then…
vedit render launch-demo     # build/visual.mp4 (picture only)
vedit finish launch-demo     # audio mix + exports → out/
```

If you hand-edit `build/hf/index.html`, run `render` + `finish` and skip `compose`. Otherwise `compose` overwrites your edits.

## project.json reference

| Key | Default | What it does |
|---|---|---|
| `title`, `subtitle` | from name | Intro card text |
| `speaker.name`, `speaker.role` | empty | Lower-third. Leave the name empty to hide it. |
| `outroTitle`, `cta` | "Thanks for watching", "Subscribe for more" | Outro card |
| `intro`, `outro` | 3, 4 | Card lengths in seconds. Set 0 to skip a card. |
| `brand.bg/ink/accent/font` | dark / white / violet / Inter | Colors + Google Font name |
| `lowerThird.at`, `.duration` | 1, 5 | Seconds after the recording starts |
| `prep.trimSilence` | true | Cut dead air at the start and end |
| `prep.denoise` | true | FFT noise reduction on the voice |
| `prep.trim` | — | `{ "start": 4.2, "end": 95 }`: manual cut that overrides auto-trim |
| `music.volume` | 0.18 | Music bed level before ducking |
| `music.duck` | true | Sidechain-compress the music under the voice |
| `music.credit` | — | Shown on the outro as "Music: … · Epidemic Sound" |
| `output.quality` | delivery | HyperFrames quality: draft / looks / delivery |
| `output.vertical`, `.thumbnail` | true | Extra exports |
| `output.loudness` | −14 | Target LUFS (−14 suits YouTube/Spotify, −16 suits podcasts) |

## Using it with Claude Code

HyperFrames ships with agent skills. To let Claude design custom animations in `build/hf/`, run:
```bash
npx skills add heygen-com/hyperframes
```
Then ask, for example: *"In projects/launch-demo/build/hf, add a kinetic-type section listing three features at 0:20"*. `CLAUDE.md` in this repo tells Claude how the pipeline works.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ffmpeg is not installed` | Redo Step 1. On Windows, open a new terminal so PATH updates. |
| Render fails with a Chrome or browser error | `npx hyperframes doctor`. Install Chrome, or render with `npx hyperframes render build/hf --docker`. |
| Render is slow | Use `--draft` while iterating. Final renders run at about 1× real time on a laptop. |
| Music too loud or quiet | Change `music.volume` (0.10–0.25), then run `vedit finish` only. No re-render needed. |
| Speech clipped at the start | Set `prep.trimSilence: false`, or set `prep.trim` manually. |
| Tella 401/403 | Regenerate the API key. Viewers need downloads enabled on the video. |
| Epidemic "premium" / no download URL | Set `EPIDEMIC_USER_ID` for a subscribed user, or use manual mode. |
