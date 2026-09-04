#!/usr/bin/env python3
"""
USB HIDボタン(Copy/Paste刻印)によるLED制御デーモン

対象デバイス: USB Vendor=514c Product=8851 (刻印はCopy/Pasteだが実体は
汎用HIDキーボードで、ボタンはそれぞれ Ctrl+C / Ctrl+V のキーストロークを
エミュレートする。evtest不要でraw /dev/input/eventNを直接読んで判定する)

仕様:
  Copyボタン(KEY_C)を押している間 -> LED点灯(100%)、離すと消灯
  Pasteボタン(KEY_V)を押している間 -> LEDがフラッシュ(点滅)、離すと消灯

前提: led_control.py と同じディレクトリに置くこと(pigpio接続処理を再利用)。
      pigpiodデーモンが起動していること。
      実行ユーザーが input グループに所属していること(sudo不要でraw device読取可能)。

使い方:
  python3 button_led_daemon.py
"""

import os
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import led_control

VENDOR_ID = "514c"
PRODUCT_ID = "8851"

EV_KEY = 1
KEY_C = 46
KEY_V = 47

FLASH_INTERVAL = 0.1     # フラッシュ点滅の半周期(秒) = 5Hz点滅
RETRY_INTERVAL = 5.0     # デバイス未検出時の再検索間隔(秒)

# input_eventの構造体フォーマットはアーキテクチャ依存(timeval部分のサイズが異なる)。
# @llHHi はネイティブアライメントで自動的に実行環境に合わせたサイズになる。
EVENT_FORMAT = "@llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)


def find_device_path():
    """/proc/bus/input/devicesからVendor/Product一致かつkbdハンドラを持つevent nodeを探す"""
    try:
        with open("/proc/bus/input/devices", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return None

    for block in content.split("\n\n"):
        if f"Vendor={VENDOR_ID}" not in block or f"Product={PRODUCT_ID}" not in block:
            continue
        h_line = next((line for line in block.splitlines() if line.startswith("H:")), None)
        if not h_line:
            continue
        handlers = h_line.split("=", 1)[1].split()
        if "kbd" not in handlers:
            continue  # マウスインターフェース側は無視
        for h in handlers:
            if h.startswith("event"):
                return f"/dev/input/{h}"
    return None


def read_events(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        buf = b""
        while True:
            buf += os.read(fd, EVENT_SIZE * 64)
            while len(buf) >= EVENT_SIZE:
                chunk, buf = buf[:EVENT_SIZE], buf[EVENT_SIZE:]
                _sec, _usec, etype, code, value = struct.unpack(EVENT_FORMAT, chunk)
                yield etype, code, value
    finally:
        os.close(fd)


class Flasher:
    """Pasteボタンを押している間、別スレッドでLEDを点滅させる"""

    def __init__(self, pi):
        self._pi = pi
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        led_control.set_duty_percent(self._pi, 0.0)

    def _run(self):
        on = False
        while not self._stop.is_set():
            on = not on
            led_control.set_duty_percent(self._pi, 100.0 if on else 0.0)
            self._stop.wait(FLASH_INTERVAL)


def main():
    pi = led_control.connect()
    led_control.set_duty_percent(pi, 0.0)
    flasher = Flasher(pi)
    c_down = False
    v_down = False

    print("ボタン待ち受け中... (Ctrl+Cで終了)")
    try:
        while True:
            path = find_device_path()
            if not path:
                print(f"ボタンデバイスが見つかりません。{RETRY_INTERVAL:.0f}秒後に再検索します。")
                time.sleep(RETRY_INTERVAL)
                continue

            print(f"ボタンデバイス検出: {path}")
            try:
                for etype, code, value in read_events(path):
                    if etype != EV_KEY:
                        continue

                    ts = time.strftime("%H:%M:%S")
                    if code == KEY_C:
                        if value == 1 and not c_down:
                            c_down = True
                            flasher.stop()
                            led_control.set_duty_percent(pi, 100.0)
                            print(f"[{ts}] Copy押下 -> LED ON (duty={pi.get_PWM_dutycycle(led_control.GPIO_PIN)})")
                        elif value == 0 and c_down:
                            c_down = False
                            led_control.set_duty_percent(pi, 0.0)
                            print(f"[{ts}] Copy解放 -> LED OFF")

                    elif code == KEY_V:
                        if value == 1 and not v_down:
                            v_down = True
                            flasher.start()
                            print(f"[{ts}] Paste押下 -> LEDフラッシュ開始")
                        elif value == 0 and v_down:
                            v_down = False
                            flasher.stop()
                            print(f"[{ts}] Paste解放 -> LED OFF")
            except OSError as e:
                print(f"デバイス読み取りエラー({e})。再接続を試みます。")
                c_down = False
                v_down = False
                flasher.stop()
                time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        flasher.stop()
        led_control.set_duty_percent(pi, 0.0)
        pi.stop()


if __name__ == "__main__":
    main()
