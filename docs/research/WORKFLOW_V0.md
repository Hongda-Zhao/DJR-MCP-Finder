# DJR-MCP Finder project V0：完整工作流

状态：主发布 **all ESM-C 6B 已冻结**；schema 5 Amendment D 是当前最宽的八模型／混合 Head 四来源
辅助分析；schema 4 保留为两模型连续性基线。两项 robustness 都不是独立 Test，也不能反馈 V0。

```text
data-curation V3 -> project V0
 -> 11,060 representatives
 -> component-safe Train / Validation / Test
 -> 14-model shared Train-CV
 -> Validation calibration + gates + paired one-SE
 -> freeze all ESM-C 6B
 -> user inference release
 -> post-freeze schema 4 / schema 5 diagnostics (read-only)
```

## 1. 三个级联 Head

```text
protein
 └─ H1: DJR?
     ├─ no  -> non_djr
     └─ yes -> H2: viral morphogenesis-associated?
               ├─ no  -> cellular DJR / none
               └─ yes -> H3: known phylum or reject
```

| Head | 训练范围 | 任务 | 主开发指标 |
| --- | --- | --- | --- |
| H1 | 全部蛋白 | DJR / non-DJR | AP |
| H2 | DJR | VMA-DJR / cellular DJR | AP；Validation 同时检查 macro-F1 |
| H3 | 两个样本充分的 VMA phyla | Nucleocytoviricota / Preplasmiviricota + reject | known-class macro-F1 |

H3 的 560 条 VMA-DJR 由 Nucleocytoviricota 415、Preplasmiviricota 117、Produgelaviricota 26 和
literature-unclassified 2 组成。前两类共 532 条参与已知类拟合；后 28 条只作 reject diagnostic。
`unknown/other` 表示“不强塞进两个已知类”，不表示发现新病毒或新 phylum。

## 2. 数据与 component-safe split

| source set | representatives | H1 | H2 |
| --- | ---: | --- | --- |
| VMA-DJR data-curation V3 | 560 | positive | positive |
| cellular DJR | 500 | positive | negative |
| hard non-DJR | 5,000 | negative | N/A |
| background non-DJR | 5,000 | negative | N/A |
| total | **11,060** | — | — |

上游 V3 有 564 个 official cluster rows；exact-sequence 去重后有 560 个建模正例。版本映射始终是
`data-curation V3 -> project V0`。

切分前将以下关系取传递闭包：

1. normalized exact-identical sequence；
2. 同 source cluster；
3. 已有 legacy/global component；
4. MMseqs2 identity≥30%、双向 coverage≥80% 的 qualifying relation。

完整 component 只能进入一个 split：

| split | records | DJR / non-DJR | VMA-DJR |
| --- | ---: | ---: | ---: |
| Train | 6,634 | 634 / 6,000 | 336 |
| Validation | 2,212 | 212 / 2,000 | 112 |
| Test | 2,214 | 214 / 2,000 | 112 |

全图有 27,427 nodes、9,262 个含建模代表的 global components；quarantined model representatives=0，
full-search residual qualifying cross-split edges=0。这个门槛降低强同源泄漏风险，但不证明 30% identity
以下不存在远同源。

## 3. 14-model benchmark

所有模型读取同一 manifest、split 和 Train-only `global_component_id` 5-fold map；checkpoint revision、
precision、窗口、stride、pooling 与 checksum 固定。超长序列必须滑窗覆盖全长，padding 和特殊 token
不进入 residue mean。

```text
S = 0.60 * CV H1 raw-score AP
  + 0.30 * CV H2 raw-score AP
  + 0.10 * CV H3 known-class macro-F1
```

Validation gate 要求任一 Head 相对 fresh ESM-2 650M baseline 的下降不超过 0.01。通过 gate 后使用共享
fold 的 paired one-SE；速度只在定义完全可比时作末级成本判据。

