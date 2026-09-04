#!/usr/bin/env python3
"""
スマホ(や他PC)のブラウザからLEDを操作するWebサーバー

led_control.py と同じディレクトリに置くこと(pigpio接続処理を再利用)。
Copy/Pasteボタンやマウスモード(button_led_daemon.py)と同じUX:
  「点灯」ボタンを押している間だけ点灯、離すと消灯
  「フラッシュ」ボタンを押している間だけ点滅、離すと消灯
標準ライブラリのみで動作(Flask等は不要)。アプリ不要、ブラウザだけで使える。

前提: pigpiodデーモンが起動していること。

使い方:
  python3 web_led_server.py [port]   # 既定ポート8080
  同じWiFi内のスマホから http://<RaspberryPiのIP>:8080/ にアクセス
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import led_control

DEFAULT_PORT = 8080
FLASH_INTERVAL = 0.1  # フラッシュ点滅の半周期(秒) = 5Hz点滅

PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>LED Control</title>
<style>
  html, body {
    margin: 0; height: 100%; background: #111; color: #eee;
    font-family: system-ui, sans-serif; -webkit-user-select: none; user-select: none;
  }
  body {
    display: flex; flex-direction: column; gap: 16px;
    padding: 16px; box-sizing: border-box;
  }
  h1 { text-align: center; font-size: 1.1rem; font-weight: normal; opacity: 0.7; margin: 4px 0; }
  .btn {
    flex: 1; border-radius: 24px; border: none;
    font-size: 1.6rem; font-weight: bold;
    display: flex; align-items: center; justify-content: center;
    touch-action: none; -webkit-tap-highlight-color: transparent;
    transition: transform 0.05s, filter 0.05s;
  }
  .btn:active, .btn.active { filter: brightness(1.3); transform: scale(0.98); }
  #onBtn { background: #ffcc00; color: #222; }
  #flashBtn { background: #3399ff; color: #fff; }
  #status { text-align: center; opacity: 0.6; font-size: 0.9rem; height: 1.2em; }
</style>
</head>
<body>
  <h1>バスケットボールコート LED操作</h1>
  <button id="onBtn" class="btn">押している間 点灯</button>
  <button id="flashBtn" class="btn">押している間 フラッシュ</button>
  <div id="status"></div>
<script>
const statusEl = document.getElementById('status');

function post(path) {
  fetch(path, { method: 'POST' }).catch(() => {
    statusEl.textContent = '通信エラー';
  });
}

function bindHold(btn, downPath, upPath) {
  let active = false;
  const start = (e) => {
    e.preventDefault();
    if (active) return;
    active = true;
    btn.classList.add('active');
    post(downPath);
  };
  const end = (e) => {
    e.preventDefault();
    if (!active) return;
    active = false;
    btn.classList.remove('active');
    post(upPath);
  };
  btn.addEventListener('pointerdown', start);
  btn.addEventListener('pointerup', end);
  btn.addEventListener('pointercancel', end);
  btn.addEventListener('pointerleave', (e) => { if (active) end(e); });
  btn.addEventListener('contextmenu', (e) => e.preventDefault());
}

bindHold(document.getElementById('onBtn'), '/api/on', '/api/off');
bindHold(document.getElementById('flashBtn'), '/api/flash/start', '/api/flash/stop');
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    led = None
    flasher = None

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def _send(self, code, body=b"", content_type="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found")

    def do_POST(self):
        actions = {
            "/api/on": lambda: (self.flasher.stop(), self.led.set(100.0)),
            "/api/off": lambda: self.led.set(0.0),
            "/api/flash/start": lambda: self.flasher.start(),
            "/api/flash/stop": lambda: self.flasher.stop(),
        }
        action = actions.get(self.path)
        if action is None:
            self._send(404, b"not found")
            return
        action()
        self._send(200, json.dumps({"ok": True}).encode("utf-8"), "application/json")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT

    pi = led_control.connect()
    led = led_control.LedController(pi)
    led.set(0.0)
    flasher = led_control.Flasher(led, interval=FLASH_INTERVAL)

    Handler.led = led
    Handler.flasher = flasher

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Webサーバー起動: http://0.0.0.0:{port}/ (Ctrl+Cで終了)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        flasher.stop()
        led.set(0.0)
        server.server_close()
        pi.stop()


if __name__ == "__main__":
    main()
