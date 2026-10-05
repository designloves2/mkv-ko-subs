#!/usr/bin/env python3
"""MKV 자막 한글화 도구 (mkvtoolnix + ffmpeg 필요). 규칙은 ../SKILL.md 참고.

  plan    <mkv>                       상황 판정만 출력 (파일을 만들지 않음)
  prepare <mkv> [--work DIR]          영어 자막(원본 타입)·한글 SRT 파일을 영상 옆에 만들고, 번역이 필요하면 작업용 시트 생성
  dump    <worksheet.srt>             작업용 시트를 `번호|텍스트` 로 출력 (번역할 때 읽는 용도)
  build   <mkv> --trans FILE [--work DIR]   번역 파일로 <영상>.kor.srt 생성
  mux     <mkv> [--outdir done]       영상의 모든 자막을 지우고 1.한글(SRT) 2.영어(원본 타입) 순서로 넣어 done에 저장
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile

SUB_EXTS = (".srt", ".ass", ".ssa", ".smi", ".sami", ".vtt")
EN_TAGS = {"eng", "en", "english", "enus", "en-us"}
KO_TAGS = {"kor", "ko", "korean", "kr", "kor-kr", "한국어", "한글"}
CODEC_EXT = {"S_TEXT/ASS": ".ass", "S_TEXT/SSA": ".ssa", "S_TEXT/UTF8": ".srt", "S_TEXT/WEBVTT": ".vtt"}
DEFAULT_WORK = os.path.join(tempfile.gettempdir(), "mkv-ko-subs")


def die(msg, code=2):
    print(msg)
    sys.exit(code)


def run(cmd, ok=(0,)):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode not in ok:
        die(f"실패: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r


def base_of(mkv):
    return os.path.splitext(os.path.basename(mkv))[0]


def dir_of(mkv):
    return os.path.dirname(os.path.abspath(mkv))


# ---------- 텍스트 읽기/변환 ----------
def read_text(path):
    raw = open(path, "rb").read()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for enc in ("utf-8", "cp949", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def detect_lang_by_content(path):
    t = read_text(path)
    if path.lower().endswith((".ass", ".ssa")):
        t = "\n".join(ln.split(",", 9)[9] for ln in t.split("\n") if ln.startswith("Dialogue:") and ln.count(",") >= 9)
    t = re.sub(r"<[^>]+>|\{[^}]*\}|&nbsp;", " ", t)
    ko = len(re.findall(r"[\uac00-\ud7a3]", t))
    en = len(re.findall(r"[A-Za-z]", t))
    if ko + en < 50:
        return None
    ratio = ko / (ko + en)
    if ratio > 0.3:
        return "ko"
    if ratio < 0.05:
        return "en"
    return None


SRT_CUE = re.compile(
    r"(?:^|\n)(\d+)[ \t]*\n(\d\d:\d\d:\d\d[,.]\d{1,3}) --> (\d\d:\d\d:\d\d[,.]\d{1,3})[^\n]*\n(.*?)(?=\n\n+\d+[ \t]*\n\d\d:\d\d:\d\d[,.]\d|\Z)",
    re.S)


def clean_text(t):
    t = re.sub(r"</?font[^>]*>", "", t)
    t = re.sub(r"\{\\[^}]*\}", "", t)
    lines = [ln.strip() for ln in t.replace("\r", "").split("\n") if ln.strip()]
    return "\n".join(lines)


def parse_srt(text, clean=True):
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip() + "\n"
    cues = []
    for m in SRT_CUE.finditer(text):
        body = clean_text(m.group(4)) if clean else m.group(4).strip()
        if not body or re.match(r"^m -?\d+ -?\d+ l ", body):  # 빈 큐, ASS 그리기 명령
            continue
        cues.append((int(m.group(1)), m.group(2).replace(".", ","), m.group(3).replace(".", ","), body))
    return cues


def write_srt(path, cues, renumber=True):
    out = []
    for i, (n, s, e, t) in enumerate(cues, 1):
        out.append(f"{i if renumber else n}\n{s} --> {e}\n{t}")
    open(path, "w", encoding="utf-8").write("\n\n".join(out) + "\n")


def sub_to_srt_cues(path):
    """ASS/SSA/SMI/VTT/SRT → 큐 목록(번호는 변환 결과 번호 유지, 태그 정리)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".srt":
        return parse_srt(read_text(path))
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in" + ext)
        open(src, "w", encoding="utf-8").write(read_text(path))
        dst = os.path.join(d, "out.srt")
        subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-i", src, dst], capture_output=True, text=True)
        if not os.path.exists(dst):
            die(f"자막 변환 실패: {path}")
        return parse_srt(open(dst, encoding="utf-8").read())


