"""Where things are, run as a script (launcher\\launcher.pyw) or as a packaged exe (TotK Launcher.exe).

ROOT: the game folder (totk.exe). APP: the launcher's own folder for its options, backups and overlays
(ROOT\\launcher). RES: files that ship with the launcher (inside the exe when packaged).

The game folder is, in order: the folder of the exe (or of the launcher folder), its parent, or the folder the user
picked once (remembered in %APPDATA%\\TotK Launcher\\location.json). FOUND tells whether totk.exe is there.
"""
import json
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
LOCATION = Path(os.environ.get("APPDATA") or Path.home()) / "TotK Launcher" / "location.json"


def saved_game_folder() -> Path | None:
    try:
        folder = Path(json.loads(LOCATION.read_text(encoding="utf-8"))["game"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return folder if (folder / "totk.exe").is_file() else None


def save_game_folder(folder: Path) -> None:
    LOCATION.parent.mkdir(parents=True, exist_ok=True)
    LOCATION.write_text(json.dumps({"game": str(folder)}, ensure_ascii=False), encoding="utf-8")


def _find() -> tuple[Path, Path]:
    """(ROOT, APP)."""
    here = Path(sys.executable if FROZEN else __file__).resolve().parent
    if FROZEN and (here / "totk.exe").is_file():          # TotK Launcher.exe next to totk.exe
        return here, here / "launcher"
    if (here.parent / "totk.exe").is_file():               # inside <game>\launcher
        return here.parent, here
    saved = saved_game_folder()
    if saved:
        return saved, saved / "launcher"
    return (here, here / "launcher") if FROZEN else (here.parent, here)


RES = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) if FROZEN else Path(__file__).resolve().parent
ROOT, APP = _find()
FOUND = (ROOT / "totk.exe").is_file()
