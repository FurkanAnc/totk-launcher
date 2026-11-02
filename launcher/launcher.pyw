"""TotK Launcher: the window (pywebview, HTML in ui/) and the API its page calls.

All game logic is in core.py, prompts.py and achievements.py; this file only turns it into calls for ui/app.js.
English by default; Turkish can be chosen in Settings.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import struct
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import achievements  # noqa: E402
import core  # noqa: E402
import i18n  # noqa: E402
import paths  # noqa: E402
import prompts  # noqa: E402
from i18n import t  # noqa: E402
from paths import FROZEN, RES, ROOT  # noqa: E402

UI = RES / "ui" / "index.html"


def strings() -> dict:
    """Every fixed text of the page, in the current language."""
    return {k: t(*v) for k, v in {
        "home": ("Home", "Ana sayfa"), "settings": ("Settings", "Ayarlar"), "controls": ("Controls", "Kontroller"),
        "mods_page": ("Mods", "Modlar"),
        "mods_sub": ("romfs_mods and the mods in the mods folder next to totk.exe (one folder per mod) are combined "
                     "when you press PLAY. A mod lower in the list wins when two change the same file; your "
                     "romfs_mods folder is never changed.",
                     "romfs_mods ve totk.exe'nin yanındaki mods klasöründeki modlar (her mod ayrı klasörde) OYNA'ya "
                     "basınca birleştirilir. İki mod aynı dosyayı değiştirirse listede alttaki geçerli olur; "
                     "romfs_mods klasörün hiç değişmez."),
        "mod_list": ("Installed mods", "Yüklü modlar"), "add_mod": ("Add a mod folder…", "Mod klasörü ekle…"),
        "mods_folder": ("Mods folder", "Mods klasörü"), "no_mods": ("No mods yet. Put a mod's folder into the mods "
                                                                   "folder or use Add a mod folder.",
                                                                   "Henüz mod yok. Bir modun klasörünü mods klasörüne "
                                                                   "koyun ya da Mod klasörü ekle'yi kullanın."),
        "base_mod": ("Your romfs_mods folder, always first", "romfs_mods klasörün, hep ilk sırada"),
        "replaces": ("replaces files of", "şunun dosyalarını değiştirir:"),
        "mods_master_off": ("Load mods is off in the sidebar: no mod is used.",
                            "Kenar çubuğunda Yamalarla başlat kapalı: hiçbir mod kullanılmıyor."),
        "play_time": ("Play time", "Oynama süresi"), "sessions": ("sessions", "oturum"),
        "from_save": ("from your most played save", "en çok oynanan kayıttan"),
        "no_play": ("No save yet", "Henüz kayıt yok"),
        "game_ver": ("Game", "Oyun"), "recomp_ver": ("Recomp", "Recomp"), "up_to_date": ("up to date", "güncel"),
        "available": ("available", "çıktı"), "fps_avg": ("avg", "ort."),
        "update_recomp": ("Recomp update", "Recomp güncellemesi"), "update_launcher": ("Launcher update",
                                                                                     "Launcher güncellemesi"),
        "update_have": ("you have", "sendeki"), "release_notes": ("Release page", "Sürüm sayfası"),
        "check_updates": ("Check for updates", "Güncellemeleri kontrol et"),
        "check_updates_hint": ("Asks GitHub at most every six hours whether a newer recomp or launcher is out. "
                               "Nothing is downloaded.",
                               "En fazla altı saatte bir GitHub'a yeni recomp ya da launcher sürümü çıkıp "
                               "çıkmadığını sorar. Hiçbir şey indirmez."),
        "shortcut_hint": ("Adds a TotK Launcher shortcut to the desktop.", "Masaüstüne TotK Launcher kısayolu ekler."),
        "slots": ("Save slots", "Kayıt yuvaları"), "slots_sub": ("What each slot holds, most recent first.",
                                                               "Her yuvada ne var, en son kaydedilen en üstte."),
        "hearts_s": ("hearts", "kalp"), "stamina_s": ("stamina", "dayanıklılık"), "battery_s": ("battery", "pil"),
        "rupees_s": ("rupees", "rupi"),
        "inventory": ("Inventory", "Envanter"),
        "inventory_sub": ("Pouch slots and the stock of items you already have. Items you don't have yet can't be "
                          "added here.", "Çanta yuvaları ve zaten sahip olduğun eşyaların sayısı. Henüz olmayan "
                          "eşyalar buradan eklenemez."),
        "not_owned": ("Not in this save yet:", "Bu kayıtta henüz yok:"),
        "repair": ("Repair equipment", "Ekipmanı onar"),
        "repair_hint": ("Refills the durability of every weapon, bow and shield to its full value when you apply.",
                        "Uygula'ya basınca her silah, yay ve kalkanın dayanıklılığını tam değerine doldurur."),
        "worn_n": ("worn items", "yıpranmış eşya"), "saved_at": ("Saved", "Kaydedildi"), "layout_xbox_prompts": ("Xbox prompts", "Xbox simgeleri"),
        "saves": ("Saves", "Kayıtlar"), "achievements": ("Achievements", "Başarımlar"), "cheats": ("Cheats", "Hileler"),
        "play": ("Play", "Oyna"), "running": ("Running", "Çalışıyor"), "preparing": ("Preparing…", "Hazırlanıyor…"),
        "st_ready": ("Ready", "Hazır"), "st_running": ("Game is running", "Oyun çalışıyor"),
        "st_closed": ("Game closed", "Oyun kapandı"), "st_preparing": ("Preparing prompts…", "Simgeler hazırlanıyor…"),
        "load_mods": ("Load mods", "Yamalarla başlat"),
        "subtitle": ("PC recomp launcher", "PC recomp launcher"),
        "status": ("Status", "Durum"), "quick_fps": ("Frame rate limit", "Kare sınırı"),
        "monitor": ("Monitor", "Monitör"), "recent_log": ("Recent log", "Son log"), "refresh": ("Refresh", "Yenile"),
        "log_folder": ("Log folder", "Log klasörü"), "game_folder_btn": ("Game folder", "Oyun klasörü"),
        "shortcut": ("Desktop shortcut", "Masaüstü kısayolu"), "no_log": ("No log yet.", "Henüz log yok."),
        "settings_sub": ("Written to totk.ini, with a backup before every save. The other settings are in the "
                         "game's F1 menu.", "totk.ini'ye yazılır, her kayıttan önce yedek alınır. Diğer ayarlar "
                         "oyunda F1 menüsünde."),
        "launcher": ("Launcher", "Launcher"), "ui_lang": ("Interface language", "Arayüz dili"),
        "game_folder": ("Game folder", "Oyun klasörü"), "change": ("Change…", "Değiştir…"),
        "save": ("Save", "Kaydet"), "reset_defaults": ("Reset to defaults", "Varsayılanlara dön"),
        "open_ini": ("Open totk.ini", "totk.ini'yi aç"), "automatic": ("Automatic", "Otomatik"),
        "controls_sub": ("Keyboard, mouse and controller: each has its own buttons and they work together.",
                         "Klavye, fare ve kumanda: her birinin kendi düğmeleri vardır ve birlikte çalışır."),
        "prompts_devices": ("Prompts and devices", "Simgeler ve cihaz"),
        "button_prompts": ("Button prompts", "Tuş simgeleri"),
        "prompts_help": ("The button icons in the game. With keyboard and mouse they are drawn from the bindings "
                         "below (the first key is shown), the action prompt included, and updated on every launch.",
                         "Oyundaki düğme simgeleri. Klavye ve fare seçiliyken aşağıdaki atamalardan çizilir (ilk "
                         "tuş gösterilir; aksiyon simgesi dahil) ve her OYNA'da güncellenir."),
        "keyboard_mouse": ("Keyboard & mouse", "Klavye ve fare"), "mod_icons": ("Mod icons", "Mod simgeleri"),
        "no_romfs": ("RomFS not found: prompts cannot be changed", "RomFS bulunamadı: simgeler değiştirilemez"),
        "controller_layout": ("Controller layout", "Kumanda düzeni"),
        "layout_help": ("Nintendo: buttons by position (A on the right). Xbox: the bottom button is A. Xbox prompts "
                        "(recomp 0.2.8+): buttons as Nintendo, the game's prompts show the Xbox letters.",
                        "Nintendo: düğmeler konumuna göre (sağdaki A). Xbox: alttaki düğme A. Xbox simgeleri "
                        "(recomp 0.2.8+): düğmeler Nintendo gibi, oyundaki simgeler Xbox harflerini gösterir."),
        "layout_auto": ("Automatic", "Otomatik"), "layout_nintendo": ("Nintendo", "Nintendo"),
        "layout_xbox": ("Xbox", "Xbox"),
        "mouse_camera": ("Mouse camera", "Fare kamerası"),
        "mouse_help": ("Sensitivity 0 to 10; 0 turns the mouse camera off. Applies while the game runs.",
                       "Hassasiyet 0-10; 0 fare kamerasını kapatır. Oyun açıkken de uygulanır."),
        "bind_help": ("Click a cell, then press a key or a mouse button; Esc cancels, right-click clears. A key "
                      "used elsewhere moves here. Movement and camera directions take keys only.",
                      "Bir hücreye tıklayın, sonra bir tuşa ya da fare düğmesine basın; Esc iptal eder, sağ tık "
                      "temizler. Başka yerde kullanılan tuş buraya taşınır. Hareket ve kamera yönlerine yalnızca "
                      "tuş atanır."),
        "key1": ("Key 1", "Tuş 1"), "key2": ("Key 2", "Tuş 2"), "controller": ("Controller", "Kumanda"),
        "press_key": ("Press a key…", "Bir tuşa basın…"), "default": ("Default", "Varsayılan"), "none": ("None", "Yok"),
        "left_stick": ("Left stick", "Sol çubuk"), "right_stick": ("Right stick", "Sağ çubuk"),
        "reset_bindings": ("Reset all bindings", "Tüm tuşları sıfırla"),
        "undo": ("Undo changes", "Değişiklikleri geri al"),
        "keys_only": ("Movement and camera directions take keys only", "Hareket ve kamera yönlerine yalnızca tuş "
                      "atanır"),
        "moved_from": ("moved from", "şuradan taşındı:"), "unknown_key": ("The game cannot use this key",
                                                                         "Bu tuş oyunda kullanılamaz"),
        "saves_sub": ("Game saves: profile\\save. Backups: profile\\launcher-backups.",
                      "Oyun kayıtları: profile\\save. Yedekler: profile\\launcher-backups."),
        "auto_backup": ("Automatic backup", "Otomatik yedek"),
        "backup_on_play": ("Back up the saves before every launch", "Her OYNA'da önce kayıtları yedekle"),
        "keep": ("Automatic backups kept", "Saklanacak otomatik yedek"),
        "close_on_play": ("Close the launcher when the game starts", "Oyun açılınca launcher'ı kapat"),
        "backup_now": ("Back up now", "Şimdi yedekle"), "save_folder": ("Save folder", "Kayıt klasörü"),
        "backup_folder": ("Backup folder", "Yedek klasörü"), "backups": ("Backups", "Yedekler"),
        "no_backups": ("No backups yet.", "Henüz yedek yok."), "restore": ("Restore", "Geri yükle"),
        "delete": ("Delete", "Sil"),
        "ach_sub": ("Read from your save files after every game session. Saves from before the Great Sky Island "
                    "don't count; once unlocked, an achievement stays unlocked.",
                    "Her oyun oturumundan sonra kayıt dosyalarından okunur. Gökyüzü Adası'ndan önceki kayıtlar "
                    "sayılmaz; açılan başarım açık kalır."),
        "progress": ("Progress", "İlerleme"), "check_now": ("Check now", "Şimdi kontrol et"),
        "all": ("All", "Tümü"), "locked": ("Locked", "Kilitli"), "unlocked_on": ("Unlocked", "Açıldı"),
        "ach_unlocked": ("Achievement unlocked", "Başarım açıldı"),
        "ach_credit": ("Flag lists: the TotK savegame editor by Marc Robledo and its researchers (MIT).",
                       "Bayrak listeleri: Marc Robledo'nun TotK kayıt editörü ve araştırmacıları (MIT)."),
        "cheats_sub": ("Edits the save file (progress.sav) while the game is closed; the saves are backed up "
                       "before every change.", "Oyun kapalıyken kayıt dosyasını (progress.sav) düzenler; her "
                       "değişiklikten önce kayıtlar yedeklenir."),
        "save_slot": ("Save slot", "Kayıt yuvası"), "values": ("Values", "Değerler"), "now": ("Now", "Şu an"),
        "max": ("Max", "En çok"), "max_all": ("Max out all", "Hepsini en çoğa çek"), "apply": ("Apply", "Uygula"),
        "no_save": ("No save found. Save once in the game first.", "Kayıt bulunamadı. Önce oyunda bir kez kaydedin."),
        "game_running_warn": ("The game is running. Close it to apply cheats.",
                              "Oyun çalışıyor. Hileleri uygulamak için oyunu kapatın."),
        "cheats_note": ("During the prologue the game sets these values itself; cheats stick in saves made after "
                        "reaching the Great Sky Island.", "Giriş bölümünde oyun bu değerleri kendisi ayarlar; "
                        "hileler Gökyüzü Adası'na çıktıktan sonraki kayıtlarda kalıcıdır."),
        "confirm": ("Confirm", "Onayla"), "cancel": ("Cancel", "İptal"), "yes": ("Yes", "Evet"),
        "find_game": ("Find your game", "Oyununu bul"),
        "find_game_text": ("The launcher could not find the game next to it. Select totk.exe in the folder where "
                           "the Tears of the Kingdom PC recomp is installed; the launcher remembers it. You can also "
                           "put TotK Launcher.exe in that folder, next to totk.exe.",
                           "Launcher oyunu yanında bulamadı. Tears of the Kingdom PC recomp'un kurulu olduğu "
                           "klasördeki totk.exe'yi seçin; launcher bunu hatırlar. TotK Launcher.exe'yi o klasöre, "
                           "totk.exe'nin yanına da koyabilirsiniz."),
        "select_exe": ("Select totk.exe…", "totk.exe'yi seç…"),
        "found": ("found", "bulundu"), "not_found": ("not found", "bulunamadı"), "game": ("Game", "Oyun"),
        "version": ("Version", "Sürüm"), "gpu": ("Graphics card", "Ekran kartı"), "mods": ("Mods", "Yamalar"),
        "last_start": ("Last start", "Son açılış"), "files": ("files", "dosya"), "on": ("on", "açık"),
        "off": ("off", "kapalı"), "unknown": ("not known yet", "henüz bilinmiyor"),
        "more_ach": ("more achievements", "başarım daha"),
        "theme": ("Theme", "Tema"), "theme_help": ("The look of the launcher.", "Launcher'ın görünümü."),
        "theme_light": ("Light", "Açık"), "theme_night": ("Night", "Gece"),
        "game_title": ("Tears of the Kingdom", "Tears of the Kingdom"),
        "last_session": ("Last session", "Son oturum"), "avg_fps": ("average", "ortalama"),
        "low_fps": ("1% low", "%1 düşük"), "frames": ("frames", "kare"),
        "not_ready": ("totk.exe was not found in the game folder.", "Oyun klasöründe totk.exe bulunamadı."),
        "fps_applied": ("Applied immediately to totk.ini", "totk.ini'ye hemen uygulanır"),
        "log_sub": ("logs\\totk.log · last 80 lines", "logs\\totk.log · son 80 satır"),
        "always_on": ("always on", "hep açık"),
        "lang_hint": ("The language of the launcher.", "Launcher'ın dili."),
        "folder_hint": ("The folder containing totk.exe.", "totk.exe'nin bulunduğu klasör."),
        "backup_note": ("A backup is created before every save.", "Her kayıttan önce yedek alınır."),
        "save_settings": ("Save settings", "Ayarları kaydet"),
        "prompts_sub": ("The preview updates from your current bindings.",
                        "Önizleme mevcut atamalarından güncellenir."),
        "input": ("Input", "Giriş"), "key_bindings": ("Key bindings", "Tuş atamaları"), "action": ("Action", "Eylem"),
        "actions_n": ("actions", "eylem"), "save_bindings": ("Save bindings", "Atamaları kaydet"),
        "backup_on_play_hint": ("Creates a timestamped copy before the game starts.",
                                "Oyun başlamadan önce tarihli bir kopya oluşturur."),
        "keep_hint": ("Older automatic backups are removed when this limit is reached.",
                      "Sınıra ulaşılınca eski otomatik yedekler silinir."),
        "close_hint": ("Exit the launcher after totk.exe opens.", "totk.exe açılınca launcher kapanır."),
        "newest_first": ("Newest first", "En yeni en üstte"),
        "kind_auto": ("Automatic", "Otomatik"), "kind_manual": ("Manual", "Elle"),
        "kind_before_restore": ("Before restore", "Geri yüklemeden önce"),
        "kind_before_cheats": ("Before cheats", "Hilelerden önce"),
        "overall": ("Overall progress", "Genel ilerleme"),
        "notice_ok": ("A backup is created before changes are applied.",
                      "Değişiklikler uygulanmadan önce yedek alınır."),
        "notice_ok_sub": ("Cheats are available only while the game is closed.",
                          "Hileler yalnızca oyun kapalıyken uygulanabilir."),
        "notice_run_sub": ("Save editing is locked while totk.exe is running.",
                           "totk.exe çalışırken kayıt düzenleme kilitli."),
        "selected_save": ("Selected save", "Seçili kayıt"),
        "slot_hint": ("Slots are sorted by most recently played.", "En son oynanan en üstte."),
        "values_sub": ("Enter a value or use Max to reach the allowed limit.",
                       "Bir değer girin ya da en yüksek değer için En çok'a basın."),
        "safe_edit": ("Game is closed · safe to edit", "Oyun kapalı · düzenlenebilir"),
        "locked_edit": ("Game is running · editing locked", "Oyun çalışıyor · düzenleme kilitli"),
        "apply_changes": ("Apply changes", "Değişiklikleri uygula"),
        "no_cancel": ("No, cancel", "Hayır, vazgeç"), "yes_continue": ("Yes, continue", "Evet, devam et"),
        "first_setup": ("First setup", "İlk kurulum"), "play_again": ("Play again", "Tekrar oyna"),
    }.items()}


def last_start() -> str:
    """When the game last wrote its log: "Today, 09:42", "Yesterday, 22:06" or a date."""
    try:
        when = core.GAME_LOG.stat().st_mtime
    except OSError:
        return ""
    day = time.strftime("%Y%m%d", time.localtime(when))
    clock = time.strftime("%H:%M", time.localtime(when))
    if day == time.strftime("%Y%m%d"):
        return t("Today", "Bugün") + ", " + clock
    if day == time.strftime("%Y%m%d", time.localtime(time.time() - 86400)):
        return t("Yesterday", "Dün") + ", " + clock
    return time.strftime(t("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"), time.localtime(when))


def game_version() -> str:
    try:
        return json.loads((ROOT / "totk-install.json").read_text(encoding="utf-8")).get("version", "")
    except (OSError, ValueError):
        return ""


def last_session() -> dict | None:
    """The game's own measurement at the end of the last run (the frametime line of logs\\totk.log)."""
    for line in reversed(core.log_lines(400)):
        m = re.search(r"frametime: exit: (\d+) frames in ([\d.]+) s, mean ([\d.]+) fps, 1% low ([\d.]+) fps", line)
        if m:
            return {"frames": int(m.group(1)), "seconds": float(m.group(2)), "mean": float(m.group(3)),
                    "low": float(m.group(4))}
    return None