# ---------- 상황 판정 ----------
def mkv_info(mkv):
    return json.loads(run(["mkvmerge", "-J", mkv], ok=(0, 1)).stdout)


def internal_subs(mkv):
    out = []
    for t in mkv_info(mkv)["tracks"]:
        if t["type"] != "subtitles":
            continue
        p = t["properties"]
        lang = (p.get("language") or "und").lower()
        name = (p.get("track_name") or "")
        if lang in EN_TAGS or "english" in name.lower():
            l = "en"
        elif lang in KO_TAGS or "한국어" in name or "korean" in name.lower():
            l = "ko"
        else:
            l = None
        out.append({"id": t["id"], "codec_id": p.get("codec_id"), "lang": l, "raw_lang": lang, "name": name})
    return out


def external_subs(mkv, subs_dir=None):
    d = subs_dir or dir_of(mkv)
    base = base_of(mkv)
    found = []
    for f in sorted(os.listdir(d)):
        if not f.startswith(base) or f.lower().endswith(".mkv"):
            continue
        rest = f[len(base):]
        m = re.match(r"^(?:\.([^.]+))?(\.[A-Za-z0-9]+)$", rest)
        if not m or m.group(2).lower() not in SUB_EXTS:
            continue
        tag = (m.group(1) or "").lower()
        path = os.path.join(d, f)
        lang = "en" if tag in EN_TAGS else "ko" if tag in KO_TAGS else detect_lang_by_content(path)
        found.append({"path": path, "ext": m.group(2).lower(), "tag": tag, "lang": lang})
    return found


def make_plan(mkv, subs_dir=None):
    if not mkv.lower().endswith(".mkv") or not os.path.exists(mkv):
        die("MKV 파일이 아니거나 없습니다 (다운로드 미완료 .fdmdownload 파일은 처리하지 않습니다).")
    ints = internal_subs(mkv)
    exts = external_subs(mkv, subs_dir)
    ask = []
    unknown_i = [t for t in ints if t["lang"] is None]
    unknown_e = [e for e in exts if e["lang"] is None]
    if unknown_i:
        ask.append(f"언어를 알 수 없는 내장 자막 트랙: {[(t['id'], t['raw_lang'], t['name']) for t in unknown_i]}")
    if unknown_e:
        ask.append(f"언어를 알 수 없는 외부 자막: {[os.path.basename(e['path']) for e in unknown_e]}")
    i_en = [t for t in ints if t["lang"] == "en"]
    i_ko = [t for t in ints if t["lang"] == "ko"]
    e_en = [e for e in exts if e["lang"] == "en"]
    e_ko = [e for e in exts if e["lang"] == "ko"]
    # prepare 가 만든 표준 이름 파일(<영상>.kor.srt, <영상>.eng.<타입>)은 원본 외부 자막에서 파생된 것이므로,
    # 다른 후보가 함께 있으면 후보에서 제외한다. (표준 이름 파일만 있으면 그 파일이 외부 자막)
    if len(e_ko) > 1:
        e_ko = [e for e in e_ko if os.path.abspath(e["path"]) != os.path.abspath(kor_path(mkv))]
    if len(e_en) > 1:
        e_en = [e for e in e_en if os.path.basename(e["path"]) != base_of(mkv) + ".eng" + e["ext"]]
    if len(i_en) > 1:
        ask.append(f"내장 영어 자막 트랙이 여러 개: {[t['id'] for t in i_en]}")
    if len(e_ko) > 1:
        ask.append(f"외부 한글 자막이 여러 개: {[os.path.basename(e['path']) for e in e_ko]}")
    if not i_en and len(e_en) > 1:
        ask.append(f"외부 영어 자막이 여러 개: {[os.path.basename(e['path']) for e in e_en]}")
    if i_ko and not e_ko:
        ask.append("내장 한글 자막이 있는데 외부 한글 자막은 없음 (규칙에 정의되지 않은 상황)")
    for t in i_en:
        if t["codec_id"] not in CODEC_EXT:
            ask.append(f"내장 영어 자막 트랙 {t['id']} 가 텍스트 자막이 아님({t['codec_id']})")
    plan = {"mkv": mkv, "internal": ints, "external": exts, "ask": ask,
            "eng_src": None, "kor_src": None, "translate": False, "scenario": None}
    if ask:
        plan["scenario"] = "질문 필요"
        return plan
    if i_en:
        plan["eng_src"] = ("internal", i_en[0])
    elif e_en:
        plan["eng_src"] = ("external", e_en[0])
    if e_ko:
        plan["kor_src"] = e_ko[0]
        plan["scenario"] = ("S3 외부 한글 + 내장 영어" if i_en else
                            "S4 외부 한글 + 외부 영어" if e_en else
                            "S5 외부 한글만 (영어 자막 없음 → 한글 1개만 삽입)")
    elif plan["eng_src"]:
        plan["translate"] = True
        plan["scenario"] = "S1 내장 영어 → 번역" if i_en else "S2 외부 영어 → 번역"
    else:
        plan["scenario"] = "질문 필요"
        plan["ask"].append("영어 자막도 한글 자막도 없음")
    return plan


