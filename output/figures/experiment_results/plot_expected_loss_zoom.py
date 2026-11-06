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
COLORS = ['#7A8491', '#4C78A8', '#BE8748', '#278578']
summary = pd.read_csv(ROOT / 'research/paper_final_20261029/arm_summary.csv').set_index('arm').loc[ARMS]
observations = pd.read_csv(ROOT / 'paper/assets_20261029/figure2_distance_gap_regret.csv')
values = observations.groupby('arm').R_monthly_basis_points.mean().loc[ARMS].to_numpy()
assert np.allclose(values, summary.R_full.to_numpy() * 10000)
baseline_value = float(summary.hold_h_R_full.iloc[0] * 10000)

font_manager.fontManager.addfont('C:/Windows/Fonts/malgun.ttf')
plt.rcParams.update({'font.family': 'Malgun Gothic', 'font.size': 11,
                     'axes.unicode_minus': False, 'axes.linewidth': .7,
                     'text.color': '#25323E', 'axes.labelcolor': '#303B46',
                     'xtick.color': '#46515C', 'ytick.color': '#46515C'})
fig, ax = plt.subplots(figsize=(8, 5.6), dpi=300, facecolor='white')
fig.subplots_adjust(left=.14, right=.97, top=.88, bottom=.24)
ax.set_title('근거 제공 단계별 기대수익 손실', fontsize=15, pad=17)
ax.set_ylabel('모형상 월간 기대수익 손실 (bp)', fontsize=11, labelpad=11)
ax.set_xlim(-.65, 3.65)
ax.set_ylim(85, 102)
ax.set_yticks([85, 90, 95, 100, 102])
ax.set_xticks(np.arange(4), ['R0\n미제공', 'R1\n계획부터', 'R2\n작성부터', 'R3\n점검부터'])
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
ax.scatter(np.arange(4), values, s=130, c=COLORS, edgecolors='white', linewidths=1, zorder=4)
for x, value, color in zip(np.arange(4), values, COLORS):
    ax.annotate(f'{value:.2f}', (x, value), xytext=(0, 10), textcoords='offset points',
                ha='center', va='bottom', fontsize=12, color=color)
line = ax.axhline(baseline_value, color='#3E4852', linewidth=1.1,
                  linestyle=(0, (5, 3)), zorder=3,
                  label=f'기존 비중 유지 ({baseline_value:.2f}bp)')
fig.legend(handles=[line], loc='lower center', bbox_to_anchor=(.55, .04),
           frameon=False, fontsize=10, handlelength=3)
path = OUT / '02_expected_return_loss_zoom.png'
fig.savefig(path, dpi=300, metadata={
    'Source': '[LIBERA_최종] 2조_문규리, pp.9-11; verified experiment CSV aggregates',
    'Description': 'Same data, y-axis 85 to 102 bp, point plot.',
})
plt.close(fig)
print(path)
print('Values (bp):', np.round(values, 2).tolist())
