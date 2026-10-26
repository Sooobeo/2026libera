"""Reproducible print figures for the v5.2 manuscript.

Run with the managed Codex Python runtime. Values are read from the frozen
completed dataset; raw/model outputs are never changed by this script.
"""
from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import FancyBboxPatch
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "figures"
DATA = ROOT / "research/last_final_20261026/derived_allocation/completed_five_condition_dataset.json"
OUT.mkdir(parents=True, exist_ok=True)
font_manager.fontManager.addfont("C:/Windows/Fonts/malgun.ttf")
plt.rcParams.update({
    "font.family": ["Malgun Gothic", "DejaVu Sans"], "font.size": 9.4,
    "axes.titlesize": 10.5, "axes.labelsize": 9.4,
    "xtick.labelsize": 9.2, "ytick.labelsize": 9.2,
    "axes.unicode_minus": False, "svg.fonttype": "none",
    "savefig.facecolor": "white", "figure.facecolor": "white",
    "text.color": "#202a35", "axes.labelcolor": "#202a35",
    "xtick.color": "#202a35", "ytick.color": "#202a35",
})
D = json.loads(DATA.read_text(encoding="utf-8"))
CASES = D["case_order"]
NAMES = dict(zip(CASES, ["Fidelity E", "Fidelity L", "UBS E", "UBS L", "C"]))
SECTORS = ["10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60"]
SECTOR_NAMES = ["에너지", "소재", "산업재", "경기소비재", "필수소비재", "헬스케어", "금융", "정보기술", "커뮤니케이션 서비스", "유틸리티", "부동산"]
RECORDS = {(r["case_id"], r["stage"]): r for r in D["stage_records"]}
BLUE = "#315c7c"
MID = "#658096"
PALE = "#edf2f6"
GRID = "#d9e0e5"
CM = 1 / 2.54
MANIFEST = []


def row_for(case, stage, sector):
    return next(r for r in RECORDS[(case, stage)]["rows"] if r["sector_code"] == sector)


def final(case, stage, sector):
    return row_for(case, stage, sector)["final_units"] / 100


def raw(case, stage, sector):
    return float(Decimal(row_for(case, stage, sector)["raw_weight_exact_decimal"]) * 100)


def write_csv(name, headers, rows):
    path = OUT / f"{name}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    return path


def save(fig, name, title, caption, note, width, height, data_csv):
    # No tight bounding box: explicit physical dimensions remain reproducible.
    fig.savefig(OUT / f"{name}.png", dpi=600)
    fig.savefig(OUT / f"{name}.svg")
    plt.close(fig)
    MANIFEST.append({
        "id": name, "title": title, "caption": caption, "note": note,
        "png": str((OUT / f"{name}.png").resolve()),
        "svg": str((OUT / f"{name}.svg").resolve()),
        "width_cm": width, "height_cm": height,
        "data_csv": str(data_csv.resolve()),
        "source": str(DATA.relative_to(ROOT)),
    })


