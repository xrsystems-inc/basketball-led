#!/usr/bin/env python3
"""
USB HIDボタン(Copy/Paste刻印) + マウス によるLED制御デーモン

■ Copy/Pasteボタン(USB Vendor=514c Product=8851, 実体はCtrl+C/Ctrl+Vを
  エミュレートする汎用HIDキーボード):
    Copyボタン(KEY_C)を押している間 -> LED点灯(100%)、離すと消灯
    Pasteボタン(KEY_V)を押している間 -> LEDがフラッシュ(点滅)、離すと消灯

■ マウス(実機のポインティングデバイス。上記ボタンとは別デバイスとして
  Vendor/Product自動検出):
    左クリックを1.5秒以内に4回押す(ダウンイベント)と「マウスモード」を
    ON/OFFトグルする。
    マウスモードON中:
      左ボタンを押している間 -> LED点灯(100%)、離すと消灯
      右ボタンを押している間 -> LEDがフラッシュ(点滅)、離すと消灯
    マウスモードOFF中はクリックしてもLEDは反応しない(通常のマウス動作の
    まま。4連打の検出だけは常時動いている)。

evtest不要でraw /dev/input/eventNを直接読んで判定する。
Copy/Pasteボタンとマウスは別スレッドで並行監視するが、LED(pigpio)への
書き込みは共通ロックで排他制御し、フラッシュ状態も1つのFlasherを共有する
(同時に両方から光らせようとしても競合しない)。

前提: led_control.py と同じディレクトリに置くこと(pigpio接続処理を再利用)。
      pigpiodデーモンが起動していること。
      実行ユーザーが input グループに所属していること(sudo不要でraw device読取可能)。

使い方:
  python3 button_led_daemon.py
"""

import collections
import os
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import led_control

BUTTON_VENDOR_ID = "514c"
BUTTON_PRODUCT_ID = "8851"

EV_KEY = 1
KEY_C = 46
KEY_V = 47
BTN_LEFT = 0x110
BTN_RIGHT = 0x111

FLASH_INTERVAL = 0.1          # フラッシュ点滅の半周期(秒) = 5Hz点滅
RETRY_INTERVAL = 5.0          # デバイス未検出時の再検索間隔(秒)
QUINT_CLICK_COUNT = 4         # マウスモード切替に必要な連続クリック数
QUINT_CLICK_WINDOW = 1.5      # 連続クリックとみなす時間窓(秒)

# input_eventの構造体フォーマットはアーキテクチャ依存(timeval部分のサイズが異なる)。
# @llHHi はネイティブアライメントで自動的に実行環境に合わせたサイズになる。
EVENT_FORMAT = "@llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)


