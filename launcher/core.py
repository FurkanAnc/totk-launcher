r"""The launcher's logic, without any window: totk.ini, saves, cheats, settings schema, the mod library, play time,
update checks and starting the game.

The game loads romfs_mods and romfs-patches itself; the launcher only passes environment variables and writes totk.ini.
Mods in the library (the mods folder next to totk.exe, one folder per mod) are merged with romfs_mods into a copy in
launcher\rt\mods-src when the game starts; romfs_mods itself is never changed.
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

VERSION = "1.3.0"
EXE = ROOT / "totk.exe"
INI = ROOT / "totk.ini"
LOGS = ROOT / "logs"
GAME_LOG = LOGS / "totk.log"
MODS = ROOT / "romfs_mods"
LIBRARY = ROOT / "mods"
MERGED = APP / "rt" / "mods-src"
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
    cfg.setdefault("mods_off", [])
    cfg.setdefault("check_updates", True)
    cfg.setdefault("play", {"seconds": 0, "sessions": 0, "counted": []})
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
        ("poe", "PlayerStatus.CurrentMamo", T_INT, 1, 99999, t("Poes", "Poe"),
         t("Spent at the Bargainer Statues in the Depths.", "Derinlikler'deki Bargainer heykellerinde harcanır.")),
        ("pony", "HorseInnMemberPoint", T_INT, 1, 9999, t("Pony Points", "Pony Points"),
         t("Rewards at the stables.", "Ahırlardaki ödüller için.")),
    ]


ZERO_MIN = {"rupee", "poe", "pony"}   # cheats that may be set to 0


# --------------------------------------------------------------------------- pouches (arrays in progress.sav)
POUCH_SLOTS = [("slots_weapon", "Weapon", 20, ("Weapon slots", "Silah yuvası")),
               ("slots_bow", "Bow", 14, ("Bow slots", "Yay yuvası")),
               ("slots_shield", "Shield", 20, ("Shield slots", "Kalkan yuvası"))]
POUCH_ITEMS = [("zonaite", "Item_Ore_L", ("Zonaite", "Zonaite")),
               ("zonaite_l", "Item_Ore_M", ("Large Zonaite", "Büyük Zonaite")),
               ("charge", "Energy_Material_01", ("Crystallized Charges", "Kristal enerji")),
               ("charge_l", "Energy_Material_03", ("Large Crystallized Charges", "Büyük kristal enerji")),
               ("arrow", "NormalArrow", ("Arrows", "Ok")),
               ("bombflower", "BombFruit", ("Bomb Flowers", "Bomba çiçeği"))]
ITEM_POUCHES = ("Material", "Arrow", "KeyItem")
DURABILITY_UP = {murmur3("DurabilityUp"), murmur3("DurabilityUpPlus")}


class SaveFile:
    """A progress.sav to edit in place: scalars and the arrays the pouches are made of. Arrays: the value is the
    offset of a 32-bit count followed by the items (4 bytes, or 64 for a String64)."""

    def __init__(self, slot: Path):
        self.path = slot / "progress.sav"
        self.data = bytearray(self.path.read_bytes())
        self.idx = _sav_index(self.data)

    def _array(self, name: str) -> tuple[int, int]:
        _kind, off = self.idx.get(murmur3(name), (None, None))
        if off is None:
            return 0, 0
        ptr = struct.unpack_from("<I", self.data, off)[0]
        if ptr + 4 > len(self.data):
            return 0, 0
        return ptr + 4, struct.unpack_from("<I", self.data, ptr)[0]

    def ints(self, name: str) -> list[int]:
        start, n = self._array(name)
        return list(struct.unpack_from(f"<{n}i", self.data, start)) if n else []

    def set_int(self, name: str, i: int, value: int) -> None:
        start, n = self._array(name)
        if not 0 <= i < n:
            raise ValueError(f"{name}[{i}]")
        struct.pack_into("<i", self.data, start + 4 * i, value)

    def strings(self, name: str) -> list[str]:
        start, n = self._array(name)
        return [bytes(self.data[start + i * 64:start + (i + 1) * 64]).split(b"\0")[0].decode("utf-8", "replace")
                for i in range(n)]

    def find_item(self, item: str) -> tuple[str, int] | None:
        """(pouch, index) of an item the player has."""
        for pouch in ITEM_POUCHES:
            names = self.strings(f"Pouch.{pouch}.Content.Name")
            if item in names:
                return pouch, names.index(item)
        return None

    def worn(self) -> list[tuple[str, int, int]]:
        """(pouch, index, maximum) of every weapon, bow and shield below its full durability."""
        table = __import__("achievements").data()["durability"]
        out = []
        for pouch in ("Weapon", "Bow", "Shield"):
            names, life = self.strings(f"Pouch.{pouch}.Content.Name"), self.ints(f"Pouch.{pouch}.Content.Life")
            kinds = [v & 0xFFFFFFFF for v in self.ints(f"Pouch.{pouch}.Content.Effect.Type")]
            extra = self.ints(f"Pouch.{pouch}.Content.Effect.Value")
            for i, name in enumerate(names):
                if not name or i >= len(life) or life[i] < 0:
                    continue
                top = table.get(name, 70)
                if i < len(kinds) and kinds[i] in DURABILITY_UP and i < len(extra) and 0 < extra[i] < 10000:
                    top += extra[i]
                if life[i] < top:
                    out.append((pouch, i, top))
        return out

    def save(self) -> None:
        """A new file, never written in place: saves share files with their backups through hard links."""
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(self.data)
        os.replace(tmp, self.path)


def read_pouches(slot: Path) -> dict:
    """{"fields": [...], "missing": [labels], "worn": n} for the Cheats page."""
    sav = SaveFile(slot)
    fields, missing = [], []
    for key, pouch, top, label in POUCH_SLOTS:
        valid = sav.ints(f"Pouch.{pouch}.ValidNum")
        if valid:
            fields.append({"key": key, "label": t(*label), "value": max(valid), "min": max(valid), "max": top, "step": 1,
                           "help": t(f"Up to {top}.", f"En çok {top}.")})
    for key, item, label in POUCH_ITEMS:
        found = sav.find_item(item)
        if found:
            pouch, i = found
            fields.append({"key": key, "label": t(*label), "value": sav.ints(f"Pouch.{pouch}.Content.StockNum")[i],
                           "min": 1, "max": 999, "step": 1, "help": ""})
        else:
            missing.append(t(*label))
    return {"fields": fields, "missing": missing, "worn": len(sav.worn())}


def write_pouches(slot: Path, values: dict, repair: bool) -> int:
    """Writes pouch slots and item counts (only items the player has) and refills durability; returns the changes."""
    sav = SaveFile(slot)
    changes = 0
    for key, pouch, top, _label in POUCH_SLOTS:
        if key in values:
            valid = sav.ints(f"Pouch.{pouch}.ValidNum")
            v = max(max(valid or [0]), min(top, int(values[key])))
            for i, old in enumerate(valid):
                if old != v:
                    sav.set_int(f"Pouch.{pouch}.ValidNum", i, v)
                    changes += 1
    for key, item, _label in POUCH_ITEMS:
        if key in values:
            found = sav.find_item(item)
            if found:
                pouch, i = found
                v = max(1, min(999, int(values[key])))
                if sav.ints(f"Pouch.{pouch}.Content.StockNum")[i] != v:
                    sav.set_int(f"Pouch.{pouch}.Content.StockNum", i, v)
                    changes += 1
    if repair:
        for pouch, i, top in sav.worn():
            sav.set_int(f"Pouch.{pouch}.Content.Life", i, top)
            changes += 1
    if changes:
        sav.save()
    return changes


LIFE = "PlayerStatus.Life"


PLAYTIME = 0xE573F564   # progress.sav: the play time in seconds (UInt), as read by the TotK savegame editor
T_UINT = 20


def slot_playtime(slot: Path) -> int | None:
    try:
        data = (slot / "progress.sav").read_bytes()
        kind, off = _sav_index(data).get(PLAYTIME, (None, None))
    except (OSError, ValueError):
        return None
    return struct.unpack_from("<I", data, off)[0] if kind == T_UINT else None


def play_time() -> int:
    """The game's own play time of the most played save slot, in seconds (0 without saves)."""
    return max((s for s in map(slot_playtime, save_slots()) if s), default=0)