class Api:
    """Methods ui/app.js calls through window.pywebview.api. Every one returns plain JSON data."""

    def __init__(self):
        self._cfg = core.load_config()
        i18n.set_lang(self._cfg["lang"])
        self._window = None
        self._proc = None
        self._running = False
        self._was_running = False
        self._preparing = False
        self._events: list[dict] = []
        self._lock = threading.Lock()
        self._ach_stats: dict | None = None
        if paths.FOUND:
            threading.Thread(target=self._check_achievements, args=(True,), daemon=True).start()
            threading.Thread(target=self._watch, daemon=True).start()
            if not core.game_running() and core.count_session(self._cfg):
                core.save_config(self._cfg)

    # -- general
    def log(self, message):
        """Errors of the page (ui/app.js), for troubleshooting."""
        try:
            paths.APP.mkdir(parents=True, exist_ok=True)
            with (paths.APP / "ui-errors.log").open("a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(message)[:2000] + "\n")
        except OSError:
            pass

    def boot(self):
        page = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--page=")), None)
        return {"found": paths.FOUND, "lang": self._cfg["lang"], "langs": i18n.LANGS, "strings": strings(),
                "start_page": page,
                "root": str(ROOT), "cfg": {k: self._cfg[k] for k in ("mods", "prompts", "backup_before_play",
                                                                   "backup_keep", "close_on_play", "theme",
                                                                   "check_updates")},
                "version": core.VERSION}

    def set_lang(self, code):
        self._set_cfg("lang", code)
        i18n.set_lang(code)
        return self.boot()

    def set_option(self, key, value):
        if key in ("mods", "prompts", "backup_before_play", "backup_keep", "close_on_play", "theme",
                   "check_updates"):
            self._set_cfg(key, value)
        return True

    def title_bar(self, dark, color):
        """Matches the window's title bar to the theme: dark (bool) and the caption colour (#rrggbb)."""
        set_title_bar(bool(dark), str(color))
        return True

    def _set_cfg(self, key, value):
        self._cfg[key] = value
        if paths.FOUND:
            core.save_config(self._cfg)

    def status(self):
        with self._lock:
            events, self._events = self._events, []
        state = ("preparing" if self._preparing else "running" if self._running
                 else "closed" if self._was_running else "ready")
        return {"state": state, "events": events}

    def _watch(self):
        """Notices the game starting and stopping (also when started elsewhere)."""
        while True:
            on = (self._proc is not None and self._proc.poll() is None) or core.game_running()
            if on != self._running:
                if self._running and not on:
                    self._was_running = True
                    threading.Thread(target=self._check_achievements, daemon=True).start()
                    time.sleep(1.5)   # the game writes its last log lines while it closes
                    if core.count_session(self._cfg):
                        core.save_config(self._cfg)
                self._running = on
            time.sleep(2.5)

    def _push(self, event):
        with self._lock:
            self._events.append(event)

    # -- home
    def home(self):
        mods, patches = core.mod_files(core.MODS), core.mod_files(core.PATCHES)
        return {
            "exe": core.EXE.exists(), "version": core.installed_version(),
            "gpu": core.log_fact(r"vk: using gpu \d+: (.+)"), "mods": len(mods), "mods_on": self._cfg["mods"],
            "patches": len(patches), "last": last_start(), "session": last_session(),
            "fps": core.read_ini().get("fps_limit", "60"), "play": self._cfg.get("play", {}),
            "play_time": core.play_time(), "game_version": game_version(), "recomp": core.installed_release(),
            "recomp_build": core.installed_build(),
        }

    def recent_log(self):
        return "\n".join(core.log_lines(80))

    def updates(self):
        """Newer recomp and launcher releases (cached for six hours); {} when the check is turned off."""
        if not self._cfg.get("check_updates", True):
            return {}
        before = (self._cfg.get("update_cache") or {}).get("time")
        out = core.check_updates(self._cfg)
        if self._cfg["update_cache"].get("time") != before:
            core.save_config(self._cfg)
        return out

    def open_url(self, url):
        if str(url).startswith("https://github.com/"):
            os.startfile(url)
        return True

    # -- mods
    def mods(self):
        return {"items": core.mod_list(self._cfg), "on": self._cfg["mods"], "folder": str(core.LIBRARY)}

    def set_mod(self, name, on):
        off = [n for n in self._cfg.get("mods_off", []) if n != name]
        if not on:
            off.append(name)
        self._set_cfg("mods_off", off)
        return self.mods()

    def add_mod(self):
        import webview
        res = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not res:
            return {"ok": False}
        folder = Path(res[0] if isinstance(res, (list, tuple)) else res)
        if folder.resolve() in (core.MODS.resolve(), core.LIBRARY.resolve()) or core.LIBRARY.resolve() in folder.resolve().parents:
            return {"ok": False, "message": t("That folder is already used by the launcher.",
                                              "Bu klasör zaten launcher tarafından kullanılıyor.")}
        if not core.mod_files(folder):
            return {"ok": False, "message": t("That folder has no files.", "Bu klasörde dosya yok.")}
        name = core.add_mod(folder)
        return {"ok": True, "message": t(f"Added: {name}", f"Eklendi: {name}")}

    def quick_fps(self, value):
        changes = {"fps_limit": value}
        if value not in ("30", "60"):
            changes["realtime"] = "1"
        core.write_ini(changes, core.SECTIONS)
        return True

    # -- settings
    def settings(self):
        ini = core.read_ini()
        groups = []
        for title, items in core.setting_groups():
            groups.append({"title": title, "items": [
                {"key": key, "label": label, "kind": kind, "choices": list(choices), "default": default,
                 "value": ini.get(key, default), "help": help_}
                for key, _sec, label, kind, choices, default, help_ in items]})
        return {"groups": groups, "gpus": [[i, n] for i, n in core.gpus_from_log()]}

    def save_settings(self, values):
        out = {}
        for _, items in core.setting_groups():
            for key, _sec, label, kind, *_rest in items:
                v = values.get(key)
                if kind == "bool":
                    v = "1" if v else "0"
                elif kind == "gpu":
                    v = v or None
                else:
                    v = str(v).strip()
                    if kind == "combo" and key != "render_scale" and not __import__("re").fullmatch(
                            r"\d{3,4}x\d{3,4}", v):
                        return {"ok": False, "message": t(f"{label}: use the form 1920x1080.",
                                                          f"{label}: 1920x1080 biçiminde olmalı.")}
                    if key == "render_scale" and v != "game" and not (v.isdigit() and 25 <= int(v) <= 400):
                        return {"ok": False, "message": t(f"{label}: 'game' or a number from 25 to 400.",
                                                          f"{label}: 'game' ya da 25-400 arası bir sayı olmalı.")}
                out[key] = v
        cur = core.read_ini()
        changes = {k: v for k, v in out.items() if cur.get(k) != v and not (v is None and k not in cur)}
        if not changes:
            return {"ok": True, "message": t("No changes", "Değişiklik yok")}
        core.write_ini(changes, core.SECTIONS)
        n = len(changes)
        return {"ok": True, "message": t(f"{n} settings saved", f"{n} ayar kaydedildi")}

    def reset_settings(self):
        core.write_ini({k: None for k in core.SECTIONS}, core.SECTIONS)
        return {"ok": True, "message": t("Back to defaults", "Varsayılanlara dönüldü")}

    def open_ini(self):
        if core.INI.exists():
            os.startfile(core.INI)

    def choose_game(self):
        import webview
        # pywebview filters must look like "Description (*.ext)"
        res = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                                              file_types=("TotK game (*.exe)",))
        if not res:
            return {"ok": False}
        exe = Path(res[0] if isinstance(res, (list, tuple)) else res)
        if exe.name.lower() != "totk.exe" or not exe.is_file():
            return {"ok": False, "message": t("Please select totk.exe, the game of the PC recomp.",
                                              "Lütfen PC recomp'un oyun dosyası totk.exe'yi seçin.")}
        paths.save_game_folder(exe.parent)
        threading.Timer(0.3, restart).start()
        return {"ok": True}

    # -- controls
    def controls(self):
        ini = core.read_ini()
        sens = ini.get("mouse_sens", "1")
        return {
            "binds": prompts.parse_binds(ini), "defaults": prompts.DEFAULT_KEYS,
            "buttons": [{"id": b, "group": t(*g), "label": t(*d), "stick": b in prompts.STICK_DIRS}
                        for b, g, d, _k, _p in prompts.BUTTONS],
            "key_labels": {k: prompts.key_label(k) for k in prompts.KEY_NAMES},
            "pads": [[p, prompts.pad_label(p)] for p in prompts.PAD_NAMES],
            "prompt_sets": [["keyboard", "keyboard_mouse"], ["switch", None]]
            + ([["mod", "mod_icons"]] if self._cfg["mods"] and prompts.mod_prompts_available() else []),
            "prompts": self._cfg["prompts"], "available": prompts.prompts_available(),
            "pad_layout": ini.get("pad_layout", "auto"), "mouse_sens": int(sens) if sens.isdigit() else 1,
        }

    def preview(self, prompt_set, binds):
        try:
            img = prompts.strip(prompt_set, binds, self._cfg["mods"], "#efe6cf", "#000000", 56)
        except Exception as e:  # noqa: BLE001 - shown on the page
            return {"ok": False, "message": str(e)}
        img = img.convert("L").point(lambda v: v)  # white on black -> mask
        rgba = __import__("PIL.Image", fromlist=["Image"]).new("RGBA", img.size, (239, 230, 207, 0))
        rgba.putalpha(img)
        buf = io.BytesIO()
        rgba.save(buf, "PNG")
        return {"ok": True, "src": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}

    def save_controls(self, binds, pads, layout, sens):
        changes = {}
        for b in prompts.DEFAULT_KEYS:
            keys = [k for k in binds.get(b, {}).get("keys", []) if k in prompts.KEY_NAMES]
            pad = pads.get(b, "default")
            changes["bind_" + b.lower()] = prompts.bind_line(b, keys, pad)
        changes["pad_layout"] = layout
        changes["mouse_sens"] = str(int(sens))
        cur = core.read_ini()
        changes = {k: v for k, v in changes.items() if cur.get(k) != v and not (v is None and k not in cur)}
        if not changes:
            return {"ok": True, "message": t("No changes", "Değişiklik yok")}
        core.write_ini(changes, {**core.SECTIONS, **{k: "input" for k in changes}})
        return {"ok": True, "message": t("Controls saved", "Kontroller kaydedildi")
                + (t(" · prompts update on the next start", " · simgeler bir sonraki açılışta güncellenir")
                   if self._running else "")}

    def reset_controls(self):
        core.write_ini({"bind_" + b.lower(): None for b in prompts.DEFAULT_KEYS}, core.SECTIONS)
        return {"ok": True, "message": t("Bindings reset", "Atamalar sıfırlandı")}

    # -- saves
    def saves(self):
        fmt = t("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M")
        slots = []
        for slot in core.save_slots():
            d = core.slot_summary(slot)
            d["time"] = time.strftime(fmt, time.localtime(d["time"]))
            slots.append(d)
        return {"backups": [{"name": b.name, "size": round(core.dir_size(b) / 1048576, 1)}
                            for b in core.list_backups()[:40]], "slots": slots}

    def backup_now(self):
        d = core.backup_saves("manual", 0)
        return {"ok": bool(d), "message": t(f"Backed up: {d.name}", f"Yedeklendi: {d.name}") if d
                else t("No saves to back up", "Yedeklenecek kayıt yok")}

    def restore(self, name):
        if self._running:
            return {"ok": False, "message": t("Close the game first.", "Önce oyunu kapatın.")}
        src = core.SAVE_BACKUPS / name
        if not src.is_dir() or src.parent != core.SAVE_BACKUPS:
            return {"ok": False, "message": "?"}
        core.backup_saves("before-restore", 0)
        if core.SAVE.exists():
            shutil.rmtree(core.SAVE)
        shutil.copytree(src, core.SAVE)
        return {"ok": True, "message": t("Restored", "Geri yüklendi")}

    def delete_backup(self, name):
        p = core.SAVE_BACKUPS / name
        if p.is_dir() and p.parent == core.SAVE_BACKUPS:
            shutil.rmtree(p, ignore_errors=True)
        return {"ok": True}

    def open_folder(self, which):
        folder = {"logs": core.LOGS, "game": ROOT, "saves": core.SAVE, "backups": core.SAVE_BACKUPS,
                  "mods": core.LIBRARY}[which]
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def shortcut(self):
        try:
            if FROZEN:
                core.create_shortcut(sys.executable, "", sys.executable)
            else:
                pyw = Path(sys.executable).with_name("pythonw.exe")
                core.create_shortcut(str(pyw if pyw.exists() else sys.executable), str(Path(__file__).resolve()),
                                     str(core.EXE))
            return {"ok": True, "message": t("Added a 'TotK Launcher' shortcut to the desktop",
                                             "Masaüstüne 'TotK Launcher' kısayolu eklendi")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}

    # -- achievements
    def _check_achievements(self, quiet_first=False):
        unlocked = dict(self._cfg.get("achievements", {}))
        first = not unlocked
        try:
            best, new = achievements.evaluate(core.SAVE, unlocked)
        except Exception:  # noqa: BLE001 - a broken save must not stop the launcher
            return []
        self._ach_stats = best
        if new:
            self._set_cfg("achievements", unlocked)
            if first and quiet_first and len(new) > 1:
                self._push({"type": "toast", "message": t(f"{len(new)} achievements unlocked from your saves",
                                                          f"Kayıtlarından {len(new)} başarım açıldı")})
            else:
                for aid in new:
                    a = next(x for x in achievements.ACHIEVEMENTS if x[0] == aid)
                    self._push({"type": "achievement", "icon": a[2], "title": t(*a[3]), "desc": t(*a[4])})
        self._push({"type": "achievements_changed"})
        return new

    def check_achievements(self):
        self._check_achievements()
        return self.achievements()

    def achievements(self):
        unlocked = self._cfg.get("achievements", {})
        best = self._ach_stats
        items = []
        for aid, cat, icon, title, desc, stat, target in achievements.ACHIEVEMENTS:
            value = None if best is None else min(best.get(stat, 0), target)
            items.append({"id": aid, "cat": cat, "icon": icon, "title": t(*title), "desc": t(*desc),
                          "target": target, "value": value, "unlocked": unlocked.get(aid)})
        return {"items": items, "loaded": best is not None, "play": self._cfg.get("play", {}),
                "play_time": core.play_time(),
                "categories": [[c, t(*n)] for c, n in achievements.CATEGORIES]}

    # -- cheats
    def cheats(self, slot=None):
        slots = core.save_slots()
        if not slots:
            return {"slots": []}
        chosen = next((s for s in slots if str(s) == slot), slots[0])
        try:
            values = core.read_cheats(chosen)
        except (OSError, ValueError) as e:
            return {"slots": [], "error": str(e)}
        try:
            pouches = core.read_pouches(chosen)
        except (OSError, ValueError, struct.error):
            pouches = {"fields": [], "missing": [], "worn": 0}
        fmt = t("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M")
        return {
            "slots": [{"id": str(s), "label": f"{s.name} · {time.strftime(fmt, time.localtime((s / 'progress.sav').stat().st_mtime))}"}
                      for s in slots],
            "slot": str(chosen), "running": self._running,
            "fields": [{"key": key, "label": label, "help": help_, "max": top, "value": values[key],
                        "step": 0.2 if key == "stamina" else 1, "min": 0 if key in core.ZERO_MIN else 1}
                       for key, _n, _k, _u, top, label, help_ in core.cheats() if key in values],
            "pouch_fields": pouches["fields"], "missing": pouches["missing"], "worn": pouches["worn"],
        }

    def apply_cheats(self, slot, values):
        if self._running or core.game_running():
            return {"ok": False, "message": t("Close the game first.", "Önce oyunu kapatın.")}
        chosen = next((s for s in core.save_slots() if str(s) == slot), None)
        if chosen is None:
            return {"ok": False, "message": "?"}
        now = core.read_cheats(chosen)
        tops = {key: top for key, _n, _k, _u, top, *_r in core.cheats()}
        repair = bool(values.pop("repair", False))
        pouch_keys = {k for k, *_r in core.POUCH_SLOTS} | {k for k, *_r in core.POUCH_ITEMS}
        pouch_values = {}
        for key in [k for k in values if k in pouch_keys]:
            try:
                pouch_values[key] = int(float(str(values.pop(key)).replace(",", ".")))
            except ValueError:
                return {"ok": False, "message": t("Not a number", "Geçersiz sayı")}
        out = {}
        for key, v in values.items():
            try:
                v = float(str(v).replace(",", "."))
            except ValueError:
                return {"ok": False, "message": t(f"Not a number: {v}", f"Geçersiz sayı: {v}")}
            if key not in now or abs(v - now[key]) < 1e-6:
                continue  # untouched: keep the save's value
            v = max(0 if key in core.ZERO_MIN else 1, min(tops[key], v))
            out[key] = round(v * 5) / 5 if key == "stamina" else int(v)
        now_pouch = {f["key"]: f["value"] for f in core.read_pouches(chosen)["fields"]}
        pouch_values = {k: v for k, v in pouch_values.items() if now_pouch.get(k) != v}
        if not out and not pouch_values and not repair:
            return {"ok": True, "message": t("No changes", "Değişiklik yok")}
        core.backup_saves("before-cheats", 0)
        if out:
            core.write_cheats(chosen, out)
        if pouch_values or repair:
            core.write_pouches(chosen, pouch_values, repair)
        return {"ok": True, "message": t(f"Cheats written to {chosen.name}", f"Hileler {chosen.name} yuvasına yazıldı")}

    # -- play
    def play(self):
        try:
            return self._play()
        except Exception as e:  # noqa: BLE001 - shown on the page instead of failing silently
            self._preparing = False
            self.log(f"play: {e!r}")
            return {"ok": False, "message": t(f"Could not start the game: {e}", f"Oyun başlatılamadı: {e}")}

    def _play(self):
        if not core.EXE.exists():
            return {"ok": False, "message": t("totk.exe not found", "totk.exe bulunamadı")}
        if self._running or self._preparing:
            return {"ok": False, "message": t("The game is already running.", "Oyun zaten çalışıyor.")}
        if self._cfg["backup_before_play"]:
            try:
                core.backup_saves("auto", int(self._cfg["backup_keep"]))
            except OSError:
                pass
        env, build = core.game_env(self._cfg)
        self._preparing = build
        threading.Thread(target=self._start, args=(env, build), daemon=True).start()
        return {"ok": True}

    def _start(self, env, build):
        if build:
            try:
                core.build_prompts(self._cfg, env)
            except Exception as e:  # noqa: BLE001 - shown, the game still starts with its own prompts
                self._push({"type": "toast", "message": t(f"Could not prepare the button prompts: {e}",
                                                          f"Tuş simgeleri hazırlanamadı: {e}")})
                if not self._cfg["mods"]:
                    core.EMPTY.mkdir(parents=True, exist_ok=True)
                    env["TOTK_ROMFS_MODS"] = str(core.EMPTY)
        try:
            self._proc = core.launch(env)
            self._running = True
        except OSError as e:
            self._push({"type": "toast", "message": t(f"Could not start the game: {e}", f"Oyun başlatılamadı: {e}")})
        self._preparing = False
        if self._running and self._cfg["close_on_play"]:
            time.sleep(1.5)
            self._window.destroy()


