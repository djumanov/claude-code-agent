"""Claude Desktop konfiguratsiyasiga davinci-resolve MCP serverini qo'shadi.

Foydalanish:  python scripts/register_claude.py <python.exe yo'li>
Mavjud sozlamalar saqlanib qoladi, faqat "davinci-resolve" yozuvi qo'shiladi/yangilanadi.
"""

import json
import os
import sys
from pathlib import Path


def config_path() -> Path:
    if sys.platform.startswith("win"):
        return Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


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


if __name__ == "__main__":
    main()
