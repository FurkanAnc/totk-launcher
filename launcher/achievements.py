"""Achievements computed from the save files (profile/save/<user>/slot_NN/progress.sav).

The game has no achievements of its own; these are read from the progress it keeps in the save: shrines, towers,
Lightroots, Korok seeds, caves, bosses, main quests, enemy statistics. The flag lists are in achievement_data.json
(see its _source). An achievement, once reached in any slot, stays unlocked: the launcher records the date.
"""
from __future__ import annotations

import json
import struct
import time
from pathlib import Path

from i18n import t

from paths import RES

DATA = RES / "achievement_data.json"

SAV_MAGIC = 0x01020304


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


class Save:
    """The flags of one progress.sav: hash -> raw 32-bit value (arrays are not read)."""

    def __init__(self, path: Path):
        data = path.read_bytes()
        if len(data) < 0x20 or struct.unpack_from("<I", data, 0)[0] != SAV_MAGIC:
            raise ValueError(f"{path}: not a progress.sav")
        end = min(struct.unpack_from("<I", data, 8)[0], len(data))
        self.values = {}
        for off in range(0x20, end - 7, 8):
            h, v = struct.unpack_from("<II", data, off)
            if h:
                self.values[h] = v

    def u32(self, name_or_hash) -> int | None:
        h = murmur3(name_or_hash) if isinstance(name_or_hash, str) else name_or_hash
        return self.values.get(h)

    def i32(self, name) -> int:
        v = self.u32(name)
        return 0 if v is None else struct.unpack("<i", struct.pack("<I", v))[0]

    def f32(self, name) -> float:
        v = self.u32(name)
        return 0.0 if v is None else struct.unpack("<f", struct.pack("<I", v))[0]

    def is_(self, name, value="Complete") -> bool:
        """An enum flag holds murmur3(value); a bool holds 1."""
        return self.u32(name) == (1 if value is True else murmur3(value))

    def count(self, items, value=True) -> int:
        want = 1 if value is True else murmur3(value)
        return sum(1 for it in items if self.values.get(murmur3(it) if isinstance(it, str) else it) == want)


_DATA = None


def data() -> dict:
    global _DATA
    if _DATA is None:
        _DATA = json.loads(DATA.read_text(encoding="utf-8"))
    return _DATA


def stats(save: Save) -> dict[str, float]:
    """Every number the achievements look at."""
    L = data()["lists"]
    enemies = data()["enemies"]

    def kills(prefix=""):
        return sum(save.i32(f"DefeatedEnemyNum.{e}") for e in enemies if e.startswith(prefix))

    def battle(field):
        return sum(save.i32(f"EnemyBattleData.{e}.{field}") for e in enemies)

    s = {
        "towers": save.count(L["towers_activated"]),
        "shrines": save.count(L["shrines_status"], "Clear"),
        "lightroots": save.count(L["lightroots_status"], "Open"),
        "koroks": save.count(L["koroks_hidden"]) + 2 * save.count(L["koroks_carry"], "Clear"),
        "caves": save.count(L["location_caves_visited"]),
        "wells": save.count(L["location_wells_visited"]),
        "chasms": save.count(L["location_chasms_visited"]),
        "bubbuls": save.count(L["bubbuls_defeated"]),
        "schematics": save.count(L["schematics_stone_found"]) + save.count(L["schematics_yiga_found"]),
        "treasure_maps": save.count(L["treasure_maps_found"]),
        "compendium": len(L["compendium_status"]) - save.count(L["compendium_status"], "Unopened"),
        "hinox": save.count(L["bosses_hinoxes_defeated"]),
        "talus": save.count(L["bosses_taluses_defeated"]),
        "molduga": save.count(L["bosses_moldugas_defeated"]),
        "flux": save.count(L["bosses_flux_construct_defeated"]),
        "frox": save.count(L["bosses_froxs_defeated"]),
        "gleeok": save.count(L["bosses_gleeoks_defeated"]),
        "kills": kills(),
        "lynels": kills("Enemy_Lynel"),
        "flurry": battle("JustAvoidCount"),
        "perfect_guard": battle("GuardJustCount"),
        "headshots": battle("HeadShotCount"),
        "no_damage": battle("DefeatedNoDamageCount"),
        "hearts": save.i32("PlayerStatus.MaxLife") / 4,
        "stamina": save.f32("PlayerStatus.MaxStamina") / 1000,
        "battery": save.f32("PlayerStatus.MaxEnergy") / 1000,
        "rupees": save.i32("PlayerStatus.CurrentRupee"),
        "poes": save.i32("PlayerStatus.CurrentMamo"),
        "tears": sum(save.is_(f"Complete_DragonTears{i:02d}", True) for i in range(1, 13)),
        "sages": sum(save.is_(f"Step_SageOf{s}") for s in ("Wind", "Fire", "Zora", "Gerudo")),
    }
    for quest in ("SageOfWind", "SageOfFire", "SageOfZora", "SageOfGerudo", "SageOfSoul", "GetMasterSword",
                  "MemoryOfTheDragon", "HyruleCastleIncident", "MainChallenge"):
        s["q_" + quest] = 1 if save.is_("Step_" + quest) else 0
    s["game_clear"] = 1 if save.is_("IsGameClear", True) or save.is_("Step_DefeatGanondorf") else 0
    return s


