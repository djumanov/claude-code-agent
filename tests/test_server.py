"""Soxta Resolve obyektlari bilan server tool larini tekshirish (Resolve o'rnatilmagan holda)."""

from __future__ import annotations

import asyncio

import pytest

from davinci_resolve_mcp import server
from davinci_resolve_mcp.connection import ResolveError


class FakeClip:
    def __init__(self, name, fps="25", frames=250):
        self.name, self.fps, self.frames = name, fps, frames

    def GetName(self):
        return self.name

    def GetClipProperty(self, key=None):
        props = {"Type": "Video", "FPS": self.fps, "Frames": str(self.frames),
                 "Duration": "00:00:10:00", "Resolution": "1920x1080", "File Path": f"/m/{self.name}"}
        return props if key is None else props.get(key)


class FakeFolder:
    def __init__(self, name, clips=(), subs=()):
        self.name, self.clips, self.subs = name, list(clips), list(subs)

    def GetName(self):
        return self.name

    def GetClipList(self):
        return self.clips

    def GetSubFolderList(self):
        return self.subs


class FakeItem:
    def __init__(self, name, start, end):
        self.name, self.start, self.end = name, start, end
        self.props, self.markers, self.enabled = {}, {}, True

    def GetName(self): return self.name
    def GetStart(self): return self.start
    def GetEnd(self): return self.end
    def GetDuration(self): return self.end - self.start
    def GetLeftOffset(self): return 0
    def GetMediaPoolItem(self): return None
    def SetProperty(self, k, v):
        self.props[k] = v
        return True
    def GetProperty(self, k=None): return self.props
    def SetClipEnabled(self, e):
        self.enabled = e
        return True
    def AddMarker(self, *a):
        self.markers[a[0]] = a
        return True


class FakeTimeline:
    def __init__(self, name):
        self.name = name
        self.items = {("video", 1): [FakeItem("a.mp4", 90000, 90250), FakeItem("b.mp4", 90250, 90500)]}
        self.markers = {}
        self.tc = None
        self.deleted = None

    def GetName(self): return self.name
    def GetSetting(self, k): return "25" if k == "timelineFrameRate" else None
    def GetStartFrame(self): return 90000
    def GetEndFrame(self): return 90500
    def GetStartTimecode(self): return "01:00:00:00"
    def GetCurrentTimecode(self): return "01:00:00:00"
    def GetTrackCount(self, t): return 1 if t == "video" else 0
    def GetTrackName(self, t, i): return f"{t[0].upper()}{i}"
    def GetItemListInTrack(self, t, i): return self.items.get((t, i), [])
    def SetCurrentTimecode(self, tc):
        self.tc = tc
        return True
    def AddMarker(self, frame, color, name, note, dur):
        self.markers[frame] = {"color": color, "name": name, "note": note, "duration": dur}
        return True
    def GetMarkers(self): return self.markers
    def DeleteClips(self, items, ripple):
        self.deleted = (items, ripple)
        return True


class FakeMediaPool:
    def __init__(self, root):
        self.root = root
        self.appended = None
        self.created = None

    def GetRootFolder(self): return self.root
    def AppendToTimeline(self, infos):
        self.appended = infos
        return [object()] * len(infos)
    def CreateEmptyTimeline(self, name):
        self.created = FakeTimeline(name)
        return self.created
    def CreateTimelineFromClips(self, name, clips):
        self.created = FakeTimeline(name)
        self.created.clips = clips
        return self.created


class FakeProject:
    def __init__(self):
        self.root = FakeFolder("Master", [FakeClip("intro.mp4")], [FakeFolder("Broll", [FakeClip("city.mov", fps="50")])])
        self.mp = FakeMediaPool(self.root)
        self.timeline = FakeTimeline("Main")
        self.render_settings = None

    def GetName(self): return "Demo"
    def GetMediaPool(self): return self.mp
    def GetCurrentTimeline(self): return self.timeline
    def SetCurrentTimeline(self, tl):
        self.timeline = tl
        return True
    def GetTimelineCount(self): return 1
    def GetTimelineByIndex(self, i): return self.timeline
    def GetSetting(self, k=None): return "25" if k == "timelineFrameRate" else "1920"
    def LoadRenderPreset(self, p): return True
    def SetRenderSettings(self, s):
        self.render_settings = s
        return True
    def AddRenderJob(self): return "job-1"
    def StartRendering(self, jobs, interactive): return True
    def IsRenderingInProgress(self): return False
    def GetRenderJobStatus(self, j): return {"JobStatus": "Complete", "CompletionPercentage": 100}


