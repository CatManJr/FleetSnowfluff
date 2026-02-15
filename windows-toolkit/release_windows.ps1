param(
    [string]$Version = "",
    [switch]$SkipVideoConvert
)

$ErrorActionPreference = "Stop"

if (-not $IsWindows) {
    throw "This script only supports Windows."
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
$ReleaseDir = Join-Path $ProjectRoot "release"
$BuildDir = Join-Path $ScriptDir "build"
$ResourceStageDir = Join-Path $BuildDir "resources_win_pack"
$AppName = "Fleet Snowfluff"

if (-not $Version) {
    $Version = python -c "from pathlib import Path; import tomllib; p=Path('pyproject.toml'); print(tomllib.loads(p.read_text(encoding='utf-8')).get('project',{}).get('version','v1.0.2') if p.exists() else 'v1.0.2')"
}

$InstallerBaseName = "FleetSnowfluff-$Version-Windows-Installer"
$AppDistDir = Join-Path $ReleaseDir $AppName
$AppExePath = Join-Path $AppDistDir "$AppName.exe"
$IssPath = Join-Path $ScriptDir "release_windows.iss"
$InstallerPath = Join-Path $ReleaseDir "$InstallerBaseName.exe"

function Remove-DeveloperData {
    $paths = @(
        (Join-Path $env:APPDATA "FleetSnowfluff"),
        (Join-Path $env:APPDATA "Aemeath"),
        (Join-Path $env:LOCALAPPDATA "FleetSnowfluff"),
        (Join-Path $env:LOCALAPPDATA "Aemeath")
    )

    foreach ($dir in $paths) {
        $chat = Join-Path $dir "chat_history.jsonl"
        $settings = Join-Path $dir "settings.json"
        if (Test-Path $chat) {
            Remove-Item $chat -Force
            Write-Host "   removed $chat"
        }
        if (Test-Path $settings) {
            Remove-Item $settings -Force
            Write-Host "   removed $settings (API key)"
        }
    }
}

function Resolve-Iscc {
    $iscc = Get-Command iscc -ErrorAction SilentlyContinue
    if ($iscc) { return $iscc.Source }

    $known = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    foreach ($path in $known) {
        if (Test-Path $path) { return $path }
    }
    throw "Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6 first."
}

function Resolve-ResourcesDir {
    $candidates = @(
        (Join-Path $ProjectRoot "resources"),
        (Join-Path (Resolve-Path (Join-Path $ProjectRoot "..")) "resources")
    )
    foreach ($path in $candidates) {
        if (Test-Path $path -PathType Container) {
            return (Resolve-Path $path).Path
        }
    }
    throw "Could not locate resources directory."
}

function New-ResourceStageOnlyMp4 {
    param(
        [string]$SourceDir,
        [string]$TargetDir
    )

    if (Test-Path $TargetDir) {
        Remove-Item $TargetDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null

    # Copy everything except .mov files.
    Get-ChildItem -Path $SourceDir -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($SourceDir.Length).TrimStart("\", "/")
        if ($_.Extension -ieq ".mov") { return }
        $dest = Join-Path $TargetDir $relative
        $destDir = Split-Path -Parent $dest
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }
        Copy-Item $_.FullName $dest -Force
    }
}

Write-Host "==> Sync dependencies"
Push-Location $ScriptDir
uv sync

Write-Host "==> Cleaning old artifacts"
New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null
Remove-Item $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $ScriptDir "__pycache__") -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $ScriptDir -Filter "*.spec" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Remove-Item $AppDistDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $InstallerPath -Force -ErrorAction SilentlyContinue

Write-Host "==> Removing developer chat history"
Remove-DeveloperData

$ResourcesDir = Resolve-ResourcesDir

if (-not $SkipVideoConvert) {
    $convertScript = Join-Path $ProjectRoot "windows-toolkit\convert_mov_to_mp4.ps1"
    if (Test-Path $convertScript) {
        Write-Host "==> Converting .mov videos to .mp4"
        & $convertScript -Root (Join-Path $ResourcesDir "Call") -Recurse
    }
}

Write-Host "==> Preparing resources (mp4 only for videos)"
New-ResourceStageOnlyMp4 -SourceDir $ResourcesDir -TargetDir $ResourceStageDir

Write-Host "==> Building app with PyInstaller"
$pyiArgs = @(
    "run", "pyinstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--distpath", $ReleaseDir,
    "--workpath", $BuildDir,
    "--specpath", $ScriptDir,
    "--name", $AppName,
    "--add-data", "$ResourceStageDir;resources",
    "--add-data", "$ScriptDir\config\FleetSnowfluff.json;resources/config",
    "$ScriptDir\main.py"
)
& uv @pyiArgs

if (-not (Test-Path $AppExePath)) {
    throw "Build failed: executable not found at $AppExePath"
}

Write-Host "==> Creating installer with Inno Setup"
$iss = @"
[Setup]
AppName=$AppName
AppVersion=$Version
DefaultDirName={autopf}\$AppName
DefaultGroupName=$AppName
OutputDir=$ReleaseDir
OutputBaseFilename=$InstallerBaseName
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
DisableDirPage=no
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\$AppName.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "$AppDistDir\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\$AppName"; Filename: "{app}\$AppName.exe"
Name: "{autodesktop}\$AppName"; Filename: "{app}\$AppName.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\$AppName.exe"; Description: "Launch $AppName"; Flags: nowait postinstall skipifsilent
"@
$iss | Set-Content -Path $IssPath -Encoding UTF8

$isccPath = Resolve-Iscc
& $isccPath $IssPath | Out-Null

# Keep only installer output in release artifacts.
Remove-Item $AppDistDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $IssPath -Force -ErrorAction SilentlyContinue
Remove-Item $ResourceStageDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Release build complete:"
Write-Host "  Installer:  $InstallerPath"

Pop-Location
