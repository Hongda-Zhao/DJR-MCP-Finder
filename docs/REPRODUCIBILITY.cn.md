# 可复现性层级与归档边界

[English](REPRODUCIBILITY.md) | **简体中文** | [日本語](REPRODUCIBILITY.ja.md)

[文档导航](README.cn.md) | [仓库 README](repository/README.cn.md) |
[科研证据](SCIENTIFIC_EVIDENCE.cn.md)

在本项目中，“可复现”包含三种不同含义：验证公开 checkout、利用公开模型 checkpoint 重复一次用户预测，或使用冻结归档与可移植 Python 入口重放科研流程。下文有意分别说明各自要求；原始 PBS launcher 是历史重放证据，不是公开默认入口。

## 范围概览

| 层级 | 仅凭公开 checkout 即可？ | 可复现的内容 | 额外要求 |
| --- | --- | --- | --- |
| A — Checkout 验证 | 是 | 元数据、文档、测试、FASTA 验证、bundle 身份和包构建 | Python 3.12+ 及声明的依赖项 |
| B — 公开用户推理 | 否 | 使用用户 FASTA 完成一次真实的 V0 或 V0.1 预测 | 固定的公开 checkpoint；经过验证并推荐的工作站路径：Linux、Docker 和 CUDA GPU |
| C — 依赖归档的科研重放 | 否 | 数据集构建、embedding、模型选择和内部 Benchmark 流程 | 冻结的私有归档/数据库、checksum、Python 及 MMseqs2 等版本化工具；仅重放历史 launcher 时才需要 HPC |
| 受保护的 Test 评估 | 否 | 经管理员授权的预注册 Test 运行 | 受保护 ledger 和单独授权；仅拥有归档与 HPC 仍不充分 |

这个精简的 GitHub 仓库不会重新分发全部原始数据库、模型 checkpoint、大型 embedding、日志、TIFF 文件或历史运行输出。

## Level A — 验证公开 checkout

以下路径无需下载任何大型 encoder，也无需 GPU，即可检查代码和冻结包约定：

```bash
cd /path/to/DJR-MCP-Finder
python3.12 -m venv .venv
source .venv/bin/activate

make setup
make metadata docs-check lint test smoke
```

`make smoke` 会运行 FASTA 验证和 `model-info`，但不会执行预测。如需同时进行 wheel/sdist 构建并运行所有本地 CI 等价门槛，请执行：

```bash
make check
```

规范 target 定义位于仓库的 [`Makefile`](../Makefile) 中。Level A 验证通过，说明 checkout 与精简 bundle 在内部保持一致；这并不能证明生物学准确性或外部泛化能力。

## Level B — 重复一次公开用户预测

用户推理不需要私有科研归档。

用户推理也不需要 PBS、`qsub` 或 HPC 调度器；PBS 不属于任何一版公开预测接口。

经过验证并推荐的工作站路径为 Linux + Docker + CUDA GPU。两个包也明确提供自动/CPU 设备模式，但高内存 CPU fallback 未包含在正式工作站验证中，因此不应被视为参考可复现路径。

