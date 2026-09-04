# Raspberry Pi 2 Model B - N-ch MOSFET LED制御

Raspberry Pi 2 Model B (ユーザー: <user>, ホスト名: <host>) のGPIOで、
外付けNチャネルMOSFET(Active High, ローサイドスイッチ)を介して
12V駆動LEDテープ/モジュールをPWM調光するプロジェクト。

## 構成

- Raspberry Pi 2 Model B
- Nチャネル MOSFET (ロジックレベル品, 例: IRLZ44N, IRLB8721, AO3400等)
- 12V LEDテープ/モジュール(内部に電流制限抵抗を内蔵済み)
- 電源: PoEスプリッターの12V出力

## 接続図

```
                                    +-------------------------+
                                    |   PoEスプリッター (12V出力) |
                                    +------------+-------------+
                                                 |
                                      12V(+)     |     GND
                                        |        |      |
                                        |        |      |
                                        v        |      v
                              +-------------------------------------+
                              |         LED(+)              |       |
                              |     12V LEDテープ/モジュール    |       |
                              |         LED(-)              |       |
                              +-------------------------------------+
                                        |                     |
                                        v                     |
                                     Drain                    |
                              +------------------+            |
Raspberry Pi 2                |   N-ch MOSFET    |            |
                              |   (ロジックレベル)  |            |
GPIO18 ----[470Ω]----------- Gate               |            |
(物理12番)         |          |   Source ---------+------------+
                    |          +------------------+       共通GND
                 [10kΩ]
                    |
                   GND (Pi/PoEスプリッターと共通)
```

### ポイント

- **LED(+)はPoEスプリッターの12V(+)へ直結**。直列抵抗は不要
  (12V LEDテープ/モジュールは内部に電流制限抵抗を内蔵済みのため、
  外部に抵抗を追加すると電圧降下で正しく点灯しない)。
- **GPIO18 → ゲート間に470Ωの直列抵抗**。ゲート容量の充放電時の
  突入電流をGPIOピンから制限する。PWM周波数200Hzでは470Ωでも
  スイッチング速度への影響は無視できるレベル。
- **ゲート-GND間に10kΩのプルダウン抵抗**。Pi起動中(OS起動完了まで)
  GPIOは不定状態になるため、これがないとActive High構成では
  起動シーケンス中にLEDが誤って一瞬点灯する可能性がある。
- **MOSFETはロジックレベル品を使用**。3.3V(Raspberry Pi GPIO)の
  ゲート駆動で十分にONする特性のものでないと、Rds(on)が高いまま
  になり発熱の原因になる。
- **PoEスプリッターの12V GNDとRaspberry PiのGNDを共通化**すること。
  ローサイドスイッチ方式のため、ゲート信号(Pi側)とドレイン電流経路
  (PoEスプリッターの12V系)が同じGND基準でないと正しく動作しない。
- **LEDテープの総電流がPoEスプリッターの12V出力定格を超えないこと**
  (802.3afの目安は0.7-0.8A、802.3atは~2A程度)。Raspberry Pi自体の
  電源も同じPoE系統から取る場合は合算で確認する。

## セットアップ

```bash
sudo apt update
sudo apt install -y python3-pigpio pigpio
sudo systemctl enable --now pigpiod
```

`pigpiod` はGPIO18のハードウェアPWMを扱うために必要な常駐デーモン。
Pythonスクリプト(クライアント)が終了しても、`pigpiod` がGPIO状態を
保持し続けるため、`on`実行後にスクリプトが終了してもLEDは点灯状態を
維持する。

## 使い方

```bash
python3 led_control.py <コマンド> [引数]
```

| コマンド | 説明 | 例 |
|---|---|---|
| `on` | 100%点灯 | `python3 led_control.py on` |
| `off` | 消灯 | `python3 led_control.py off` |
| `brightness <0-100>` | 明るさを%指定 | `python3 led_control.py brightness 30` |
| `fade-in [秒]` | フェードイン(既定2秒) | `python3 led_control.py fade-in 3` |
| `fade-out [秒]` | フェードアウト(既定2秒) | `python3 led_control.py fade-out 3` |
| `pulse [秒] [回数]` | 呼吸点灯(既定1秒周期・無限、Ctrl+Cで停止) | `python3 led_control.py pulse 1.5 5` |

## ファイル

- `led_control.py` - LED制御スクリプト本体(pigpio直接使用、GPIO18ハードウェアPWM)
