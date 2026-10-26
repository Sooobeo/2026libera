"""Print-ready proposed-workflow diagram. This is a design, not a result."""
from pathlib import Path
import json
import hashlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image

BASE = Path(__file__).resolve().parent
OUT = BASE / "figures"
OUT.mkdir(parents=True, exist_ok=True)
font_manager.fontManager.addfont("C:/Windows/Fonts/malgun.ttf")
plt.rcParams.update({
    "font.family": ["Malgun Gothic", "DejaVu Sans"],
    "font.size": 9.1,
    "svg.fonttype": "none",
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    "text.color": "#202a35",
    "axes.unicode_minus": False,
})
BLUE = "#315c7c"
GREY = "#9caab5"
LIGHT = "#d7dee3"

fig, ax = plt.subplots(figsize=(16 / 2.54, 6.5 / 2.54))
fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

ax.text(.5, .935, "Workflow RAG 대응 설계", ha="center", va="center",
        fontsize=11, fontweight="bold")
ax.text(.5, .827, "입력: 펀드별 적격 문서에서 미리 고정한 같은 검색 근거",
        ha="center", va="center", fontsize=9.1)
ax.plot([.035, .965], [.755, .755], color=LIGHT, lw=.7)

centers = [.175, .5, .825]
stages = [
    ("① 계획", "시장·펀드조건 해석", "R1: 이 단계에서 최초 제공"),
    ("② 배분안 구성", "목표비중·변경근거 작성", "R2: 이 단계에서 최초 제공"),
    ("③ 점검·수정", "근거·제약·실제비중 대조", "R3: 이 단계에서 최초 제공"),
]
for x, (title, detail, condition) in zip(centers, stages):
    ax.text(x, .653, title, ha="center", va="center", fontsize=10.1,
            fontweight="bold")
    ax.text(x, .533, detail, ha="center", va="center", fontsize=9.1)
    ax.text(x, .400, condition, ha="center", va="center", fontsize=9.0,
            color=BLUE)
for start, end in [(.295, .365), (.630, .700)]:
    ax.annotate("", xy=(end, .647), xytext=(start, .647),
                arrowprops={"arrowstyle": "->", "color": BLUE,
                            "lw": 1, "mutation_scale": 9})

# These are alternative first-injection conditions, with subsequent retention.
ax.annotate("", xy=(.92, .280), xytext=(.08, .280),
            arrowprops={"arrowstyle": "->", "color": GREY,
                        "lw": .8, "mutation_scale": 8})
ax.text(.5, .280, "한 번 제공한 근거는 이후 단계에서도 유지",
        ha="center", va="center", fontsize=9.1,
        bbox={"facecolor": "white", "edgecolor": "none", "pad": 2.0})
ax.plot([.035, .965], [.185, .185], color=LIGHT, lw=.7)
ax.text(.5, .095, "통제조건  R0: 추가 근거 없음  |  FULL: 전체 적격 원문 최초 제공",
        ha="center", va="center", fontsize=9.0)

stem = "fig05_workflow_design"
png, svg = OUT / f"{stem}.png", OUT / f"{stem}.svg"
fig.savefig(png, dpi=600)
fig.savefig(svg)
plt.close(fig)

entry = {
    "id": stem,
    "title": "같은 검색 근거의 최초 제공 시점을 비교하는 Workflow RAG 대응 설계",
    "caption": "그림 5. 본실험의 관측을 반영한 Workflow RAG 대응 설계",
    "note": "R1·R2·R3는 펀드별 적격 문서에서 미리 고정한 같은 검색 근거의 최초 제공 단계만 달리하는 대안 조건이며, 한 번 제공한 근거는 이후 단계에서도 유지한다. R0는 추가 근거 없음, FULL은 전체 적격 원문 최초 제공 조건이다. 본실험의 관측을 반영한 대응 설계이며, RAG 조건의 검색·완화효과 비교는 후속 검증 대상이다. 현재 본실험의 E·L·C와 R0·R1·R2·R3·FULL은 구분한다.",
    "png": str(png.resolve()),
    "svg": str(svg.resolve()),
    "width_cm": 16,
    "height_cm": 6.5,
    "source": "greengreen (1).pdf의 Workflow RAG 본실험 구상 및 research/document_v540_20261026/concept_audit.md",
}
(OUT / "manifest.json").write_text(json.dumps([entry], ensure_ascii=False, indent=2), encoding="utf-8")
with Image.open(png) as im:
    receipt = {
        "id": stem, "pixel_dimensions": list(im.size),
        "dpi": list(im.info.get("dpi", [])),
        "minimum_text_pt": 9.0,
        "png_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
        "svg_text_nodes": svg.read_text(encoding="utf-8").count("<text"),
    }
(OUT / "verification.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(receipt, ensure_ascii=False))
