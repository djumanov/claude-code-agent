"""DaVinci Resolve MCP server.

Claude (Desktop yoki Claude Code) shu server orqali DaVinci Resolve ni boshqaradi:
loyiha ochish, media import, timeline yig'ish, kesish, marker, titr, rang (LUT/CDL),
subtitr va render.

Ishga tushirish:  ``python -m davinci_resolve_mcp``  (stdio transport)
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import sys
import time
import traceback
from typing import Any

from mcp.server.fastmcp import FastMCP

from .connection import ResolveError, connection_mode, get_resolve

logging.basicConfig(
    level=os.environ.get("DAVINCI_MCP_LOG", "INFO"),
    stream=sys.stderr,  # stdout MCP protokoli uchun band, unga hech narsa yozmaslik kerak
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

mcp = FastMCP(
    "davinci-resolve",
    instructions=(
        "Tools to edit video in a running DaVinci Resolve instance. "
        "Typical workflow: resolve_status -> open/create project -> import_media -> "
        "create_timeline / append_clips -> trim, markers, titles, color -> render. "
        "Track and item indexes are 1-based; use get_timeline_info to see them. "
        "Times can be given in seconds; they are converted to frames with the timeline fps. "
        "If something is not covered by a dedicated tool, use execute_resolve_script."
    ),
)

PAGES = ["media", "cut", "edit", "fusion", "color", "fairlight", "deliver"]
TRACK_TYPES = ["video", "audio", "subtitle"]
MARKER_COLORS = [
    "Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple", "Fuchsia",
    "Rose", "Lavender", "Sky", "Mint", "Lemon", "Sand", "Cocoa", "Cream",
]
CLIP_COLORS = [
    "Orange", "Apricot", "Yellow", "Lime", "Olive", "Green", "Teal", "Navy",
    "Blue", "Purple", "Violet", "Pink", "Tan", "Beige", "Brown", "Chocolate",
]


# --------------------------------------------------------------------------- #
# Yordamchi funksiyalar
# --------------------------------------------------------------------------- #

def _project_manager() -> Any:
    pm = get_resolve().GetProjectManager()
    if pm is None:
        raise ResolveError("ProjectManager olinmadi")
    return pm


def _project() -> Any:
    project = _project_manager().GetCurrentProject()
    if project is None:
        raise ResolveError("Ochiq loyiha yo'q. Avval open_project yoki create_project ishlating.")
    return project


def _media_pool() -> Any:
    return _project().GetMediaPool()


def _timeline() -> Any:
    tl = _project().GetCurrentTimeline()
    if tl is None:
        raise ResolveError("Joriy timeline yo'q. create_timeline yoki set_current_timeline ishlating.")
    return tl


def _parse_fps(value: Any) -> float:
    try:
        return float(str(value).split()[0])
    except (ValueError, IndexError):
        return 24.0


def _timeline_fps(tl: Any | None = None) -> float:
    tl = tl or _timeline()
    fps = tl.GetSetting("timelineFrameRate") or _project().GetSetting("timelineFrameRate")
    return _parse_fps(fps)


def _sec_to_frames(seconds: float, fps: float) -> int:
    return int(round(seconds * fps))


def _frames_to_tc(frames: int, fps: float) -> str:
    base = max(1, int(round(fps)))
    f = frames % base
    s = frames // base
    return f"{s // 3600:02d}:{(s // 60) % 60:02d}:{s % 60:02d}:{f:02d}"


def _check_choice(value: str, choices: list[str], what: str) -> str:
    for c in choices:
        if c.lower() == value.lower():
            return c
    raise ResolveError(f"Noto'g'ri {what}: {value!r}. Mumkin: {', '.join(choices)}")


def _iter_folders(folder: Any, path: str = ""):
    name = folder.GetName()
    full = f"{path}/{name}" if path else name
    yield full, folder
    for sub in folder.GetSubFolderList() or []:
        yield from _iter_folders(sub, full)


def _find_folder(bin_path: str | None) -> Any:
    root = _media_pool().GetRootFolder()
    if not bin_path:
        return root
    wanted = bin_path.strip("/").lower()
    for full, folder in _iter_folders(root):
        rel = full.split("/", 1)[1] if "/" in full else ""
        if wanted in (full.lower(), rel.lower(), folder.GetName().lower()):
            return folder
    raise ResolveError(f"Bin topilmadi: {bin_path}")


def _all_clips() -> list[tuple[str, Any]]:
    out = []
    for full, folder in _iter_folders(_media_pool().GetRootFolder()):
        for clip in folder.GetClipList() or []:
            out.append((full, clip))
    return out


def _find_clip(name: str) -> Any:
    clips = _all_clips()
    for _, clip in clips:
        if clip.GetName() == name:
            return clip
    for _, clip in clips:
        if clip.GetName().lower() == name.lower():
            return clip
    matches = [c for _, c in clips if name.lower() in c.GetName().lower()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ResolveError(
            f"{name!r} bir nechta klipga mos keldi: {[c.GetName() for c in matches[:10]]}"
        )
    raise ResolveError(f"Media Pool da klip topilmadi: {name}")


def _clip_info(clip: Any) -> dict[str, Any]:
    props = clip.GetClipProperty() or {}
    return {
        "name": clip.GetName(),
        "type": props.get("Type"),
        "duration": props.get("Duration"),
        "fps": props.get("FPS"),
        "resolution": props.get("Resolution"),
        "file_path": props.get("File Path"),
    }


def _find_timeline(name: str) -> Any:
    project = _project()
    for i in range(1, int(project.GetTimelineCount() or 0) + 1):
        tl = project.GetTimelineByIndex(i)
        if tl and tl.GetName() == name:
            return tl
    raise ResolveError(f"Timeline topilmadi: {name}")


def _item(track_type: str, track_index: int, item_index: int) -> Any:
    track_type = _check_choice(track_type, TRACK_TYPES, "track_type")
    items = _timeline().GetItemListInTrack(track_type, track_index) or []
    if not 1 <= item_index <= len(items):
        raise ResolveError(
            f"{track_type} {track_index}-trekda {item_index}-element yo'q (jami {len(items)} ta)."
        )
    return items[item_index - 1]


def _item_info(item: Any, idx: int, fps: float) -> dict[str, Any]:
    start, end = item.GetStart(), item.GetEnd()
    info = {
        "index": idx,
        "name": item.GetName(),
        "start_frame": start,
        "end_frame": end,
        "duration_frames": item.GetDuration(),
        "duration_sec": round(item.GetDuration() / fps, 3),
        "start_tc": _frames_to_tc(start, fps),
    }
    with contextlib.suppress(Exception):
        info["source_in"] = item.GetLeftOffset()
    with contextlib.suppress(Exception):
        mpi = item.GetMediaPoolItem()
        if mpi is not None:
            info["media"] = mpi.GetName()
    return info


# --------------------------------------------------------------------------- #
# Holat va sahifalar
# --------------------------------------------------------------------------- #

@mcp.tool()
def resolve_status() -> dict[str, Any]:
    """Show Resolve version, current page, open project and current timeline."""
    resolve = get_resolve()
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    out: dict[str, Any] = {
        "product": resolve.GetProductName(),
        "version": resolve.GetVersionString(),
        "page": resolve.GetCurrentPage(),
        "connection": connection_mode(),
        "project": project.GetName() if project else None,
    }
    if project:
        tl = project.GetCurrentTimeline()
        out["timeline"] = tl.GetName() if tl else None
        out["timeline_count"] = project.GetTimelineCount()
        out["frame_rate"] = project.GetSetting("timelineFrameRate")
        out["resolution"] = (
            f"{project.GetSetting('timelineResolutionWidth')}x"
            f"{project.GetSetting('timelineResolutionHeight')}"
        )
    return out


@mcp.tool()
def open_page(page: str) -> str:
    """Switch Resolve page: media, cut, edit, fusion, color, fairlight, deliver."""
    page = _check_choice(page, PAGES, "sahifa")
    if not get_resolve().OpenPage(page):
        raise ResolveError(f"{page} sahifasi ochilmadi")
    return f"{page} sahifasi ochildi"


# --------------------------------------------------------------------------- #
# Loyihalar
# --------------------------------------------------------------------------- #

@mcp.tool()
def list_projects() -> list[str]:
    """List projects in the current project-manager folder."""
    return list(_project_manager().GetProjectListInCurrentFolder() or [])


@mcp.tool()
def open_project(name: str) -> str:
    """Open an existing project by name."""
    if not _project_manager().LoadProject(name):
        raise ResolveError(f"Loyiha ochilmadi: {name}")
    return f"Loyiha ochildi: {name}"


@mcp.tool()
def create_project(
    name: str,
    frame_rate: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> str:
    """Create and open a new project. Optionally set timeline fps (e.g. "25", "29.97") and resolution (e.g. 1920x1080, 1080x1920 for vertical)."""
    project = _project_manager().CreateProject(name)
    if project is None:
        raise ResolveError(f"Loyiha yaratilmadi (nom band bo'lishi mumkin): {name}")
    if frame_rate:
        project.SetSetting("timelineFrameRate", str(frame_rate))
    if width and height:
        project.SetSetting("timelineResolutionWidth", str(width))
        project.SetSetting("timelineResolutionHeight", str(height))
    return f"Loyiha yaratildi: {name}"


@mcp.tool()
def save_project() -> str:
    """Save the current project."""
    project = _project()
    if not _project_manager().SaveProject():
        raise ResolveError("Loyiha saqlanmadi")
    return f"Saqlandi: {project.GetName()}"


@mcp.tool()
def get_project_settings(keys: list[str] | None = None) -> dict[str, Any]:
    """Read project settings. Without keys returns all settings."""
    project = _project()
    if keys:
        return {k: project.GetSetting(k) for k in keys}
    return dict(project.GetSetting() or {})


@mcp.tool()
def set_project_setting(name: str, value: str) -> str:
    """Set a project setting, e.g. timelineFrameRate, timelineResolutionWidth, timelineResolutionHeight."""
    if not _project().SetSetting(name, str(value)):
        raise ResolveError(f"Sozlama o'rnatilmadi: {name}={value}")
    return f"{name} = {value}"


# --------------------------------------------------------------------------- #
# Media Pool
# --------------------------------------------------------------------------- #

@mcp.tool()
def import_media(paths: list[str], bin_name: str | None = None) -> list[dict[str, Any]]:
    """Import files or whole folders (from the user's computer) into the Media Pool, optionally into a bin (created if missing)."""
    mp = _media_pool()
    if bin_name:
        try:
            folder = _find_folder(bin_name)
        except ResolveError:
            folder = mp.AddSubFolder(mp.GetRootFolder(), bin_name)
        mp.SetCurrentFolder(folder)
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise ResolveError(f"Fayl/papka topilmadi: {missing}")
    clips = get_resolve().GetMediaStorage().AddItemListToMediaPool(paths) or []
    if not clips:
        raise ResolveError("Hech narsa import qilinmadi (format qo'llab-quvvatlanmasligi mumkin)")
    return [_clip_info(c) for c in clips]


@mcp.tool()
def list_media_pool(bin_path: str | None = None, recursive: bool = True) -> list[dict[str, Any]]:
    """List clips in the Media Pool (whole pool or one bin)."""
    out = []
    folders = _iter_folders(_find_folder(bin_path)) if recursive else [(bin_path or "", _find_folder(bin_path))]
    for full, folder in folders:
        for clip in folder.GetClipList() or []:
            info = _clip_info(clip)
            info["bin"] = full
            out.append(info)
    return out


@mcp.tool()
def create_bin(name: str, parent_bin: str | None = None) -> str:
    """Create a bin (folder) in the Media Pool."""
    mp = _media_pool()
    if mp.AddSubFolder(_find_folder(parent_bin), name) is None:
        raise ResolveError(f"Bin yaratilmadi: {name}")
    return f"Bin yaratildi: {name}"


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #

@mcp.tool()
def list_timelines() -> list[dict[str, Any]]:
    """List all timelines in the project."""
    project = _project()
    current = project.GetCurrentTimeline()
    cur_name = current.GetName() if current else None
    out = []
    for i in range(1, int(project.GetTimelineCount() or 0) + 1):
        tl = project.GetTimelineByIndex(i)
        out.append({"index": i, "name": tl.GetName(), "current": tl.GetName() == cur_name})
    return out


@mcp.tool()
def create_timeline(name: str, clip_names: list[str] | None = None) -> str:
    """Create a timeline and make it current. If clip_names are given, the clips are placed one after another."""
    mp = _media_pool()
    if clip_names:
        tl = mp.CreateTimelineFromClips(name, [_find_clip(n) for n in clip_names])
    else:
        tl = mp.CreateEmptyTimeline(name)
    if tl is None:
        raise ResolveError(f"Timeline yaratilmadi (nom band bo'lishi mumkin): {name}")
    _project().SetCurrentTimeline(tl)
    return f"Timeline yaratildi: {name}"


@mcp.tool()
def set_current_timeline(name: str) -> str:
    """Make a timeline current by name."""
    if not _project().SetCurrentTimeline(_find_timeline(name)):
        raise ResolveError(f"Timeline tanlanmadi: {name}")
    return f"Joriy timeline: {name}"


@mcp.tool()
def duplicate_timeline(new_name: str) -> str:
    """Duplicate the current timeline (good before risky edits)."""
    tl = _timeline().DuplicateTimeline(new_name)
    if tl is None:
        raise ResolveError("Timeline nusxalanmadi")
    return f"Nusxa yaratildi: {new_name}"


@mcp.tool()
def get_timeline_info(include_items: bool = True) -> dict[str, Any]:
    """Describe current timeline: fps, start/end, tracks and their clips (1-based indexes)."""
    tl = _timeline()
    fps = _timeline_fps(tl)
    start, end = tl.GetStartFrame(), tl.GetEndFrame()
    info: dict[str, Any] = {
        "name": tl.GetName(),
        "fps": fps,
        "start_frame": start,
        "end_frame": end,
        "duration_sec": round((end - start) / fps, 3),
        "start_timecode": tl.GetStartTimecode(),
        "current_timecode": tl.GetCurrentTimecode(),
        "tracks": {},
    }
    for tt in TRACK_TYPES:
        tracks = []
        for ti in range(1, int(tl.GetTrackCount(tt) or 0) + 1):
            t: dict[str, Any] = {"index": ti, "name": tl.GetTrackName(tt, ti)}
            items = tl.GetItemListInTrack(tt, ti) or []
            t["item_count"] = len(items)
            if include_items:
                t["items"] = [_item_info(it, i, fps) for i, it in enumerate(items, 1)]
            tracks.append(t)
        info["tracks"][tt] = tracks
    return info


@mcp.tool()
def append_clips(clips: list[dict[str, Any]]) -> str:
    """Append clips to the current timeline.

    Each entry: {"name": clip name (required), "in_sec": source start, "out_sec": source end,
    "track": track index (default 1), "at_sec": timeline position in seconds from timeline start
    (omit to append at the end), "media_type": 1=video only, 2=audio only (omit for both)}.
    """
    tl = _timeline()
    mp = _media_pool()
    tl_start = tl.GetStartFrame()
    tl_fps = _timeline_fps(tl)
    infos = []
    for c in clips:
        clip = _find_clip(c["name"])
        cfps = _parse_fps(clip.GetClipProperty("FPS") or tl_fps)
        info: dict[str, Any] = {"mediaPoolItem": clip}
        if "in_sec" in c or "out_sec" in c:
            info["startFrame"] = _sec_to_frames(float(c.get("in_sec", 0)), cfps)
            if "out_sec" in c:
                info["endFrame"] = _sec_to_frames(float(c["out_sec"]), cfps) - 1
            else:
                frames = clip.GetClipProperty("Frames")
                info["endFrame"] = int(frames) - 1 if frames else info["startFrame"] + int(10 * cfps)
        if "track" in c:
            info["trackIndex"] = int(c["track"])
        if "at_sec" in c:
            info["recordFrame"] = tl_start + _sec_to_frames(float(c["at_sec"]), tl_fps)
        if "media_type" in c:
            info["mediaType"] = int(c["media_type"])
        infos.append(info)
    added = mp.AppendToTimeline(infos) or []
    if not added:
        raise ResolveError("Kliplar timeline ga qo'shilmadi")
    return f"{len(added)} ta element timeline ga qo'shildi"


@mcp.tool()
def add_track(track_type: str = "video", audio_type: str = "stereo") -> str:
    """Add a video/audio/subtitle track. audio_type: mono, stereo, 5.1, adaptive1..."""
    track_type = _check_choice(track_type, TRACK_TYPES, "track_type")
    tl = _timeline()
    ok = tl.AddTrack(track_type, audio_type) if track_type == "audio" else tl.AddTrack(track_type)
    if not ok:
        raise ResolveError("Trek qo'shilmadi")
    return f"{track_type} trek qo'shildi (jami {tl.GetTrackCount(track_type)})"


@mcp.tool()
def delete_clips(track_type: str, track_index: int, item_indexes: list[int], ripple: bool = False) -> str:
    """Delete timeline items. ripple=True closes the gaps."""
    items = [_item(track_type, track_index, i) for i in item_indexes]
    if not _timeline().DeleteClips(items, ripple):
        raise ResolveError("Elementlar o'chirilmadi")
    return f"{len(items)} ta element o'chirildi"


@mcp.tool()
def set_clip_properties(track_type: str, track_index: int, item_index: int, properties: dict[str, Any]) -> dict[str, bool]:
    """Set Inspector properties of a timeline item, e.g. ZoomX, ZoomY, Pan, Tilt, RotationAngle,
    Opacity (0-100), CropLeft/Right/Top/Bottom, FlipX, FlipY, CompositeMode, RetimeProcess, Speed."""
    item = _item(track_type, track_index, item_index)
    return {k: bool(item.SetProperty(k, v)) for k, v in properties.items()}


@mcp.tool()
def get_clip_properties(track_type: str, track_index: int, item_index: int) -> dict[str, Any]:
    """Read all Inspector properties of a timeline item."""
    return dict(_item(track_type, track_index, item_index).GetProperty() or {})


@mcp.tool()
def set_clip_enabled(track_type: str, track_index: int, item_index: int, enabled: bool) -> str:
    """Enable or disable (mute) a timeline item."""
    if not _item(track_type, track_index, item_index).SetClipEnabled(enabled):
        raise ResolveError("Holat o'zgarmadi")
    return "yoqildi" if enabled else "o'chirildi"


@mcp.tool()
def set_clip_color(track_type: str, track_index: int, item_index: int, color: str) -> str:
    """Set clip color label (Orange, Blue, Green, ...)."""
    color = _check_choice(color, CLIP_COLORS, "rang")
    _item(track_type, track_index, item_index).SetClipColor(color)
    return f"Rang: {color}"


@mcp.tool()
def set_playhead(timecode: str | None = None, seconds: float | None = None) -> str:
    """Move the playhead to a timecode (HH:MM:SS:FF) or seconds from timeline start."""
    tl = _timeline()
    if timecode is None:
        if seconds is None:
            raise ResolveError("timecode yoki seconds bering")
        fps = _timeline_fps(tl)
        timecode = _frames_to_tc(tl.GetStartFrame() + _sec_to_frames(seconds, fps), fps)
    if not tl.SetCurrentTimecode(timecode):
        raise ResolveError(f"Playhead o'rnatilmadi: {timecode} (Edit/Cut/Color sahifasida bo'ling)")
    return f"Playhead: {timecode}"


# --------------------------------------------------------------------------- #
# Markerlar
# --------------------------------------------------------------------------- #

@mcp.tool()
def add_marker(
    seconds: float,
    name: str = "",
    note: str = "",
    color: str = "Blue",
    duration_sec: float = 0,
    track_type: str | None = None,
    track_index: int | None = None,
    item_index: int | None = None,
) -> str:
    """Add a marker at `seconds` from timeline start (or from clip start if a clip is given)."""
    color = _check_choice(color, MARKER_COLORS, "marker rangi")
    fps = _timeline_fps()
    target = (
        _item(track_type, track_index, item_index)
        if track_type and track_index and item_index
        else _timeline()
    )
    frame = _sec_to_frames(seconds, fps)
    duration = max(1, _sec_to_frames(duration_sec, fps))
    if not target.AddMarker(frame, color, name, note, duration):
        raise ResolveError("Marker qo'shilmadi (shu kadrda marker allaqachon bo'lishi mumkin)")
    return f"Marker qo'shildi: {seconds}s {color} {name}"


@mcp.tool()
def get_markers() -> list[dict[str, Any]]:
    """List markers of the current timeline."""
    fps = _timeline_fps()
    markers = _timeline().GetMarkers() or {}
    return [
        {"frame": f, "seconds": round(f / fps, 3), **m}
        for f, m in sorted(markers.items())
    ]


@mcp.tool()
def delete_markers(color: str = "All", seconds: float | None = None) -> str:
    """Delete markers: one at `seconds`, or all of a color ("All" = every marker)."""
    tl = _timeline()
    if seconds is not None:
        ok = tl.DeleteMarkerAtFrame(_sec_to_frames(seconds, _timeline_fps(tl)))
    else:
        ok = tl.DeleteMarkersByColor(color)
    return "Markerlar o'chirildi" if ok else "O'chiriladigan marker topilmadi"


# --------------------------------------------------------------------------- #
# Titrlar, generatorlar, subtitr, avtomatik tahrir
# --------------------------------------------------------------------------- #

@mcp.tool()
def add_text_title(text: str, at_seconds: float | None = None, font_size: float | None = None) -> str:
    """Insert a Fusion "Text+" title at the playhead (or at at_seconds) and set its text.
    The title goes on the highest video track at the playhead."""
    if at_seconds is not None:
        set_playhead(seconds=at_seconds)
    item = _timeline().InsertFusionTitleIntoTimeline("Text+")
    if item is None:
        raise ResolveError("Titr qo'shilmadi (Edit sahifasini oching va playhead ni tekshiring)")
    comp = item.GetFusionCompByIndex(1)
    tool = None
    if comp is not None:
        tools = comp.GetToolList(False, "TextPlus") or {}
        tool = next(iter(tools.values()), None) if isinstance(tools, dict) else None
    if tool is None:
        return "Titr qo'shildi, lekin matnni avtomatik o'rnatib bo'lmadi — Inspector da o'zgartiring"
    tool.SetInput("StyledText", text)
    if font_size is not None:
        tool.SetInput("Size", font_size)
    return f"Titr qo'shildi: {text!r}"


@mcp.tool()
def insert_title(title_name: str = "Text", at_seconds: float | None = None) -> str:
    """Insert a standard Edit-page title (e.g. "Text", "Scroll", "Lower Third") at the playhead."""
    if at_seconds is not None:
        set_playhead(seconds=at_seconds)
    if _timeline().InsertTitleIntoTimeline(title_name) is None:
        raise ResolveError(f"Titr qo'shilmadi: {title_name}")
    return f"Titr qo'shildi: {title_name}"


@mcp.tool()
def insert_generator(generator_name: str = "Solid Color", at_seconds: float | None = None) -> str:
    """Insert a generator (e.g. "Solid Color", "10 Step", "Grey Scale") at the playhead."""
    if at_seconds is not None:
        set_playhead(seconds=at_seconds)
    if _timeline().InsertGeneratorIntoTimeline(generator_name) is None:
        raise ResolveError(f"Generator qo'shilmadi: {generator_name}")
    return f"Generator qo'shildi: {generator_name}"


@mcp.tool()
def create_subtitles_from_audio(language: str = "auto", chars_per_line: int = 42) -> str:
    """Auto-generate subtitles from the timeline audio (Resolve 18.5+ Studio).
    language: auto, english, russian, turkish, spanish, german, french, ... (Uzbek is not supported by Resolve; use auto)."""
    resolve = get_resolve()
    settings: dict[Any, Any] = {}
    const = getattr(resolve, f"AUTO_CAPTION_{language.upper()}", None)
    lang_key = getattr(resolve, "SUBTITLE_LANGUAGE", None)
    if const is not None and lang_key is not None:
        settings[lang_key] = const
    cpl_key = getattr(resolve, "SUBTITLE_CHARS_PER_LINE", None)
    if cpl_key is not None:
        settings[cpl_key] = chars_per_line
    if not _timeline().CreateSubtitlesFromAudio(settings):
        raise ResolveError("Subtitr yaratilmadi (Studio versiya va 18.5+ kerak)")
    return "Subtitrlar yaratildi"


@mcp.tool()
def detect_scene_cuts() -> str:
    """Detect scene cuts in the current timeline and split clips there (Resolve 18.5+ Studio)."""
    if not _timeline().DetectSceneCuts():
        raise ResolveError("Sahna kesimlari aniqlanmadi")
    return "Sahna kesimlari bo'yicha bo'lindi"


@mcp.tool()
def build_timeline_from_folder(folder: str, timeline_name: str, extensions: list[str] | None = None) -> dict[str, Any]:
    """One step rough cut: import every media file of a folder (sorted by name) and put them on a new timeline."""
    if not os.path.isdir(folder):
        raise ResolveError(f"Papka topilmadi: {folder}")
    exts = tuple(e.lower() for e in (extensions or [
        ".mp4", ".mov", ".mxf", ".mkv", ".avi", ".braw", ".r3d", ".wav", ".mp3", ".png", ".jpg",
    ]))
    files = sorted(
        os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts)
    )
    if not files:
        raise ResolveError("Papkada mos media fayl yo'q")
    clips = get_resolve().GetMediaStorage().AddItemListToMediaPool(files) or []
    tl = _media_pool().CreateTimelineFromClips(timeline_name, clips)
    if tl is None:
        raise ResolveError("Timeline yaratilmadi")
    _project().SetCurrentTimeline(tl)
    return {"timeline": timeline_name, "clips": [c.GetName() for c in clips]}


