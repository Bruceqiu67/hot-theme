"""
AI 客户端编排逻辑测试
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.ai_client as ai_client


def _nodes(count: int) -> list[dict]:
    return [
        {"level1": f"L1-{i}", "level2": f"L2-{i}", "level3": f"L3-{i}", "importance": "观察"}
        for i in range(count)
    ]


def test_generate_stock_mapping_batches_nodes(monkeypatch):
    calls = []

    def fake_batch(topic, chain_data, evidence_items, api_key, base_url, model):
        batch = chain_data["chain_nodes"]
        calls.append(len(batch))
        return [
            {
                "stock_code": f"00000{len(calls)}",
                "level1": batch[0]["level1"],
                "level2": batch[0]["level2"],
                "level3": batch[0]["level3"],
            }
        ]

    monkeypatch.setattr(ai_client, "_generate_stock_mapping_batch", fake_batch)
    stocks = ai_client.generate_stock_mapping(
        topic={"topic_name": "测试题材"},
        chain_data={"chain_nodes": _nodes(5)},
        evidence_items=[],
        api_key="test",
    )
    assert calls == [3, 2]
    assert len(stocks) == 2


def test_generate_stock_mapping_falls_back_to_single_node(monkeypatch):
    calls = []

    def fake_batch(topic, chain_data, evidence_items, api_key, base_url, model):
        batch = chain_data["chain_nodes"]
        calls.append(len(batch))
        if len(batch) > 1:
            raise RuntimeError("个股映射输出被截断，请重试")
        node = batch[0]
        return [
            {
                "stock_code": f"00000{len(calls)}",
                "level1": node["level1"],
                "level2": node["level2"],
                "level3": node["level3"],
            }
        ]

    monkeypatch.setattr(ai_client, "_generate_stock_mapping_batch", fake_batch)
    stocks = ai_client.generate_stock_mapping(
        topic={"topic_name": "测试题材"},
        chain_data={"chain_nodes": _nodes(3)},
        evidence_items=[],
        api_key="test",
    )
    assert calls == [3, 1, 1, 1]
    assert len(stocks) == 3
