"""
P1-6: 分析报告导出模块
基于题材数据生成 Markdown 分析报告，支持导出分享。
"""
from __future__ import annotations

import os
from datetime import datetime
from config import DATA_DIR, get_logger
import core.database as db

_log = get_logger("report_generator")

OUTPUT_DIR = os.path.join(DATA_DIR, "reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def generate_theme_report(theme_name: str, output_path: str = "") -> str:
    """
    为指定题材生成 Markdown 分析报告。

    Args:
        theme_name: 题材名称
        output_path: 可选输出路径，不传则使用默认 OUTPUT_DIR

    Returns:
        生成的报告文件绝对路径
    """
    stocks = db.get_theme_stocks(theme_name)
    if not stocks:
        raise ValueError(f"题材「{theme_name}」下暂无数据")

    # 统计数据
    total_stocks = len(stocks)
    importance_counts = {"高": 0, "中": 0, "低": 0}
    market_counts = {}
    level1_set: dict[str, list[dict]] = {}
    for s in stocks:
        imp = s.get("importance", "中")
        if imp in importance_counts:
            importance_counts[imp] += 1
        else:
            importance_counts["中"] += 1
        mkt = s.get("market_type", "未知")
        market_counts[mkt] = market_counts.get(mkt, 0) + 1
        l1 = s.get("level1") or "(未分类)"
        level1_set.setdefault(l1, []).append(s)

    # 质量评分
    quality = _get_quality(theme_name)

    # 验证状态统计
    verified = sum(1 for s in stocks if s.get("verification_status") in ("verified_auto", "verified_inferred"))
    unverified = total_stocks - verified
    verified_rate = round(verified / max(total_stocks, 1) * 100, 1)

    date_str = datetime.now().strftime("%Y-%m-%d")
    report = _build_markdown(
        stocks=stocks,
        theme_name=theme_name,
        date_str=date_str,
        total_stocks=total_stocks,
        verified=verified,
        unverified=unverified,
        verified_rate=verified_rate,
        importance_counts=importance_counts,
        market_counts=market_counts,
        level1_set=level1_set,
        quality=quality,
    )

    if not output_path:
        safe_name = theme_name.replace("/", "_").replace("\\", "_")
        output_path = os.path.join(OUTPUT_DIR, f"{safe_name}_分析报告_{date_str}.md")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    _log.info("报告已生成: %s", output_path)
    return output_path


def _get_quality(theme_name: str) -> dict | None:
    """获取题材质量评分"""
    try:
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM theme_quality WHERE theme_name = ?",
                [theme_name],
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def _build_markdown(
    stocks: list,
    theme_name: str,
    date_str: str,
    total_stocks: int,
    verified: int,
    unverified: int,
    verified_rate: float,
    importance_counts: dict,
    market_counts: dict,
    level1_set: dict,
    quality: dict | None,
) -> str:
    """构建 Markdown 报告内容"""

    # 评分信息
    score_info = ""
    if quality:
        score_info = f"""
| 维度 | 分数 | 说明 |
|------|------|------|
| 广度 (Breadth) | {quality.get('breadth', '-')} | 产业链覆盖广度 |
| 事件密度 | {quality.get('event_density', '-')} | 近期相关事件密度 |
| 资金热度 | {quality.get('capital_flow', '-')} | 市场资金关注度 |
| 持续性 | {quality.get('sustainability', '-')} | 题材可持续性 |
| **综合评分** | **{quality.get('overall_score', '-')}** | |

{quality.get('summary', '')}
"""

    # 产业链图谱（文字版）
    chain_section = ""
    for l1, stocks_in_l1 in level1_set.items():
        l2_set: dict[str, int] = {}
        for s in stocks_in_l1:
            l2 = s.get("level2") or "(未分类)"
            l2_set[l2] = l2_set.get(l2, 0) + 1
        l2_lines = "\n".join(f"    - {l2} ({cnt} 只个股)" for l2, cnt in sorted(l2_set.items()))
        chain_section += f"- **{l1}** ({len(stocks_in_l1)} 只个股)\n{l2_lines}\n"

    # 核心个股表
    stock_table = "| # | 股票名称 | 代码 | 市场 | 重要性 | 产业链环节 | 评分 | 验证状态 | 投资逻辑 |\n"
    stock_table += "|---|----------|------|------|--------|------------|------|----------|----------|\n"
    for i, s in enumerate(stocks, 1):
        name = s.get("stock_name", "")
        code = s.get("stock_code", "")
        mkt = s.get("market_type", "")
        imp = s.get("importance", "中")
        l1 = s.get("level1", "")
        l2 = s.get("level2", "")
        l3 = s.get("level3", "")
        chain = f"{l1} > {l2} > {l3}" if l3 else f"{l1} > {l2}"
        biz = s.get("biz_relevance") or "-"
        verif = s.get("verification_status", "待核验")
        logic = (s.get("logic_summary") or "")[:50]
        stock_table += f"| {i} | {name} | {code} | {mkt} | {imp} | {chain} | {biz} | {verif} | {logic} |\n"

    # 风险提示模板
    risk_text = """
- **信息时效性**：本报告基于 AI 自动生成的分析数据，部分字段可能未经验证。
- **投资风险**：题材投资本身具有高波动性，本报告不构成任何投资建议。
- **数据完整度**：本题材有 {unverified}/{total} 只个股信息未完成自动验证，请人工复核关键数据。
""".format(unverified=unverified, total=total_stocks)

    return f"""# {theme_name} — 产业链分析报告

> **生成日期**：{date_str}
> **工具**：A股热点题材产业链梳理工具 v3.6

---

## 一、题材概况

| 指标 | 数值 |
|------|------|
| 关联个股总数 | {total_stocks} 只 |
| 已自动验证 | {verified} 只 ({verified_rate}%) |
| 待核验 | {unverified} 只 |
| 高重要性个股 | {importance_counts.get('高', 0)} 只 |
| 中重要性个股 | {importance_counts.get('中', 0)} 只 |
| 低重要性个股 | {importance_counts.get('低', 0)} 只 |

### 市场分布

| 市场 | 个股数量 |
|------|----------|
{chr(10).join(f'| {mkt} | {cnt} |' for mkt, cnt in sorted(market_counts.items()))}

## 二、产业链图谱

{chain_section}

## 三、题材质量评分
{score_info if score_info else '暂无评分数据'}

## 四、核心个股明细

{stock_table}

## 五、风险提示
{risk_text}

---

*本报告由 [A股热点题材产业链梳理工具](.) 自动生成，数据来源基于 AI 分析结果，仅供参考。*
"""


def list_reports() -> list[dict]:
    """列出所有已生成的报告"""
    reports = []
    if not os.path.isdir(OUTPUT_DIR):
        return reports
    for fname in sorted(os.listdir(OUTPUT_DIR), reverse=True):
        if fname.endswith(".md"):
            fpath = os.path.join(OUTPUT_DIR, fname)
            st = os.stat(fpath)
            reports.append({
                "filename": fname,
                "path": fpath,
                "size": st.st_size,
                "mtime": st.st_mtime,
            })
    return reports
