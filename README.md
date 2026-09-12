# Raspberry Pi 2 Model B - N-ch MOSFET LED制御

Raspberry Pi 2 Model B のGPIOで、
外付けNチャネルMOSFET(Active High, ローサイドスイッチ)を介して
12V駆動LEDテープ/モジュールをPWM調光するプロジェクト。

## プロジェクトの目的

デフバスケットボール(聴覚障がい者バスケットボール)向けに開発している。
審判の笛の音が聞こえない選手に、笛の合図を視覚的に伝える手段として、
コートサイドに設置したLEDテープを笛の代わりに点灯・フラッシュさせる
ことを目的としている。

入力(トリガー)手段は複数用意している(詳細は下記「入力デバイス」参照)が、
**試合中のリアルタイムな合図用途にはUSB接続の物理ボタン/マウス
(`button_led_daemon.py`)を推奨する**。スマホのブラウザ経由(`web_led_server.py`)
はネットワーク往復の遅延が体感できる程度あり、実際に試したところ
笛の代替としては反応が遅く感じられたため、動作確認・デモ・遠隔操作用途
向けと位置づけている。

## 構成

- Raspberry Pi 2 Model B
- Nチャネル MOSFET (ロジックレベル品, 例: IRLZ44N, IRLB8721, AO3400等)
- 12V LEDテープ/モジュール(内部に電流制限抵抗を内蔵済み)
- 電源: PoEスプリッターの12V出力
- (任意)GPIO出力モニタ用の小型LED + 直列抵抗(1kΩ目安、詳細は後述)

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

### モニタ用LED(GPIO直接駆動、トランジスタ不要)

12V系(LEDテープ/PoE/MOSFET)を接続していない状態でも、GPIO18が
正しくHigh/Low・PWM出力できているかを目視確認できるよう、GPIO18から
直列抵抗を介して小型LEDを直接駆動しGNDへ落とす分岐を追加できる。

```
GPIO18 ----[1kΩ]---- LED(アノード)
                       LED(カソード) ---- GND
```

- **トランジスタは不要**。Raspberry PiのGPIOはピン1本あたり最大16mA
  まで安全にソース/シンクできる(Broadcom SoCの絶対最大定格)。
  モニタ用LED1本(数mA)を追加する程度ではこの定格に対して十分な
  余裕があり、3.3Vレール全体への影響も無視できる。12V LEDテープ側で
  MOSFETが必要なのは電圧(12V > 3.3V)と電流がGPIOの駆動能力を
  超えるためであり、低電流の単体LEDには当てはまらない。
- **抵抗値の目安**: 赤色LED(Vf≈2V)なら `(3.3V − 2V) / 1kΩ ≈ 1.3mA`。
  明るさを上げたい場合は330〜470Ωまで下げても
  `(3.3V − 2V) / 330Ω ≈ 3.9mA` 程度に収まり、16mAの定格に対して
  十分安全。
- GPIO18は同時にゲート抵抗470Ω経由でMOSFETゲートも駆動しているが、
  ゲート側の電流はゲート容量の充放電による短時間の過渡電流のみで
  平均電流はごく僅かなため、モニタ用LEDの電流と合算しても定格に
  問題は生じない。
- GPIO18はPWM出力のため、モニタ用LEDの明るさもデューティ比に連動して
  変化する。点灯/消灯だけでなく、フェードやパルスの動作確認にも使える。

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

### systemdサービスの登録

常駐プログラム(`button_led_daemon.py` / `web_led_server.py`)は**テンプレート
ユニット**として提供している。実行ユーザー名をインスタンス名として渡すと、
ユニット内の`%i`がユーザー名とホームディレクトリの両方に展開される
(`User=%i` と `WorkingDirectory=/home/%i/basketball/raspi2-led`)。
これによりユニットファイル自体に環境固有のユーザー名を書かずに済む。

リポジトリの内容を`~/basketball/raspi2-led/`に配置した上で:

```bash
sudo cp button-led-daemon@.service web-led-server@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now button-led-daemon@$USER.service
sudo systemctl enable --now web-led-server@$USER.service
```

状態確認・ログは通常のsystemdと同じ(インスタンス名を含める):