def print_plan(p):
    print(f"영상: {os.path.basename(p['mkv'])}")
    print("내장 자막:", [(t["id"], t["codec_id"], t["raw_lang"], t["name"], t["lang"]) for t in p["internal"]] or "없음")
    print("외부 자막:", [(os.path.basename(e["path"]), e["lang"]) for e in p["external"]] or "없음")
    print("판정:", p["scenario"])
    for a in p["ask"]:
        print("질문 필요:", a)
    if p["eng_src"]:
        k, s = p["eng_src"]
        print("영어 출처:", "내장 트랙 %d" % s["id"] if k == "internal" else os.path.basename(s["path"]))
    if p["kor_src"]:
        print("한글 출처: 외부", os.path.basename(p["kor_src"]["path"]))
    print("번역 필요:", "예" if p["translate"] else "아니오")


# ---------- 단계 실행 ----------
def eng_path(mkv, ext):
    return os.path.join(dir_of(mkv), base_of(mkv) + ".eng" + ext)


def kor_path(mkv):
    return os.path.join(dir_of(mkv), base_of(mkv) + ".kor.srt")


def work_sheet(mkv, work):
    return os.path.join(work, base_of(mkv) + ".work.srt")


def prepare(mkv, work, subs_dir=None):
    p = make_plan(mkv, subs_dir)
    print_plan(p)
    if p["ask"]:
        die("→ 위 항목을 사용자에게 물어본 뒤 진행하세요. 임의로 판단하지 마세요.", 3)
    os.makedirs(work, exist_ok=True)
    eng_file = None
    if p["eng_src"]:
        kind, s = p["eng_src"]
        if kind == "internal":
            ext = CODEC_EXT[s["codec_id"]]
            eng_file = eng_path(mkv, ext)
            if os.path.exists(eng_file):
                print("이미 있음(재사용):", eng_file)
            else:
                run(["mkvextract", mkv, "tracks", f"{s['id']}:{eng_file}"], ok=(0, 1))
                print("영어 자막 저장:", eng_file)
        else:
            eng_file = eng_path(mkv, s["ext"])
            if os.path.abspath(s["path"]) != os.path.abspath(eng_file):
                shutil.copyfile(s["path"], eng_file)
                print("영어 자막 저장(외부 파일 복사):", eng_file)
    if p["kor_src"]:
        src = p["kor_src"]["path"]
        dst = kor_path(mkv)
        if os.path.splitext(src)[1].lower() == ".srt":
            if os.path.abspath(src) != os.path.abspath(dst):
                t = read_text(src).replace("\r\n", "\n").replace("\r", "\n")
                open(dst, "w", encoding="utf-8").write(t)
                print("한글 SRT 저장(UTF-8 변환):", dst)
        else:
            write_srt(dst, sub_to_srt_cues(src))
            print("한글 자막을 SRT로 변환 저장:", dst)
    if p["translate"]:
        cues = sub_to_srt_cues(eng_file)
        ws = work_sheet(mkv, work)
        write_srt(ws, cues, renumber=False)
        print(f"번역용 시트: {ws} ({len(cues)}큐) → `dump` 로 읽고 `번호|번역` 파일을 작성한 뒤 `build`")
    else:
        print("번역 없음 → 바로 mux")


def dump(ws):
    for n, s, e, t in parse_srt(open(ws, encoding="utf-8").read()):
        print(f"{n}|{t.replace(chr(10), ' / ')}")