def _find_event_path(match_block, prefer_handler):
    """/proc/bus/input/devicesを走査し、match_block(block)->boolに合致する
    最初のデバイスブロックから、prefer_handlerで始まるハンドラのevent nodeを返す"""
    try:
        with open("/proc/bus/input/devices", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return None

    for block in content.split("\n\n"):
        if not match_block(block):
            continue
        h_line = next((line for line in block.splitlines() if line.startswith("H:")), None)
        if not h_line:
            continue
        handlers = h_line.split("=", 1)[1].split()
        if not any(h.startswith(prefer_handler) for h in handlers):
            continue
        for h in handlers:
            if h.startswith("event"):
                return f"/dev/input/{h}"
    return None


def find_button_device_path():
    """Copy/Pasteボタン(キーボードエミュレーション側インターフェース)を探す"""
    def is_button_block(block):
        return f"Vendor={BUTTON_VENDOR_ID}" in block and f"Product={BUTTON_PRODUCT_ID}" in block
    return _find_event_path(is_button_block, "kbd")


def find_mouse_device_path():
    """実際のポインティングデバイス(Copy/Pasteボタン自身のマウスIFは除外)を探す"""
    def is_real_mouse_block(block):
        if f"Vendor={BUTTON_VENDOR_ID}" in block and f"Product={BUTTON_PRODUCT_ID}" in block:
            return False  # ボタンデバイス自身の(未使用の)マウスIFは除外
        return True
    return _find_event_path(is_real_mouse_block, "mouse")


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


def watch_device(name, find_path_fn, handle_event_fn):
    """デバイスを検出してイベントを読み続ける。切断/未検出時は自動的に再試行する"""
    while True:
        path = find_path_fn()
        if not path:
            print(f"[{name}] デバイスが見つかりません。{RETRY_INTERVAL:.0f}秒後に再検索します。")
            time.sleep(RETRY_INTERVAL)
            continue

        print(f"[{name}] デバイス検出: {path}")
        try:
            for etype, code, value in read_events(path):
                handle_event_fn(etype, code, value)
        except OSError as e:
            print(f"[{name}] デバイス読み取りエラー({e})。再接続を試みます。")
            time.sleep(2)


class ButtonKeyboardHandler:
    """Copy(Ctrl+C)/Paste(Ctrl+V)ボタンのイベント処理"""

    def __init__(self, led, flasher):
        self._led = led
        self._flasher = flasher
        self._c_down = False
        self._v_down = False

    def handle(self, etype, code, value):
        if etype != EV_KEY:
            return
        ts = time.strftime("%H:%M:%S")

        if code == KEY_C:
            if value == 1 and not self._c_down:
                self._c_down = True
                self._flasher.stop()
                self._led.set(100.0)
                print(f"[{ts}] Copy押下 -> LED ON")
            elif value == 0 and self._c_down:
                self._c_down = False
                self._led.set(0.0)
                print(f"[{ts}] Copy解放 -> LED OFF")

        elif code == KEY_V:
            if value == 1 and not self._v_down:
                self._v_down = True
                self._flasher.start()
                print(f"[{ts}] Paste押下 -> LEDフラッシュ開始")
            elif value == 0 and self._v_down:
                self._v_down = False
                self._flasher.stop()
                print(f"[{ts}] Paste解放 -> LED OFF")


class MouseModeHandler:
    """左4連打でマウスモードをトグルし、モード中は左=点灯/右=フラッシュ"""

    def __init__(self, led, flasher):
        self._led = led
        self._flasher = flasher
        self._mouse_mode = False
        self._left_down = False
        self._right_down = False
        self._click_times = collections.deque()

    def handle(self, etype, code, value):
        if etype != EV_KEY:
            return
        ts = time.strftime("%H:%M:%S")

        if code == BTN_LEFT:
            if value == 1:
                self._register_click_and_maybe_toggle(ts)
            else:  # release
                if self._mouse_mode and self._left_down:
                    self._left_down = False
                    self._led.set(0.0)
                    print(f"[{ts}] マウス左解放 -> LED OFF")

        elif code == BTN_RIGHT and self._mouse_mode:
            if value == 1 and not self._right_down:
                self._right_down = True
                self._flasher.start()
                print(f"[{ts}] マウス右押下 -> LEDフラッシュ開始")
            elif value == 0 and self._right_down:
                self._right_down = False
                self._flasher.stop()
                print(f"[{ts}] マウス右解放 -> LED OFF")

    def _register_click_and_maybe_toggle(self, ts):
        now = time.monotonic()
        self._click_times.append(now)
        while self._click_times and now - self._click_times[0] > QUINT_CLICK_WINDOW:
            self._click_times.popleft()

        if len(self._click_times) >= QUINT_CLICK_COUNT:
            self._click_times.clear()
            self._mouse_mode = not self._mouse_mode
            self._left_down = False
            self._right_down = False
            self._flasher.stop()
            self._led.set(0.0)
            print(f"[{ts}] 左{QUINT_CLICK_COUNT}連打検出 -> マウスモード {'ON' if self._mouse_mode else 'OFF'}")
        elif self._mouse_mode:
            self._left_down = True
            self._flasher.stop()
            self._led.set(100.0)
            print(f"[{ts}] マウス左押下 -> LED ON")


def main():
    pi = led_control.connect()
    led = led_control.LedController(pi)
    led.set(0.0)
    flasher = led_control.Flasher(led, interval=FLASH_INTERVAL)

    kb_handler = ButtonKeyboardHandler(led, flasher)
    mouse_handler = MouseModeHandler(led, flasher)

    mouse_thread = threading.Thread(
        target=watch_device,
        args=("マウス", find_mouse_device_path, mouse_handler.handle),
        daemon=True,
    )
    mouse_thread.start()

    print(f"ボタン/マウス待ち受け中... 左クリック{QUINT_CLICK_COUNT}連打でマウスモード切替 (Ctrl+Cで終了)")
    try:
        watch_device("ボタン", find_button_device_path, kb_handler.handle)
    except KeyboardInterrupt:
        pass
    finally:
        flasher.stop()
        led.set(0.0)
        pi.stop()


if __name__ == "__main__":
    main()
