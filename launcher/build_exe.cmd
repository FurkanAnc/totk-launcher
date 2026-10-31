@echo off
rem Builds "TotK Launcher.exe" (one file, no console) into launcher\dist with PyInstaller.
rem Needs: pip install -r requirements.txt pyinstaller
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "TotK Launcher" --icon "%~dp0icon.ico" ^
  --add-data "%~dp0achievement_data.json;." --add-data "%~dp0icon.ico;." --add-data "%~dp0ui;ui" ^
  --collect-submodules fontTools.ttLib.tables --collect-all webview ^
  --exclude-module tkinter --exclude-module pygame --exclude-module numpy --exclude-module matplotlib ^
  --exclude-module scipy --exclude-module pandas --exclude-module IPython --exclude-module pytest ^
  --distpath "%~dp0dist" --workpath "%~dp0build" --specpath "%~dp0build" "%~dp0launcher.pyw"
