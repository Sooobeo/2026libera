"""Publication plots from the independently verified audit tables only."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[2]
AUDIT = Path(__file__).resolve().parent
ASSETS = ROOT / "paper/assets_20261029"
ASSETS.mkdir(parents=True, exist_ok=True)
data = json.loads((AUDIT / "numeric_audit.json").read_text(encoding="utf-8"))
arms = data["arm_summary"]
with (AUDIT / "scenario_metrics.csv").open(encoding="utf-8-sig") as f:
    scenarios = list(csv.DictReader(f))

plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False,
                     "font.size": 11, "axes.titlesize": 13, "axes.labelsize": 11,
                     "figure.facecolor": "white", "axes.facecolor": "white",
                     "text.color": "#233247", "axes.labelcolor": "#233247",
                     "xtick.color": "#233247", "ytick.color": "#536173",
                     "svg.fonttype": "none", "savefig.facecolor": "white"})
TEAL, AMBER, CORAL, INK, GRID = "#167582", "#DCA540", "#D47863", "#233247", "#E5E9EC"
labels = ["R0\n추가 전망 없음", "R1\n계획부터", "R2\n배분안 작성부터", "R3\n점검·수정부터"]


def finish(ax):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#B9C2CC")
    ax.tick_params(axis="both", length=0, pad=8)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=.7)


def save(fig, name):
    fig.savefig(ASSETS / (name + ".png"), dpi=260, bbox_inches="tight", pad_inches=.14)
    fig.savefig(ASSETS / (name + ".svg"), bbox_inches="tight", pad_inches=.14)
    plt.close(fig)


x = np.arange(4)
fig, ax = plt.subplots(figsize=(6.3, 4.9))
fig.subplots_adjust(top=.75, bottom=.26, left=.12, right=.98)
fig.text(.12, .955, "최종 배분안의 유효성과 외부 보정", fontsize=14, weight="bold")
fig.text(.12, .90, "조건별 최종 제안의 처리 결과", fontsize=10.5, color="#536173")
bottom = np.zeros(4)
sources = []
for key, label, color in (("raw_valid", "원출력 유효(기존 비중)", TEAL), ("rescued", "비례 보정 후 유효", AMBER), ("fallback", "실패: 기존 비중 유지", CORAL)):
    values = np.array([r[key] / r["trajectories"] * 100 for r in arms])
    ax.bar(x, values, bottom=bottom, width=.64, color=color, edgecolor="white", linewidth=.8, label=label)
    for i, (n, pct) in enumerate(zip([r[key] for r in arms], values)):
        if n:
            textcolor = "white" if key == "raw_valid" else "#172B3A"
            ax.text(i, bottom[i] + pct / 2, f"{pct:g}%", ha="center", va="center", fontsize=11, color=textcolor, weight="bold")
    bottom += values
ax.set_xticks(x, labels)
ax.set_ylabel("작업 흐름 비중 (%)")
ax.set_ylim(0, 100)
ax.set_yticks([0, 25, 50, 75, 100])
ax.legend(loc="lower left", bbox_to_anchor=(-.02, 1.03), frameon=False, ncol=3, fontsize=10, handlelength=.9, columnspacing=.7, handletextpad=.35)
finish(ax)
fig.text(.12, .055, "원출력 유효안은 모두 기존 비중 h를 유지했다.\n실제 재배분은 외부 비례 보정 이후 유효해졌다.", fontsize=10.2, color="#536173", linespacing=1.6)
save(fig, "figure1_validity_by_timing")
for r in arms:
    sources.append({"arm": r["arm"], "n": r["trajectories"], **{k: r[k] for k in ("raw_valid", "rescued", "fallback")}, **{k + "_percent": 100*r[k]/r["trajectories"] for k in ("raw_valid", "rescued", "fallback")}})
with (ASSETS / "figure1_validity_by_timing.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(sources[0])); w.writeheader(); w.writerows(sources)

fig, axes = plt.subplots(3, 1, figsize=(6.3, 8.8))
fig.subplots_adjust(top=.82, bottom=.09, left=.15, right=.97, hspace=.57)
fig.text(.15, .965, "정보 제공 시점과 배분·판단 품질", fontsize=14, weight="bold")
fig.text(.15, .925, "점: 상황별 지표 · ◆: 전체 평균", fontsize=10.5, color="#536173")
for ax, name, scale, title, ylabel in zip(axes, ("D_full", "G_full", "R_full"), (100., 100., 10000.),
                                         ("A  펀드 간 배분 거리", "B  기준 대비 이질성 격차", "C  기대수익 기회손실"),
                                         ("D (%p)", "G = D* - D (%p)", "R (월간 bp)")):
    for i, arm in enumerate(("R0", "R1", "R2", "R3")):
        selected = sorted([r for r in scenarios if r["arm"] == arm], key=lambda r: r["scenario"])
        for precision, color, offset in ((.5, AMBER, -.085), (2., TEAL, .085)):
            sub = [r for r in selected if float(r["r"]) == precision]
            jitter = np.linspace(-.042, .042, len(sub))
            ax.scatter(i + offset + jitter, [float(r[name])*scale for r in sub], s=30, color=color, alpha=.86, edgecolors="white", linewidths=.45, zorder=3)
    means = [r[name]*scale for r in arms]
    ax.scatter(x, means, color=INK, marker="D", s=50, edgecolors="white", linewidths=.8, zorder=5)
    ax.set_title(title, loc="left", pad=11, weight="bold", fontsize=11.5)
    ax.set_xticks(x, ["R0", "R1", "R2", "R3"])
    ax.set_ylabel(ylabel)
    ax.set_xlim(-.5, 3.5)
    finish(ax)
axes[0].axhline(arms[0]["Dstar_full"]*100, color="#647587", linestyle=(0, (5, 3)), linewidth=1.2, zorder=2)
axes[0].text(.99, .95, f"평균 기준 D* = {arms[0]['Dstar_full']*100:.2f}%p", transform=axes[0].transAxes, fontsize=10, color="#536173", ha="right", va="top")
axes[0].set_ylim(20, 60)
axes[0].set_yticks([20, 30, 40, 50, 60])
axes[1].axhline(0, color="#647587", linewidth=.9, zorder=2)
axes[1].text(.02, .95, "G > 0: 기준보다 낮은 이질성", transform=axes[1].transAxes, fontsize=10, color="#536173", va="top")
axes[2].set_ylim(bottom=-8)
handles = [Line2D([], [], marker="o", linestyle="", color=AMBER, markersize=5.5, label="낮은 정밀도 r = 0.5"),
           Line2D([], [], marker="o", linestyle="", color=TEAL, markersize=5.5, label="높은 정밀도 r = 2.0"),
           Line2D([], [], marker="D", linestyle="", color=INK, markersize=5.5, label="전체 평균")]
fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(.14, .891), frameon=False, ncol=3, fontsize=10, handletextpad=.25, columnspacing=.65)
fig.text(.15, .028, "최종 적용 비중은 외부 비례 보정과 실패 시 h 유지를 포함한다.", fontsize=10, color="#536173")
save(fig, "figure2_distance_gap_regret")
plotrows = [{k:r[k] for k in ("scenario", "r", "arm", "D_full", "Dstar_full", "G_full", "R_full")} | {"D_percentage_points": float(r["D_full"])*100, "Dstar_percentage_points": float(r["Dstar_full"])*100, "G_percentage_points": float(r["G_full"])*100, "R_monthly_basis_points": float(r["R_full"])*10000} for r in scenarios]
with (ASSETS / "figure2_distance_gap_regret.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(plotrows[0])); w.writeheader(); w.writerows(plotrows)
print(json.dumps({"output_directory": str(ASSETS), "figures": ["figure1_validity_by_timing", "figure2_distance_gap_regret"], "formats": ["png", "svg", "csv"]}))
