# -*- coding: utf-8 -*-
"""v2 配音引擎：语义分句 + 首尾静音裁剪 + 可控停顿 + 多音字校正。

与 v1 的区别：v1 把整句一次性交给 TTS，句内停顿由模型自行决定，且每段 MP3 自带
首尾静音，拼接后出现忽长忽短的断裂感；v2 把每句切成语义呼吸组，逐组合成、裁掉静音，
再按标点插入固定时长的停顿，使旁白停顿自然、语义连贯。

多音字处理只对**送进 TTS 的文本**做同音替换，字幕/文稿/脚本仍保留正确汉字：
  「一行」→「一航」：航只有 háng 一个读音，从而保证读作 yì háng（代码行/行数），
                     而不是 yì xíng；这是本次要求的硬性校正项。
  「七行」→「七航」：网格行数 qī háng。
含混措辞「重设计 / 重算」已在文稿中改写为「重新做了 3D 设计 / 同步重新计算」，
从源头消除 chóng / zhòng 歧义。
"""
import asyncio
import re
import subprocess
import wave
from pathlib import Path

import edge_tts
import numpy as np

SR, CH, SW = 48000, 2, 2
VERSION = "v2-clause-pronunciation-1"

# 标点 -> 组间停顿（毫秒）。空串表示该镜头最后一组，不额外加停顿。
PAUSE_MS = {"，": 150, "、": 110, "：": 200, "；": 240,
            "。": 320, "！": 320, "？": 320, "": 0}
MAJOR = "。！？；"

# 仅作用于 TTS 输入的发音映射；(原文, 同音替换)
PRONUNCIATION_MAP = [
    ("一行", "一航"),   # yì háng，代码行／行数；避免 yì xíng
    ("七行", "七航"),   # qī háng，网格行数
]


def apply_pronunciation(text):
    out = text
    for src, dst in PRONUNCIATION_MAP:
        out = out.replace(src, dst)
    return out


def split_groups(text, min_len=26):
    """按标点切原子片段，再合并为约 20–35 字的语义呼吸组；
    遇句号/叹号/问号/分号立即成组，避免跨句连读造成断句生硬。"""
    atoms = [a for a in re.findall(r"[^，。；：！？、]*[，。；：！？、]?", text) if a]
    groups, buf = [], ""
    for a in atoms:
        buf += a
        last = a[-1] if a[-1] in PAUSE_MS else ""
        if last in MAJOR or len(buf) >= min_len:
            groups.append((buf, last))
            buf = ""
    if buf:
        last = buf[-1] if buf[-1] in PAUSE_MS else ""
        groups.append((buf, last))
    return groups


def decode(mp3, wav):
    subprocess.check_call(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
         "-ar", str(SR), "-ac", str(CH), "-c:a", "pcm_s16le", str(wav)])
    with wave.open(str(wav), "rb") as f:
        raw = f.readframes(f.getnframes())
    return np.frombuffer(raw, dtype=np.int16).reshape(-1, CH).copy()


def trim(arr, thresh=180, pad_ms=25):
    """裁掉 TTS 自带首尾静音，并在两端做 5ms 淡入淡出防爆音。"""
    amp = np.abs(arr).max(axis=1)
    idx = np.nonzero(amp > thresh)[0]
    if not len(idx):
        return arr[:0]
    a = max(0, int(idx[0]) - int(pad_ms * SR / 1000))
    b = min(len(arr), int(idx[-1]) + int(pad_ms * SR / 1000))
    seg = arr[a:b].copy()
    n = int(0.005 * SR)
    if len(seg) > 2 * n:
        seg[:n] = (seg[:n].astype(np.float32) *
                   np.linspace(0, 1, n)[:, None]).astype(np.int16)
        seg[-n:] = (seg[-n:].astype(np.float32) *
                    np.linspace(1, 0, n)[:, None]).astype(np.int16)
    return seg


def write_wav(path, arr):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(CH)
        f.setsampwidth(SW)
        f.setframerate(SR)
        f.writeframes(arr.astype(np.int16).tobytes())


async def _synth(text, path, voice, rate):
    for attempt in range(3):
        try:
            await edge_tts.Communicate(text, voice, rate=rate).save(str(path))
            if path.exists() and path.stat().st_size > 2000:
                return
        except Exception as exc:
            print("   retry", path.name, type(exc).__name__)
        await asyncio.sleep(0.7)
    raise RuntimeError("TTS failed: " + str(path))


def ffprobe_duration(p):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(p)], text=True).strip())


def generate_all(shots, d_seg, tmp):
    """返回每个镜头的实测配音时长（秒），并写出 逐段/Nxx.mp3。"""
    d_seg.mkdir(parents=True, exist_ok=True)
    ver = d_seg / "_version.txt"
    fresh = (not ver.exists()) or ver.read_text(encoding="utf-8").strip() != VERSION

    async def run():
        for sh in shots.SHOTS:
            n = sh["n"]
            groups = split_groups(shots.NARR[n])
            pieces = []
            for i, (g, punc) in enumerate(groups):
                mp3 = tmp / ("%s_%d.mp3" % (n, i))
                if fresh or not mp3.exists():
                    await _synth(apply_pronunciation(g), mp3, shots.VOICE, shots.RATE)
                arr = trim(decode(mp3, tmp / ("%s_%d.wav" % (n, i))))
                pieces.append((arr, punc))
            track = np.zeros((0, CH), dtype=np.int16)
            for arr, punc in pieces:
                track = np.vstack([track, arr])
                ms = PAUSE_MS.get(punc, 0)
                if ms:
                    track = np.vstack([track, np.zeros((int(SR * ms / 1000), CH),
                                                       dtype=np.int16)])
            wav = tmp / (n + "_joined.wav")
            write_wav(wav, track)
            out = d_seg / (n + ".mp3")
            subprocess.check_call(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                 "-c:a", "libmp3lame", "-q:a", "2", str(out)])
            print("  tts %-5s %2d groups  %5.2fs" %
                  (n, len(groups), ffprobe_duration(out)))

    asyncio.run(run())
    ver.write_text(VERSION, encoding="utf-8")
    return [ffprobe_duration(d_seg / (s["n"] + ".mp3")) for s in shots.SHOTS]


def generate_comparison(outdir, voice="zh-CN-YunyangNeural"):
    """「一行」校正前后试听对比，供人工核验 yì háng 读音。"""
    outdir.mkdir(parents=True, exist_ok=True)
    phrase = "渲染层一行不用改"

    async def run():
        await _synth(phrase, outdir / "一行-未校正-YiXing.mp3", voice, "+0%")
        await _synth(apply_pronunciation(phrase),
                     outdir / "一行-已校正-YiHang.mp3", voice, "+0%")
    asyncio.run(run())
    return outdir
