"""Key bindings and button prompts.

The game draws its button prompts from the font scft/External.bfotf (inside Font/Font.Nin_NX_NVN.bfarc.zs): U+E040 A,
E041 B, E042 X, E043 Y, E044 L, E045 R, E046 ZL, E047 ZR, E049 d-pad, E04B +, E04C -, E050-E05F sticks, E060-E065
d-pad directions, E068 right stick all ways. The action prompt in the corner is a texture of the Common layout archive
(Nt_KeyTex*), and the letters around it are one-character messages of LayoutMsg/DoCommand_00.msbt drawn with the
Normal_00 font (Symbol, then Rodin).

This module redraws those from the keyboard and mouse bindings in totk.ini and writes them to copies of romfs_mods and
romfs-patches (launcher/rt/mods, launcher/rt/patches); the user's folders are never touched. Every game file it needs
(zstd dictionaries, the original fonts, Common, Mals, the resource size table) is read from the user's own RomFS
(romfs/index.json + romfs/romfs.bin); nothing from the game ships with the launcher.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import struct
import zlib
from pathlib import Path

from i18n import t

from paths import APP, ROOT

MODS = ROOT / "romfs_mods"
PATCHES = ROOT / "romfs-patches"
RT = APP / "rt"
OUT = RT / "mods"
OUT_PATCHES = RT / "patches"
STAMP = RT / "overlay.sig"
BUILD_VERSION = 3

FONT_PATH = "Font/Font.Nin_NX_NVN.bfarc.zs"
EXTERNAL = "scft/External.bfotf"
SYMBOL = "scft/Symbol.bfotf"
LABEL_FONT = "scft/ninP_RodinNTLG-B_DH_003_subset.bfotf"
COMBINED = "timg/__Combined.bntx"
DOCOMMAND_MSG = "LayoutMsg/DoCommand_00.msbt"
ZSDIC_PACK = "Pack/ZsDic.pack.zs"

# Prompt sets: keyboard (drawn from the bindings), switch (the game's own), mod (the icons of the font in romfs_mods)
PROMPT_SETS = ("keyboard", "switch", "mod")

# --------------------------------------------------------------------------- bindings
# (button, group, description, default keys, controller name) — defaults as in the game's F1 > Controls tab.
G_MOVE = ("Movement and camera", "Hareket ve kamera")
G_ACT = ("Actions", "Eylemler")
G_MENU = ("Menus and d-pad", "Menüler ve yön tuşları")
BUTTONS = [
    ("LSTICK_UP", G_MOVE, ("Move forward", "İleri hareket"), ["w"], None),
    ("LSTICK_DOWN", G_MOVE, ("Move back", "Geri hareket"), ["s"], None),
    ("LSTICK_LEFT", G_MOVE, ("Move left", "Sola hareket"), ["a"], None),
    ("LSTICK_RIGHT", G_MOVE, ("Move right", "Sağa hareket"), ["d"], None),
    ("LCLICK", G_MOVE, ("Crouch (left stick click)", "Eğil / gizlen (sol çubuğa bas)"), ["lctrl"], "lstick"),
    ("RSTICK_UP", G_MOVE, ("Camera up", "Kamera yukarı"), ["up"], None),
    ("RSTICK_DOWN", G_MOVE, ("Camera down", "Kamera aşağı"), ["down"], None),
    ("RSTICK_LEFT", G_MOVE, ("Camera left", "Kamera sola"), ["left"], None),
    ("RSTICK_RIGHT", G_MOVE, ("Camera right", "Kamera sağa"), ["right"], None),
    ("RCLICK", G_MOVE, ("Scope / first person (right stick click)", "Dürbün / ilk şahıs bakış (sağ çubuğa bas)"),
     ["c"], "rstick"),
    ("A", G_ACT, ("Interact, talk, pick up; confirm in menus (A)", "Etkileşim, konuş, al; menüde onayla (A)"),
     ["e"], "east"),
    ("B", G_ACT, ("Sprint (hold); back in menus (B)", "Koş (basılı tut); menüde geri (B)"), ["lshift"], "south"),
    ("X", G_ACT, ("Jump (X)", "Zıpla (X)"), ["space"], "north"),
    ("Y", G_ACT, ("Attack (Y)", "Saldırı (Y)"), ["mouse_l"], "west"),
    ("ZR", G_ACT, ("Draw bow / shoot (ZR)", "Yay çek / ok at (ZR)"), ["f", "x"], "zr"),
    ("ZL", G_ACT, ("Lock on / shield (ZL)", "Hedefe kilitlen / kalkan (ZL)"), ["mouse_r", "z"], "zl"),
    ("L", G_ACT, ("Abilities (L)", "Yetenekler (L)"), ["q"], "l"),
    ("R", G_ACT, ("Throw weapon (R)", "Silah fırlat (R)"), ["r"], "r"),
    ("PLUS", G_MENU, ("Inventory (+)", "Envanter menüsü (+)"), ["tab"], "start"),
    ("MINUS", G_MENU, ("Purah Pad / map (−)", "Purah Pad / harita (−)"), ["m"], "back"),
    ("UP", G_MENU, ("D-pad up: materials", "Yön tuşu yukarı: malzeme menüsü"), ["2"], "dpad_up"),
    ("DOWN", G_MENU, ("D-pad down: whistle / call horse", "Yön tuşu aşağı: ıslık / at çağır"), ["4"], "dpad_down"),
    ("LEFT", G_MENU, ("D-pad left: shields", "Yön tuşu sol: kalkan seç"), ["1"], "dpad_left"),
    ("RIGHT", G_MENU, ("D-pad right: weapons", "Yön tuşu sağ: silah seç"), ["3"], "dpad_right"),
]
DEFAULT_KEYS = {b: k for b, _g, _d, k, _p in BUTTONS}
STICK_DIRS = {b for b, *_r in BUTTONS if "STICK_" in b}

KEY_NAMES = (
    [chr(c) for c in range(ord("a"), ord("z") + 1)] + [str(i) for i in range(10)]
    + "space tab enter backspace lshift rshift lctrl rctrl lalt capslock insert delete home end pageup pagedown "
      "up down left right f2 f3 f4 f5 f6 f7 f9 f12 num0 num1 num2 num3 num4 num5 num6 num7 num8 num9 num_add "
      "num_sub num_mul num_div num_decimal minus equals lbracket rbracket semicolon apostrophe comma period slash "
      "backslash grave mouse_l mouse_r mouse_m mouse_x1 mouse_x2".split())
PAD_NAMES = ("south east west north l r zl zr start back lstick rstick dpad_left dpad_up dpad_right dpad_down"
              .split())

# Names in the launcher's table
KEY_LABELS = {
    "space": ("Space", "Boşluk"), "tab": ("Tab", "Tab"), "enter": ("Enter", "Enter"),
    "backspace": ("Backspace", "Backspace"), "lshift": ("Left Shift", "Sol Shift"),
    "rshift": ("Right Shift", "Sağ Shift"), "lctrl": ("Left Ctrl", "Sol Ctrl"), "rctrl": ("Right Ctrl", "Sağ Ctrl"),
    "lalt": ("Left Alt", "Sol Alt"), "capslock": ("Caps Lock", "Caps Lock"), "insert": ("Insert", "Insert"),
    "delete": ("Delete", "Delete"), "home": ("Home", "Home"), "end": ("End", "End"),
    "pageup": ("Page Up", "Page Up"), "pagedown": ("Page Down", "Page Down"), "up": ("↑", "↑"),
    "down": ("↓", "↓"), "left": ("←", "←"), "right": ("→", "→"), "num_add": ("Num +", "Num +"),
    "num_sub": ("Num −", "Num −"), "num_mul": ("Num *", "Num *"), "num_div": ("Num /", "Num /"),
    "num_decimal": ("Num .", "Num ."), "minus": ("-", "-"), "equals": ("=", "="), "lbracket": ("[", "["),
    "rbracket": ("]", "]"), "semicolon": (";", ";"), "apostrophe": ("'", "'"), "comma": (",", ","),
    "period": (".", "."), "slash": ("/", "/"), "backslash": ("\\", "\\"), "grave": ("`", "`"),
    "mouse_l": ("Left click", "Sol tık"), "mouse_r": ("Right click", "Sağ tık"),
    "mouse_m": ("Middle click", "Orta tık"), "mouse_x1": ("Mouse 4", "Fare 4"), "mouse_x2": ("Mouse 5", "Fare 5"),
}
PAD_LABELS = {
    "south": ("Bottom button", "Alt düğme"), "east": ("Right button", "Sağ düğme"),
    "west": ("Left button", "Sol düğme"), "north": ("Top button", "Üst düğme"),
    "l": ("Left bumper", "Sol omuz"), "r": ("Right bumper", "Sağ omuz"), "zl": ("Left trigger", "Sol tetik"),
    "zr": ("Right trigger", "Sağ tetik"), "start": ("Start / +", "Start / +"), "back": ("Back / −", "Select / −"),
    "lstick": ("Left stick click", "Sol çubuk bas"), "rstick": ("Right stick click", "Sağ çubuk bas"),
    "dpad_left": ("D-pad left", "Yön sol"), "dpad_up": ("D-pad up", "Yön yukarı"),
    "dpad_right": ("D-pad right", "Yön sağ"), "dpad_down": ("D-pad down", "Yön aşağı"),
}
# Short labels drawn on the keycaps (the same in every language)
CAP_LABELS = {
    "space": "Space", "tab": "Tab", "enter": "Enter", "backspace": "Back", "lshift": "Shift", "rshift": "Shift",
    "lctrl": "Ctrl", "rctrl": "Ctrl", "lalt": "Alt", "capslock": "Caps", "insert": "Ins", "delete": "Del",
    "home": "Home", "end": "End", "pageup": "PgUp", "pagedown": "PgDn", "up": "↑", "down": "↓", "left": "←",
    "right": "→", "num_add": "N+", "num_sub": "N-", "num_mul": "N*", "num_div": "N/", "num_decimal": "N.",
    "minus": "-", "equals": "=", "lbracket": "[", "rbracket": "]", "semicolon": ";", "apostrophe": "'",
    "comma": ",", "period": ".", "slash": "/", "backslash": "\\", "grave": "`", "mouse_x1": "M4", "mouse_x2": "M5",
}


def key_label(k: str) -> str:
    if k in KEY_LABELS:
        return t(*KEY_LABELS[k])
    if k.startswith("num") and k[3:].isdigit():
        return "Num " + k[3:]
    return k.upper()


def pad_label(p: str) -> str:
    return t(*PAD_LABELS[p])


def cap_label(k: str) -> str:
    if k in CAP_LABELS:
        return CAP_LABELS[k]
    if k.startswith("num") and k[3:].isdigit():
        return "N" + k[3:]
    return k.upper()


def parse_binds(ini: dict[str, str]) -> dict[str, dict]:
    """button -> {"keys": [...], "pad": "default" | "none" | name}. ini: read_ini() (lower-case keys)."""
    out = {}
    for b in DEFAULT_KEYS:
        line = ini.get("bind_" + b.lower())
        if line is None:
            out[b] = {"keys": list(DEFAULT_KEYS[b]), "pad": "default"}
            continue
        keys, pad, key_default = [], "none", False
        for part in (p.strip().lower() for p in line.split(",")):
            if part == "key:default":
                key_default = True
            elif part.startswith("key:") and part[4:] in KEY_NAMES:
                keys.append(part[4:])
            elif part == "pad:default":
                pad = "default"
            elif part.startswith("pad:") and part[4:] in PAD_NAMES:
                pad = part[4:]
        if key_default:
            keys = list(DEFAULT_KEYS[b]) + [k for k in keys if k not in DEFAULT_KEYS[b]]
        out[b] = {"keys": keys, "pad": pad}
    return out


def bind_line(b: str, keys: list[str], pad: str) -> str | None:
    """The totk.ini value of bind_<b>; None (line removed) when it matches the defaults."""
    if keys == DEFAULT_KEYS[b] and pad == "default":
        return None
    parts = [f"key:{k}" for k in keys]
    if b not in STICK_DIRS and pad != "none":
        parts.append(f"pad:{pad}")
    return ", ".join(parts) if parts else "none"


# --------------------------------------------------------------------------- the user's RomFS
def romfs_dir() -> Path | None:
    """The extracted RomFS: TOTK_ROMFS, else romfs/ (or romfs2/) next to totk.exe, with index.json and romfs.bin."""
    for d in (os.environ.get("TOTK_ROMFS"), ROOT / "romfs", ROOT / "romfs2"):
        if d and (Path(d) / "index.json").is_file() and (Path(d) / "romfs.bin").is_file():
            return Path(d)
    return None


class RomFS:
    def __init__(self):
        d = romfs_dir()
        if d is None:
            raise FileNotFoundError(t("The game's RomFS (romfs\\index.json and romfs.bin) was not found.",
                                      "Oyunun RomFS'i (romfs\\index.json ve romfs.bin) bulunamadı."))
        self.bin = d / "romfs.bin"
        index = json.loads((d / "index.json").read_text(encoding="utf-8"))
        self.files = {f["path"]: (f["offset"], f["size"]) for f in index["files"]}
        self._dicts = None

    def read(self, path: str) -> bytes:
        off, size = self.files[path]
        with self.bin.open("rb") as f:
            f.seek(off)
            data = f.read(size)
        if len(data) != size:
            raise OSError(f"romfs.bin: {path} is truncated")
        return data

    def latest(self, pattern: str) -> str | None:
        """The path matching pattern (one group: the version number) with the highest version."""
        best = None
        for p in self.files:
            m = re.fullmatch(pattern, p)
            if m and (best is None or int(m.group(1)) > best[0]):
                best = (int(m.group(1)), p)
        return best[1] if best else None

    # -- zstd: TotK compresses with the dictionaries of Pack/ZsDic.pack.zs
    def dicts(self) -> dict:
        if self._dicts is None:
            import zstandard as zs
            pack = zs.ZstdDecompressor().decompress(self.read(ZSDIC_PACK), max_output_size=50_000_000)
            self._dicts = {}
            for name, _node, lo, hi in sarc_nodes(pack):
                d = zs.ZstdCompressionDict(pack[lo:hi])
                self._dicts[d.dict_id()] = d
        return self._dicts

    def unzstd(self, raw: bytes) -> bytes:
        import zstandard as zs
        did = zs.get_frame_parameters(raw).dict_id
        dec = zs.ZstdDecompressor(dict_data=self.dicts()[did]) if did else zs.ZstdDecompressor()
        return dec.decompress(raw, max_output_size=300_000_000)

    def zstd(self, data: bytes, like: bytes) -> bytes:
        """Compressed like the file `like` (same dictionary)."""
        import zstandard as zs
        did = zs.get_frame_parameters(like).dict_id
        comp = zs.ZstdCompressor(level=12, dict_data=self.dicts()[did]) if did else zs.ZstdCompressor(level=12)
        out = comp.compress(data)
        assert self.unzstd(out) == data
        return out


def prompts_available() -> bool:
    return romfs_dir() is not None


def mod_prompts_available() -> bool:
    return (MODS / FONT_PATH).is_file()


# --------------------------------------------------------------------------- file formats
def sarc_nodes(data: bytes):
    assert data[:4] == b"SARC"
    header, start = struct.unpack_from("<H", data, 4)[0], struct.unpack_from("<I", data, 12)[0]
    count = struct.unpack_from("<H", data, header + 6)[0]
    names = header + 12 + count * 16 + 8
    out = []
    for i in range(count):
        node = header + 12 + i * 16
        _, attr, lo, hi = struct.unpack_from("<4I", data, node)
        off = names + (attr & 0xFFFFFF) * 4
        out.append((data[off:data.index(0, off)].decode(), node, start + lo, start + hi))
    return out


def sarc_get(data: bytes, name: str) -> bytes:
    for n, _node, lo, hi in sarc_nodes(data):
        if n == name:
            return data[lo:hi]
    raise KeyError(name)


def sarc_replace(data: bytes, new: dict[str, bytes]) -> bytes:
    """Members laid out again in their old order, each with at least the alignment its old offset had."""
    start = struct.unpack_from("<I", data, 12)[0]
    out = bytearray(data[:start])
    for name, node, lo, hi in sorted(sarc_nodes(data), key=lambda n: n[2]):
        align = min(lo & -lo, 0x2000) if lo else 0x2000
        out += bytes(-len(out) % align)
        body = new.get(name, data[lo:hi])
        struct.pack_into("<II", out, node + 8, len(out) - start, len(out) - start + len(body))
        out += body
    struct.pack_into("<I", out, 8, len(out))
    return bytes(out)


BFOTF_MAGIC = 0x18029A7F


def bfotf_decode(b: bytes) -> tuple[bytes, int]:
    """BFOTF (an OTF XORed with a 32-bit key) -> (OTF, key)."""
    key = struct.unpack_from("<I", b, 0)[0] ^ BFOTF_MAGIC
    size = int.from_bytes((struct.unpack_from("<I", b, 4)[0] ^ key).to_bytes(4, "little"), "big")
    body = b[8:] + bytes(-(len(b) - 8) % 4)
    words = struct.unpack(f"<{len(body) // 4}I", body)
    return struct.pack(f"<{len(words)}I", *(w ^ key for w in words))[:size], key


def bfotf_encode(otf: bytes, key: int) -> bytes:
    pad = otf + bytes(-len(otf) % 4)
    words = struct.unpack(f"<{len(pad) // 4}I", pad)
    head = struct.pack("<II", BFOTF_MAGIC ^ key, int.from_bytes(len(otf).to_bytes(4, "big"), "little") ^ key)
    return head + struct.pack(f"<{len(words)}I", *(w ^ key for w in words))


# --------------------------------------------------------------------------- drawing
K = 0.5523  # cubic control ratio of a quarter circle


class Shape:
    """Contours of ('M', p) ('L', p) ('C', p1, p2, p3) commands; fills run counter-clockwise, holes clockwise."""

    def __init__(self):
        self.contours: list[list[tuple]] = []

    def add(self, contour, hole=False):
        if _area(contour) < 0:
            contour = _reverse(contour)
        self.contours.append(_reverse(contour) if hole else contour)

    def draw(self, pen):
        for c in self.contours:
            pen.moveTo(c[0][1])
            for cmd in c[1:]:
                if cmd[0] == "L":
                    pen.lineTo(cmd[1])
                else:
                    pen.curveTo(cmd[1], cmd[2], cmd[3])
            pen.closePath()


def _area(c) -> float:
    pts = []
    prev = c[0][1]
    for cmd in c:
        if cmd[0] == "C":
            p0, p1, p2, p3 = prev, cmd[1], cmd[2], cmd[3]
            for i in range(1, 9):
                s = i / 8
                ms = 1 - s
                pts.append((ms ** 3 * p0[0] + 3 * ms * ms * s * p1[0] + 3 * ms * s * s * p2[0] + s ** 3 * p3[0],
                            ms ** 3 * p0[1] + 3 * ms * ms * s * p1[1] + 3 * ms * s * s * p2[1] + s ** 3 * p3[1]))
        else:
            pts.append(cmd[-1])
        prev = cmd[-1]
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts))) / 2


def _reverse(c):
    segs = []
    prev = c[0][1]
    for cmd in c[1:]:
        segs.append((prev, cmd))
        prev = cmd[-1]
    if prev != c[0][1]:
        segs.append((prev, ("L", c[0][1])))
    out = [("M", c[0][1])]
    for start, cmd in reversed(segs):
        out.append(("C", cmd[2], cmd[1], start) if cmd[0] == "C" else ("L", start))
    if out[-1][0] == "L" and out[-1][1] == out[0][1]:
        out.pop()
    return out


def rrect(x0, y0, x1, y1, r):
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    k = r * K
    return [("M", (x0 + r, y0)), ("L", (x1 - r, y0)), ("C", (x1 - r + k, y0), (x1, y0 + r - k), (x1, y0 + r)),
            ("L", (x1, y1 - r)), ("C", (x1, y1 - r + k), (x1 - r + k, y1), (x1 - r, y1)), ("L", (x0 + r, y1)),
            ("C", (x0 + r - k, y1), (x0, y1 - r + k), (x0, y1 - r)), ("L", (x0, y0 + r)),
            ("C", (x0, y0 + r - k), (x0 + r - k, y0), (x0 + r, y0))]


class Recorder:
    """fontTools pen that collects Shape contours (quadratics raised to cubics), with an affine transform."""

    def __init__(self, transform):
        self.t = transform
        self.contours = []
        self.cur = None
        self.last = (0, 0)

    def _p(self, p):
        a, b, c, d, e, f = self.t
        return (a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f)

    def moveTo(self, p):
        self.cur = [("M", self._p(p))]
        self.last = p

    def lineTo(self, p):
        self.cur.append(("L", self._p(p)))
        self.last = p

    def curveTo(self, *pts):
        if len(pts) == 3:
            self.cur.append(("C", *map(self._p, pts)))
            self.last = pts[-1]
        else:
            from fontTools.pens.basePen import decomposeSuperBezierSegment
            for seg in decomposeSuperBezierSegment(pts):
                self.curveTo(*seg)

    def qCurveTo(self, *pts):
        from fontTools.pens.basePen import decomposeQuadraticSegment
        for q1, q2 in decomposeQuadraticSegment(pts):
            p0 = self.last
            c1 = (p0[0] + 2 / 3 * (q1[0] - p0[0]), p0[1] + 2 / 3 * (q1[1] - p0[1]))
            c2 = (q2[0] + 2 / 3 * (q1[0] - q2[0]), q2[1] + 2 / 3 * (q1[1] - q2[1]))
            self.curveTo(c1, c2, q2)

    def closePath(self):
        if self.cur and len(self.cur) > 1:
            self.contours.append(self.cur)
        self.cur = None

    endPath = closePath

    def addComponent(self, name, transform):
        raise NotImplementedError


class Painter:
    """Builds the shapes of one glyph (units of a 1000 em, baseline 0)."""

    CAP_H = 560      # keycap height
    Y0 = 20          # keycap bottom

    def __init__(self, label_font, base_font):
        self.lgs = label_font.getGlyphSet()
        self.lcm = label_font.getBestCmap()
        self.bgs = base_font.getGlyphSet()
        self.bcm = base_font.getBestCmap()
        from fontTools.pens.boundsPen import BoundsPen
        bp = BoundsPen(self.lgs)
        self.lgs[self.lcm[ord("H")]].draw(bp)
        self.cap_height = bp.bounds[3]

    def _glyph(self, ch):
        return self.lcm.get(ord(ch)) or self.lcm[ord("?")]

    def text_contours(self, text, size, x, y):
        s = size / self.cap_height
        out, pen_x = [], 0.0
        for ch in text:
            g = self._glyph(ch)
            rec = Recorder((s, 0, 0, s, x + pen_x * s, y))
            self.lgs[g].draw(rec)
            out += rec.contours
            pen_x += self.lgs[g].width
        return out, pen_x * s

    def text_width(self, text, size):
        return sum(self.lgs[self._glyph(c)].width for c in text) * size / self.cap_height

    def keycap(self, sh: Shape, x, label, h=None, y=None, min_w=None):
        """A filled key from x with its label cut out. Returns its width."""
        h = h or self.CAP_H
        y = self.Y0 if y is None else y
        size = h * (0.5 if len(label) == 1 else 0.36 if len(label) <= 3 else 0.3)
        tw = self.text_width(label, size)
        w = max(min_w or h, tw + h * 0.42)
        sh.add(rrect(x, y, x + w, y + h, h * 0.2))
        sh.add(rrect(x + h * 0.12, y + h * 0.1, x + w - h * 0.12, y + h * 0.1 + h * 0.035, h * 0.017), hole=True)
        cons, _ = self.text_contours(label, size, x + (w - tw) / 2, y + (h - size) / 2 + h * 0.035)
        for c in cons:
            sh.add(c, hole=True)
        return w

    def mouse(self, sh: Shape, x, button=None, h=None, y=None):
        """A mouse: the button ('mouse_l', 'mouse_r', 'mouse_m') filled, the others outlined; None = body only."""
        h = h or self.CAP_H + 30
        y = (self.Y0 - 15) if y is None else y
        w = h * 0.66
        th, gap = h * 0.075, h * 0.05
        r = w / 2
        sh.add(rrect(x, y, x + w, y + h, r))
        cx, split = x + w / 2, y + h * 0.56
        top = y + h
        sh.add(rrect(cx - gap / 2, split + gap / 2, cx + gap / 2, top - th * 0.2, gap / 4), hole=True)
        sh.add(rrect(x + th * 0.2, split - gap / 2, x + w - th * 0.2, split + gap / 2, gap / 4), hole=True)

        def region(left: bool):
            a, b = (x + th, cx - gap / 2 - th) if left else (cx + gap / 2 + th, x + w - th)
            c, d = split + gap / 2 + th, top - th
            ry = min(d - c, r - th)
            rx = b - a
            if left:
                return [("M", (b, c)), ("L", (b, d)), ("L", (a + rx, d)),
                        ("C", (a + rx - rx * K, d), (a, d - ry + ry * K), (a, d - ry)), ("L", (a, c))]
            return [("M", (a, c)), ("L", (b, c)), ("L", (b, d - ry)),
                    ("C", (b, d - ry + ry * K), (b - rx + rx * K, d), (b - rx, d)), ("L", (a, d))]

        if button in ("mouse_l", "mouse_r", "mouse_m"):
            for left in (True, False):
                pressed = (button == "mouse_l" and left) or (button == "mouse_r" and not left)
                if not pressed:
                    sh.add(region(left), hole=True)
            if button == "mouse_m":
                wy = split + gap / 2 + th
                sh.add(rrect(cx - gap * 0.9, wy, cx + gap * 0.9, wy + (top - wy) * 0.6, gap * 0.9))
        return w

    def base_glyph(self, sh: Shape, code, x, y, scale):
        rec = Recorder((scale, 0, 0, scale, x, y))
        self.bgs[self.bcm[code]].draw(rec)
        for c in rec.contours:
            sh.add(c)

    def arrow(self, sh: Shape, direction, x, y, size=300):
        """The original font's arrows: E087 right, E088 left, E089 up, E08A down, E083 left-right, E084 up-down."""
        code = {"right": 0xE087, "left": 0xE088, "up": 0xE089, "down": 0xE08A, "lr": 0xE083, "ud": 0xE084}[direction]
        self.base_glyph(sh, code, x, y, size / 700)
        return size * 0.86

    def key_or_mouse(self, sh, x, key, **kw):
        if key in ("mouse_l", "mouse_r", "mouse_m"):
            return self.mouse(sh, x, key, **kw)
        return self.keycap(sh, x, cap_label(key), **kw)

    def cluster(self, sh, x, top, left, mid, right):
        """Inverted T: one small key above three."""
        s, g = 285, 20
        y_low, y_high = self.Y0 - 25, self.Y0 - 25 + s + g
        self.keycap(sh, x + s + g, cap_label(top), h=s, y=y_high, min_w=s)
        for i, k in enumerate((left, mid, right)):
            self.keycap(sh, x + i * (s + g), cap_label(k), h=s, y=y_low, min_w=s)
        return 3 * s + 2 * g


