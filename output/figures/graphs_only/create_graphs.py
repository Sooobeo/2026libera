from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
ARMS = ['R0', 'R1', 'R2', 'R3']
LABELS = ['R0  미제공', 'R1  계획부터', 'R2  작성부터', 'R3  점검부터']
COLORS = ['#7B8593', '#4D79B4', '#BE8545', '#207F74']
INK = '#24394D'
MUTED = '#657487'
Y = np.arange(4)

summary = pd.read_csv(ROOT / 'research/paper_final_20261029/arm_summary.csv').set_index('arm').loc[ARMS]
scenarios = pd.read_csv(ROOT / 'paper/assets_20261029/figure2_distance_gap_regret.csv')
paths = pd.read_csv(ROOT / 'paper/assets_20261029/figure1_validity_by_timing.csv').set_index('arm').loc[ARMS]
means = scenarios.groupby('arm')[['G_percentage_points', 'R_monthly_basis_points']].mean().loc[ARMS]
assert np.allclose(means.G_percentage_points, summary.G_full * 100)
assert np.allclose(means.R_monthly_basis_points, summary.R_full * 10000)
assert np.array_equal(paths.raw_valid + paths.rescued + paths.fallback, paths.n)
assert np.array_equal(summary.raw_equal_h_1e12, summary.raw_valid)
assert np.array_equal(summary.effective_equal_h_1e12 + summary.rescued, summary.trajectories)
G = means.G_percentage_points.to_numpy()
R = means.R_monthly_basis_points.to_numpy()
HOLD = float(summary.hold_h_R_full.iloc[0] * 10000)
RAW = paths.raw_valid_percent.to_numpy()
RESCUED = paths.rescued_percent.to_numpy()
FALLBACK = paths.fallback_percent.to_numpy()
VALID = RAW + RESCUED

font_manager.fontManager.addfont('C:/Windows/Fonts/malgun.ttf')
font_manager.fontManager.addfont('C:/Windows/Fonts/malgunbd.ttf')
plt.rcParams.update({
    'font.family': 'Malgun Gothic',
    'axes.unicode_minus': False,
    'text.color': INK,
    'axes.labelcolor': MUTED,
    'xtick.color': MUTED,
    'ytick.color': MUTED,
    'font.size': 12,
    'svg.fonttype': 'path',
    'savefig.facecolor': 'white',
})


def base(ax, title):
    ax.set_facecolor('white')
    ax.set_ylim(3.55, -.65)
    ax.set_yticks(Y, LABELS)
    ax.tick_params(axis='y', length=0, pad=12, labelsize=12)
    ax.tick_params(axis='x', length=0, pad=9, labelsize=10.5)
    for tick, color in zip(ax.get_yticklabels(), COLORS):
        tick.set_color(color)
        tick.set_fontweight('bold')
    ax.axhspan(2.61, 3.39, color='#EDF6F4', zorder=0)
    ax.grid(axis='x', color='#E7EBF0', linewidth=.7)
    ax.set_axisbelow(True)
    for side in ['top', 'left', 'right']:
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color('#D5DDE5')
    ax.set_title(title, fontsize=16.5, fontweight='bold', loc='left', pad=24)


def convergence(ax):
    base(ax, '과잉수렴 격차')
    ax.set_xlim(-6.4, 5.2)
    ax.set_xticks([-6, -3, 0, 3])
    ax.axvline(0, color='#697A8A', linewidth=1.1, zorder=2)
    for y, val, color in zip(Y, G, COLORS):
        ax.plot([0, val], [y, y], color=color, linewidth=4.2,
                solid_capstyle='round', alpha=.6, zorder=3)
        ax.scatter(val, y, color=color, s=118, edgecolor='white', linewidth=1, zorder=4)
        dx = .28 if val >= 0 else -.28
        ax.text(val + dx, y, f'{val:+.2f}', va='center',
                ha='left' if val >= 0 else 'right', fontsize=13, color=color, fontweight='bold')
    ax.set_xlabel('평균 G (%p)', labelpad=13, fontsize=11.5)
    ax.text(0, -.26, 'G > 0: 기준보다 펀드 간 차이 축소',
            transform=ax.transAxes, fontsize=10.2, color=MUTED, va='top')


