# -*- coding: utf-8 -*-
"""由 shots.py + 推广文稿生成配音、字幕、三份脚本文档与最终 MP4 成片。

用法：
  python build_video.py tts     # 配音 + 时间轴 + 字幕 + 脚本文档
  python build_video.py video   # 片段预渲染 + 转场合成 + 音画混流
  python build_video.py all     # 全部
"""
import asyncio
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import edge_tts

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import shots  # noqa: E402

ROOT = HERE.parent
REPO = ROOT.parent
D_VOICE = ROOT / "03_配音"
D_SEG = D_VOICE / "逐段"
D_SUB = ROOT / "04_字幕"
D_DOC = ROOT / "02_脚本"
D_STILL = ROOT / "05_画面素材" / "静帧"
D_CLIP = ROOT / "05_画面素材" / "动态"
D_OUT = ROOT / "06_成片"
TMP = Path(tempfile.mkdtemp(prefix="cf-build-"))
OUT_MP4 = D_OUT / "耕年-立体年鉴-推广片.mp4"
TIMELINE_JSON = HERE / "timeline.json"

for d in (D_SEG, D_SUB, D_DOC, D_OUT):
    d.mkdir(parents=True, exist_ok=True)


def ffprobe_duration(p):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(p)], text=True)
    return float(out.strip())


def ffmpeg(*args):
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", *map(str, args)])


# ───────────────────────── 配音 ─────────────────────────
def gen_tts():
    async def run():
        for sh in shots.SHOTS:
            out = D_SEG / (sh["n"] + ".mp3")
            if out.exists() and out.stat().st_size > 2000:
                continue
            txt = shots.NARR[sh["n"]]
            await edge_tts.Communicate(txt, shots.VOICE, rate=shots.RATE).save(str(out))
            print("  tts", sh["n"], out.stat().st_size, "bytes")
    asyncio.run(run())
    return [ffprobe_duration(D_SEG / (s["n"] + ".mp3")) for s in shots.SHOTS]


def build_timeline(vo_durs):
    items = []
    start = 0.0
    for i, sh in enumerate(shots.SHOTS):
        dur = sh["lead"] + vo_durs[i] + sh["tail"]
        items.append(dict(
            id=sh["id"], n=sh["n"], asset=sh["asset"], chapter=sh["chapter"],
            start=round(start, 3), dur=round(dur, 3),
            lead=sh["lead"], tail=sh["tail"],
            vo_start=round(start + sh["lead"], 3),
            vo_end=round(start + sh["lead"] + vo_durs[i], 3),
            vo_dur=round(vo_durs[i], 3),
            trans=sh["trans"] if i < len(shots.SHOTS) - 1 else "",
            tdur=sh["tdur"] if i < len(shots.SHOTS) - 1 else 0.0,
            badge=sh["badge"], text=shots.NARR[sh["n"]],
        ))
        start = start + dur - (sh["tdur"] if i < len(shots.SHOTS) - 1 else 0)
    total = round(items[-1]["start"] + items[-1]["dur"], 3)
    return items, total


def build_audio(items, total):
    """按最终时间轴把逐段配音放到精确位置，生成全片配音音轨。"""
    sr, ch, sw = 48000, 2, 2
    wavs = []
    for it in items:
        w = TMP / (it["n"] + ".wav")
        ffmpeg("-i", D_SEG / (it["n"] + ".mp3"), "-ar", sr, "-ac", ch,
               "-c:a", "pcm_s16le", w)
        with wave.open(str(w), "rb") as f:
            wavs.append(f.readframes(f.getnframes()))
    frame_sz = ch * sw
    total_frames = int(round(total * sr))
    buf = bytearray(total_frames * frame_sz)
    for it, data in zip(items, wavs):
        pos = int(round(it["vo_start"] * sr)) * frame_sz
        end = min(len(buf), pos + len(data))
        buf[pos:end] = data[:end - pos]
    full_wav = TMP / "voice_full.wav"
    with wave.open(str(full_wav), "wb") as f:
        f.setnchannels(ch); f.setsampwidth(sw); f.setframerate(sr)
        f.writeframes(bytes(buf))
    ffmpeg("-i", full_wav, "-c:a", "libmp3lame", "-q:a", "2",
           D_VOICE / "配音-全片-男声.mp3")
    return full_wav


