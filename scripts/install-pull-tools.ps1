param([switch]$Interactive)
$ErrorActionPreference = "Stop"
function Refresh-ToolPath {
    $env:Path = (@($env:Path, [Environment]::GetEnvironmentVariable('Path','User'),
        [Environment]::GetEnvironmentVariable('Path','Machine'), "$env:LOCALAPPDATA\Microsoft\WinGet\Links") -join ';')
}
try {
    Refresh-ToolPath
    $packages = [ordered]@{ "ffmpeg" = "Gyan.FFmpeg"; "deno" = "DenoLand.Deno"; "yt-dlp" = "yt-dlp.yt-dlp" }
    foreach ($tool in $packages.Keys) {
        if ($tool -eq "ffmpeg" -and (Get-Command ffmpeg -ErrorAction SilentlyContinue) -and (Get-Command ffprobe -ErrorAction SilentlyContinue)) { continue }
        if ($tool -ne "ffmpeg" -and (Get-Command $tool -ErrorAction SilentlyContinue)) { continue }
        winget install --id $packages[$tool] --exact --source winget --accept-package-agreements --accept-source-agreements
        Refresh-ToolPath
        if (-not (Get-Command $tool -CommandType Application -ErrorAction SilentlyContinue)) { throw "Could not find $tool after installation. Check the WinGet output above." }
    }
    foreach ($name in 'ffmpeg','ffprobe','yt-dlp','deno') {
        if (-not (Get-Command $name -CommandType Application -ErrorAction SilentlyContinue)) { throw "Missing $name after installation." }
    }
    Write-Output "Video Pull tools are ready. Return to TubeVault and retry the pull."
} catch {
    Write-Host $_.Exception.Message
    if ($Interactive) { Read-Host 'Press Enter to close' }
    exit 1
}
