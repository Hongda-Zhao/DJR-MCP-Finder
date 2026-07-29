# Schema-5 Head-focus figure contract

状态：绘图合同；不改变模型、阈值、候选顺序或 robustness 数值。  
后端：Python/matplotlib only。  
目标尺寸：183 mm 双栏宽；SVG/PDF editable text，PNG 300 dpi，TIFF 600 dpi。

## Core conclusion

八个 homogeneous 模型的差异主要集中在 cellular DJR 的 H1 与 viral H3；混合系统
`H1/H2=ESM-2 3B + H3=ESM-C 6B` 先由共享 Train-only five-fold CV 选出，再由四来源同簇近亲作
选择后辅助检查，robustness 不参与重新排序。

## Archetype and evidence hierarchy

- archetype：quantitative grid + explanatory decision strip；
- hero evidence：逐 Head 的 56 个合法 model/source endpoint；
- validation evidence：8×4 whole-cascade expected-path accuracy；
- decision explanation：3×3 Train-CV 配方表 → 固定 Head 分工 → nominee 四来源检查；
- boundary：Validation-family diagnostic，Test accessed=0，V0 unchanged，external confirmation required。

## Panel map

### a — Head-by-head robustness

- 8 个 homogeneous models，固定相同行顺序；
- H1：viral/cellular positive sensitivity，background/HardNeg negative specificity；
- H2：viral positive sensitivity，cellular negative specificity；
- H3：viral expected-label accuracy；
- 点为 equal block→cluster→member member estimate，线为 95% dependence-block bootstrap CI；
- 共 8×(4+2+1)=56 行，不加入 9 个 mixed systems 的重复组件结果；
- 橙色只表示 Train-CV 已选组件：H1/H2 的 ESM-2 3B、H3 的 ESM-C 6B，不表示 robustness winner。

### b — Whole-cascade robustness

- 8 models × 4 sources 的 expected-path accuracy；
- 一个输入在该来源所有适用 Head 均正确才记 1；
- cell 显示 point estimate 与 95% CI；橙线显示 all-members-correct cluster proportion；
- 四来源不合并成总分。

### c — Choose, assign, then check

1. `3 H1/H2 encoders × 3 H3 encoders` 的 Train-CV `S ± fold SE` 配方表；
2. 显示冻结分工：ESM-2 3B 负责 H1/H2，ESM-C 6B 负责 H3；
3. 显示 nominee 的四来源 expected-path CI 与相对 all-6B 的 warning count。

公式固定为：

```text
S = 0.60 × H1 AP + 0.30 × H2 AP + 0.10 × H3 known macro-F1
```

panel c 必须直接写明：Train-CV 才是选择证据；four-source robustness 是选择后检查，不重排候选。

## Data and statistics contract

- result input：schema-5 Amendment D compact result，目录 `CHECKSUMS.sha256` 全部通过；
- benchmark input：metric-revision-1 comparison，comparison manifest 验证；
- CI：10,000 次固定种子 dependence-block bootstrap；
- weighting：equal dependence block → source cluster → member；
- no exclusions：56 head rows、32 path rows、9 candidate rows、4 nominee diagnostic rows 全部进入 Source Data；
- H1/H2 robustness 的 sensitivity/specificity 不得写成 AP；
- H3 robustness 的 expected-label accuracy 不得写成 Train-CV macro-F1；
- N/A Head 不生成 row，也不以 0 表示；
- 不生成跨来源或跨 Head 平均分。

## Reviewer risks and safeguards

1. ESM3-open 1.4B 的 family-neighbour H3 expected-label point estimate 可高于 ESM-C 6B；图中必须注明
   这是不同 cohort/endpoint 的选择后诊断，不能推翻 Train-CV 排序。
2. H2 cellular 的 1.000 是当前 cohort ceiling，不能表述为普适完美。
3. 13,054 等 member relations 不是独立重复；CI 的推断单位是 dependence block，并按 cluster/member
   嵌套加权。
4. H3 expected-label accuracy 不是普适 unknown detection；稀有 reject 的 n=7 与 n=1 仍以原 H3
   boundary panel 为准。
5. `0/4 warnings` 表示 Holm 校正后未建立 source-specific inferiority，不表示统计等价。