排序型指标必须使用 raw `decision_function`。旧 Figure 1a 曾用 sigmoid probability 计算 AP，饱和为
精确 0/1 后错误地产生 `0.857107`；同一 ESM-2 650M fold predictions 的 raw-score AP 为 `0.997917`。
这是数值修复，不是新数据或新生物学证据。

| model | rank | `S` | gate |
| --- | ---: | ---: | --- |
| **ESM-C 6B** | 1 | **0.997145** | PASS / selected |
| ESM-2 3B | 2 | 0.994873 | PASS |
| ESM-C 300M | 3 | 0.993444 | PASS |
| ESM-2 650M | 8 | 0.990376 | baseline PASS |

完整 14-model 表位于 `results/model_benchmark_v0_metric_revision_1/model_comparison.tsv`。

## 4. 校准、冻结参数与 Test 边界

Temperature 仅改变概率刻度，不改变 raw-score 排序。H1 threshold 在 Validation 最大化 MCC，H2 最大化
macro-F1；H3 reject threshold 只看 Validation 已知类，使 known acceptance 接近 0.95。rare/unclassified
记录不参与 H3 threshold 选择。

| Head | classifier | temperature | decision/reject threshold |
| --- | ---: | ---: | ---: |
| H1 | alpha=`1e-5` | 1168.1537298613255 | 0.9687754839244975 |
| H2 | C=`0.01` | 0.8241381150130028 | 0.9639353725025007 |
| H3 | C=`10` | 4.2474179687096845 | 0.7126488980564439 |

历史 2,214-record Test 只曾为 ESM-2 650M 打开。对同一冻结 prediction 的数值追溯为 H1 AP=0.998068、
AUROC=0.999724、FPR@95% recall=0；它们不能贴到 ESM-C 6B。当前 all-6B 与所有 schema 5 候选均为
`test_status=not_evaluated`。新 prospective/external Test 必须先冻结协议，再一次性打开。

## 5. HardNeg 来源恢复

用于 V0 的历史四批 DAG 已从冻结输入完整重放：

```text
172,346 raw
 -> 42,266 strict rows / 42,264 unique
 -> 36,138 Tier1 members
 -> 10,880 representatives
 -> 10,878 H1-negative pass + 2 quarantine
 -> 5,000 selected
```

93/93 search units 验证完成；A/B member map 一致；retained representatives、selected artifacts 与重建结果
逐字节或语义等价；G0–G6 7/7 PASS，状态为 `FULL_OPERATIONAL_RECOVERY_PASS`。较晚六批扩展的 57,708
Tier1 / 18,819 representatives 是独立探索，不属于 V0。

恢复结果只为 selected HardNeg clusters 提供 matched members，不改变 11,060 条代表、split、模型、参数或
Test。旧 5,878 pass-but-unselected representatives 是历史 unpaired sensitivity，不能冒充 selected-cluster
members。

## 6. schema 4：两模型连续性基线

schema 4 在冻结 all-6B 与 ESM-2 650M 上建立四来源、适用 Head 的 matched-family baseline：

| source | legal clusters / members / blocks | all-6B full path | ESM-2 650M |
| --- | ---: | ---: | ---: |
| viral | 69 / 13,054 / 32 | 0.9536 | 0.9325 |
| cellular | 43 / 391 / 12 | 0.8791 | 0.9997 |
| background | 1,000 / 3,000 / 893 | 0.9948 | 0.9974 |
| selected HardNeg | 382 / 3,478 / 237 | 0.9978 | 1.0000 |

四来源不汇总为总分。统计按 equal dependence block→source cluster→member，固定 seed 20260724，10,000
次 paired bootstrap。negative-only 来源只报告 specificity/FPR，不计算 AP、AUROC 或 F1。所有
member−representative delta 的 95% CI 都包含 0；all-6B 的主要弱点是 cellular H1。

