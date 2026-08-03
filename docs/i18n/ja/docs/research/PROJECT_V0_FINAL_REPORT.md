<!-- i18n-mirror: non-authoritative translation; source=docs/research/PROJECT_V0_FINAL_REPORT.md -->

> **翻訳について：** この翻訳は閲覧用です。凍結済みの中国語原文を正式版とします。

# DJR-MCP Finder project V0：最終簡潔レポート

## 一文での結論

Project V0 は data-curation V3 によって 11,060 件の代表タンパク質を構築し、component-safe split と
14-model Train/Validation 開発プロセスを経て **all ESM-C 6B** を凍結しました。その後の解析では、
ESM-2 3B が H1/H2 に対してより強い内部候補シグナルを示しましたが、mixed system、
PLM-vs-classical、ultra-remote の結果はいずれも外部 Test ではなく、V0 を置き換えるには不十分です。

## 1. 凍結済み主要リリース

| 項目 | 凍結値 |
| --- | --- |
| データ | 560 VMA-DJR + 500 cellular DJR + 5,000 HardNeg + 5,000 background |
| split | Train 6,634 / Validation 2,212 / Test 2,214 |
| 漏洩制御 | exact/source/component/MMseqs2 の関係を統合；residual qualifying cross-split edge=0 |
| benchmark | 14 models；共通 Train-only 5-fold component map |
| 選択規則 | 三 Head Validation gate + composite score + paired one-SE |
| released model | all ESM-C 6B、`S=0.997145` |

| Head | classifier | temperature | threshold |
| --- | ---: | ---: | ---: |
| H1：DJR / non-DJR | alpha=`1e-5` | 1168.1537298613255 | 0.9687754839244975 |
| H2：VMA / cellular DJR | C=`0.01` | 0.8241381150130028 | 0.9639353725025007 |
| H3：two known phyla + reject | C=`10` | 4.2474179687096845 | 0.7126488980564439 |

H3 の `unknown/other` は強制分類を棄却するものであり、任意の未知ウイルスを発見するものでは
ありません。過去の Test は ESM-2 650M にだけ使用されており、all ESM-C 6B の Test ステータスは
`not_evaluated` です。

## 2. Schema 5 mixed-head の結論

Schema 5 は、同じ matched Validation-family cohort で 8 個の homogeneous systems を比較します。
このラウンドの結果を見る前に、mixed search を次の範囲に限定しました。

```text
H1=H2 in {ESM-2 650M, ESM-2 3B, ESM-C 6B}
H3    in {ESM-C 300M, ESM-C 600M, ESM-C 6B}
```

候補は既存の Train-CV `S` だけで順位付けします。四情報源 robustness は統合せず、再順位付けにも
使用せず、Holm-corrected source warnings だけを生成します。nominee は
**H1/H2 ESM-2 3B + H3 ESM-C 6B** です。

| system | Train-CV `S` | always-on s·seq⁻¹ | worst-case s·seq⁻¹ |
| --- | ---: | ---: | ---: |
| mixed nominee | **0.997645** | **0.023524** | 0.083055 |
| frozen all ESM-C 6B | 0.997145 | 0.059531 | **0.059531** |

| source | nominee expected path (95% CI) | strict clusters | all-6B expected path |
| --- | ---: | ---: | ---: |
| viral | 0.9537 (0.9131–0.9872) | 52/69 | 0.9536 |
| cellular | 1.0000 (1.0000–1.0000) | 43/43 | 0.8791 |
| background | 0.9985 (0.9963–1.0000) | 997/1,000 | 0.9948 |
| matched HardNeg | 0.9998 (0.9995–1.0000) | 381/382 | 0.9978 |

all-6B に対する warnings は `0/4` ですが、これは四情報源の non-inferiority/equivalence の証明では
ありません。nominee の viral strict clusters は all-6B の 55/69 より少なく、H3 の worst case では
二つ目の encoder を実行する必要があります。Schema 5 independent validation は 20/20 gates PASS、
Test=0 です。training、recalibration、threshold adjustment、release-feedback operations はすべて 0 です。
正式なステータスは `recommended_for_external_confirmation` であり、released V0.1 ではありません。

## 3. PLM と古典的相同性検索：内部 cross-fit

完了済みの `plm_vs_classical_v0` は、6,634 件の Train records と既存の component folds を使用し、
3 folds fit/reference + 1 fold calibration + 1 fold evaluation を巡回して実行します。
Validation/Test prediction rows はいずれも 0 です。

Controlled retrieval トラックでは、すべての手法に同じ fold-specific positive references を与えます。
下表は、calibration-target 99.5% source-balanced specificity における fold-macro component AP /
sensitivity です。

| method | H1 | H2 | VMA end-to-end |
| --- | ---: | ---: | ---: |
| ESM-C 6B cosine | 0.8719 / 0.7340 | 0.9861 / 0.9306 | 0.9528 / 0.9301 |
| BLASTP | 0.9392 / 0.8692 | 0.9829 / 0.9443 | 0.9544 / 0.9401 |
| DIAMOND ultra | 0.9406 / 0.9025 | 0.9806 / 0.9317 | 0.9497 / 0.9317 |
| MMseqs2 | 0.9319 / 0.8805 | 0.9751 / 0.9119 | 0.9317 / 0.9078 |
| component-HMMER | 0.9542 / 0.9016 | 0.9911 / 0.9569 | 0.9660 / 0.9569 |
| ESM-2 650M cosine, contextual | 0.9515 / 0.8954 | 0.9965 / 0.9977 | 0.9906 / 0.9859 |

