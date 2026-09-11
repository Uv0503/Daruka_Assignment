"""Opt-in local Chrome demo check; no browser profile or new dependency needed."""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import websocket


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8510')
    args = parser.parse_args()
    if not args.url.startswith(('http://127.0.0.1:', 'http://localhost:')):
        raise ValueError('This check is restricted to the local demo.')
    prompt = 'What evidence supports the idea that increasing crop diversity can improve biodiversity or ecosystem services on agricultural land?'
    with tempfile.TemporaryDirectory(prefix='daruka-browser-') as profile:
        process = subprocess.Popen([
            '/usr/bin/google-chrome', '--headless=new', '--disable-gpu',
            '--no-first-run', '--no-default-browser-check',
            '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
            f'--user-data-dir={profile}', 'about:blank',
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            port_file = Path(profile) / 'DevToolsActivePort'
            deadline = time.monotonic() + 20
            while not port_file.exists() and time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Isolated Chrome exited before startup.')
                time.sleep(.2)
            port = port_file.read_text().splitlines()[0]
            with httpx.Client(trust_env=False, timeout=10) as client:
                tabs = client.get(f'http://127.0.0.1:{port}/json/list').json()
            page = next(tab for tab in tabs if tab['type'] == 'page')
            ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=15, suppress_origin=True)
            sequence = 0

            def call(method: str, params: dict | None = None) -> dict:
                nonlocal sequence
                sequence += 1
                ws.send(json.dumps({'id': sequence, 'method': method, 'params': params or {}}))
                while True:
                    reply = json.loads(ws.recv())
                    if reply.get('id') == sequence:
                        if 'error' in reply:
                            raise RuntimeError(reply['error'])
                        return reply.get('result', {})

            def evaluate(expression: str):
                reply = call('Runtime.evaluate', {'expression': expression, 'returnByValue': True})
                if reply.get('exceptionDetails'):
                    raise RuntimeError('Browser expression failed')
                return reply.get('result', {}).get('value')

            def wait_for(expression: str, seconds: int = 45):
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    value = evaluate(expression)
                    if value:
                        return value
                    time.sleep(.3)
                raise RuntimeError('Browser timed out waiting for UI state: ' + expression)

            call('Page.enable')
            call('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 1100, 'deviceScaleFactor': 1, 'mobile': False})
            call('Page.navigate', {'url': args.url})
            wait_for("document.querySelector('textarea[data-testid=stChatInputTextArea]:not([disabled])') !== null")
            evaluate("document.querySelector('textarea[data-testid=stChatInputTextArea]').focus()")
            call('Input.insertText', {'text': prompt})
            call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13})
            call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13})
            wait_for("document.querySelectorAll('[data-testid=stChatMessage]').length >= 2", 100)
            wait_for("Array.from(document.querySelectorAll('summary')).some(e => /Evidence|evidence context/.test(e.innerText))", 20)
            evaluate("document.querySelectorAll('details').forEach(e => e.open = true)")
            body = evaluate('document.body.innerText')
            links = evaluate("Array.from(document.querySelectorAll('a')).filter(a => a.innerText === 'Open source').map(a => a.href)")
            assert links, 'No original source links visible'
            assert 'Exact locator' in body and 'Complete extracted passage' in body
            assert 'KeyError' not in body and '[svg]' not in body
            assert 'chunk_id' not in body and 'evidence_quality' not in body
            screenshot = call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
            output = Path('artifacts')
            output.mkdir(exist_ok=True)
            (output / 'browser_demo.png').write_bytes(base64.b64decode(screenshot['data']))
            result = {'status': 'passed', 'method': 'isolated headless Chrome via CDP', 'url': args.url,
                      'prompt': prompt, 'source_links': links, 'visible_text': body,
                      'screenshot': 'artifacts/browser_demo.png'}
            (output / 'browser_demo.json').write_text(json.dumps(result, indent=2))
            print(json.dumps({'status': 'passed', 'source_links': len(links), 'artifact': 'artifacts/browser_demo.json'}))
            ws.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    main()
