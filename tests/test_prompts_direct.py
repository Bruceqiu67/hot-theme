"""
Direct LLM prompt testing - bypasses web search for fast validation.
Tests all prompt templates produce valid JSON.
"""
import sys, json, time, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from core.ai_prompts import (
    SYSTEM_PROMPT, HOT_TOPICS_PROMPT, CANDIDATE_TOPICS_PROMPT,
    CHAIN_DECOMPOSITION_PROMPT, STOCK_MAPPING_PROMPT,
    FERMENTATION_OBSERVATION_PROMPT, PREDICTIONS_PROMPT,
)
from core.ai_validators import (
    _extract_json, _repair_truncated_json,
    validate_hot_topics, validate_candidate_topics,
    validate_chain_decomposition, validate_stock_mapping,
    validate_fermentation_observations, validate_predictions,
    validate_theme_analysis,
)

API_KEY = "sk-your-deepseek-api-key"
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-flash"
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

def call_llm(system_prompt, user_content, temperature=0.6, max_tokens=4096):
    """Call LLM and extract JSON from response"""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=temperature, max_tokens=max_tokens, timeout=180,
    )
    choice = response.choices[0]
    content = choice.message.content or getattr(choice.message, 'reasoning_content', '')
    if not content:
        raise RuntimeError("Empty response")
    json_text = _extract_json(content.strip())
    try:
        return json.loads(json_text), choice.finish_reason
    except json.JSONDecodeError:
        repaired = _repair_truncated_json(json_text)
        return json.loads(repaired), choice.finish_reason

# ====== Test 1: HOT_TOPICS_PROMPT ======
print("=" * 60)
print("TEST A: HOT_TOPICS_PROMPT (hot topic discovery)")
print("=" * 60)
t0 = time.time()
data, reason = call_llm(
    HOT_TOPICS_PROMPT,
    "Based on your knowledge as of 2026, list the top 8 hottest A-share thematic sectors right now. Focus on China A-share market themes with active catalyst events.",
    temperature=0.7, max_tokens=4096,
)
topics = validate_hot_topics(data.get("topics", []))
print(f"  SUCCESS ({time.time()-t0:.0f}s): {len(topics)} topics")
for i, t in enumerate(topics[:8]):
    print(f"  [{i+1}] {t['theme_name']}: {t.get('summary','')[:80]}")
assert len(topics) >= 3, f"Too few topics: {len(topics)}"
for t in topics:
    assert 'theme_name' in t and 'summary' in t
print(f"  VALIDATION: OK ({len(topics)} topics)\n")

# ====== Test 2: CHAIN_DECOMPOSITION_PROMPT ======
print("=" * 60)
print("TEST B: CHAIN_DECOMPOSITION_PROMPT (supply chain decomposition)")
print("=" * 60)
t0 = time.time()
topic_data = {
    "topic": {
        "topic_name": "固态电池",
        "trigger_event": "多家车企宣布搭载固态电池车型量产时间表",
        "core_logic": "固态电池能量密度翻倍+安全性革命，产业链重构",
    },
    "evidence_items": [
        {"news_id":"n1","title":"丰田固态电池2027年量产","summary":"丰田宣布全固态电池量产计划","source":"test"},
        {"news_id":"n2","title":"宁德时代固态进展","summary":"宁德发布凝聚态电池，能量密度500Wh/kg","source":"test"},
    ],
}
data, reason = call_llm(
    CHAIN_DECOMPOSITION_PROMPT,
    json.dumps(topic_data, ensure_ascii=False),
    temperature=0.45, max_tokens=4096,
)
chain = validate_chain_decomposition(data)
nodes = chain.get("chain_nodes", [])
print(f"  SUCCESS ({time.time()-t0:.0f}s): {len(nodes)} chain nodes")
print(f"  Theme definition: {chain.get('theme_definition','')[:120]}")
for n in nodes[:5]:
    print(f"    {n.get('level1','')} > {n.get('level2','')} > {n.get('level3','')}")
assert len(nodes) >= 4
assert chain.get('theme_definition')
print(f"  VALIDATION: OK\n")

# ====== Test 3: STOCK_MAPPING_PROMPT ======
print("=" * 60)
print("TEST C: STOCK_MAPPING_PROMPT (A-share stock mapping)")
print("=" * 60)
t0 = time.time()
mapping_data = {
    "topic": {"topic_name": "固态电池", "heat_score": 92},
    "chain_decomposition": {
        "chain_nodes": nodes[:3],  # Test with first 3 nodes only
        "core_logic": chain.get("core_logic", ""),
    },
    "evidence_items": topic_data["evidence_items"],
    "output_limits": {"max_stocks_per_node": 3, "max_total_stocks": 8, "keep_text_brief": True},
}
data, reason = call_llm(
    STOCK_MAPPING_PROMPT,
    json.dumps(mapping_data, ensure_ascii=False),
    temperature=0.35, max_tokens=6144,
)
stocks = validate_stock_mapping(data, nodes[:3])
print(f"  SUCCESS ({time.time()-t0:.0f}s): {len(stocks)} stocks mapped")
for s in stocks[:8]:
    print(f"    {s.get('stock_code','')} {s.get('stock_name','')}: {s.get('role','')} ({s.get('level1','')}>{s.get('level2','')})")