# --------------------------------------------------------------------------- #
# Rang (Color)
# --------------------------------------------------------------------------- #

@mcp.tool()
def apply_lut(track_index: int, item_index: int, lut_path: str, node_index: int = 1) -> str:
    """Apply a LUT file (.cube) to a node of a video clip's grade."""
    item = _item("video", track_index, item_index)
    ok = False
    with contextlib.suppress(Exception):
        graph = item.GetNodeGraph()
        ok = bool(graph and graph.SetLUT(node_index, lut_path))
    if not ok:
        ok = bool(item.SetLUT(node_index, lut_path))
    if not ok:
        raise ResolveError("LUT qo'llanmadi (fayl yo'lini yoki LUT ro'yxatini tekshiring)")
    return f"LUT qo'llandi: {os.path.basename(lut_path)}"


@mcp.tool()
def set_cdl(
    track_index: int,
    item_index: int,
    slope: list[float] | None = None,
    offset: list[float] | None = None,
    power: list[float] | None = None,
    saturation: float = 1.0,
    node_index: int = 1,
) -> str:
    """Set CDL (slope/offset/power RGB + saturation) on a clip node — simple primary correction."""
    fmt = lambda v, d: " ".join(str(x) for x in (v or d))  # noqa: E731
    cdl = {
        "NodeIndex": str(node_index),
        "Slope": fmt(slope, [1, 1, 1]),
        "Offset": fmt(offset, [0, 0, 0]),
        "Power": fmt(power, [1, 1, 1]),
        "Saturation": str(saturation),
    }
    if not _item("video", track_index, item_index).SetCDL(cdl):
        raise ResolveError("CDL o'rnatilmadi")
    return "CDL o'rnatildi"


