# -*- coding: utf-8 -*-
"""从真实运行的 HTML 页面采集推广片全部画面素材。

- 静帧：无头 Edge CDP 全页截图 -> 按镜头裁切/缩放 -> 1600x900 JPEG
- 动态：按 10 fps 连续截取视口 -> ffmpeg 编码为 MP4
所有画面均来自项目实际运行，未使用素材库图片或 AI 生成画面。
"""
import base64
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import shots  # noqa: E402

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PAGE3D = shots.VIDEO_SRC
PAGE2D = shots.VIDEO_SRC_2D
OUT_STILL = ROOT / "05_画面素材" / "静帧"
OUT_CLIP = ROOT / "05_画面素材" / "动态"
RAW = Path(tempfile.mkdtemp(prefix="cf-frames-"))
FONT = r"C:\Windows\Fonts\msyh.ttc"
W, H = shots.W, shots.H
CLIP_FPS = 10

OUT_STILL.mkdir(parents=True, exist_ok=True)
OUT_CLIP.mkdir(parents=True, exist_ok=True)

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
s = socket.socket()
s.bind(("127.0.0.1", 0))
PORT = s.getsockname()[1]
s.close()
profile = tempfile.mkdtemp(prefix="cf-edge-")
proc = subprocess.Popen(
    [EDGE, "--headless=new", "--disable-gpu", "--no-proxy-server", "--no-first-run",
     "--user-data-dir=" + profile, "--remote-debugging-port=%d" % PORT,
     "--window-size=%d,%d" % (W, H), "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def send(method, params=None):
    global _mid
    _mid += 1
    mid = _mid
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == mid:
            if "error" in r:
                raise RuntimeError("%s: %s" % (method, r["error"]))
            return r.get("result", {})


def ev(expr):
    r = send("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                 "awaitPromise": True})
    if "exceptionDetails" in r:
        raise RuntimeError("JS: %s" % str(r["exceptionDetails"])[:300])
    return r.get("result", {}).get("value")


def screenshot(path, beyond=False):
    p = {"format": "png"}
    if beyond:
        p["captureBeyondViewport"] = True
    r = send("Page.captureScreenshot", p)
    path.write_bytes(base64.b64decode(r["data"]))


def rect(sel):
    return ev("""(function(){var e=document.querySelector(%s);if(!e)return null;
      var r=e.getBoundingClientRect();return {x:r.left+scrollX,y:r.top+scrollY,
      w:r.width,h:r.height}})()""" % json.dumps(sel))


def wait_ready(tag=""):
    for _ in range(80):
        try:
            if ev("document.readyState==='complete' && document.querySelectorAll('.stat').length>=5"):
                break
        except Exception:
            pass
        time.sleep(0.2)
    time.sleep(1.4)
    print("  ready", tag)


def nav(url):
    # 每个镜头组都从默认账号状态开始，避免上一次自定义账号的缓存串场
    try:
        ev("try{localStorage.removeItem('cf_account_state')}catch(e){}")
    except Exception:
        pass
    send("Page.navigate", {"url": "about:blank"})
    time.sleep(0.25)
    send("Page.navigate", {"url": url})
    wait_ready(Path(url).name)


def pause_cruise():
    if ev("(function(){var b=document.getElementById('cruiseBtn');return !!b && b.classList.contains('on')})()"):
        ev("document.getElementById('cruiseBtn').click()")
        time.sleep(0.3)


def setview(v, wait=1.3):
    ev("document.querySelector('.viewbtn[data-v=%s]').click()" % json.dumps(v))
    time.sleep(wait)


def flatten():
    ev("document.getElementById('riseBtn').click()")
    time.sleep(0.4)
    setview("top", 1.2)


def rise():
    ev("document.getElementById('riseBtn').click()")
    time.sleep(0.4)
    setview("iso", 1.4)


def scroll_to_stage():
    ev("(function(){var r=document.getElementById('viewport').getBoundingClientRect();"
       "window.scrollTo(0,Math.max(0,r.top+scrollY-70));return true})()")
    time.sleep(0.35)


def hitpoint():
    return ev("""(function(){var c=document.getElementById('scene'),r=c.getBoundingClientRect();
      for(var y=0.28;y<0.80;y+=0.035)for(var x=0.16;x<0.88;x+=0.035){
        var px=r.left+r.width*x,py=r.top+r.height*y;
        c.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,clientX:px,clientY:py,pointerId:9}));
        if(document.getElementById('tip').classList.contains('on'))return [Math.round(px),Math.round(py)];
      }return null})()""")


# ─────────── 画面合成 ───────────
def _font(sz):
    return ImageFont.truetype(FONT, sz)


def save(img, name, label=None):
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)
    if label:
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((28, 26, 28 + 18 * len(label) + 34, 78), radius=8,
                            fill=(247, 246, 241))
        d.text((45, 38), label, font=_font(22), fill=(32, 40, 35))
    img.convert("RGB").save(OUT_STILL / name, "JPEG", quality=90, subsampling=0)
    print("  still ->", name)


def crop_mode(raw, mode, label=None, **kw):
    im = Image.open(raw).convert("RGB")
    iw = min(W, im.width)   # 全页截图会少一条滚动条宽度
    if mode == "top":
        box = (0, 0, iw, H)
        out = im.crop(box)
    elif mode == "fit":
        out = Image.new("RGB", (W, H), (247, 246, 241))
        cp = im.copy()
        cp.thumbnail((W - 40, H - 40), Image.LANCZOS)
        out.paste(cp, ((W - cp.width) // 2, (H - cp.height) // 2))
    elif mode in ("stage", "controls", "info"):
        r = rect(kw.get("sel", "#viewport"))
        if mode == "stage":
            y = max(0, int(r["y"]) - 110)
        elif mode == "controls":
            y = max(0, int(r["y"]) - 300)
        else:
            y = max(0, int(r["y"]) + 180)
        y = min(y, max(0, im.height - H))
        box = (0, y, iw, y + H)
        out = im.crop(box)
    elif mode == "zoom":
        sel = kw["sel"]
        r = rect(sel)
        cx = r["x"] + r["w"] / 2
        cy = r["y"] + r["h"] / 2
        zw, zh = kw.get("zw", 1000), kw.get("zh", 562)
        x0 = max(0, min(im.width - zw, int(cx - zw / 2)))
        y0 = max(0, min(im.height - zh, int(cy - zh / 2 + kw.get("dy", 0))))
        out = im.crop((x0, y0, x0 + zw, y0 + zh)).resize((W, H), Image.LANCZOS)
    elif mode == "window":
        y = min(max(0, int(kw["y"])), max(0, im.height - H))
        out = im.crop((0, y, iw, y + H))
    else:
        raise ValueError(mode)
    save(out, kw["name"], label)


def capture_still(name, mode, label=None, **kw):
    raw = RAW / ("raw_%s.png" % name.replace(".jpg", ""))
    screenshot(raw, beyond=True)
    crop_mode(raw, mode, label, name=name, **kw)


def encode_clip(name, frames, fps=CLIP_FPS):
    """frames: 已按顺序写入的 PNG 路径列表"""
    if not frames:
        raise RuntimeError("no frames for " + name)
    # 统一为序列文件
    seq = RAW / ("seq_" + name.replace(".mp4", ""))
    seq.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(frames):
        shutil.copy2(f, seq / ("f%04d.png" % i))
    out = OUT_CLIP / name
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
           "-i", str(seq / "f%04d.png"), "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(shots.FPS), str(out)]
    subprocess.check_call(cmd)
    print("  clip  ->", name, len(frames), "frames", out.stat().st_size, "bytes")


def record(name, seconds, actions=None, fps=CLIP_FPS):
    """按固定帧率截取视口；actions(t) 在每帧前调用，用于驱动页面交互。"""
    frames = []
    n = int(seconds * fps)
    t0 = time.perf_counter()
    for i in range(n):
        if actions:
            actions(time.perf_counter() - t0)   # 用真实经过时间驱动交互
        f = RAW / ("%s_%04d.png" % (name.replace(".mp4", ""), i))
        screenshot(f, beyond=False)
        frames.append(f)
        target = t0 + (i + 1) / fps
        d = target - time.perf_counter()
        if d > 0:
            time.sleep(d)
    elapsed = time.perf_counter() - t0
    real_fps = len(frames) / elapsed if elapsed > 0 else fps
    encode_clip(name, frames, round(real_fps, 3))
    print("    real capture %.1fs -> playback fps %.2f" % (elapsed, real_fps))
    return frames


# ─────────── 主流程 ───────────
def main():
    global ws, _mid
    tabs = None
    for _ in range(80):
        try:
            tabs = json.loads(opener.open("http://127.0.0.1:%d/json/list" % PORT, timeout=2).read())
            break
        except Exception:
            time.sleep(0.4)
    pg = next(x for x in tabs if x.get("type") == "page")
    ws = websocket.create_connection(pg["webSocketDebuggerUrl"], suppress_origin=True, timeout=40)
    _mid = 0
    send("Page.enable")
    send("Runtime.enable")
    send("Emulation.setDeviceMetricsOverride",
         {"width": W, "height": H, "deviceScaleFactor": 1, "mobile": False})

    # ── 序章 / 3D 版基础状态 ──
    print("[1] 3D 版基础画面")
    nav(PAGE3D.as_uri())
    pause_cruise()
    flatten()
    capture_still("S01_commit_wall.jpg", "stage", "摊平 · 俯瞰 · 53 × 7")
    scroll_to_stage()

    def _rise_action(t):
        if 0.15 <= t < 0.25:
            ev("document.getElementById('riseBtn').click()")
    record("C01_rise.mp4", 6.0, _rise_action)
    time.sleep(0.8)
    capture_still("S03_iso.jpg", "stage", "等距 · 立体田垄")
    ev("window.scrollTo(0,0)")
    time.sleep(0.3)
    capture_still("S04_overview.jpg", "top", "耕年 · 立体年鉴")
    capture_still("S07_stats.jpg", "zoom", "真实贡献日历", sel=".stats", zw=1120, zh=630, dy=-30)
    capture_still("S08_legend.jpg", "zoom", "五档色阶与图例", sel=".legend", zw=1200, zh=675, dy=0)
    capture_still("S24_fullpage.jpg", "fit", "整页运行画面")

    # ── 2D 对照版 ──
    print("[2] 2D 对照版")
    nav(PAGE2D.as_uri())
    time.sleep(0.6)
    capture_still("S05_2d_record.jpg", "stage", "第一版 · 记录面", sel="#stage")
    ev("document.getElementById('flipBtn').click()")
    time.sleep(2.0)
    capture_still("S06_2d_flipped.jpg", "stage", "第一版 · 耕作面", sel="#stage")

    # ── 3D：视角、孤峰、天际线 ──
    print("[3] 视角与光影")
    nav(PAGE3D.as_uri())
    pause_cruise()
    setview("top", 1.5)
    capture_still("S09_grid.jpg", "stage", "俯瞰读色阶")
    capture_still("S21_dike.jpg", "stage", "金色田埂 · 休耕雾带")
    setview("iso", 1.4)
    # 以视口中心放大，突出孤峰光柱
    capture_still("S10_peak.jpg", "zoom", "孤峰 · 163 次贡献",
                  sel="#viewport", zw=1000, zh=562)
    setview("horizon", 1.6)
    capture_still("S11_horizon.jpg", "stage", "平视 · 贡献天际线")
    capture_still("S26_end.jpg", "stage")

    # 三视角动态录屏
    scroll_to_stage()

    def _views_action(t):
        if 0.15 <= t < 0.25:
            ev("document.querySelector('.viewbtn[data-v=\"top\"]').click()")
        elif 2.35 <= t < 2.45:
            ev("document.querySelector('.viewbtn[data-v=\"iso\"]').click()")
        elif 4.65 <= t < 4.75:
            ev("document.querySelector('.viewbtn[data-v=\"horizon\"]').click()")
    record("C02_views.mp4", 7.0, _views_action)

    # ── 无人机巡航 ──
    print("[4] 无人机巡航")
    nav(PAGE3D.as_uri())
    pause_cruise()
    scroll_to_stage()
    ev("document.getElementById('droneBtn').click()")
    time.sleep(0.65)
    capture_still("S13_drone_start.jpg", "stage", "起飞 · 田被清空")
    ev("document.getElementById('droneBtn').click()")  # 召回，重新完整录一轮
    time.sleep(1.2)
    scroll_to_stage()

    def _drone_action(t):
        if 0.15 <= t < 0.25:
            ev("document.getElementById('droneBtn').click()")
    record("C03_drone.mp4", 11.0, _drone_action)
    time.sleep(0.5)
    capture_still("S15_mission.jpg", "controls", "巡航完成 · 任务接口")
    capture_still("S16_controls.jpg", "zoom", "功能控制条",
                  sel="#secondary", zw=1200, zh=675, dy=0)

    # ── 反事实编辑 ──
    print("[5] 反事实与形态")
    nav(PAGE3D.as_uri())
    pause_cruise()
    ev("document.getElementById('editBtn').click()")
    time.sleep(0.4)
    hp = hitpoint()
    if hp:
        ev("(function(){var c=document.getElementById('scene');"
           "c.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:%d,clientY:%d}));"
           "return true})()" % (hp[0], hp[1]))
        time.sleep(0.6)
    print("  edit hitpoint", hp, "badge", ev("document.getElementById('editBadge').textContent"))
    capture_still("S17_counterfactual.jpg", "controls", "反事实编辑 · 实时重算")

    # 三种形态各截一张，合成三联（每一联都是真实截图的裁切）
    form_raw = []
    for fkey, tag in [("contour", "梯田"), ("weave", "织物"), ("rings", "年轮")]:
        ev("document.querySelector('#formbar .mini[data-f=%s]').click()" % json.dumps(fkey))
        time.sleep(1.3)
        p = RAW / ("form_%s.png" % fkey)
        screenshot(p, beyond=True)
        form_raw.append((p, tag))
    pw = 528
    panels = Image.new("RGB", (pw * 3, H), (247, 246, 241))
    for i, (p, tag) in enumerate(form_raw):
        im = Image.open(p).convert("RGB")
        r = rect("#viewport")
        y = min(max(0, int(r["y"]) - 150), max(0, im.height - 900))
        # 每联取真实纵向切片（不做形变拉伸）
        sl = im.crop((i * pw, y, i * pw + pw, y + 900))
        panels.paste(sl, (i * pw, 0))
        d = ImageDraw.Draw(panels)
        d.rounded_rectangle((i * pw + 16, 18, i * pw + 130, 66), radius=8,
                            fill=(247, 246, 241))
        d.text((i * pw + 30, 26), tag, font=_font(24), fill=(32, 40, 35))
    save(panels, "S18_forms.jpg", "同一份数据 · 三种形态")

    # ── 自定义账号 / 错误状态 ──
    print("[6] 账号与异常状态")
    nav(PAGE3D.as_uri())
    pause_cruise()
    ev("(function(){var i=document.getElementById('accountInput');i.value='https://example.com/foo';"
       "document.getElementById('accountGo').click();return true})()")
    time.sleep(0.8)
    capture_still("S20_error.jpg", "top", "异常状态 · 数据保持不变")
    print("  error status:", ev("document.getElementById('accountStatus').textContent"))

    nav(PAGE3D.as_uri())
    ev("(function(){var i=document.getElementById('accountInput');i.value='torvalds';"
       "document.getElementById('accountGo').click();return true})()")
    ok = False
    for _ in range(70):
        time.sleep(0.4)
        try:
            if ev("(function(){var e=document.getElementById('sourceLine');"
                  "return !!e && e.textContent.indexOf('torvalds')>=0})()"):
                ok = True
                break
        except Exception:
            pass
    print("  custom account loaded:", ok)
    pause_cruise()
    time.sleep(0.6)
    if ok:
        capture_still("S19_account.jpg", "top", "自定义 GitHub 账号")
    else:
        # 网络不可用时保留账号栏真实状态，不伪造成功画面
        capture_still("S19_account.jpg", "zoom", "自定义 GitHub 账号",
                      sel="#accountBar", zw=1200, zh=675, dy=0)

    # ── 悬停详情 / 相机环绕 ──
    print("[7] 交互细节与环绕")
    nav(PAGE3D.as_uri())
    pause_cruise()
    hp = hitpoint()
    print("  hover hitpoint", hp)
    if hp:
        capture_still("S22_detail.jpg", "info", "悬停 · 当日精确数值")
        capture_still("S25_hover.jpg", "zoom", "改动可被立刻验证",
                      sel="#tip", zw=900, zh=506, dy=0)
    else:
        capture_still("S22_detail.jpg", "info")
        capture_still("S25_hover.jpg", "stage")
    scroll_to_stage()
    ev("(function(){var c=document.getElementById('scene'),r=c.getBoundingClientRect();"
       "c.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:r.left+700,"
       "clientY:r.top+220,pointerId:3}));return true})()")

    def _orbit_action(t):
        ev("(function(){var c=document.getElementById('scene'),r=c.getBoundingClientRect();"
           "c.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,"
           "clientX:r.left+700+%d,clientY:r.top+220,pointerId:3}));return true})()"
           % min(360, int(t * 45)))
    record("C04_orbit.mp4", 6.5, _orbit_action)
    ev("(function(){var c=document.getElementById('scene'),r=c.getBoundingClientRect();"
       "c.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,clientX:r.left+1090,"
       "clientY:r.top+220,pointerId:3}));return true})()")

    # ── 汇总 ──
    print("\n=== 素材清单 ===")
    want = sorted(set(x["asset"] for x in shots.SHOTS))
    miss = []
    for a in want:
        p = (OUT_CLIP if a.endswith(".mp4") else OUT_STILL) / a
        print(("OK  " if p.exists() else "MISS"), a,
              p.stat().st_size if p.exists() else 0)
        if not p.exists():
            miss.append(a)
    if miss:
        raise RuntimeError("missing assets: %s" % miss)
    ws.close()


if __name__ == "__main__":
    try:
        main()
    finally:
        proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)
        # 保留 RAW 供排错，清理在 build_video.py 完成后由用户自行决定
        print("raw frames at", RAW)
