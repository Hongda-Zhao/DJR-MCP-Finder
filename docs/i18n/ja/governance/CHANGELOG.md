<!-- i18n-mirror: non-authoritative translation; source=docs/repository/CHANGELOG.md -->

> **翻訳について：** この翻訳は閲覧用です。相違がある場合は、原文の言語版を正式版とします。

# 変更履歴

DJR-MCP Finder の重要なエンジニアリング上の変更はすべてここに記録します。科学的エビデンスの
改訂は、引き続き凍結済み protocols と checksum manifests によって管理されます。

形式は [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) に従います。リポジトリのリリースには
簡潔な `MAJOR.MINOR` ラベルを使用し、インストール可能な Python distributions は独立した PEP 440
versions を維持します。

## [未リリース]

## [0.2] - 2026-09-28

### 追加

- Train 内の component 分離による短配列 benchmark。検証済み embedding の再利用、
  対応のある切断の準備、元の配列長別評価を実装しました。
- MCP 陽性 560 例（Train 336 例）の長さ統計。保留データでは長さだけを調べ、評価しません。
- <250、250–299、300–349、350–399、400–449、450–499、≥500 aa の集計表と英語図。
  V0.1 は Train の 331/336 MCP を検出し、偽陽性は 0/6,298。切断性能の評価は未完了です。
- 任意の `djrmcp-predict-v02-preview` は 250 aa 未満に `mcp_unreliable_short_sequence`
  と `NA` を返しモデルを実行しません。それ以上は固定 V0.1 を使用します。陰性ではなく保留です。
- 三言語の V0.2 設計とポリシー文書、および従来の比較形式を使った性能表と英語図。

### 変更

- ソフトウェア `v0.2`、研究パッケージ `0.2.0`、候補推論パッケージ `0.3.0` に更新。
  正式 V0 パッケージは `0.1.0` のままです。
- 引用メタデータとバージョン対応を更新。科学モデル ID、重み、校正、bundle は維持し、
  科学モデル V0.2 の学習は行っていません。
- 主図の FP 列を削除し、全体の偽陽性はキャプションに残しました。

### 検証

- ローカルでコア 236、正式 V0 33、候補推論 69、合計 338 テストに合格。
- 文書、メタデータ、Ruff と三つの wheel/sdist の検査に合格。
- 境界長、混合入力順序、モデルの省略、不正 FASTA、スコア維持、checksum、上書きを検証。

### v0.1 以降のその他のエンジニアリング更新


### 追加

- 階層化した `docs/` 情報アーキテクチャと機械可読 release manifest。
- 三つのランディングページ言語に共通する、安定したトップレベルディレクトリ機能表。
- 統一された `make setup/test/lint/smoke/build/check` コントリビューターコマンド。
- tag を契機とする package build と GitHub Release artifact のワークフロー。

### 変更

- Python package metadata は、SPDX/PEP 639 licensing、完全な project URLs、typed-package markers、
  metadata に基づく runtime versions を使用するようになりました。
- ランディング README は導入と利用に焦点を絞り、詳細な科学的資料と再現性資料は `docs/` に
  配置しました。
- V0.1 を現在の推奨結果としながら、公開済み V0 は第一級の再現可能 baseline および fallback として
  維持します。両方をそれぞれ異なる release statuses とともに表示します。
- 現在の推論出力は MCP 用語（`head2_mcp_probability`、`djr_non_mcp`、`mcp::...`）を使用します。
  アーカイブ済み benchmark identifiers は再現性のため変更しません。
- ランディングページでは、凍結済み V0 model-selection benchmark を V0/V0.1 remote-component
  development audit より先に提示し、V0.1 を現在の推奨結果として示します。
- ルートレベルにあった科学的 workflow、report、robustness protocol 文書を `docs/research/` に
  移動し、ドキュメントチェックによってルートの Markdown が再び増えすぎないようにしました。
- 補助ランディングページ翻訳、変更履歴、リポジトリレベルの第三者通知を
  `docs/repository/` に集約し、ルートには主要な英語 Markdown README のみを残しました。

### 削除

- 独立したコントリビューションおよびセキュリティポリシーページを公開文書から削除しました。
  issue と pull-request のテンプレートは引き続き `.github/` に保持します。

## [0.1] - 2026-07-30

### 追加

- 凍結済み `model-v0` user-inference package を含む、最初の正式な GitHub release。
- 二言語のランディング README、MIT license、citation metadata、third-party notices、baseline CI。

[未リリース]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/compare/v0.2...HEAD
[0.2]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/compare/v0.1...v0.2
[0.1]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases/tag/v0.1
