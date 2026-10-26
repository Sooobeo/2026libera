"""Use the established managed renderer with the revised manuscript paths."""
from pathlib import Path
import importlib.util

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
spec = importlib.util.spec_from_file_location('libera_render', ROOT / 'research/document_v520_20261026/render_and_raster.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
renderer.WORK = WORK
renderer.DOCX = ROOT / 'paper/LIBERA_소논문_문제제기개선_v5.3_20261026.docx'
raise SystemExit(renderer.main())