def build(mkv, trans, work):
    ws = work_sheet(mkv, work)
    if not os.path.exists(ws):
        die(f"번역용 시트가 없습니다: {ws} (prepare 먼저)")
    cues = parse_srt(open(ws, encoding="utf-8").read())
    tr = {}
    for ln in open(trans, encoding="utf-8").read().split("\n"):
        if "|" in ln:
            n, t = ln.split("|", 1)
            if n.strip().isdigit():
                tr[int(n)] = t.replace(" / ", "\n")
    nums = {c[0] for c in cues}
    extra = [n for n in tr if n not in nums]
    if extra:
        die(f"번역 파일에 시트에 없는 번호가 있습니다: {extra[:10]}")
    out, kept = [], []
    for n, s, e, t in cues:
        if n in tr:
            out.append((n, s, e, tr[n]))
        else:
            kept.append(n)
            out.append((n, s, e, t))
    write_srt(kor_path(mkv), out)
    print(f"저장: {kor_path(mkv)} (총 {len(cues)}큐, 번역 {len(cues) - len(kept)}, 영어 원문 유지 {len(kept)})")
    if kept:
        print("영어 원문 유지 번호:", kept[:60], "..." if len(kept) > 60 else "")


def mux(mkv, outdir, subs_dir=None):
    p = make_plan(mkv, subs_dir)
    if p["ask"]:
        print_plan(p)
        die("→ 위 항목을 사용자에게 물어본 뒤 진행하세요. 임의로 판단하지 마세요.", 3)
    kor = kor_path(mkv)
    if not os.path.exists(kor):
        die(f"한글 SRT가 없습니다: {kor}")
    eng = None
    if p["eng_src"]:
        kind, s = p["eng_src"]
        ext = CODEC_EXT[s["codec_id"]] if kind == "internal" else s["ext"]
        eng = eng_path(mkv, ext)
        if not os.path.exists(eng):
            die(f"영어 자막 파일이 없습니다: {eng} (prepare 먼저)")
    out_dir = outdir if os.path.isabs(outdir) else os.path.join(dir_of(mkv), outdir)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, os.path.basename(mkv))
    eng_mux = eng
    if eng and os.path.splitext(eng)[1].lower() in (".smi", ".sami", ".vtt"):  # MKV 에 직접 못 넣는 형식은 멕싱용으로만 SRT 변환
        tmp_conv = os.path.join(tempfile.mkdtemp(), "eng.srt")
        write_srt(tmp_conv, sub_to_srt_cues(eng))
        eng_mux = tmp_conv
        print("참고: 영어 자막이", os.path.splitext(eng)[1], "형식이라 멕싱용으로만 SRT 로 변환 (저장된 원본 파일은 그대로)")
    keep = [t["id"] for t in mkv_info(mkv)["tracks"] if t["type"] != "subtitles"]
    cmd = ["mkvmerge", "-o", out, "-S", mkv,
           "--language", "0:kor", "--track-name", "0:한국어", "--default-track-flag", "0:yes", kor]
    order = [f"0:{i}" for i in keep] + ["1:0"]
    if eng_mux:
        cmd += ["--language", "0:eng", "--track-name", "0:English", "--default-track-flag", "0:no", eng_mux]
        order.append("2:0")
    cmd += ["--track-order", ",".join(order)]
    run(cmd, ok=(0, 1))
    subs = [(t["properties"].get("language"), t["properties"].get("track_name"), t["codec"],
             "기본" if t["properties"].get("default_track") else "-")
            for t in mkv_info(out)["tracks"] if t["type"] == "subtitles"]
    expect = 2 if eng else 1
    print("저장:", out)
    print("결과 자막 트랙:", subs)
    if len(subs) != expect:
        die(f"자막 트랙 수가 예상({expect})과 다릅니다!", 4)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="c", required=True)
    for name in ("plan", "prepare", "build", "mux"):
        s = sp.add_parser(name)
        s.add_argument("mkv")
        s.add_argument("--subs-dir")
        if name in ("prepare", "build"):
            s.add_argument("--work", default=DEFAULT_WORK)
        if name == "build":
            s.add_argument("--trans", required=True)
        if name == "mux":
            s.add_argument("--outdir", default="done")
    d = sp.add_parser("dump")
    d.add_argument("worksheet")
    a = ap.parse_args()
    if a.c == "plan":
        print_plan(make_plan(a.mkv, a.subs_dir))
    elif a.c == "prepare":
        prepare(a.mkv, a.work, a.subs_dir)
    elif a.c == "dump":
        dump(a.worksheet)
    elif a.c == "build":
        build(a.mkv, a.trans, a.work)
    elif a.c == "mux":
        mux(a.mkv, a.outdir, a.subs_dir)


if __name__ == "__main__":
    main()
