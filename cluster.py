#!/usr/bin/env python3
"""
主题聚类分析 - 计算引擎
支持中英文文本的 TF-IDF + KMeans/层次聚类/LDA 主题聚类
"""

import argparse
import json
import os
import pickle
import re
import sys
import warnings
from collections import Counter

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

# ── 依赖检查 ──────────────────────────────────────────
MISSING = []

try:
    import jieba
except ImportError:
    MISSING.append("jieba")

try:
    import spacy
except ImportError:
    MISSING.append("spacy")

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
except ImportError:
    MISSING.append("scikit-learn")

try:
    from sklearn.cluster import KMeans, AgglomerativeClustering
    from sklearn.decomposition import LatentDirichletAllocation
except ImportError:
    pass  # scikit-learn handles this

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    MISSING.append("matplotlib")

try:
    from wordcloud import WordCloud as WC
except ImportError:
    WC = None  # optional

try:
    from scipy.cluster.hierarchy import dendrogram as shc_dendrogram, linkage
except ImportError:
    shc_dendrogram = None  # optional


def check_deps():
    if MISSING:
        print(json.dumps({"status": "missing_deps", "missing": MISSING}))
        sys.exit(1)


# ── 语言检测 ──────────────────────────────────────────
def detect_language(texts, sample_size=20):
    """基于文本采样检测语言"""
    sample = texts[:sample_size] if len(texts) > sample_size else texts
    zh_chars = 0
    en_chars = 0
    total = 0

    for t in sample:
        t = str(t)
        for ch in t:
            if "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿":
                zh_chars += 1
            elif ch.isalpha() and ch.isascii():
                en_chars += 1
            total += 1

    if total == 0:
        return "en"

    zh_ratio = zh_chars / total
    en_ratio = en_chars / total

    if zh_ratio > 0.15:
        return "zh"
    elif en_ratio > 0.7:
        return "en"

    # mixed: look at more samples
    if zh_ratio > en_ratio:
        return "zh"
    return "en"


def load_data(input_path, text_col=None):
    """加载数据，返回 (df, text_col_name)"""
    ext = os.path.splitext(input_path)[1].lower()

    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(input_path)
    elif ext == ".csv":
        for enc in ["utf-8", "gbk", "gb2312", "utf-8-sig", "latin-1"]:
            try:
                df = pd.read_csv(input_path, encoding=enc)
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        else:
            df = pd.read_csv(input_path, encoding="utf-8", errors="replace")
    else:
        # 文件夹模式
        if os.path.isdir(input_path):
            records = []
            for fname in sorted(os.listdir(input_path)):
                fpath = os.path.join(input_path, fname)
                if os.path.isfile(fpath) and fname.lower().endswith(
                    (".txt", ".md", ".html", ".htm")
                ):
                    for enc in ["utf-8", "gbk", "gb2312", "utf-8-sig"]:
                        try:
                            with open(fpath, "r", encoding=enc) as f:
                                records.append(
                                    {
                                        "filename": fname,
                                        "content": f.read(),
                                    }
                                )
                            break
                        except (UnicodeDecodeError, UnicodeError):
                            continue
                    else:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            records.append(
                                {"filename": fname, "content": f.read()}
                            )
            df = pd.DataFrame(records)
            text_col = "content"
        else:
            raise ValueError(f"不支持的文件格式: {ext}")

    # 找文本列
    if text_col is None or text_col not in df.columns:
        for col in df.columns:
            if df[col].dtype == "object" and df[col].str.len().mean() > 50:
                text_col = col
                break
        else:
            text_col = df.columns[0]

    return df, text_col


# ── 中文预处理 ─────────────────────────────────────────
_zh_stopwords_default = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "所", "为", "所以", "因为", "但是", "然而", "可以", "这个", "那个",
    "什么", "怎么", "如何", "还是", "或者", "不过", "然后", "之后",
    "而且", "并且", "如果", "虽然", "的话", "吧", "吗", "呢", "啊", "哦",
    "嗯", "哈", "呀", "嘛", "被", "把", "从", "以", "对", "向", "与",
    "及", "其", "等", "之", "中", "已", "将", "能", "该", "应", "可",
    "让", "用", "做", "没", "还", "再", "又", "才", "只", "请", "最",
    "更", "比较", "非常", "多", "少", "来", "去", "里", "外", "前",
    "后", "大", "小", "新", "旧", "年", "月", "日", "时", "分", "现在",
    "今天", "昨天", "明天", "已经", "正在", "将", "需要", "可能",
    "能够", "不同", "通过", "进行", "使用", "主要", "相关", "包括",
    "提供", "表示", "认为", "发展", "问题", "情况", "方面", "目前",
    "系统", "数据", "技术", "工作", "生活", "方式", "关系", "程度",
    "成为", "作为", "对于", "关于", "以及", "还是", "还有", "不是",
}


