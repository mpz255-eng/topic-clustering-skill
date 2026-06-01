# 主题聚类分析工具

对中英文文本做分词、向量化、聚类，输出带簇标签的 Excel 和每簇 Top N 关键词。

支持 **KMeans**、**层次聚类**、**LDA** 三种方法，含肘部法辅助选 K。

---

## 功能

- 中英文自动检测与预处理（jieba 中文分词 / spaCy 英文词形还原）
- TF-IDF 向量化
- 三种聚类方法：KMeans（+ 肘部法选 K）、层次聚类（+ 树状图）、LDA 主题模型
- 逐簇关键词提取（TF-IDF centroid）和**高频词统计**（原始词频 + 频次）
- 逐簇交互式三选一命名
- 输出 Excel 文件，含原始数据标注、簇关键词、簇高频词、簇统计四个 sheet
- 可选：每簇词云图生成

---

## 安装

### 方式一：Claude Code Skill 安装（推荐）

在 Claude Code 对话中直接说：

> "帮我安装 topic-clustering skill，从 https://github.com/mpz255-eng/topic-clustering-skill"

或者手动安装：

```bash
# 1. 克隆到 Claude Code skills 目录
git clone https://github.com/mpz255-eng/topic-clustering-skill \
  ~/.claude/skills/topic-clustering

# 2. 安装 Python 依赖
pip install -r ~/.claude/skills/topic-clustering/requirements.txt

# 3. 安装 spaCy 英文模型（处理英文文本时需要）
python -m spacy download en_core_web_sm
```

安装后，在 Claude Code 对话中说出以下关键词即可自动触发 skill：

> "主题聚类"、"文本聚类"、"KMeans聚类"、"LDA主题模型"、"层次聚类文本"、"文本自动分组"、"给这些新闻分个类"……

Skill 会以**交互式向导模式**运行：检测语种 → 预处理 → 向量化 → 选 K → 聚类 → 逐簇命名 → 导出。

### 方式二：命令行独立使用

```bash
git clone https://github.com/mpz255-eng/topic-clustering-skill.git
cd topic-clustering-skill
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

完整 CLI 流程：

```bash
WORKSPACE="./workspace"
DATA="./examples/sample_news.xlsx"
TEXT_COL="content"

# 1. 语言检测
python cluster.py detect --input "$DATA" --text-col "$TEXT_COL"

# 2. 预处理（分词 + 去停用词）
python cluster.py preprocess \
  --input "$DATA" --text-col "$TEXT_COL" \
  --output "$WORKSPACE/preprocessed.pkl"

# 3. TF-IDF 向量化
python cluster.py vectorize \
  --input "$WORKSPACE/preprocessed.pkl" \
  --output "$WORKSPACE/vectorized.pkl"

# 4. 肘部法（辅助选 K）
python cluster.py elbow \
  --input "$WORKSPACE/vectorized.pkl" \
  --output "$WORKSPACE/elbow.png" \
  --k-range 3 20

# 5. 执行聚类（KMeans, K=8）
python cluster.py fit \
  --input "$WORKSPACE/vectorized.pkl" \
  --texts "$WORKSPACE/preprocessed.pkl" \
  --method kmeans --k 8 \
  --output "$WORKSPACE/model.pkl" \
  --labels-output "$WORKSPACE/labels.csv"

# 6. 导出结果（可选传 --cluster-names 命名簇）
python cluster.py export \
  --input "$DATA" --text-col "$TEXT_COL" \
  --labels "$WORKSPACE/labels.csv" \
  --keywords "$WORKSPACE/model.pkl" \
  --output "./聚类结果.xlsx" \
  --cluster-names '{"0":"版权声明（噪声）","1":"AI安全与法律规制",...}'
```

---

## 输出

Excel 文件包含 4 个 sheet：

| Sheet | 内容 |
|---|---|
| 原始数据 | 原始数据 + `cluster_label` + `cluster_name` |
| 簇关键词 | 每簇 TF-IDF centroid Top 30 关键词 |
| 簇高频词 | 每簇 Top 20 高频词 + 频次 |
| 簇统计 | 每簇文档数、占比 |

---

## 聚类方法

| 方法 | 原理 | 适用场景 |
|---|---|---|
| KMeans | 距离最小化，球形簇 | 大多数场景，速度快，首选 |
| 层次聚类 | 自底向上合并最相似簇 | 探索层级结构，数据量 < 500 |
| LDA | 概率生成模型 | 长文本（论文、报告），软分类 |

详见 [references/algorithm-guide.md](references/algorithm-guide.md)。

---

## 实际案例

使用本工具对中国日报（China Daily）2015-2026 年 1424 篇 AI 主题英文报道做 KMeans 聚类（K=12），产出 12 个主题簇：

| 簇 | 命名 | 篇数 | 占比 |
|---|---|---|---|
| 0 | 版权声明（噪声） | 12 | 0.8% |
| 1 | AI安全与法律规制 | 76 | 5.3% |
| 2 | 国际AI治理与合作 | 88 | 6.2% |
| 3 | 大模型产品与消费应用 | 171 | 12.0% |
| 4 | 自动驾驶与智能出行 | 54 | 3.8% |
| 5 | 产业数字化与智能制造 | 258 | 18.1% |
| 6 | AI政策与政府议程 | 130 | 9.1% |
| 7 | AI+医疗健康 | 60 | 4.2% |
| 8 | AI+教育 | 97 | 6.8% |
| 9 | AI与社会文化 | 384 | 27.0% |
| 10 | AI消费电子硬件 | 31 | 2.2% |
| 11 | 算力与芯片基础设施 | 63 | 4.4% |

---

## 命令行参考

```
cluster.py detect      语言检测
cluster.py preprocess  分词 + 去停用词
cluster.py vectorize   TF-IDF 向量化
cluster.py elbow       肘部法 SSE 图
cluster.py dendrogram  层次聚类树状图
cluster.py fit         执行聚类
cluster.py export      导出 Excel
cluster.py wordcloud   生成词云图
```

---

## 依赖

- Python 3.9+
- numpy, pandas, scikit-learn
- jieba（中文分词）
- spaCy + en_core_web_sm（英文分词）
- matplotlib（图表）
- openpyxl（Excel 导出）
- scipy（层次聚类树状图，可选）
- wordcloud（词云图，可选）

---

## License

MIT
