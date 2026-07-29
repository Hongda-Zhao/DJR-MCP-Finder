# DJR-MCP Finder project V0：最终精简报告

## 一句话结论

Project V0 以 data-curation V3 构建 11,060 条代表蛋白，经 component-safe split 和 14-model
Train/Validation 开发流程冻结 **all ESM-C 6B**。后续分析发现 ESM-2 3B 更适合 H1/H2 的内部候选信号，
但 mixed system、PLM-vs-classical 和 ultra-remote 结果都不是外部 Test，尚不足以替换 V0。

## 1. 冻结主发布

| 项目 | 冻结值 |
| --- | --- |
| 数据 | 560 VMA-DJR + 500 cellular DJR + 5,000 HardNeg + 5,000 background |
| split | Train 6,634 / Validation 2,212 / Test 2,214 |
| 泄漏控制 | exact/source/component/MMseqs2 关系合并；residual qualifying cross-split edge=0 |
| benchmark | 14 models；共享 Train-only 5-fold component map |
| 选择规则 | 三 Head Validation gate + composite score + paired one-SE |
| released model | all ESM-C 6B，`S=0.997145` |

| Head | classifier | temperature | threshold |
| --- | ---: | ---: | ---: |
| H1：DJR / non-DJR | alpha=`1e-5` | 1168.1537298613255 | 0.9687754839244975 |
| H2：VMA / cellular DJR | C=`0.01` | 0.8241381150130028 | 0.9639353725025007 |
| H3：two known phyla + reject | C=`10` | 4.2474179687096845 | 0.7126488980564439 |

H3 的 `unknown/other` 是拒绝硬分类，不是发现任意未知病毒。历史 Test 只用于 ESM-2 650M；all ESM-C
6B 的 Test 状态为 `not_evaluated`。

## 2. schema 5 mixed-head 结论

schema 5 在相同的 matched Validation-family cohort 上比较 8 个 homogeneous systems，并在看到本轮结果
前把 mixed search 限定为：

```text
H1=H2 in {ESM-2 650M, ESM-2 3B, ESM-C 6B}
H3    in {ESM-C 300M, ESM-C 600M, ESM-C 6B}
```

候选只按既有 Train-CV `S` 排序；四来源 robustness 不合并、不参与重排，只产生 Holm-corrected
source warnings。nominee 为 **H1/H2 ESM-2 3B + H3 ESM-C 6B**：

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

相对 all-6B 为 `0/4` warnings，但这不是四来源 non-inferiority/equivalence 证明；nominee 的 viral strict
clusters 低于 all-6B 的 55/69，H3 worst-case 还要运行第二个 encoder。schema 5 independent validation
为 20/20 gates PASS；Test=0；训练、重校准、
调阈值和发布反馈操作均为 0。正式状态是 `recommended_for_external_confirmation`，不是 released V0.1。

## 3. PLM 与经典同源检索：内部 cross-fit

已完成的 `plm_vs_classical_v0` 使用 6,634 条 Train records 和既有 component folds，循环执行
3 folds fit/reference + 1 fold calibration + 1 fold evaluation。Validation/Test prediction rows 都为 0。

Controlled retrieval 轨道给所有方法相同的 fold-specific positive references；下表为 fold-macro
component AP / sensitivity at calibration-target 99.5% source-balanced specificity：

| method | H1 | H2 | VMA end-to-end |
| --- | ---: | ---: | ---: |
| ESM-C 6B cosine | 0.8719 / 0.7340 | 0.9861 / 0.9306 | 0.9528 / 0.9301 |
| BLASTP | 0.9392 / 0.8692 | 0.9829 / 0.9443 | 0.9544 / 0.9401 |
| DIAMOND ultra | 0.9406 / 0.9025 | 0.9806 / 0.9317 | 0.9497 / 0.9317 |
| MMseqs2 | 0.9319 / 0.8805 | 0.9751 / 0.9119 | 0.9317 / 0.9078 |
| component-HMMER | 0.9542 / 0.9016 | 0.9911 / 0.9569 | 0.9660 / 0.9569 |
| ESM-2 650M cosine, contextual | 0.9515 / 0.8954 | 0.9965 / 0.9977 | 0.9906 / 0.9859 |

ESM-C cosine 对四个 classical anchors 的 H1 AP 与 sensitivity delta CI 全为负；内部结果不支持“ESM-C
cosine retrieval 更灵敏”。H2 和 end-to-end 的预注册 delta CI 均跨 0，不能建立优劣。

这一结论有四个边界：