schema 4 独立验证 PASS：22 endpoints 重算一致，predictions=92,844、expected paths=39,846、HardNeg
H2/H3=0、Test=0。它现在作为 schema 5 的 checksum-bound continuity baseline，而不是最新最宽结论。

## 7. schema 5：八模型与混合 Head

### 7.1 固定设计

schema 5 使用与 schema 4 相同的四来源合法 cohort，将昂贵扩展限制为原 14-model benchmark 中已满足固定
候选边界的 8 个模型：ESM-2 650M/3B、ESM-C 300M/600M/6B、ProtT5-XL-U50、ProstT5、ESM3-open
1.4B。

第一层是 8 个 homogeneous systems；第二层只有 9 个预注册 mixed candidates：

```text
H1=H2 in {ESM-2 650M, ESM-2 3B, ESM-C 6B}
H3    in {ESM-C 300M, ESM-C 600M, ESM-C 6B}
```

H1/H2 共用 encoder；只有通过 H1→H2 到达 viral 路径时才调用第二个 H3 encoder。没有搜索任意 8³
组合。候选 ordering 只使用既有共享 Train-CV `S`；robustness 仅检查相对 all-6B 的 source-specific
inferiority warning，并在每个来源内做 Holm 校正。

### 7.2 homogeneous 结果

| system | viral | cellular | background | matched HardNeg |
| --- | ---: | ---: | ---: | ---: |
| ESM-2 650M | 0.9325 | 0.9997 | 0.9974 | **1.0000** |
| ESM-2 3B | 0.8949 | **1.0000** | 0.9985 | 0.9998 |
| ESM-C 300M | 0.9060 | 0.9620 | 0.9907 | 0.9988 |
| ESM-C 600M | 0.9063 | 0.8790 | 0.9966 | **1.0000** |
| ESM-C 6B | 0.9536 | 0.8791 | 0.9948 | 0.9978 |
| ProtT5-XL-U50 | 0.9084 | 0.7960 | 0.9991 | 0.9958 |
| ProstT5 | 0.9078 | 0.9877 | 0.9989 | **1.0000** |
| ESM3-open 1.4B | **0.9685** | 0.8885 | 0.9989 | **1.0000** |

没有 homogeneous model 在四来源全胜；来源间取舍是真实的，不能用一个后验均值隐藏。

### 7.3 mixed nominee 与成本

| candidate | Train-CV `S` | always-on s·seq⁻¹ | worst-case s·seq⁻¹ |
| --- | ---: | ---: | ---: |
| **H1/H2 ESM-2 3B + H3 ESM-C 6B** | **0.997645** | **0.023524** | 0.083055 |
| all ESM-C 6B | 0.997145 | 0.059531 | **0.059531** |
| H1/H2 ESM-2 650M + H3 ESM-C 6B | 0.996813 | **0.007405** | 0.066935 |

nominee=`h12_esm2_3b__h3_esmc_6b`：

| source | expected path (95% CI) | strict clusters |
| --- | ---: | ---: |
| viral | 0.9537 (0.9131–0.9872) | 52/69 |
| cellular | 1.0000 (1.0000–1.0000) | 43/43 |
| background | 0.9985 (0.9963–1.0000) | 997/1,000 |
| matched HardNeg | 0.9998 (0.9995–1.0000) | 381/382 |

相对 all-6B 为 `0/4` Holm-corrected warnings，但这不是四来源 non-inferiority/equivalence 证明；viral
strict clusters 低于 all-6B 的 55/69，且 H3 worst-case 需运行两个 encoders。正式状态仅为
`recommended_for_external_confirmation`；
`released_v0_change_permitted=0`。

### 7.4 H3 边界

nominee H3 与 all-6B 相同：Nucleocytoviricota F1=0.9792，Preplasmiviricota F1=1.0000；
Produgelaviricota reject=6/7（2 parents/blocks），literature-unclassified=1/1（1 parent，无可估 CI）。
两组必须分开；pooled 7/8 只作 secondary diagnostic。

## 8. schema 5 完整性

