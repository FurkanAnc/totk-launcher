"""TotK launcher: starts the game, edits totk.ini without touching its comments, backs up saves, edits key bindings
and button prompts.

The game loads romfs_mods and romfs-patches itself; the launcher only passes environment variables and writes totk.ini.
The interface is English by default; Turkish can be chosen in Settings.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import i18n  # noqa: E402
import prompts  # noqa: E402
import achievements  # noqa: E402
from i18n import t  # noqa: E402

ROOT = HERE.parent
EXE = ROOT / "totk.exe"
INI = ROOT / "totk.ini"
LOGS = ROOT / "logs"
GAME_LOG = LOGS / "totk.log"
MODS = ROOT / "romfs_mods"
PATCHES = ROOT / "romfs-patches"
SAVE = ROOT / "profile" / "save"
SAVE_BACKUPS = ROOT / "profile" / "launcher-backups"
INI_BACKUPS = HERE / "ini-backups"
EMPTY = HERE / "rt" / "empty"
CONFIG = HERE / "launcher.json"

NO_WINDOW = 0x08000000
NEW_GROUP = 0x00000200

BG, SIDE, PANEL, EDGE = "#0d1114", "#090c0e", "#141b20", "#243039"
TXT, DIM, ACCENT, WARN, BAD = "#e3eaee", "#7d8d97", "#3fcfa8", "#e6a73c", "#e05a55"


# --------------------------------------------------------------------------- config
def migrate_old_names() -> None:
    """Folder names of the first (Turkish-only) version."""
    for old, new in ((ROOT / "profile" / "launcher-yedek", SAVE_BACKUPS), (HERE / "ini-yedek", INI_BACKUPS)):
        if old.is_dir() and not new.exists():
            try:
                old.rename(new)
            except OSError:
                pass
    for old in (HERE / "bos-klasor", HERE / "data"):
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
    cfg.setdefault("achievements", {})
    cfg["prompts"] = {"klavye": "keyboard", "playstation": "mod"}.get(cfg.get("prompts"), cfg.get("prompts"))
    if cfg["prompts"] not in prompts.PROMPT_SETS:
        cfg["prompts"] = "keyboard"
    return cfg


def save_config(cfg: dict) -> None:
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
        INI_BACKUPS.mkdir(exist_ok=True)
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
RES = ("1280x720", "1600x900", "1920x1080", "2560x1440", "3840x2160")


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
            ("window_size", "display", t("Window size", "Pencere boyutu"), "combo", RES, "1920x1080",
             t("When fullscreen is off.", "Tam ekran kapalıyken.")),
            ("output_res", "display", t("Game resolution", "Oyun çözünürlüğü"), "combo", RES, "1920x1080",
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


# --------------------------------------------------------------------------- key capture
VK_KEYS = {0x20: "space", 0x09: "tab", 0x0D: "enter", 0x08: "backspace", 0x14: "capslock", 0x2D: "insert",
           0x2E: "delete", 0x24: "home", 0x23: "end", 0x21: "pageup", 0x22: "pagedown", 0x26: "up", 0x28: "down",
           0x25: "left", 0x27: "right", 0x6B: "num_add", 0x6D: "num_sub", 0x6A: "num_mul", 0x6F: "num_div",
           0x6E: "num_decimal", 0xBD: "minus", 0xBB: "equals", 0xDB: "lbracket", 0xDD: "rbracket",
           0xBA: "semicolon", 0xDE: "apostrophe", 0xBC: "comma", 0xBE: "period", 0xBF: "slash",
           0xDC: "backslash", 0xC0: "grave", 0x71: "f2", 0x72: "f3", 0x73: "f4", 0x74: "f5", 0x75: "f6",
           0x76: "f7", 0x78: "f9", 0x7B: "f12"}
SIDE_KEYS = {"Shift_L": "lshift", "Shift_R": "rshift", "Control_L": "lctrl", "Control_R": "rctrl",
             "Alt_L": "lalt"}


def key_from_event(e) -> str | None:
    """A Tk key event as the game's key name (by Windows virtual-key code)."""
    if e.keysym in SIDE_KEYS:
        return SIDE_KEYS[e.keysym]
    vk = e.keycode
    if 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"num{vk - 0x60}"
    return VK_KEYS.get(vk)


# --------------------------------------------------------------------------- ui helpers
def btn(parent, text, cmd, kind="ghost", **kw):
    bg, fg, act = {"ghost": (PANEL, TXT, EDGE), "accent": (ACCENT, "#03140f", "#34b693"),
                   "warn": (PANEL, WARN, EDGE), "side": (SIDE, DIM, PANEL)}[kind]
    return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=act,
                     activeforeground=fg if kind != "side" else TXT, relief="flat", bd=0, cursor="hand2",
                     font=("Segoe UI Semibold" if kind == "accent" else "Segoe UI", 10), padx=14, pady=7, **kw)


def segmented(parent, options, current, command):
    """A row of toggle buttons: options = [(value, label)]."""
    for value, label in options:
        on = current == value
        tk.Button(parent, text=label, command=lambda v=value: command(v), relief="flat", bd=0, cursor="hand2",
                  bg=ACCENT if on else BG, fg="#03140f" if on else TXT, activebackground=EDGE,
                  activeforeground=TXT, padx=16, pady=7,
                  font=("Segoe UI Semibold" if on else "Segoe UI", 10)).pack(side="left", padx=(0, 2))


