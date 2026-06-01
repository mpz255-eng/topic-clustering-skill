---
name: topic-clustering
description: |
  计算式主题聚类分析工具，对中英文文本做分词、向量化、聚类，输出带簇标签的 Excel 和每簇 Top N 关键词。
  支持 KMeans、层次聚类、LDA 三种方法，含肘部法辅助选 K。
  当用户提到"主题聚类"、"文本聚类"、"话题聚类"、"聚类分析"、"自动分类文本"、"把这些文本分几类"、
  "KMeans聚类"、"LDA主题模型"、"层次聚类文本"、"按主题归类"、"文本自动分组"、"给这些新闻/评论/文章分个类"、
  "跑一个聚类"、"文本分群"、"tfidf聚类"、"文档聚类"时触发此 skill。
  注意与 thematic-analysis 的区别：thematic-analysis 是 Braun & Clarke 框架下的人工质性主题分析，
  本 skill 是 TF-IDF + KMeans/层次聚类/LDA 的计算式方法。
---

# 主题聚类分析工具

本 skill 对中英文文本执行计算式主题聚类。**交互式向导模式**：每一步展示结果让用户确认后再继续。

---

## 阶段 0：接收数据

触发后，第一步确认输入：

> "主题聚类分析——请提供：
> 1. **数据文件路径**（支持 .xlsx / .csv / 文件夹路径）
> 2. **文本列的列名**（Excel/CSV 时必填；文件夹模式自动跳过）
> 3. **是否有额外的停用词表？**（可选，提供文件路径）"

---

## 阶段 1：语言检测与预处理

### 1.1 调用检测脚本

```bash
python "<skill-base>/cluster.py" detect \
  --input "<input_path>" \
  --text-col "<text_col>" \
  --sample-size 20
```

解析 JSON 输出，获得 `language`（`zh`/`en`/`mixed`）、`total_docs`、`sample_words`。

告知用户：
> "检测结果：共 N 篇文档，语种判定为 **[中文/英文/混合]**。接下来将按此语种做分词预处理。"

### 1.2 预处理

询问用户确认预处理参数：

> "预处理参数（可直接回车使用默认值）：
> - 去停用词：**[是/否]**
> - 自定义词典路径：**[无/用户提供]**
> - 保留词性（中文）：**[名词/动词/形容词，默认全保留]**
> - 保留词性（英文）：**[NOUN/VERB/ADJ，默认全保留]**
> - 最短词长：**[默认 2]**"

用户确认后，调用预处理：

```bash
python "<skill-base>/cluster.py" preprocess \
  --input "<input_path>" \
  --text-col "<text_col>" \
  --output "<workspace>/preprocessed.pkl" \
  --lang "<detected_lang>" \
  --min-word-len 2 \
  --stopwords "<stopwords_path_or_none>" \
  --user-dict "<user_dict_or_none>" \
  --pos-filter "<noun,verb,adj or all>"
```

**预处理完成后自动报告**：原始文档数、有效文档数、平均词数/篇、高频词 Top 15。

---

## 阶段 2：向量化

询问参数：

> "TF-IDF 向量化参数：
> - **min_df**：词最少出现在几篇文档（默认 5）
> - **max_df**：词最多出现在百分之几的文档（默认 0.4，即 40%）"

调用：

```bash
python "<skill-base>/cluster.py" vectorize \
  --input "<workspace>/preprocessed.pkl" \
  --output "<workspace>/vectorized.pkl" \
  --min-df 5 \
  --max-df 0.4
```

**向量化完成后自动报告**：矩阵维度（文档数 × 特征词数）、特征词示例 20 个。

---

## 阶段 3：选择聚类方法

展示选项并询问：

> "选择聚类方法：
> **A. KMeans** — 快速、结果稳定，适合大多数场景。需肘部法辅助选 K
> **B. 层次聚类** — 输出树状图，适合探索层级结构，小数据集（< 500 篇）效果更好
> **C. LDA 主题模型** — 概率模型，输出"文档-主题"和"主题-词"分布，适合长文本
>
> 选哪个？（推荐 A）"

