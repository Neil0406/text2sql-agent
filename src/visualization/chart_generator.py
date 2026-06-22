"""
chart_generator.py — Generate bar / line / pie / scatter charts from query results.

Uses matplotlib with a non-interactive Agg backend so it works in CLI and
Streamlit without a display server.  Chinese font auto-detection is included.

# chart_generator_node(state) 流程
#     │
#     ├─ 讀取 query_results + chart_type + intent
#     ├─ 偵測系統中文字型（macOS: PingFang / Linux: Noto Sans CJK）
#     ├─ 依 chart_type 選擇繪圖方式
#     │   bar     → 長條圖（分組比較）
#     │   line    → 折線圖（時序趨勢）
#     │   pie     → 圓餅圖（佔比分佈）
#     │   scatter → 散點圖（相關性）
#     ├─ 儲存為 PNG 至 data/charts/<hash>.png
#     └─ 寫入 state["chart_path"]
"""
import hashlib
import json
import os

import matplotlib
matplotlib.use("Agg")   # must be set before pyplot is imported
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from typing import Optional


# ── Font setup ────────────────────────────────────────────────────────────────
_CHINESE_FONTS = [
    "PingFang TC", "PingFang SC", "STHeiti", "Heiti TC",
    "Microsoft YaHei", "SimHei", "Noto Sans CJK TC",
    "Noto Sans CJK SC", "WenQuanYi Zen Hei", "Arial Unicode MS",
]

def _setup_font() -> str:
    available = {f.name for f in fm.fontManager.ttflist}
    for font in _CHINESE_FONTS:
        if font in available:
            plt.rcParams["font.family"] = font
            plt.rcParams["axes.unicode_minus"] = False
            return font
    plt.rcParams["font.family"] = "DejaVu Sans"
    return "DejaVu Sans"


# ── Main generator ────────────────────────────────────────────────────────────
def generate_chart(
    results: list[dict],
    chart_type: str,
    title: str = "",
    output_dir: str = "data/charts",
) -> Optional[str]:
    """
    Generate a chart from query results and save to disk.

    Parameters
    ----------
    results    : list of row dicts from sql_executor
    chart_type : "bar" | "line" | "pie" | "scatter"
    title      : chart title (usually the user question)
    output_dir : directory to save PNG files

    Returns
    -------
    filepath (str) or None if chart could not be generated
    """
    if not results or len(results) < 1:
        return None

    keys = list(results[0].keys())
    if len(keys) < 2:
        return None

    label_col = keys[0]
    value_col = keys[1]

    labels = [str(r[label_col]) for r in results]
    values: list[float] = []
    for r in results:
        try:
            values.append(float(r[value_col]))
        except (TypeError, ValueError):
            values.append(0.0)

    os.makedirs(output_dir, exist_ok=True)
    _setup_font()

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    palette = plt.cm.tab10.colors  # type: ignore[attr-defined]

    if chart_type == "bar":
        bars = ax.bar(labels, values, color=palette[: len(labels)], edgecolor="white", linewidth=0.8)
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(values) * 0.01,
                f"{val:,.1f}",
                ha="center", va="bottom", fontsize=8, color="#333333",
            )
        ax.set_xlabel(label_col, fontsize=11)
        ax.set_ylabel(value_col, fontsize=11)
        plt.xticks(rotation=35, ha="right", fontsize=9)

    elif chart_type == "line":
        x_idx = range(len(labels))
        ax.plot(x_idx, values, marker="o", color=palette[0], linewidth=2, markersize=6)
        ax.fill_between(x_idx, values, alpha=0.12, color=palette[0])
        ax.set_xticks(list(x_idx))
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=9)
        ax.set_xlabel(label_col, fontsize=11)
        ax.set_ylabel(value_col, fontsize=11)

    elif chart_type == "pie":
        # Filter zeros to avoid invisible slices
        pairs = [(l, v) for l, v in zip(labels, values) if v > 0]
        if not pairs:
            plt.close(fig)
            return None
        lbs, vals = zip(*pairs)
        wedge_props = {"linewidth": 1, "edgecolor": "white"}
        ax.pie(
            vals,
            labels=lbs,
            autopct="%1.1f%%",
            startangle=140,
            colors=palette[: len(vals)],
            wedgeprops=wedge_props,
        )
        ax.axis("equal")

    elif chart_type == "scatter":
        ax.scatter(range(len(values)), values, color=palette[0], alpha=0.65, s=60)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=9)
        ax.set_xlabel(label_col, fontsize=11)
        ax.set_ylabel(value_col, fontsize=11)

    else:
        plt.close(fig)
        return None

    if title:
        ax.set_title(title[:70], fontsize=13, fontweight="bold", pad=14, color="#222222")

    ax.grid(axis="y", alpha=0.3, linestyle="--", linewidth=0.7)
    plt.tight_layout()

    # Stable filename based on content hash
    content_hash = hashlib.md5(
        json.dumps(results[:10], default=str, sort_keys=True).encode()
    ).hexdigest()[:10]
    filename = f"chart_{chart_type}_{content_hash}.png"
    filepath = os.path.join(output_dir, filename)
    plt.savefig(filepath, dpi=140, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    return filepath


def chart_generator_node(state: dict) -> dict:
    """LangGraph node — Chart Generator."""
    results = state.get("query_results") or []
    chart_type = state.get("chart_type") or "bar"
    user_input = state.get("user_input", "")

    chart_path = generate_chart(
        results=results,
        chart_type=chart_type,
        title=user_input[:60],
        output_dir="data/charts",
    )
    return {"chart_path": chart_path}