class Card(tk.Frame):
    def __init__(self, parent, title: str):
        super().__init__(parent, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        tk.Label(self, text=title, bg=PANEL, fg=DIM, font=("Segoe UI Semibold", 9), anchor="w").pack(
            fill="x", padx=16, pady=(12, 6))


class Scrollable(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=BG)
        win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(win, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel)

    def _wheel(self, e):
        try:
            if self.body.winfo_height() > self.canvas.winfo_height():
                self.canvas.yview_scroll(int(-e.delta / 60), "units")
        except tk.TclError:
            pass


# --------------------------------------------------------------------------- app
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        i18n.set_lang(self.cfg["lang"])
        self.proc: subprocess.Popen | None = None
        self.running = False
        self.preparing = False
        self.page = "home"
        self.vars: dict[str, tk.Variable] = {}
        self.binds = None
        self.capture = None
        root.title("TotK Launcher")
        root.configure(bg=BG)
        root.geometry("1060x720")
        root.minsize(920, 600)
        self._style()
        self._build()
        self.show("home")
        self._poll()
        self.check_achievements()
        self.root.bind_all("<KeyPress>", self._on_key)
        self.root.bind_all("<ButtonPress>", self._on_mouse)

    def _style(self):
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("TCombobox", fieldbackground=BG, background=PANEL, foreground=TXT, arrowcolor=TXT,
                     bordercolor=EDGE, lightcolor=EDGE, darkcolor=EDGE, padding=4)
        st.map("TCombobox", fieldbackground=[("readonly", BG)], foreground=[("readonly", TXT)],
               selectbackground=[("readonly", BG)], selectforeground=[("readonly", TXT)])
        st.configure("Horizontal.TScale", background=ACCENT, troughcolor=BG, bordercolor=PANEL,
                     lightcolor=ACCENT, darkcolor=ACCENT)
        st.configure("Vertical.TScrollbar", background=PANEL, troughcolor=BG, bordercolor=BG,
                     arrowcolor=DIM, lightcolor=PANEL, darkcolor=PANEL)
        self.root.option_add("*TCombobox*Listbox.background", PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", TXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", EDGE)

    def _build(self):
        side = tk.Frame(self.root, bg=SIDE, width=230)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="TOTK", bg=SIDE, fg=ACCENT, font=("Segoe UI Black", 24)).pack(
            anchor="w", padx=22, pady=(22, 0))
        tk.Label(side, text="Tears of the Kingdom", bg=SIDE, fg=DIM, font=("Segoe UI", 9)).pack(
            anchor="w", padx=23, pady=(0, 22))
        self.nav = {}
        for key, label in (("home", t("Home", "Ana sayfa")), ("settings", t("Settings", "Ayarlar")),
                           ("controls", t("Controls", "Kontroller")), ("saves", t("Saves", "Kayıtlar")),
                           ("achievements", t("Achievements", "Başarımlar")), ("cheats", t("Cheats", "Hileler"))):
            b = btn(side, "   " + label, lambda k=key: self.show(k), "side", anchor="w")
            b.pack(fill="x")
            self.nav[key] = b

        bottom = tk.Frame(side, bg=SIDE)
        bottom.pack(side="bottom", fill="x", padx=16, pady=16)
        st = tk.Frame(bottom, bg=SIDE)
        st.pack(fill="x", pady=(0, 10))
        self.dot = tk.Canvas(st, width=10, height=10, bg=SIDE, highlightthickness=0)
        self.dot.create_oval(1, 1, 9, 9, fill=DIM, outline="", tags="d")
        self.dot.pack(side="left", padx=(2, 8))
        self.status = tk.Label(st, text="", bg=SIDE, fg=DIM, font=("Segoe UI", 9))
        self.status.pack(side="left")
        self.play_btn = tk.Button(bottom, text="", command=self.play, bg=ACCENT, fg="#03140f",
                                  activebackground="#34b693", activeforeground="#03140f", relief="flat", bd=0,
                                  cursor="hand2", font=("Segoe UI Black", 15), pady=12)
        self.play_btn.pack(fill="x")
        self.mods_var = tk.BooleanVar(value=self.cfg["mods"])
        tk.Checkbutton(bottom, text=t("Load mods (romfs_mods)", "Yamalarla başlat (romfs_mods)"),
                       variable=self.mods_var, command=self._set_mods, bg=SIDE, fg=DIM, selectcolor=SIDE,
                       activebackground=SIDE, activeforeground=TXT, font=("Segoe UI", 9), anchor="w", bd=0,
                       highlightthickness=0).pack(fill="x", pady=(8, 0))
        self._show_state()

        self.main = Scrollable(self.root)
        self.main.pack(side="left", fill="both", expand=True)

    def rebuild(self):
        """Builds the whole window again (after a language change)."""
        for w in self.root.winfo_children():
            w.destroy()
        self._build()
        self.show(self.page)

    def show(self, page: str):
        self.page = page
        self.capture = None
        for k, b in self.nav.items():
            on = k == page
            b.configure(bg=PANEL if on else SIDE, fg=TXT if on else DIM,
                        font=("Segoe UI Semibold" if on else "Segoe UI", 10))
        for w in self.main.body.winfo_children():
            w.destroy()
        self.main.canvas.yview_moveto(0)
        {"home": self.page_home, "settings": self.page_settings, "controls": self.page_controls,
         "saves": self.page_saves, "achievements": self.page_achievements,
         "cheats": self.page_cheats}[page](self.main.body)

    def _title(self, p, title, sub=""):
        tk.Label(p, text=title, bg=BG, fg=TXT, font=("Segoe UI Black", 20), anchor="w").pack(
            fill="x", padx=28, pady=(24, 0))
        tk.Label(p, text=sub, bg=BG, fg=DIM, font=("Segoe UI", 9), anchor="w", justify="left",
                 wraplength=760).pack(fill="x", padx=28, pady=(0, 10))

    # -- home
    def page_home(self, p):
        self._banner(p)
        ini = read_ini()

        info = Card(p, t("STATUS", "DURUM"))
        info.pack(fill="x", padx=28, pady=6)
        mods, patches = mod_files(MODS), mod_files(PATCHES)
        on = self.cfg["mods"]
        rows = [
            (t("Game", "Oyun"), t("totk.exe found", "totk.exe bulundu") if EXE.exists()
             else t("totk.exe not found", "totk.exe bulunamadı"), ACCENT if EXE.exists() else BAD),
            (t("Version", "Sürüm"), installed_version(), TXT),
            (t("Graphics card", "Ekran kartı"), log_fact(r"vk: using gpu \d+: (.+)") or t("not known yet",
                                                                                         "henüz bilinmiyor"), TXT),
            (t("Mods", "Yamalar"), (t(f"{len(mods)} files · ", f"{len(mods)} dosya · ")
                                    + (t("on", "açık") if on else t("OFF", "KAPALI")))
             if mods else t("romfs_mods is empty", "romfs_mods boş"), ACCENT if mods and on else WARN),
            ("romfs-patches", t(f"{len(patches)} files (always on)", f"{len(patches)} dosya (hep açık)"), TXT),
            (t("Last start", "Son açılış"), log_fact(r"RomFS (ready: .+)") or "—", DIM),
        ]
        for label, value, color in rows:
            f = tk.Frame(info, bg=PANEL)
            f.pack(fill="x", padx=16, pady=2)
            tk.Label(f, text=label, bg=PANEL, fg=DIM, width=16, anchor="w", font=("Segoe UI", 9)).pack(side="left")
            tk.Label(f, text=value, bg=PANEL, fg=color, anchor="w", font=("Segoe UI Semibold", 9)).pack(side="left")
        tk.Frame(info, bg=PANEL, height=10).pack()

        quick = Card(p, t("QUICK FRAME RATE LIMIT", "HIZLI KARE SINIRI"))
        quick.pack(fill="x", padx=28, pady=6)
        row = tk.Frame(quick, bg=PANEL)
        row.pack(fill="x", padx=16, pady=(0, 14))
        fps = tk.StringVar(value=ini.get("fps_limit", "60"))
        for v in ("30", "60", "120", "144", "display"):
            tk.Radiobutton(row, text=v if v != "display" else t("Monitor", "Monitör"), value=v, variable=fps,
                           command=lambda: self._quick_fps(fps.get()), indicatoron=False, bg=BG, fg=TXT,
                           selectcolor=ACCENT, activebackground=EDGE, activeforeground=TXT, bd=0,
                           relief="flat", padx=16, pady=6, font=("Segoe UI", 10), cursor="hand2",
                           highlightthickness=0).pack(side="left", padx=(0, 6))

        log = Card(p, t("RECENT LOG (logs\\totk.log)", "SON LOG (logs\\totk.log)"))
        log.pack(fill="both", expand=True, padx=28, pady=6)
        self.logbox = tk.Text(log, height=10, bg="#0a0f12", fg="#a9bac3", bd=0, relief="flat",
                              font=("Consolas", 9), wrap="none", padx=8, pady=6)
        self.logbox.pack(fill="both", expand=True, padx=12)
        bar = tk.Frame(log, bg=PANEL)
        bar.pack(fill="x", padx=12, pady=10)
        btn(bar, t("Refresh", "Yenile"), self.refresh_log).pack(side="left")
        btn(bar, t("Log folder", "Log klasörü"), lambda: self.open(LOGS)).pack(side="left", padx=6)
        btn(bar, t("Game folder", "Oyun klasörü"), lambda: self.open(ROOT)).pack(side="left")
        btn(bar, t("Desktop shortcut", "Masaüstü kısayolu"), self.shortcut).pack(side="right")
        self.refresh_log()
        tk.Frame(p, bg=BG, height=18).pack()

    def _banner(self, p):
        c = tk.Canvas(p, height=130, bg=BG, highlightthickness=0)
        c.pack(fill="x", padx=28, pady=(24, 10))

        def draw(_=None):
            c.delete("all")
            w, h = max(c.winfo_width(), 400), 130
            for y in range(0, h, 2):
                f = y / h
                c.create_rectangle(0, y, w, y + 2, outline="",
                                   fill="#%02x%02x%02x" % (int(14 + 18 * f), int(30 + 30 * f), int(34 + 24 * f)))
            pts = [0, h]
            for i in range(13):
                pts += [w * i / 12, h - 26 - (i * 37 % 5) * 9]
            pts += [w, h]
            c.create_polygon(*pts, fill="#0b1315", outline="")
            for i in range(60):
                c.create_oval((i * 151) % w, (i * 47) % 70, (i * 151) % w + 2, (i * 47) % 70 + 2,
                              fill="#7fd9c0", outline="")
            c.create_text(26, 36, text="TEARS OF THE KINGDOM", anchor="w", fill="#eef6f3",
                          font=("Segoe UI Black", 22))
            c.create_text(28, 70, text="PC recomp · launcher", anchor="w", fill="#8fb8ad", font=("Segoe UI", 10))
        c.bind("<Configure>", draw)

    def _quick_fps(self, v: str):
        changes = {"fps_limit": v}
        if v not in ("30", "60"):
            changes["realtime"] = "1"
        write_ini(changes, SECTIONS)
        self.toast(t(f"Frame rate limit: {v}", f"Kare sınırı: {v}"))

    def refresh_log(self):
        if not getattr(self, "logbox", None) or not self.logbox.winfo_exists():
            return
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.insert("1.0", "\n".join(log_lines(60)) or t("No log yet.", "Henüz log yok."))
        self.logbox.see("end")
        self.logbox.xview_moveto(0)
        self.logbox.configure(state="disabled")

    # -- settings
    def page_settings(self, p):
        self._title(p, t("Settings", "Ayarlar"),
                    t("Written to totk.ini; a backup goes to launcher\\ini-backups before every save. The other "
                      "settings are in the game's F1 menu.",
                      "totk.ini'ye yazılır; her kayıttan önce launcher\\ini-backups klasörüne yedek alınır. "
                      "Diğer ayarlar oyunda F1 menüsünde."))
        launcher = Card(p, "LAUNCHER")
        launcher.pack(fill="x", padx=28, pady=6)
        row = tk.Frame(launcher, bg=PANEL)
        row.pack(fill="x", padx=16, pady=(0, 14))
        tk.Label(row, text=t("Interface language", "Arayüz dili"), bg=PANEL, fg=TXT, font=("Segoe UI", 10),
                 anchor="w").pack(side="left", fill="x", expand=True)
        seg = tk.Frame(row, bg=PANEL)
        seg.pack(side="right")
        segmented(seg, i18n.LANGS, self.cfg["lang"], self._set_lang)

        ini = read_ini()
        self.vars = {}
        gpus = gpus_from_log()
        for title, items in setting_groups():
            card = Card(p, title)
            card.pack(fill="x", padx=28, pady=6)
            for key, _sec, label, kind, choices, default, help_ in items:
                self._setting_row(card, key, label, kind, choices, ini.get(key, default), help_, gpus)
            tk.Frame(card, bg=PANEL, height=8).pack()
        bar = tk.Frame(p, bg=BG)
        bar.pack(fill="x", padx=28, pady=(10, 28))
        btn(bar, t("Save", "Kaydet"), self.save_settings, "accent").pack(side="right")
        btn(bar, t("Reset to defaults", "Varsayılanlara dön"), self.reset_settings).pack(side="right", padx=8)
        btn(bar, t("Open totk.ini", "totk.ini'yi aç"),
            lambda: os.startfile(INI) if INI.exists() else None).pack(side="left")

    def _set_lang(self, code):
        self._cfg("lang", code)
        i18n.set_lang(code)
        self.rebuild()

    def _setting_row(self, card, key, label, kind, choices, value, help_, gpus):
        f = tk.Frame(card, bg=PANEL)
        f.pack(fill="x", padx=16, pady=5)
        left = tk.Frame(f, bg=PANEL)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=label, bg=PANEL, fg=TXT, font=("Segoe UI", 10), anchor="w").pack(fill="x")
        if help_:
            tk.Label(left, text=help_, bg=PANEL, fg=DIM, font=("Segoe UI", 8), anchor="w", justify="left",
                     wraplength=480).pack(fill="x")
        if kind == "bool":
            var = tk.BooleanVar(value=value not in ("", "0", "false", "off"))
            tk.Checkbutton(f, variable=var, bg=PANEL, fg=ACCENT, activebackground=PANEL, activeforeground=ACCENT,
                           selectcolor=BG, bd=0, highlightthickness=0, cursor="hand2").pack(side="right")
        elif kind == "scale":
            var = tk.IntVar(value=int(value) if str(value).lstrip("-").isdigit() else int(choices[0]))
            tk.Label(f, textvariable=var, bg=PANEL, fg=TXT, width=4, font=("Segoe UI Semibold", 10)).pack(
                side="right")
            ttk.Scale(f, from_=choices[0], to=choices[1], orient="horizontal", length=200,
                      value=var.get(), command=lambda v, vv=var: vv.set(round(float(v)))).pack(side="right")
        elif kind == "gpu":
            auto = t("Automatic", "Otomatik")
            names = [auto] + [f"{i}: {n}" for i, n in gpus]
            cur = next((n for n in names[1:] if n.split(":")[0] == value), auto if not value else value)
            var = tk.StringVar(value=cur)
            ttk.Combobox(f, textvariable=var, values=names, state="readonly", width=34).pack(side="right")
        else:
            var = tk.StringVar(value=value)
            ttk.Combobox(f, textvariable=var, values=list(choices), width=14,
                         state="readonly" if kind == "choice" else "normal").pack(side="right")
        self.vars[key] = var

    def _collect(self) -> dict[str, str | None] | None:
        out: dict[str, str | None] = {}
        for _, items in setting_groups():
            for key, _sec, label, kind, *_rest in items:
                v = self.vars[key].get()
                if kind == "bool":
                    v = "1" if v else "0"
                elif kind == "gpu":
                    v = None if v == t("Automatic", "Otomatik") else v.split(":")[0].strip()
                else:
                    v = str(v).strip()
                    if kind == "combo" and key != "render_scale" and not re.fullmatch(r"\d{3,4}x\d{3,4}", v):
                        messagebox.showerror("TotK", t(f"{label}: use the form 1920x1080.",
                                                       f"{label}: 1920x1080 biçiminde olmalı."))
                        return None
                    if key == "render_scale" and v != "game" and not (v.isdigit() and 25 <= int(v) <= 400):
                        messagebox.showerror("TotK", t(f"{label}: 'game' or a number from 25 to 400.",
                                                       f"{label}: 'game' ya da 25-400 arası bir sayı olmalı."))
                        return None
                out[key] = v
        return out

    def save_settings(self):
        new = self._collect()
        if new is None:
            return
        cur = read_ini()
        changes = {k: v for k, v in new.items() if cur.get(k) != v and not (v is None and k not in cur)}
        if not changes:
            return self.toast(t("No changes", "Değişiklik yok"))
        write_ini(changes, SECTIONS)
        n = len(changes)
        self.toast(t(f"{n} settings saved", f"{n} ayar kaydedildi")
                   + (t(" · some apply when the game restarts", " · bazıları oyun yeniden açılınca geçerli")
                      if self.running else ""))

    def reset_settings(self):
        if not messagebox.askyesno("TotK", t("Remove the settings of this page from totk.ini and go back to the "
                                             "game's defaults?",
                                             "Bu sayfadaki ayarlar totk.ini'den silinip oyunun varsayılanlarına "
                                             "dönülsün mü?")):
            return
        write_ini({k: None for k in SECTIONS}, SECTIONS)
        self.show("settings")
        self.toast(t("Back to defaults", "Varsayılanlara dönüldü"))

    # -- saves
    def page_saves(self, p):
        self._title(p, t("Saves", "Kayıtlar"), t("Game saves: profile\\save. Backups: profile\\launcher-backups.",
                                                 "Oyun kayıtları: profile\\save. Yedekler: "
                                                 "profile\\launcher-backups."))
        opts = Card(p, t("AUTOMATIC BACKUP", "OTOMATİK YEDEK"))
        opts.pack(fill="x", padx=28, pady=6)
        row = tk.Frame(opts, bg=PANEL)
        row.pack(fill="x", padx=16, pady=(0, 14))
        auto = tk.BooleanVar(value=self.cfg["backup_before_play"])
        tk.Checkbutton(row, text=t("Back up the saves before every launch", "Her OYNA'da önce kayıtları yedekle"),
                       variable=auto, command=lambda: self._cfg("backup_before_play", auto.get()), bg=PANEL,
                       fg=TXT, selectcolor=PANEL, activebackground=PANEL, activeforeground=TXT, bd=0,
                       highlightthickness=0, font=("Segoe UI", 10)).pack(side="left")
        keep = tk.IntVar(value=self.cfg["backup_keep"])
        tk.Label(row, text=t("   automatic backups kept:", "   saklanacak otomatik yedek:"), bg=PANEL, fg=DIM,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Spinbox(row, from_=1, to=100, textvariable=keep, width=4, bg=BG, fg=TXT, buttonbackground=PANEL,
                   relief="flat", insertbackground=TXT,
                   command=lambda: self._cfg("backup_keep", keep.get())).pack(side="left", padx=6)
        close = tk.BooleanVar(value=self.cfg["close_on_play"])
        row2 = tk.Frame(opts, bg=PANEL)
        row2.pack(fill="x", padx=16, pady=(0, 14))
        tk.Checkbutton(row2, text=t("Close the launcher when the game starts", "Oyun açılınca launcher'ı kapat"),
                       variable=close, command=lambda: self._cfg("close_on_play", close.get()), bg=PANEL, fg=TXT,
                       selectcolor=PANEL, activebackground=PANEL, activeforeground=TXT, bd=0,
                       highlightthickness=0, font=("Segoe UI", 10)).pack(side="left")

        bar = tk.Frame(p, bg=BG)
        bar.pack(fill="x", padx=28, pady=6)
        btn(bar, t("Back up now", "Şimdi yedekle"), self.manual_backup, "accent").pack(side="left")
        btn(bar, t("Save folder", "Kayıt klasörü"), lambda: self.open(SAVE)).pack(side="left", padx=6)
        btn(bar, t("Backup folder", "Yedek klasörü"), lambda: self.open(SAVE_BACKUPS)).pack(side="left")

        lst = Card(p, t("BACKUPS", "YEDEKLER"))
        lst.pack(fill="x", padx=28, pady=(6, 28))
        backups = list_backups()
        if not backups:
            tk.Label(lst, text=t("No backups yet.", "Henüz yedek yok."), bg=PANEL, fg=DIM, font=("Segoe UI", 9),
                     anchor="w").pack(fill="x", padx=16, pady=(0, 14))
        for b in backups[:40]:
            f = tk.Frame(lst, bg=PANEL)
            f.pack(fill="x", padx=16, pady=2)
            tk.Label(f, text=b.name, bg=PANEL, fg=TXT, font=("Segoe UI", 10), anchor="w").pack(side="left")
            tk.Label(f, text=f"{dir_size(b) / 1048576:.1f} MiB", bg=PANEL, fg=DIM, font=("Segoe UI", 8)).pack(
                side="left", padx=10)
            btn(f, t("Delete", "Sil"), lambda bb=b: self.delete_backup(bb)).pack(side="right")
            btn(f, t("Restore", "Geri yükle"), lambda bb=b: self.restore(bb), "warn").pack(side="right", padx=6)
        tk.Frame(lst, bg=PANEL, height=10).pack()

    def manual_backup(self):
        d = backup_saves("manual", 0)
        self.toast(t(f"Backed up: {d.name}", f"Yedeklendi: {d.name}") if d
                   else t("No saves to back up", "Yedeklenecek kayıt yok"))
        self.show("saves")

    def restore(self, b: Path):
        if self.running:
            return messagebox.showwarning("TotK", t("Close the game first.", "Önce oyunu kapatın."))
        if not messagebox.askyesno("TotK", t(f"Restore '{b.name}'?\n\nThe current saves are backed up first as "
                                             "'before-restore'.",
                                             f"'{b.name}' geri yüklensin mi?\n\nŞu anki kayıtlar önce "
                                             "'before-restore' adıyla yedeklenir.")):
            return
        backup_saves("before-restore", 0)
        if SAVE.exists():
            shutil.rmtree(SAVE)
        shutil.copytree(b, SAVE)
        self.toast(t("Restored", "Geri yüklendi"))
        self.show("saves")

    def delete_backup(self, b: Path):
        if messagebox.askyesno("TotK", t(f"Delete the backup '{b.name}'?", f"'{b.name}' yedeği silinsin mi?")):
            shutil.rmtree(b, ignore_errors=True)
            self.show("saves")

    # -- controls
    def prompt_options(self):
        return [("keyboard", t("Keyboard and mouse", "Klavye ve fare")), ("switch", "Switch"),
                ("mod", t("Mod icons", "Mod simgeleri"))]

    def pad_layouts(self):
        return [("auto", t("Automatic", "Otomatik")), ("nintendo", t("Nintendo (by position)",
                                                                       "Nintendo (konuma göre)")),
                ("xbox", t("Xbox (by label)", "Xbox (etikete göre)"))]

    def page_controls(self, p):
        self._title(p, t("Controls", "Kontroller"),
                    t("Keyboard, mouse and controller: each has its own buttons and they work together.",
                      "Klavye, fare ve kumanda: her birinin kendi düğmeleri vardır ve birlikte çalışır."))
        ini = read_ini()
        if self.binds is None:
            self.binds = prompts.parse_binds(ini)
        self.capture = None

        top = Card(p, t("PROMPTS AND DEVICES", "SİMGELER VE CİHAZ"))
        top.pack(fill="x", padx=28, pady=6)

        def row(label, help_=""):
            f = tk.Frame(top, bg=PANEL)
            f.pack(fill="x", padx=16, pady=(4, 12))
            tk.Label(f, text=label, bg=PANEL, fg=TXT, font=("Segoe UI", 10), width=18, anchor="nw").pack(
                side="left", anchor="n", pady=(6, 0))
            right = tk.Frame(f, bg=PANEL)
            right.pack(side="left", fill="x", expand=True)
            body = tk.Frame(right, bg=PANEL)
            body.pack(fill="x", anchor="w")
            if help_:
                tk.Label(right, text=help_, bg=PANEL, fg=DIM, font=("Segoe UI", 8), anchor="w", justify="left",
                         wraplength=560).pack(fill="x", pady=(4, 0))
            return right, body

        right, seg = row(t("Button prompts", "Tuş simgeleri"),
                         t("The button icons in the game. With keyboard and mouse they are drawn from the bindings "
                           "below (the first key is shown), the action prompt and the letters around it included, "
                           "and updated on every launch. Mod icons: the icons of the font in romfs_mods.",
                           "Oyundaki düğme simgeleri. Klavye ve fare seçiliyken simgeler aşağıdaki atamalardan "
                           "çizilir (ilk tuş gösterilir; aksiyon simgesi ve çevresindeki harfler dahil) ve her "
                           "OYNA'da güncellenir. Mod simgeleri: romfs_mods'taki fontun simgeleri."))
        options = self.prompt_options()
        if not (self.cfg["mods"] and prompts.mod_prompts_available()):
            options = options[:2]
        segmented(seg, options, self.cfg["prompts"], self._set_prompts)
        if not prompts.prompts_available():
            tk.Label(seg, text=t("  RomFS not found: prompts cannot be changed",
                                 "  RomFS bulunamadı: simgeler değiştirilemez"), bg=PANEL, fg=WARN,
                     font=("Segoe UI", 9)).pack(side="left")
        self.preview_box = tk.Label(right, bg=PANEL, text=t("Preparing preview…", "Önizleme hazırlanıyor…"),
                                    fg=DIM, font=("Segoe UI", 9), anchor="w")
        self.preview_box.pack(fill="x", pady=(10, 0))
        self.root.after(50, self._preview)

        _, pad = row(t("Controller layout", "Kumanda düzeni"),
                     t("Nintendo: buttons by position (A on the right). Xbox: the bottom button is A. Automatic: "
                       "Nintendo for pads with Nintendo labels, Xbox for the others.",
                       "Nintendo: düğmeler konumuna göre (sağdaki A). Xbox: alttaki düğme A. Otomatik: Nintendo "
                       "etiketli kumandalarda Nintendo, diğerlerinde Xbox."))
        layouts = self.pad_layouts()
        names = [n for _, n in layouts]
        self.pad_layout = tk.StringVar(value=dict(layouts).get(ini.get("pad_layout", "auto"), names[0]))
        ttk.Combobox(pad, textvariable=self.pad_layout, values=names, state="readonly", width=26).pack(side="left")

        _, sens = row(t("Mouse camera", "Fare kamerası"),
                      t("Camera sensitivity with the mouse, 0 to 10. 0 turns the mouse camera and cursor capture "
                        "off. Applies while the game runs.",
                        "Fareyle kamera hassasiyeti, 0-10. 0 fare kamerasını ve imleç yakalamayı kapatır. Oyun "
                        "açıkken de hemen uygulanır."))
        cur = ini.get("mouse_sens", "1")
        self.mouse_sens = tk.IntVar(value=int(cur) if cur.isdigit() else 1)
        ttk.Scale(sens, from_=0, to=10, orient="horizontal", length=260, value=self.mouse_sens.get(),
                  command=lambda v: self.mouse_sens.set(round(float(v)))).pack(side="left")
        tk.Label(sens, textvariable=self.mouse_sens, bg=PANEL, fg=TXT, width=4,
                 font=("Segoe UI Semibold", 10)).pack(side="left")

        tk.Label(p, text=t("Click a cell, then press a key or click a mouse button; Esc cancels. Right-click clears "
                           "a cell. A key used by another button moves here. Movement and camera directions take "
                           "keys only.",
                           "Bir hücreye tıklayın, ardından bir tuşa basın ya da bir fare düğmesine tıklayın; Esc "
                           "iptal eder. Sağ tık hücreyi temizler. Başka bir düğmede kullanılan tuş buraya taşınır. "
                           "Hareket ve kamera yönlerine yalnızca tuş atanabilir."),
                 bg=BG, fg=DIM, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=720).pack(
            fill="x", padx=28, pady=(12, 4))

        self.cells = {}
        self.pad_vars = {}
        default, none = t("Default", "Varsayılan"), t("None", "Yok")
        pad_names = [default, none] + [prompts.pad_label(n) for n in prompts.PAD_NAMES]
        group = grid = None
        r = 0
        for b, g, desc, _defaults, _pad in prompts.BUTTONS:
            if g != group:
                group = g
                card = Card(p, t(*g).upper())
                card.pack(fill="x", padx=28, pady=6)
                grid = tk.Frame(card, bg=PANEL)
                grid.pack(fill="x", padx=16, pady=(0, 12))
                grid.columnconfigure(0, weight=1)
                for c in (1, 2, 3):
                    grid.columnconfigure(c, minsize=150, uniform="cells")
                for c, head in enumerate((t("Key 1", "Tuş 1"), t("Key 2", "Tuş 2"), t("Controller", "Kumanda")),
                                         start=1):
                    tk.Label(grid, text=head, bg=PANEL, fg=DIM, font=("Segoe UI", 8)).grid(row=0, column=c)
                r = 1
            tk.Label(grid, text=t(*desc), bg=PANEL, fg=TXT, font=("Segoe UI", 10), anchor="w").grid(
                row=r, column=0, sticky="we", pady=3)
            for i in (0, 1):
                cell = tk.Label(grid, text="", bg=BG, fg=TXT, pady=5, cursor="hand2", font=("Segoe UI", 9),
                                highlightthickness=1, highlightbackground=EDGE)
                cell.grid(row=r, column=1 + i, sticky="we", padx=3, pady=3)
                cell.bind("<ButtonRelease-1>", lambda e, bb=b, ii=i: self._start_capture(bb, ii))
                cell.bind("<Button-3>", lambda e, bb=b, ii=i: self._clear_cell(bb, ii))
                self.cells[(b, i)] = cell
            if b in prompts.STICK_DIRS:
                tk.Label(grid, text=t("Left stick", "Sol çubuk") if b.startswith("L") else t("Right stick",
                                                                                            "Sağ çubuk"),
                         bg=PANEL, fg=DIM, font=("Segoe UI", 9)).grid(row=r, column=3, sticky="we", padx=3)
            else:
                cur = self.binds[b]["pad"]
                var = tk.StringVar(value=default if cur == "default" else none if cur == "none"
                                   else prompts.pad_label(cur))
                ttk.Combobox(grid, textvariable=var, values=pad_names, state="readonly", width=12).grid(
                    row=r, column=3, sticky="we", padx=3)
                self.pad_vars[b] = var
            r += 1
        self._refresh_cells()

        bar = tk.Frame(p, bg=BG)
        bar.pack(fill="x", padx=28, pady=(10, 28))
        btn(bar, t("Save", "Kaydet"), self.save_controls, "accent").pack(side="right")
        btn(bar, t("Reset all bindings", "Tüm tuşları sıfırla"), self.reset_controls).pack(side="right", padx=8)
        btn(bar, t("Undo unsaved changes", "Kaydedilmemişleri geri al"), self._reload_controls).pack(side="left")

    def _preview(self):
        if not getattr(self, "preview_box", None) or not self.preview_box.winfo_exists():
            return
        box, prompt_set, binds, use_mods = self.preview_box, self.cfg["prompts"], self.binds, self.cfg["mods"]
        binds = json.loads(json.dumps(binds))

        def work():
            try:
                result = prompts.strip(prompt_set, binds, use_mods, TXT, PANEL)
            except Exception as e:  # noqa: BLE001 - shown in the box
                result = e
            self.root.after(0, lambda: show(result))

        def show(result):
            if not box.winfo_exists():
                return
            if isinstance(result, Exception):
                box.configure(text=t(f"No preview: {result}", f"Önizleme yok: {result}"), image="")
                return
            from PIL import ImageTk
            self._preview_img = ImageTk.PhotoImage(result)
            box.configure(image=self._preview_img, text="")
        threading.Thread(target=work, daemon=True).start()

    def _set_prompts(self, value):
        self._cfg("prompts", value)
        self._rerender_controls()

    def _rerender_controls(self):
        y = self.main.canvas.yview()[0]
        self.show("controls")
        self.root.update_idletasks()
        self.main.canvas.yview_moveto(y)

    def _refresh_cells(self):
        for (b, i), cell in self.cells.items():
            keys = self.binds[b]["keys"]
            capturing = self.capture == (b, i)
            text = t("Press a key…", "Bir tuşa basın…") if capturing else (
                prompts.key_label(keys[i]) if i < len(keys) else "—")
            cell.configure(text=text, fg=ACCENT if capturing else (TXT if i < len(keys) else DIM),
                           highlightbackground=ACCENT if capturing else EDGE)

    def _start_capture(self, b, i):
        self.capture = (b, i)
        self._capture_armed = False
        self._refresh_cells()
        self.root.after(150, lambda: setattr(self, "_capture_armed", True))

    def _clear_cell(self, b, i):
        if self.capture:
            return
        keys = self.binds[b]["keys"]
        if i < len(keys):
            del keys[i]
        self._refresh_cells()
        self._preview()

    def _assign(self, key):
        b, i = self.capture
        self.capture = None
        moved = []
        for other, data in self.binds.items():
            if other != b and key in data["keys"]:
                data["keys"].remove(key)
                moved.append(other)
        keys = [k for k in self.binds[b]["keys"] if k != key]
        if i < len(keys):
            keys[i] = key
        else:
            keys.append(key)
        self.binds[b]["keys"] = keys
        self._refresh_cells()
        self._preview()
        if moved:
            names = {bb: t(*d) for bb, _g, d, *_r in prompts.BUTTONS}
            self.toast(t(f"{prompts.key_label(key)} moved from: ", f"{prompts.key_label(key)} şuradan taşındı: ")
                       + ", ".join(names[m] for m in moved))

    def _on_key(self, e):
        if not self.capture or self.page != "controls":
            return None
        if e.keysym == "Escape":
            self.capture = None
            self._refresh_cells()
            return "break"
        key = key_from_event(e)
        if key:
            self._assign(key)
        else:
            self.toast(t(f"The game cannot use this key ({e.keysym})", f"Bu tuş oyunda kullanılamaz ({e.keysym})"))
        return "break"

    def _on_mouse(self, e):
        if not self.capture or self.page != "controls" or not getattr(self, "_capture_armed", False):
            return None
        key = {1: "mouse_l", 2: "mouse_m", 3: "mouse_r"}.get(e.num)
        if not key:
            return None
        if self.capture[0] in prompts.STICK_DIRS:
            self.toast(t("Movement and camera directions take keys only",
                         "Hareket ve kamera yönlerine yalnızca tuş atanabilir"))
            self.capture = None
            self._refresh_cells()
            return "break"
        self._assign(key)
        return "break"

    def _collect_controls(self) -> dict[str, str | None]:
        rev = {prompts.pad_label(k): k for k in prompts.PAD_NAMES}
        default, none = t("Default", "Varsayılan"), t("None", "Yok")
        changes: dict[str, str | None] = {}
        for b in prompts.DEFAULT_KEYS:
            pad = "default"
            if b in self.pad_vars:
                v = self.pad_vars[b].get()
                pad = "default" if v == default else "none" if v == none else rev[v]
            self.binds[b]["pad"] = pad
            changes["bind_" + b.lower()] = prompts.bind_line(b, self.binds[b]["keys"], pad)
        changes["pad_layout"] = {n: k for k, n in self.pad_layouts()}[self.pad_layout.get()]
        changes["mouse_sens"] = str(self.mouse_sens.get())
        return changes

    def save_controls(self):
        changes = self._collect_controls()
        cur = read_ini()
        changes = {k: v for k, v in changes.items() if cur.get(k) != v and not (v is None and k not in cur)}
        if not changes:
            return self.toast(t("No changes", "Değişiklik yok"))
        write_ini(changes, {**SECTIONS, **{k: "input" for k in changes}})
        self.binds = None
        self._rerender_controls()
        self.toast(t("Controls saved", "Kontroller kaydedildi")
                   + (t(" · prompts update on the next game start",
                        " · simgeler oyunun bir sonraki açılışında güncellenir") if self.running else ""))

    def reset_controls(self):
        if not messagebox.askyesno("TotK", t("Reset every key and controller binding to the game's defaults?",
                                             "Tüm tuş ve kumanda atamaları oyunun varsayılanlarına dönsün mü?")):
            return
        write_ini({"bind_" + b.lower(): None for b in prompts.DEFAULT_KEYS}, SECTIONS)
        self.binds = None
        self._rerender_controls()
        self.toast(t("Bindings reset", "Atamalar sıfırlandı"))

    def _reload_controls(self):
        self.binds = None
        self._rerender_controls()

    # -- achievements
    def check_achievements(self, announce=True):
        """Reads the saves in the background; new unlocks are recorded and shown."""
        def work():
            unlocked = dict(self.cfg.get("achievements", {}))
            first = not unlocked
            try:
                best, new = achievements.evaluate(SAVE, unlocked)
            except Exception:  # noqa: BLE001 - a broken save must not stop the launcher
                return
            self.root.after(0, lambda: done(best, new, unlocked, first))

        def done(best, new, unlocked, first):
            self.ach_stats = best
            if new:
                self._cfg("achievements", unlocked)
                if announce and first and len(new) > 1:
                    # first look at existing progress: one summary instead of a popup per achievement
                    self.toast(t(f"{len(new)} achievements unlocked from your saves",
                                 f"Kayıtlarından {len(new)} başarım açıldı"))
                elif announce:
                    for i, aid in enumerate(new[:5]):
                        self.root.after(i * 4200, lambda a=aid: self.unlock_popup(a))
                    if len(new) > 5:
                        self.root.after(5 * 4200, lambda: self.toast(
                            t(f"+{len(new) - 5} more achievements", f"+{len(new) - 5} başarım daha")))
            if self.page == "achievements":
                self._rerender("achievements")
        threading.Thread(target=work, daemon=True).start()

    def unlock_popup(self, aid):
        a = next(x for x in achievements.ACHIEVEMENTS if x[0] == aid)
        box = tk.Frame(self.root, bg=PANEL, highlightbackground=ACCENT, highlightthickness=1)
        tk.Label(box, text=a[2], bg=ACCENT, fg="#03140f", font=("Segoe UI Symbol", 18), width=2).pack(
            side="left", fill="y", ipadx=8)
        right = tk.Frame(box, bg=PANEL)
        right.pack(side="left", padx=12, pady=8)
        tk.Label(right, text=t("ACHIEVEMENT UNLOCKED", "BAŞARIM AÇILDI"), bg=PANEL, fg=ACCENT,
                 font=("Segoe UI Semibold", 8), anchor="w").pack(fill="x")
        tk.Label(right, text=t(*a[3]), bg=PANEL, fg=TXT, font=("Segoe UI Semibold", 11), anchor="w").pack(fill="x")
        tk.Label(right, text=t(*a[4]), bg=PANEL, fg=DIM, font=("Segoe UI", 8), anchor="w").pack(fill="x")
        box.place(relx=1.0, rely=1.0, anchor="se", x=-24, y=-24)
        self.root.after(4000, box.destroy)

    def page_achievements(self, p):
        unlocked = self.cfg.get("achievements", {})
        best = getattr(self, "ach_stats", None)
        total = len(achievements.ACHIEVEMENTS)
        self._title(p, t("Achievements", "Başarımlar"),
                    t("Read from your save files after every game session. Saves made before reaching the Great Sky "
                      "Island don't count; once unlocked, an achievement stays unlocked.",
                      "Her oyun oturumundan sonra kayıt dosyalarından okunur. Gökyüzü Adası'na çıkmadan önceki "
                      "kayıtlar sayılmaz; açılan başarım açık kalır."))

        top = Card(p, t("PROGRESS", "İLERLEME"))
        top.pack(fill="x", padx=28, pady=6)
        row = tk.Frame(top, bg=PANEL)
        row.pack(fill="x", padx=16, pady=(0, 14))
        n = sum(1 for a in achievements.ACHIEVEMENTS if a[0] in unlocked)
        tk.Label(row, text=f"{n} / {total}", bg=PANEL, fg=TXT, font=("Segoe UI Black", 20)).pack(side="left")
        bar = tk.Canvas(row, height=10, bg=BG, highlightthickness=0)
        bar.pack(side="left", fill="x", expand=True, padx=16)
        bar.bind("<Configure>", lambda e, c=bar, f=n / total: (c.delete("all"), c.create_rectangle(
            0, 0, e.width * f, 10, fill=ACCENT, outline="")))
        tk.Label(row, text=f"{round(100 * n / total)}%", bg=PANEL, fg=ACCENT, font=("Segoe UI Semibold", 12)).pack(
            side="left")
        btn(row, t("Check now", "Şimdi kontrol et"), lambda: self.check_achievements()).pack(side="right", padx=(16, 0))

        filt = tk.Frame(p, bg=BG)
        filt.pack(fill="x", padx=28, pady=(8, 2))
        cur = getattr(self, "ach_filter", "all")
        segmented(filt, [("all", t("All", "Tümü"))] + [(c, t(*name)) for c, name in achievements.CATEGORIES]
                  + [("locked", t("Locked", "Kilitli"))], cur, self._set_ach_filter)

        grid = tk.Frame(p, bg=BG)
        grid.pack(fill="x", padx=22, pady=(6, 28))
        grid.columnconfigure(0, weight=1, uniform="ach")
        grid.columnconfigure(1, weight=1, uniform="ach")
        shown = [a for a in achievements.ACHIEVEMENTS
                 if cur == "all" or a[1] == cur or (cur == "locked" and a[0] not in unlocked)]
        if best is None:
            tk.Label(grid, text=t("Reading the saves…", "Kayıtlar okunuyor…"), bg=BG, fg=DIM,
                     font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", padx=6)
        for i, (aid, _cat, icon, title, desc, stat, target) in enumerate(shown):
            done = aid in unlocked
            card = tk.Frame(grid, bg=PANEL, highlightbackground=ACCENT if done else EDGE, highlightthickness=1)
            card.grid(row=i // 2 + 1, column=i % 2, sticky="nsew", padx=6, pady=6)
            tk.Label(card, text=icon, bg=ACCENT if done else BG, fg="#03140f" if done else DIM,
                     font=("Segoe UI Symbol", 18), width=2).pack(side="left", fill="y", ipadx=8)
            body = tk.Frame(card, bg=PANEL)
            body.pack(side="left", fill="both", expand=True, padx=12, pady=10)
            tk.Label(body, text=t(*title), bg=PANEL, fg=TXT if done else DIM, font=("Segoe UI Semibold", 11),
                     anchor="w").pack(fill="x")
            tk.Label(body, text=t(*desc), bg=PANEL, fg=DIM, font=("Segoe UI", 8), anchor="w", justify="left",
                     wraplength=330).pack(fill="x")
            if done:
                tk.Label(body, text=t(f"Unlocked {unlocked[aid]}", f"Açıldı: {unlocked[aid]}"), bg=PANEL, fg=ACCENT,
                         font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=(4, 0))
            elif target > 1 and best is not None:
                value = min(best.get(stat, 0), target)
                prog = tk.Frame(body, bg=PANEL)
                prog.pack(fill="x", pady=(6, 0))
                shown_value = f"{value:g}" if isinstance(value, float) else str(value)
                tk.Label(prog, text=f"{shown_value} / {target:g}", bg=PANEL, fg=DIM, font=("Segoe UI", 8)).pack(
                    side="right", padx=(8, 0))
                c = tk.Canvas(prog, height=6, width=60, bg=BG, highlightthickness=0)
                c.pack(side="left", fill="x", expand=True)
                c.bind("<Configure>", lambda e, cv=c, f=value / target: (cv.delete("all"), cv.create_rectangle(
                    0, 0, e.width * f, 6, fill=DIM, outline="")))
        tk.Label(p, text=t("Flag lists: the TotK savegame editor by Marc Robledo and its researchers (MIT).",
                           "Bayrak listeleri: Marc Robledo'nun TotK kayıt editörü ve araştırmacıları (MIT)."),
                 bg=BG, fg=DIM, font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=28, pady=(0, 20))

    def _set_ach_filter(self, value):
        self.ach_filter = value
        self._rerender("achievements")

    def _rerender(self, page):
        y = self.main.canvas.yview()[0]
        self.show(page)
        self.root.update_idletasks()
        self.main.canvas.yview_moveto(y)

    # -- cheats
    def page_cheats(self, p):
        self._title(p, t("Cheats", "Hileler"),
                    t("Edits the save file (progress.sav). Works while the game is closed; the saves are backed up "
                      "before every change.",
                      "Kayıt dosyasını (progress.sav) düzenler. Oyun kapalıyken çalışır; her değişiklikten önce "
                      "kayıtlar yedeklenir."))
        slots = save_slots()
        if not slots:
            card = Card(p, t("SAVE", "KAYIT"))
            card.pack(fill="x", padx=28, pady=6)
            tk.Label(card, text=t("No save found. Save once in the game first.",
                                  "Kayıt bulunamadı. Önce oyunda bir kez kaydedin."), bg=PANEL, fg=WARN,
                     font=("Segoe UI", 10), anchor="w").pack(fill="x", padx=16, pady=(0, 14))
            return
        if self.running:
            warn = tk.Frame(p, bg=PANEL, highlightbackground=WARN, highlightthickness=1)
            warn.pack(fill="x", padx=28, pady=6)
            tk.Label(warn, text=t("The game is running. Close it to apply cheats; values written while it runs are "
                                  "lost when it saves.",
                                  "Oyun çalışıyor. Hileleri uygulamak için oyunu kapatın; açıkken yazılan değerler "
                                  "oyun kaydedince silinir."), bg=PANEL, fg=WARN, font=("Segoe UI", 10),
                     anchor="w", justify="left", wraplength=640).pack(fill="x", padx=16, pady=12)

        pick = Card(p, t("SAVE SLOT", "KAYIT YUVASI"))
        pick.pack(fill="x", padx=28, pady=6)
        fmt = t("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M")
        labels = [f"{s.name}  ·  {time.strftime(fmt, time.localtime((s / 'progress.sav').stat().st_mtime))}"
                  for s in slots]
        cur = getattr(self, "cheat_slot", None)
        slot_var = tk.StringVar(value=labels[[str(s) for s in slots].index(cur)] if cur in map(str, slots)
                                else labels[0])
        row = tk.Frame(pick, bg=PANEL)
        row.pack(fill="x", padx=16, pady=(0, 14))
        tk.Label(row, text=t("Most recently saved first.", "En son kaydedilen en üstte."), bg=PANEL, fg=DIM,
                 font=("Segoe UI", 9)).pack(side="left")
        box = ttk.Combobox(row, textvariable=slot_var, values=labels, state="readonly", width=30)
        box.pack(side="right")

        def changed(_=None):
            self.cheat_slot = str(slots[labels.index(slot_var.get())])
            self.show("cheats")
        box.bind("<<ComboboxSelected>>", changed)
        slot = slots[labels.index(slot_var.get())]

        try:
            values = read_cheats(slot)
        except (OSError, ValueError) as e:
            tk.Label(p, text=t(f"Could not read the save: {e}", f"Kayıt okunamadı: {e}"), bg=BG, fg=BAD,
                     font=("Segoe UI", 10)).pack(padx=28, anchor="w")
            return

        card = Card(p, t("VALUES", "DEĞERLER"))
        card.pack(fill="x", padx=28, pady=6)
        self.cheat_vars = {}
        self.cheat_now = values
        for key, _name, _kind, _unit, top, label, help_ in cheats():
            if key not in values:
                continue
            f = tk.Frame(card, bg=PANEL)
            f.pack(fill="x", padx=16, pady=5)
            left = tk.Frame(f, bg=PANEL)
            left.pack(side="left", fill="x", expand=True)
            tk.Label(left, text=label, bg=PANEL, fg=TXT, font=("Segoe UI", 10), anchor="w").pack(fill="x")
            tk.Label(left, text=t(f"Now: {values[key]:g}", f"Şu an: {values[key]:g}")
                     + (f"  ·  {help_}" if help_ else ""), bg=PANEL, fg=DIM, font=("Segoe UI", 8),
                     anchor="w").pack(fill="x")
            var = tk.StringVar(value=f"{values[key]:g}")
            tk.Spinbox(f, from_=0 if key == "rupee" else 1, to=max(top, values[key]), increment=0.2 if key == "stamina" else 1,
                       format="%.1f" if key == "stamina" else "%.0f", textvariable=var, width=9, bg=BG, fg=TXT,
                       buttonbackground=PANEL, relief="flat", insertbackground=TXT,
                       font=("Segoe UI", 10)).pack(side="right")
            btn(f, t("Max", "En çok"), lambda v=var, m=top: v.set(str(m))).pack(side="right", padx=8)
            self.cheat_vars[key] = (var, top)
        tk.Frame(card, bg=PANEL, height=8).pack()

        bar = tk.Frame(p, bg=BG)
        bar.pack(fill="x", padx=28, pady=(10, 6))
        btn(bar, t("Apply", "Uygula"), lambda: self.apply_cheats(slot), "accent").pack(side="right")
        btn(bar, t("Max out all", "Hepsini en çoğa çek"),
            lambda: [v.set(str(m)) for v, m in self.cheat_vars.values()]).pack(side="right", padx=8)
        tk.Label(p, text=t("Note: during the prologue at the start the game sets these values itself; cheats stick "
                           "in saves made after reaching the Great Sky Island.",
                           "Not: Oyunun başındaki giriş bölümünde oyun bu değerleri kendisi ayarlar; hileler "
                           "Gökyüzü Adası'na çıktıktan sonra alınan kayıtlarda kalıcıdır."),
                 bg=BG, fg=DIM, font=("Segoe UI", 8), anchor="w", justify="left", wraplength=700).pack(
            fill="x", padx=28, pady=(4, 28))

    def apply_cheats(self, slot: Path):
        if self.running or game_running():
            return messagebox.showwarning("TotK", t("Close the game first.", "Önce oyunu kapatın."))
        values = {}
        for key, (var, top) in self.cheat_vars.items():
            try:
                v = float(var.get().replace(",", "."))
            except ValueError:
                return messagebox.showerror("TotK", t(f"Not a number: {var.get()}", f"Geçersiz sayı: {var.get()}"))
            if abs(v - self.cheat_now.get(key, -1)) < 1e-6:
                continue  # untouched: keep the save's value, even one outside the usual range
            v = max(0 if key == "rupee" else 1, min(top, v))
            v = round(v * 5) / 5 if key == "stamina" else int(v)
            if abs(v - self.cheat_now.get(key, -1)) > 1e-6:
                values[key] = v
        if not values:
            return self.toast(t("No changes", "Değişiklik yok"))
        try:
            backup_saves("before-cheats", 0)
            write_cheats(slot, values)
        except (OSError, ValueError) as e:
            return messagebox.showerror("TotK", t(f"Could not apply the cheats:\n{e}", f"Hile uygulanamadı:\n{e}"))
        self.cheat_slot = str(slot)
        self.show("cheats")
        self.toast(t(f"Cheats written to {slot.name}", f"Hileler {slot.name} yuvasına yazıldı"))

    # -- actions
    def _cfg(self, key, value):
        self.cfg[key] = value
        save_config(self.cfg)

    def _set_mods(self):
        self._cfg("mods", self.mods_var.get())
        if self.page in ("home", "controls"):
            self.show(self.page)

    def play(self):
        if not EXE.exists():
            return messagebox.showerror("TotK", t(f"totk.exe not found:\n{EXE}", f"totk.exe bulunamadı:\n{EXE}"))
        if self.running or self.preparing:
            return messagebox.showinfo("TotK", t("The game is already running.", "Oyun zaten çalışıyor."))
        if self.cfg["backup_before_play"]:
            try:
                backup_saves("auto", int(self.cfg["backup_keep"]))
            except OSError as e:
                if not messagebox.askyesno("TotK", t(f"Could not back up the saves:\n{e}\n\nStart anyway?",
                                                     f"Kayıt yedeği alınamadı:\n{e}\n\nYine de başlatılsın mı?")):
                    return
        env = os.environ.copy()
        env.pop("TOTK_ROMFS_MODS", None)
        env.pop("TOTK_ROMFS_PATCHES", None)
        if not (ROOT / "romfs").exists() and (ROOT / "romfs2").exists():
            env["TOTK_ROMFS"] = str(ROOT / "romfs2")
        prompt_set, use_mods = self.cfg["prompts"], self.cfg["mods"]
        if not prompts.prompts_available() or (prompt_set == "switch" and not use_mods):
            if not use_mods:
                EMPTY.mkdir(parents=True, exist_ok=True)
                env["TOTK_ROMFS_MODS"] = str(EMPTY)
            return self._launch(env)

        # prepare the prompts in the background (about 10 s the first time), then start
        self.preparing = True
        self._show_state()
        binds, game_lang = prompts.parse_binds(read_ini()), read_ini().get("lang")

        def work():
            try:
                result = prompts.build_overlay(prompt_set, binds, use_mods, game_lang)
            except Exception as e:  # noqa: BLE001 - shown to the user
                result = e
            self.root.after(0, lambda: self._overlay_ready(env, result, use_mods))
        threading.Thread(target=work, daemon=True).start()

    def _overlay_ready(self, env, result, use_mods):
        self.preparing = False
        self._show_state()
        if isinstance(result, Exception):
            if not messagebox.askyesno("TotK", t(f"Could not prepare the button prompts:\n{result}\n\nStart the "
                                                 "game with its current prompts?",
                                                 f"Tuş simgeleri hazırlanamadı:\n{result}\n\nOyun mevcut "
                                                 "simgelerle başlatılsın mı?")):
                return
            if not use_mods:
                EMPTY.mkdir(parents=True, exist_ok=True)
                env["TOTK_ROMFS_MODS"] = str(EMPTY)
        else:
            mods, patches = result
            env["TOTK_ROMFS_MODS"] = str(mods)
            if patches:
                env["TOTK_ROMFS_PATCHES"] = str(patches)
        self._launch(env)

    def _launch(self, env):
        try:
            self.proc = subprocess.Popen([str(EXE)], cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         creationflags=NO_WINDOW | NEW_GROUP)
        except OSError as e:
            return messagebox.showerror("TotK", t(f"Could not start the game:\n{e}", f"Oyun başlatılamadı:\n{e}"))
        self._set_running(True)
        if self.cfg["close_on_play"]:
            self.root.after(1500, self.root.destroy)
        else:
            self.root.after(8000, self._after_start)

    def _after_start(self):
        if self.page == "home":
            self.show("home")
        fact = log_fact(r"RomFS (ready: .+)")
        if fact:
            self.toast("RomFS " + fact)

    def _set_running(self, on: bool):
        if self.running and not on:
            self.root.after(1500, self.check_achievements)
        self.was_running = self.running or getattr(self, "was_running", False)
        self.running = on
        self._show_state()

    def _show_state(self):
        if not getattr(self, "play_btn", None) or not self.play_btn.winfo_exists():
            return
        on, was = self.running, getattr(self, "was_running", False) and not self.running
        if self.preparing:
            text, color, label = t("Preparing prompts…", "Simgeler hazırlanıyor…"), ACCENT, t("PREPARING…",
                                                                                              "HAZIRLANIYOR…")
        elif on:
            text, color, label = t("Game is running", "Oyun çalışıyor"), ACCENT, t("RUNNING", "ÇALIŞIYOR")
        else:
            text, color, label = (t("Game closed", "Oyun kapandı") if was else t("Ready", "Hazır"),
                                  WARN if was else DIM, t("PLAY", "OYNA"))
        self.dot.itemconfigure("d", fill=color)
        self.status.configure(text=text, fg=ACCENT if (on or self.preparing) else DIM)
        busy = on or self.preparing
        self.play_btn.configure(text=label, bg=EDGE if busy else ACCENT, fg=TXT if busy else "#03140f",
                                state="disabled" if self.preparing else "normal")

    def _poll(self):
        def work():
            on = (self.proc is not None and self.proc.poll() is None) or game_running()
            self.root.after(0, lambda: on != self.running and self._set_running(on))
        threading.Thread(target=work, daemon=True).start()
        self.root.after(3000, self._poll)

    def shortcut(self):
        pyw = Path(sys.executable).with_name("pythonw.exe")
        lnk = Path(os.environ["USERPROFILE"]) / "Desktop" / "TotK Launcher.lnk"
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:L);$s.TargetPath=$env:T;"
              "$s.Arguments='\"'+$env:A+'\"';$s.WorkingDirectory=$env:W;$s.IconLocation=$env:I+',0';$s.Save()")
        env = {**os.environ, "L": str(lnk), "T": str(pyw if pyw.exists() else sys.executable),
               "A": str(Path(__file__).resolve()), "W": str(ROOT), "I": str(EXE)}
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True,
                           creationflags=NO_WINDOW, timeout=30)
            self.toast(t("Added a 'TotK Launcher' shortcut to the desktop",
                         "Masaüstüne 'TotK Launcher' kısayolu eklendi"))
        except (OSError, subprocess.SubprocessError) as e:
            messagebox.showerror("TotK", t(f"Could not create the shortcut:\n{e}", f"Kısayol oluşturulamadı:\n{e}"))

    def open(self, path: Path):
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(path)
        except OSError:
            pass

    def toast(self, msg: str):
        lab = tk.Label(self.root, text=msg, bg=EDGE, fg=TXT, font=("Segoe UI", 10), padx=16, pady=9)
        lab.place(relx=1.0, rely=1.0, anchor="se", x=-24, y=-24)
        self.root.after(4000, lab.destroy)


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("totk.launcher")
    except Exception:
        pass
    migrate_old_names()
    root = tk.Tk()
    try:
        import ctypes
        root.update()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        dark = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
