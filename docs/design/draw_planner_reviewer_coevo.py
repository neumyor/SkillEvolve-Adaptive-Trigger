"""Render the Planner-Reviewer co-evolution diagram (v1, option B) to PNG."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib import patheffects as pe
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
font_manager.fontManager.addfont(FONT)
plt.rcParams["font.family"] = [font_manager.FontProperties(fname=FONT).get_name(), "DejaVu Sans"]

OUT = Path(__file__).resolve().parent / "planner_reviewer_coevo.png"

fig, ax = plt.subplots(figsize=(20, 15.4))
ax.set_xlim(0, 100)
ax.set_ylim(-3, 74)
ax.axis("off")

INK = "#262626"
SUB = "#5a5a5a"
BLUE, ORANGE, GREEN = "#3b78c2", "#d1802c", "#3f9a57"
GOLD, PURPLE, GRAY, VIOLET = "#b8901a", "#8a5a9e", "#6b6b6b", "#7a55b8"
TINT = {BLUE: "#e6effa", ORANGE: "#fbeee0", GRAY: "#ececec"}

HEADER = 3.2
LINE = 2.05


def card(cx, cy, w, h, title, lines, color, solid=True, size=10.5):
    """A card with a colored header strip and left-aligned body lines."""
    x0, y0 = cx - w / 2, cy - h / 2
    ax.add_patch(FancyBboxPatch((x0, y0), w, h, boxstyle="round,pad=0.5,rounding_size=1.0",
                                fc="white", ec=color, lw=1.8, zorder=2))
    head_fc = color if solid else TINT.get(color, "#eeeeee")
    head_tc = "white" if solid else color
    ax.add_patch(FancyBboxPatch((x0, y0 + h - HEADER), w, HEADER,
                                boxstyle="round,pad=0.5,rounding_size=1.0",
                                fc=head_fc, ec=color, lw=1.8, zorder=3))
    ax.add_patch(Rectangle((x0 - 0.5, y0 + h - HEADER - 0.5), w + 1, 1.0,
                           fc=head_fc, ec="none", zorder=3.5))
    ax.plot([x0 - 0.5, x0 - 0.5], [y0 + h - HEADER - 0.5, y0 + h - HEADER + 0.5],
            color=color, lw=1.8, zorder=4)
    ax.plot([x0 + w + 0.5, x0 + w + 0.5], [y0 + h - HEADER - 0.5, y0 + h - HEADER + 0.5],
            color=color, lw=1.8, zorder=4)
    ax.text(x0 + 0.6, y0 + h - HEADER / 2 + 0.1, title, ha="left", va="center",
            fontsize=12.5, weight="bold", color=head_tc, zorder=5)
    top = y0 + h - HEADER - 1.9
    for i, line in enumerate(lines):
        ax.text(x0 + 0.8, top - i * LINE, line, ha="left", va="center",
                fontsize=size, color=INK, zorder=5)


def chip(cx, cy, w, h, text, ec, fc="white"):
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                                boxstyle="round,pad=0.4,rounding_size=1.2",
                                fc=fc, ec=ec, lw=1.6, zorder=2))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=10.5, color=INK, zorder=5)


def panel(x0, y0, x1, y1, text):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0,
                                boxstyle="round,pad=0.3,rounding_size=1.5",
                                fc="#f7f7f5", ec="#dddddd", lw=1.2, zorder=0))
    ax.text(x0 - 1.1, (y0 + y1) / 2, text, ha="center", va="center", rotation=90,
            fontsize=12, color="#8a8a8a", weight="bold")


def arrow(p, q, color=INK, ls="-", lw=1.8, z=1, bridge=False):
    a = FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=17, color=color,
                        lw=lw, linestyle=ls, shrinkA=0, shrinkB=0, zorder=z)
    if bridge:
        a.set_path_effects([pe.withStroke(linewidth=lw + 6, foreground="#f7f7f5")])
    ax.add_patch(a)


def route(points, color=INK, ls="-", lw=1.8):
    xs, ys = zip(*points[:-1])
    ax.plot(xs, ys, color=color, lw=lw, ls=ls, solid_capstyle="round", zorder=1)
    arrow(points[-2], points[-1], color=color, ls=ls, lw=lw)


def note(x, y, text, color=SUB, ha="center", size=10, weight="normal"):
    ax.text(x, y, text, ha=ha, va="center", fontsize=size, color=color, weight=weight, zorder=6)


# ---------------- Title ----------------
ax.text(50, 72.4, "Planner – Reviewer 协同进化（第一版）", ha="center", va="center",
        fontsize=20, weight="bold", color=INK)
ax.text(50, 69.9, "每一轮：Planner 提议 → Reviewer 先预测 → 真实抽检 → 按事先固定的规则决策；判定者核实声明，只写入账本",
        ha="center", va="center", fontsize=11.5, color=SUB)

panel(3, 23, 99, 67.5, "一轮的流程")
panel(3, 1, 99, 22, "账本与记忆")

C1, C2, C3, C4 = 14, 38, 62, 86
W = 19
ROW = 48
H = 13.5

# ---------------- Inputs and the acceptance loop ----------------
chip(8, 60, 9.5, 3.4, "本轮 train 经验卡", "#9a9a9a")
chip(20, 60, 9.5, 3.4, "当前 Skill", VIOLET, fc="#f1eafb")
arrow((8.6, 57.9), (12, 55.3))
arrow((19.4, 57.9), (16, 55.3))
route([(C4, 55.3), (C4, 64.6), (20, 64.6), (20, 62.1)], color=VIOLET, lw=2.4)
note(53, 65.8, "接受 → 成为下一轮的当前 Skill", color=VIOLET, size=11, weight="bold")

# ---------------- Pipeline ----------------
card(C1, ROW, W, H, "① 提议 · Planner",
     ["读：当前 Skill、train 经验卡、提案历史",
      "出：一条结构化改动",
      "附声明：触发条件 + 动作变化",
      "看不到 val 题目和 Reviewer 理由"], BLUE)
card(C2, ROW, W, H, "② 预测 · Reviewer",
     ["读：val 题目、当前 Skill、改动与声明",
      "参考：相似的错判案例",
      "出：每道 val 题的预测 Δ",
      "先于抽检完成，看不到抽检结果"], ORANGE)
card(C3, ROW, W, H, "③ 抽检 · 真实环境",
     ["随机抽取部分 val 题",
      "旧 / 新 Skill 各跑一次",
      "固定随机性，保留两条轨迹",
      "得到真实 Δ 和首个差异片段"], GREEN)
card(C4, ROW, W, H, "④ 决策 · 固定规则",
     ["用抽检结果修正预测",
      "置信下界 > 0 才接受",
      "只看真实 Δ，不看判定结论",
      "规则在实验开始前写定"], GOLD)

arrow((C1 + W / 2 + 0.6, ROW), (C2 - W / 2 - 0.6, ROW), lw=2.2)
note((C1 + C2) / 2, ROW + 2.6, "改动\n+ 声明", size=9.5, color=INK)
arrow((C2 + W / 2 + 0.6, ROW), (C3 - W / 2 - 0.6, ROW), lw=2.2)
note((C2 + C3) / 2, ROW + 2.6, "预测\n完成后", size=9.5, color=INK)
arrow((C3 + W / 2 + 0.6, ROW), (C4 - W / 2 - 0.6, ROW), lw=2.2)
note((C3 + C4) / 2, ROW + 2.0, "真实 Δ", size=9.5, color=INK)

# ---------------- Judge ----------------
JY = 31.5
card(C3, JY, W, 13.2, "⑤ 判定 · 独立判定者",
     ["冻结，看不到成绩",
      "读：规则、声明、首个差异片段",
      "出：与规则无关 · 符合声明",
      "　　不符合声明 · 无法判断"], PURPLE)
arrow((C3, ROW - H / 2 - 0.6), (C3, JY + 6.6 + 0.6), color=PURPLE)
note(C3 + 1.0, 39.65, "有差异时才调用", ha="left", size=9.5, color=PURPLE)

# ---------------- Ledger and memories ----------------
MY = 10
card(C1, MY, W, 13.5, "Planner 记忆 · 提案历史",
     ["每个改动的结论：有效 / 无效 / 证据不足",
      "声明兑现：触发 n/N，符合声明 n/N",
      "Reviewer 预测 vs 真实 Δ",
      "只到改动这一层，不含 val 题目"], BLUE, solid=False, size=10)
card(C2, MY, W, 13.5, "Reviewer 记忆 · 错判案例",
     ["高估：看似有用，实则无用",
      "低估：看似无用，实则有用",
      "每例附判定结论（如：规则未被触发）",
      "含 val 题目，按固定规则检索"], ORANGE, solid=False, size=10)
card(74.5, MY, 43, 13.5, "共享账本",
     ["每个改动 × 每道抽检题记一行",
      "字段：改动 · 声明 · 预测 Δ · 判定结论 · 真实 Δ · 决策",
      "只追加，不修改",
      "两份记忆都由账本计算得出，可以随时重算"], GRAY, size=10.5)

# writes into the ledger (dashed)
arrow((C3, JY - 6.6 - 0.6), (C3, MY + 6.75 + 0.6), color=GRAY, ls="--")
note(C3 + 1.0, 21.0, "写入账本", ha="left", size=9.5)
arrow((C4, ROW - H / 2 - 0.6), (C4, MY + 6.75 + 0.6), color=GRAY, ls="--")
note(C4 + 1.0, 30.0, "预测 Δ · 真实 Δ · 决策\n写入账本", ha="left", size=9.5)

# ledger -> memories
arrow((74.5 - 21.5 - 0.6, MY), (C2 + W / 2 + 0.6, MY), color=ORANGE, lw=2.2)
route([(56, MY + 6.75 + 0.6), (56, 19.4), (20, 19.4), (20, MY + 6.75 + 0.6)], color=BLUE, lw=2.2)
note(29, 20.5, "按改动汇总 · 去掉 val 题目", color=BLUE, size=10, weight="bold")

# memories -> players
arrow((9, MY + 6.75 + 0.6), (9, ROW - H / 2 - 0.6), color=BLUE, lw=2.2)
arrow((C2, MY + 6.75 + 0.6), (C2, ROW - H / 2 - 0.6), color=ORANGE, lw=2.2, z=1.5, bridge=True)
note(9.8, 31.5, "每轮刷新", ha="left", size=10, color=BLUE, weight="bold")
note(C2 + 0.8, 31.5, "每轮刷新", ha="left", size=10, color=ORANGE, weight="bold")

# ---------------- Legend ----------------
ax.plot([30, 34], [-1.6, -1.6], color=INK, lw=2)
note(34.8, -1.6, "数据流", ha="left")
ax.plot([42, 46], [-1.6, -1.6], color=GRAY, lw=2, ls="--")
note(46.8, -1.6, "写入账本", ha="left")
ax.plot([55, 57], [-1.6, -1.6], color=BLUE, lw=2.4)
ax.plot([57, 59], [-1.6, -1.6], color=ORANGE, lw=2.4)
note(59.8, -1.6, "刷新记忆", ha="left")
note(66, -1.6, "判定者只影响记忆，不影响是否接受", ha="left")

fig.savefig(OUT, dpi=160, bbox_inches="tight", facecolor="white")
print(OUT)
