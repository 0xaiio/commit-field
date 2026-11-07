# -*- coding: utf-8 -*-
"""《耕年 · 立体年鉴》推广片的唯一时间轴数据源。

旁白文本从 01_文稿/推广文稿.md 的 N01..N26 逐行读取，字幕、配音、脚本、
分镜表、转场说明与最终成片全部由本文件派生，保证彼此严格一致。
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
DOC = ROOT / "01_文稿" / "推广文稿.md"
VIDEO_SRC = REPO / "耕年-CommitField-3D.html"
VIDEO_SRC_2D = REPO / "耕年-CommitField.html"

VOICE = "zh-CN-YunyangNeural"      # 男声 · Professional / Reliable · 沉稳
RATE = "+0%"                      # 正常语速
W, H, FPS = 1600, 900, 24         # 成片规格


def narration():
    s = DOC.read_text(encoding="utf-8")
    rows = re.findall(r"^(N\d{2})｜(.+)$", s, re.M)
    assert len(rows) == 26, "旁白段数应为 26，实际 %d" % len(rows)
    return dict(rows)


NARR = narration()

# 每镜头：旁白编号 / 画面素材 / 画面描述 / 画面重点 / 转场(到下一镜头) / 转场时长 /
#         配音前留白 lead / 配音后演示留白 tail / 章节 / 上屏补充信息
SHOTS = [
    dict(id="S01", n="N01", asset="S01_commit_wall.jpg", chapter="序章",
         visual="3D 版摊平俯瞰，53×7 五档色块铺满画面", focus="熟悉的 commit 墙、色阶",
         trans="fade", tdur=0.50, lead=0.45, tail=0.70, badge=""),
    dict(id="S02", n="N02", asset="C01_rise.mp4", chapter="序章",
         visual="实拍录屏：点击「立起为立体田」，370 根柱子连续升起", focus="平面变立体的生长转场",
         trans="fade", tdur=0.50, lead=0.35, tail=2.10, badge=""),
    dict(id="S03", n="N03", asset="S03_iso.jpg", chapter="序章",
         visual="等距视角全田，柱高起伏与孤峰光柱", focus="高低、阴影、孤峰",
         trans="fadewhite", tdur=0.90, lead=0.35, tail=1.35, badge=""),
    dict(id="S04", n="N04", asset="S04_overview.jpg", chapter="序章",
         visual="首页整体：标题、五张统计卡、来源行、控制条、3D 视口", focus="作品全貌与真实数据标注",
         trans="fadewhite", tdur=0.90, lead=0.35, tail=1.35, badge=""),

    dict(id="S05", n="N05", asset="S05_2d_record.jpg", chapter="一 · 创作过程",
         visual="2D 对照版记录面，格子和月份轴", focus="第一版的起点",
         trans="fade", tdur=0.45, lead=0.35, tail=0.60, badge=""),
    dict(id="S06", n="N06", asset="S06_2d_flipped.jpg", chapter="一 · 创作过程",
         visual="2D 版翻面后的耕作面：土壤、作物、金色田埂、休耕雾", focus="翻面隐喻与四类信息编码",
         trans="dissolve", tdur=0.45, lead=0.35, tail=0.60, badge=""),
    dict(id="S07", n="N07", asset="S07_stats.jpg", chapter="一 · 创作过程",
         visual="3D 版五张统计卡与来源行特写", focus="2,978 / 247 / 37 天 / 2 段 / 163 次",
         trans="fade", tdur=0.45, lead=0.35, tail=0.60,
         badge="github.com/hengxin · 2025-11-02 → 2026-11-06 · 370 天"),
    dict(id="S08", n="N08", asset="S08_legend.jpg", chapter="一 · 创作过程",
         visual="图例与分档色阶特写", focus="真实数据暴露的分档问题",
         trans="dissolve", tdur=0.45, lead=0.35, tail=0.60, badge=""),
    dict(id="S09", n="N09", asset="S09_grid.jpg", chapter="一 · 创作过程",
         visual="俯瞰视角下的五档色阶网格", focus="层次回到数据本身",
         trans="fadewhite", tdur=0.90, lead=0.35, tail=1.35,
         badge="GitHub 原生五档 0 / 1–17 / 18–34 / 39–49 / 54–163"),

    dict(id="S10", n="N10", asset="S10_peak.jpg", chapter="二 · 项目成果",
         visual="孤峰特写：163 次贡献那天的柱体与光柱", focus="数据自身生成的视觉焦点",
         trans="smoothleft", tdur=0.40, lead=0.35, tail=0.80, badge=""),
    dict(id="S11", n="N11", asset="S11_horizon.jpg", chapter="二 · 项目成果",
         visual="平视视角，一年贡献的天际线与地平线辉光", focus="长焦透视与光影",
         trans="smoothleft", tdur=0.40, lead=0.35, tail=0.80, badge=""),
    dict(id="S12", n="N12", asset="C02_views.mp4", chapter="二 · 项目成果",
         visual="实拍录屏：俯瞰 → 等距 → 平视三视角缓动飞行", focus="同一份数据的三种读法",
         trans="fade", tdur=0.40, lead=0.35, tail=1.90, badge=""),
    dict(id="S13", n="N13", asset="S13_drone_start.jpg", chapter="二 · 项目成果",
         visual="无人机起飞，田被清空、状态卡出现", focus="巡航起点与任务反馈",
         trans="fade", tdur=0.40, lead=0.35, tail=0.70, badge=""),
    dict(id="S14", n="N14", asset="C03_drone.mp4", chapter="二 · 项目成果",
         visual="实拍录屏：无人机沿时间轴播下 commits，左半田立起、右半仍是平面", focus="沿途播下的核心演示",
         trans="fade", tdur=0.40, lead=0.35, tail=3.40,
         badge="播下 247 枚 · 跳过 123 块休耕地 · 全程约 10 秒"),
    dict(id="S15", n="N15", asset="S15_mission.jpg", chapter="二 · 项目成果",
         visual="巡航完成报告与「播种 / 巡检 / 收割」任务按钮", focus="可插拔任务接口与状态机",
         trans="dissolve", tdur=0.45, lead=0.35, tail=0.65, badge=""),
    dict(id="S16", n="N16", asset="S16_controls.jpg", chapter="二 · 项目成果",
         visual="第二控制条特写：反事实、形态、任务、生态、海报、纪录片", focus="功能全貌",
         trans="smoothleft", tdur=0.40, lead=0.35, tail=0.65, badge=""),
    dict(id="S17", n="N17", asset="S17_counterfactual.jpg", chapter="二 · 项目成果",
         visual="反事实编辑态：虚线幽灵柱与「改动 1 天」Δ 徽标", focus="统计实时重算",
         trans="dissolve", tdur=0.45, lead=0.35, tail=0.65,
         badge="实测：抹掉 45 次贡献那天 → 最长连续 37 天变 21 天"),
    dict(id="S18", n="N18", asset="S18_forms.jpg", chapter="二 · 项目成果",
         visual="真实截图三联：梯田 / 织物 / 年轮三种形态", focus="同一数据的不同世界观",
         trans="smoothleft", tdur=0.40, lead=0.35, tail=0.75, badge=""),
    dict(id="S19", n="N19", asset="S19_account.jpg", chapter="二 · 项目成果",
         visual="自定义账号栏、状态提示与更新后的统计卡", focus="账号输入与数据切换",
         trans="fade", tdur=0.45, lead=0.35, tail=0.65, badge=""),
    dict(id="S20", n="N20", asset="S20_error.jpg", chapter="二 · 项目成果",
         visual="错误状态：红色提示文字，原有数据保持不变", focus="异常状态不破坏当前数据",
         trans="fade", tdur=0.45, lead=0.35, tail=0.65, badge=""),
    dict(id="S21", n="N21", asset="S21_dike.jpg", chapter="二 · 项目成果",
         visual="俯瞰下的金色田埂与休耕雾带", focus="克制后的信息密度",
         trans="fade", tdur=0.55, lead=0.35, tail=0.75,
         badge="田埂 ≥12 天连续 · 雾带 ≥10 天空白"),
    dict(id="S22", n="N22", asset="S22_detail.jpg", chapter="二 · 项目成果",
         visual="悬停当日精确数值的 tooltip 与「这一格」详情面板", focus="数据始终可读",
         trans="fadewhite", tdur=0.90, lead=0.35, tail=1.35, badge=""),

    dict(id="S23", n="N23", asset="C04_orbit.mp4", chapter="三 · 使用体验",
         visual="实拍录屏：拖拽相机绕田一周", focus="可探索的交互体验",
         trans="fade", tdur=0.50, lead=0.35, tail=1.90, badge=""),
    dict(id="S24", n="N24", asset="S24_fullpage.jpg", chapter="三 · 使用体验",
         visual="整页运行画面，右下角 FPS 指示可见", focus="验证后的运行状态",
         trans="dissolve", tdur=0.50, lead=0.35, tail=0.80,
         badge="76 项回归 + 37 项账号断言 · 60 FPS · 0 控制台报错"),
    dict(id="S25", n="N25", asset="S25_hover.jpg", chapter="三 · 使用体验",
         visual="柱子悬停高亮与详情面板联动", focus="改动能被立刻打开、点击、验证",
         trans="fade", tdur=0.55, lead=0.35, tail=0.85, badge=""),
    dict(id="S26", n="N26", asset="S26_end.jpg", chapter="三 · 使用体验",
         visual="平视天际线收尾，片尾信息卡", focus="作品与仓库地址",
         trans="fade", tdur=0.50, lead=0.40, tail=6.00, badge=""),
]

assert len(SHOTS) == 26
assert all(s["n"] in NARR for s in SHOTS)
assert all(s["tail"] >= s["tdur"] + 0.15 for s in SHOTS[:-1]), \
    "配音后留白必须覆盖该镜头到下一镜头的转场时长"

CHAPTERS = [
    ("序章 · 看效果", "S01"),
    ("一 · 创作过程", "S05"),
    ("二 · 项目成果", "S10"),
    ("三 · 使用体验", "S23"),
]

END_CARD = [
    "耕年 · 立体年鉴",
    "github.com/0xaiio/commit-field   ·   MIT",
    "画面均为项目真实运行截图与录屏（经裁切排版），未使用素材库画面",
    "模型标识请在客户端确认；本片不陈述模型参数与评测成绩",
]