@mcp.tool()
def copy_grade(from_track: int, from_item: int, to_items: list[list[int]]) -> str:
    """Copy the grade of one clip to others. to_items: [[track, item], ...]."""
    src = _item("video", from_track, from_item)
    targets = [_item("video", t, i) for t, i in to_items]
    if not src.CopyGrades(targets):
        raise ResolveError("Grade nusxalanmadi")
    return f"Grade {len(targets)} ta klipga nusxalandi"


@mcp.tool()
def apply_grade_from_drx(drx_path: str, items: list[list[int]], mode: int = 0) -> str:
    """Apply a still/grade .drx file to clips [[track, item], ...]. mode: 0 no keyframes, 1 source TC, 2 start frames."""
    targets = [_item("video", t, i) for t, i in items]
    graph = None
    with contextlib.suppress(Exception):
        graph = _timeline().GetNodeGraph()
    ok = graph.ApplyGradeFromDRX(drx_path, mode, targets) if graph else _timeline().ApplyGradeFromDRX(drx_path, mode, targets)
    if not ok:
        raise ResolveError("DRX qo'llanmadi")
    return "Grade qo'llandi"


# --------------------------------------------------------------------------- #
# Import / eksport
# --------------------------------------------------------------------------- #

EXPORT_FORMATS = {
    "aaf": ("EXPORT_AAF", "EXPORT_AAF_NEW"),
    "edl": ("EXPORT_EDL", "EXPORT_NONE"),
    "fcpxml": ("EXPORT_FCPXML_1_10", "EXPORT_NONE"),
    "fcp7xml": ("EXPORT_FCP_7_XML", "EXPORT_NONE"),
    "drt": ("EXPORT_DRT", "EXPORT_NONE"),
    "otio": ("EXPORT_OTIO", "EXPORT_NONE"),
    "csv": ("EXPORT_TEXT_CSV", "EXPORT_NONE"),
}