- result status=`complete_eight_model_nine_candidate_four_source`；independent validation **20/20 gates PASS**，
  289 endpoints 重算一致；
- 18 个新 materialization receipts + 6 个 reuse attestations = 24/24；
- schema 4 的 92,844 keys、464,220 numeric strings 在冻结 Python 3.11.7／四线程数值算子下 exact replay，
  numeric/semantic/derived-decision mismatches=0；
- single-model predictions=371,376；system predictions=789,174；expected paths=338,691；
  bootstrap rows=680,000；Test records=0；
- Amendment D 对 predictions、thresholds、CV scores、candidate order 等 7 个正式合同 artifacts 与
  Amendment C 逐字节等价；H3 subgroup endpoints 由冻结 manifest 独立重算；
- compact result 17/17 checksum PASS；原 a–e figure package 11/11 PASS。活动主图采用只读的
  head-focus companion：top release 4/4、目录内 13/13 checksum PASS；56 Head endpoints、32 path cells、
  9 recipes、4 nominee diagnostics 与正式结果逐字段一致，不产生新科学结论。

Amendments A–D 的失败关闭、数值算子和显示合同细节保留在
`VALIDATION_FAMILY_ROBUSTNESS_V0_SCHEMA5_MIXED_HEADS_PROTOCOL.md`，不再重复写入主工作流。

## 9. 已完成的 PLM-vs-classical 内部 benchmark

### 9.1 设计与公平边界

该 benchmark 只使用 frozen Train 的 6,634 records。五个既有 `global_component_id` folds 循环承担
3-fit/reference、1-calibration 和 1-evaluation；同一轮的 reference/profile/model 不读取 calibration 或
evaluation。Validation/Test prediction rows 均为 0。

三项任务为 H1 DJR detection、H2 VMA|DJR 和 VMA end-to-end。Controlled primary 轨道中 ESM-C 6B
cosine、BLASTP、DIAMOND、MMseqs2 和 component-HMMER 共用相同 positive reference IDs；ESM-2 650M
是单独的 controlled PLM context。PSI-BLAST、metadata-family HMM 和每 outer fold 重拟合的 supervised
ESM-C 属于不同 supplementary/operational tracks，不混入 controlled headline。

Primary metrics：五 evaluation folds 的 component-balanced AP macro-average，以及在独立 calibration
fold 选择 99.5% specificity-target threshold 后的 evaluation sensitivity。99.9% 只作
`RESOLUTION_LIMITED_SECONDARY`，FP-per-million 不可估。

### 9.2 正式内部结果

| method | H1 AP / sens. | H2 AP / sens. | VMA e2e AP / sens. |
| --- | ---: | ---: | ---: |
| ESM-C 6B cosine | 0.8719 / 0.7340 | 0.9861 / 0.9306 | 0.9528 / 0.9301 |
| BLASTP | 0.9392 / 0.8692 | 0.9829 / 0.9443 | 0.9544 / 0.9401 |
| DIAMOND ultra | 0.9406 / 0.9025 | 0.9806 / 0.9317 | 0.9497 / 0.9317 |
| MMseqs2 | 0.9319 / 0.8805 | 0.9751 / 0.9119 | 0.9317 / 0.9078 |
| component-HMMER | 0.9542 / 0.9016 | 0.9911 / 0.9569 | 0.9660 / 0.9569 |
| ESM-2 650M cosine, context | 0.9515 / 0.8954 | 0.9965 / 0.9977 | 0.9906 / 0.9859 |

ESM-C cosine 相对四个 classical anchors 的 H1 AP 与 sensitivity delta 95% CI 均为负；H2 和 e2e 的
所有预注册 CI 均跨 0。这不支持“ESM-C cosine retrieval 已比经典工具更灵敏”。它也不等于冻结 supervised
V0 分类器的外部性能。

### 9.3 验证与限制

