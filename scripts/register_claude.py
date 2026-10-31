"""Claude Desktop konfiguratsiyasiga davinci-resolve MCP serverini qo'shadi
va DaVinci_MCP_Bridge.py ni Resolve ning Scripts/Utility papkasiga nusxalaydi.

Foydalanish:  python scripts/register_claude.py <python.exe yo'li>
Mavjud sozlamalar saqlanib qoladi, faqat "davinci-resolve" yozuvi qo'shiladi/yangilanadi.
"""

import json
import os
import shutil
import sys
from pathlib import Path


def config_path() -> Path:
    if sys.platform.startswith("win"):
        return Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def resolve_scripts_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ["APPDATA"]) / "Blackmagic Design" / "DaVinci Resolve" / "Support"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve"
    else:
        base = Path.home() / ".local" / "share" / "DaVinciResolve"
    return base / "Fusion" / "Scripts" / "Utility"


def install_bridge() -> None:
    src = Path(__file__).resolve().parents[1] / "bridge" / "DaVinci_MCP_Bridge.py"
    dst_dir = resolve_scripts_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / src.name)
    print(f"Ko'prik skripti o'rnatildi: {dst_dir / src.name}")


def main() -> None:
    python = sys.argv[1] if len(sys.argv) > 1 else sys.executable
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if path.exists() and path.read_text(encoding="utf-8").strip():
        data = json.loads(path.read_text(encoding="utf-8"))
        path.with_suffix(".json.bak").write_text(json.dumps(data, indent=2), encoding="utf-8")
    data.setdefault("mcpServers", {})["davinci-resolve"] = {
        "command": python,
        "args": ["-m", "davinci_resolve_mcp"],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Claude Desktop sozlandi: {path}")
    install_bridge()


if __name__ == "__main__":
    main()