@mcp.tool()
def export_timeline(file_path: str, fmt: str = "fcpxml") -> str:
    """Export the current timeline to a file: aaf, edl, fcpxml, fcp7xml, drt, otio, csv."""
    resolve = get_resolve()
    key = fmt.lower()
    if key not in EXPORT_FORMATS:
        raise ResolveError(f"Format: {', '.join(EXPORT_FORMATS)}")
    type_name, sub_name = EXPORT_FORMATS[key]
    ftype = getattr(resolve, type_name, None)
    sub = getattr(resolve, sub_name, None)
    if ftype is None:
        raise ResolveError(f"Bu Resolve versiyasi {fmt} ni qo'llamaydi")
    ok = _timeline().Export(file_path, ftype, sub) if sub is not None else _timeline().Export(file_path, ftype)
    if not ok:
        raise ResolveError("Eksport bo'lmadi")
    return f"Eksport qilindi: {file_path}"


@mcp.tool()
def import_timeline(file_path: str) -> str:
    """Import a timeline from AAF/EDL/XML/FCPXML/DRT/OTIO file."""
    tl = _media_pool().ImportTimelineFromFile(file_path)
    if tl is None:
        raise ResolveError("Timeline import qilinmadi")
    return f"Import qilindi: {tl.GetName()}"


