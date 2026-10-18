"""Render existing local HTML for visual inspection; no model or GPU use."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CHROME = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
OUTPUT = ROOT / 'research/evidence/v481_delivery_20261019/visual'


def ref(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    if OUTPUT.exists():
        raise FileExistsError('Preserve prior visual evidence')
    if not CHROME.is_file():
        raise FileNotFoundError(CHROME)
    paper = ROOT / 'paper/LIBERA_텀페이퍼_초안_v4.8.1_20261019.html'
    plan = ROOT / 'plan/LIBERA_실험준비현황_v4.8.1_20261019.html'
    inputs = [ref(paper), ref(plan)]
    OUTPUT.mkdir(parents=True)
    captures = []
    for name, path, fragment, size in [
        ('paper_top', paper, '', '1440,1100'),
        ('paper_results', paper, '#readiness', '1440,1600'),
        ('paper_implications', paper, '#implications', '1440,1100'),
        ('plan_mobile', plan, '', '430,1800'),
    ]:
        image = OUTPUT / (name + '.png')
        profile = ROOT / 'tmp/browser_profiles/v481_20261019' / name
        command = [str(CHROME), '--headless', '--disable-gpu', '--no-first-run',
                   '--no-default-browser-check', '--hide-scrollbars',
                   '--force-device-scale-factor=1', '--run-all-compositor-stages-before-draw',
                   '--virtual-time-budget=3000', '--window-size=' + size,
                   '--user-data-dir=' + str(profile), '--screenshot=' + str(image),
                   path.as_uri() + fragment]
        result = subprocess.run(command, capture_output=True, timeout=60,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        (OUTPUT / (name + '.stdout.bin')).write_bytes(result.stdout)
        (OUTPUT / (name + '.stderr.bin')).write_bytes(result.stderr)
        if result.returncode or not image.is_file():
            raise RuntimeError('Rendering failed: ' + name)
        captures.append({'name': name, 'input': ref(path), 'fragment': fragment,
                         'viewport': size, 'output': ref(image), 'returncode': result.returncode})
    if inputs != [ref(paper), ref(plan)]:
        raise RuntimeError('Documents changed during rendering')
    receipt = {'at_utc': datetime.now(timezone.utc).isoformat(), 'inputs': inputs,
               'captures': captures, 'renderer': ref(Path(__file__)),
               'model_calls': 0, 'visual_review_completed': False,
               'scope': 'Capture only. Inspect the actual images separately.'}
    (OUTPUT / 'capture_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(OUTPUT), 'captures': len(captures)}))


if __name__ == '__main__':
    main()
