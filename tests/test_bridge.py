"""Ko'prik (bepul versiya rejimi): Resolve ichidagi skript + HTTP klient birgalikda."""

from __future__ import annotations

import importlib.util
import os
import threading
from pathlib import Path

import pytest

from davinci_resolve_mcp import connection, server
from test_server import FakeResolve

BRIDGE = Path(__file__).resolve().parents[1] / "bridge" / "DaVinci_MCP_Bridge.py"


def _load_bridge():
    os.environ["DAVINCI_BRIDGE_TEST"] = "1"
    spec = importlib.util.spec_from_file_location("dvr_bridge", BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def bridged(monkeypatch):
    fake = FakeResolve()
    fake.EXPORT_AAF = 7  # konstanta
    httpd = _load_bridge().make_server(fake, port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setattr(connection.BridgeClient.__init__, "__defaults__", (f"http://127.0.0.1:{port}", 30))
    monkeypatch.setenv("DAVINCI_MCP_MODE", "bridge")
    connection.reset_connection()
    yield fake
    httpd.shutdown()
    connection.reset_connection()


def test_status_via_bridge(bridged):
    st = server.resolve_status()
    assert st["connection"] == "bridge"
    assert st["project"] == "Demo" and st["timeline"] == "Main"


def test_constants_and_objects_roundtrip(bridged):
    r = connection.get_resolve()
    assert r.EXPORT_AAF == 7
    tl = r.GetProjectManager().GetCurrentProject().GetCurrentTimeline()
    assert tl.GetName() == "Main"


def test_edit_tools_via_bridge(bridged):
    server.append_clips([{"name": "city", "in_sec": 1, "out_sec": 3, "at_sec": 4}])
    info = bridged.pm.project.mp.appended[0]
    assert info["mediaPoolItem"].GetName() == "city.mov"  # obyekt ko'prik orqali qaytib keldi
    assert info["recordFrame"] == 90100
    server.add_marker(2.0, name="Hook", color="Red")
    assert server.get_markers()[0]["frame"] == 50  # int kalitlar saqlanadi
    server.delete_clips("video", 1, [2])
    assert bridged.pm.project.timeline.deleted[0][0].GetName() == "b.mp4"


def test_bridge_error_is_reported(bridged):
    with pytest.raises(connection.ResolveError, match="Resolve xatosi"):
        connection.get_resolve().GetProjectManager().NoSuchMethod()


def test_bridge_not_running(monkeypatch):
    monkeypatch.setattr(connection.BridgeClient.__init__, "__defaults__", ("http://127.0.0.1:1", 2))
    monkeypatch.setenv("DAVINCI_MCP_MODE", "bridge")
    connection.reset_connection()
    with pytest.raises(connection.ResolveError, match="DaVinci_MCP_Bridge"):
        connection.get_resolve()
    connection.reset_connection()