# --------------------------------------------------------------------------- #
# Render (Deliver)
# --------------------------------------------------------------------------- #

@mcp.tool()
def list_render_presets() -> list[str]:
    """List render presets (e.g. YouTube - 1080p, H.264 Master)."""
    return list(_project().GetRenderPresetList() or [])


@mcp.tool()
def list_render_formats(format_name: str | None = None) -> dict[str, Any]:
    """List render formats, or codecs of one format (e.g. "mp4", "mov")."""
    project = _project()
    if format_name:
        return dict(project.GetRenderCodecs(format_name) or {})
    return dict(project.GetRenderFormats() or {})


@mcp.tool()
def render(
    output_dir: str,
    file_name: str,
    preset: str | None = None,
    format_name: str | None = None,
    codec: str | None = None,
    start_sec: float | None = None,
    end_sec: float | None = None,
    extra_settings: dict[str, Any] | None = None,
    wait: bool = False,
    timeout_sec: int = 3600,
) -> dict[str, Any]:
    """Render the current timeline.

    preset: render preset name (see list_render_presets), e.g. "YouTube - 1080p".
    format_name/codec: e.g. "mp4" + "H264" (see list_render_formats).
    start_sec/end_sec: render only a range (seconds from timeline start).
    extra_settings: raw SetRenderSettings keys (FormatWidth, FormatHeight, FrameRate, VideoQuality, ExportAudio...).
    wait=True blocks until rendering finishes.
    """
    project = _project()
    tl = _timeline()
    open_page("deliver")
    if preset and not project.LoadRenderPreset(preset):
        raise ResolveError(f"Preset yuklanmadi: {preset}")
    if format_name and codec and not project.SetCurrentRenderFormatAndCodec(format_name, codec):
        raise ResolveError(f"Format/kodek o'rnatilmadi: {format_name}/{codec}")
    os.makedirs(output_dir, exist_ok=True)
    settings: dict[str, Any] = {"TargetDir": output_dir, "CustomName": file_name}
    if start_sec is not None or end_sec is not None:
        fps = _timeline_fps(tl)
        start = tl.GetStartFrame()
        settings["SelectAllFrames"] = False
        settings["MarkIn"] = start + _sec_to_frames(start_sec or 0, fps)
        settings["MarkOut"] = (
            start + _sec_to_frames(end_sec, fps) - 1 if end_sec is not None else tl.GetEndFrame()
        )
    else:
        settings["SelectAllFrames"] = True
    settings.update(extra_settings or {})
    if not project.SetRenderSettings(settings):
        raise ResolveError(f"Render sozlamalari o'rnatilmadi: {settings}")
    job_id = project.AddRenderJob()
    if not job_id:
        raise ResolveError("Render navbatga qo'shilmadi")
    if not project.StartRendering([job_id], False):
        raise ResolveError("Render boshlanmadi")
    result: dict[str, Any] = {"job_id": job_id, "output": os.path.join(output_dir, file_name)}
    if wait:
        deadline = time.time() + timeout_sec
        while project.IsRenderingInProgress() and time.time() < deadline:
            time.sleep(2)
    result["status"] = project.GetRenderJobStatus(job_id)
    return result


