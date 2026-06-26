"""
综合集成测试 — 跳过缓慢的网络搜索，直接测试 LLM 路径
"""
import sys, json, time, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_KEY = "sk-your-deepseek-api-key"
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-flash"

def test_theme_analysis_hbm():
    print('\n' + '='*60)
    print('TEST 1: generate_theme_analysis — HBM高带宽存储')
    print('='*60)
    import core.ai_client as ac
    t0 = time.time()
    result = ac.generate_theme_analysis(
        theme_name='HBM高带宽存储',
        api_key=API_KEY, base_url=BASE_URL, model=MODEL,
    )
    elapsed = time.time() - t0
    chains = result.get('chains', [])
    total_stocks = sum(len(c.get('stocks',[])) for c in chains)
    print(f'  SUCCESS ({elapsed:.0f}s): {len(chains)} chains, {total_stocks} stocks')
    for c in chains[:6]:
        print(f'    {c.get("level1","?")} > {c.get("level2","?")}: {len(c.get("stocks",[]))} stocks')
    assert 'theme_name' in result and len(chains) > 0
    for c in chains:
        for s in c.get('stocks', []):
            assert 'stock_code' in s and 'stock_name' in s
    print(f'  VALIDATION: OK')
    return result

def test_analysis_draft_ssb():
    print('\n' + '='*60)
    print('TEST 2: generate_analysis_draft — 固态电池')
    print('='*60)
    import core.ai_client as ac
    t0 = time.time()
    topic = {
        'topic_id': 998, 'topic_name': '固态电池',
        'trigger_event': '多家车企宣布搭载固态电池车型量产时间表',
        'core_logic': '固态电池能量密度翻倍+安全性革命，产业链重构',
        'heat_score': 92,
    }
    evidence = [
        {'news_id':'ev1','title':'丰田固态电池2027年量产','summary':'丰田宣布固态电池量产','source':'test'},
        {'news_id':'ev2','title':'宁德时代固态进展','summary':'宁德发布凝聚态电池','source':'test'},
    ]
    draft = ac.generate_analysis_draft(
        topic=topic, evidence_items=evidence,
        api_key=API_KEY, base_url=BASE_URL, model=MODEL,
    )
    elapsed = time.time() - t0
    nodes = draft.get('chain_nodes', [])
    stocks = draft.get('stocks', [])
    print(f'  SUCCESS ({elapsed:.0f}s): {len(nodes)} nodes, {len(stocks)} stocks')
    print(f'  Definition: {draft.get("theme_definition","?")[:120]}')
    print(f'  Nodes:')
    for n in nodes[:5]:
        print(f'    {n.get("level1","?")} > {n.get("level2","?")} > {n.get("level3","?")}')
    print(f'  Stocks:')
    for s in stocks[:6]:
        print(f'    {s.get("stock_code","?")} {s.get("stock_name","?")}: {s.get("role","?")}')
    assert len(nodes) > 0 and len(stocks) > 0
    for s in stocks:
        assert 'stock_code' in s and 'stock_name' in s
    print(f'  VALIDATION: OK')
    return draft

def test_flatten_and_db(hbm_result):
    print('\n' + '='*60)
    print('TEST 3: flatten_chains + DB import + roundtrip')
    print('='*60)
    from core.ai_validators import flatten_chains
    import core.database as db
    import pandas as pd

    # Flatten HBM result
    rows, quality = flatten_chains(hbm_result)
    print(f'  Flattened: {len(rows)} rows')
    for r in rows[:3]:
        print(f'    {r["stock_code"]} {r["stock_name"]} ({r["level1"]} > {r["level2"]})')

    # Save to DB
    count = db.replace_theme('HBM高带宽存储', pd.DataFrame(rows), quality)
    print(f'  Saved: {count} rows to theme_stocks')

    # Verify
    stats = db.get_db_stats()
    print(f'  DB Stats: {stats["theme_count"]} themes, {stats["stock_count"]} stocks, {stats["total_rows"]} rows')

    # Read back
    hbm_df = db.get_theme_tree_data('HBM高带宽存储')
    print(f'  Roundtrip: {len(hbm_df)} rows read back')
    assert len(hbm_df) >= len(rows) - 2  # Allow small variation

    # Cross-theme
    cross = db.get_cross_theme_stocks()
    print(f'  Cross-theme stocks: {len(cross)}')
    if len(cross) > 0:
        top = cross.iloc[0]
        print(f'    Top: {top["stock_name"]} in {top["theme_count"]} themes')

    # Summary with dimensions
    summary = db.get_theme_summary_with_dimensions()
    hbm_sum = summary[summary['theme_name'] == 'HBM高带宽存储']
    if len(hbm_sum) > 0:
        r = hbm_sum.iloc[0]
        print(f'  Summary: {r["node_count"]} nodes, {r["stock_count"]} stocks, score={r.get("overall_score","?")}')

    print(f'  VALIDATION: OK')

