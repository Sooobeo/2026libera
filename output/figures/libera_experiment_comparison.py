from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib import font_manager
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ARMS = ['R0', 'R1', 'R2', 'R3']
CONDITIONS = ['미제공', '계획부터', '작성부터', '점검부터']
COLORS = ['#687789', '#5374B1', '#AE793A', '#187A73']
INK = '#172B42'
MUTED = '#607087'
GRID = '#E6EBF1'

summary = pd.read_csv(ROOT / 'research/paper_final_20261029/arm_summary.csv').set_index('arm').loc[ARMS]
observations = pd.read_csv(ROOT / 'paper/assets_20261029/figure2_distance_gap_regret.csv')
paths = pd.read_csv(ROOT / 'paper/assets_20261029/figure1_validity_by_timing.csv').set_index('arm').loc[ARMS]

# Confirm the figure reproduces both independent aggregation sources.
means = observations.groupby('arm')[['G_percentage_points', 'R_monthly_basis_points']].mean().loc[ARMS]
assert np.allclose(means.G_percentage_points, summary.G_full * 100)
assert np.allclose(means.R_monthly_basis_points, summary.R_full * 10000)
assert (paths.n == 40).all()
assert (paths.raw_valid + paths.rescued + paths.fallback == paths.n).all()
assert np.array_equal(paths.raw_valid, summary.raw_valid)
assert np.array_equal(paths.rescued, summary.rescued)
assert np.array_equal(paths.fallback, summary.fallback)
assert np.array_equal(summary.raw_equal_h_1e12, summary.raw_valid)
assert (summary.effective_equal_h_1e12 + summary.rescued == summary.trajectories).all()
assert summary.independent_scenarios.eq(10).all()

g = means.G_percentage_points.to_numpy()
regret = means.R_monthly_basis_points.to_numpy()
hold_regret = float(summary.hold_h_R_full.iloc[0] * 10000)
raw = paths.raw_valid_percent.to_numpy()
rescued = paths.rescued_percent.to_numpy()
fallback = paths.fallback_percent.to_numpy()
valid = raw + rescued
hold_percent = 100 * summary.effective_equal_h_1e12.sum() / summary.trajectories.sum()
change_percent = 100 - hold_percent

font_manager.fontManager.addfont('C:/Windows/Fonts/malgun.ttf')
font_manager.fontManager.addfont('C:/Windows/Fonts/malgunbd.ttf')
plt.rcParams.update({
    'font.family': 'Malgun Gothic',
    'axes.unicode_minus': False,
    'text.color': INK,
    'axes.labelcolor': MUTED,
    'xtick.color': MUTED,
    'ytick.color': MUTED,
    'svg.fonttype': 'path',
    'savefig.facecolor': '#F3F6FA',
})

fig = plt.figure(figsize=(16, 9), dpi=240, facecolor='#F3F6FA')

def text(x, y, value, size=12, color=INK, weight='normal', **kw):
    return fig.text(x, y, value, fontsize=size, color=color,
                    fontweight=weight, ha=kw.pop('ha', 'left'),
                    va=kw.pop('va', 'center'), **kw)

def box(x, y, w, h, color, edge='none', radius=.012, z=-5):
    patch = FancyBboxPatch((x, y), w, h,
                          boxstyle=f'round,pad=0,rounding_size={radius}',
                          transform=fig.transFigure, facecolor=color,
                          edgecolor=edge, linewidth=.8, zorder=z)
    fig.add_artist(patch)
    return patch

def style_axis(ax, ticks, ylim):
    ax.set_facecolor('white')
    ax.set_xlim(-.62, 3.62)
    ax.set_ylim(*ylim)
    ax.set_yticks(ticks)
    ax.grid(axis='y', color=GRID, linewidth=.7, zorder=0)
    ax.set_axisbelow(True)
    ax.axvspan(2.55, 3.45, facecolor='#EDF7F5', zorder=-1)
    for side in ['top', 'right', 'left']:
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color('#DDE4EC')
    ax.tick_params(axis='both', length=0)
    ax.tick_params(axis='y', labelsize=9, pad=7)
    ax.set_xticks(np.arange(4), [f'{a}\n{c}' for a, c in zip(ARMS, CONDITIONS)])
    ax.tick_params(axis='x', labelsize=10.3, pad=12)
    for label, color in zip(ax.get_xticklabels(), COLORS):
        label.set_color(color)
        label.set_fontweight('bold')

