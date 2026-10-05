# mkv-ko-subs 스킬 설치 (Windows PowerShell)
# 사용: PowerShell 에서  .\install.ps1   (실행 정책 오류 시: powershell -ExecutionPolicy Bypass -File .\install.ps1)
$ErrorActionPreference = "Stop"
$dest = Join-Path $env:USERPROFILE ".claude\skills\mkv-ko-subs"
$src  = Split-Path -Parent $MyInvocation.MyCommand.Path

foreach ($c in @("mkvmerge", "mkvextract", "ffmpeg")) {
    if (-not (Get-Command $c -ErrorAction SilentlyContinue)) {
        Write-Warning "'$c' 를 찾을 수 없습니다. PATH 에 있어야 합니다. (winget install MoritzBunkus.MKVToolNix Gyan.FFmpeg)"
    }
}
if (-not ((Get-Command python -ErrorAction SilentlyContinue) -or (Get-Command py -ErrorAction SilentlyContinue))) {
    Write-Warning "Python 3 가 없습니다. (winget install Python.Python.3.12)"
}

New-Item -ItemType Directory -Force -Path (Join-Path $dest "scripts") | Out-Null
Copy-Item (Join-Path $src "SKILL.md") (Join-Path $dest "SKILL.md") -Force
Copy-Item (Join-Path $src "scripts\mkv_subs.py") (Join-Path $dest "scripts\mkv_subs.py") -Force
Write-Host "설치 완료: $dest"
Write-Host "Claude Code 를 새 세션으로 시작하면 /mkv-ko-subs 로 사용할 수 있습니다."
