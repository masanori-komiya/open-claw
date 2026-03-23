# book_resale_monitor

物理系の学術書転売候補を自動収集するスクリプトです。

## 設定済み条件

- 対象: 物理系 / 医学系 / 情報系 / 化学系 / 洋書キーワード
- 最低利益額: 1000円
- 最低利益率: 15%
- 実行時刻: 7:00 / 13:00 / 21:00（cron）

## 対応ソース（初期）

- メルカリ
- ヤフオク

> 注意: 各サイト仕様変更で取得が不安定になる場合があります。

## セットアップ

```bash
cd book_resale_monitor
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/playwright install chromium
./venv/bin/python monitor.py
```

または

```bash
./run.sh
```

## 出力

- `output/latest.json` … 機械可読
- `output/latest.md` … 人間向けレポート

## cron登録

自動登録スクリプト:

```bash
./install_cron.sh
```

環境によって `crontab` が対話待ちになる場合は、手動で以下を追加してください。

```cron
0 7,13,21 * * * cd /Users/norinori/.openclaw/workspace/book_resale_monitor && /bin/bash /Users/norinori/.openclaw/workspace/book_resale_monitor/run.sh >> /Users/norinori/.openclaw/workspace/book_resale_monitor/output/cron.log 2>&1
```

## 珍しいものリスト

- `rare_items_seed.md` に高値化しやすい候補をカテゴリ別で整理済み
- `rare_items.json` に ISBN/著者/別名を登録済み（自動検索に使用）
- `config.json` の `use_rare_items` が true のとき、通常キーワードに加えて ISBN・著者ベースでも検索します

## 調整ポイント

- キーワード: `config.json` の `keywords`
- 利益条件: `min_profit_yen`, `min_profit_rate`
- ソース追加: `monitor.py` にスクレイパーを追加