def slot_summary(slot: Path) -> dict:
    """Saved time and the player's values of one slot, for the Saves page."""
    when = (slot / "progress.sav").stat().st_mtime
    try:
        v = read_cheats(slot)
    except (OSError, ValueError):
        v = {}
    return {"name": slot.name, "time": when, "hearts": v.get("hearts"), "stamina": v.get("stamina"),
            "battery": v.get("battery"), "rupee": v.get("rupee"), "playtime": slot_playtime(slot)}


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
        (t("PICTURE AND CAMERA", "GÖRÜNTÜ VE KAMERA"), [
            ("aspect", "display", t("Picture shape", "Görüntü oranı"), "choice", ("fit", "stretch"), "fit",
             t("When the window's shape differs from the game resolution: fit keeps the shape with black bars, "
               "stretch fills the window. Recomp 0.2.8 and newer.",
               "Pencere oranı oyun çözünürlüğünden farklıysa: fit oranı korur ve siyah bant bırakır, stretch "
               "pencereyi doldurur. Recomp 0.2.8 ve sonrası.")),
            ("fov", "display", t("Field of view (%)", "Görüş alanı (%)"), "scale", (70, 140), "100",
             t("100 is the game's own camera; higher shows more around Link. Game 1.4.3, recomp 0.2.8 and newer.",
               "100 oyunun kendi kamerası; yüksek değer Link'in çevresini daha geniş gösterir. Oyun 1.4.3, recomp "
               "0.2.8 ve sonrası.")),
            ("color_preset", "display", t("Colour profile", "Renk profili"), "choice",
             ("default", "vivid", "clarity", "custom"), "default",
             t("The four values below are used with custom. Recomp 0.2.8 and newer.",
               "Aşağıdaki dört değer custom ile kullanılır. Recomp 0.2.8 ve sonrası.")),
            ("color_brightness", "display", t("Brightness", "Parlaklık"), "scale", (-30, 30), "0", ""),
            ("color_contrast", "display", t("Contrast (%)", "Kontrast (%)"), "scale", (70, 150), "100", ""),
            ("color_saturation", "display", t("Saturation (%)", "Doygunluk (%)"), "scale", (50, 200), "100", ""),
            ("color_gamma", "display", t("Gamma", "Gama"), "scale", (0.8, 1.2, 0.05), "1",
             t("Below 1 brightens the dark tones.", "1'in altı koyu tonları aydınlatır.")),
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
            ("rumble_strength", "input", t("Rumble strength (%)", "Titreşim gücü (%)"), "scale", (0, 300), "130",
             t("Recomp 0.2.8 and newer.", "Recomp 0.2.8 ve sonrası.")),
            ("rumble_triggers", "input", t("Trigger rumble (Xbox)", "Tetik titreşimi (Xbox)"), "bool", (), "0",
             t("Also drives the impulse triggers of an Xbox pad. Recomp 0.2.8 and newer.",
               "Xbox kumandasının tetik motorlarını da çalıştırır. Recomp 0.2.8 ve sonrası.")),
            ("stick_deadzone", "input", t("Stick dead zone (%)", "Çubuk ölü bölgesi (%)"), "scale", (0, 50), "8",
             t("Raise it for a stick that drifts. Recomp 0.2.8 and newer.",
               "Kendi kendine kayan bir çubuk için yükseltin. Recomp 0.2.8 ve sonrası.")),
        ]),
    ]


