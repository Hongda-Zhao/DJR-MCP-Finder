# 图怎么读

## a：逐个 Head 看

每个点是一种模型在一个合法来源上的正确决策率，横线是 95% CI，越靠右越好。H1 有四个合法来源，
H2 有两个，H3 只有 viral。橙色只是标出 Train-CV 已经选定的组件，不表示用本图重新选模。

## b：看整条工具路径

一个输入在该来源所有应运行的 Head 都答对，才算 expected path 正确。格内是点估计和 95% CI；橙线是
“整个 cluster 的所有近亲都正确”的 cluster 比例。

## c：按 1 → 2 → 3 阅读

1. 只用 Train 的五折 CV 比较 3×3 种配方；每格是 S ± fold SE。
2. 最高的预注册配方把 H1/H2 交给 ESM-2 3B，把 H3 交给 ESM-C 6B。
3. 选定后才检查四来源同簇近亲；0/4 warning 只表示没有建立相对 all-6B 的来源特异劣势，不能证明等价。

重要边界：robustness 没有参与候选排序；Test accessed=0；冻结 V0 没有改变，仍需外部/前瞻确认。
ESM3-open 1.4B 在本次 H3 family-neighbour expected-label accuracy 上点估计较高，但这不是 Train-CV
known macro-F1，也不是同一个证据层，不能用来事后重排。
