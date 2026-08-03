<!-- i18n-mirror: non-authoritative translation; source=benchmarks/ultra_remote_v0_v01/README.md -->

この翻訳は閲覧の便宜のみを目的としています。凍結された英語の原文が正式な文書です。

[English](../../../../../benchmarks/ultra_remote_v0_v01/README.md) | [简体中文](../../../../../benchmarks/ultra_remote_v0_v01/README.cn.md) | **日本語**

# Ultra-remote benchmark：v0 対 v0.1

これは、独立した fail-closed の開発監査です。リリース済みの
`plm_vs_classical_v0` benchmark を変更せず、Validation または Test を開きません。

この active directory は、compact publication/checksum core です。protocol、configuration、
code、compact results、小規模な reproduction contract、figure source data、PNG/PDF/SVG 出力を
保持します。行レベルの diagnostics、log、TIFF export は、
`FULL_ARTIFACT_POINTER.json` が指定する完全な archive 内で引き続き checksum-bound です。
data は削除されていません。

## 実際に比較するもの

| レイヤー | v0 | v0.1 candidate | 公平な比較条件 |
|---|---|---|---|
| H1/H2 encoder | ESM-C 6B | ESM-2 3B | 同一の positive reference ID、maximum cosine |
| H1/H2 detector | ESM-C 6B + frozen classifier family | ESM-2 3B + 同じ classifier family | 同一の cyclic 3-fit/1-calibration/1-evaluation fold と hyperparameter |
| H3 phylum head | ESM-C 6B | 同じ ESM-C 6B | 除外：変更がなく、homology-detection endpoint ではない |

cosine layer は、representation 自体が held-out component を検索できるかを調べます。
supervised layer は、実際の H1/H2 detector がその representation を利用できるかを調べます。
classical tool は、parent benchmark で凍結された元の score と information-budget label を
維持します。

## Ultra-remote の境界

現在の data には、best BLAST query coverage が 80% 以上、identity が 20% 未満の positive
independent component が一つしかありません。したがって、この stratum は case series であり、
inferential benchmark ではありません。`qcov < 80%` は descriptive stress test に十分な数を
持ちますが、low-coverage proxy であり、ultra-remote homology の証明ではありません。また、
その定義は比較対象 method の一つである BLAST に由来するため、別の method が BLAST より優れて
いるという正式な主張を支えることはできません。

release-grade の ultra-remote benchmark は、label と distance stratum がすべての比較 method
から独立して凍結された external lockbox のために留保されます。structure または
experimental/manual evidence に基づくものが望まれます。

## Compact core の検証

```bash
cd /path/to/DJR-MCP-Finder/benchmarks/ultra_remote_v0_v01
sha256sum -c CHECKSUMS.sha256
```

`results/validation.json` は、成功した full-validator の凍結 record です。元の行レベル score
ledger と TIFF contract は archive のみにあるため、この compact tree から active validator を
replay することはできません。GitHub の `pbs/` launcher はポータブルな replay template であり、
standalone runner ではありません。正確な scoring、rendering、validation replay を行うには、
`FULL_ARTIFACT_POINTER.json` に従い、まずその `full_v1` tree を復元してください。ultra script は
parent PLM の input、query score、classical receipt も使用するため、
`../plm_vs_classical_v0/FULL_ARTIFACT_POINTER.json` が指定する PLM tree も、記録された active
path に復元してください。visualization manifest には、compact rendering output と source-data
checksum が記録されています。

別の system に archive を復元した後、リポジトリ root で `scripts/render_portable_config.py` を
使用して local config を生成し、`DJRMCP_ULTRA_CONFIG` をその copy に設定してください。さらに、
`DJRMCP_PROJECT_ROOT`、`DJRMCP_ARCHIVE_ROOT`、`DJRMCP_VENV_ROOT` を設定します。checked-in JSON は、
元の gds2 run の不変 record のままです。
