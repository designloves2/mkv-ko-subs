# mkv-ko-subs

MKV 영상의 자막을 한글화하는 [Claude Code](https://claude.com/claude-code) 스킬.

- 영어 자막(내장/외부)을 한국어로 번역하거나, 외부 한글 자막을 그대로 사용
- 영상의 기존 자막을 전부 지우고 **1. 한글(SRT, 기본) / 2. 영어(원본 타입)** 두 개만 넣어 `done/`에 저장
- 규칙 전문은 [SKILL.md](SKILL.md)

## 설치 (다른 컴퓨터 포함)

필요: `mkvtoolnix`(mkvmerge/mkvextract), `ffmpeg`, `python3` — 모두 PATH에 있어야 합니다.

### macOS / Linux
```bash
# macOS: brew install mkvtoolnix ffmpeg
git clone https://github.com/designloves2/mkv-ko-subs.git
cd mkv-ko-subs && ./install.sh
```

### Windows (PowerShell)
```powershell
winget install MoritzBunkus.MKVToolNix Gyan.FFmpeg Python.Python.3.12
git clone https://github.com/designloves2/mkv-ko-subs.git
cd mkv-ko-subs
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
winget 설치 후에는 PowerShell을 새로 열어야 PATH가 적용됩니다. Windows에서는 `python3` 대신 `python`(또는 `py`)을 쓰세요.

설치 위치: `~/.claude/skills/mkv-ko-subs/` (Windows: `%USERPROFILE%\.claude\skills\mkv-ko-subs\`). Claude Code를 새 세션으로 시작하면 스킬이 인식됩니다.

## 업데이트

```bash
cd mkv-ko-subs
git pull
./install.sh        # Windows: .\install.ps1
```

## 사용

Claude Code에서 "이 폴더 MKV 자막 한글화해줘" 처럼 요청하거나 `/mkv-ko-subs` 를 호출합니다.
스크립트를 직접 쓸 수도 있습니다: `python3 ~/.claude/skills/mkv-ko-subs/scripts/mkv_subs.py plan "영상.mkv"` (Windows는 `python`)