SECTIONS = {k: sec for _, items in setting_groups() for (k, sec, *_rest) in items}


# --------------------------------------------------------------------------- the mod library
def mod_root(folder: Path) -> Path:
    """A mod folder holds the game's file tree, directly or in a romfs subfolder (as many mods are shipped)."""
    return folder / "romfs" if (folder / "romfs").is_dir() else folder


def library() -> list[Path]:
    if not LIBRARY.is_dir():
        return []
    return sorted((p for p in LIBRARY.iterdir() if p.is_dir()), key=lambda p: p.name.lower())


def mod_sources(cfg: dict) -> list[tuple[str, Path]]:
    """(name, file tree) of everything that goes into the game: romfs_mods first, then the enabled library mods;
    a later one wins when two have the same file."""
    out = [("romfs_mods", MODS)] if MODS.is_dir() else []
    return out + [(m.name, mod_root(m)) for m in library() if m.name not in cfg.get("mods_off", [])]


def mod_list(cfg: dict) -> list[dict]:
    """The page's list: every source with its file count, size, switch and the files a later mod replaces."""
    seen: dict[str, str] = {}
    rows = []
    entries = [("romfs_mods", MODS, True)] if MODS.is_dir() else []
    entries += [(m.name, mod_root(m), m.name not in cfg.get("mods_off", [])) for m in library()]
    for name, root, on in entries:
        files = mod_files(root)
        rel = [f.relative_to(root).as_posix() for f in files]
        over = sorted({seen[r] for r in rel if r in seen}) if on else []
        if on:
            seen.update({r: name for r in rel})
        rows.append({"name": name, "files": len(files), "size": round(sum(f.stat().st_size for f in files) / 1048576, 1),
                     "on": on, "base": root == MODS, "overrides": over})
    return rows