# ───────────────────────── 字幕 ─────────────────────────
def wrap_text(t, width=30):
    """按中文长度折行，最多两行；折行不改变文字内容。"""
    if len(t) <= width:
        return [t]
    cut = -1
    for j in range(width - 8, min(len(t), width + 9)):
        if t[j] in "，。；：、！？ ":
            cut = j + 1
    if cut < 0:
        cut = width
    lines = [t[:cut].strip(), t[cut:].strip()]
    if len(lines[1]) > width + 6:
        # 三行兜底，避免文字出屏
        a, b = lines[0], lines[1]
        k = len(b) // 2
        lines = [a, b[:k], b[k:]]
    return [x for x in lines if x]


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def vtt_time(t):
    return srt_time(t).replace(",", ".")


def ass_time(t):
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def gen_subtitles(items, total):
    # SRT / VTT：仅旁白字幕，与配音逐字一致
    srt, vtt = [], ["WEBVTT", ""]
    for i, it in enumerate(items, 1):
        body = "\n".join(wrap_text(it["text"]))
        srt.append("%d\n%s --> %s\n%s\n" % (i, srt_time(it["vo_start"]),
                                            srt_time(it["vo_end"]), body))
        vtt.append("%d\n%s --> %s\n%s\n" % (i, vtt_time(it["vo_start"]),
                                            vtt_time(it["vo_end"]), body))
    (D_SUB / "字幕-中文.srt").write_text("\n".join(srt), encoding="utf-8")
    (D_SUB / "字幕-中文.vtt").write_text("\n".join(vtt), encoding="utf-8")

    # ASS：旁白 + 数据角标 + 章节标题 + 片尾卡，用于烧录
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1600
PlayResY: 900
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Microsoft YaHei,38,&H00FFFFFF,&H000000FF,&H80202818,&H00000000,-1,0,0,0,100,100,0,0,3,8,0,2,70,70,50,1
Style: Badge,Microsoft YaHei,25,&H00232820,&H000000FF,&H00F1F6F7,&H80000000,0,0,0,0,100,100,0,0,3,7,0,9,40,40,46,1
Style: Chapter,Microsoft YaHei,34,&H00232820,&H000000FF,&H00F1F6F7,&H80000000,-1,0,0,0,100,100,0,0,3,9,0,7,40,40,46,1
Style: End,Microsoft YaHei,30,&H00232820,&H000000FF,&H00F1F6F7,&H80000000,-1,0,0,0,100,100,0,0,3,12,0,5,60,60,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for it in items:
        sub = "\\N".join(wrap_text(it["text"]))
        ev.append("Dialogue: 0,%s,%s,Sub,,0,0,0,,%s" %
                  (ass_time(it["vo_start"]), ass_time(it["vo_end"]), sub))
        if it["badge"]:
            bs = it["start"] + 0.55
            be = it["start"] + it["dur"] - 0.35
            ev.append("Dialogue: 0,%s,%s,Badge,,0,0,0,,{\\fad(300,300)}%s" %
                      (ass_time(bs), ass_time(be), it["badge"]))
    for label, sid in shots.CHAPTERS:
        it = next(x for x in items if x["id"] == sid)
        ev.append("Dialogue: 0,%s,%s,Chapter,,0,0,0,,{\\fad(350,350)}%s" %
                  (ass_time(it["start"] + 0.1), ass_time(it["start"] + 3.6), label))
    last = items[-1]
    es = last["vo_end"] + 0.35
    ee = total - 0.15
    endtxt = "\\N".join(shots.END_CARD)
    ev.append("Dialogue: 0,%s,%s,End,,0,0,0,,{\\fad(500,500)}%s" %
              (ass_time(es), ass_time(ee), endtxt))
    (D_SUB / "字幕-烧录.ass").write_text(head + "\n".join(ev) + "\n", encoding="utf-8")


# ───────────────────────── 脚本文档 ─────────────────────────
def tc(t):
    m, s = divmod(t, 60)
    return "%02d:%04.1f" % (int(m), s)