- validation=PASS；250,236 query-score rows、27 primary rows、12 paired deltas；Test/Validation rows=0；
- 点估计由独立实现重算；`bootstrap_recomputed=false`，validator 只校验 CI schema、范围、顺序、
  replicate count 和 registry，不能写成全部 10,000 bootstrap 被独立重放；
- fold 3 的 62 个 cellular negatives 只有一个 component；fold 2 的 119 VMA positives 只有 18 components，
  H2/e2e low-FPR intervals 因此 conditional/resolution-limited；
- equal task-specific references 不消除 PLM pretraining exposure unknown；
- 完整原始 release 的 20,424 项 checksum PASS。活动复制曾漏 3 个 figure source-data TSV；从冻结结果
  确定性重建后 SHA 与原清单逐项一致，compact figure release 已恢复完整。

内部 P0/development comparison 已完成；source-component-disjoint external lockbox、99.9% specificity/FPM
和更完整 PLMSearch/pLM-BLAST/hybrid 矩阵仍处于 prospective planned 状态。

## 10. V0/V0.1 ultra-remote 开发审计

V0.1 只把 H1/H2 encoder 换为 ESM-2 3B；H3 仍用 ESM-C 6B。它复用同一 Train-only cyclic cross-fit，
比较 raw cosine encoder 与相同 classifier family 的 task-adapted detector。

| endpoint | all holdout Δ(v0.1−v0) | `qcov<80%` | `qcov≥80%, 20–30% identity` |
| --- | ---: | ---: | ---: |
| H1 encoder sensitivity | +0.197 | +0.260 (0.206–0.317) | +0.046 (0.013–0.086) |
| H1 detector sensitivity | +0.017 | +0.028 (0.011–0.049) | 0.000 |
| H2 encoder sensitivity | +0.049 | +0.062 (0.020–0.112) | +0.024 (0.001–0.057) |
| H2 detector sensitivity | 0.000 | 0.000 | 0.000 |

encoder signal 没有等比例转化为 operational detector 增益。所有 paired systems 至少一个 fold 未达到实际
99.5% specificity；V0.1 H2 detector minimum-fold specificity=0.5426，V0 为 0.8599。严格
`qcov≥80%, identity<20%` 只有 1 个 independent positive component，低于预注册总计 100／每 fold 20
的门槛；BLAST-defined strata 本身还有方法条件化偏差。

validation 状态为 `PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE`：流程 PASS，但 matched-specificity、
external Test 和 formal ultra-remote claims 全部不成立。V0.1 development workflow 必须与 released V0
隔离。

## 11. 活动文件、归档与运行位置

| role | active path |
| --- | --- |
| frozen model benchmark | `results/model_benchmark_v0_metric_revision_1/` |
| schema 5 compact results | `results/validation_family_robustness_v0_schema5_mixed_heads/` |
| schema 5 publication companion | `results/figures/project_v0/validation_family_robustness_v0_schema5_head_focus/` |
| PLM/classical compact benchmark | `benchmarks/plm_vs_classical_v0/` |
| V0/V0.1 compact audit | `benchmarks/ultra_remote_v0_v01/` |
| frozen model identity | `results/model_benchmark_v0_metric_revision_1/esmc_6b/FROZEN_MODEL_CHECKSUMS.sha256` |
| released user inference V0 | `user-inference-v0/` |
| unreleased user inference V0.1 candidate | `user-inference-v0.1/` |
| portable root research entrypoints | `scripts/run_v0_dataset.py`; `scripts/run_postsplit_integrity_audit.py` |

以下完整 schema 5 和 schema 4 路径是原 gds2 generation 的冻结 provenance：

- `/aptmp/hongda/DJRMCP_Develope/project-V0__validation-family-robustness-schema5-mixed-heads__20260728/schema5_v1_amendment_d/`
- `/aptmp/hongda/DJRMCP_Develope/project-V0__validation-family-robustness-schema4__20260728/schema4_v1/`

