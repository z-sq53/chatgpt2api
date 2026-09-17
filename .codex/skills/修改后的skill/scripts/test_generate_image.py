import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a6uoAAAAASUVORK5CYII=')
SCRIPT = Path(__file__).with_name('generate_image.py')


class ImageScriptTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                data = json.dumps({'data': [{'b64_json': base64.b64encode(PNG).decode()}]}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.temp.cleanup()

    def run_script(self, *args):
        env = {**os.environ, 'CHATGPT2API_API_KEY': 'test-only-key', 'PYTHONUTF8': '1'}
        return subprocess.run([sys.executable, str(SCRIPT), '--base-url', f'http://127.0.0.1:{self.server.server_port}/v1',
                               '--output-dir', str(self.root / 'out'), '--prompt', '保留产品，改变背景', *args],
                              env=env, capture_output=True, text=True, encoding='utf-8', timeout=10)

    def test_reference_bytes_and_order_reach_edit_endpoint(self):
        first = self.root / '产品 正面.png'
        second = self.root / '产品侧面.png'
        first.write_bytes(PNG)
        second.write_bytes(PNG)
        result = self.run_script('--image', str(first), '--image', str(second))
        self.assertEqual(result.returncode, 0, result.stderr)
        endpoint, payload = self.requests[0]
        self.assertEqual(endpoint, '/v1/images/edits')
        self.assertEqual([i['filename'] for i in payload['images']], [first.name, second.name])
        for item in payload['images']:
            self.assertEqual(base64.b64decode(item['b64_json']), PNG)
            self.assertEqual(item['mime_type'], 'image/png')
        output = json.loads(result.stdout)
        self.assertEqual(Path(output['files'][0]).read_bytes(), PNG)
        self.assertEqual(first.read_bytes(), PNG)
        self.assertNotIn('test-only-key', result.stdout + result.stderr)

    def test_no_reference_keeps_generation_endpoint(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.requests[0][0], '/v1/images/generations')
        self.assertNotIn('images', self.requests[0][1])

    def test_missing_or_nonimage_reference_fails_before_network(self):
        bad = self.root / 'not-an-image.png'
        bad.write_text('not an image')
        for ref in [self.root / 'missing.png', bad]:
            result = self.run_script('--image', str(ref))
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.requests, [])


if __name__ == '__main__':
    unittest.main()
