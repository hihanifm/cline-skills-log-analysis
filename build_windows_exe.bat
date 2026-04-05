@echo off
:: build_windows_exe.bat — Build cline-log-analysis-setup.exe on Windows.
::
:: Prerequisites (run once):
::   pip install pyinstaller
::
:: Output: dist\cline-log-analysis-setup.exe

echo.
echo  Installing PyInstaller...
pip install pyinstaller
if errorlevel 1 (
    echo  ERROR: pip install pyinstaller failed. Is Python in PATH?
    pause
    exit /b 1
)

echo.
echo  Building exe...
pyinstaller --onefile --console --name cline-log-analysis-setup ^
  --add-data "skills;skills" ^
  --add-data "yaml_utils.py;." ^
  --add-data "config.py;." ^
  --add-data "workflow_config.yaml;." ^
  windows_installer.py

if errorlevel 1 (
    echo.
    echo  ERROR: PyInstaller failed. See output above.
    pause
    exit /b 1
)

echo.
echo  Done! Installer is at: dist\cline-log-analysis-setup.exe
echo  Share that file with Windows users — no Python required to run it.
echo.
pause
