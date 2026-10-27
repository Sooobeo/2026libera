"""Temporary loopback-only UI for moving this task's artifacts through a browser.

No remote browser state, credentials or external network endpoints are accessed.
Only a prepared bundle is served; received archives are new-only in a task folder.
"""
import argparse
import base64
import hashlib
import html
import json
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8769)
    args = parser.parse_args()
    folder = args.directory.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    origin = f'http://127.0.0.1:{args.port}'

    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, content):
            raw = content.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.headers.get('Host') != f'127.0.0.1:{args.port}':
                return self.reply(403, 'Loopback host required')
            bundle_routes = {'/bundle': 'bundle.tar.gz', '/latency-bundle': 'latency_bundle.tar.gz',
                             '/real-input-bundle': 'real_input_bundle.tar.gz'}
            if self.path in bundle_routes:
                bundle = folder / bundle_routes[self.path]
                if not bundle.is_file():
                    return self.reply(404, 'Bundle not prepared')
                raw = bundle.read_bytes()
                return self.reply(200, '<h1>LIBERA task bundle</h1><p id="sha256">' + hashlib.sha256(raw).hexdigest() + '</p><pre id="payload">' + base64.b64encode(raw).decode('ascii') + '</pre>')
            if self.path != '/':
                return self.reply(404, 'Not found')
            self.reply(200, '<!doctype html><meta charset="utf-8"><title>LIBERA artifact transfer</title><h1>LIBERA artifact transfer</h1><p>Temporary loopback transfer of experiment files.</p><form method="post" action="/"><input type="hidden" name="token" value="' + token + '"><p><label>Artifact name <input name="name" required></label></p><p><label>Hex payload <textarea name="hex" rows="12" cols="90" required></textarea></label></p><button type="submit">Save artifact</button></form>')

        def do_POST(self):
            try:
                if self.path != '/' or self.headers.get('Host') != f'127.0.0.1:{args.port}' or self.headers.get('Origin') != origin:
                    raise ValueError('Same loopback origin required')
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 16_000_000:
                    raise ValueError('Invalid payload size')
                fields = parse_qs(self.rfile.read(size).decode('utf-8'), strict_parsing=True)
                if not secrets.compare_digest(fields.get('token', [''])[0], token):
                    raise ValueError('Invalid form token')
                name = fields.get('name', [''])[0]
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.(?:tar\.gz|png|jpg|txt|html|json|part[0-9]{3})', name):
                    raise ValueError('A task archive or screenshot filename is required')
                encoded = fields.get('hex', [''])[0]
                if not re.fullmatch(r'[0-9a-fA-F]+', encoded) or len(encoded) % 2:
                    raise ValueError('Invalid hex payload')
                raw = bytes.fromhex(encoded)
                chunk = bool(re.search(r'\.part[0-9]{3}$', name))
                expected = (b'\x89PNG\r\n\x1a\n' if name.endswith('.png') else
                            b'\xff\xd8\xff' if name.endswith('.jpg') else b'\x1f\x8b')
                if not chunk and not name.endswith(('.txt','.html','.json')) and not raw.startswith(expected):
                    raise ValueError('File signature does not match the task artifact type')
                target = folder / name
                with target.open('xb') as out:
                    out.write(raw)
                receipt = {'name': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                (folder / (name + '.receipt.json')).write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
                self.reply(200, '<h1>Saved</h1><pre>' + html.escape(json.dumps(receipt, indent=2)) + '</pre><a href="/">Transfer another artifact</a>')
            except Exception as exc:
                self.reply(400, '<h1>Not saved</h1><p>' + html.escape(str(exc)) + '</p>')

        def log_message(self, fmt, *values):
            print(fmt % values, flush=True)

    print(f'LIBERA artifact transfer UI: {origin}/', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