assert len(stocks) >= 3, f"Too few stocks: {len(stocks)}"
for s in stocks:
    assert len(s.get('stock_code', '')) == 6, f"Invalid stock code: {s.get('stock_code')}"
    assert s.get('stock_name'), f"Missing stock name"
print(f"  VALIDATION: OK\n")

# ====== Test 4: CANDIDATE_TOPICS_PROMPT ======
print("=" * 60)
print("TEST D: CANDIDATE_TOPICS_PROMPT (candidate topic extraction)")
print("=" * 60)
t0 = time.time()
sample_news = [
    {"news_id":"n1","title":"HBM需求爆发 国内封测厂受益","summary":"AI算力需求推动HBM出货量增长300%，国内长电科技、通富微电积极布局先进封装","source":"eastmoney.com","published_at":"2026-06-24","fetched_at":"2026-06-25","search_query":"半导体产业链","category":"半导体"},
    {"news_id":"n2","title":"固态电池概念掀涨停潮","summary":"宁德时代、比亚迪等发布固态电池进展，产业链上下游集体走强","source":"10jqka.com.cn","published_at":"2026-06-24","fetched_at":"2026-06-25","search_query":"固态电池","category":"新能源"},
    {"news_id":"n3","title":"低空经济政策加码 eVTOL适航认证加速","summary":"民航局发布低空经济新规，亿航智能等企业适航认证进度超预期","source":"cls.cn","published_at":"2026-06-23","fetched_at":"2026-06-25","search_query":"低空经济","category":"低空经济"},
    {"news_id":"n4","title":"人形机器人产业链迎来量产元年","summary":"特斯拉Optimus、优必选等机器人量产在即，减速器、传感器等核心零部件需求爆发","source":"stcn.com","published_at":"2026-06-23","fetched_at":"2026-06-25","search_query":"机器人","category":"机器人"},
    {"news_id":"n5","title":"先进封装产能紧缺 CoWoS供不应求","summary":"台积电CoWoS产能持续紧张，国内封测企业加速布局先进封装技术","source":"eastmoney.com","published_at":"2026-06-22","fetched_at":"2026-06-25","search_query":"先进封装","category":"半导体"},
]
valid_ids = {n["news_id"] for n in sample_news}
payload = {"raw_news": sample_news, "key_entities": ["HBM","固态电池","低空经济","人形机器人","先进封装","CoWoS"]}
data, reason = call_llm(
    CANDIDATE_TOPICS_PROMPT,
    json.dumps(payload, ensure_ascii=False),
    temperature=0.55, max_tokens=8192,
)
topics = validate_candidate_topics(data.get("topics", []), valid_ids)
print(f"  SUCCESS ({time.time()-t0:.0f}s): {len(topics)} candidate topics")
for i, t in enumerate(topics[:5]):
    print(f"  [{i+1}] {t['topic_name']} (type:{t.get('topic_type','')}, specificity:{t.get('specificity_score','')})")
    print(f"       trigger: {t.get('trigger_event','')[:80]}")
assert len(topics) >= 2
for t in topics:
    assert 'topic_name' in t
print(f"  VALIDATION: OK\n")

# ====== Test 5: FERMENTATION_OBSERVATION_PROMPT ======
print("=" * 60)
print("TEST E: FERMENTATION_OBSERVATION_PROMPT")
print("=" * 60)
t0 = time.time()
ferm_payload = {
    "existing_themes": ["固态电池", "低空经济", "半导体设备"],
    "raw_news": sample_news,
}
data, reason = call_llm(
    FERMENTATION_OBSERVATION_PROMPT,
    json.dumps(ferm_payload, ensure_ascii=False),
    temperature=0.5, max_tokens=8192,
)
observations = validate_fermentation_observations(data.get("observations", []), valid_ids)
print(f"  SUCCESS ({time.time()-t0:.0f}s): {len(observations)} observations")
for i, obs in enumerate(observations[:5]):
    print(f"  [{i+1}] {obs['topic_name']}: {obs.get('trigger_event','')[:80]}")
assert len(observations) >= 1, f"Expected >=1 observation with 5 news items, got {len(observations)}"
for obs in observations:
    assert 'topic_name' in obs
print(f"  VALIDATION: OK\n")

# ====== Summary ======
print("=" * 60)
print("ALL DIRECT PROMPT TESTS PASSED")
print("=" * 60)
print("Tested prompts: HOT_TOPICS, CHAIN_DECOMPOSITION, STOCK_MAPPING, CANDIDATE_TOPICS, FERMENTATION_OBSERVATION")
print("All produce valid JSON output with proper validation.")
