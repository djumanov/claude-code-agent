"""DaVinci Resolve scripting API bilan ulanish.

DaVinci Resolve o'zining Python API sini ``DaVinciResolveScript`` moduli orqali
beradi. Bu modul Resolve o'rnatilgan papkada turadi, shuning uchun uni topish
uchun ``RESOLVE_SCRIPT_API`` va ``RESOLVE_SCRIPT_LIB`` muhit o'zgaruvchilari
kerak. Agar ular berilmagan bo'lsa, operatsion tizimga qarab standart yo'llar
ishlatiladi.
"""

from __future__ import annotations

import importlib
import json
import logging
import urllib.error
import urllib.request
import os
import sys
from typing import Any

log = logging.getLogger(__name__)


class ResolveError(RuntimeError):
    """Resolve bilan ishlashdagi tushunarli xato."""


def _default_paths() -> tuple[str, str]:
    if sys.platform.startswith("win"):
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        api = os.path.join(
            program_data,
            "Blackmagic Design",
            "DaVinci Resolve",
            "Support",
            "Developer",
            "Scripting",
        )
        lib = os.path.join(
            program_files, "Blackmagic Design", "DaVinci Resolve", "fusionscript.dll"
        )
    elif sys.platform == "darwin":
        api = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
        lib = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
    else:
        api = "/opt/resolve/Developer/Scripting"
        lib = "/opt/resolve/libs/Fusion/fusionscript.so"
    return api, lib


def configure_environment() -> None:
    """RESOLVE_SCRIPT_API / RESOLVE_SCRIPT_LIB ni o'rnatadi va Modules ni sys.path ga qo'shadi."""
    api_default, lib_default = _default_paths()
    api = os.environ.setdefault("RESOLVE_SCRIPT_API", api_default)
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", lib_default)
    modules = os.path.join(api, "Modules")
    if modules not in sys.path:
        sys.path.append(modules)


_resolve: Any = None
_mode: str | None = None

BRIDGE_URL = os.environ.get("DAVINCI_BRIDGE_URL", "http://127.0.0.1:8765")


# --------------------------------------------------------------------------- #
# Ko'prik (bepul versiya): Resolve ichidagi DaVinci_MCP_Bridge.py ga HTTP orqali
# --------------------------------------------------------------------------- #

class BridgeClient:
    def __init__(self, url: str = BRIDGE_URL, timeout: float = 600):
        self.url = url
        self.timeout = timeout

    def request(self, payload: dict[str, Any]) -> Any:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=data,
            headers={"Content-Type": "application/json", "X-Resolve-Bridge": "1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            raise ResolveError(
                "Resolve ichidagi ko'prik javob bermadi. Resolve da Workspace > Scripts > "
                f"DaVinci_MCP_Bridge ni ishga tushiring. ({exc})"
            ) from exc
        if not out.get("ok"):
            raise ResolveError(f"Resolve xatosi: {out.get('error')}")
        return self.decode(out.get("result"))

    def encode(self, value: Any) -> Any:
        if isinstance(value, RemoteObject):
            return {"__obj__": value._oid}
        if isinstance(value, (list, tuple)):
            return [self.encode(v) for v in value]
        if isinstance(value, dict):
            return {"__dict__": [[self.encode(k), self.encode(v)] for k, v in value.items()]}
        return value

    def decode(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self.decode(v) for v in value]
        if isinstance(value, dict):
            if "__obj__" in value:
                return RemoteObject(self, value["__obj__"], value.get("__type__", "obj"))
            if "__dict__" in value:
                return {self.decode(k): self.decode(v) for k, v in value["__dict__"]}
            return {k: self.decode(v) for k, v in value.items()}
        return value

    def ping(self) -> bool:
        try:
            return self.request({"op": "ping"}) == "pong"
        except ResolveError:
            return False


class RemoteObject:
    """Resolve ichidagi obyektning nusxasi: metod chaqiruvlari ko'prik orqali bajariladi."""

    def __init__(self, client: BridgeClient, oid: int, type_name: str = "Resolve"):
        self._client, self._oid, self._type = client, oid, type_name

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if any(ch.islower() for ch in name):  # metodlar: GetName, AddMarker ...
            return self._method(name)
        value = self._client.request({"op": "getattr", "obj": self._oid, "name": name})
        if isinstance(value, dict) and value.get("__callable__"):
            return self._method(name)
        return value  # konstantalar: EXPORT_AAF, SUBTITLE_LANGUAGE ...

    def _method(self, name: str):
        def call(*args: Any) -> Any:
            return self._client.request(
                {"op": "call", "obj": self._oid, "name": name, "args": self._client.encode(list(args))}
            )

        call.__name__ = name
        return call

    def __repr__(self) -> str:
        return f"<Remote {self._type} #{self._oid}>"


def _connect_bridge() -> Any | None:
    client = BridgeClient()
    if not client.ping():
        return None
    client.request({"op": "reset"})
    return RemoteObject(client, 0)


def connection_mode() -> str | None:
    return _mode


def _connect_native() -> Any:
    configure_environment()
    try:
        dvr = importlib.import_module("DaVinciResolveScript")
    except ImportError as exc:  # pragma: no cover - depends on local install
        raise ResolveError(
            "DaVinciResolveScript moduli topilmadi. DaVinci Resolve o'rnatilganini va "
            f"RESOLVE_SCRIPT_API to'g'ri ekanini tekshiring (hozir: {os.environ.get('RESOLVE_SCRIPT_API')}). "
            f"Xato: {exc}"
        ) from exc

    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        raise ResolveError("Resolve tashqi skriptingga ruxsat bermadi")
    return resolve


def _connect() -> Any:
    """Avval ko'prikni (bepul versiya), keyin to'g'ridan-to'g'ri API ni (Studio) sinaydi."""
    global _mode
    mode = os.environ.get("DAVINCI_MCP_MODE", "auto").lower()
    if mode in ("auto", "bridge"):
        resolve = _connect_bridge()
        if resolve is not None:
            _mode = "bridge"
            return resolve
        if mode == "bridge":
            raise ResolveError(
                "Ko'prik ishlamayapti. Resolve da Workspace > Scripts > DaVinci_MCP_Bridge ni bosing."
            )
    try:
        resolve = _connect_native()
    except ResolveError as exc:
        raise ResolveError(
            "DaVinci Resolve ga ulanib bo'lmadi. Resolve ochiq bo'lsin va "
            "Workspace > Scripts > DaVinci_MCP_Bridge ni ishga tushiring (bepul versiya), "
            "yoki Studio da Preferences > System > General > External scripting using = Local qiling. "
            f"Tafsilot: {exc}"
        ) from exc
    _mode = "native"
    return resolve


def get_resolve() -> Any:
    """Ishlayotgan Resolve obyektini qaytaradi, kerak bo'lsa qayta ulanadi."""
    global _resolve
    if _resolve is not None:
        try:
            if _resolve.GetProjectManager() is not None:
                return _resolve
        except Exception:  # Resolve yopilgan yoki qayta ishga tushgan
            log.info("Resolve bilan aloqa uzildi, qayta ulanmoqda")
    _resolve = _connect()
    return _resolve


def reset_connection() -> None:
    global _resolve
    _resolve = None
