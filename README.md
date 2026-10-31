# TotK Launcher

A launcher for the Tears of the Kingdom PC recomp (`totk.exe`). English by default, Turkish available in Settings.

- **Home**: game status, graphics card, a quick frame rate limit and the latest game log.
- **Settings**: frame rate, display, language and sound options, written to `totk.ini` without touching its comments
  (a backup goes to `launcher\ini-backups` before every save).
- **Controls**: rebind keyboard, mouse and controller buttons (click a cell, press a key), controller layout and
  mouse camera sensitivity. Writes the game's own `bind_*` lines.
- **Button prompts**: the in-game button icons can show your **keyboard and mouse** keys (drawn from your bindings,
  the action prompt in the corner included), the original **Switch** icons, or the icons of a font mod in
  `romfs_mods`.
- **Saves**: automatic backup before every launch, manual backups, restore.
- **Cheats**: rupees, hearts, stamina wheels and battery cells in a save slot (while the game is closed).

## Install

1. Install [Python](https://www.python.org/downloads/) 3.10 or newer (tick "Add Python to PATH").
2. Install the libraries:

   ```
   pip install -r launcher\requirements.txt
   ```

3. Put the `launcher` folder and `TotK Launcher.cmd` in the game folder, next to `totk.exe`:

   ```
   <game folder>\totk.exe
   <game folder>\romfs\index.json, romfs.bin
   <game folder>\launcher\launcher.pyw
   <game folder>\TotK Launcher.cmd
   ```

4. Start `TotK Launcher.cmd` (or `launcher\launcher.pyw`). Home > Desktop shortcut adds a shortcut.

## How the button prompts work

No game file ships with the launcher. When you press PLAY it reads what it needs from your own extracted RomFS
(`romfs\index.json` and `romfs\romfs.bin`: the zstd dictionaries, the button font, the Common layout archive, the
message archive of your game language and the resource size table), redraws the prompts and writes the result to
`launcher\rt\mods` and `launcher\rt\patches`. The game is started with `TOTK_ROMFS_MODS` and `TOTK_ROMFS_PATCHES`
pointing there. Your own `romfs_mods` and `romfs-patches` folders are copied, never changed.

The first launch after a change takes about 10 seconds; later launches reuse the result.

## Files it creates

| Path | What |
|---|---|
| `launcher\launcher.json` | launcher options |
| `launcher\ini-backups\` | the last 10 copies of `totk.ini` |
| `launcher\rt\` | the prompt overlays (safe to delete) |
| `profile\launcher-backups\` | save backups |

To uninstall, delete the `launcher` folder and `TotK Launcher.cmd`.