def expected_loss(ax):
    base(ax, '월간 기대수익 손실')
    ax.set_xlim(84.7, 102.4)
    ax.set_xticks([85, 90, 95, 100])
    ax.axvline(HOLD, color='#8A98A7', linewidth=1.1, linestyle=(0, (4, 3)), zorder=2)
    for y, val, color in zip(Y, R, COLORS):
        ax.plot([HOLD, val], [y, y], color=color, linewidth=4.2,
                solid_capstyle='round', alpha=.35, zorder=3)
        ax.scatter(val, y, color=color, s=118, edgecolor='white', linewidth=1, zorder=4)
        ax.text(val + .42, y, f'{val:.2f}', va='center', ha='left',
                fontsize=13, color=color, fontweight='bold')
    ax.set_xlabel('평균 손실 (bp) · 낮을수록 좋음', labelpad=13, fontsize=11.5)
    ax.legend([Line2D([0], [0], color='#8A98A7', linestyle=(0, (4, 3)), lw=1.1)],
              [f'기존 비중 유지: {HOLD:.2f}bp'], frameon=False, fontsize=10.2,
              loc='upper left', bbox_to_anchor=(-.02, -.22), handlelength=2, borderaxespad=0)


def allocation_paths(ax):
    base(ax, '최종 배분의 생성 경로')
    ax.set_xlim(0, 126)
    ax.set_xticks([0, 25, 50, 75, 100])
    # Both the first and third segments retain the existing holdings.
    # The middle segment contains all observed actual reallocations.
    path_colors = ['#526A82', '#A2B8CB', '#E3E8EE']
    bottom = np.zeros(4)
    for values, color, label_color in zip([RAW, RESCUED, FALLBACK], path_colors,
                                          ['white', '#24394D', '#53677C']):
        ax.barh(Y, values, left=bottom, height=.57, color=color,
                edgecolor='white', linewidth=1.2, zorder=3)
        for y, value, start in zip(Y, values, bottom):
            if value:
                label = f'{value:g}%'
                ax.text(start + value/2, y, label, va='center', ha='center',
                        color=label_color, fontsize=10.4, fontweight='bold', zorder=4)
        bottom += values
    ax.text(106, -.46, '유효율', ha='left', va='center', fontsize=10.3, color=MUTED)
    for y, value, color in zip(Y, VALID, COLORS):
        ax.text(106, y, f'{value:.1f}%', ha='left', va='center',
                fontsize=12.5, fontweight='bold', color=color)
    ax.set_xlabel('구성 비율 (%)', labelpad=13, fontsize=11.5)
    handles = [Patch(facecolor=c) for c in path_colors]
    labels = ['원출력 유효\n기존 비중 유지', '정규화 후 유효\n실제 재배분', '실패 처리\n기존 비중 유지']
    ax.legend(handles, labels, ncol=3, frameon=False, fontsize=9.2,
              loc='upper left', bbox_to_anchor=(-.02, -.22), handlelength=1.1,
              columnspacing=1.4, handletextpad=.55, borderaxespad=0)


PLOTS = [
    ('01_convergence_gap', convergence),
    ('02_expected_return_loss', expected_loss),
    ('03_allocation_paths', allocation_paths),
]

# Deliver three standalone chart images, with no slide or narrative decoration.
for name, draw in PLOTS:
    fig, ax = plt.subplots(figsize=(7.5, 5.5), dpi=300, facecolor='white')
    fig.subplots_adjust(left=.205, right=.965, bottom=.25, top=.855)
    draw(ax)
    fig.savefig(OUT / f'{name}.png', dpi=300)
    fig.savefig(OUT / f'{name}.svg')
    plt.close(fig)

# A plain aligned arrangement of the same three charts for comparison.
fig, axes = plt.subplots(1, 3, figsize=(22, 5.8), dpi=240, facecolor='white',
                         gridspec_kw={'width_ratios': [1, 1, 1.35]})
fig.subplots_adjust(left=.064, right=.989, bottom=.255, top=.84, wspace=.56)
for (_, draw), ax in zip(PLOTS, axes):
    draw(ax)
fig.savefig(OUT / 'three_graphs_aligned.png', dpi=240)
fig.savefig(OUT / 'three_graphs_aligned.svg')
plt.close(fig)

with Image.open(OUT / 'three_graphs_aligned.png') as im:
    im.resize((2112, 557), Image.Resampling.LANCZOS).save(OUT / 'three_graphs_preview.png')

print(json.dumps({'output_directory': str(OUT),
                  'individual_charts': [name + '.png' for name, _ in PLOTS],
                  'comparison': 'three_graphs_aligned.png',
                  'G': G.round(2).tolist(), 'regret': R.round(2).tolist(),
                  'valid_percent': VALID.tolist()}, ensure_ascii=False, indent=2))