def merged_mods(cfg: dict) -> Path:
    """romfs_mods alone, or a merged copy with the enabled library mods (hard links when the drive allows it)."""
    sources = mod_sources(cfg)
    if all(root == MODS for _, root in sources):
        return MODS
    if MERGED.exists():
        shutil.rmtree(MERGED)
    MERGED.mkdir(parents=True)
    for _, root in sources:
        for f in mod_files(root):
            dst = MERGED / f.relative_to(root)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                dst.unlink()
            try:
                os.link(f, dst)
            except OSError:
                shutil.copy2(f, dst)
    return MERGED


def add_mod(folder: Path) -> str:
    """Copies a mod folder into the library; returns its name there."""
    LIBRARY.mkdir(parents=True, exist_ok=True)
    name, n = folder.name, 2
    while (LIBRARY / name).exists():
        name, n = f"{folder.name} ({n})", n + 1
    shutil.copytree(folder, LIBRARY / name)
    return name


# --------------------------------------------------------------------------- play time
def count_session(cfg: dict) -> bool:
    """Adds the last run of the game (its frametime line, logs\\totk.log) to the play time once; True when new."""
    try:
        stamp = str(GAME_LOG.stat().st_mtime_ns)
    except OSError:
        return False
    play = cfg.setdefault("play", {"seconds": 0, "sessions": 0, "counted": []})
    if stamp in play["counted"]:
        return False
    for line in reversed(log_lines(400)):
        m = re.search(r"frametime: exit: \d+ frames in ([\d.]+) s", line)
        if m:
            play["seconds"] += float(m.group(1))
            play["sessions"] += 1
            play["counted"] = (play["counted"] + [stamp])[-50:]
            return True
    return False


# --------------------------------------------------------------------------- updates
RECOMP_REPO = "valentderah/totk-pc-recomp"
LAUNCHER_REPO = "FurkanAnc/totk-launcher"


def _version(text: str) -> tuple[int, ...]:
    m = re.search(r"(\d+(?:\.\d+)*)", text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def installed_release() -> str:
    """The recomp release the game was built with (totk-install.json), e.g. 0.1.1."""
    try:
        return json.loads((ROOT / "totk-install.json").read_text(encoding="utf-8")).get("release", "").split("+")[0]
    except (OSError, ValueError):
        return ""


def installed_build() -> str:
    """The commit after the release number in totk-install.json (0.1.1+701bd62 -> 701bd62)."""
    try:
        rel = json.loads((ROOT / "totk-install.json").read_text(encoding="utf-8")).get("release", "")
    except (OSError, ValueError):
        return ""
    return rel.split("+", 1)[1] if "+" in rel else ""


def latest_release(repo: str) -> dict | None:
    """The latest GitHub release of a repository: {"tag", "url"}; None when it cannot be read."""
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "totk-launcher"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode("utf-8"))
        setup = next((a for a in d.get("assets", []) if a["name"].lower().endswith("-windows.zip")), None)
        return {"tag": d["tag_name"], "url": d["html_url"],
                "setup": {"name": setup["name"], "url": setup["browser_download_url"], "size": setup["size"]}
                if setup else None}
    except Exception:  # noqa: BLE001 - offline or rate limited: no notice
        return None