def glyph_specs(binds: dict[str, dict]):
    """code point -> drawing function (Painter, Shape, x) -> width, or None (the original glyph stays)."""
    def first(b):
        ks = binds[b]["keys"]
        return ks[0] if ks else None

    specs = {}

    def single(b):
        k = first(b)
        return (lambda p, sh, x: p.key_or_mouse(sh, x, k)) if k else None

    def pair(a, b):
        ka, kb = first(a), first(b)
        if not (ka and kb):
            return None

        def f(p, sh, x):
            w = p.key_or_mouse(sh, x, ka)
            return w + 50 + p.key_or_mouse(sh, x + w + 50, kb)
        return f

    for code, b in ((0xE040, "A"), (0xE041, "B"), (0xE042, "X"), (0xE043, "Y"), (0xE044, "L"), (0xE045, "R"),
                    (0xE046, "ZL"), (0xE047, "ZR"), (0xE04B, "PLUS"), (0xE04C, "MINUS"), (0xE056, "LCLICK"),
                    (0xE057, "RCLICK"), (0xE060, "UP"), (0xE061, "DOWN"), (0xE062, "LEFT"), (0xE063, "RIGHT"),
                    (0xE052, "LSTICK_UP"), (0xE050, "LSTICK_DOWN"), (0xE05A, "LSTICK_LEFT"),
                    (0xE058, "LSTICK_RIGHT")):
        specs[code] = single(b)
    specs[0xE064] = pair("UP", "DOWN")
    specs[0xE065] = pair("LEFT", "RIGHT")
    specs[0xE054] = pair("LSTICK_LEFT", "LSTICK_RIGHT")
    specs[0xE05C] = pair("LSTICK_UP", "LSTICK_DOWN")

    def clus(up, left, down, right):
        ks = [first(b) for b in (up, left, down, right)]
        if not all(ks):
            return None
        return lambda p, sh, x: p.cluster(sh, x, ks[0], ks[1], ks[2], ks[3])
    specs[0xE05E] = clus("LSTICK_UP", "LSTICK_LEFT", "LSTICK_DOWN", "LSTICK_RIGHT")
    specs[0xE049] = clus("UP", "LEFT", "DOWN", "RIGHT")

    # right stick = camera = mouse
    def cam(arrows):
        def f(p, sh, x):
            w = p.mouse(sh, x)
            if not arrows:
                return w
            if arrows == "all":
                p.arrow(sh, "ud", x + w + 30, 300, 280)
                return w + 30 + p.arrow(sh, "lr", x + w + 30, 20, 280)
            return w + 30 + p.arrow(sh, arrows, x + w + 30, 150, 340)
        return f
    for code, arrows in ((0xE05F, None), (0xE053, "up"), (0xE051, "down"), (0xE05B, "left"), (0xE059, "right"),
                         (0xE055, "lr"), (0xE05D, "ud"), (0xE068, "all")):
        specs[code] = cam(arrows)
    return specs


