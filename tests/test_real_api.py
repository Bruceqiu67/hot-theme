"""
真实 API 核心功能测试
使用提供的 API Key 测试 DeepSeek API 的各核心功能
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_KEY = "sk-your-deepseek-api-key"
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-flash"

# ============================================================
# Test 1: API 连通性 & 基础调用
# ============================================================
def test_api_connectivity():
    """测试 API Key 是否有效，基础连通性"""
    print("\n" + "="*60)
    print("TEST 1: API 连通性测试")
    print("="*60)
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "user", "content": "请用JSON格式回复：{\"status\": \"ok\", \"message\": \"API连接成功\"}"}
            ],
            temperature=0.1,
            max_tokens=200,
            timeout=30,
        )
        content = response.choices[0].message.content
        print(f"  ✅ API 连通性: OK")
        print(f"  📝 响应: {content[:200]}")
        print(f"  📊 Tokens: {response.usage}")
        return True
    except Exception as e:
        print(f"  ❌ API 连通性失败: {e}")
        return False


# ============================================================
# Test 2: 热点题材提取
# ============================================================
def test_hot_topics_generation():
    """测试 generate_hot_topics - 搜索 + LLM 汇总热点题材"""
    print("\n" + "="*60)
    print("TEST 2: 热点题材生成测试")
    print("="*60)

    import core.ai_client as ac

    try:
        topics = ac.generate_hot_topics(
            api_key=API_KEY,
            base_url=BASE_URL,
            model=MODEL,
        )
        print(f"  ✅ 生成成功，共 {len(topics)} 个题材")
        for i, t in enumerate(topics[:5]):
            print(f"  [{i+1}] {t.get('theme_name', '?')}: {t.get('summary', '?')[:80]}")

        # 验证数据结构
        assert len(topics) > 0, "应至少返回 1 个题材"
        for t in topics:
            assert "theme_name" in t, f"题材缺少 theme_name: {t.keys()}"
            assert "summary" in t, f"题材缺少 summary"
        print(f"  ✅ 数据结构验证通过")
        return topics
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# Test 3: 题材产业链分析
# ============================================================
def test_theme_analysis():
    """测试 generate_theme_analysis - 搜索 + LLM 生成产业链"""
    print("\n" + "="*60)
    print("TEST 3: 题材产业链分析测试")
    print("="*60)

    import core.ai_client as ac

    theme_name = "固态电池"

    try:
        result = ac.generate_theme_analysis(
            theme_name=theme_name,
            api_key=API_KEY,
            base_url=BASE_URL,
            model=MODEL,
        )
        print(f"  ✅ 分析成功: theme={result.get('theme_name', '?')}")
        chains = result.get("chains", [])
        print(f"  📊 产业链环节数: {len(chains)}")

        # 验证数据结构
        assert "theme_name" in result, "缺少 theme_name"
        assert "chains" in result, "缺少 chains"
        for chain in chains[:3]:
            level1 = chain.get("level1", "?")
            stocks = chain.get("stocks", [])
            print(f"  - {level1}: {len(stocks)} 只个股")

        print(f"  ✅ 数据结构验证通过")
        return result
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# Test 4: 新闻搜索 + 候选题材提取
# ============================================================
def test_news_and_candidates():
    """测试 fetch_news + generate_candidate_topics 完整链路"""
    print("\n" + "="*60)
    print("TEST 4: 新闻搜索 + 候选题材提取测试")
    print("="*60)

    from core.fetch_news import fetch_news, TIME_RANGE_OPTIONS, SEARCH_CATEGORIES
    import core.ai_client as ac
    import core.database as db
    from datetime import datetime

    # Step 1: 搜索新闻
    print("  [1/3] 搜索新闻...")
    try:
        raw_news = fetch_news(
            time_range="最近 24 小时",
            selected_categories=["全市场热点", "半导体"],
            max_results_per_query=3,
        )
        print(f"  ✅ 搜索到 {len(raw_news)} 条新闻")
        if raw_news:
            print(f"  示例: {raw_news[0].get('title', '?')[:80]}")
    except Exception as e:
        print(f"  ⚠️ 搜索失败 (可能网络问题): {e}")
        return None

    if len(raw_news) < 3:
        print(f"  ⚠️ 新闻数量不足，跳过后续测试")
        return None

    # Step 2: 保存新闻到 DB
    print("  [2/3] 保存新闻到数据库...")
    db.save_raw_news(raw_news)

    # Step 3: 提取候选题材
    print("  [3/3] AI 提取候选题材...")
    try:
        time_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        topics = ac.generate_candidate_topics(
            raw_news=raw_news[:30],
            api_key=API_KEY,
            base_url=BASE_URL,
            model=MODEL,
            time_start=time_start,
            time_end=time_end,
        )
        print(f"  ✅ 提取到 {len(topics)} 个候选题材")
        for i, t in enumerate(topics[:5]):
            print(f"  [{i+1}] {t.get('topic_name', '?')} (热度: {t.get('heat_score', '?')}, 等级: {t.get('heat_level', '?')})")

        # 验证数据结构
        assert len(topics) > 0, "应至少返回 1 个候选题材"
        for t in topics:
            assert "topic_name" in t, f"题材缺少 topic_name"
            assert "heat_score" in t, f"题材缺少 heat_score"
        print(f"  ✅ 数据结构验证通过")

        # 保存到 DB
        news_by_id = {item["news_id"]: item for item in raw_news if item.get("news_id")}
        saved = db.save_hot_topic_candidates(topics, news_by_id)
        print(f"  ✅ 已保存 {saved} 个候选题材到数据库")

        return topics
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# Test 5: 两阶段 AI 草稿生成
# ============================================================
def test_analysis_draft():
    """测试 generate_analysis_draft - 产业链拆解 + 个股映射"""
    print("\n" + "="*60)
    print("TEST 5: AI 分析草稿生成测试 (两阶段)")
    print("="*60)

    import core.ai_client as ac
    import core.database as db

    # 先获取一个候选题材
    candidates = db.get_hot_topic_candidates()
    if not candidates:
        print("  ⚠️ 数据库无候选题材，先运行 Test 4 或使用模拟数据")
        # 使用模拟数据
        topic = {
            "topic_id": 999,
            "topic_name": "HBM高带宽存储",
            "trigger_event": "AI服务器需求爆发，HBM供不应求",
            "core_logic": "HBM是AI芯片的核心配套，SK海力士/三星垄断，国产替代需求迫切",
            "heat_score": 85,
        }
        evidence_items = [
            {
                "news_id": "test001",
                "title": "HBM需求爆发，国内封测厂商受益",
                "summary": "AI算力需求推动HBM出货量增长300%",
                "source": "eastmoney.com",
                "url": "https://example.com/1",
                "reason": "直接相关",
            }
        ]
    else:
        topic = candidates[0]
        topic_id = topic["topic_id"]
        evidence_items = db.get_topic_evidence(topic_id)
        if not evidence_items:
            evidence_items = [
                {
                    "news_id": "test001",
                    "title": topic.get("trigger_event", "相关新闻"),
                    "summary": topic.get("core_logic", ""),
                    "source": "test",
                    "url": "",
                    "reason": "主证据",
                }
            ]

    print(f"  测试题材: {topic.get('topic_name', '?')}")

    try:
        draft = ac.generate_analysis_draft(
            topic=topic,
            evidence_items=evidence_items,
            api_key=API_KEY,
            base_url=BASE_URL,
            model=MODEL,
        )

        print(f"  ✅ 草稿生成成功")
        print(f"  📝 题材定义: {draft.get('theme_definition', '?')[:100]}")
        chain_nodes = draft.get("chain_nodes", [])
        stocks = draft.get("stocks", [])
        print(f"  📊 产业链节点: {len(chain_nodes)}")
        for node in chain_nodes[:5]:
            print(f"    - {node.get('level1', '?')} > {node.get('level2', '?')} > {node.get('level3', '?')}")
        print(f"  📊 映射个股: {len(stocks)}")
        for s in stocks[:5]:
            print(f"    - {s.get('stock_code', '?')} {s.get('stock_name', '?')} ({s.get('role', '?')})")

        # 验证数据结构
        assert "topic_name" in draft, "缺少 topic_name"
        assert "chain_nodes" in draft, "缺少 chain_nodes"
        assert "stocks" in draft, "缺少 stocks"
        assert len(chain_nodes) > 0, "产业链节点不能为空"
        assert len(stocks) > 0, "个股映射不能为空"

        for s in stocks:
            assert "stock_code" in s, f"个股缺少 stock_code: {s}"
            assert "stock_name" in s, f"个股缺少 stock_name"

        print(f"  ✅ 数据结构验证通过")

        # 保存草稿到 DB
        draft_id = db.create_analysis_draft(
            topic.get("topic_id"),
            topic.get("topic_name", "test"),
            draft,
        )
        print(f"  ✅ 已保存草稿 #{draft_id}")

        return draft
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# Test 6: 发酵观察
# ============================================================
def test_fermentation():
    """测试 generate_fermentation_observations"""
    print("\n" + "="*60)
    print("TEST 6: 发酵观察测试")
    print("="*60)

    import core.ai_client as ac
    from core.fetch_news import fetch_news

    # 搜索近期新闻
    print("  [1/2] 搜索新闻...")
    try:
        raw_news = fetch_news(
            time_range="最近 24 小时",
            selected_categories=["科技成长", "低空经济"],
            max_results_per_query=3,
        )
    except Exception as e:
        print(f"  ⚠️ 搜索失败: {e}")
        return None

    if len(raw_news) < 3:
        print(f"  ⚠️ 新闻数量不足 ({len(raw_news)}), 跳过")
        return None

    print(f"  ✅ 搜索到 {len(raw_news)} 条新闻")

    # AI 发酵观察
    print("  [2/2] AI 发酵观察...")
    try:
        observations = ac.generate_fermentation_observations(
            raw_news=raw_news,
            api_key=API_KEY,
            base_url=BASE_URL,
            model=MODEL,
            existing_themes=["固态电池", "低空经济"],
        )
        print(f"  ✅ 生成 {len(observations)} 条发酵观察")
        for i, obs in enumerate(observations[:5]):
            print(f"  [{i+1}] {obs.get('topic_name', '?')} "
                  f"(发酵分: {obs.get('fermentation_score', '?')}, "
                  f"状态: {obs.get('status', '?')})")

        # 验证数据结构
        assert len(observations) > 0, "应至少返回 1 条观察"
        for obs in observations:
            assert "topic_name" in obs, f"缺少 topic_name"
            assert "fermentation_score" in obs, f"缺少 fermentation_score"
        print(f"  ✅ 数据结构验证通过")
        return observations
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# Test 7: Prompt 模板和验证器完整性
# ============================================================
def test_prompts_and_validators():
    """验证所有 Prompt 模板和验证器是否正确加载"""
    print("\n" + "="*60)
    print("TEST 7: Prompt 模板和验证器完整性")
    print("="*60)

    from core.ai_prompts import (
        SYSTEM_PROMPT, HOT_TOPICS_PROMPT, FERMENTATION_OBSERVATION_PROMPT,
        PREDICTIONS_PROMPT, CANDIDATE_TOPICS_PROMPT, ENTITY_EXTRACTION_PROMPT,
        CHAIN_DECOMPOSITION_PROMPT, STOCK_MAPPING_PROMPT,
    )
    from core.ai_validators import (
        validate_theme_analysis, validate_hot_topics, validate_predictions,
        validate_fermentation_observations, validate_candidate_topics,
        validate_chain_decomposition, validate_stock_mapping,
        _extract_json, _repair_truncated_json, flatten_chains,
    )

    prompts = {
        "SYSTEM_PROMPT": SYSTEM_PROMPT,
        "HOT_TOPICS_PROMPT": HOT_TOPICS_PROMPT,
        "FERMENTATION_OBSERVATION_PROMPT": FERMENTATION_OBSERVATION_PROMPT,
        "PREDICTIONS_PROMPT": PREDICTIONS_PROMPT,
        "CANDIDATE_TOPICS_PROMPT": CANDIDATE_TOPICS_PROMPT,
        "ENTITY_EXTRACTION_PROMPT": ENTITY_EXTRACTION_PROMPT,
        "CHAIN_DECOMPOSITION_PROMPT": CHAIN_DECOMPOSITION_PROMPT,
        "STOCK_MAPPING_PROMPT": STOCK_MAPPING_PROMPT,
    }

    for name, prompt in prompts.items():
        assert isinstance(prompt, str), f"{name} 不是字符串"
        assert len(prompt) > 100, f"{name} 太短: {len(prompt)} 字符"
        print(f"  ✅ {name}: {len(prompt)} 字符")

    # 测试 JSON 提取和修复
    test_json = '一些前缀文本 {"topics": [{"theme_name": "测试", "summary": "测试摘要"}]} 后缀'
    extracted = _extract_json(test_json)
    parsed = json.loads(extracted)
    assert "topics" in parsed
    print(f"  ✅ JSON 提取: OK")

    # 测试 JSON 修复
    truncated = '{"topics": [{"theme_name": "测试", "summary": "测试摘要"'
    repaired = _repair_truncated_json(truncated)
    parsed_repaired = json.loads(repaired)
    assert "topics" in parsed_repaired
    print(f"  ✅ JSON 修复: OK")

    # 测试 flatten_chains
    chains = [
        {
            "level1": "上游",
            "level2": "原材料",
            "level3": "正极材料",
            "stocks": [
                {"stock_code": "300750", "stock_name": "宁德时代", "role": "龙头"},
            ]
        }
    ]
    rows, quality = flatten_chains({"theme_name": "固态电池", "chains": chains})
    assert len(rows) > 0
    assert rows[0]["stock_code"] == "300750"
    print(f"  ✅ flatten_chains: OK ({len(rows)} rows)")

    print(f"  ✅ 所有 Prompt 和验证器测试通过")


# ============================================================
# Test 8: 数据新鲜度模块
# ============================================================
def test_data_freshness():
    """测试数据新鲜度计算"""
    print("\n" + "="*60)
    print("TEST 8: 数据新鲜度模块测试")
    print("="*60)

    from core.data_freshness import compute_global_freshness, compute_theme_freshness, get_freshness_label
    from datetime import datetime, timedelta
    import core.database as db

    # 从数据库获取真实数据
    raw = db.get_freshness_raw_data()
    if raw:
        parsed = []
        for r in raw:
            last_update = None
            if r.get("last_update"):
                try:
                    last_update = datetime.strptime(r["last_update"][:19], "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    pass
            last_news = None
            if r.get("last_news"):
                try:
                    last_news = datetime.strptime(r["last_news"][:19], "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    pass
            parsed.append({
                "theme_name": r["theme_name"],
                "last_update": last_update,
                "last_news": last_news,
            })

        gf = compute_global_freshness(parsed)
        print(f"  ✅ 全局新鲜度: 健康度 {gf.health_pct}%")
        print(f"  📊 新鲜: {gf.fresh_count}, 一般: {gf.normal_count}, 过期: {gf.stale_count}")
        print(f"  📊 总题材: {gf.total_themes}")

        # 单个题材新鲜度
        for theme_data in parsed[:3]:
            f = compute_theme_freshness(
                theme_data["theme_name"],
                theme_data.get("last_update"),
                theme_data.get("last_news"),
            )
            print(f"  - {f.theme_name}: {f.overall_score}分 ({f.level})")

        print(f"  ✅ 数据新鲜度模块测试通过")
    else:
        print(f"  ⚠️ 数据库无题材数据，跳过新鲜度测试")


# ============================================================
# Test 9: Serenity 四维分析与 JSON 序列化
# ============================================================
def test_serenity_full():
    """测试 Serenity 完整分析流程"""
    print("\n" + "="*60)
    print("TEST 9: Serenity 四维分析完整流程")
    print("="*60)

    import core.serenity_analyzer as sa

    # 测试所有维度
    bn = sa.analyze_bottleneck(
        industry_position="upstream",
        domestic_substitution_rate=0.12,
        import_dependency=0.85,
        tech_autonomy_score=30,
        moat_description="半导体设备国产替代，技术壁垒极高",
        key_bottleneck_items=["光刻机", "刻蚀机", "离子注入"],
        substitution_timeline="预计 5-8 年",
    )
    print(f"  ✅ 卡脖子指数: {bn.score} ({bn.level.value})")

    inst = sa.analyze_institutional_behavior(
        northbound_flow_score=78,
        margin_trading_score=65,
        dragon_tiger_score=55,
        institution_research_score=70,
        signals_summary="北向持续流入，机构密集调研",
    )
    print(f"  ✅ 机构信号: {inst.score} ({inst.signal.value})")

    val = sa.analyze_long_term_value(
        roe=22.5,
        gross_margin=48.0,
        cashflow_quality_score=75,
        moat_score=80,
        moat_type="技术壁垒+专利",
        value_summary="高毛利+强护城河",
    )
    print(f"  ✅ 长线价值: {val.score}")

    vr = sa.analyze_valuation_reset(
        is_paradigm_shift=True,
        is_value_trap=False,
        industry_cycle_phase="复苏初期",
        policy_driver_score=85,
        reset_trigger="国家大基金三期 + 新质生产力政策",
        risk_warning="技术突破进度不及预期",
    )
    print(f"  ✅ 估值重置: {vr.score} ({vr.regime.value})")

    # 综合报告
    report = sa.generate_serenity_report(
        target_name="中微公司",
        target_type="stock",
        bottleneck=bn,
        institutional=inst,
        value=val,
        valuation_reset=vr,
        investment_thesis="半导体设备国产替代核心标的，政策+资金双驱动",
    )
    print(f"  ✅ 综合置信度: {report.composite_score} ({report.composite_grade})")

    # JSON 序列化
    json_str = sa.report_to_json(report)
    parsed = json.loads(json_str)
    assert parsed["composite_score"] == report.composite_score
    assert parsed["bottleneck"]["score"] == bn.score
    print(f"  ✅ JSON 序列化: OK ({len(json_str)} 字符)")

    # 快速评分
    quick = sa.quick_score_stock("测试股票", domestic_substitution_rate=0.08, northbound_flow_score=82, roe=25)
    print(f"  ✅ 快速评分: {quick.composite_score} ({quick.composite_grade})")

    # 启发式
    all_h = sa.DecisionHeuristic.all_heuristics()
    assert len(all_h) == 12
    print(f"  ✅ 决策启发式: {len(all_h)} 条")

    print(f"  ✅ Serenity 完整流程测试通过")


# ============================================================
# Main
# ============================================================
def main():
    print("="*60)
    print("🚀 A股题材追踪器 - 核心功能测试套件")
    print(f"📡 API: {BASE_URL} | Model: {MODEL}")
    print(f"🔑 Key: {API_KEY[:15]}...{API_KEY[-5:]}")
    print("="*60)

    results = {}

    # Test 1: API 连通性 (必须先通过)
    results["api_connectivity"] = test_api_connectivity()
    if not results["api_connectivity"]:
        print("\n❌ API 连通性测试失败，终止后续测试")
        return results

    # Test 7: Prompt 模板 (不需要 API)
    try:
        test_prompts_and_validators()
        results["prompts_validators"] = True
    except Exception as e:
        print(f"  ❌ Prompt 测试失败: {e}")
        results["prompts_validators"] = False

    # Test 8: 数据新鲜度
    try:
        test_data_freshness()
        results["data_freshness"] = True
    except Exception as e:
        print(f"  ❌ 数据新鲜度测试失败: {e}")
        results["data_freshness"] = False

    # Test 9: Serenity
    try:
        test_serenity_full()
        results["serenity"] = True
    except Exception as e:
        print(f"  ❌ Serenity 测试失败: {e}")
        results["serenity"] = False

    # Test 2: 热点题材 (API, ~30s)
    try:
        results["hot_topics"] = test_hot_topics_generation() is not None
    except Exception as e:
        print(f"  ❌ 热点题材测试异常: {e}")
        results["hot_topics"] = False

    # Test 3: 题材分析 (API, ~60s)
    try:
        results["theme_analysis"] = test_theme_analysis() is not None
    except Exception as e:
        print(f"  ❌ 题材分析测试异常: {e}")
        results["theme_analysis"] = False

    # Test 4: 新闻+候选题材 (API, ~90s)
    try:
        results["news_candidates"] = test_news_and_candidates() is not None
    except Exception as e:
        print(f"  ❌ 新闻候选测试异常: {e}")
        results["news_candidates"] = False

    # Test 5: 两阶段草稿 (API, ~120s)
    try:
        results["analysis_draft"] = test_analysis_draft() is not None
    except Exception as e:
        print(f"  ❌ 草稿生成测试异常: {e}")
        results["analysis_draft"] = False

    # Test 6: 发酵观察 (API, ~60s)
    try:
        results["fermentation"] = test_fermentation() is not None
    except Exception as e:
        print(f"  ❌ 发酵观察测试异常: {e}")
        results["fermentation"] = False

    # 汇总
    print("\n" + "="*60)
    print("📊 测试结果汇总")
    print("="*60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, status in results.items():
        icon = "✅" if status else "❌"
        print(f"  {icon} {name}: {'PASS' if status else 'FAIL'}")
    print(f"\n  🎯 通过率: {passed}/{total} ({passed/total*100:.0f}%)")

    return results


if __name__ == "__main__":
    main()