# (id, category, icon, (title en, tr), (description en, tr), stat, target)
STORY, EXPLORE, COLLECT, COMBAT, HERO = "story", "explore", "collect", "combat", "hero"
CATEGORIES = [(STORY, ("Story", "Hikâye")), (EXPLORE, ("Exploration", "Keşif")),
              (COLLECT, ("Collection", "Koleksiyon")), (COMBAT, ("Combat", "Savaş")), (HERO, ("Hero", "Kahraman"))]

ACHIEVEMENTS = [
    # story
    ("q_wind", STORY, "✦", ("Wind Temple", "Rüzgâr Tapınağı"),
     ("Clear the Wind Temple with Tulin.", "Tulin ile Rüzgâr Tapınağı'nı tamamla."), "q_SageOfWind", 1),
    ("q_fire", STORY, "✦", ("Fire Temple", "Ateş Tapınağı"),
     ("Clear the Fire Temple with Yunobo.", "Yunobo ile Ateş Tapınağı'nı tamamla."), "q_SageOfFire", 1),
    ("q_water", STORY, "✦", ("Water Temple", "Su Tapınağı"),
     ("Clear the Water Temple with Sidon.", "Sidon ile Su Tapınağı'nı tamamla."), "q_SageOfZora", 1),
    ("q_lightning", STORY, "✦", ("Lightning Temple", "Şimşek Tapınağı"),
     ("Clear the Lightning Temple with Riju.", "Riju ile Şimşek Tapınağı'nı tamamla."), "q_SageOfGerudo", 1),
    ("q_four", STORY, "✹", ("Regional Phenomena", "Bölgesel Olaylar"),
     ("Clear all four regional temples.", "Dört bölge tapınağının hepsini tamamla."), "sages", 4),
    ("q_spirit", STORY, "✦", ("Spirit Temple", "Ruh Tapınağı"),
     ("Clear the Spirit Temple with Mineru.", "Mineru ile Ruh Tapınağı'nı tamamla."), "q_SageOfSoul", 1),
    ("q_tears", STORY, "❖", ("Dragon's Tears", "Ejderhanın Gözyaşları"),
     ("Find all 12 Dragon's Tears memories.", "12 Ejderha Gözyaşı anısının hepsini bul."), "tears", 12),
    ("q_sword", STORY, "†", ("The Master Sword", "Master Sword"),
     ("Draw the Master Sword from the Light Dragon.", "Master Sword'u Işık Ejderhası'ndan çek."),
     "q_GetMasterSword", 1),
    ("q_end", STORY, "♛", ("Demon King Defeated", "İblis Kral Yenildi"),
     ("Defeat Ganondorf and finish the game.", "Ganondorf'u yen ve oyunu bitir."), "game_clear", 1),
    # exploration
    ("tower_1", EXPLORE, "▲", ("Eye in the Sky", "Gökteki Göz"),
     ("Activate a Skyview Tower.", "Bir Skyview Kulesi'ni etkinleştir."), "towers", 1),
    ("tower_all", EXPLORE, "▲", ("Cartographer", "Haritacı"),
     ("Activate all 15 Skyview Towers.", "15 Skyview Kulesi'nin hepsini etkinleştir."), "towers", 15),
    ("shrine_1", EXPLORE, "◆", ("First Light", "İlk Işık"), ("Complete a shrine.", "Bir tapınak bitir."),
     "shrines", 1),
    ("shrine_20", EXPLORE, "◆", ("Shrine Seeker", "Tapınak Avcısı"), ("Complete 20 shrines.", "20 tapınak bitir."),
     "shrines", 20),
    ("shrine_60", EXPLORE, "◆", ("Trial Veteran", "Sınav Ustası"), ("Complete 60 shrines.", "60 tapınak bitir."),
     "shrines", 60),
    ("shrine_120", EXPLORE, "◆", ("Shrine Master", "Tapınak Üstadı"),
     ("Complete 120 shrines.", "120 tapınak bitir."), "shrines", 120),
    ("shrine_all", EXPLORE, "◆", ("Every Blessing", "Bütün Kutsamalar"),
     ("Complete all 152 shrines.", "152 tapınağın hepsini bitir."), "shrines", 152),
    ("root_1", EXPLORE, "✺", ("Into the Dark", "Karanlığa Doğru"),
     ("Activate a Lightroot in the Depths.", "Derinlikler'de bir Lightroot etkinleştir."), "lightroots", 1),
    ("root_60", EXPLORE, "✺", ("Lamplighter", "Fenerci"), ("Activate 60 Lightroots.", "60 Lightroot etkinleştir."),
     "lightroots", 60),
    ("root_all", EXPLORE, "✺", ("No More Darkness", "Karanlık Kalmadı"),
     ("Activate all 120 Lightroots.", "120 Lightroot'un hepsini etkinleştir."), "lightroots", 120),
    ("cave_25", EXPLORE, "◒", ("Spelunker", "Mağaracı"), ("Visit 25 caves.", "25 mağaraya gir."), "caves", 25),
    ("cave_all", EXPLORE, "◒", ("Underground", "Yeraltı"), ("Visit all 147 caves.", "147 mağaranın hepsine gir."),
     "caves", 147),
    ("well_all", EXPLORE, "◎", ("Well Traveled", "Kuyu Kuyu"), ("Visit all 58 wells.", "58 kuyunun hepsine gir."),
     "wells", 58),
    ("chasm_all", EXPLORE, "▼", ("Down the Hole", "Dipsiz Kuyu"),
     ("Visit all 36 chasms.", "36 uçurumun hepsine gir."), "chasms", 36),
    # collection
    ("korok_1", COLLECT, "✿", ("Yahaha!", "Yahaha!"), ("Find a Korok seed.", "Bir Korok tohumu bul."), "koroks", 1),
    ("korok_100", COLLECT, "✿", ("Korok Friend", "Korok Dostu"), ("Get 100 Korok seeds.", "100 Korok tohumu topla."),
     "koroks", 100),
    ("korok_421", COLLECT, "✿", ("Bulging Pockets", "Dolu Cepler"),
     ("Get 421 Korok seeds, enough for every upgrade.", "421 Korok tohumu topla, her geliştirmeye yeter."),
     "koroks", 421),
    ("korok_all", COLLECT, "✿", ("Hestu's Gift", "Hestu'nun Hediyesi"),
     ("Get all 1000 Korok seeds.", "1000 Korok tohumunun hepsini topla."), "koroks", 1000),
    ("bubbul_25", COLLECT, "●", ("Frog Hunter", "Kurbağa Avcısı"),
     ("Get 25 Bubbul Gems.", "25 Bubbul Gem topla."), "bubbuls", 25),
    ("bubbul_all", COLLECT, "●", ("Koltin's Favourite", "Koltin'in Gözdesi"),
     ("Get all 147 Bubbul Gems.", "147 Bubbul Gem'in hepsini topla."), "bubbuls", 147),
    ("schem_all", COLLECT, "⚙", ("Engineer", "Mühendis"),
     ("Find all 46 schematics (Schema Stones and Yiga).", "46 şemanın hepsini bul (Schema Stone ve Yiga)."),
     "schematics", 46),
    ("maps_all", COLLECT, "✉", ("Treasure Hunter", "Hazine Avcısı"),
     ("Find all 31 old maps.", "31 eski haritanın hepsini bul."), "treasure_maps", 31),
    ("comp_100", COLLECT, "▣", ("Shutterbug", "Fotoğraf Meraklısı"),
     ("Fill 100 Hyrule Compendium entries.", "Hyrule Compendium'da 100 kayıt doldur."), "compendium", 100),
    ("comp_all", COLLECT, "▣", ("Encyclopedia", "Ansiklopedi"),
     ("Fill every Hyrule Compendium entry.", "Hyrule Compendium'un hepsini doldur."), "compendium", 509),
    # combat
    ("kill_100", COMBAT, "⚔", ("Monster Slayer", "Canavar Avcısı"), ("Defeat 100 enemies.", "100 düşman yen."),
     "kills", 100),
    ("kill_1000", COMBAT, "⚔", ("Thousand Foes", "Bin Düşman"), ("Defeat 1000 enemies.", "1000 düşman yen."),
     "kills", 1000),
    ("kill_5000", COMBAT, "⚔", ("Scourge of Monsters", "Canavarların Belası"),
     ("Defeat 5000 enemies.", "5000 düşman yen."), "kills", 5000),
    ("lynel_1", COMBAT, "♞", ("Lynel Slayer", "Lynel Avcısı"), ("Defeat a Lynel.", "Bir Lynel yen."), "lynels", 1),
    ("lynel_25", COMBAT, "♞", ("King of the Hill", "Tepenin Kralı"), ("Defeat 25 Lynels.", "25 Lynel yen."),
     "lynels", 25),
    ("hinox_all", COMBAT, "☗", ("Giant Killer", "Dev Avcısı"),
     ("Defeat all 69 Hinoxes.", "69 Hinox'un hepsini yen."), "hinox", 69),
    ("talus_all", COMBAT, "☗", ("Rock Breaker", "Kaya Kıran"),
     ("Defeat all 87 Stone Taluses.", "87 Stone Talus'un hepsini yen."), "talus", 87),
    ("molduga_all", COMBAT, "☗", ("Sand Shark", "Kum Köpekbalığı"),
     ("Defeat all 4 Moldugas.", "4 Molduga'nın hepsini yen."), "molduga", 4),
    ("flux_all", COMBAT, "☗", ("Construct Crusher", "Yapı Ezici"),
     ("Defeat all 35 Flux Constructs.", "35 Flux Construct'ın hepsini yen."), "flux", 35),
    ("frox_all", COMBAT, "☗", ("Frox Hunter", "Frox Avcısı"),
     ("Defeat all 40 Froxes.", "40 Frox'un hepsini yen."), "frox", 40),
    ("gleeok_all", COMBAT, "☗", ("Dragon Slayer", "Ejderha Avcısı"),
     ("Defeat all 14 Gleeoks.", "14 Gleeok'un hepsini yen."), "gleeok", 14),
    ("flurry_50", COMBAT, "⚡", ("Flurry Rush", "Hızlı Saldırı"),
     ("Pull off 50 Flurry Rushes.", "50 Flurry Rush yap."), "flurry", 50),
    ("guard_50", COMBAT, "⛨", ("Perfect Guard", "Kusursuz Savunma"),
     ("Land 50 Perfect Guards.", "50 Perfect Guard yap."), "perfect_guard", 50),
    ("head_250", COMBAT, "➶", ("Sharpshooter", "Keskin Nişancı"),
     ("Land 250 headshots.", "250 kafa vuruşu yap."), "headshots", 250),
    ("nodmg_500", COMBAT, "✧", ("Untouchable", "Dokunulmaz"),
     ("Defeat 500 enemies without taking damage.", "Hasar almadan 500 düşman yen."), "no_damage", 500),
    # hero
    ("hearts_20", HERO, "♥", ("Big Heart", "Koca Yürek"), ("Have 20 hearts.", "20 kalbe ulaş."), "hearts", 20),
    ("hearts_40", HERO, "♥", ("Heart of the Hero", "Kahramanın Kalbi"),
     ("Have 40 hearts.", "40 kalbe ulaş."), "hearts", 40),
    ("stamina_3", HERO, "◔", ("Tireless", "Yorulmak Bilmez"),
     ("Have 3 full stamina wheels.", "3 tam dayanıklılık çarkına ulaş."), "stamina", 3),
    ("battery_8", HERO, "▮", ("Fully Charged", "Tam Şarj"),
     ("Have 8 Zonai battery cells.", "8 Zonai pil hücresine ulaş."), "battery", 8),
    ("rupee_10k", HERO, "◈", ("Well Off", "Hali Vakti Yerinde"),
     ("Hold 10,000 rupees.", "10.000 rupiye sahip ol."), "rupees", 10000),
    ("rupee_100k", HERO, "◈", ("Rupee Tycoon", "Rupi Kralı"),
     ("Hold 100,000 rupees.", "100.000 rupiye sahip ol."), "rupees", 100000),
    ("poe_1000", HERO, "☄", ("Poe Collector", "Poe Koleksiyoncusu"),
     ("Hold 1000 Poes.", "1000 Poe'ya sahip ol."), "poes", 1000),
]


