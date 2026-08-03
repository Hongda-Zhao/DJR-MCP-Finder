<!-- i18n-mirror: non-authoritative translation; source=docs/VALIDATION_FAMILY_ROBUSTNESS_V0_SCHEMA5_HEAD_FOCUS_FIGURE_CONTRACT.md -->

> **翻訳について：** この翻訳は閲覧用です。凍結済みの中国語原文を正式版とします。

# Schema-5 Head-focus 図の仕様

ステータス：作図仕様。モデル、閾値、候補の順序、robustness 値は変更しません。
バックエンド：Python/matplotlib only。
目標サイズ：183 mm の二段組幅。SVG/PDF は編集可能なテキスト、PNG 300 dpi、TIFF 600 dpi。

## 中心的な結論

八つの homogeneous モデル間の差は、主として cellular DJR の H1 と viral H3 に集中します。混合
システム `H1/H2=ESM-2 3B + H3=ESM-C 6B` は、最初に共通の Train-only five-fold CV で選択され、
その後、四つの情報源に由来する同一クラスター内の近縁配列によって、選択後の補助チェックを
受けます。robustness は再順位付けには使用しません。

## アーキタイプとエビデンス階層

- archetype：quantitative grid + explanatory decision strip；
- hero evidence：Head ごとの 56 個の有効な model/source endpoint；
- validation evidence：8×4 の whole-cascade expected-path accuracy；
- decision explanation：3×3 Train-CV レシピ表 → 固定された Head 分担 → nominee の四情報源チェック；
- boundary：Validation-family diagnostic、Test accessed=0、V0 unchanged、external confirmation required。

## パネル構成

### a — Head ごとの robustness

- 8 個の homogeneous models を、同じ固定行順で表示；
- H1：viral/cellular positive sensitivity、background/HardNeg negative specificity；
- H2：viral positive sensitivity、cellular negative specificity；
- H3：viral expected-label accuracy；
- 点は equal block→cluster→member member estimate、線は 95% dependence-block bootstrap CI；
- 合計 8×(4+2+1)=56 行。9 個の mixed systems に由来する重複 component results は追加しない；
- オレンジ色は Train-CV で選択済みの components、すなわち H1/H2 の ESM-2 3B と H3 の ESM-C 6B
  だけを示し、robustness winner を意味しない。

### b — Whole-cascade robustness

- 8 models × 4 sources の expected-path accuracy；
- 入力は、その情報源に適用されるすべての Head が正しい場合にだけ 1 とする；
- cell には point estimate と 95% CI を表示し、オレンジ線には all-members-correct cluster proportion
  を表示する；
- 四つの情報源を統合した総合スコアは作らない。

### c — 選び、割り当て、その後に確認する

1. `3 H1/H2 encoders × 3 H3 encoders` の Train-CV `S ± fold SE` レシピ表；
2. 凍結済みの分担、すなわち ESM-2 3B が H1/H2、ESM-C 6B が H3 を担当することを示す；
3. nominee の四情報源 expected-path CI と、all-6B に対する warning count を示す。

式は次のとおり固定します。

```text
S = 0.60 × H1 AP + 0.30 × H2 AP + 0.10 × H3 known macro-F1
```

panel c には、Train-CV だけが選択エビデンスであり、four-source robustness は選択後チェックであって
候補を再順位付けしないことを、直接明記する必要があります。

## データと統計の仕様

- result input：schema-5 Amendment D compact result。ディレクトリの `CHECKSUMS.sha256` はすべて合格；
- benchmark input：metric-revision-1 comparison。comparison manifest を検証済み；
- CI：固定 seed による dependence-block bootstrap を 10,000 回；
- weighting：equal dependence block → source cluster → member；
- no exclusions：56 head rows、32 path rows、9 candidate rows、4 nominee diagnostic rows のすべてを Source Data に含める；
- H1/H2 robustness の sensitivity/specificity を AP と表現してはならない；
- H3 robustness の expected-label accuracy を Train-CV macro-F1 と表現してはならない；
- N/A Head は row を生成せず、0 としても表現しない；
- 情報源間または Head 間の平均スコアを作らない。

## レビュアー向けのリスクと安全策

1. ESM3-open 1.4B の family-neighbour H3 expected-label point estimate は ESM-C 6B より高くなり得ます。
   図には、これが異なる cohort/endpoint に対する選択後診断であり、Train-CV の順位を覆すことは
   できないと明記する必要があります。
2. H2 cellular の 1.000 は現在の cohort における ceiling であり、普遍的な完全性と表現しては
   なりません。
3. 13,054 などの member relations は独立した反復ではありません。CI の推論単位は dependence block
   であり、cluster/member による入れ子の重み付けを行います。
4. H3 expected-label accuracy は普遍的な unknown detection ではありません。稀な reject の n=7 と n=1
   については、引き続き元の H3 boundary panel に従います。
5. `0/4 warnings` は、Holm 補正後に source-specific inferiority が確立されなかったことを示します。
   統計的同等性を意味するものではありません。