def _save_font(font) -> bytes:
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


def build_keyboard_font(binds: dict[str, dict], original_otf: bytes, label_otf: bytes) -> bytes:
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.ttLib import TTFont
    font = TTFont(io.BytesIO(original_otf), recalcTimestamp=False)
    cmap = font.getBestCmap()
    painter = Painter(TTFont(io.BytesIO(label_otf), recalcTimestamp=False),
                      TTFont(io.BytesIO(original_otf), recalcTimestamp=False))
    top = font["CFF "].cff.topDictIndex[0]
    margin = 40
    for code, spec in glyph_specs(binds).items():
        if spec is None or code not in cmap:
            continue
        sh = Shape()
        adv = int(round(spec(painter, sh, margin) + 2 * margin))
        pen = T2CharStringPen(adv, None)
        sh.draw(pen)
        top.CharStrings[cmap[code]] = pen.getCharString(private=top.Private, globalSubrs=top.GlobalSubrs)
        font["hmtx"][cmap[code]] = (adv, margin)
    return _save_font(font)


def build_mod_font(original_otf: bytes, mod_otf: bytes) -> bytes:
    """The button glyphs of the mod's font, with the ones it lacks (arrows, home, ...) from the original."""
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.ttLib import TTFont
    font = TTFont(io.BytesIO(original_otf), recalcTimestamp=False)
    mod = TTFont(io.BytesIO(mod_otf), recalcTimestamp=False)
    cmap, mcm, mgs = font.getBestCmap(), mod.getBestCmap(), mod.getGlyphSet()
    top = font["CFF "].cff.topDictIndex[0]
    for code in range(0xE040, 0xE0A0):
        if code not in cmap or code not in mcm:
            continue
        rec = RecordingPen()
        mgs[mcm[code]].draw(rec)
        if not rec.value:
            continue
        adv, lsb = mod["hmtx"][mcm[code]]
        pen = T2CharStringPen(adv, None)
        rec.replay(pen)
        top.CharStrings[cmap[code]] = pen.getCharString(private=top.Private, globalSubrs=top.GlobalSubrs)
        font["hmtx"][cmap[code]] = (adv, lsb)
    return _save_font(font)


