# バージョンと命名の規約

[English](VERSIONING.md) | [简体中文](VERSIONING.cn.md) | **日本語**

[ドキュメント一覧](README.ja.md) | [リポジトリ README](repository/README.ja.md) |
[リリースマニフェスト](../release-manifest.json)

このプロジェクトには、ソフトウェアリリース、Python distribution、科学モデル、固定された artifact bundle、データキュレーションの各バージョンがあります。それぞれ更新周期が異なるため、一つの番号ですべてを安全に表すことはできません。

## 要点

| ユーザーに表示される名称 | マシン識別子 | 意味 |
| --- | --- | --- |
| **Model V0.1 Candidate** | `model-v0.1-candidate` | 探索的スクリーニングで優先する実験的候補。独立した外部検証は未実施 |
| **Model V0** | `model-v0` | リリース済みで固定された科学的ベースライン、およびサポート対象のフォールバック |
| リポジトリリリース `v0.1` | `repository_release.tag` | GitHub ソフトウェアリリースのバージョンであり、科学モデルに関する主張ではない |
| Candidate パッケージ `0.2.1` | `djrmcp-user-inference-v01==0.2.1` | Candidate 推論 distribution のエンジニアリング改訂であり、「Model V0.2」ではない |

マシン向けメタデータとエビデンス記録では、常に完全な科学 ID `model-v0.1-candidate` を使用してください。ユーザー向けナビゲーションで短い **V0.1** を使用できるのは、隣接する表または文章で、外部検証を待つ Candidate であることを明記している場合に限ります。正式な表示名は **Model V0.1 Candidate** です。

新規スクリーニングで Model V0.1 Candidate を優先しても、それが正式に確認済みのモデルになるわけではなく、Model V0 が非推奨になるわけでもありません。

## 標準レイヤー

| レイヤー | 形式 | 例 | 変更されるタイミング |
| --- | --- | --- | --- |
| リポジトリ／ソフトウェアリリース | `vMAJOR.MINOR` | `v0.1` | GitHub ソフトウェアリリース系列が変わるとき |
| Python distribution | PEP 440 バージョン | `djrmcp-user-inference==0.1.0` | 対象のインストール可能パッケージが変わるとき |
| 科学モデル | `model-v<scientific line>[-candidate]` | `model-v0`、`model-v0.1-candidate` | 固定モデルの識別子またはエビデンス状態が変わるとき |
| Bundle リビジョン | `<model-id>-<encoder>-rN` | `model-v0-esmc6b-r1` | エクスポート済みファイルまたはパッケージングのリビジョンが変わるとき |
| データキュレーション | `data-curation-vN` | `data-curation-v3` | データセット構築規約が変わるとき |

メタデータでは小文字のマシン ID を、科学的な文章では上記の正式表示名を使用してください。

## 現在の対応関係

| コンポーネント | バージョン / ID | 状態 |
| --- | --- | --- |
| GitHub リポジトリ | `v0.1` | リリース済みソフトウェアスナップショット |
| 研究パイプライン distribution | `djrmcp-finder==0.1.0` | Alpha ソフトウェア |
| 正式推論 distribution | `djrmcp-user-inference==0.1.0` | `model-v0` を同梱 |
| Candidate 推論 distribution | `djrmcp-user-inference-v01==0.2.1` | `model-v0.1-candidate` のエンジニアリング改訂 |
| 正式 bundle | `model-v0-esmc6b-r1` | リリース済み・固定済み |
| Candidate bundle | `model-v0.1-mixed-r1` | 外部検証が必要 |

Candidate パッケージバージョン `0.2.1` は、科学モデルが V0.2 としてリリースされたことを意味しません。パッケージバージョンを下げたり、リポジトリタグと同じ値に強制したりはしません。

## マシン可読な正規情報源

[`release-manifest.json`](../release-manifest.json) は、これらのレイヤー間の唯一の簡潔な対応表です。次のコマンドは、各 `pyproject.toml`、実行時バージョン情報、`py.typed` マーカー、bundle の `release.json`、科学的状態フィールドとの整合性を検証します。

```bash
python scripts/check_project_metadata.py
```

パッケージバージョンを `__init__.py` に重複して記載しないでください。実行時コードは `importlib.metadata` を通じてインストール済み distribution のメタデータを読みます。未インストールのソース checkout は、リリース版を装うのではなく `0.0.0.dev0` を返します。

## 変更ルール

### リポジトリリリース

リポジトリリリースには簡潔な `MAJOR.MINOR` ラベルを使用します。後方互換性のある機能追加やパッケージ化された Candidate の変更では MINOR を増やし、公開 CLI、出力 schema、パッケージ API の互換性を壊す変更では MAJOR を増やします。パッチレベルのエンジニアリング改訂は Python distribution と bundle のバージョンに反映し、リポジトリリリースに第三の構成要素は追加しません。

`release-manifest.json` のリポジトリバージョンとタグを更新し、`docs/repository/CHANGELOG.md` を
更新して `make check` に合格させ、`main` にマージしてから、一致する annotated tag を作成します。

### Python distribution

変更された distribution だけを更新します。その `pyproject.toml` と `release-manifest.json` 内の対応項目を更新してください。パッケージレベルの Release Candidate には `0.3.0rc1` のような PEP 440 プレリリースを使用します。パッケージバージョンから科学的エビデンス状態を推測してはいけません。

### 科学モデル

新しいモデル ID には、固定されたモデルカード、完全な bundle メタデータと checksum、明示されたエビデンス状態、そして [`WORKFLOW_V0.md`](research/WORKFLOW_V0.md) に定める科学的リリースゲートが必要です。すべての固定パラメータを維持するエンジニアリング上のリファクタリングは、新しいモデル ID を作りません。

### Bundle リビジョン

モデルの挙動を変えずに、エクスポート済みファイルまたはモデル以外の bundle メタデータを変更する場合は `rN` を増やします。分類器の重み、閾値、ルーティング、encoder を変更する場合は、その変更を bundle リビジョンに隠さず、新しい科学モデル識別子を作成してください。

## タグリリースゲート

リリース workflow は、マニフェストのリポジトリタグと一致するタグだけを受け付けます。三つの distribution すべてについて wheel と sdist をビルド・検証し、GitHub Release に添付します。パッケージ名を確保し、保護された GitHub environment で Trusted Publishing を設定するまでは、PyPI アップロードを意図的に無効にしています。

## 日本語要約

リポジトリリリース、Python パッケージ、科学モデル、bundle revision は別々のレイヤーです。現在の正式表示名は **Model V0.1 Candidate**、マシン ID は `model-v0.1-candidate` です。これは探索的スクリーニングで優先する実験的候補ですが、独立した外部検証は未実施です。**Model V0**（`model-v0`）は、リリース済みで固定された正式なベースラインとして維持されます。リポジトリタグ `v0.1` と Candidate パッケージ `0.2.1` は、いずれも科学モデルのエビデンス状態を表しません。すべての対応関係は `release-manifest.json` で一元管理され、CI によって検証されます。