def restart() -> None:
    """Starts the launcher again (the game folder is read once, at start) and ends this one."""
    import subprocess
    args = [sys.executable] if FROZEN else [sys.executable, str(Path(__file__).resolve())]
    subprocess.Popen(args, cwd=str(Path(args[-1]).parent), creationflags=core.NO_WINDOW)
    os._exit(0)


def set_title_bar(dark: bool, color: str = "#182935") -> None:
    """Dark or light title bar with the caption colour of the page (the theme sets it at start and on a change)."""
    try:
        import ctypes
        for _ in range(50):
            hwnd = ctypes.windll.user32.FindWindowW(None, "TotK Launcher")
            if hwnd:
                break
            time.sleep(0.1)
        on = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
        r, g, b = (int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        caption = ctypes.c_int(b << 16 | g << 8 | r)  # COLORREF is 0x00BBGGRR
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))
    except Exception:  # noqa: BLE001 - cosmetic
        pass


def main():
    if "--selftest" in sys.argv:
        return core.selftest()
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("totk.launcher")
    except Exception:  # noqa: BLE001
        pass
    if paths.FOUND:
        core.migrate_old_names()
    import webview
    api = Api()
    light = api._cfg["theme"] == "light"
    paper = "#f2d4ac" if light else "#182935"   # the background of the page, shown before it loads
    window = webview.create_window("TotK Launcher", str(UI), js_api=api, width=1240, height=800,
                                   min_size=(1040, 660), background_color=paper, text_select=False)
    api._window = window
    webview.start(set_title_bar, args=(not light, paper), gui="edgechromium", icon=str(RES / "icon.ico"),
                  debug="--debug" in sys.argv,
                  storage_path=str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TotK Launcher" / "webview"))


if __name__ == "__main__":
    main()