- **优先实验候选：** 请遵循 [Model V0.1 Candidate 用户指南](../user-inference-v0.1/README.md)和[首次克隆后的工作站配置](../user-inference-v0.1/workstation/README.md#fresh-clone-setup)。首次预测会下载 ESM-2；当至少一条序列进入 H3 时才会下载 ESM-C。
- **已发布基线：** 请遵循 [Model V0 用户指南](../user-inference-v0/README.md)和 [V0 工作站配置](../user-inference-v0/workstation/README.md)。首次预测会下载固定的 ESM-C checkpoint。

两条路径都会生成 `predictions.tsv`、`run_metadata.json` 和 `CHECKSUMS.sha256`。只有在该输入路径需要的所有 checkpoint 都已缓存后，后续才可在禁用网络的条件下运行。重复用户推理可以验证冻结的模型/运行时路径；它不会重放训练数据、模型选择或 Benchmark。

## Level C — 重放依赖归档的科研流程

完整重放需要公开 checkout 中没有提供的资源：

- checksum 匹配的源数据库以及精简/完整 artifact 归档；
- 冻结配置所引用的模型 embedding 和原始 Benchmark ledger，以及存在时 `FULL_ARTIFACT_POINTER.json` 文件所引用的内容；
- 有记录的 Python、CUDA、MMseqs2 和其他版本化软件环境；
- 与所选阶段匹配的本地或 HPC 计算资源。只有主动重放原始、与 checksum 绑定的 Benchmark launcher 时才需要 PBS/HPC。

### 本地化历史路径

冻结配置中的历史绝对路径作为溯源信息保留。请生成一份站点本地副本，而不要修改冻结输入：

```bash
cd /path/to/DJR-MCP-Finder

export DJRMCP_PROJECT_ROOT="$(pwd -P)"
export DJRMCP_ARCHIVE_ROOT=/absolute/path/to/checksum-bound-archives
export DJRMCP_DATABASE_ROOT=/absolute/path/to/frozen-input-databases
export DJRMCP_SOFTWARE_ROOT=/absolute/path/to/versioned-HPC-software
export DJRMCP_VENV_ROOT=/absolute/path/to/project-python-environment

python3 scripts/render_portable_config.py \
  configs/v0_dataset.json \
  build/local-configs/v0_dataset.json
```

这些变量是本地资源定位符，而不是下载 URL 或凭据。renderer 会重写已声明的路径前缀；它不会下载文件，也不会证明映射的资源确实存在。映射后的输入必须已经存在，并与冻结 checksum 匹配。

### 运行可移植的 Python 科研入口

数据集构建需要 Python 和 MMseqs2，但不需要 PBS 或 Environment Modules。runner 会拒绝覆盖已有输出目录，因此请使用尚不存在的明确路径：

```bash
python3 scripts/run_v0_dataset.py \
  --config build/local-configs/v0_dataset.json \
  --work-dir build/replay/v0-interim \
  --output-dir build/replay/v0-processed

python3 scripts/run_postsplit_integrity_audit.py --help
```

第二条命令会列出可移植 split 后审计所需的 manifest、FASTA 输入和输出目录。两个 runner 都接受 `--python` 和 `--mmseqs` 覆盖，否则使用本地可执行文件。Benchmark 重放仍需要冻结配置所引用的归档 embedding、ledger 和存在时的 `FULL_ARTIFACT_POINTER.json`。与 checksum 绑定的 `benchmarks/*/pbs/` launcher 只是可选的历史 HPC 重放证据，不是普通入口；保留原样可维持冻结证据包的身份。

## 冻结溯源与完整性

- `/aptmp/hongda/DJRMCP_Develope/` 下的历史路径和记录的主机是溯源信息或归档定位符，而不是普通用户推理的运行时要求。
- 冻结模型 bundle 会在加载分类器 head 前验证其 `CHECKSUMS.sha256`。
- 用户预测会为输出和运行元数据附带 `CHECKSUMS.sha256`。
- 精简 Benchmark 和 Release 证据会保留其所属的 checksum manifest。
- 模型 checkpoint 从固定的上游身份下载，不在这里重新分发。
- Checksum 只能确定内容身份，不能证明作者身份或传输安全。

不要批量替换冻结配置、验证记录、报告或 artifact pointer 中的历史路径。特别是，`legacy_schema4_numerical_operator.venv_root` 属于 Amendment-D 的精确数值重放约定。修改冻结 bundle 内的 notice 或模型卡文件，需要刷新该 bundle 的 checksum manifest 并重新运行 `model-info`。修改权重、阈值、路由或 encoder，则需要根据 [`VERSIONING.md`](VERSIONING.md) 建立新的科学模型身份。

## 受保护的 Test 边界

仓库包含一个仅运行已选模型的 Test runner，但公开 checkout 或路径覆盖无法授予访问权限。生产 ledger 固定在外部管理员 registry 中并拒绝覆盖；运行仍需获得 registry 权限以及对冻结输入和流程的授权。仅拥有归档、软件栈或 HPC 访问权限，并不等于获得 Test 运行授权。

## 可复现性入口

- [完整科研流程](research/WORKFLOW_V0.md)
- [科研证据与结论边界](SCIENTIFIC_EVIDENCE.md)
- [正式 V0 参考环境](../user-inference-v0/environment/REFERENCE_ENVIRONMENT.md)
- [Candidate 参考环境](../user-inference-v0.1/environment/REFERENCE_ENVIRONMENT.md)
- [正式 V0 工作站验证](../user-inference-v0/workstation/VALIDATION.json)
- [Candidate 工作站验证](../user-inference-v0.1/workstation/VALIDATION.json)
- [仓库 Release 清单](../release-manifest.json)
