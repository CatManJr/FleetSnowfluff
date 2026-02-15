param(
    [string]$Root = "",
    [switch]$Recurse,
    [switch]$Overwrite
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
    $Root = Join-Path (Join-Path $PSScriptRoot "..") "resources\Call"
}
$Root = (Resolve-Path $Root).Path

if (-not (Test-Path $Root -PathType Container)) {
    throw "Input directory not found: $Root"
}

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    throw "ffmpeg not found in PATH. Install ffmpeg before converting videos."
}

$movFiles = Get-ChildItem -Path $Root -File -Recurse:$Recurse | Where-Object {
    $_.Extension -ieq ".mov"
}

if (-not $movFiles) {
    Write-Host "No .mov files found under: $Root"
    exit 0
}

$converted = 0
$skipped = 0

foreach ($mov in $movFiles) {
    $mp4Path = Join-Path $mov.DirectoryName ($mov.BaseName + ".mp4")
    if ((Test-Path $mp4Path) -and (-not $Overwrite)) {
        Write-Host "Skip existing: $mp4Path"
        $skipped++
        continue
    }

    Write-Host "Converting: $($mov.FullName)"
    $args = @(
        "-hide_banner",
        "-loglevel", "warning",
        "-y",
        "-i", $mov.FullName,
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        $mp4Path
    )
    if (-not $Overwrite) {
        $args[2] = "-n"
    }

    & ffmpeg @args
    if ($LASTEXITCODE -ne 0) {
        throw "ffmpeg failed for: $($mov.FullName)"
    }
    $converted++
}

Write-Host ""
Write-Host "Done."
Write-Host "Converted: $converted"
Write-Host "Skipped:   $skipped"