1. 它比较 representation retrieval，不是冻结 supervised V0 工具的外部性能；
2. fold 3 的 62 个 cellular negatives 只有一个 component，H2/end-to-end low-FPR CI 是 conditional、
   resolution-limited；
3. 99.9% specificity 只作 resolution-limited secondary，FP-per-million 不可估；
4. validator 独立重算点估计，但 `bootstrap_recomputed=false`，没有独立重跑 10,000 个 bootstrap。

数值 benchmark validation=PASS。原 figure bundle 曾因活动复制遗漏 3 个 source-data TSV 而不完整；这些表
已从冻结结果确定性重建，经原 `figures/CHECKSUMS.sha256` 逐项验证后纳入 compact release。

## 4. V0/V0.1 ultra-remote 开发审计

V0.1 candidate 仅将 H1/H2 encoder 从 ESM-C 6B 换为 ESM-2 3B；H3 仍为 ESM-C 6B。该审计复用同一
Train-only cyclic component cross-fit，不打开 Validation/Test。

| comparison | all component holdout | BLAST-defined `qcov<80%` | `qcov≥80%, 20–30% identity` |
| --- | ---: | ---: | ---: |
| H1 encoder Δ sensitivity | +0.197 | +0.260 (0.206–0.317) | +0.046 (0.013–0.086) |
| H1 supervised detector Δ | +0.017 | +0.028 (0.011–0.049) | 0.000 |
| H2 encoder Δ | +0.049 | +0.062 (0.020–0.112) | +0.024 (0.001–0.057) |
| H2 supervised detector Δ | 0.000 | 0.000 | 0.000 |

encoder 层信号明显强于 operational detector 增益。更重要的是：所有 paired systems 至少一个 fold 未达到
实际 99.5% specificity，因此不是 matched-specificity improvement；ESM-2 3B H2 detector 的最低-fold
specificity 仅 0.5426，阈值转移不稳定。严格 `qcov≥80%, identity<20%` 只有一个独立 positive
component，无 CI，不能做正式 ultra-remote 推断。

最终状态为 `PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE`：流程与完整性通过，科学主张门禁
未通过。BLAST 定义的 distance strata 还会产生方法条件化偏差，不能据此宣称 PLM 胜过 BLAST。

## 5. H3、HardNeg 与适用范围

nominee H3 与 V0 都使用 ESM-C 6B：Nucleocytoviricota F1=0.9792，Preplasmiviricota F1=1.0000。
Produgelaviricota reject=6/7（2 parents），literature-unclassified=1/1（1 parent）；两组只能分开作描述性
结果，不能汇成普适 unknown-virus detection。

HardNeg source reconstruction 为 `FULL_OPERATIONAL_RECOVERY_PASS`；当前 robustness 第四来源是 selected
clusters 的 3,478 matched members，不是旧 5,878 pass-but-unselected representatives。

## 6. 证据边界与发布判断

| claim | current status |
| --- | --- |
| component-safe 数据构筑与 14-model development selection | 可报告 |
| frozen all ESM-C 6B 工具 | 可报告为 V0 research release |
| schema 5 family-neighbour robustness | 可报告为 post-freeze auxiliary evidence |
| PLM/classical Train-only cross-fit | 可报告为 internal development comparison |
| V0.1 low-coverage signal | 可报告为 descriptive development evidence |
| all-6B 或 V0.1 held-out Test performance | **不可报告；not evaluated** |
| PLM 外部优于经典方法、正式 ultra-remote superiority | **不可报告** |
| clinical/diagnostic 或 universal unknown-virus detection | **不可报告** |

V0 可作为可复现的 research release、候选优先级排序工具与论文方法基础。模型升级前必须预注册
source-component-disjoint
external lockbox、方法独立的 distance labels、足够的 `<20% identity` components、primary endpoints、
specificity/cost 门禁与一次性 Test ledger。

## 7. 当前权威材料

- 完整流程：`WORKFLOW_V0.md`
- schema 5 results：`results/validation_family_robustness_v0_schema5_mixed_heads/`
- publication companion：`results/figures/project_v0/validation_family_robustness_v0_schema5_head_focus/`
- internal homology benchmark：`benchmarks/plm_vs_classical_v0/`
- V0/V0.1 development audit：`benchmarks/ultra_remote_v0_v01/`
- frozen user inference：`/aptmp/hongda/DJRMCP_Develope/user-inference-V0`

完整 predictions、bootstrap、search databases、logs、TIFF 和 V0.1 development code 均保留在
`/aptmp/hongda/DJRMCP_Develope/` 的 checksum-bound archives；活动目录只保留 compact evidence core。