def save_files(save_root: Path) -> list[Path]:
    return sorted(save_root.glob("*/slot_*/progress.sav"))


def best_stats(save_root: Path) -> dict[str, float]:
    """For every stat, the best value over all save slots."""
    best: dict[str, float] = {}
    for p in save_files(save_root):
        try:
            save = Save(p)
        except (OSError, ValueError):
            continue
        # The prologue lends Link 30 hearts and 3 stamina wheels: only saves made after reaching the Great Sky
        # Island count.
        if save.u32("IsVisitLocation.BeginningIsland") != 1:
            continue
        s = stats(save)
        for k, v in s.items():
            best[k] = max(best.get(k, 0), v)
    return best


def evaluate(save_root: Path, unlocked: dict[str, str]) -> tuple[dict[str, float], list[str]]:
    """(best stats, ids unlocked just now). `unlocked` (id -> date) is updated in place."""
    best = best_stats(save_root)
    new = []
    for aid, _c, _i, _t, _d, stat, target in ACHIEVEMENTS:
        if aid not in unlocked and best.get(stat, 0) >= target:
            unlocked[aid] = time.strftime("%Y-%m-%d")
            new.append(aid)
    return best, new


def title(aid: str) -> str:
    return next(t(*a[3]) for a in ACHIEVEMENTS if a[0] == aid)
