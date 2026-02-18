# One-command Windows release build for Fleet Snowfluff.
# Builds .exe with PyInstaller and packages installer with Inno Setup.
# Aligned with release_macos.sh: paths, version, excludes, sanitize, optional resource compression.
#
# Usage:
#   .\release_windows.ps1
#   .\release_windows.ps1 -Version v1.2.0
#   $env:RESOURCE_COMPRESS="1"; .\release_windows.ps1

param(
    [string]$Version = "",
    [switch]$SkipVideoConvert
)

# Optional env (same as macOS): RESOURCE_COMPRESS=1 to optimize stage;
# JPEG_QUALITY, MP3_BITRATE, M4A_BITRATE, OGG_QUALITY for compression settings.
$ErrorActionPreference = "Stop"

# Compatible check for Windows (works on PS 5.1 and PS Core)
$IsWindowsPlatform = $IsWindows -or $env:OS -like "*Windows*"
if (-not $IsWindowsPlatform) {
    throw "This script only supports Windows."
}

# Paths aligned with release_macos.sh: ScriptDir = toolkit dir, ProjectRoot = src, RepoRoot = repo root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Join-Path $ScriptDir ".."
if (Test-Path $ProjectRoot) { $ProjectRoot = (Resolve-Path $ProjectRoot).Path }
$RepoRoot = Join-Path $ProjectRoot ".."
if (Test-Path $RepoRoot) { $RepoRoot = (Resolve-Path $RepoRoot).Path }

$ReleaseDir = Join-Path $RepoRoot "release"
$BuildDir = Join-Path $ScriptDir "build"
$ResourceStageDir = Join-Path $BuildDir "resources_release"
$AppName = "Fleet Snowfluff"

# Version from pyproject.toml (same as macOS; fallback v1.2.0beta)
if (-not $Version) {
    $PyprojectPath = Join-Path $ProjectRoot "pyproject.toml"
    $Version = & python -c "import sys,os,tomllib; path=sys.argv[-1] if len(sys.argv)>1 else ''; d=tomllib.loads(open(path,'rb').read()) if path and os.path.isfile(path) else {}; print(d.get('project',{}).get('version','v1.2.0beta'))" $PyprojectPath 2>$null
    if (-not $Version) { $Version = "v1.2.0beta" }
}

$InstallerBaseName = "FleetSnowfluff-$Version-Windows-Installer"
$AppDistDir = Join-Path $ReleaseDir $AppName
$AppExePath = Join-Path $AppDistDir "$AppName.exe"
$IssPath = Join-Path $ScriptDir "release_windows.iss"
$InstallerPath = Join-Path $ReleaseDir "$InstallerBaseName.exe"

function Remove-DeveloperData {
    # Intentionally no-op:
    # keep developer's local usage traces and settings untouched.
    # Packaging sanitization is handled on build artifacts only.
    Write-Host "   skip local data cleanup (keep developer history/settings)"
}

