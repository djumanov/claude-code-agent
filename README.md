# Claude → DaVinci Resolve (MCP)

Bu loyiha **Claude** ni kompyuteringizdagi **DaVinci Resolve** ga MCP orqali ulaydi.
Siz Claude ga oddiy tilda buyruq berasiz ("intro.mp4 ni 3-sekunddan 10-sekundgacha kesib timeline ga qo'y,
ustiga titr yoz va 1080p da render qil"), Claude esa Resolve ichida o'zi bajaradi.

```
Siz ──> Claude Desktop / Claude Code ──(MCP)──> davinci_resolve_mcp ──(Resolve Scripting API)──> DaVinci Resolve
```

## 1. Talablar

| Nima | Izoh |
|---|---|
| DaVinci Resolve 18 / 19 / 20 | Studio versiya tavsiya etiladi. Bepul versiyada tashqi skripting va AI funksiyalar (subtitr, sahna aniqlash) cheklangan bo'lishi mumkin. |
| Python 3.10 – 3.12, **64-bit** | [python.org](https://www.python.org/downloads/) dan. Windows da o'rnatishda **"Add Python to PATH"** belgisini qo'ying. |
| Claude Desktop yoki Claude Code | [claude.ai/download](https://claude.ai/download) |

## 2. DaVinci Resolve ni sozlash (bir marta)

1. Resolve ni oching → **DaVinci Resolve → Preferences → System → General**
2. **External scripting using** → **Local** ni tanlang
3. Resolve ni qayta ishga tushiring.

## 3. O'rnatish

Repo ni yuklab oling:

```bash
git clone https://github.com/djumanov/claude-code-agent.git
```

```bash
cd claude-code-agent
```

### Windows

```bash
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1
```

### macOS

```bash
bash scripts/install_mac.sh
```

Skript: `.venv` yaratadi → paketlarni o'rnatadi → Claude Desktop konfiguratsiyasiga
`davinci-resolve` serverini qo'shadi (eski konfiguratsiya `.bak` faylga saqlanadi).

So'ng **Claude Desktop ni to'liq yopib qayta oching** (tray/menyu bardan Quit). Chat oynasida
asboblar (🔨) belgisida `davinci-resolve` ko'rinishi kerak.

### Claude Code (terminal) ishlatsangiz

Windows:

```bash
claude mcp add davinci-resolve -- "C:\path\to\claude-code-agent\.venv\Scripts\python.exe" -m davinci_resolve_mcp
```

macOS:

```bash
claude mcp add davinci-resolve -- /path/to/claude-code-agent/.venv/bin/python -m davinci_resolve_mcp
```

### Qo'lda sozlash

`config/` papkasidagi namunadan foydalaning va uni quyidagi faylga yozing:

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

Resolve boshqa joyga o'rnatilgan bo'lsa, `env` qo'shing:

```json
"env": {
  "RESOLVE_SCRIPT_API": "C:\\ProgramData\\Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting",
  "RESOLVE_SCRIPT_LIB": "C:\\Program Files\\Blackmagic Design\\DaVinci Resolve\\fusionscript.dll"
}
```

## 4. Tekshirish

Resolve ochiq turganda Claude ga yozing:

> DaVinci holatini ko'rsat

Claude `resolve_status` ni chaqiradi va versiya, loyiha, timeline ni ko'rsatadi.

## 5. Buyruq namunalari

- *"Yangi 'Reels' loyiha yarat, 1080x1920, 30 fps"*
- *"D:\Video\Shoot papkasidagi barcha videolarni import qilib 'Rough cut' timeline yasa"*
- *"intro.mp4 ning 2–8 sekundini, keyin city.mov ning 0–5 sekundini timeline ga qo'y"*
- *"Timeline da nima borligini ko'rsat"*
- *"2-klipni 120% ga zoom qil va biroz chapga sur"*
- *"5-sekundda 'Obuna bo'ling!' degan titr qo'sh"*
- *"Har bir sahna boshiga qizil marker qo'y"*
- *"Hamma kliplarga D:\LUTs\film.cube LUT ni qo'lla"*
- *"Audiodan avtomatik subtitr yarat"*
- *"YouTube 1080p preset bilan D:\Export ga 'final' nomi bilan render qil va tugashini kut"*

## 6. Mavjud asboblar (tools)

| Bo'lim | Asboblar |
|---|---|
| Holat | `resolve_status`, `open_page` |
| Loyiha | `list_projects`, `open_project`, `create_project`, `save_project`, `get_project_settings`, `set_project_setting` |
| Media | `import_media`, `list_media_pool`, `create_bin`, `build_timeline_from_folder` |
| Timeline | `list_timelines`, `create_timeline`, `set_current_timeline`, `duplicate_timeline`, `get_timeline_info`, `append_clips`, `add_track`, `delete_clips`, `set_playhead` |
| Klip | `set_clip_properties`, `get_clip_properties`, `set_clip_enabled`, `set_clip_color` |
| Marker | `add_marker`, `get_markers`, `delete_markers` |
| Titr / AI | `add_text_title`, `insert_title`, `insert_generator`, `create_subtitles_from_audio`, `detect_scene_cuts` |
| Rang | `apply_lut`, `set_cdl`, `copy_grade`, `apply_grade_from_drx` |
| Import/eksport | `export_timeline` (fcpxml, edl, aaf, otio, drt, csv), `import_timeline` |
| Render | `list_render_presets`, `list_render_formats`, `render`, `render_status`, `stop_render` |
| Universal | `execute_resolve_script` — boshqa asboblar qamramagan har qanday ishni Resolve Python API orqali bajaradi |

Indekslar 1 dan boshlanadi (V1 trek, 1-klip). Vaqtlar sekundlarda beriladi va timeline fps bo'yicha kadrga aylantiriladi.

> `execute_resolve_script` Claude ga Resolve ichida ixtiyoriy Python kodini ishga tushirish imkonini beradi.
> Uni o'chirish uchun konfiguratsiyaga `"env": {"DAVINCI_MCP_ALLOW_SCRIPT": "0"}` qo'shing.

## 7. Muammolar

| Xato | Yechim |
|---|---|
| `DaVinciResolveScript moduli topilmadi` | Resolve o'rnatilgan yo'lni `RESOLVE_SCRIPT_API`/`RESOLVE_SCRIPT_LIB` orqali ko'rsating. |
| `DaVinci Resolve ga ulanib bo'lmadi` | Resolve ochiqmi? External scripting = **Local**mi? Python 64-bit va 3.10–3.12 mi? |
| Claude da asbob ko'rinmayapti | Claude Desktop ni to'liq yopib oching; logni tekshiring: Windows `%APPDATA%\Claude\logs\mcp-server-davinci-resolve.log`, macOS `~/Library/Logs/Claude/`. |
| Playhead / titr ishlamaydi | Resolve da **Edit** sahifasini oching. |
| Subtitr / sahna aniqlash ishlamaydi | Bu funksiyalar Resolve **Studio** 18.5+ talab qiladi. |

Qo'lda tekshirish (Resolve ochiq holda):

```bash
.venv/bin/python -c "from davinci_resolve_mcp.server import resolve_status; print(resolve_status())"
```

## 8. Dasturchilar uchun

```bash
pip install -e ".[dev]"
```

```bash
pytest
```

Testlar soxta Resolve obyektlari bilan ishlaydi, Resolve o'rnatilishi shart emas.