def gen_docs(items, total):
    def chapter_of(sid):
        for label, first in shots.CHAPTERS:
            if sid == first:
                return label
        return ""

    # 视频脚本
    L = ["# 《耕年 · 立体年鉴》推广片 · 视频脚本", "",
         "- 成片规格：%d×%d / %d fps / H.264 + AAC" % (shots.W, shots.H, shots.FPS),
         "- 片长：**%s（%.1f 秒）**" % (tc(total), total),
         "- 配音：`zh-CN-YunyangNeural` 男声、正常语速（rate +0%），沉稳播报",
         "- 字幕：中文，逐字取自配音文稿；片尾另含来源与模型标识说明",
         "- 画面：全部为本项目真实运行的截图与录屏（含裁切排版），未使用素材库画面",
         "- 时间码为**成片实测时间轴**，已计入转场重叠；配音起点 = 字幕起点", "",
         "> 转场列表示「本镜头 → 下一镜头」的类型与时长。", ""]
    prev = None
    for i, it in enumerate(items):
        ch = chapter_of(it["id"])
        if ch:
            L += ["---", "", "## %s" % ch, ""]
        L += ["### %s · %s ｜ %s → %s（%.1f 秒）" %
              (it["id"], it["n"], tc(it["start"]), tc(it["start"] + it["dur"]), it["dur"]), "",
              "| 项 | 内容 |", "| --- | --- |",
              "| 旁白 | %s |" % it["text"],
              "| 画面 | %s |" % next(s for s in shots.SHOTS if s["id"] == it["id"])["visual"],
              "| 配音 | %s → %s（%.1f 秒） |" % (tc(it["vo_start"]), tc(it["vo_end"]), it["vo_dur"]),
              "| 字幕 | 与旁白逐字一致，%s → %s |" % (tc(it["vo_start"]), tc(it["vo_end"])),
              "| 上屏补充 | %s |" % (it["badge"] or "—"),
              "| 转场 | %s（%.2f 秒）→ %s |" %
              (it["trans"] or "—", it["tdur"], items[i + 1]["id"] if i + 1 < len(items) else "片尾"),
              ""]
    (D_DOC / "视频脚本.md").write_text("\n".join(L), encoding="utf-8")

    # 分镜表
    M = ["# 《耕年 · 立体年鉴》推广片 · 分镜表", "",
         "共 %d 个镜头，总时长 %.1f 秒；时间码与成片、SRT 字幕严格一致。" % (len(items), total), "",
         "| 镜号 | 时间码 | 时长 | 镜头内容（素材） | 画面重点 | 字幕 | 转场 |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    for i, it in enumerate(items):
        sh = next(s for s in shots.SHOTS if s["id"] == it["id"])
        sub = " / ".join(wrap_text(it["text"])).replace("|", "\\|")
        M.append("| %s | %s–%s | %.1fs | %s<br>`%s` | %s | %s | %s %.2fs |" %
                 (it["id"], tc(it["start"]), tc(it["start"] + it["dur"]), it["dur"],
                  sh["visual"], it["asset"], sh["focus"], sub,
                  it["trans"] or "—", it["tdur"]))
    M += ["", "说明：字幕栏中的 `/` 表示折行，文字内容与配音完全相同；`<br>` 仅为表格排版。", ""]
    (D_DOC / "分镜表.md").write_text("\n".join(M), encoding="utf-8")

    # 转场说明
    T = ["# 《耕年 · 立体年鉴》推广片 · 转场说明", "",
         "## 设计原则", "",
         "1. **纸白闪切（fadewhite）用于章节边界**：作品本身以 `#f7f6f1` 纸白为底色，转场瞬间的白场与页面配色同源，不引入外来视觉语言。",
         "2. **横向推移（smoothleft）用于时间与形态的枚举**：呼应 53 列时间轴从左到右的推进，镜头之间读起来像沿田垄往前走。",
         "3. **溶解（dissolve / fade）用于同一状态的细部切换**：避免频繁硬切打断旁白。",
         "4. **转场时长服从节奏**：章节边界 0.9 秒慢转，演示密集段 0.40 秒快切，收尾 0.55 秒放缓；所有转场都落在**配音结束之后**（配音后留白 ≥ 转场时长 + 0.15 秒），因此不会出现字幕压在转场白场上的情况。",
         "5. 成片时间轴已扣除转场重叠：`下一镜头起点 = 上一镜头起点 + 上一镜头时长 − 转场时长`，脚本与分镜表的时间码即按此计算。", "",
         "## 逐处转场", "",
         "| 边界 | 起点 | 类型 | 时长 | 叙事作用 |", "| --- | --- | --- | --- | --- |"]
    reasons = {
        "fadewhite": "章节收束，回到纸白再开新章",
        "smoothleft": "沿时间轴或形态序列向前推进",
        "dissolve": "同一状态内的细部过渡，保持旁白连贯",
        "fade": "常规换镜，不抢画面重点",
    }
    for i, it in enumerate(items[:-1]):
        nxt = items[i + 1]
        T.append("| %s → %s | %s | `%s` | %.2fs | %s |" %
                 (it["id"], nxt["id"], tc(it["start"] + it["dur"] - it["tdur"]),
                  it["trans"], it["tdur"], reasons[it["trans"]]))
    T += ["", "## 节奏曲线", "",
          "- 序章（%s）：4 镜，慢起，先给效果再给全貌。" % chapter_of("S01"),
          "- 创作过程（5 镜）：以溶解为主，讲取舍与两次真实数据暴露的问题。",
          "- 项目成果（13 镜）：节奏最快，0.40 秒横推串联视角、形态与功能，中段插入 4 段实拍录屏。",
          "- 使用体验（4 镜）：降速，0.50–0.90 秒转场，末尾 6 秒留给片尾信息卡。", ""]
    (D_DOC / "转场说明.md").write_text("\n".join(T), encoding="utf-8")

    TIMELINE_JSON.write_text(json.dumps(dict(total=total, shots=items),
                                        ensure_ascii=False, indent=2), encoding="utf-8")


# ───────────────────────── 成片 ─────────────────────────
def render_segments(items):
    segdir = TMP / "segments"
    segdir.mkdir(exist_ok=True)
    paths = []
    for i, it in enumerate(items):
        out = segdir / ("%02d.mp4" % i)
        src = (D_CLIP if it["asset"].endswith(".mp4") else D_STILL) / it["asset"]
        assert src.exists(), src
        vf = ("fps=%d,scale=%d:%d:force_original_aspect_ratio=increase,"
              "crop=%d:%d,setsar=1,format=yuv420p" %
              (shots.FPS, shots.W, shots.H, shots.W, shots.H))
        if it["asset"].endswith(".mp4"):
            ffmpeg("-stream_loop", "-1", "-i", src, "-t", it["dur"],
                   "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
                   "-crf", "20", "-r", shots.FPS, out)
        else:
            ffmpeg("-loop", "1", "-framerate", shots.FPS, "-t", it["dur"], "-i", src,
                   "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
                   "-crf", "20", "-r", shots.FPS, out)
        paths.append(out)
        print("  segment %s %.1fs" % (it["id"], it["dur"]))
    return paths


def assemble(items, total, segs, voice_wav):
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for p in segs:
        cmd += ["-i", str(p)]
    cmd += ["-i", str(voice_wav)]
    n = len(segs)
    parts = []
    for i in range(n):
        parts.append("[%d:v]settb=AVTB,fps=%d,format=yuv420p[v%d]" % (i, shots.FPS, i))
    cur = "v0"
    for i in range(n - 1):
        it = items[i]
        nxt = "x%d" % i
        offset = round(items[i + 1]["start"], 3)
        parts.append("[%s][v%d]xfade=transition=%s:duration=%.2f:offset=%.3f[%s]" %
                     (cur, i + 1, it["trans"], it["tdur"], offset, nxt))
        cur = nxt
    parts.append("[%s]ass=04_字幕/字幕-烧录.ass[vout]" % cur)
    cmd += ["-filter_complex", ";".join(parts),
            "-map", "[vout]", "-map", "%d:a" % n,
            "-c:v", "libx264", "-preset", "medium", "-crf", "21",
            "-pix_fmt", "yuv420p", "-r", str(shots.FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-t", "%.3f" % total, "-movflags", "+faststart", str(OUT_MP4)]
    # 在 video/ 目录下使用相对 ASS 路径，避免 Windows 盘符冒号被滤镜解析
    subprocess.check_call(list(map(str, cmd)), cwd=str(ROOT))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    vo = gen_tts()
    items, total = build_timeline(vo)
    print("total duration %.2fs = %.2f min" % (total, total / 60))
    assert 180 <= total <= 300, "片长必须落在 3–5 分钟"
    voice_wav = build_audio(items, total)
    gen_subtitles(items, total)
    gen_docs(items, total)
    print("  tts / subtitles / docs done")
    if mode in ("video", "all"):
        segs = render_segments(items)
        assemble(items, total, segs, voice_wav)
        print("  final", OUT_MP4, OUT_MP4.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