```bash
systemctl status button-led-daemon@$USER.service
journalctl -u button-led-daemon@$USER.service -f
```

配置先を`~/basketball/raspi2-led/`以外にする場合はユニットの
`WorkingDirectory`を書き換えること。

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

## 入力デバイス

CLIでの直接操作(`led_control.py`)以外に、以下の常駐プログラムでLEDを
即座にトリガーできる。いずれもsystemdサービス化済みで、Pi起動時に
自動起動・異常終了時は自動再起動する。

なお常駐デーモン側は、入力デバイスが切断された時点でそのデバイスの押下状態を
解除しLEDを消灯する(押している最中にBTドングルがUSBリセットされると解放
イベントが届かず、LEDが点灯したまま固着するため)。消灯するのはそのデバイスが
点灯させていた場合に限り、他の入力源が点灯中のLEDには干渉しない。

### USB HIDボタン / マウス (`button_led_daemon.py`)

- 「Copy/Paste」刻印のUSBボタン(実体はCtrl+C/Ctrl+Vキーを送る汎用HID
  キーボード): Copyボタンを押している間LED点灯、Pasteボタンを押している間
  フラッシュ。離すと消灯。
- 通常のUSBマウス: 左クリックを1.5秒以内に4回押すと「マウスモード」を
  ON/OFFトグル。マウスモード中は左ボタン押しっぱなしで点灯、右ボタン
  押しっぱなしでフラッシュ。
- どちらも物理入力でネットワークを経由しないため遅延が最小で、
  実運用の笛代わり用途に最も適している。
- systemdサービス: `button-led-daemon@<ユーザー名>.service`
  (ユニットファイル: `button-led-daemon@.service`。後述の「systemdサービスの
  登録」を参照)

### Bluetoothシャッターボタン (`button_led_daemon.py` に統合)

市販のBLEカメラシャッターボタン(ATUMTEK等)をペアリングし、押している間LED
点灯・離すと消灯する。1ボタンしかないためフラッシュ機能は割り当てていない。

- **検出方式**: BT HIDデバイスは`/proc/bus/input/devices`の`I:`行が
  `Bus=0005`(USB機器は`0003`)になるため、バス種別で識別する。シャッターは
  製品ごとにVendor/Productがバラバラなので、Copy/Pasteボタンのような
  ID直書きは使えない。
- **キーコードは固定しない**: 実測ではATUMTEK製が`Consumer Control`ノードで
  `code=115`(`KEY_VOLUMEUP`, iOSモードの典型)を送出したが、製品/モードにより
  `KEY_ENTER`等に変わるため、キーコードを問わず「押されている間」で判定する。
  押下・解放の両方が届くことは実測で確認済み(押している時間がそのまま
  イベント間隔に一致)。
- Pi 2 Model BはBluetooth非搭載のため、**別途USB BTドングルが必要**
  (後述の注意を参照)。

ペアリング手順(シャッターの電源を入れてLED高速点滅=ペアリング待ちにしてから):

```bash
bluetoothctl --timeout 20 -- scan on      # アドレスを確認
bluetoothctl pair <MACアドレス>
bluetoothctl trust <MACアドレス>
bluetoothctl connect <MACアドレス>
```

#### BTドングルの注意(重要)

**2026-09時点で試した2製品はいずれも実戦投入に耐えない。**BT経路を使う場合は
ドングルの選定が最大のリスク要因になる。

| ドングル | USB ID | 症状 |
|---|---|---|
| UGREEN CM749 (Barrot BR8554) | `33fa:0010` | BLEスキャン中に数秒おきに`command 0x2041 tx timeout`→USB切断を繰り返す。実質使用不可。 |
| ノーブランド「BT DONGLE10」(CSR8510 A10クローン) | `0a12:0001` | ペアリング・LED点灯までは正常動作するが、**LEスキャン有効化(`0x200b`)で飛ぶ**。`start background scanning failed: -16`の直後にUSB切断→再列挙。約12分間隔で再発し、一度ハングするとBlueZの`power off/on`では復旧せず抜き差しが必要。 |

