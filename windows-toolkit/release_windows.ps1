param(
    [string]$Version = "",
    [switch]$SkipVideoConvert
)

$ErrorActionPreference = "Stop"

# Compatible check for Windows (works on PS 5.1 and PS Core)
$IsWindowsPlatform = $IsWindows -or $env:OS -like "*Windows*"
if (-not $IsWindowsPlatform) {
    throw "This script only supports Windows."
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Try to keep paths relative if possible, but Resolve-Path usually returns absolute.
# We will use relative path calculation based on ScriptDir for clarity in output.
$ProjectRoot = Join-Path $ScriptDir ".."
if (Test-Path $ProjectRoot) { $ProjectRoot = (Resolve-Path $ProjectRoot).Path }

# Ensure release folder is parallel to src (ProjectRoot is src currently based on user context, wait)
# The user cloned to 'src'. So $ScriptDir is .../src/windows-toolkit.
# $ProjectRoot is .../src.
# Parallel to src means .../release, which is .../src/../release.
$ReleaseDir = Join-Path (Join-Path $ProjectRoot "..") "release"
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

    $canary = $env:RELEASE_CANARY
    if ($canary) {
        $files = Get-ChildItem -Path $TargetDir -Recurse -File -ErrorAction SilentlyContinue
        foreach ($f in $files) {
            try {
                if ($f.Length -gt 8MB) { continue }
                $content = [System.IO.File]::ReadAllText($f.FullName)
                if ($content -like "*$canary*") {
                    throw "LEAKED_CANARY::$($f.FullName)"
                }
            } catch {
                if ($_.Exception.Message -like "LEAKED_CANARY::*") {
                    $path = $_.Exception.Message.Substring("LEAKED_CANARY::".Length)
                    throw "RELEASE_CANARY leaked into bundle: $path"
                }
                # Ignore unreadable/binary files.
            }
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
        (Join-Path $ProjectRoot "..\resources")
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

function Resolve-ResourcesDir {
    $candidates = @(
        (Join-Path $ProjectRoot "resources"),
        (Join-Path $ProjectRoot "..\resources")
    )
    foreach ($path in $candidates) {
        if (Test-Path $path -PathType Container) {
            return $path
        }
    }
    throw "Could not locate resources directory."
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

Write-Host "==> Preparing resources (mp4 only for videos)"
New-ResourceStageOnlyMp4 -SourceDir $ResourcesDir -TargetDir $ResourceStageDir

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
& uv @pyiArgs

if (-not (Test-Path $AppExePath)) {
    throw "Build failed: executable not found at $AppExePath"
}

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
