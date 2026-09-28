# 短序列 benchmark v1

[English](README.md) | **简体中文** | [日本語](README.ja.md)

状态（2026-09-28）：**已复用历史 embedding，在 CPU 上完成原始长度分层评测；
配对截短实验仍待完成。**本 benchmark 用有标签的蛋白检验 DJR-MCP-Finder 的短片段能力，
不使用实际应用中的候选预测充当真值。V0.1 Candidate 是后续 V0.2 的基线，V0 作历史对照。

## 原始长度结果（2026-09-28）

两个编码器均命中全部 6,634 条 Train 序列，共复用 13,268 个向量，不进行 GPU 编码。
已附上[指标表](results/observed_length_20260928/metrics.tsv)和
[结果图](results/observed_length_20260928/observed_length.pdf)。

| 输入长度（aa） | MCP 数量 | V0.1 方案 MCP 召回率 | 非 MCP 数量 | V0.1 方案误报数 |
|---|---:|---:|---:|---:|
| <130 | 0 | NA | 0 | NA |
| 130–149 | 0 | NA | 1 | 0 |
| 150–199 | 0 | NA | 278 | 0 |
| 200–249 | 0 | NA | 280 | 0 |
| 250–299 | 13 | 13/13（100%） | 482 | 0 |
| >=300 | 323 | 318/323（98.45%） | 5,257 | 0 |

关键限制是 **250 aa 以下没有 MCP 阳性**，因此不能估计该范围的 MCP 召回率，
也不能据此确定最短可用长度。13/13 的样本量很小，零观测误报也不代表总体误报率
为零。V0 的汇总 MCP 召回率相同，在 200–249 aa 有 1 个误报、>=300 aa 有 2 个。
这仍是内部 component 交叉验证，不是发布分类头的独立外部测试。配套截短实验仅对
新增片段进行 GPU 编码。


## 复用历史 embedding：先运行 CPU 原始长度分层评测

`prepare --mode observed` 只保留原始 Train 序列，不生成片段。七个长度区间全部
保留；没有样本时记为 NA，不能解释为召回率为零。不同区间包含不同蛋白和来源组成，
因此这项分析不能单独证明截短同一条蛋白的因果影响。

```bash
python3 benchmarks/short_sequence_v1/benchmark.py prepare --mode observed --out run/observed
python3 benchmarks/short_sequence_v1/benchmark.py reuse --run run/observed --encoder esm2_3b --source /path/to/v0_benchmark_esm2_3b --require-complete
python3 benchmarks/short_sequence_v1/benchmark.py reuse --run run/observed --encoder esmc_6b --source /path/to/v0_benchmark_esmc_6b --require-complete
python3 benchmarks/short_sequence_v1/benchmark.py score --run run/observed
python3 benchmarks/short_sequence_v1/benchmark.py summarize --run run/observed
python3 benchmarks/short_sequence_v1/benchmark.py validate --run run/observed
python3 benchmarks/short_sequence_v1/benchmark.py plot --run run/observed
```

上述步骤需要 NumPy、scikit-learn、PyYAML、Matplotlib，不加载蛋白语言模型，
不需要 Torch 或 GPU。复用前校验文件哈希、模型 commit、计算精度、pooling、窗口、
特殊 token 规则和 adapter 配置。按序列 SHA-256 与长度匹配，**只导入 Train 行**，
不依赖旧蛋白 ID。历史 bundle 中的 Validation/Test 向量及标签不参与拟合、校准或
评价；原始缓存保持不变，已有目标 bundle 不覆盖。

截短实验使用默认 `--mode truncation`：同样先执行 `reuse`，去掉
`--require-complete`，再执行 `embed`。命中的向量已经标记完成，只补算缺失序列。
`reuse/*.json` 和映射表独立记录来源校验值与行对应关系，编码续跑不会覆盖它们。
脚本变化必须准备新运行目录。绘图生成 `observed_length.png/.pdf/.svg`；截短实验
另外生成 `length_curves`。


## 设计

- 只用冻结的 6,634 条 Train 蛋白和既有五折 component 划分，校验 Train manifest、
  FASTA、fold map 与编码器 registry 的 SHA-256；不导入或评分 Validation/Test；历史混合 split 缓存仅校验容器并选取 Train 行。
- 每轮用三折完整蛋白拟合、一折完整蛋白校准、一折的完整蛋白与片段评价。母序列
  及所有片段继承同一 component/fold；每个 component 只作一次评价。
