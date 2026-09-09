$ErrorActionPreference = "Stop"

Write-Host "Building server.exe..."
pyinstaller --clean --onefile --console --name server server.py --noupx --noconfirm
Write-Host "Done: dist\server.exe"