def preprocess_zh(
    df, text_col, stopwords_file=None, user_dict=None, pos_filter=None, min_word_len=2
):
    """中文预处理：jieba 分词 + 去停用词"""
    # 停用词
    stopwords = _zh_stopwords_default.copy()
    if stopwords_file and os.path.exists(stopwords_file):
        with open(stopwords_file, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip()
                if w:
                    stopwords.add(w)

    # 自定义词典
    if user_dict and os.path.exists(user_dict):
        jieba.load_userdict(user_dict)

    def _clean(text):
        text = str(text)
        # 移除 URL
        text = re.sub(r"http\S+|www\S+|https\S+", "", text)
        # 移除 HTML
        text = re.sub(r"<.*?>", "", text)
        # 保留中英文和数字
        text = re.sub(r"[^一-龥a-zA-Z0-9]", " ", text)
        return text

    def _segment(text):
        text = _clean(text)
        words = jieba.lcut(text)
        result = []
        for w in words:
            w = w.strip().lower()
            if len(w) < min_word_len:
                continue
            if w in stopwords:
                continue
            if not w.isalpha() and not w.isalnum():
                continue
            result.append(w)
        return " ".join(result)

    texts = df[text_col].astype(str).apply(_segment)
    valid_mask = texts.str.len() > 0
    texts = texts[valid_mask]
    df = df[valid_mask].copy()

    # 高频词统计
    all_words = " ".join(texts).split()
    word_freq = Counter(all_words).most_common(15)

    return texts.tolist(), df, word_freq


# ── 英文预处理 ─────────────────────────────────────────
def preprocess_en(
    df, text_col, stopwords_file=None, pos_filter=None, min_word_len=2
):
    """英文预处理：spacy 词性还原"""
    nlp = spacy.load("en_core_web_sm")

    # 额外停用词：用户提供原词后，自动做词形还原，同时加入原词和还原词
    extra_stops = set()
    if stopwords_file and os.path.exists(stopwords_file):
        with open(stopwords_file, "r", encoding="utf-8") as f:
            raw_stops = [line.strip().lower() for line in f if line.strip()]
        for w in raw_stops:
            extra_stops.add(w)
            doc = nlp(w)
            for token in doc:
                lemma = token.lemma_.lower().strip()
                if lemma and lemma != w:
                    extra_stops.add(lemma)

    if pos_filter is None:
        pos_filter = {"NOUN", "VERB", "ADJ"}

    def _clean(text):
        text = str(text).lower()
        text = re.sub(r"http\S+|www\S+|https\S+", "", text)
        text = re.sub(r"<.*?>", "", text)
        text = re.sub(r"[^a-z\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _lemmatize(text):
        text = _clean(text)
        if not text:
            return ""
        doc = nlp(text)
        tokens = []
        for token in doc:
            if token.pos_ not in pos_filter:
                continue
            lemma = token.lemma_.lower().strip()
            if not lemma.isalpha():
                continue
            if len(lemma) < min_word_len:
                continue
            if token.is_stop:
                continue
            if lemma in extra_stops or token.text.lower().strip() in extra_stops:
                continue
            tokens.append(lemma)
        return " ".join(tokens)

    texts = df[text_col].astype(str).apply(_lemmatize)
    valid_mask = texts.str.len() > 0
    texts = texts[valid_mask]
    df = df[valid_mask].copy()

    all_words = " ".join(texts).split()
    word_freq = Counter(all_words).most_common(15)

    return texts.tolist(), df, word_freq


# ── TF-IDF 向量化 ──────────────────────────────────────
def vectorize(texts, min_df=5, max_df=0.4):
    """TF-IDF 向量化"""
    vectorizer = TfidfVectorizer(min_df=min_df, max_df=max_df)
    X = vectorizer.fit_transform(texts)
    return X, vectorizer


# ── 肘部法 ────────────────────────────────────────────
def elbow_method(X, k_range, output_path):
    """生成肘部法 SSE 图"""
    from sklearn.cluster import KMeans

    sse = []
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        km.fit(X)
        sse.append(float(km.inertia_))

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(list(k_range), sse, marker="o", linewidth=2)
    ax.set_xlabel("Number of clusters (k)", fontsize=12)
    ax.set_ylabel("SSE (Inertia)", fontsize=12)
    ax.set_title("Elbow Method for Optimal k", fontsize=14)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)

    return {"sse": sse, "k_range": list(k_range), "elbow_plot": output_path}


# ── 层次聚类树状图 ─────────────────────────────────────
def dendrogram_plot(X, output_path, max_k=15):
    """生成层次聚类树状图（截断展示）"""
    if shc_dendrogram is None:
        raise ImportError("需要安装 scipy: pip install scipy")

    linkage_matrix = linkage(X.toarray() if hasattr(X, "toarray") else X, method="ward")

    fig, ax = plt.subplots(figsize=(14, 6))
    shc_dendrogram(
        linkage_matrix,
        truncate_mode="lastp",
        p=max_k,
        leaf_rotation=90.0,
        leaf_font_size=8.0,
        show_contracted=True,
        ax=ax,
    )
    ax.set_title("Hierarchical Clustering Dendrogram (truncated)", fontsize=14)
    ax.set_xlabel("Cluster size / sample index", fontsize=12)
    ax.set_ylabel("Distance (Ward)", fontsize=12)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)

    return {"dendrogram_plot": output_path, "method": "ward"}


