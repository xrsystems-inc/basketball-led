#!/usr/bin/env python3
"""
Raspberry Pi 2 Model B - N-ch MOSFET駆動LED制御 (Active High / PWM調光)

配線 (LED: 12V駆動LEDテープ/モジュール, 電源: PoEスプリッター12V出力):
  GPIO18 (物理12番, ハードウェアPWM対応) --[470ohm]--> MOSFET Gate
    ※ゲート抵抗は220-470ohm程度で可(今回のPWM=200Hzでは470ohmでも
      スイッチング速度への影響は無視できるレベル)
  MOSFET Gate --[10kohm]--> GND (プルダウン, 起動時の誤点灯防止)
  MOSFET Source --> GND (PoEスプリッターのGND, Piと共通)
  MOSFET Drain  --> LED(-)
  PoEスプリッター 12V(+) --> LED(+)  ※直列抵抗は不要(テープ側に電流制限抵抗が内蔵済み)

  注意:
  - MOSFETは3.3V(GPIO)ゲート駆動対応のロジックレベル品を使用すること
    (例: IRLZ44N, IRLB8721, AO3400等)。汎用パワーMOSFETは3.3Vで
    十分にONせずRds(on)が高いままになり発熱する。
  - PoEスプリッターの12V GNDとRaspberry PiのGNDを必ず共通化すること
    (ローサイドスイッチ方式のためGND基準が一致していないと正しく動作しない)。
  - LEDテープの総電流がPoEスプリッターの12V出力定格を超えないこと。

なぜ pigpio を直接使うか:
  gpiozero はデフォルトでスクリプト終了時(atexit)に全デバイスをクリーンアップし
  ピンをOFF/入力に戻してしまう。そのため「on」を実行して終了すると直後にLEDが
  消えてしまう。pigpio はデーモン(pigpiod)側がGPIO状態を保持し続けるので、
  スクリプト(クライアント)が終了してもLEDの点灯状態はそのまま維持される。
  これは「点けたら消すまで点灯し続ける」CLI的な使い方に必須の挙動。

前提:
  pigpiodデーモンが起動していること
    sudo systemctl enable pigpiod
    sudo systemctl start pigpiod
  pigpio Pythonモジュールが入っていること
    sudo apt install python3-pigpio

使い方:
  python3 led_control.py on
  python3 led_control.py off
  python3 led_control.py brightness 50            # 0-100(%)
  python3 led_control.py fade-in  [seconds]       # 既定2秒。実行中はブロックする
  python3 led_control.py fade-out [seconds]
  python3 led_control.py pulse [seconds] [count]  # 呼吸(パルス)点灯。countは繰り返し回数(既定は無限, Ctrl+Cで停止)
"""

import sys
import time

import pigpio

GPIO_PIN = 18            # ハードウェアPWM対応ピン (物理12番)
PWM_FREQUENCY = 200      # Hz
DUTY_MAX = 1_000_000     # pigpioのhardware_PWMは0-1,000,000でデューティ比を指定
STEP_INTERVAL = 0.02     # フェード時の更新間隔(秒)
GAMMA = 2.8              # 人の目の明るさ知覚に合わせるガンマ補正係数


def connect():
    pi = pigpio.pi()
    if not pi.connected:
        print("エラー: pigpiodに接続できません。"
              " 'sudo systemctl start pigpiod' を実行してください。", file=sys.stderr)
        sys.exit(1)
    return pi


def percent_to_duty(percent):
    """percent(体感の明るさ, 0-100)をガンマ補正しPWMデューティ値(0-DUTY_MAX)へ変換"""
    percent = max(0.0, min(100.0, percent))
    linear = percent / 100.0
    return int((linear ** GAMMA) * DUTY_MAX)


def duty_to_percent(duty):
    """PWMデューティ値(0-DUTY_MAX)を体感の明るさpercent(0-100)へ逆変換"""
    linear = duty / DUTY_MAX
    if linear <= 0:
        return 0.0
    return (linear ** (1.0 / GAMMA)) * 100.0


def set_duty_percent(pi, percent):
    """percent: 0.0-100.0 (Active High: 0%=常時LOW=消灯, 100%=常時HIGH=全点灯)"""
    pi.hardware_PWM(GPIO_PIN, PWM_FREQUENCY, percent_to_duty(percent))


def get_duty_percent(pi):
    return duty_to_percent(pi.get_PWM_dutycycle(GPIO_PIN))


def cmd_on(pi, args):
    set_duty_percent(pi, 100.0)
    print("LED ON (100%)")


def cmd_off(pi, args):
    set_duty_percent(pi, 0.0)
    print("LED OFF")


def cmd_brightness(pi, args):
    if not args:
        print("使用法: brightness <0-100>", file=sys.stderr)
        sys.exit(1)
    percent = float(args[0])
    set_duty_percent(pi, percent)
    print(f"LED brightness = {max(0.0, min(100.0, percent)):.0f}%")


def _ramp(pi, start_percent, end_percent, duration):
    if duration <= 0:
        set_duty_percent(pi, end_percent)
        return
    steps = max(1, int(duration / STEP_INTERVAL))
    for i in range(steps + 1):
        p = start_percent + (end_percent - start_percent) * (i / steps)
        set_duty_percent(pi, p)
        time.sleep(duration / steps)


def cmd_fade_in(pi, args):
    duration = float(args[0]) if args else 2.0
    current = get_duty_percent(pi)
    _ramp(pi, current, 100.0, duration)
    print(f"フェードイン完了 ({duration}秒)")


def cmd_fade_out(pi, args):
    duration = float(args[0]) if args else 2.0
    current = get_duty_percent(pi)
    _ramp(pi, current, 0.0, duration)
    print(f"フェードアウト完了 ({duration}秒)")


def cmd_pulse(pi, args):
    duration = float(args[0]) if len(args) > 0 else 1.0
    count = int(args[1]) if len(args) > 1 else None
    print("パルス点灯中... Ctrl+Cで停止")
    n = 0
    try:
        while count is None or n < count:
            _ramp(pi, 0.0, 100.0, duration)
            _ramp(pi, 100.0, 0.0, duration)
            n += 1
    except KeyboardInterrupt:
        set_duty_percent(pi, 0.0)


COMMANDS = {
    "on": cmd_on,
    "off": cmd_off,
    "brightness": cmd_brightness,
    "fade-in": cmd_fade_in,
    "fade-out": cmd_fade_out,
    "pulse": cmd_pulse,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"使用法: {sys.argv[0]} <{'|'.join(COMMANDS)}> [引数...]", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]

    pi = connect()
    try:
        COMMANDS[command](pi, args)
    finally:
        # pi.stop()はソケット接続を閉じるだけで、pigpiod側が保持しているGPIO/PWM状態は
        # そのまま維持される(gpiozeroのようにピンがOFF/入力に戻ることはない)。
        pi.stop()


if __name__ == "__main__":
    main()
