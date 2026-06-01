# 主题聚类分析工具

对中英文文本做分词、向量化、聚类，输出带簇标签的 Excel 和每簇 Top N 关键词。

支持 **KMeans**、**层次聚类**、**LDA** 三种方法，含肘部法辅助选 K。

## 功能

- 中英文自动检测与预处理（jieba 中文分词 / spaCy 英文词形还原）
- TF-IDF 向量化
- 三种聚类方法：KMeans（+ 肘部法选 K）、层次聚类（+ 树状图）、LDA 主题模型
- 逐簇关键词提取（TF-IDF centroid）和高频词统计（原始词频）
- 输出 Excel 文件，含原始数据标注、簇关键词、簇高频词、簇统计四个 sheet
- 可选：每簇词云图生成

## 安装

```bash
# 1. 克隆仓库
git clone https://github.com/<your-username>/topic-clustering.git
cd topic-clustering

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装 spaCy 英文模型（处理英文文本时需要）
python -m spacy download en_core_web_sm
```

## 快速开始

完整流程分 5 步：检测 → 预处理 → 向量化 → 聚类 → 导出。

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

# 6. 导出结果
python cluster.py export \
  --input "$DATA" --text-col "$TEXT_COL" \
  --labels "$WORKSPACE/labels.csv" \
  --keywords "$WORKSPACE/model.pkl" \
  --output "./聚类结果.xlsx"
```

## 聚类方法

| 方法 | 原理 | 适用场景 |
|---|---|---|
| KMeans | 距离最小化，球形簇 | 大多数场景，速度快，首选 |
| 层次聚类 | 自底向上合并最相似簇 | 探索层级结构，数据量 < 500 |
| LDA | 概率生成模型 | 长文本（论文、报告），软分类 |

详见 [references/algorithm-guide.md](references/algorithm-guide.md)。

## 输出

Excel 文件包含 4 个 sheet：

| Sheet | 内容 |
|---|---|
| 原始数据 | 原始数据 + `cluster_label` + `cluster_name` 列 |
| 簇关键词 | 每簇 TF-IDF centroid Top 30 关键词 |
| 簇高频词 | 每簇 Top 20 高频词 + 频次 |
| 簇统计 | 每簇文档数、占比 |

## 命令行参考

```
cluster.py detect      语言检测
cluster.py preprocess  分词 + 去停用词
cluster.py vectorize   TF-IDF 向量化
cluster.py elbow       肘部法 SSD 图
cluster.py dendrogram  层次聚类树状图
cluster.py fit         执行聚类
cluster.py export      导出 Excel
cluster.py wordcloud   生成词云图
```

## 依赖

- Python 3.9+
- numpy, pandas, scikit-learn
- jieba（中文分词）
- spaCy + en_core_web_sm（英文分词）
- matplotlib（图表）
- openpyxl（Excel 导出）
- scipy（层次聚类树状图，可选）
- wordcloud（词云图，可选）

## License

MIT