# --------------------------------------------------------------------------- action prompt
# Textures at the centre of the action prompt (108x108 R8, block linear) -> External glyph
ACTION_TEXTURES = {"Nt_KeyTexA_00": 0xE040, "Nt_KeyTexB_00": 0xE041, "Nt_KeyTexX_00": 0xE042,
                   "Nt_KeyTexY_00": 0xE043, "Nt_KeyTexL_00": 0xE044, "Nt_KeyTexZL_00": 0xE046,
                   "Nt_KeyTexLSt_00": 0xE052, "Nt_KeyTexLSt_01": 0xE05E}
# One-character messages around it
DIAMOND = {"A": 0xE040, "B": 0xE041, "X": 0xE042, "Y": 0xE043, "Plus": 0xE04B}
# Game language (totk.ini lang) -> message archive
MALS_OF_LANG = {"en-US": "USen", "en-GB": "EUen", "de-DE": "EUde", "fr-FR": "EUfr", "es-ES": "EUes",
                "it-IT": "EUit", "nl-NL": "EUnl", "ru-RU": "EUru", "fr-CA": "USfr", "es-419": "USes",
                "ja": "JPja", "ko": "KRko", "zh-Hans": "CNzh", "zh-Hant": "TWzh"}


def _gob_off(x, y):
    return (x % 64 // 32) * 256 + (y % 8 // 2) * 64 + (x % 32 // 16) * 32 + (y % 2) * 16 + x % 16


def _bl_offset(x, y, row_bytes, block_height):
    """Offset of (x byte, y row) in Tegra X1 block-linear layout (depth 1)."""
    gobs_x = (row_bytes + 63) // 64
    block = 512 * block_height
    return ((y // (8 * block_height)) * gobs_x * block + (x // 64) * block
            + ((y % (8 * block_height)) // 8) * 512 + _gob_off(x, y))


def bntx_textures(b: bytes) -> dict[str, dict]:
    """name (without its ^ suffix) -> {format, width, height, tile, mips, block_height, size, data}."""
    assert b[:4] == b"BNTX" and b[0x20:0x24] == b"NX  "
    count, info = struct.unpack_from("<I", b, 0x24)[0], struct.unpack_from("<Q", b, 0x28)[0]
    out = {}
    for i in range(count):
        brti = struct.unpack_from("<Q", b, info + i * 8)[0]
        assert b[brti:brti + 4] == b"BRTI"
        noff = struct.unpack_from("<Q", b, brti + 0x60)[0]
        name = b[noff + 2:noff + 2 + struct.unpack_from("<H", b, noff)[0]].decode().split("^")[0]
        w, h = struct.unpack_from("<ii", b, brti + 0x24)
        out[name] = {"format": struct.unpack_from("<I", b, brti + 0x1C)[0], "width": w, "height": h,
                     "tile": struct.unpack_from("<H", b, brti + 0x12)[0],
                     "mips": struct.unpack_from("<H", b, brti + 0x16)[0],
                     "block_height": 1 << (struct.unpack_from("<i", b, brti + 0x34)[0] & 7),
                     "size": struct.unpack_from("<I", b, brti + 0x50)[0],
                     "data": struct.unpack_from("<Q", b, struct.unpack_from("<Q", b, brti + 0x70)[0])[0]}
    return out


def bntx_put_r8(b: bytearray, tex: dict, img) -> None:
    """Replace the first mip of an R8_UNORM (0x0201) texture with a PIL 'L' image."""
    assert tex["format"] == 0x0201 and tex["tile"] == 0 and tex["mips"] == 1, tex
    w, h = tex["width"], tex["height"]
    assert img.size == (w, h)
    px = img.tobytes()
    for y in range(h):
        for x in range(w):
            off = _bl_offset(x, y, w, tex["block_height"])
            assert off < tex["size"]
            b[tex["data"] + off] = px[y * w + x]


def glyph_image(otf: bytes, code: int, size: int, fill: int):
    """The glyph, white on black, fitted into a size x size 'L' image."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(io.BytesIO(otf), 512)
    big = Image.new("L", (1600, 900), 0)
    ImageDraw.Draw(big).text((100, 100), chr(code), font=font, fill=255)
    glyph = big.crop(big.getbbox())
    s = fill / max(glyph.size)
    glyph = glyph.resize((max(1, round(glyph.width * s)), max(1, round(glyph.height * s))), Image.LANCZOS)
    out = Image.new("L", (size, size), 0)
    out.paste(glyph, ((size - glyph.width) // 2, (size - glyph.height) // 2))
    return out


def symbol_with_glyphs(symbol_otf: bytes, external_otf: bytes, codes) -> bytes:
    """Symbol with External's glyphs at the same code points, in its unused glyph slots (the count stays)."""
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
    sym = TTFont(io.BytesIO(symbol_otf), recalcTimestamp=False)
    ext = TTFont(io.BytesIO(external_otf), recalcTimestamp=False)
    ecm, egs = ext.getBestCmap(), ext.getGlyphSet()
    used = set(sym.getBestCmap().values()) | {".notdef"}
    free = [g for g in reversed(sym.getGlyphOrder()) if g not in used and g.startswith("_")]
    top = sym["CFF "].cff.topDictIndex[0]
    k = sym["head"].unitsPerEm / ext["head"].unitsPerEm
    for code in codes:
        name = free.pop(0)
        rec = RecordingPen()
        egs[ecm[code]].draw(rec)
        adv = round(ext["hmtx"][ecm[code]][0] * k)
        pen = T2CharStringPen(adv, None)
        rec.replay(TransformPen(pen, (k, 0, 0, k, 0, 0)))
        top.CharStrings[name] = pen.getCharString(private=top.Private, globalSubrs=top.GlobalSubrs)
        sym["hmtx"][name] = (adv, 0)
        for table in sym["cmap"].tables:
            if table.format == 4:
                table.cmap[code] = name
    return _save_font(sym)


def msbt_set_chars(m: bytearray, chars: dict[str, str]) -> int:
    """Replace, in place, the character of the one-character messages with these labels; returns how many."""
    assert m[:8] == b"MsgStdBn"
    pos, secs = 0x20, {}
    while pos + 16 <= len(m):
        size = struct.unpack_from("<I", m, pos + 4)[0]
        secs[bytes(m[pos:pos + 4])] = (pos + 16, size)
        pos += 16 + size
        pos += -pos % 16
    lbl, _ = secs[b"LBL1"]
    labels = {}
    for i in range(struct.unpack_from("<I", m, lbl)[0]):
        count, off = struct.unpack_from("<II", m, lbl + 4 + i * 8)
        p = lbl + off
        for _ in range(count):
            n = m[p]
            labels[m[p + 1:p + 1 + n].decode()] = struct.unpack_from("<I", m, p + 1 + n)[0]
            p += 5 + n
    txt, _ = secs[b"TXT2"]
    changed = 0
    for label, ch in chars.items():
        if label not in labels:
            continue
        start = txt + struct.unpack_from("<I", m, txt + 4 + labels[label] * 4)[0]
        if m[start + 2:start + 4] != b"\0\0":  # not a single character: leave it
            continue
        m[start:start + 2] = ch.encode("utf-16le")
        changed += 1
    return changed


def diamond_chars() -> dict[str, str]:
    return {f"T_{letter}_{i:02d}": chr(code) for letter, code in DIAMOND.items() for i in range(4)}


# --------------------------------------------------------------------------- overlay folders
def _manifest(folder: Path) -> dict[str, list[str]]:
    out = {}
    mf = folder / "manifest.tsv"
    if mf.exists():
        for line in mf.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                p = line.split("\t")
                out[p[0]] = p
    return out


def _write_manifest(folder: Path, manifest: dict[str, list[str]]) -> None:
    lines = ["# path\tsize\tsha256\toriginal_sha256 (launcher/prompts.py)"] + ["\t".join(r) for r in manifest.values()]
    (folder / "manifest.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _rstb_fit(fs: RomFS, raw: bytes, path: str, size: int) -> bytes | None:
    """The size table with path's entry raised to fit size, or None when it already fits."""
    data = bytearray(fs.unzstd(raw))
    assert data[:6] == b"RESTBL"
    _ver, strsz, ncrc, nname = struct.unpack_from("<IIII", data, 6)
    need = size + 0x2000
    crc = zlib.crc32(path.encode())
    lo, hi = 0, ncrc - 1
    while lo <= hi:  # the crc table is sorted
        mid = (lo + hi) // 2
        c, v = struct.unpack_from("<II", data, 22 + mid * 8)
        if c == crc:
            if v >= need:
                return None
            struct.pack_into("<I", data, 22 + mid * 8 + 4, need)
            return fs.zstd(bytes(data), raw)
        lo, hi = (mid + 1, hi) if c < crc else (lo, mid - 1)
    base = 22 + ncrc * 8
    for i in range(nname):
        off = base + i * (strsz + 4)
        if data[off:off + strsz].split(b"\0")[0] == path.encode():
            if struct.unpack_from("<I", data, off + strsz)[0] >= need:
                return None
            struct.pack_into("<I", data, off + strsz, need)
            return fs.zstd(bytes(data), raw)
    return None


def _tree_sig(folder: Path) -> dict:
    if not folder.is_dir():
        return {}
    return {p.relative_to(folder).as_posix(): [p.stat().st_size, p.stat().st_mtime_ns]
            for p in sorted(folder.rglob("*")) if p.is_file()}


class Sources:
    """A game file from romfs_mods (when used), romfs-patches, or the RomFS, and its original for the manifest."""

    def __init__(self, fs: RomFS, use_mods: bool):
        self.fs, self.use_mods = fs, use_mods

    def get(self, path: str, folder: Path) -> bytes:
        if (folder is not MODS or self.use_mods) and (folder / path).is_file():
            return (folder / path).read_bytes()
        return self.fs.read(path)

    def original_sha(self, path: str) -> str:
        return hashlib.sha256(self.fs.read(path)).hexdigest()


def _put(folder: Path, manifest: dict, src: Sources, path: str, data: bytes) -> None:
    (folder / path).parent.mkdir(parents=True, exist_ok=True)
    (folder / path).write_bytes(data)
    row = manifest.get(path) or [path, "", "", src.original_sha(path)]
    row[1], row[2] = str(len(data)), hashlib.sha256(data).hexdigest()
    manifest[path] = row


def build_overlay(prompts: str, binds: dict[str, dict], use_mods: bool, game_lang: str | None) -> tuple[Path, Path | None]:
    """Copies of romfs_mods (or an empty folder when use_mods is off) and romfs-patches with the chosen prompts:
    (mods folder, patches folder, or None for romfs-patches as it is). prompts: one of PROMPT_SETS."""
    if prompts == "mod" and not (use_mods and mod_prompts_available()):
        prompts = "switch"
    action = prompts != "switch"
    sig = hashlib.sha256(json.dumps({
        "v": BUILD_VERSION, "prompts": prompts, "binds": binds if prompts == "keyboard" else None,
        "mods": _tree_sig(MODS) if use_mods else None, "patches": _tree_sig(PATCHES), "lang": game_lang,
    }, sort_keys=True).encode()).hexdigest()
    if STAMP.exists() and STAMP.read_text() == sig and OUT.is_dir():
        return OUT, (OUT_PATCHES if action else None)
    STAMP.unlink(missing_ok=True)
    for d in (OUT, OUT_PATCHES):
        if d.exists():
            shutil.rmtree(d)
    if use_mods and MODS.is_dir():
        shutil.copytree(MODS, OUT)
    else:
        OUT.mkdir(parents=True)
    manifest = _manifest(OUT)
    if prompts == "switch" and not use_mods:
        _write_manifest(OUT, manifest)
        STAMP.write_text(sig)
        return OUT, None

    fs = RomFS()
    src = Sources(fs, use_mods)
    rstb_path = fs.latest(r"System/Resource/ResourceSizeTable\.Product\.(\d+)\.Nin_NX_NVN\.rsizetable\.zs")

    # Font: External (button glyphs) and, for the action prompt, Symbol
    raw = src.get(FONT_PATH, MODS)
    bfarc = fs.unzstd(raw)
    original_otf, _ = bfotf_decode(sarc_get(fs.unzstd(fs.read(FONT_PATH)), EXTERNAL))
    _, key = bfotf_decode(sarc_get(bfarc, EXTERNAL))
    if prompts == "keyboard":
        otf = build_keyboard_font(binds, original_otf, bfotf_decode(sarc_get(bfarc, LABEL_FONT))[0])
    elif prompts == "mod":
        otf = build_mod_font(original_otf, bfotf_decode(sarc_get(bfarc, EXTERNAL))[0])
    else:
        otf = original_otf
    members = {EXTERNAL: bfotf_encode(otf, key)}
    if action:
        sym_otf, sym_key = bfotf_decode(sarc_get(bfarc, SYMBOL))
        members[SYMBOL] = bfotf_encode(symbol_with_glyphs(sym_otf, otf, sorted(set(DIAMOND.values()))), sym_key)
    new_bfarc = sarc_replace(bfarc, members)
    _put(OUT, manifest, src, FONT_PATH, fs.zstd(new_bfarc, raw))

    # Messages around the action prompt: the game language's archive and every one in romfs_mods
    if action:
        mals = set()
        if use_mods and (MODS / "Mals").is_dir():
            mals |= {p.relative_to(MODS).as_posix() for p in (MODS / "Mals").glob("*.sarc.zs")}
        code = MALS_OF_LANG.get(game_lang or "", "USen")
        latest = fs.latest(rf"Mals/{code}\.Product\.(\d+)\.sarc\.zs")
        if latest and not any(p.startswith(f"Mals/{code}.") for p in mals):
            mals.add(latest)
        for path in sorted(mals):
            if path not in fs.files and not (OUT / path).is_file():
                continue
            mraw = src.get(path, MODS)
            arc = fs.unzstd(mraw)
            msg = bytearray(sarc_get(arc, DOCOMMAND_MSG))
            if msbt_set_chars(msg, diamond_chars()):
                _put(OUT, manifest, src, path, fs.zstd(sarc_replace(arc, {DOCOMMAND_MSG: bytes(msg)}), mraw))

    # The resource size table must fit the larger font archive
    if rstb_path:
        rraw = src.get(rstb_path, MODS)
        fitted = _rstb_fit(fs, rraw, FONT_PATH[:-3], len(new_bfarc))
        if fitted:
            _put(OUT, manifest, src, rstb_path, fitted)
    _write_manifest(OUT, manifest)

    # Action prompt textures in the Common layout archive (romfs-patches already replaces it: build on that)
    if action:
        common = fs.latest(r"UI/LayoutArchive/Common\.Product\.(\d+)\.Nin_NX_NVN\.blarc\.zs")
        if PATCHES.is_dir():
            shutil.copytree(PATCHES, OUT_PATCHES)
        else:
            OUT_PATCHES.mkdir(parents=True)
        pmanifest = _manifest(OUT_PATCHES)
        craw = src.get(common, PATCHES)
        blarc = fs.unzstd(craw)
        bntx = bytearray(sarc_get(blarc, COMBINED))
        textures = bntx_textures(bntx)
        for name, code in ACTION_TEXTURES.items():
            tex = textures[name]
            bntx_put_r8(bntx, tex, glyph_image(otf, code, tex["width"], round(tex["width"] * 0.93)))
        _put(OUT_PATCHES, pmanifest, src, common, fs.zstd(sarc_replace(blarc, {COMBINED: bytes(bntx)}), craw))
        _write_manifest(OUT_PATCHES, pmanifest)

    STAMP.write_text(sig)
    return OUT, (OUT_PATCHES if action else None)


# --------------------------------------------------------------------------- preview
def font_bytes(prompts: str, binds: dict[str, dict], use_mods: bool) -> bytes:
    fs = RomFS()
    vanilla = fs.unzstd(fs.read(FONT_PATH))
    original_otf, _ = bfotf_decode(sarc_get(vanilla, EXTERNAL))
    base = fs.unzstd((MODS / FONT_PATH).read_bytes()) if use_mods and mod_prompts_available() else vanilla
    if prompts == "keyboard":
        return build_keyboard_font(binds, original_otf, bfotf_decode(sarc_get(base, LABEL_FONT))[0])
    if prompts == "mod" and base is not vanilla:
        return build_mod_font(original_otf, bfotf_decode(sarc_get(base, EXTERNAL))[0])
    return original_otf


def strip(prompts: str, binds: dict[str, dict], use_mods: bool, fg: str, bg: str, height: int = 46):
    """A row of the chosen prompts (PIL Image): A B X Y L R ZL ZR + − left stick, right stick, d-pad."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(io.BytesIO(font_bytes(prompts, binds, use_mods)), height)
    text = [chr(c) for c in (0xE040, 0xE041, 0xE042, 0xE043, 0xE044, 0xE045, 0xE046, 0xE047, 0xE04B, 0xE04C,
                             0xE05E, 0xE05F, 0xE049)]
    pad = height // 4
    w = int(sum(font.getlength(c) for c in text)) + pad * (len(text) - 1) + 8
    img = Image.new("RGB", (w, int(height * 1.15)), bg)
    d, x = ImageDraw.Draw(img), 4
    for c in text:
        d.text((x, int(height * 0.08)), c, font=font, fill=fg)
        x += int(font.getlength(c)) + pad
    return img