def check_updates(cfg: dict, max_age: float = 6 * 3600) -> dict:
    """{"recomp": {...} | None, "launcher": {...} | None}: a newer release than the installed one. Asks GitHub at most
    every six hours; the answer is kept in launcher.json."""
    cache = cfg.get("update_cache") or {}
    if time.time() - cache.get("time", 0) > max_age:
        cache = {"time": time.time(), "recomp": latest_release(RECOMP_REPO), "launcher": latest_release(LAUNCHER_REPO)}
        cfg["update_cache"] = cache
    out = {}
    have = {"recomp": installed_release(), "launcher": VERSION}
    for k in ("recomp", "launcher"):
        rel = cache.get(k)
        newer = rel and have[k] and _version(rel["tag"]) > _version(have[k])
        out[k] = {**rel, "have": have[k]} if newer else None
    return out


SETUP_DIR = APP / "rt" / "recomp-setup"


def download_setup(rel: dict, progress) -> Path:
    """Downloads and unpacks the recomp's Windows setup of a release; returns TotK-Setup.exe. progress(done, total)."""
    import urllib.request
    import zipfile
    setup = rel["setup"]
    if not setup["url"].startswith("https://github.com/valentderah/totk-pc-recomp/releases/download/"):
        raise ValueError("unexpected download address")
    folder = SETUP_DIR / rel["tag"]
    exe = next(folder.rglob("TotK-Setup.exe"), None) if folder.is_dir() else None
    if exe:
        return exe
    SETUP_DIR.mkdir(parents=True, exist_ok=True)
    part = SETUP_DIR / (setup["name"] + ".part")
    req = urllib.request.Request(setup["url"], headers={"User-Agent": "totk-launcher"})
    with urllib.request.urlopen(req, timeout=30) as r, part.open("wb") as f:
        total, done = int(r.headers.get("Content-Length") or setup["size"]), 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            progress(done, total)
    if done != total:
        raise OSError(f"download incomplete: {done} of {total} bytes")
    if folder.exists():
        shutil.rmtree(folder)
    with zipfile.ZipFile(part) as z:
        for member in z.namelist():   # stay inside the folder
            if member.startswith(("/", "\\")) or ".." in Path(member).parts:
                raise ValueError(f"unsafe path in the archive: {member}")
        z.extractall(folder)
    part.unlink()
    exe = next(folder.rglob("TotK-Setup.exe"), None)
    if not exe:
        raise FileNotFoundError("TotK-Setup.exe is not in the download")
    return exe


# --------------------------------------------------------------------------- collectibles: what is still missing
def collectibles(slot: Path) -> list[dict]:
    """Per kind: done, total, and every item with its place (from the TotK savegame editor's coordinates) and
    whether this slot has it."""
    import achievements
    d = achievements.data()
    lists, places = d["lists"], d["places"]
    save = achievements.Save(slot / "progress.sav")
    clear, open_ = murmur3("Clear"), murmur3("Open")

    def pretty(name: str, kind: str) -> str:
        name = re.sub(r"^(Cave|Well|DeepHole)_", "", name).replace("_", " ")
        name = re.sub(r"\b0*(\d+)\b", r"\1", name)
        return re.sub(r"\s0$", "", name).strip() or kind

    kinds = [
        ("shrines", t("Shrines", "Tapınaklar"), "shrines_status", clear),
        ("lightroots", t("Lightroots", "Lightroot'lar"), "lightroots_status", open_),
        ("towers", t("Skyview Towers", "Skyview Kuleleri"), "towers_activated", 1),
        ("caves", t("Caves", "Mağaralar"), "location_caves_visited", 1),
        ("wells", t("Wells", "Kuyular"), "location_wells_visited", 1),
        ("chasms", t("Chasms", "Uçurumlar"), "location_chasms_visited", 1),
        ("bubbuls", t("Bubbul Frogs", "Bubbul kurbağaları"), "bubbuls_defeated", 1),
        ("koroks_hidden", t("Koroks (hidden)", "Koroklar (saklı)"), "koroks_hidden", 1),
        ("koroks_carry", t("Koroks (carry)", "Koroklar (taşıma)"), "koroks_carry", clear),
    ]
    out = []
    for key, label, list_name, want in kinds:
        items = []
        for i, flag in enumerate(lists[list_name]):
            place = places[key][i] if i < len(places[key]) else [None, None, None]
            name = place[3] if len(place) > 3 else ""
            name = pretty(name, "") if name else ""
            if name.isdigit():
                name = t("Well", "Kuyu") + " " + name
            items.append({"n": i + 1, "name": name, "x": place[0], "y": place[1],
                          "z": place[2], "done": save.values.get(flag) == want})
        out.append({"key": key, "label": label, "total": len(items), "done": sum(it["done"] for it in items),
                    "items": items})
    return out


