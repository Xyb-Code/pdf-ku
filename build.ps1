$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& powershell -NoProfile -ExecutionPolicy Bypass -File './prepare_engine.ps1'
if ($LASTEXITCODE -ne 0) { throw 'Engine preparation failed' }
& './.venv/Scripts/python.exe' -m PyInstaller --noconfirm --onefile --windowed --name 'PDF简作' `
    --collect-all customtkinter --collect-all tkinterdnd2 `
    --add-binary 'tools/ghostscript/bin/gsdll64.dll;ghostscript/bin' `
    --add-data 'tools/ghostscript/Resource;ghostscript/Resource' `
    --add-data 'tools/ghostscript/iccprofiles;ghostscript/iccprofiles' `
    --add-data 'tools/ghostscript/lib;ghostscript/lib' `
    --add-data 'tools/ghostscript/doc/COPYING;ghostscript' app.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }

