"""DaVinci Resolve scripting API bilan ulanish.

DaVinci Resolve o'zining Python API sini ``DaVinciResolveScript`` moduli orqali
beradi. Bu modul Resolve o'rnatilgan papkada turadi, shuning uchun uni topish
uchun ``RESOLVE_SCRIPT_API`` va ``RESOLVE_SCRIPT_LIB`` muhit o'zgaruvchilari
kerak. Agar ular berilmagan bo'lsa, operatsion tizimga qarab standart yo'llar
ishlatiladi.
"""

from __future__ import annotations

import importlib
import logging
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


def _connect() -> Any:
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
        raise ResolveError(
            "DaVinci Resolve ga ulanib bo'lmadi. Tekshiring: 1) Resolve ochiq bo'lsin; "
            "2) Preferences > System > General > 'External scripting using' = Local; "
            "3) Python versiyasi Resolve bilan mos (64-bit, 3.10-3.12 tavsiya etiladi)."
        )
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