class FakePM:
    def __init__(self):
        self.project = FakeProject()

    def GetCurrentProject(self): return self.project
    def GetProjectListInCurrentFolder(self): return ["Demo", "Other"]
    def LoadProject(self, name): return name in ("Demo", "Other")


class FakeResolve:
    def __init__(self):
        self.pm = FakePM()
        self.page = "edit"

    def GetProjectManager(self): return self.pm
    def GetProductName(self): return "DaVinci Resolve Studio"
    def GetVersionString(self): return "19.1"
    def GetCurrentPage(self): return self.page
    def OpenPage(self, p):
        self.page = p
        return True


@pytest.fixture
def resolve(monkeypatch):
    r = FakeResolve()
    monkeypatch.setattr(server, "get_resolve", lambda: r)
    return r


def test_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert {"resolve_status", "import_media", "append_clips", "render", "execute_resolve_script"} <= names
    assert len(names) >= 35


def test_status(resolve):
    st = server.resolve_status()
    assert st["project"] == "Demo" and st["timeline"] == "Main" and st["version"] == "19.1"


def test_open_page_validation(resolve):
    assert "color" in server.open_page("Color")
    with pytest.raises(ResolveError):
        server.open_page("nope")


def test_media_pool_listing_and_find(resolve):
    clips = server.list_media_pool()
    assert [c["name"] for c in clips] == ["intro.mp4", "city.mov"]
    assert clips[1]["bin"] == "Master/Broll"
    assert server.list_media_pool("Broll")[0]["name"] == "city.mov"


def test_append_clips_converts_seconds(resolve):
    server.append_clips([{"name": "city", "in_sec": 1, "out_sec": 3, "track": 2, "at_sec": 4}])
    info = resolve.pm.project.mp.appended[0]
    assert info["startFrame"] == 50 and info["endFrame"] == 149  # 50 fps klip
    assert info["recordFrame"] == 90000 + 100  # 25 fps timeline
    assert info["trackIndex"] == 2


def test_timeline_info_and_clip_ops(resolve):
    info = server.get_timeline_info()
    assert info["duration_sec"] == 20.0
    assert info["tracks"]["video"][0]["items"][1]["name"] == "b.mp4"
    server.set_clip_properties("video", 1, 2, {"ZoomX": 1.2})
    assert resolve.pm.project.timeline.items[("video", 1)][1].props == {"ZoomX": 1.2}
    with pytest.raises(ResolveError):
        server.set_clip_properties("video", 1, 5, {})
    server.delete_clips("video", 1, [1], ripple=True)
    assert resolve.pm.project.timeline.deleted[1] is True


def test_markers_and_playhead(resolve):
    server.add_marker(2.0, name="Hook", color="red")
    assert resolve.pm.project.timeline.markers[50]["color"] == "Red"
    assert server.get_markers()[0]["seconds"] == 2.0
    server.set_playhead(seconds=61)
    assert resolve.pm.project.timeline.tc == "01:01:01:00"


def test_create_timeline_from_clips(resolve):
    server.create_timeline("Edit v1", ["intro.mp4", "city.mov"])
    assert resolve.pm.project.timeline.GetName() == "Edit v1"


def test_render_range(resolve, tmp_path):
    out = server.render(str(tmp_path), "final", preset="YouTube - 1080p", start_sec=0, end_sec=10, wait=True)
    s = resolve.pm.project.render_settings
    assert s["MarkIn"] == 90000 and s["MarkOut"] == 90249 and s["SelectAllFrames"] is False
    assert out["status"]["JobStatus"] == "Complete"
    assert resolve.page == "deliver"


def test_execute_script(resolve):
    out = server.execute_resolve_script("print(project.GetName())\nresult = timeline.GetName()")
    assert out == {"ok": True, "stdout": "Demo\n", "result": "Main"}
    bad = server.execute_resolve_script("1/0")
    assert bad["ok"] is False and "ZeroDivisionError" in bad["error"]