- V0 使用 ESM-C 6B 的 H1/H2，V0.1 Candidate 使用 ESM-2 3B。H3 每折在许可的
  ESM-C 6B 完整训练蛋白上拟合一次，两种方法共用。编码器版本、pooling、精度、
  分类器类型和超参数固定。
- 这是模型方案的**分折重拟合**，不是让发布版分类头识别自己的训练片段，不能
  宣称独立外部性能，也不会改变现有权重或模型选择。
- H1 在校准组优化 MCC，H2 在真实 DJR 校准蛋白上优化 macro-F1，直接对 raw
  score 选阈值以避免 sigmoid 饱和；同分选较高阈值，包含全部拒绝的候选阈值。
  一折的所有长度和位置共用阈值。
- H3 仅学习两个已知门，用完整已知类校准蛋白的绝对 logit 下 5% 分位点作为
  拒绝阈值，目标为至少 95% 已知类接受率。二分类绝对 logit 与任何正温度下的
  置信度排序一致；本实验不把分数宣称为校准后的后验概率。

## 片段与分母

主分析固定同一批长度 >=300 aa 的母序列，生成 **50、100、130、150、200、250、
300 aa** 片段及完整对照。正负例规则完全相同。每个长度生成 N 端、C 端、一个
均匀抽样的严格内部片段；哈希派生的随机种子与输入顺序无关。坐标从 0 起、右端
不包含。不存在内部起点时不补造片段；300 aa 母序列的两个 300 aa 端部视图均
等于完整序列。相同序列只计算一次 embedding，评价视图仍保留。

保留母序列、component、来源类别、片段位置、原长、剩余比例、序列哈希和排除
原因。小于 300 aa 的母序列不进入主配对曲线，但保留在完整输入长度分层中。
生成片段若与另一折的查询（含完整输入）出现完全相同序列，会将有关母序列从
**所有配对长度及完整对照**中一起排除。该检查只能识别精确碰撞，不能证明不存在
其他远同源关系；排除发生在评分前。

阳性片段指“来源于 MCP”，不代表片段拥有完整 DJR 结构或生物学功能。50/100 aa
位于已记录训练长度范围之外，作为压力测试。完整输入按 <100、100–129、130–149、
150–199、200–249、250–299、>=300 aa 另表报告；这些短输入也未必是经实验确认的
天然完整短蛋白。

主指标是 H1 AND H2 的 MCP 召回率和假阳性率。`mcp::unknown/other` 仍算检出
MCP。阴性分为 cellular DJR、困难 non-DJR、普通背景，并分别报告；总体 FPR 只
对应本评测的来源组成，不是实际筛查的假发现率。

H1/H2 漏检、H3 各门端到端召回率、通过 H1/H2 后的门分类准确率、错分率与拒绝率
另列。H2 诊断使用全部真实 DJR，H3 条件指标只用通过 H1/H2 的 MCP；端到端指标
则把上游漏检留在分母。unknown 拒绝只作小样本诊断。

先在母序列内平均片段结果，再对母序列平均；按完整 component 重采样 2,000 次
得到 95% CI，同时报告片段数、母序列数与独立 component 数。只有一个 component
不提供 CI；零错误形成的退化区间会标记，不能证明总体错误率为零。区间不包含
重新拟合模型或预训练的不确定性。配对差值包括“该长度减完整”和“V0.1 减 V0”，
只使用两边都有合法分母的母序列。H3 条件分母会随门禁变化，应优先看端到端指标。

## 执行

GitHub 不分发原始 Train FASTA；在包含冻结数据的项目目录运行。准备仅需 Python
3.10+。gds2 的四项输入校验和已于 2026-09-28 核对一致。

```bash
cd /path/to/DJR-MCP-Finder
python3 benchmarks/short_sequence_v1/benchmark.py prepare \
  --project-root /path/to/DJR-MCP-Finder \
  --out benchmarks/short_sequence_v1/run/production_v1
```

`prepare` 拒绝非空输出目录；修改协议或脚本应创建新 run。接着在已分配的 GPU
上，用既有的两个兼容环境分别生成特征，不能在登录节点运行。ESM-C 需要项目
固定的 Transformers 实现，ESM-2 使用它自己的环境。变量填写对应 Python 路径。

```bash
"${ESMC_PYTHON:?设置 ESM-C 环境 Python}" benchmarks/short_sequence_v1/benchmark.py embed \
  --run benchmarks/short_sequence_v1/run/production_v1 --encoder esmc_6b --device cuda
"${ESM2_PYTHON:?设置 ESM-2 环境 Python}" benchmarks/short_sequence_v1/benchmark.py embed \
  --run benchmarks/short_sequence_v1/run/production_v1 --encoder esm2_3b --device cuda
```