PLM benchmark 的 7.6GB work/logs/databases 和 ultra-remote 大型 work/TIFF 位于 2026-07-29 日期化
checksum-bound archives。活动路径只保留协议、代码、正式摘要表、验证、PNG/PDF/SVG 与 source data。

GPU 用于 encoder embedding；统计、checksum 与多数校验为 CPU 工作。面向用户的两个包已经随 GitHub
检出提供，入口分别为：

```bash
cd user-inference-v0
bash scripts/run_user_fasta.sh INPUT.faa OUTPUT_DIR cuda

cd ../user-inference-v0.1
bash workstation/run_user_fasta.sh INPUT.faa OUTPUT_DIR GPU_INDEX
```

V0.1 仍是 `recommended_for_external_confirmation` 的候选包，不替代 V0。原
`/aptmp/hongda/DJRMCP_Develope/user-inference-V0` 与 `hongda-133:/lab/hongda/user-inference-V0`
只记录历史验证/部署位置，不是当前检出的运行依赖。新分析没有修改 V0 的模型、三 Head、temperature、
threshold、窗口或 pooling。

普通用户预测不依赖 PBS、`qsub` 或 HPC 调度器。

### 11.1 可移植路径与冻结 provenance

仓库可检出到任意绝对路径。非冻结的 launcher 使用 `DJRMCP_PROJECT_ROOT`、
`DJRMCP_ARCHIVE_ROOT`、`DJRMCP_DATABASE_ROOT`、`DJRMCP_SOFTWARE_ROOT` 与
`DJRMCP_VENV_ROOT`；缺省工程根由脚本位置推导。冻结 config 保留原始
`/aptmp/...` 值以维持来源与 checksum 语义，不应原地编辑。使用
`scripts/render_portable_config.py` 生成本地 JSON/YAML 副本，再通过 launcher 的 `*_CONFIG` 环境变量传入；
完整示例见 `README.md` 和 `.env.example`。

根目录的数据集构建与 split 后完整性审计分别由 `scripts/run_v0_dataset.py` 和
`scripts/run_postsplit_integrity_audit.py` 启动，无需 scheduler。`benchmarks/*/pbs/` 内与 checksum
绑定的 launcher 不属于普通运行入口；它们只作为可选的历史 HPC 重放证据保留，不应从 Benchmark
证据包中删除或改写。

GitHub 打包时，source-level manifests 已为上述可移植 launcher、文档与发布 allowlist 重新生成。
这不是重新计算科学结果：冻结模型、阈值、config、compact 数值证据及其内部 artifact checksums 保持不变；
原 gds2 入口的身份仍在日期化 archive provenance 中。

schema-5 Amendment D 的 exact-numeric replay 仍检查历史 Python/BLAS operator，其中的
`legacy_schema4_numerical_operator.venv_root` 是 provenance 合同而不是普通存储路径。非同一 attested
环境会 fail closed；这不影响阅读或校验仓库内 compact evidence。production Test ledger 也保持固定外部
管理员 registry，公开检出不能用路径覆盖来获得新的 Test 授权。

## 12. 可发表范围与下一版本门禁

V0 可报告：component-safe dataset、14-model development selection、冻结 all-6B 工具、schema 5
family-neighbour robustness，以及明确标为 Train-only 的内部 homology comparisons。不能报告：all-6B 或
V0.1 held-out Test performance、PLM 外部优于经典工具、formal ultra-remote superiority、普适 unknown
virus detection 或临床/诊断用途。

升级 V1 前必须冻结：

1. 与当前 Train/Validation family 独立、且 distance label 不由被比较方法定义的 external lockbox；
2. 足够的严格 `<20% identity` positive components（总≥100、每 fold≥20）；
3. source-specific endpoints、99.9% specificity/FPM、multiplicity 和 power；
4. all-6B 与 V0.1 的一次性 Test ledger及 accuracy/cost 接受规则；
5. external gates 通过后才允许修改发布模型和用户推理包。