# ── 聚类拟合 ───────────────────────────────────────────
def fit_cluster(X, method="kmeans", k=5, random_state=42):
    """拟合聚类模型，返回 labels 和各簇关键词"""
    if method == "kmeans":
        from sklearn.cluster import KMeans

        model = KMeans(n_clusters=k, random_state=random_state, n_init=20)
        labels = model.fit_predict(X)
        # 按簇大小排序（大簇在前）
        return labels, model

    elif method == "hierarchical":
        from sklearn.cluster import AgglomerativeClustering

        model = AgglomerativeClustering(n_clusters=k, linkage="ward")
        labels = model.fit_predict(X.toarray() if hasattr(X, "toarray") else X)
        return labels, model

    elif method == "lda":
        from sklearn.decomposition import LatentDirichletAllocation

        model = LatentDirichletAllocation(
            n_components=k, random_state=random_state, learning_method="batch"
        )
        doc_topics = model.fit_transform(X)
        labels = doc_topics.argmax(axis=1)
        return labels, model

    else:
        raise ValueError(f"不支持的聚类方法: {method}")


# ── 提取关键词 ─────────────────────────────────────────
def extract_keywords(model, vectorizer, labels, k, method="kmeans", top_n=20):
    """提取每个簇的 Top N 关键词"""
    terms = vectorizer.get_feature_names_out()
    cluster_keywords = {}

    if method == "kmeans":
        order = model.cluster_centers_.argsort()[:, ::-1]
        for i in range(k):
            keywords = [terms[idx] for idx in order[i, :top_n]]
            cluster_keywords[str(i)] = keywords

    elif method == "hierarchical":
        # 层次聚类没有 centroid，用簇内平均 TF-IDF
        if hasattr(model, "labels_"):
            clust_labels = model.labels_
        else:
            clust_labels = labels
        for i in range(k):
            mask = clust_labels == i
            if mask.sum() == 0:
                cluster_keywords[str(i)] = []
                continue
            if hasattr(labels, "dtype"):
                pass
            centroid = np.asarray(X[mask].mean(axis=0)).flatten()
            top_idx = centroid.argsort()[::-1][:top_n]
            cluster_keywords[str(i)] = [terms[idx] for idx in top_idx]

    elif method == "lda":
        for i, topic in enumerate(model.components_):
            top_idx = topic.argsort()[::-1][:top_n]
            cluster_keywords[str(i)] = [terms[idx] for idx in top_idx]

    return cluster_keywords


