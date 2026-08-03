<!-- i18n-mirror: non-authoritative translation; source=.github/pull_request_template.md -->

> **翻訳について：** この翻訳は閲覧用です。相違がある場合は、原文の言語版を正式版とします。

## 概要

<!-- 何を、誰のために、なぜ変更しましたか？ -->

## 対象範囲

- [ ] 研究パイプライン
- [ ] 正式な `model-v0` 推論
- [ ] `model-v0.1-candidate` 推論
- [ ] ドキュメント/コミュニティファイル
- [ ] パッケージ化またはリリース自動化

## 検証

<!-- 実行した正確なコマンドと結果を記載してください。make targets を優先してください。 -->

- [ ] `make lint`
- [ ] 関連するテスト
- [ ] 関連するスモークチェック
- [ ] パッケージのメタデータまたは同梱ファイルを変更した場合は `make package-check`
- [ ] すべての GitHub Actions チェックが成功している

## 科学的境界とリリース境界

- [ ] 変更によって、凍結済みの encoders、heads、thresholds、routing、または evidence status が暗黙に変わっていない。
- [ ] checksum で拘束されたファイルを変更した場合、そのファイルを管理する checksum manifest も更新している。
- [ ] identifier または version を変更した場合、`release-manifest.json`、`docs/VERSIONING.md`、`docs/repository/CHANGELOG.md` が一致している。
- [ ] ユーザー向けの主張が `docs/SCIENTIFIC_EVIDENCE.md` の範囲内にとどまっている。

## セキュリティとデータ

- [ ] secrets、private sequences、checkpoints、raw datasets、caches、生成済み environments を含めていない。
- [ ] 新しい input、path、deserialization、overwrite の挙動について明示的な安全性レビューを行っている。

## レビュアー向け注記

<!-- 残存リスク、意図的に延期した作業、または手動で行う GitHub/PyPI 設定。 -->