# --------------------------------------------------------------------------- crashes
CRASHES = APP / "crash-reports"
CRASH_RE = re.compile(r"^\s*(FATAL|fatal)[: ]")


def crash_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if CRASH_RE.match(line)]


def keep_crash_log() -> Path | None:
    """The game overwrites its log at the next start: a copy of a log that ends in a crash report."""
    try:
        text = GAME_LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not crash_lines(text.splitlines()[-400:]):
        return None
    CRASHES.mkdir(parents=True, exist_ok=True)
    dst = CRASHES / time.strftime("totk-%Y%m%d-%H%M%S.log", time.localtime(GAME_LOG.stat().st_mtime))
    if not dst.exists():
        dst.write_text(text, encoding="utf-8")
    for old in sorted(CRASHES.glob("totk-*.log"))[:-10]:
        old.unlink(missing_ok=True)
    return dst


def _redact(text: str) -> str:
    """No user name or home folder in a report that goes on the web."""
    home = os.path.expanduser("~")
    user = os.environ.get("USERNAME", "")
    text = text.replace(home, "%USERPROFILE%").replace(home.replace("\\", "/"), "%USERPROFILE%")
    if len(user) > 2:
        text = re.sub(re.escape(user), "<user>", text, flags=re.I)
    return text


def crash_report(log_path: Path | None = None) -> dict:
    """The facts the recomp's crash issue form asks for, from the last log (or a kept crash log)."""
    import platform
    path = log_path or GAME_LOG
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    fatal = crash_lines(lines)
    if fatal:   # the crash report and what led to it
        at = max(i for i, line in enumerate(lines) if CRASH_RE.match(line))
        excerpt = lines[max(0, at - 40):at + 25]
    else:
        excerpt = lines[-60:]
    gpu = log_fact(r"vk: using gpu \d+: (.+)")
    driver = log_fact(r"vk: driver[^:]*:\s*(.+)") or log_fact(r"driver (?:version )?([\d.]+.*)")
    try:
        inst = json.loads((ROOT / "totk-install.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        inst = {}
    version = f"TotK Recomp {inst.get('release', '?')}, game {inst.get('version', '?')}"
    system = f"{gpu or '?'}{', driver ' + driver if driver else ''}; Windows {platform.version()}"
    log = _redact("\n".join(excerpt))
    return {"crashed": bool(fatal), "summary": _redact(fatal[-1].strip()) if fatal else "", "version": version,
            "system": _redact(system), "log": log, "log_file": str(path),
            "text": _redact(f"Version: {version}\nSystem: {system}\n\nLog ({path.name}):\n{log}")}


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
    elif not build:
        mods = merged_mods(cfg)
        if mods != MODS:
            env["TOTK_ROMFS_MODS"] = str(mods)
    return env, build


def build_prompts(cfg: dict, env: dict) -> None:
    """Builds the prompt overlays and points env at them (about 10 s the first time)."""
    ini = read_ini()
    prompts.MODS = merged_mods(cfg) if cfg["mods"] else MODS   # the overlay starts from the mods in use
    try:
        mods, patches = prompts.build_overlay(cfg["prompts"], prompts.parse_binds(ini), cfg["mods"], ini.get("lang"))
    finally:
        prompts.MODS = MODS
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
