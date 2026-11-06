from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
ARMS = ['R0', 'R1', 'R2', 'R3']
TICKS = ['R0\n미제공', 'R1\n계획부터', 'R2\n작성부터', 'R3\n점검부터']
COLORS = ['#7A8491', '#4C78A8', '#BE8748', '#278578']
X = np.arange(4)

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

font_manager.fontManager.addfont('C:/Windows/Fonts/malgun.ttf')
font_manager.fontManager.addfont('C:/Windows/Fonts/malgunbd.ttf')
plt.rcParams.update({
    'font.family': 'Malgun Gothic',
    'font.size': 11,
    'axes.unicode_minus': False,
    'axes.linewidth': .7,
    'axes.labelcolor': '#303B46',
    'xtick.color': '#46515C',
    'ytick.color': '#46515C',
    'text.color': '#25323E',
    'savefig.facecolor': 'white',
})


def figure(title, ylabel):
    fig, ax = plt.subplots(figsize=(8, 5.6), dpi=300, facecolor='white')
    fig.subplots_adjust(left=.14, right=.97, top=.88, bottom=.24)
    ax.set_title(title, fontsize=15, pad=17)
    ax.set_ylabel(ylabel, fontsize=11, labelpad=11)
    ax.set_xticks(X, TICKS)
    ax.set_xlim(-.65, 3.65)
    ax.tick_params(axis='x', length=0, pad=9)
    ax.tick_params(axis='y', length=3, width=.7)
    for tick, color in zip(ax.get_xticklabels(), COLORS):
        tick.set_color(color)
    for side in ['top', 'right']:
        ax.spines[side].set_visible(False)
    for side in ['left', 'bottom']:
        ax.spines[side].set_color('#8B959F')
    ax.grid(axis='y', color='#E7EAEE', linewidth=.6)
    ax.set_axisbelow(True)
    return fig, ax


def save(fig, name):
    fig.savefig(OUT / name, dpi=300, metadata={
        'Source': '[LIBERA_최종] 2조_문규리, pp.9-11; verified experiment CSV aggregates',
        'Description': 'Four funds, ten independent synthetic scenarios, forty workflows per condition.',
    })
    plt.close(fig)


fig, ax = figure('근거 제공 단계별 과잉수렴 격차', '평균 과잉수렴 격차 G (%p)')
ax.set_ylim(-6, 4.5)
ax.set_yticks([-6, -4, -2, 0, 2, 4])
ax.axhline(0, color='#56616C', linewidth=.9)
ax.bar(X, G, width=.58, color=COLORS, zorder=3)
for x, val, color in zip(X, G, COLORS):
    ax.annotate(f'{val:+.2f}', (x, val), xytext=(0, 6 if val > 0 else -6),
                textcoords='offset points', ha='center',
                va='bottom' if val > 0 else 'top', fontsize=12, color=color)
save(fig, '01_convergence_gap.png')

fig, ax = figure('근거 제공 단계별 기대수익 손실', '모형상 월간 기대수익 손실 (bp)')
ax.set_ylim(0, 110)
ax.set_yticks(np.arange(0, 101, 20))
ax.bar(X, R, width=.58, color=COLORS, zorder=3)
baseline = ax.axhline(HOLD, color='#3E4852', linewidth=1.1,
                      linestyle=(0, (5, 3)), zorder=4,
                      label=f'기존 비중 유지 ({HOLD:.2f}bp)')
for x, val, color in zip(X, R, COLORS):
    ax.annotate(f'{val:.2f}', (x, val), xytext=(0, 6), textcoords='offset points',
                ha='center', va='bottom', fontsize=12, color=color)
fig.legend(handles=[baseline], loc='lower center', bbox_to_anchor=(.55, .04),
           frameon=False, fontsize=10, handlelength=3)
save(fig, '02_expected_return_loss.png')

fig, ax = figure('근거 제공 단계별 최종 배분 구성', '업무 흐름 비율 (%)')
ax.set_ylim(0, 116)
ax.set_yticks([0, 20, 40, 60, 80, 100])
path_colors = ['#455F78', '#A1B7C9', '#DEE5EB']
labels = ['원출력 유효\n기존 비중 유지', '정규화 후 유효\n실제 재배분', '실패 처리\n기존 비중 유지']
bottom = np.zeros(4)
for values, color, label, text_color in zip(
        [paths.raw_valid_percent.to_numpy(), paths.rescued_percent.to_numpy(), paths.fallback_percent.to_numpy()],
        path_colors, labels, ['white', '#243444', '#425466']):
    ax.bar(X, values, bottom=bottom, width=.58, color=color,
           edgecolor='white', linewidth=.8, label=label, zorder=3)
    for x, value, start in zip(X, values, bottom):
        if value > 0:
            ax.text(x, start+value/2, f'{value:g}%', ha='center', va='center',
                    color=text_color, fontsize=10.5)
    bottom += values
valid = paths.raw_valid_percent.to_numpy() + paths.rescued_percent.to_numpy()
for x, value, color in zip(X, valid, COLORS):
    ax.text(x, 104, f'유효 {value:.1f}%', ha='center', va='bottom', fontsize=10.2, color=color)
handles, legend_labels = ax.get_legend_handles_labels()
fig.legend(handles, legend_labels, loc='lower center', bbox_to_anchor=(.55, .025),
           ncol=3, frameon=False, fontsize=9.5, handlelength=1.4,
           columnspacing=1.6, handletextpad=.6)
save(fig, '03_allocation_paths.png')

print('Saved exactly three independent PNG plots at 2400 x 1680 pixels.')
for f in sorted(OUT.glob('*.png')):
    print(f)