text(.04, .952, 'LIBERA  /  실험결과 비교', size=11, color=MUTED, weight='bold')
text(.04, .902, '근거 제공의 효과는 ‘차이·품질·생성 경로’를 함께 봐야 한다',
     size=25, weight='bold')
text(.04, .856, '동일 모델 · 4개 펀드 · 10개 합성 상황 · 총 160개 업무 흐름',
     size=11.5, color=MUTED)
box(.842, .842, .119, .032, '#E1F1ED', radius=.007, z=-1)
text(.9015, .858, 'R3  후기 제공 강조', size=10.2, color=COLORS[3], weight='bold', ha='center')

card_x = [.035, .352, .669]
card_w = .296
for x in card_x:
    box(x, .299, card_w, .516, 'white', edge='#E3E9F0')

# 1. Signed excess convergence: zero is a reference, not a quality optimum.
x = card_x[0]
text(x + .019, .776, '① 펀드 간 차이는 어떻게 달라졌나', size=15.1, weight='bold')
text(x + .019, .742, '평균 과잉수렴 격차 G  (%p)', size=10.5, color=MUTED)
ax = fig.add_axes([x + .036, .442, card_w - .054, .245])
style_axis(ax, [-6, -3, 0, 3, 6], (-6.8, 6.2))
ax.axhspan(0, 6.2, color='#FCF5F0', zorder=-2)
ax.axhline(0, color='#778698', linewidth=1.05)
ax.bar(np.arange(4), g, width=.55, color=COLORS, zorder=3)
for i, val in enumerate(g):
    ax.text(i, val + (.38 if val > 0 else -.38), f'{val:+.2f}',
            ha='center', va='bottom' if val > 0 else 'top', fontsize=13,
            color=COLORS[i], fontweight='bold')
ax.text(-.56, 5.48, '+  필요한 차이 축소', fontsize=9.5, color='#9A6847', va='center')
text(x + .019, .354, 'R1·R2: 평균적으로 과잉수렴', size=12.2, weight='bold')
text(x + .019, .322, '음수도 ‘더 적절한 차이’를 뜻하지는 않음', size=10.1, color=MUTED)

# 2. Dot plot uses a restricted axis without truncating bars.
x = card_x[1]
text(x + .019, .776, '② 기대수익 손실은 줄었나', size=15.1, weight='bold')
text(x + .019, .742, '월간 모형상 기대수익 손실  (bp)  ·  낮을수록 좋음', size=10.0, color=MUTED)
ax = fig.add_axes([x + .036, .442, card_w - .054, .245])
style_axis(ax, [85, 90, 95, 100], (84, 103.2))
ax.axhline(hold_regret, color='#8C9BAD', linewidth=1, linestyle=(0, (4, 3)), zorder=1)
for i, val in enumerate(regret):
    ax.plot([i, i], [hold_regret, val], color=COLORS[i], linewidth=2.2, alpha=.35, zorder=2)
    ax.scatter(i, val, s=104, color=COLORS[i], edgecolors='white', linewidths=1, zorder=4)
    ax.annotate(f'{val:.2f}', (i, val), xytext=(0, 11), textcoords='offset points',
                ha='center', fontsize=13, color=COLORS[i], fontweight='bold')
ax.text(-.53, 85.6, f'기존 비중 유지  {hold_regret:.2f}', fontsize=9.4, color=MUTED,
        bbox=dict(facecolor='white', edgecolor='none', pad=1))
text(x + .019, .354, f'R3 손실: 미제공보다 +{regret[3]-regret[0]:.2f}bp', size=12.2, weight='bold')
text(x + .019, .322, '후기 제공에서도 평균 손실 개선은 확인 못 함', size=10.1, color=MUTED)

# 3. Three mutually exclusive final-output paths, not three investment strategies.
x = card_x[2]
text(x + .019, .776, '③ 최종 배분은 어떻게 만들어졌나', size=15.1, weight='bold')
text(x + .019, .742, '최종 제안의 처리 경로  (%)  ·  위 숫자는 유효율', size=10.0, color=MUTED)
path_colors = ['#324F70', '#93AEC9', '#E2E7ED']
legend_items = [('원출력 유효', path_colors[0]), ('정규화 후 유효', path_colors[1]), ('실패·유지', path_colors[2])]
for lx, (label, color) in zip([x+.019, x+.104, x+.211], legend_items):
    fig.add_artist(Rectangle((lx, .704), .009, .010, transform=fig.transFigure,
                             facecolor=color, edgecolor='none'))
    text(lx+.013, .709, label, size=8.8, color=MUTED)