CSR8510クローンの障害連鎖は次のとおり。**シャッターが無操作でスリープ→切断
→BlueZが自動再接続のためLEバックグラウンドスキャンを開始→チップが飛ぶ→
復帰後もスキャン再開に失敗し自動復帰できない**。電源起因ではない
(`vcgencmd get_throttled`は`0x0`、USBオートサスペンドも無効)。

そのため、**試合での笛代替にはBT経路より2.4GHz USBレシーバー方式(HIDとして
見えるためBTスタックを一切介さない)またはUSB有線ボタンを推奨する**。
アプリケーション側の実装(`BtShutterHandler`)は完成しており、安定した
ドングルに交換すればそのまま動作する。

### Webブラウザ (`web_led_server.py`)

- 同じWiFi/ネットワーク内のスマホ・PCのブラウザから
  `http://<PiのIP>:8080/` にアクセスし、「点灯」「フラッシュ」ボタンを
  押している間だけLEDが反応する(アプリのインストールは不要)。
- 標準ライブラリのみで実装(Flask等の追加依存なし)。
- **注意**: HTTPリクエストの往復遅延があるため、試合中のリアルタイムな
  笛の代替としては反応がやや遅く感じられる。動作確認・デモ・遠隔操作
  用途向け。
- systemdサービス: `web-led-server@<ユーザー名>.service`
  (ユニットファイル: `web-led-server@.service`。後述の「systemdサービスの
  登録」を参照)

## より小型なRaspberry Piでの実現可否

現状はRaspberry Pi 2 Model Bで開発しているが、より小型・安価なモデルへの
置き換えを検討する場合の目安:

- **Raspberry Pi Zero / Zero W / Zero 2 W**: 現行コードのほぼそのまま
  動作すると考えられる。
    - LinuxベースのRaspberry Pi OSが動くため、pigpio・GPIOハードウェア
      PWM・evdev(`/dev/input`, `/proc/bus/input/devices`)の仕組みは
      本機と同様に利用できる。GPIO18のハードウェアPWMも同系統のSoCで
      利用可能。
    - ただしUSBポートが1つ(micro USB OTG)しかないため、Copy/Pasteボタン
      とマウスを同時に使うにはUSBハブが必要になる。
    - CPUは非力(Zero/Zero WはシングルコアARM 1GHz)だが、GPIO PWM制御と
      入力イベント読み取りという軽い処理なので性能面は問題にならない
      見込み。
    - Zero WはWiFi内蔵のため、`web_led_server.py`でスマホ操作をする
      場合は有線LANが不要になり好都合。
- **Raspberry Pi Pico / Pico W**: **現行コードのままでは動作しない**。
  Pico(RP2040)はLinuxを実行しないマイコンボードであり、
  `pigpiod`・systemd・`/proc/bus/input/devices`等のLinux前提の仕組みが
  そもそも存在しない。また、USBキーボード/マウスを「ホスト側」として
  読み取るUSBホスト機能もRP2040では標準搭載ではなく追加のUSBホスト
  スタック実装が必要、`http.server`ベースのWebサーバーもそのままでは
  動かない(MicroPythonでの作り直しが必要で機能も限定的)。移行するなら
  「USBボタンを直接読む」構成自体を諦め、PicoはLED点灯だけを担う
  スレーブ役にして上位のLinux機からシリアル/GPIO経由でトリガーする
  構成に設計変更するのが現実的。
  - 結論として、小型化するなら**Raspberry Pi Zero 2 W**が現行コードを
    ほぼそのまま維持できる最有力候補。Pico系はアーキテクチャが
    根本的に異なるため単純な置き換えはできない。

## ファイル

- `led_control.py` - LED制御コア(pigpio直接使用、GPIO18ハードウェアPWM、
  CLIコマンド一式、`LedController`/`Flasher`クラスも定義しており
  他スクリプトから再利用される)
- `button_led_daemon.py` - USB HIDボタン(Copy/Paste)・マウスモード常駐
  デーモン
- `button-led-daemon@.service` - 上記デーモンのsystemdユニットファイル
  (テンプレートユニット)
- `web_led_server.py` - スマホ/PCブラウザからの操作用Webサーバー
- `web-led-server@.service` - 上記Webサーバーのsystemdユニットファイル
  (テンプレートユニット)
