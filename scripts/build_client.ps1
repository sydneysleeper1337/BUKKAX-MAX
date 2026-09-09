$ErrorActionPreference = "Stop"

$ArgsList = @(
    "--clean",
    "--onefile",
    "--noconsole",
    "--name", "Bukkax",
    "--noupx",
    "--noconfirm",
    "client_qt.py"
)

$DataDirs = @(
    "bukkax_chess_assets",
    "sounds",
    "bukkax_chess_sounds"
)

foreach ($Dir in $DataDirs) {
    if (Test-Path $Dir) {
        $ArgsList += @("--add-data", "$Dir;$Dir")
    }
}

if (Test-Path "bukkax_builder_config.json") {
    $ArgsList += @("--add-data", "bukkax_builder_config.json;.")
}

$HiddenModules = @(
    "bukkax_dev_builder",
    "bukkax_builder_sync",
    "bukkax_screen_share",
    "bukkax_call_quality",
    "music_player"
)

foreach ($Module in $HiddenModules) {
    if (Test-Path "$Module.py") {
        $ArgsList += @("--hidden-import", $Module)
    }
}

Write-Host "Building Bukkax.exe..."
pyinstaller @ArgsList
Write-Host "Done: dist\Bukkax.exe"