function Test-ReleaseBundleSafety {
    param(
        [string]$TargetDir
    )

    $forbidden = @("settings.json", "chat_history.jsonl")
    foreach ($name in $forbidden) {
        $hit = Get-ChildItem -Path $TargetDir -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -ieq $name } | Select-Object -First 1
        if ($hit) {
            throw "Sensitive runtime file leaked into bundle: $($hit.FullName)"
        }
    }

    # Same as macOS: byte-scan all files (including binary) for RELEASE_CANARY; skip >8MB
    $canary = $env:RELEASE_CANARY
    if ($canary) {
        $canaryScript = Join-Path $ScriptDir "canary_check.py"
        $TargetDirEscaped = $TargetDir -replace "'", "''"
        @"
import sys
from pathlib import Path
root = Path(r'$TargetDirEscaped')
needle = sys.argv[1] if len(sys.argv) > 1 else ''
if not needle:
    sys.exit(0)
needle_b = needle.encode('utf-8')
for p in root.rglob('*'):
    if not p.is_file():
        continue
    try:
        if p.stat().st_size > 8 * 1024 * 1024:
            continue
        data = p.read_bytes()
    except OSError:
        continue
    if needle_b in data:
        print(p)
        sys.exit(2)
sys.exit(0)
"@ | Set-Content -Path $canaryScript -Encoding UTF8
        try {
            $out = & python $canaryScript $canary 2>&1
            if ($LASTEXITCODE -eq 2) {
                throw "RELEASE_CANARY leaked into bundle: $out"
            }
        } finally {
            Remove-Item $canaryScript -Force -ErrorAction SilentlyContinue
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

# Same layout as macOS: repo root resources first
function Resolve-ResourcesDir {
    $candidates = @(
        (Join-Path $RepoRoot "resources"),
        (Join-Path $ProjectRoot "resources")
    )
    foreach ($path in $candidates) {
        if (Test-Path $path -PathType Container) {
            return $path
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

    # Ensure absolute path for string manipulation
    $absSourceDir = (Resolve-Path $SourceDir).Path

    # Check if ffmpeg is in PATH environment variable
    $ffmpegCmdStr = $null
    $ffmpegInPath = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($ffmpegInPath) {
        $ffmpegCmdStr = "ffmpeg"
        Write-Host "Found ffmpeg in PATH" -ForegroundColor Green
    } else {
        Write-Warning "ffmpeg not found in PATH. Videos will be copied/renamed (MAY CAUSE LAG)."
        Write-Warning "Please add ffmpeg to your PATH environment variable. See README.md for setup instructions."
    }

    # Copy everything. If it's a .mov file, remux it to .mp4.
    Get-ChildItem -Path $SourceDir -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($absSourceDir.Length).TrimStart("\", "/")
        
        # Calculate target path
        $targetName = $relative
        if ($_.Extension -ieq ".mov") { 
            $targetName = [System.IO.Path]::ChangeExtension($relative, ".mp4")
        }

        $dest = Join-Path $TargetDir $targetName
        $destDir = Split-Path -Parent $dest
        if (-not (Test-Path -Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }

        if ($_.Extension -ieq ".mov" -and $ffmpegCmdStr) {
            # Check if MP4 version already exists in target
            if (Test-Path $dest) {
                Write-Host "   Skipping (MP4 exists): $relative" -ForegroundColor DarkYellow
            } else {
                Write-Host "   Remuxing to MP4: $relative" -ForegroundColor DarkGray
                
                # Use call operator & to run the command string
                $argList = @("-y", "-v", "error", "-i", $_.FullName, "-c", "copy", "-movflags", "+faststart", $dest)
                & $ffmpegCmdStr $argList
                
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning "   ffmpeg failed for $relative, falling back to copy."
                    Copy-Item $_.FullName $dest -Force
                }
            }
        } else {
            # Direct copy for non-mov files or if ffmpeg missing
            if (-not (Test-Path $dest)) {
                Copy-Item $_.FullName $dest -Force
            }
        }
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
    # Skip ffmpeg steps completely. We'll handle renaming in New-ResourceStageOnlyMp4.
    Write-Host "==> Skipping ffmpeg conversion (using direct file rename instead)"
}

Write-Host "==> Generating Windows icon (.ico)"
$IconPath = Join-Path $ResourcesDir "icon.ico"
if (-not (Test-Path $IconPath)) {
    # Generate icon.ico from icon.webp using PySide6 (available in env)
    $genIconScript = @"
import sys
from pathlib import Path
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
src = Path(r'$ResourcesDir') / 'icon.webp'
dst = Path(r'$IconPath')

if src.exists():
    pix = QPixmap(str(src))
    if not pix.isNull():
        pix.save(str(dst), 'ICO')
        print(f'Generated: {dst}')
"@
    # Run the python snippet
    $genIconFile = Join-Path $ScriptDir "gen_icon.py"
    $genIconScript | Set-Content -Path $genIconFile -Encoding UTF8
    python $genIconFile
    Remove-Item $genIconFile -Force
}

Write-Host "==> Preparing release resources"
New-ResourceStageOnlyMp4 -SourceDir $ResourcesDir -TargetDir $ResourceStageDir
if ($env:RESOURCE_COMPRESS -eq "1") {
    $jq = [int][Math]::Max(20, [Math]::Min(95, [int](if ($env:JPEG_QUALITY) { $env:JPEG_QUALITY } else { 82 })))
    $mp3 = if ($env:MP3_BITRATE) { $env:MP3_BITRATE } else { "128k" }
    $m4a = if ($env:M4A_BITRATE) { $env:M4A_BITRATE } else { "128k" }
    $ogg = if ($env:OGG_QUALITY) { $env:OGG_QUALITY } else { "4" }
    $optScript = Join-Path $ScriptDir "opt_resources.py"
    @"
import shutil, subprocess, sys
from pathlib import Path
stage = Path(r'$($ResourceStageDir -replace "'", "''")')
ffmpeg = shutil.which('ffmpeg')
jq, mp3, m4a, ogg = $jq, '$mp3', '$m4a', '$ogg'
saved = 0
for p in stage.rglob('*'):
    if not p.is_file(): continue
    suf = p.suffix.lower()
    if suf in ('.mp3','.m4a','.ogg') and ffmpeg and p.stat().st_size >= 512*1024:
        tmp = p.with_suffix(p.suffix + '.tmp')
        args = [ffmpeg,'-y','-i',str(p),'-map_metadata','-1','-vn']
        if suf == '.mp3': args += ['-c:a','libmp3lame','-b:a',mp3]
        elif suf == '.m4a': args += ['-c:a','aac','-b:a',m4a]
        else: args += ['-c:a','libvorbis','-q:a',ogg]
        args.append(str(tmp))
        if subprocess.run(args, capture_output=True).returncode == 0:
            old_sz, new_sz = p.stat().st_size, tmp.stat().st_size
            if 0 < new_sz < old_sz:
                p.unlink(missing_ok=True); tmp.replace(p); saved += old_sz - new_sz
        if tmp.exists(): tmp.unlink(missing_ok=True)
print(f'   optimized audio, saved={saved/(1024*1024):.2f}MB')
"@ | Set-Content -Path $optScript -Encoding UTF8
    & python $optScript
    Remove-Item $optScript -Force -ErrorAction SilentlyContinue
}

# Exclude modules (same as macOS) to keep bundle smaller
$PyiExcludeModules = @(
    "pytest", "_pytest", "hypothesis", "IPython", "ipykernel", "jupyter",
    "jupyter_client", "jupyter_core", "notebook", "matplotlib", "pandas", "scipy"
)

Write-Host "==> Building app with PyInstaller"
$pyiArgs = @(
    "run", "pyinstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--icon", $IconPath,
    "--distpath", $ReleaseDir,
    "--workpath", $BuildDir,
    "--specpath", $ScriptDir,
    "--name", $AppName,
    "--add-data", "$ResourceStageDir;resources",
    "--add-data", "$ProjectRoot\config\FleetSnowfluff.json;resources/config",
    "$ProjectRoot\main.py"
)
foreach ($mod in $PyiExcludeModules) {
    $pyiArgs += "--exclude-module", $mod
}
& uv @pyiArgs

if (-not (Test-Path $AppExePath)) {
    throw "Build failed: executable not found at $AppExePath"
}

Write-Host "==> Sanitizing bundle (remove developer local data artifacts)"
Get-ChildItem -Path $AppDistDir -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ieq "chat_history.jsonl" -or $_.Name -ieq "settings.json" } |
    Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "==> Auditing bundle for sensitive data leakage"
Test-ReleaseBundleSafety -TargetDir $AppDistDir

Write-Host "==> Creating installer with Inno Setup"
$iss = @"
[Setup]
AppName=$AppName
AppVersion=$Version
DefaultDirName={autopf}\$AppName
DefaultGroupName=$AppName
OutputDir=$ReleaseDir
OutputBaseFilename=$InstallerBaseName
SetupIconFile=$IconPath
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

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\FleetSnowfluff"
Type: filesandordirs; Name: "{localappdata}\FleetSnowfluff"
Type: filesandordirs; Name: "{userappdata}\Aemeath"
Type: filesandordirs; Name: "{localappdata}\Aemeath"
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