### 3A：KMeans + 肘部法

先展示肘部图：

```bash
python "<skill-base>/cluster.py" elbow \
  --input "<workspace>/vectorized.pkl" \
  --k-range 3 20 \
  --output "<workspace>/elbow.png"
```

展示图片（Read 工具读取 elbow.png），然后：

> "肘部图已生成。根据曲线拐点，你选 K = ？"

### 3B：层次聚类

```bash
python "<skill-base>/cluster.py" dendrogram \
  --input "<workspace>/vectorized.pkl" \
  --output "<workspace>/dendrogram.png" \
  --max-k 15
```

展示树状图，然后询问切割 K 值或距离阈值。

### 3C：LDA

直接询问：
> "LDA 主题数量（建议 5-15）："

---

## 阶段 4：执行聚类

用户选定方法和 K 后，调用：

```bash
python "<skill-base>/cluster.py" fit \
  --input "<workspace>/vectorized.pkl" \
  --texts "<workspace>/preprocessed.pkl" \
  --method "<kmeans|hierarchical|lda>" \
  --k <chosen_k> \
  --output "<workspace>/model.pkl" \
  --labels-output "<workspace>/labels.csv"
```

**聚类完成后自动报告**：
- 每簇文章数量分布
- 每簇 Top 20 关键词

---

## 阶段 5：主题命名与导出

### 5.1 展示关键词，辅助命名

逐簇展示 Top 关键词，请用户命名：

> "**Cluster 0**（544 篇）：chip, export, trade, semiconductor, restriction...
> 这簇你想叫什么名字？（如：芯片出口管制）
>
> **Cluster 1**（284 篇）：video, language, content, digital, cultural...
> 这簇你想叫什么名字？（如：数字内容与文化）"

用户可跳过命名（直接用"Cluster N"），也可逐个命名。

### 5.2 导出结果

```bash
python "<skill-base>/cluster.py" export \
  --input "<original_data>" \
  --labels "<workspace>/labels.csv" \
  --keywords "<workspace>/model.pkl" \
  --output "<output_dir>/聚类结果.xlsx" \
  --cluster-names "<names_json>"
```

**导出后告知**：
> "结果已导出至 `<output_dir>/聚类结果.xlsx`，包含：
> - `原始数据` sheet：原始数据 + 簇标签列
> - `簇关键词` sheet：每簇 Top 30 关键词（TF-IDF centroid）
> - `簇高频词` sheet：每簇 Top 20 高频词（原始词频+频次）
> - `簇统计` sheet：每簇文档数、占比、命名"

### 5.3 可选：词云图

询问是否要生成词云：

> "要不要为每个簇生成词云图？"

若需要：

```bash
python "<skill-base>/cluster.py" wordcloud \
  --input "<workspace>/preprocessed.pkl" \
  --labels "<workspace>/labels.csv" \
  --output "<output_dir>/wordclouds/" \
  --font-path "C:/Windows/Fonts/simhei.ttf"
```

---

## 阶段 6：收尾

全部完成后，输出总结：

> "聚类分析完成。
> - 方法：KMeans / K=12
> - 文档数：1591
> - 结果文件：`<output_dir>/聚类结果.xlsx`
> - 中间文件目录：`<workspace>/`
>
> 如需调整——换方法、换 K 值、修改预处理参数——随时说。"

---

## 注意事项

- 所有中间文件放在 `<workspace>/` 下（首次运行时在数据文件同级目录创建 `clustering_workspace/`）
- 中文分词必须有 jieba，英文必须有 spacy + en_core_web_sm，脚本会自动检查依赖
- 如果语种检测为 `mixed`，按中文处理（jieba 对英文词也能切分）
- 命名阶段不是强制步骤，用户可以跳过直接出结果
