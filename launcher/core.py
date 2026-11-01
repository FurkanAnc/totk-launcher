"""The launcher's logic, without any window: totk.ini, saves, cheats, settings schema, starting the game.

The game loads romfs_mods and romfs-patches itself; the launcher only passes environment variables and writes totk.ini.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import time
from pathlib import Path

import prompts
from i18n import t
from paths import APP, ROOT

EXE = ROOT / "totk.exe"
INI = ROOT / "totk.ini"
LOGS = ROOT / "logs"
GAME_LOG = LOGS / "totk.log"
MODS = ROOT / "romfs_mods"
PATCHES = ROOT / "romfs-patches"
SAVE = ROOT / "profile" / "save"
SAVE_BACKUPS = ROOT / "profile" / "launcher-backups"
INI_BACKUPS = APP / "ini-backups"
EMPTY = APP / "rt" / "empty"
CONFIG = APP / "launcher.json"

NO_WINDOW = 0x08000000
NEW_GROUP = 0x00000200

# --------------------------------------------------------------------------- config
def migrate_old_names() -> None:
    """Folder names of the first (Turkish-only) version."""
    for old, new in ((ROOT / "profile" / "launcher-yedek", SAVE_BACKUPS), (APP / "ini-yedek", INI_BACKUPS)):
        if old.is_dir() and not new.exists():
            try:
                old.rename(new)
            except OSError:
                pass
    for old in (APP / "bos-klasor", APP / "data"):
        if old.is_dir():
            shutil.rmtree(old, ignore_errors=True)


def load_config() -> dict:
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    cfg.setdefault("lang", "en")
    cfg.setdefault("mods", True)
    cfg.setdefault("backup_before_play", True)
    cfg.setdefault("backup_keep", 10)
    cfg.setdefault("close_on_play", False)
    cfg.setdefault("theme", "light")
    if cfg["theme"] not in ("light", "night"):
        cfg["theme"] = "light"
    cfg.setdefault("achievements", {})
    cfg["prompts"] = {"klavye": "keyboard", "playstation": "mod"}.get(cfg.get("prompts"), cfg.get("prompts"))
    if cfg["prompts"] not in prompts.PROMPT_SETS:
        cfg["prompts"] = "keyboard"
    return cfg


def save_config(cfg: dict) -> None:
    APP.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, CONFIG)


# --------------------------------------------------------------------------- totk.ini
SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def _active(key: str) -> re.Pattern:
    return re.compile(rf"^\s*{re.escape(key)}\s*=(.*)$", re.I)


def _commented(key: str) -> re.Pattern:
    return re.compile(rf"^\s*[#;]\s*{re.escape(key)}\s*=", re.I)


def read_ini() -> dict[str, str]:
    """Values of the active (uncommented) lines."""
    try:
        lines = INI.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    out = {}
    for line in lines:
        m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=(.*)$", line)
        if m:
            out[m.group(1).lower()] = re.split(r"\s[#;]", m.group(2))[0].strip()
    return out


def write_ini(changes: dict[str, str | None], sections: dict[str, str]) -> None:
    """Writes the values; None removes the line. A new line goes under its documented '# key = ...' line."""
    try:
        lines = INI.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    if INI.exists():
        INI_BACKUPS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(INI, INI_BACKUPS / f"totk.ini.{time.strftime('%Y%m%d-%H%M%S')}")
        for old in sorted(INI_BACKUPS.glob("totk.ini.*"))[:-10]:
            old.unlink(missing_ok=True)

    for key, value in changes.items():
        idx = next((i for i, line in enumerate(lines) if _active(key).match(line)), None)
        if value is None:
            if idx is not None:
                del lines[idx]
            continue
        new = f"{key} = {value}"
        if idx is not None:
            lines[idx] = new
            continue
        cidx = next((i for i, line in enumerate(lines) if _commented(key).match(line)), None)
        if cidx is not None:
            lines.insert(cidx + 1, new)
            continue
        sec = sections.get(key, "")
        sidx = next((i for i, line in enumerate(lines)
                     if (m := SECTION_RE.match(line)) and m.group(1).strip().lower() == sec), None)
        if sidx is None:
            lines += ["", f"[{sec}]", new]
            continue
        end = next((j for j in range(sidx + 1, len(lines)) if SECTION_RE.match(lines[j])), len(lines))
        while end > sidx + 1 and not lines[end - 1].strip():
            end -= 1
        lines.insert(end, new)

    tmp = INI.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, INI)


# --------------------------------------------------------------------------- game state
def log_lines(n: int = 400) -> list[str]:
    try:
        return GAME_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def log_head(n: int = 300) -> list[str]:
    try:
        with GAME_LOG.open(encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\n") for _, line in zip(range(n), f)]
    except OSError:
        return []


def gpus_from_log() -> list[tuple[str, str]]:
    found = {}
    for line in log_head():
        m = re.search(r"vk: gpu (\d+): (.+?) \(type", line)
        if m:
            found[m.group(1)] = m.group(2)
    return sorted(found.items())


def log_fact(pattern: str) -> str:
    for line in reversed(log_head() + log_lines(4000)):
        m = re.search(pattern, line)
        if m:
            return m.group(1).strip()
    return ""


def game_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq totk.exe", "/NH"], capture_output=True,
                             text=True, timeout=10, creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "totk.exe" in out.lower()


def installed_version() -> str:
    try:
        d = json.loads((ROOT / "totk-install.json").read_text(encoding="utf-8"))
        return f"{d.get('version', '?')} · recomp {d.get('release', '?')}"
    except (OSError, ValueError):
        return "?"


def mod_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "manifest.tsv")


# --------------------------------------------------------------------------- saves
def backup_saves(tag: str, keep: int) -> Path | None:
    if not SAVE.is_dir() or not any(SAVE.iterdir()):
        return None
    SAVE_BACKUPS.mkdir(parents=True, exist_ok=True)
    dst = SAVE_BACKUPS / f"{time.strftime('%Y-%m-%d %H-%M-%S')} {tag}"
    shutil.copytree(SAVE, dst, dirs_exist_ok=True)
    if keep > 0:
        auto = sorted(p for p in SAVE_BACKUPS.iterdir() if p.is_dir() and p.name.endswith(("auto", "otomatik")))
        for old in auto[:-keep]:
            shutil.rmtree(old, ignore_errors=True)
    return dst


def list_backups() -> list[Path]:
    if not SAVE_BACKUPS.is_dir():
        return []
    return sorted((p for p in SAVE_BACKUPS.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


# --------------------------------------------------------------------------- progress.sav (cheats)
# A 0x20-byte header (0x01020304, version, offset of the data section), then (murmur3 hash, value) pairs. A pair with
# hash 0 starts a type section: 2 = int, 4 = float. For array types the value is an offset into the file.
SAV_MAGIC = 0x01020304
T_INT, T_FLOAT = 2, 4


def murmur3(text: str) -> int:
    data, h = text.encode(), 0
    c1, c2 = 0xCC9E2D51, 0x1B873593
    n = len(data) // 4
    for i in range(n):
        k = int.from_bytes(data[i * 4:i * 4 + 4], "little")
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        h ^= (k * c2) & 0xFFFFFFFF
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
        h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF
    tail = data[n * 4:]
    if tail:
        k = int.from_bytes(tail, "little")
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        h ^= (k * c2) & 0xFFFFFFFF
    h ^= len(data)
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    return h ^ (h >> 16)


def cheats():
    """(key, name in the save, type, unit, maximum, label, help)"""
    return [
        ("rupee", "PlayerStatus.CurrentRupee", T_INT, 1, 999999, t("Rupees", "Rupi"), ""),
        ("hearts", "PlayerStatus.MaxLife", T_INT, 4, 40, t("Hearts (maximum)", "Kalp (en çok)"),
         t("Health is filled up to it too.", "Can da bu değere doldurulur.")),
        ("stamina", "PlayerStatus.MaxStamina", T_FLOAT, 1000, 3, t("Stamina wheels", "Dayanıklılık çarkı"),
         t("1 to 3 wheels, in fifths.", "1-3 çark, beşte bir adımlarla.")),
        ("battery", "PlayerStatus.MaxEnergy", T_FLOAT, 1000, 8, t("Zonai battery cells", "Zonai pil hücresi"),
         t("1 to 8 cells.", "1-8 hücre.")),
    ]


LIFE = "PlayerStatus.Life"


def save_slots() -> list[Path]:
    """profile/save/<user>/slot_NN folders, most recently saved first."""
    slots = [p.parent for p in SAVE.glob("*/slot_*/progress.sav")]
    return sorted(slots, key=lambda p: (p / "progress.sav").stat().st_mtime, reverse=True)


def _sav_index(data: bytes) -> dict[int, tuple[int, int]]:
    """hash -> (type, offset of its value in the file)."""
    if len(data) < 0x20 or struct.unpack_from("<I", data, 0)[0] != SAV_MAGIC:
        raise ValueError(t("progress.sav not recognised", "progress.sav tanınmadı"))
    end = struct.unpack_from("<I", data, 8)[0]
    out, kind = {}, -1
    for off in range(0x20, min(end, len(data)) - 7, 8):
        h, v = struct.unpack_from("<II", data, off)
        if h == 0:
            kind = v
        else:
            out[h] = (kind, off + 4)
    return out


def read_cheats(slot: Path) -> dict[str, float]:
    data = (slot / "progress.sav").read_bytes()
    idx = _sav_index(data)
    out = {}
    for key, name, kind, unit, *_ in cheats():
        k, off = idx.get(murmur3(name), (None, None))
        if k != kind:
            continue
        out[key] = struct.unpack_from("<i" if kind == T_INT else "<f", data, off)[0] / unit
    return out


def write_cheats(slot: Path, values: dict[str, float]) -> None:
    """Saves share files with their backups through hard links: write a new file, never in place."""
    path = slot / "progress.sav"
    data = bytearray(path.read_bytes())
    idx = _sav_index(data)

    def put(name, kind, raw):
        k, off = idx.get(murmur3(name), (None, None))
        if k != kind:
            raise ValueError(t(f"{name} not found in the save", f"{name} kayıtta bulunamadı"))
        struct.pack_into("<i" if kind == T_INT else "<f", data, off, raw)

    for key, name, kind, unit, *_ in cheats():
        if key in values:
            raw = values[key] * unit
            put(name, kind, int(round(raw)) if kind == T_INT else float(raw))
            if key == "hearts":
                put(LIFE, T_INT, int(round(raw)))
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- settings schema
RESOLUTIONS = ("1280x720", "1600x900", "1920x1080", "1920x1200", "2560x1080", "2560x1440", "3440x1440",
               "3840x2160", "5120x1440")


def setting_groups():
    """[(title, [(key, ini section, label, kind, choices, default, help)])]"""
    return [
        (t("FRAME RATE", "KARE HIZI"), [
            ("fps_limit", "frame rate", t("Frame rate limit", "Kare hızı sınırı"), "choice",
             ("30", "60", "120", "144", "display"), "60",
             t("Above 60 is experimental and needs the real-time frame step. Applies while the game runs.",
               "60 üstü deneysel; 'Gerçek zamanlı adım' açık olmalı. Oyun açıkken de hemen uygulanır.")),
            ("realtime", "frame rate", t("Real-time frame step", "Gerçek zamanlı adım"), "bool", (), "1",
             t("Game speed follows the clock instead of the frame count.",
               "Oyun hızı kare sayısına değil saate bağlanır.")),
            ("highfps_fix", "frame rate", t("High frame rate physics fix", "Yüksek FPS fizik düzeltmesi"), "bool",
             (), "1", t("Stops physics that bounce at high frame rates.",
                        "Yüksek kare hızında zıplayan fiziği engeller.")),
        ]),
        (t("DISPLAY", "GÖRÜNTÜ"), [
            ("fullscreen", "display", t("Fullscreen (borderless)", "Tam ekran (kenarlıksız)"), "bool", (), "0",
             t("F11 switches it in game.", "Oyunda F11 ile de değişir.")),
            ("window_size", "display", t("Window size", "Pencere boyutu"), "combo", RESOLUTIONS, "1920x1080",
             t("When fullscreen is off.", "Tam ekran kapalıyken.")),
            ("output_res", "display", t("Game resolution", "Oyun çözünürlüğü"), "combo", RESOLUTIONS, "1920x1080",
             t("The size the game draws at. Read at start.", "Oyunun çizdiği boyut. Başlangıçta okunur.")),
            ("render_scale", "display", t("3D render scale", "3D render ölçeği"), "combo",
             ("game", "50", "75", "100", "125", "150", "200"), "game",
             t("'game' = the game's own (5/6). Above 100 supersamples.",
               "'game' = oyunun kendisi (5/6). 100 üstü süper örnekleme yapar.")),
            ("upscaler", "display", t("Upscaler", "Ölçekleyici"), "choice", ("fsr", "bilinear"), "fsr", ""),
            ("sharpness", "display", t("FSR sharpness", "FSR keskinliği"), "scale", (0, 100), "80", ""),
            ("perf_overlay", "display", t("Performance overlay", "Performans göstergesi"), "choice",
             ("off", "fps", "full"), "off", t("F10 cycles it in game.", "Oyunda F10 ile değişir.")),
            ("vk_present", "display", t("Present mode", "Sunum modu"), "choice", ("mailbox", "fifo", "immediate"),
             "mailbox", t("fifo = vsync, immediate = uncapped (may tear).",
                          "fifo = dikey senkron, immediate = sınırsız (yırtılma olabilir).")),
            ("gpu_index", "display", t("Graphics card", "Ekran kartı"), "gpu", (), "",
             t("The list comes from the last game log.", "Liste son oyun logundan okunur.")),
        ]),
        (t("LANGUAGE AND SYSTEM", "DİL VE SİSTEM"), [
            ("lang", "language", t("Game language", "Oyun dili"), "choice", tuple(prompts.MALS_OF_LANG), "en-US",
             t("Translation mods usually replace one language (often en-US).",
               "Çeviri yamaları genellikle tek bir dilin (çoğunlukla en-US) yerine geçer.")),
            ("operation_mode", "language", t("Console mode", "Konsol modu"), "choice", ("docked", "handheld"),
             "docked", ""),
            ("menu_lang", "language", t("F1 menu language", "F1 menüsü dili"), "choice", ("en", "ru"), "en", ""),
        ]),
        (t("SOUND AND INPUT", "SES VE KONTROL"), [
            ("volume", "audio", t("Volume", "Ses düzeyi"), "scale", (0, 100), "100",
             t("On top of the game's own volume.", "Oyunun kendi ses ayarının üstüne.")),
            ("rumble", "input", t("Rumble", "Titreşim"), "bool", (), "1", ""),
            ("motion", "input", t("Motion controls (gyro)", "Hareket kontrolü (jiroskop)"), "bool", (), "1", ""),
        ]),
    ]


SECTIONS = {k: sec for _, items in setting_groups() for (k, sec, *_rest) in items}


# --------------------------------------------------------------------------- starting the game
def game_env(cfg: dict) -> tuple[dict, bool]:
    """(environment for totk.exe, whether the button prompts must be built first)."""
    env = os.environ.copy()
    env.pop("TOTK_ROMFS_MODS", None)
    env.pop("TOTK_ROMFS_PATCHES", None)
    if not (ROOT / "romfs").exists() and (ROOT / "romfs2").exists():
        env["TOTK_ROMFS"] = str(ROOT / "romfs2")
    build = prompts.prompts_available() and not (cfg["prompts"] == "switch" and not cfg["mods"])
    if not build and not cfg["mods"]:
        EMPTY.mkdir(parents=True, exist_ok=True)
        env["TOTK_ROMFS_MODS"] = str(EMPTY)
    return env, build


def build_prompts(cfg: dict, env: dict) -> None:
    """Builds the prompt overlays and points env at them (about 10 s the first time)."""
    ini = read_ini()
    mods, patches = prompts.build_overlay(cfg["prompts"], prompts.parse_binds(ini), cfg["mods"], ini.get("lang"))
    env["TOTK_ROMFS_MODS"] = str(mods)
    if patches:
        env["TOTK_ROMFS_PATCHES"] = str(patches)


def launch(env: dict) -> subprocess.Popen:
    return subprocess.Popen([str(EXE)], cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=NO_WINDOW | NEW_GROUP)


def create_shortcut(target: str, args: str, icon: str) -> Path:
    lnk = Path(os.environ["USERPROFILE"]) / "Desktop" / "TotK Launcher.lnk"
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:L);$s.TargetPath=$env:T;"
          "if($env:A){$s.Arguments='\"'+$env:A+'\"'};$s.WorkingDirectory=$env:W;$s.IconLocation=$env:I+',0';$s.Save()")
    env = {**os.environ, "L": str(lnk), "T": target, "A": args, "W": str(ROOT), "I": icon}
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True, creationflags=NO_WINDOW,
                   timeout=30)
    return lnk


def selftest() -> None:
    r"""`--selftest`: builds the keyboard prompts and reads the achievements without a window; writes the result to
    launcher\selftest.txt (used to check a packaged exe)."""
    import achievements
    from paths import FROZEN
    lines = [f"frozen={FROZEN} root={ROOT} app={APP}"]
    try:
        cfg = {**load_config(), "prompts": "keyboard", "mods": MODS.is_dir()}
        env, _ = game_env(cfg)
        build_prompts(cfg, env)
        lines.append(f"prompts ok: {env.get('TOTK_ROMFS_MODS')} {env.get('TOTK_ROMFS_PATCHES')}")
        _, new = achievements.evaluate(SAVE, {})
        lines.append(f"achievements ok: {len(achievements.ACHIEVEMENTS)} defined, {len(new)} reached")
    except Exception as e:  # noqa: BLE001 - reported
        import traceback
        lines.append("FAILED: " + "".join(traceback.format_exception(e)))
    APP.mkdir(parents=True, exist_ok=True)
    (APP / "selftest.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
