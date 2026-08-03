<!-- i18n-mirror: non-authoritative translation; source=benchmarks/ultra_remote_v0_v01/figures/QA_REPORT.md -->

本译文仅供阅读；冻结的英文源文档为权威版本。

# 图表 QA 报告

- 核心结论与 panel hierarchy 符合 `FIGURE_CONTRACT.md`。
- Backend：仅使用 Python/matplotlib；准确版本记录在 `visualization_manifest.json` 中。
- Static source preflight：14 PASS，0 WARN，0 FAIL。
- 视觉检查：在两次 layout revision 后检查 final-size PNG；title、legend、axis-label、panel-label
  或 footer 均无重叠，也没有 mark 被裁切。
- 最终宽度：180.1 mm；声明的最小 text size：5.1 pt。
- Compact exports：editable-text SVG、TrueType-text PDF 和 300-dpi PNG preview；600-dpi TIFF
  仍在完整 archive 中受 checksum 约束。
- 数据完整性：未抽样或删除 observation。Panel b/c 中的 method subset 已预先声明以保证可读性；
  完整 method table 仍位于 `results/`。
- 统计：paired interval 对独立 evaluation components 重采样，threshold 固定自 calibration；
  calibration uncertainty 被排除并已注明。
- Specificity：当任一系统在至少一个 fold 中未达到实际 99.5% specificity 时，空心 marker 会明确
  降级该 pair。
- Low-FPR resolution：H2 与 end-to-end pAUROC 直接被抑制而非插值，因为每个 source 的
  independent-negative resolution 在 FPR 0.005 下不足。
- Sample-size gate：strict qcov >=80%、identity <20% 仅包含 n=1 个 component，展示为证据不足；
  不附 CI 或 superiority annotation。
- Source data 与每种 export 均通过 `visualization_manifest.json` 和 benchmark 级
  `CHECKSUMS.sha256` 进行 SHA-256 绑定。
