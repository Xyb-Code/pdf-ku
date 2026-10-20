$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Test-Path -LiteralPath 'tools/ghostscript/bin/gsdll64.dll') { exit 0 }
New-Item -ItemType Directory -Force 'tools/downloads' | Out-Null
Invoke-WebRequest 'https://github.com/ip7z/7zip/releases/download/26.04/7zr.exe' -OutFile 'tools/downloads/7zr.exe'
Invoke-WebRequest 'https://github.com/ip7z/7zip/releases/download/26.04/7z2604-x64.exe' -OutFile 'tools/downloads/7zip-installer.exe'
Invoke-WebRequest 'https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10080/gs10080w64.exe' -OutFile 'tools/downloads/ghostscript-installer.exe'
# Extract only; do not run either installer or modify system installation.
& './tools/downloads/7zr.exe' x './tools/downloads/7zip-installer.exe' '-otools/7zip' -y
if ($LASTEXITCODE -ne 0) { throw '7-Zip extraction failed' }
& './tools/7zip/7z.exe' x './tools/downloads/ghostscript-installer.exe' '-otools/ghostscript' -y
if ($LASTEXITCODE -ne 0) { throw 'Ghostscript extraction failed' }