def compute_cluster_word_freq(texts, labels, k, top_n=20):
    """计算每簇内的高频词（原始词频统计）"""
    cluster_words = {}
    for i, text in enumerate(texts):
        cl = str(int(labels[i]))
        cluster_words.setdefault(cl, []).extend(text.split())

    cluster_freq = {}
    for cl, words in cluster_words.items():
        cluster_freq[cl] = Counter(words).most_common(top_n)

    for i in range(k):
        if str(i) not in cluster_freq:
            cluster_freq[str(i)] = []

    return cluster_freq


def compute_cluster_stats(labels, k):
    """计算每簇统计信息"""
    unique, counts = np.unique(labels, return_counts=True)
    total = len(labels)
    stats = {}
    for cl, cnt in zip(unique, counts):
        stats[str(int(cl))] = {
            "count": int(cnt),
            "percentage": round(cnt / total * 100, 1),
        }
    # 补上可能缺失的簇
    for i in range(k):
        if str(i) not in stats:
            stats[str(i)] = {"count": 0, "percentage": 0.0}
    return stats


# ── 词云生成 ──────────────────────────────────────────
def generate_wordclouds(texts, labels, k, output_dir, font_path=None):
    """为每个簇生成词云图"""
    if WC is None:
        print(json.dumps({"status": "skipped", "reason": "wordcloud 未安装"}))
        return None

    os.makedirs(output_dir, exist_ok=True)
    files = []

    for i in range(k):
        mask = labels == i
        cluster_texts = [texts[j] for j in range(len(texts)) if mask[j]]
        if not cluster_texts:
            continue
        combined = " ".join(cluster_texts)

        wc_kwargs = {
            "background_color": "white",
            "width": 800,
            "height": 400,
            "max_words": 100,
            "collocations": False,
        }
        if font_path and os.path.exists(font_path):
            wc_kwargs["font_path"] = font_path

        wc = WC(**wc_kwargs)
        wc.generate(combined)
        fpath = os.path.join(output_dir, f"cluster_{i}_wordcloud.png")
        wc.to_file(fpath)
        files.append(fpath)

    return files


# ── 导出 ───────────────────────────────────────────────
def export_results(
    df, labels, cluster_keywords, cluster_stats, cluster_names, cluster_word_freq, output_path
):
    """导出 Excel：原始数据 + 簇标签 + 簇关键词 + 簇统计 + 簇高频词"""
    df_out = df.copy()
    df_out["cluster_label"] = labels

    if cluster_names:
        df_out["cluster_name"] = df_out["cluster_label"].apply(
            lambda x: cluster_names.get(str(int(x)), f"Cluster {int(x)}")
        )

    # 簇关键词表（TF-IDF centroid）
    kw_data = []
    for cl, kws in sorted(cluster_keywords.items(), key=lambda x: int(x[0])):
        row = {"cluster": int(cl)}
        if cluster_names and cl in cluster_names:
            row["name"] = cluster_names[cl]
        for rank, kw in enumerate(kws, 1):
            row[f"kw_{rank}"] = kw
        kw_data.append(row)
    kw_df = pd.DataFrame(kw_data)

    # 簇高频词表（原始词频）
    freq_data = []
    for cl in sorted(cluster_word_freq.keys(), key=lambda x: int(x)):
        row = {"cluster": int(cl)}
        if cluster_names and cl in cluster_names:
            row["name"] = cluster_names[cl]
        for rank, (word, count) in enumerate(cluster_word_freq[cl], 1):
            row[f"word_{rank}"] = word
            row[f"freq_{rank}"] = count
        freq_data.append(row)
    freq_df = pd.DataFrame(freq_data)

    # 簇统计表
    stats_data = []
    for cl, info in sorted(cluster_stats.items(), key=lambda x: int(x[0])):
        row = {"cluster": int(cl), "count": info["count"], "percentage": info["percentage"]}
        if cluster_names and cl in cluster_names:
            row["name"] = cluster_names[cl]
        stats_data.append(row)
    stats_df = pd.DataFrame(stats_data)

    # 写入 Excel
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_out.to_excel(writer, sheet_name="原始数据", index=False)
        kw_df.to_excel(writer, sheet_name="簇关键词", index=False)
        freq_df.to_excel(writer, sheet_name="簇高频词", index=False)
        stats_df.to_excel(writer, sheet_name="簇统计", index=False)

    return output_path


