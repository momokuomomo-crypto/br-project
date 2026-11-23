# br-project

競艇（ボートレース）の出走表・結果・確定オッズを公式サイトから自動で集め、
「期待値派」（オッズから見た確率とモデルの確率を比べ、割安なときだけ買う）で
予想・検証するシステム。競馬版 kb-project と同じ仕組み。

* ダッシュボード：https://momokuomomo-crypto.github.io/br-project/
* 対象：全24場・全グレード、過去5年分

## 仕組み

```mermaid
flowchart LR
  PC[利用者のPC<br>self-hosted runner] -->|毎朝・15分ごと| Collect[収集・当日予想]
  Collect -->|push data/input, data/predictions| Repo[(br-project)]
  Repo -->|後続ジョブ| Analyze[分析・検証<br>GitHub クラウド]
  Analyze --> Pages[ダッシュボード<br>GitHub Pages]
```

公式サイトは海外からのアクセスを拒否するため、収集だけは日本の回線（利用者のPC）で動かす。

## 仕様書

| 設計書 | 内容 |
|---|---|
| [00_要件定義](docs/00_要件定義.md) | 目的・決定事項・構成 |
| [01_01_データ仕様](docs/01_foundation/01_01_データ仕様.md) | CSVの列・フォルダ構成 |
| [02_01_データ取得設計](docs/02_collect/02_01_データ取得設計.md) | 公式サイトからの取得・解析 |
| [04_01_期待値派モデル設計](docs/04_analysis/04_01_期待値派モデル設計.md) | 確率モデル・購入ルール・当日予想 |
| [04_02_検証設計](docs/04_analysis/04_02_検証設計.md) | 学習・選定・確認の3期間での検証 |
| [06_01_自動実行設計](docs/06_pipeline/06_01_自動実行設計.md) | GitHub Actions |
| [06_02_ダッシュボード設計](docs/06_pipeline/06_02_ダッシュボード設計.md) | 表示内容 |

実装ルールは [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)（競馬版と同じ）。