可先加 `--limit 2` 验证 GPU，再去掉参数续跑。未完成、损坏或 checkpoint 不符的
embedding 不允许评分。每个片段需要重新编码，不能切割完整蛋白的平均向量。

两种 embedding 完成后，在原 CPU 分类环境运行：

```bash
python benchmarks/short_sequence_v1/benchmark.py score --run benchmarks/short_sequence_v1/run/production_v1
python benchmarks/short_sequence_v1/benchmark.py summarize --run benchmarks/short_sequence_v1/run/production_v1
python benchmarks/short_sequence_v1/benchmark.py validate --run benchmarks/short_sequence_v1/run/production_v1
```

也可显式提交已使用 gds2 原归档 CPU 环境的作业：

```bash
qsub benchmarks/short_sequence_v1/pbs/score_gds2.pbs
```

本地安装 `.[figure]` 后，可单独执行 `plot --run ...` 输出 PNG/PDF；不会自动画图。
`scores/` 保存逐片段预测、阈值和每折合同；`results/` 保存 `metrics.tsv`、
`paired_deltas.tsv`、`REPORT.md` 和可选曲线；`inputs/` 保存样本清单、排除与覆盖
统计。所有 run 文件默认不提交 Git。漏掉预测行会报错，不能只统计成功推理的样本。

CPU 测试：`python -m pytest -q tests/test_short_sequence_benchmark.py`。
测试使用人工特征验证流程，不能代替 GPU 验证或真实性能结果。下一版模型的设计见
[V0.2 方案](../../docs/research/MODEL_V02_DESIGN.cn.md)。

## MCP 阳性长度统计

整理后的全量数据含 560 条 MCP 阳性：Train 336、Validation 112、Test 112。
[全量长度统计](results/mcp_positive_lengths_all_20260928/summary.tsv)与
[分布图](results/mcp_positive_lengths_all_20260928/mcp_positive_lengths.pdf)仅描述元数据，
不对保留集进行模型评分。全量阳性长 254–2,906 aa，中位数 473 aa；250–299 aa 有
22 条，250 aa 以下没有阳性。应与仅含 Train 的 benchmark 数量区分。

复现：`python3 benchmarks/short_sequence_v1/length_statistics.py --parents data/processed/v0/master_manifest.tsv --scope all --out benchmarks/short_sequence_v1/run/lengths_all`。

## 按 250–500+ aa 的 50 aa 区间重新汇总 benchmark

[新分组指标表](results/length_bins_250_500_20260928/confusion_by_length.tsv)与
[结果图](results/length_bins_250_500_20260928/visualization_en_v2/overview.en.pdf)复用原有 Train
交叉验证预测，不修改模型、阈值或划分。区间按左闭右开定义为 250–299、300–349、
350–399、400–449、450–499、>=500 aa，并保留 <250 aa 作为补充诊断。
V0.1 的 MCP 检出数依次为 13/13、14/15、38/38、75/77、71/71、120/122。
6,298 条非 MCP 中没有观测误报，但不能解释为总体误报率为零。最短两组分别只有
13 和 15 个阳性，且各长度的家族组成不同，不能确定单调的长度效应或最佳截断值。

<250 aa 的 MCP 预测超出了本整理数据集的阳性长度覆盖范围，其正确性与分数校准
尚未在该范围验证；没有参考阳性并不证明这些预测全是假阳性。559 条短负例未出现
误报，也不能估计短阳性检出能力或实际应用中的阳性预测值。本次不新增推理硬拒绝规则。

```bash
python3 benchmarks/short_sequence_v1/length_bins_report.py --run benchmarks/short_sequence_v1/run/observed_production_20260928 --out benchmarks/short_sequence_v1/run/length_bins_250_500_new
```

这是首轮分析之后按用户要求作的描述性重分组。全量长度统计含 560 条阳性；这里的
性能评价仍使用 336 条 Train 阳性。

### 英文可视化更新

主图将召回率色条与检出/阳性数、漏检数和误报数逐行对齐；
[V0 对照与置信区间](results/length_bins_250_500_20260928/visualization_en_v2/comparison.en.pdf)及
[门分类细节](results/length_bins_250_500_20260928/visualization_en_v2/phylum_detail.en.pdf)分为补充图。
所有图内文字为英文，原有指标表和预测未修改。