# ═══════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════

def cmd_detect(args):
    df, text_col = load_data(args.input, args.text_col)
    texts = df[text_col].astype(str).tolist()
    lang = detect_language(texts, args.sample_size)

    # 采样词语
    sample_words = []
    for t in texts[:5]:
        words = str(t).split()[:10]
        sample_words.extend(words)

    print(
        json.dumps(
            {
                "language": lang,
                "total_docs": len(texts),
                "text_col": text_col,
                "sample_words": sample_words[:30],
            },
            ensure_ascii=False,
        )
    )


def cmd_preprocess(args):
    df, text_col = load_data(args.input, args.text_col)
    texts = df[text_col].astype(str).tolist()
    lang = detect_language(texts)

    if lang == "zh":
        texts_processed, df_clean, word_freq = preprocess_zh(
            df,
            text_col,
            stopwords_file=args.stopwords,
            user_dict=args.user_dict,
            pos_filter=None,
            min_word_len=args.min_word_len,
        )
    else:
        texts_processed, df_clean, word_freq = preprocess_en(
            df,
            text_col,
            stopwords_file=args.stopwords,
            pos_filter=None,
            min_word_len=args.min_word_len,
        )

    # 保存
    data = {
        "texts": texts_processed,
        "df": df_clean,
        "lang": lang,
        "word_freq": word_freq,
    }
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "wb") as f:
        pickle.dump(data, f)

    avg_len = np.mean([len(t.split()) for t in texts_processed])
    print(
        json.dumps(
            {
                "status": "ok",
                "original_docs": len(df),
                "valid_docs": len(texts_processed),
                "avg_words_per_doc": round(float(avg_len), 1),
                "top_15_words": word_freq,
                "output": args.output,
            },
            ensure_ascii=False,
        )
    )


def cmd_vectorize(args):
    with open(args.input, "rb") as f:
        data = pickle.load(f)

    X, vectorizer = vectorize(data["texts"], min_df=args.min_df, max_df=args.max_df)

    output = {"X": X, "vectorizer": vectorizer, "lang": data["lang"]}
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "wb") as f:
        pickle.dump(output, f)

    terms = vectorizer.get_feature_names_out()
    print(
        json.dumps(
            {
                "status": "ok",
                "shape": list(X.shape),
                "n_features": len(terms),
                "sample_features": terms[:20].tolist(),
                "output": args.output,
            },
            ensure_ascii=False,
        )
    )


def cmd_elbow(args):
    with open(args.input, "rb") as f:
        data = pickle.load(f)

    k_start, k_end = args.k_range
    k_range = list(range(k_start, k_end + 1))

    result = elbow_method(data["X"], k_range, args.output)
    print(json.dumps(result, ensure_ascii=False))


def cmd_dendrogram(args):
    with open(args.input, "rb") as f:
        data = pickle.load(f)

    result = dendrogram_plot(data["X"], args.output, max_k=args.max_k)
    print(json.dumps(result, ensure_ascii=False))


def cmd_fit(args):
    with open(args.input, "rb") as f:
        data = pickle.load(f)

    X = data["X"]
    vectorizer = data["vectorizer"]

    labels, model = fit_cluster(X, method=args.method, k=args.k)

    cluster_keywords = extract_keywords(
        model, vectorizer, labels, args.k, method=args.method
    )
    cluster_stats = compute_cluster_stats(labels, args.k)

    # 每簇原始词频
    cluster_word_freq = {}
    if args.texts:
        with open(args.texts, "rb") as f:
            text_data = pickle.load(f)
        cluster_word_freq = compute_cluster_word_freq(
            text_data["texts"], labels, args.k
        )

    # 保存模型数据
    model_data = {
        "labels": labels,
        "model": model,
        "method": args.method,
        "k": args.k,
        "cluster_keywords": cluster_keywords,
        "cluster_stats": cluster_stats,
        "cluster_word_freq": cluster_word_freq,
    }
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "wb") as f:
        pickle.dump(model_data, f)

    # 保存 labels CSV
    labels_df = pd.DataFrame({"cluster": labels})
    if os.path.dirname(args.labels_output):
        os.makedirs(os.path.dirname(args.labels_output), exist_ok=True)
    labels_df.to_csv(args.labels_output, index=False)

    print(
        json.dumps(
            {
                "status": "ok",
                "method": args.method,
                "k": args.k,
                "cluster_sizes": {
                    str(k): v["count"] for k, v in cluster_stats.items()
                },
                "keywords": cluster_keywords,
                "word_freq": {
                    str(k): [{"word": w, "count": c} for w, c in v]
                    for k, v in cluster_word_freq.items()
                },
                "output": args.output,
            },
            ensure_ascii=False,
        )
    )