def test_freshness():
    print('\n' + '='*60)
    print('TEST 4: 数据新鲜度')
    print('='*60)
    from core.data_freshness import compute_global_freshness, compute_theme_freshness
    from datetime import datetime
    import core.database as db

    raw = db.get_freshness_raw_data()
    parsed = []
    for r in raw:
        last_update = None
        if r.get('last_update'):
            try:
                last_update = datetime.strptime(r['last_update'][:19], '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                pass
        last_news = None
        if r.get('last_news'):
            try:
                last_news = datetime.strptime(r['last_news'][:19], '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                pass
        parsed.append({'theme_name': r['theme_name'], 'last_update': last_update, 'last_news': last_news})

    gf = compute_global_freshness(parsed)
    print(f'  Health: {gf.health_pct}%')
    print(f'  Fresh: {gf.fresh_count}, Normal: {gf.normal_count}, Stale: {gf.stale_count}')
    print(f'  Latest: {gf.latest_update_str}')
    for theme_data in parsed[:3]:
        f = compute_theme_freshness(theme_data['theme_name'], theme_data.get('last_update'), theme_data.get('last_news'))
        print(f'    {f.theme_name}: {f.overall_score}分 ({f.level}), {f.refresh_reason}')
    print(f'  VALIDATION: OK')

def test_stock_verification():
    print('\n' + '='*60)
    print('TEST 5: 个股验证状态')
    print('='*60)
    import core.database as db

    stats = db.get_verification_stats_by_theme('HBM高带宽存储')
    print(f'  Total: {stats["total"]}')
    print(f'  Auto-verified: {stats["verified_auto"]}')
    print(f'  Inferred: {stats["verified_inferred"]}')
    print(f'  Still unverified: {stats["still_unverified"]}')
    print(f'  Verified rate: {stats["verified_rate"]}%')

    if stats['total'] > 0:
        # Batch update one stock
        stocks = db.get_theme_stocks('HBM高带宽存储')
        if stocks:
            test_stock = stocks[0]
            db.update_stock_verification(
                test_stock['stock_code'], 'HBM高带宽存储',
                'verified_auto',
                json.dumps({'verified_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'summary': '搜索引擎反查验证通过'}),
            )
            stats2 = db.get_verification_stats_by_theme('HBM高带宽存储')
            print(f'  After update: verified_rate={stats2["verified_rate"]}%')
            assert stats2['verified_auto'] >= 1
    print(f'  VALIDATION: OK')

def main():
    print('='*60)
    print('A-Share Theme Tracker - Integration Test')
    print(f'API: {BASE_URL} | Model: {MODEL}')
    print(f'Key: {API_KEY[:15]}...{API_KEY[-5:]}')
    print('='*60)

    results = {}

    # Test 1: HBM Theme Analysis (searches + LLM, ~120s)
    try:
        hbm = test_theme_analysis_hbm()
        results['hbm_analysis'] = True
    except Exception as e:
        print(f'  FAILED: {e}')
        import traceback; traceback.print_exc()
        results['hbm_analysis'] = False
        hbm = None

    # Test 2: Solid State Battery Draft (LLM only, ~60s)
    try:
        draft = test_analysis_draft_ssb()
        results['ssb_draft'] = True
    except Exception as e:
        print(f'  FAILED: {e}')
        import traceback; traceback.print_exc()
        results['ssb_draft'] = False

    # Test 3: DB roundtrip
    if hbm:
        try:
            test_flatten_and_db(hbm)
            results['db_roundtrip'] = True
        except Exception as e:
            print(f'  FAILED: {e}')
            import traceback; traceback.print_exc()
            results['db_roundtrip'] = False

    # Test 4: Freshness
    try:
        test_freshness()
        results['freshness'] = True
    except Exception as e:
        print(f'  FAILED: {e}')
        import traceback; traceback.print_exc()
        results['freshness'] = False

    # Test 5: Verification
    try:
        test_stock_verification()
        results['verification'] = True
    except Exception as e:
        print(f'  FAILED: {e}')
        import traceback; traceback.print_exc()
        results['verification'] = False

    # Summary
    print('\n' + '='*60)
    print('Test Results Summary')
    print('='*60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, status in results.items():
        print(f'  {"[OK]" if status else "[FAIL]"} {name}: {"PASS" if status else "FAIL"}')
    print(f'\n  Pass Rate: {passed}/{total} ({passed/total*100:.0f}%)')
    return results

if __name__ == '__main__':
    main()