ax = fig.add_axes([x + .036, .442, card_w - .054, .245])
style_axis(ax, [0, 50, 100], (0, 119))
bottom = np.zeros(4)
for values, color, label_color in zip([raw, rescued, fallback], path_colors, ['white', INK, '#52647B']):
    ax.bar(np.arange(4), values, bottom=bottom, width=.58, color=color,
           edgecolor='white', linewidth=.8, zorder=3)
    for i, (v, b) in enumerate(zip(values, bottom)):
        if v > 0:
            label = f'{v:.1f}'.rstrip('0').rstrip('.') + '%'
            ax.text(i, b+v/2, label, ha='center', va='center', fontsize=9.6,
                    fontweight='bold', color=label_color, zorder=4)
    bottom += values
for i, val in enumerate(valid):
    ax.text(i, 108.2, f'{val:.1f}%', ha='center', va='center', fontsize=11.5,
            fontweight='bold', color=COLORS[i])
text(x + .019, .354, 'R3 유효율 62.5%로 최고', size=12.2, weight='bold')
text(x + .019, .322, '원출력 유효안도 모두 기존 비중을 유지', size=10.1, color=MUTED)

# Main interpretation and the explicitly untested design proposal.
box(.035, .089, .93, .174, '#152D45', radius=.012, z=-2)
text(.055, .239, '세 결과를 함께 읽으면', size=10.2, color='#ADC1D3', weight='bold')
text(.055, .202, '유효율 상승 ≠ 판단 품질 개선', size=21, color='white', weight='bold')
text(.579, .218, f'전체 배분의 {hold_percent:.1f}%는 기존 비중 유지',
     size=15.2, color='#B6DED5', weight='bold')
text(.579, .184, f'실제 재배분 {change_percent:.1f}%는 모두 외부 정규화 후 발생',
     size=10.0, color='#CFDAE6')
fig.add_artist(Rectangle((.055, .159), .889, .0007, transform=fig.transFigure,
                         facecolor='#3A5269', edgecolor='none'))
text(.055, .127, '보완 방향', size=11, color='#ADC1D3', weight='bold')
text(.126, .127, '근거 채택 기준 설정  →  전제가 바뀌면 배분 재검토',
     size=13.8, color='white', weight='bold')
text(.944, .101, '보완책의 효과는 후속 실험에서 검증', size=9.0, color='#ADC1D3', ha='right')

text(.04, .057,
     '주: 조건별 40개 업무 흐름. 독립 합성 상황 10개의 탐색적 비교이며, 기대수익 손실은 실현수익률이 아닌 모형상 기회비용이다.',
     size=8.4, color=MUTED)
text(.04, .033,
     '출처: [LIBERA_최종] 2조_문규리, 표 1·그림 2 및 본문(pp.9–11). 최종 집계 원자료와 대조하여 재작성.',
     size=8.2, color=MUTED)

fig.savefig(OUT / 'libera_experiment_comparison.png', dpi=240)
fig.savefig(OUT / 'libera_experiment_comparison.svg')
plt.close(fig)

with Image.open(OUT / 'libera_experiment_comparison.png') as im:
    assert im.size == (3840, 2160)
    im.resize((1920, 1080), Image.Resampling.LANCZOS).save(OUT / 'libera_experiment_comparison_preview.png')

export = pd.DataFrame({
    'condition': ARMS,
    'first_evidence_stage': CONDITIONS,
    'excess_convergence_gap_pp': g,
    'monthly_expected_return_regret_bp': regret,
    'raw_valid_percent': raw,
    'normalized_valid_percent': rescued,
    'fallback_hold_percent': fallback,
    'valid_percent': valid,
})
export.to_csv(OUT / 'libera_experiment_comparison_data.csv', index=False, encoding='utf-8-sig')
print(json.dumps({
    'image': str(OUT / 'libera_experiment_comparison.png'),
    'size': [3840, 2160],
    'G': np.round(g, 2).tolist(),
    'regret_bp': np.round(regret, 2).tolist(),
    'valid_percent': valid.tolist(),
    'hold_percent': round(hold_percent, 1),
    'hold_baseline_regret_bp': round(hold_regret, 2),
}, ensure_ascii=False, indent=2))