def cmd_export(args):
    # 读取原始数据
    df, _ = load_data(args.input, text_col=None)

    # 读取 labels
    labels_df = pd.read_csv(args.labels)
    labels = labels_df["cluster"].values

    # 读取模型
    with open(args.keywords, "rb") as f:
        model_data = pickle.load(f)

    cluster_keywords = model_data["cluster_keywords"]
    cluster_stats = model_data["cluster_stats"]
    cluster_word_freq = model_data.get("cluster_word_freq", {})
    k = model_data["k"]

    # 簇命名
    cluster_names = {}
    if args.cluster_names:
        cluster_names = json.loads(args.cluster_names)

    # 对齐长度
    min_len = min(len(df), len(labels))
    df = df.iloc[:min_len].copy()
    labels = labels[:min_len]

    result_path = export_results(
        df, labels, cluster_keywords, cluster_stats, cluster_names, cluster_word_freq, args.output
    )
    print(
        json.dumps(
            {"status": "ok", "output": result_path, "sheets": ["原始数据", "簇关键词", "簇高频词", "簇统计"]},
            ensure_ascii=False,
        )
    )


def cmd_wordcloud(args):
    with open(args.input, "rb") as f:
        data = pickle.load(f)

    labels_df = pd.read_csv(args.labels)
    labels = labels_df["cluster"].values

    # 对齐
    texts = data["texts"]
    k = len(set(labels))
    min_len = min(len(texts), len(labels))

    files = generate_wordclouds(
        texts[:min_len],
        labels[:min_len],
        k,
        args.output,
        font_path=args.font_path,
    )
    print(json.dumps({"status": "ok", "wordclouds": files or []}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="主题聚类分析引擎")
    sub = parser.add_subparsers(dest="command")

    # detect
    p = sub.add_parser("detect")
    p.add_argument("--input", required=True)
    p.add_argument("--text-col", default=None)
    p.add_argument("--sample-size", type=int, default=20)

    # preprocess
    p = sub.add_parser("preprocess")
    p.add_argument("--input", required=True)
    p.add_argument("--text-col", default=None)
    p.add_argument("--output", required=True)
    p.add_argument("--lang", default="auto")
    p.add_argument("--min-word-len", type=int, default=2)
    p.add_argument("--stopwords", default=None)
    p.add_argument("--user-dict", default=None)
    p.add_argument("--pos-filter", default=None)

    # vectorize
    p = sub.add_parser("vectorize")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--min-df", type=int, default=5)
    p.add_argument("--max-df", type=float, default=0.4)

    # elbow
    p = sub.add_parser("elbow")
    p.add_argument("--input", required=True)
    p.add_argument("--k-range", type=int, nargs=2, default=[3, 20])
    p.add_argument("--output", required=True)

    # dendrogram
    p = sub.add_parser("dendrogram")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--max-k", type=int, default=15)

    # fit
    p = sub.add_parser("fit")
    p.add_argument("--input", required=True)
    p.add_argument("--texts", default=None)
    p.add_argument("--method", default="kmeans", choices=["kmeans", "hierarchical", "lda"])
    p.add_argument("--k", type=int, required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--labels-output", required=True)

    # export
    p = sub.add_parser("export")
    p.add_argument("--input", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--keywords", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--cluster-names", default=None)

    # wordcloud
    p = sub.add_parser("wordcloud")
    p.add_argument("--input", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--font-path", default=None)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    check_deps()

    cmds = {
        "detect": cmd_detect,
        "preprocess": cmd_preprocess,
        "vectorize": cmd_vectorize,
        "elbow": cmd_elbow,
        "dendrogram": cmd_dendrogram,
        "fit": cmd_fit,
        "export": cmd_export,
        "wordcloud": cmd_wordcloud,
    }

    cmds[args.command](args)


if __name__ == "__main__":
    main()