@mcp.tool()
def render_status(job_id: str) -> dict[str, Any]:
    """Get render job status/progress."""
    project = _project()
    return {
        "in_progress": bool(project.IsRenderingInProgress()),
        **dict(project.GetRenderJobStatus(job_id) or {}),
    }


@mcp.tool()
def stop_render() -> str:
    """Stop rendering."""
    _project().StopRendering()
    return "Render to'xtatildi"


# --------------------------------------------------------------------------- #
# Universal: ixtiyoriy Python skript
# --------------------------------------------------------------------------- #

@mcp.tool()
def execute_resolve_script(code: str) -> dict[str, Any]:
    """Run Python code against the DaVinci Resolve API for anything not covered by other tools.

    Available names: resolve, project_manager, project, media_pool, timeline, fusion (may be None).
    print() output is returned; assign to `result` to return a value.
    Disable with env DAVINCI_MCP_ALLOW_SCRIPT=0.
    """
    if os.environ.get("DAVINCI_MCP_ALLOW_SCRIPT", "1") == "0":
        raise ResolveError("execute_resolve_script o'chirilgan (DAVINCI_MCP_ALLOW_SCRIPT=0)")
    resolve = get_resolve()
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    ns: dict[str, Any] = {
        "resolve": resolve,
        "project_manager": pm,
        "project": project,
        "media_pool": project.GetMediaPool() if project else None,
        "timeline": project.GetCurrentTimeline() if project else None,
        "fusion": resolve.Fusion() if hasattr(resolve, "Fusion") else None,
        "result": None,
    }
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<resolve-script>", "exec"), ns)  # noqa: S102 - foydalanuvchining o'z kompyuteri
    except Exception:
        return {"ok": False, "stdout": buf.getvalue(), "error": traceback.format_exc(limit=5)}
    res = ns.get("result")
    try:
        import json

        json.dumps(res)
    except (TypeError, ValueError):
        res = repr(res)
    return {"ok": True, "stdout": buf.getvalue(), "result": res}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