def heatmap(name, values, labels, difference=False):
    width, height = 16, 11.5
    fig = plt.figure(figsize=(width * CM, height * CM))
    ax = fig.add_axes([.285, .105, .55, .80])
    if difference:
        cmap = LinearSegmentedColormap.from_list("bluegray_diverging", ["#243f5c", "#f9fafb", "#80604b"])
        im = ax.imshow(values, cmap=cmap, norm=TwoSlopeNorm(vmin=-9, vcenter=0, vmax=9), aspect="auto")
    else:
        cmap = LinearSegmentedColormap.from_list("paper_blue", ["#f5f8fa", "#c3d5e3", "#739bb9", "#315c7c"])
        im = ax.imshow(values, cmap=cmap, vmin=0, vmax=45, aspect="auto")
    ax.set_xticks(range(len(labels)), labels)
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", length=0, pad=9)
    ax.set_yticks(range(11), SECTOR_NAMES)
    ax.tick_params(axis="y", length=0, pad=9)
    ax.set_xticks(np.arange(-.5, len(labels), 1), minor=True)
    ax.set_yticks(np.arange(-.5, 11, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.1)
    ax.tick_params(which="minor", bottom=False, left=False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for i in range(11):
        for j in range(len(labels)):
            v = values[i, j]
            color = "white" if (abs(v) > 5.6 if difference else v > 29) else "#1c2c39"
            label = f"{v:+.2f}" if difference else f"{v:.2f}"
            ax.text(j, i, label, ha="center", va="center", fontsize=9.8, color=color)
    cax = fig.add_axes([.86, .105, .025, .80])
    cb = fig.colorbar(im, cax=cax, ticks=[-9, -6, -3, 0, 3, 6, 9] if difference else [0, 10, 20, 30, 40, 45])
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=2, labelsize=9)
    fig.text(.88, .943, "차이 (%p)" if difference else "비중 (%)", fontsize=9.2, ha="center")
    fig.text(.285, .028, "최종안 F0 · 조건별 합계 100%" if not difference else "기관 자료 조건 F0 − 대조조건 C의 F0", fontsize=9.2)
    rows = [[code, kor] + [f"{values[i,j]:.2f}" for j in range(len(labels))] for i, (code, kor) in enumerate(zip(SECTORS, SECTOR_NAMES))]
    csv_path = write_csv(name, ["sector_code", "sector_name"] + labels, rows)
    if difference:
        save(fig, name, "대조조건 대비 산업별 최종 파생 비중 차이", "그림 A1. 대조조건 C 대비 산업별 최종 파생 비중 차이", "각 셀은 기관 자료 조건의 F0 파생 비중에서 C의 F0 파생 비중을 뺀 값(%p)이다. 발산 척도는 −9~+9%p로 대칭이며, 부호와 숫자를 함께 표시했다. 자료 조건의 순수 인과효과로 해석하지 않는다. 출처: E1.", width, height, csv_path)
    else:
        save(fig, name, "조건별 최종 산업배분", "그림 1. 다섯 조건의 최종 산업별 파생 비중", "모델이 제출한 원비중을 비례 정규화한 뒤 최대잔여법으로 0.01%p 단위에 맞춘 F0 파생 비중이다. 열별 합계는 100%이다. E는 기관 자료 초기 제공, L은 후기 제공, C는 기관 자료 미제공 조건이다. 동일한 0~45% 색상 척도를 적용했다. 출처: E1.", width, height, csv_path)


def distances():
    width, height = 16, 13
    fig = plt.figure(figsize=(width * CM, height * CM))
    axa = fig.add_axes([.42, .46, .53, .41])
    axb = fig.add_axes([.42, .105, .53, .245])
    comps = D["derived_comparisons"]
    groups = [("기관 간", "between_source", "o", BLUE), ("동일 기관 E–L", "within_source", "s", "#52626f"), ("C 대비", "shared_control", "D", "#7b6859")]
    plot_rows, csv_rows = [], []
    for group, key, marker, color in groups:
        for r in comps[key]:
            left, right = r["left"].split(":")[0], r["right"].split(":")[0]
            value = float(Decimal(r["total_variation_exact_decimal"]) * 100)
            plot_rows.append((f"{NAMES[left]} – {NAMES[right]}", value, marker, color, group))
            csv_rows.append(["A", group, r["left"], r["right"], f"{value:.2f}"])
    for ax in [axa, axb]:
        ax.set_xlim(-.2, 15)
        ax.set_xticks([0, 5, 10, 15])
        ax.set_axisbelow(True)
        ax.grid(axis="x", color=GRID, linewidth=.6)
        for side in ["top", "right", "left"]:
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#9daab5")
        ax.tick_params(axis="y", length=0, pad=7)
        ax.tick_params(axis="x", length=3)
    ys = np.arange(len(plot_rows))[::-1]
    for y, (label, value, marker, color, group) in zip(ys, plot_rows):
        axa.plot(value, y, marker=marker, ms=5.3, color=color, linestyle="none", zorder=3)
        axa.text(value + .33, y, f"{value:.2f}", va="center", fontsize=9.1)
    axa.set_yticks(ys, [r[0] for r in plot_rows])
    axa.set_ylim(-.6, 7.6)
    for split in [5.5, 3.5]:
        axa.axhline(split, color=GRID, lw=.7)
    # Group names occupy the leftmost column and do not rely on marker colour.
    for y, group in [(6.5, "기관 간"), (4.5, "동일 기관\nE–L"), (1.5, "C 대비")]:
        axa.text(-11.2, y, group, va="center", ha="left", fontsize=9.2, color="#4b5b68", clip_on=False)
    fig.text(.035, .948, "A  최종안 간 배분 거리", fontsize=10.5, weight="bold")
    fig.text(.035, .385, "B  각 조건의 초안 → 최종안 수정거리", fontsize=10.5, weight="bold")
    for i, r in enumerate(comps["own_D0_F0"]):
        value = float(Decimal(r["total_variation_exact_decimal"]) * 100)
        y = 4 - i
        axb.plot(value, y, marker="o", ms=5.3, color=BLUE, linestyle="none", zorder=3)
        axb.text(value + .33, y, f"{value:.2f}", va="center", fontsize=9.1)
        csv_rows.append(["B", "D0→F0", r["left"], r["right"], f"{value:.2f}"])
    axb.set_yticks(range(4, -1, -1), list(NAMES.values()))
    axb.set_ylim(-.6, 4.6)
    axb.set_xlabel("배분 거리 (%)", labelpad=6)
    axa.set_xlabel("배분 거리 (%)", labelpad=4)
    csv_path = write_csv("fig02_distances", ["panel", "comparison_group", "left", "right", "allocation_distance_percent"], csv_rows)
    save(fig, "fig02_distances", "최종 배분의 차이와 초안 이후 수정량", "그림 2. 최종안 간 배분 거리와 조건별 수정거리", "A는 F0 파생 배분 간 8개 비교, B는 각 조건의 D0와 F0 파생 배분 간 비교이다. 거리는 총변동거리 ½Σ|wᵢ−vᵢ|를 백분율로 표시했다. 두 패널은 동일한 0~15% 눈금을 사용한다. 이는 탐색적 사례의 산출물 차이이며, 독립 반복에 기초한 효과 추정치가 아니다. 출처: E1.", width, height, csv_path)


def evidence():
    width, height = 16, 9.3
    fig = plt.figure(figsize=(width * CM, height * CM))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    headers = ["제공 근거", "모델 출력 요지", "수치·원문 대조"]
    x0s = [.025, .36, .695]
    for x, h in zip(x0s, headers):
        ax.text(x + .012, .955, h, fontsize=10.4, weight="bold", va="top")
    # Print-oriented comparison matrix: shared rules replace individual cards.
    for y in [.87, .61, .35, .09]:
        ax.plot([.025, .98], [y, y], color="#b7c3cc" if y == .87 else GRID, lw=.7)
    for x in [.338, .673]:
        ax.plot([x, x], [.09, .87], color=GRID, lw=.55)
    cells = [
        ["① 등급 해석 · UBS L\n경기소비재·유틸리티의\n제공 등급: Attractive",
         "산업행 요약: Attractive\n종합 설명: 두 산업을\nNeutral로 취급",
         "산업행 요약은 일치\n종합 설명에서는\n등급 해석이 불일치"],
        ["② 수익률 · 공유 D0\n정보기술의 과거\n누적수익률: 약 14.99%",
         "정보기술의 과거\n누적수익률을\n149.92%로 서술",
         "입력 대비 약 10배\nFidelity L·UBS L·C에\n동일 초안 내용의 오류"],
        ["③ 설명과 선택 · UBS L\n초안 정보기술\n원비중: 38%",
         "최종 설명에서\n정보기술 비중을\n늘렸다는 취지로 서술",
         "최종 원비중: 35%\n실제 변화: −3%p\n설명 방향과 모순"],
    ]
    csv_rows = []
    for i, (row, y) in enumerate(zip(cells, [.825, .565, .305])):
        for j, (x, text) in enumerate(zip(x0s, row)):
            ax.text(x + .012, y, text, va="top", ha="left", fontsize=9.4, linespacing=1.5)
        csv_rows.append([i+1, row[0].replace("\n", " "), row[1].replace("\n", " "), row[2].replace("\n", " ")])
    csv_path = OUT / "fig03_evidence.csv"
    if not csv_path.exists():
        write_csv("fig03_evidence", ["case", "provided_evidence", "model_output_summary", "comparison_result"], csv_rows)
    save(fig, "fig03_evidence", "근거·설명·선택의 불일치 사례", "그림 3. 제공 근거, 모델의 설명, 실제 선택을 대조한 사례", "가운데 열은 직접인용이 아닌 출력 요지다. 첫째 사례는 산업행 등급 요약의 일치와 종합 설명의 불일치를 구분한다. 둘째 사례의 세 조건은 동일한 초안 내용에서 오류를 공유하므로 세 개의 독립 오류로 세지 않는다. 셋째 사례는 정규화 전 원비중을 대조한다. 사례만으로 전체 오류율을 계산하지 않는다. 출처: E2·E4 및 E1.", width, height, csv_path)


def normalization():
    width, height = 16, 9.5
    fig = plt.figure(figsize=(width * CM, height * CM))
    axes = [fig.add_axes([.105, .245, .355, .59]), fig.add_axes([.60, .245, .355, .59])]
    case = CASES[1]
    a = [raw(case, s, "45") for s in ["D0", "F0"]]
    b = [final(case, s, "45") for s in ["D0", "F0"]]
    for ax, vals, title, color in zip(axes, [a, b], ["A  모델의 원비중", "B  외부 계산의 파생 비중"], ["#54626d", BLUE]):
        ax.set_ylim(34, 43)
        ax.set_xlim(-.25, 1.25)
        ax.set_yticks([34, 36, 38, 40, 42])
        ax.set_xticks([0, 1], ["초안 D0", "최종안 F0"])
        ax.grid(axis="y", color=GRID, lw=.6)
        ax.set_axisbelow(True)
        ax.plot([0, 1], vals, color=color, lw=1.8, marker="o", ms=6)
        for x, val in enumerate(vals):
            ax.annotate(f"{val:.0f}%" if ax is axes[0] else f"{val:.2f}%", (x, val), xytext=(0, 9), textcoords="offset points", ha="center", fontsize=10.2, weight="bold")
        for side in ["top", "right"]:
            ax.spines[side].set_visible(False)
        for side in ["left", "bottom"]:
            ax.spines[side].set_color("#9daab5")
        ax.set_title(title, loc="left", pad=13, fontsize=10.2, weight="bold")
        ax.tick_params(axis="x", length=0, pad=8)
        ax.tick_params(axis="y", length=3)
    axes[0].set_ylabel("정보기술 비중 (%)", labelpad=6)
    axes[0].text(.5, 34.65, "−2%p", ha="center", color="#465865", weight="bold", fontsize=11)
    axes[1].text(.5, 34.65, "+3.65%p", ha="center", color=BLUE, weight="bold", fontsize=11)
    fig.text(.105, .115, "Fidelity L · 원합계: D0 102% → F0 88%", fontsize=9.6)
    fig.text(.105, .042, "원비중의 감소가 정규화 뒤 증가로 바뀌는 사후 진단 사례", fontsize=9.3, color="#4b5b68")
    csv_path = write_csv("fig04_normalization", ["case", "stage", "sector_code", "raw_percent", "derived_percent", "raw_total_percent"], [[NAMES[case], s, "45", f"{raw(case,s,'45'):.2f}", f"{final(case,s,'45'):.2f}", str(Decimal(RECORDS[(case,s)]["raw_sum_exact_decimal"]) * 100)] for s in ["D0", "F0"]])
    save(fig, "fig04_normalization", "정규화에 따른 증감 방향의 역전", "그림 4. Fidelity L 정보기술 비중의 정규화 전후 방향 역전", "두 패널은 같은 34~43% 세로축 범위를 사용한다. 원비중은 38%에서 36%로 2%p 감소했지만, 원합계가 102%에서 88%로 줄어들어 파생 비중은 37.26%에서 40.91%로 3.65%p 증가했다. 파생 비중의 증가는 외부 계산에 따른 사후 진단이며 모델의 선호 증가를 뜻하지 않는다. 출처: E1.", width, height, csv_path)


def verify_numbers():
    with (OUT / "fig01_allocations.csv").open(encoding="utf-8-sig") as f:
        allocation_rows = list(csv.DictReader(f))
    assert len(allocation_rows) == 11
    checked, pairs, diffs = 0, 0, 0
    sums = {}
    for case, name in NAMES.items():
        rec = RECORDS[(case, "F0")]
        sums[name] = sum(r["final_units"] for r in rec["rows"])
        assert sums[name] == 10000
        for r in rec["rows"]:
            item = next(x for x in allocation_rows if x["sector_code"] == r["sector_code"])
            assert Decimal(item[name]) == Decimal(r["final_units"]) / 100
            checked += 1
    for group in D["derived_comparisons"].values():
        for c in group:
            lc, ls = c["left"].split(":")
            rc, rs = c["right"].split(":")
            left = {r["sector_code"]: r["final_units"] for r in RECORDS[(lc, ls)]["rows"]}
            right = {r["sector_code"]: r["final_units"] for r in RECORDS[(rc, rs)]["rows"]}
            expected = Decimal(sum(abs(left[k] - right[k]) for k in left)) / 20000
            assert expected == Decimal(c["total_variation_exact_decimal"])
            pairs += 1
    with (OUT / "figA01_control_difference.csv").open(encoding="utf-8-sig") as f:
        difference_rows = list(csv.DictReader(f))
    for item in difference_rows:
        sector = item["sector_code"]
        control = row_for(CASES[4], "F0", sector)["final_units"]
        for case in CASES[:4]:
            expected = Decimal(row_for(case, "F0", sector)["final_units"] - control) / 100
            assert Decimal(item[NAMES[case]]) == expected
            diffs += 1
    dimensions = {}
    for m in MANIFEST:
        with Image.open(m["png"]) as im:
            dimensions[m["id"]] = {"pixels": im.size, "dpi": im.info.get("dpi")}
    report = {
        "allocation_cells_checked": checked,
        "comparison_distances_recomputed": pairs,
        "control_difference_cells_checked": diffs,
        "final_column_units": sums,
        "figure_dimensions": dimensions,
        "minimum_plot_font_pt": 9.0,
        "source_data_modified": False,
    }
    (OUT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    values = np.array([[final(c, "F0", s) for c in CASES] for s in SECTORS])
    heatmap("fig01_allocations", values, list(NAMES.values()))
    distances()
    evidence()
    normalization()
    heatmap("figA01_control_difference", values[:, :4] - values[:, 4:5], list(NAMES.values())[:4], difference=True)
    (OUT / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=2), encoding="utf-8")
    verify_numbers()
    print(json.dumps({"output_dir": str(OUT), "figures": [m["id"] for m in MANIFEST]}, ensure_ascii=True))
