<p align="center"><img src="docs/icon.png" width="96" alt=""></p>

<h1 align="center">TotK Launcher</h1>

<p align="center">
  A launcher for the <b>Tears of the Kingdom PC recomp</b>: settings, key rebinding, keyboard &amp; mouse button prompts,
  achievements, save backups and cheats, in one window.<br>
  <a href="https://github.com/FurkanAnc/totk-launcher/releases/latest"><b>Download the latest release</b></a>
</p>

![Home](docs/home.png)

## About

The PC recomp of Tears of the Kingdom is configured through `totk.ini` and environment variables, and its button icons
are the Switch ones. TotK Launcher puts all of that in one place:

- set the frame rate, resolution, upscaler and other options without editing `totk.ini` by hand,
- rebind every button on keyboard, mouse and controller,
- see **your own keys** in the game instead of A / B / X / Y, the action prompt in the corner included,
- track 55 achievements read from your saves,
- back up and restore saves, and tweak rupees, hearts, stamina and battery.

It runs on Windows 10 and 11, in English or Turkish (Settings > Interface language). It ships **no game files**: the
little it needs for the button icons is read from your own installation.

## Screenshots

| Night theme | Controls |
|---|---|
| ![Night theme](docs/home-night.png) | ![Controls](docs/controls.png) |

| Achievements |
|---|
| ![Achievements](docs/achievements.png) |

## Features

- **Home**: the installed version, graphics card and mods in one line, the frame rate of your last session (average
  and 1% low, from the game's own log), a quick frame rate limit and the latest game log.
- **Themes**: Light (default) or Night, in Settings > Launcher.
- **Settings**: frame rate, display, language and sound options, written to `totk.ini` without touching its comments
  (a backup is taken before every save).
- **Controls**: rebind keyboard, mouse and controller buttons (click a cell, press a key or a mouse button), controller
  layout and mouse camera sensitivity. Writes the game's own `bind_*` lines.
- **Button prompts**: the in-game button icons can show your **keyboard and mouse** keys (drawn from your bindings,
  the action prompt in the corner included), the original **Switch** icons, or the icons of a font mod in
  `romfs_mods`.
- **Achievements**: 55 achievements in five categories (story, exploration, collection, combat, hero), read from
  your saves after every session: temples, shrines, Lightroots, Korok seeds, caves, wells, bosses, Lynels, Flurry
  Rushes, the Compendium and more. A popup shows new ones; saves from the prologue do not count.
- **Saves**: automatic backup before every launch, manual backups, restore.
- **Cheats**: rupees, hearts, stamina wheels and battery cells in a save slot (while the game is closed).

## Install

You need the Tears of the Kingdom PC recomp already installed (the folder with `totk.exe` and `romfs`), on Windows 10
or 11 (the window uses Microsoft Edge WebView2, which they include).

1. Download `TotK Launcher.exe` from the [latest release](https://github.com/FurkanAnc/totk-launcher/releases/latest).
2. Start it. Then either:
   - **Put it in the game folder**, next to `totk.exe`: it finds the game by itself, or
   - **Start it from anywhere** (Downloads, Desktop…): the first time it asks you to select `totk.exe` and
     remembers the folder. Settings > Launcher > Game folder changes it later.
3. Press **PLAY**. Home > Recent log > Desktop shortcut adds a shortcut.

Windows SmartScreen may warn about an unknown publisher the first time, since the exe is not signed: choose
"More info" > "Run anyway".

## How the button prompts work

When you press PLAY the launcher reads what it needs from your own extracted RomFS (`romfs\index.json` and
`romfs\romfs.bin`: the zstd dictionaries, the button font, the Common layout archive, the message archive of your game
language and the resource size table), redraws the prompts and writes the result to `launcher\rt\mods` and
`launcher\rt\patches` in the game folder. The game is started with `TOTK_ROMFS_MODS` and `TOTK_ROMFS_PATCHES` pointing
there. Your own `romfs_mods` and `romfs-patches` folders are copied, never changed.

The first launch after a change takes about 10 seconds; later launches reuse the result.

## Files it creates

In the game folder:

| Path | What |
|---|---|
| `launcher\launcher.json` | launcher options and unlocked achievements |
| `launcher\ini-backups\` | the last 10 copies of `totk.ini` |
| `launcher\rt\` | the prompt overlays (safe to delete) |
| `profile\launcher-backups\` | save backups |

And `%APPDATA%\TotK Launcher\location.json`: the game folder, when the exe is not in it.

To uninstall, delete `TotK Launcher.exe`, the `launcher` folder in the game folder and `%APPDATA%\TotK Launcher`.

## Building from source

With Python 3.10+ on Windows:

```
pip install -r launcher\requirements.txt pyinstaller
launcher\build_exe.cmd
```

The exe is written to `launcher\dist`. `python launcher\launcher.pyw` runs it without building (put the `launcher`
folder next to `totk.exe`, or select the game on the first start).

The code: `launcher.pyw` (window and the API the page calls), `ui/` (the page: HTML, CSS, JavaScript), `core.py`
(settings, saves, cheats, starting the game), `prompts.py` (bindings and button prompts), `achievements.py`, `paths.py`
and `i18n.py`.

## Türkçe

Tears of the Kingdom PC recomp için launcher: ayarlar, tuş atama, oyunda klavye/fare tuş simgeleri (aksiyon simgesi
dahil), 55 başarım, kayıt yedekleme ve hileler. Açık ve gece teması var. [Son sürümden](https://github.com/FurkanAnc/totk-launcher/releases/latest)
`TotK Launcher.exe`'yi indirin; `totk.exe`'nin yanına koyun ya da herhangi bir yerden açıp `totk.exe`'yi seçin. Arayüz
dili Settings > Interface language'dan Türkçe yapılabilir.

## Credits

The achievement flag lists (`launcher/achievement_data.json`) come from the
[Zelda: Tears of the Kingdom savegame editor](https://github.com/marcrobledo/savegame-editors) by Marc Robledo, with
research by MacSpazzy, Phil, savage13, Karlos007, Echocolat and MrCheeze. MIT License, Copyright (c) 2017-2023 Marc
Robledo.

Fonts: [Cinzel](https://fonts.google.com/specimen/Cinzel), [Nunito Sans](https://fonts.google.com/specimen/Nunito+Sans) and
[Fraunces](https://fonts.google.com/specimen/Fraunces), SIL Open Font License (`launcher/ui/fonts`).

The pictures in `launcher/ui/img` (the backgrounds, the PLAY plate and the app icon) were made for this launcher; it
uses no logo or picture from the game.

## License

MIT, see [LICENSE](LICENSE). Not affiliated with Nintendo; The Legend of Zelda: Tears of the Kingdom is a trademark of
Nintendo.
