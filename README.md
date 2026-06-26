---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 1cfef3cb409413a6dead47d1940ed319_5c2e6927702d11f1986d525400d9a7a1
    ReservedCode1: FW93k7+juTGuFI4KfO+l/8/9MRov3noSbc0fEV51s0FjcNAkkoragVp/ckjeylRi0YlVZxIkoJ3LO/2i8SCqyz9Law/NAe19HMk2avevJq343DUssqwwUsD9gcmn8uqYIVqjtpj4Iks1IdiJFmSSfCuucgs13sEMX94ZMufbEebRk+TiqdyiVCwW6PU=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 1cfef3cb409413a6dead47d1940ed319_5c2e6927702d11f1986d525400d9a7a1
    ReservedCode2: FW93k7+juTGuFI4KfO+l/8/9MRov3noSbc0fEV51s0FjcNAkkoragVp/ckjeylRi0YlVZxIkoJ3LO/2i8SCqyz9Law/NAe19HMk2avevJq343DUssqwwUsD9gcmn8uqYIVqjtpj4Iks1IdiJFmSSfCuucgs13sEMX94ZMufbEebRk+TiqdyiVCwW6PU=
---

# A-Share Theme Tracker

> AI-powered industry chain analysis for A-share thematic investing — built for quants, analysts, and PMs.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Framework](https://img.shields.io/badge/Streamlit-1.x-red)
![Tests](https://img.shields.io/badge/tests-300%20passed-green)
![Version](https://img.shields.io/badge/version-v1.0-blue)

---

## Features

- **Serenity 四维分析框架** — 从热度(Hype)、持续性(Durability)、产业链深度(Depth)、个股映射精度(Mapping)四个维度评估题材质量，告别单一热度排序
- **Bloomberg Terminal 暗色主题** — 深色专业 UI，控制台级别信息密度，<3 秒定位关键数据
- **两阶段 AI 草稿工作台** — 产业链定义与个股映射分离，支持逐节点编辑、验证后入库，避免脏数据污染主库
- **个股自动验证链路** — 搜索反查 + 财报验证双阶段机制，将"待核验"字段比例从近 100% 降至 30% 以下
- **多题材并排对比** — 2-3 个题材的环节覆盖、共有个股、质量评分横向比较
- **数据新鲜度仪表盘** — 实时展示各题材数据健康度，按新鲜度排序，自动提醒过期题材

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv

# 2. Install dependencies
.venv\Scripts\Activate.ps1    # Windows
source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

# 3. Launch
双击启动.bat                  # Windows (recommended)
streamlit run app.py          # Terminal
```

Open `http://localhost:8501` in your browser. First-time users get a guided onboarding: welcome → API key setup → sample data load (AI computing, low-altitude economy, humanoid robots).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| UI | Streamlit |
| Storage | SQLite |
| Data | pandas |
| AI | OpenAI-compatible API (DeepSeek / OpenAI) |
| Search | ddgs |
| Market Data | akshare (free, no registration) |
| Graph | pyvis |

## Project Structure

```text
a-share-theme-tracker/
├── app.py                        # Streamlit entry point
├── config.py                     # Global config
├── ui_components.py              # Shared UI (Bloomberg theme, badges)
├── 双击启动.bat                   # One-click launcher (Windows)
├── core/
│   ├── ai_client.py              # AI calls, web search, JSON repair
│   ├── ai_prompts.py             # Prompt templates
│   ├── ai_validators.py          # Output validation
│   ├── database.py               # SQLite schema, migration, import, export
│   ├── fetch_news.py             # News scraping, dedup, heat scoring
│   ├── market_data.py            # AKShare market data
│   ├── stock_verifier.py         # Auto-verification: search + financials
│   ├── data_freshness.py         # Freshness scoring & dashboard
│   ├── token_monitor.py          # API token usage
│   ├── serenity_analyzer.py      # Serenity 4D analysis framework
│   └── constants.py              # Constants
├── views/                        # Page views (theme list, hot topics, drafts, etc.)
├── tasks/                        # Task manager, onboarding, watchlist, reports
├── tests/                        # 300 unit & integration tests
├── data/                         # Local data (.gitignored)
├── lib/                          # Frontend assets
├── requirements.txt
└── README.md
```

## Local Data & Security

The following are `.gitignored` and must never be committed:

| File | Risk |
|------|------|
| `data/*.db` | Local database |
| `data/api_config.json` | API keys |
| `data/hot_topics.json` | Session cache |
| `.streamlit/secrets.toml` | Secrets |

All data stays on your machine. No telemetry, no cloud sync, no external calls beyond the AI and market data APIs you configure.
*（内容由AI生成，仅供参考）*