ESM-C cosine と四つの classical anchors の比較では、H1 AP と sensitivity の delta CI はすべて負です。
内部結果は「ESM-C cosine retrieval の方が高感度」という主張を支持しません。H2 と end-to-end の
事前登録済み delta CI はいずれも 0 をまたぐため、優劣を確立できません。

この結論には四つの境界があります。

1. 比較対象は representation retrieval であり、凍結済み supervised V0 tool の外部性能ではありません；
2. fold 3 の 62 個の cellular negatives は一つの component だけに属するため、H2/end-to-end low-FPR CI は conditional かつ resolution-limited です；
3. 99.9% specificity は resolution-limited secondary としてのみ扱い、FP-per-million は推定できません；
4. validator は点推定値を独立に再計算しましたが、`bootstrap_recomputed=false` であり、10,000 個の bootstrap は独立には再実行していません。

数値 benchmark validation=PASS です。元の figure bundle は、アクティブコピーから 3 個の source-data
TSVs が欠落していたため不完全でした。これらの表は凍結済み結果から決定論的に再構築し、元の
`figures/CHECKSUMS.sha256` と項目ごとに照合した後、compact release に収録しました。

## 4. V0/V0.1 ultra-remote 開発監査

V0.1 candidate は H1/H2 encoder だけを ESM-C 6B から ESM-2 3B に変更し、H3 は引き続き ESM-C 6B
です。この監査は同じ Train-only cyclic component cross-fit を再利用し、Validation/Test は開きません。

| comparison | all component holdout | BLAST-defined `qcov<80%` | `qcov≥80%, 20–30% identity` |
| --- | ---: | ---: | ---: |
| H1 encoder Δ sensitivity | +0.197 | +0.260 (0.206–0.317) | +0.046 (0.013–0.086) |
| H1 supervised detector Δ | +0.017 | +0.028 (0.011–0.049) | 0.000 |
| H2 encoder Δ | +0.049 | +0.062 (0.020–0.112) | +0.024 (0.001–0.057) |
| H2 supervised detector Δ | 0.000 | 0.000 | 0.000 |

encoder レベルのシグナルは operational detector の利得より明らかに強いものです。さらに重要なのは、
すべての paired systems が少なくとも一つの fold で実際の 99.5% specificity に達していないため、
matched-specificity improvement ではないことです。ESM-2 3B H2 detector の minimum-fold specificity
は 0.5426 にすぎず、threshold transfer は不安定です。strict `qcov≥80%, identity<20%` には一つの
独立 positive component しかなく、CI もないため、正式な ultra-remote 推論はできません。

最終ステータスは `PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE` です。プロセスと完全性は
合格しましたが、科学的主張の gate は合格していません。BLAST-defined distance strata には
method-conditioned bias も生じるため、PLM が BLAST より優れているとは主張できません。

## 5. H3、HardNeg、適用範囲

nominee H3 と V0 はともに ESM-C 6B を使用します。Nucleocytoviricota F1=0.9792、
Preplasmiviricota F1=1.0000 です。Produgelaviricota reject=6/7（2 parents）、
literature-unclassified=1/1（1 parent）です。二つの群は個別の記述的結果としてのみ報告でき、
普遍的な unknown-virus detection として統合することはできません。

HardNeg source reconstruction のステータスは `FULL_OPERATIONAL_RECOVERY_PASS` です。現在の
robustness の第四情報源は、selected clusters に属する 3,478 matched members であり、従来の 5,878
pass-but-unselected representatives ではありません。

## 6. エビデンスの境界とリリース判断

| claim | current status |
| --- | --- |
| component-safe データ構築と 14-model development selection | 報告可能 |
| frozen all ESM-C 6B tool | V0 research release として報告可能 |
| schema 5 family-neighbour robustness | post-freeze auxiliary evidence として報告可能 |
| PLM/classical Train-only cross-fit | internal development comparison として報告可能 |
| V0.1 low-coverage signal | descriptive development evidence として報告可能 |
| all-6B または V0.1 held-out Test performance | **報告不可；not evaluated** |
| PLM の古典的手法に対する外部優越性、正式な ultra-remote superiority | **報告不可** |
| clinical/diagnostic または universal unknown-virus detection | **報告不可** |

V0 は、再現可能な research release、候補優先順位付けツール、論文の methods 基盤として使用できます。
モデルを更新する前に、source-component-disjoint external lockbox、method-independent distance labels、
十分な `<20% identity` components、primary endpoints、specificity/cost gates、一度限りの Test ledger を
事前登録する必要があります。

## 7. 現在の正式な資料

- 完全なワークフロー：`WORKFLOW_V0.md`
- Schema 5 results：`results/validation_family_robustness_v0_schema5_mixed_heads/`
- Publication companion：`results/figures/project_v0/validation_family_robustness_v0_schema5_head_focus/`
- Internal homology benchmark：`benchmarks/plm_vs_classical_v0/`
- V0/V0.1 development audit：`benchmarks/ultra_remote_v0_v01/`
- Frozen user inference：`/aptmp/hongda/DJRMCP_Develope/user-inference-V0`

完全な predictions、bootstrap、search databases、logs、TIFF、V0.1 development code は、
`/aptmp/hongda/DJRMCP_Develope/` 以下の checksum-bound archives に保持されています。アクティブ
ディレクトリには compact evidence core だけを残します。
