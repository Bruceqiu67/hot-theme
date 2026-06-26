"""
预置示例数据 — 为新用户提供 3 个近期热点题材的预制产业链数据。
所有数据标注 "示例" 来源，不与正式 AI 生成数据混淆。
"""

EXAMPLE_THEMES = [
    {
        "theme_name": "AI 算力",
        "summary": "人工智能大模型训练与推理所需的算力基础设施，涵盖 GPU/AI 芯片、光模块、服务器、数据中心等环节。2024-2025 年全球算力需求爆发式增长。",
        "breadth": 85,
        "event_density": 90,
        "capital_flow": 88,
        "sustainability": 80,
        "overall_score": 86,
        "quality_summary": "高景气赛道，事件密度极高，资金持续流入。英伟达 GB300 发布、国内算力基建政策持续催化。",
        "chains": [
            {
                "level1": "上游 — AI 芯片与算力硬件",
                "segments": [
                    {
                        "level2": "GPU / AI 加速芯片",
                        "level3": "",
                        "stocks": [
                            {"code": "688256", "name": "寒武纪", "market": "科创板", "role": "国产 AI 芯片龙头", "importance": "高", "source": "示例"},
                            {"code": "688041", "name": "海光信息", "market": "科创板", "role": "国产 GPU/CPU", "importance": "高", "source": "示例"},
                            {"code": "688047", "name": "龙芯中科", "market": "科创板", "role": "国产 CPU", "importance": "中", "source": "示例"},
                        ],
                    },
                    {
                        "level2": "光模块 / CPO",
                        "level3": "",
                        "stocks": [
                            {"code": "300308", "name": "中际旭创", "market": "创业板", "role": "全球光模块龙头", "importance": "高", "source": "示例"},
                            {"code": "300502", "name": "新易盛", "market": "创业板", "role": "高速光模块", "importance": "高", "source": "示例"},
                            {"code": "300394", "name": "天孚通信", "market": "创业板", "role": "光器件", "importance": "中", "source": "示例"},
                        ],
                    },
                    {
                        "level2": "HBM 存储",
                        "level3": "",
                        "stocks": [
                            {"code": "002049", "name": "紫光国微", "market": "主板", "role": "特种芯片", "importance": "中", "source": "示例"},
                            {"code": "603986", "name": "兆易创新", "market": "主板", "role": "NOR Flash / MCU", "importance": "中", "source": "示例"},
                        ],
                    },
                ],
            },
            {
                "level1": "中游 — 服务器与算力平台",
                "segments": [
                    {
                        "level2": "AI 服务器",
                        "level3": "",
                        "stocks": [
                            {"code": "000977", "name": "浪潮信息", "market": "主板", "role": "国内服务器龙头", "importance": "高", "source": "示例"},
                            {"code": "603019", "name": "中科曙光", "market": "主板", "role": "高端服务器/HPC", "importance": "高", "source": "示例"},
                            {"code": "000938", "name": "紫光股份", "market": "主板", "role": "服务器/交换机", "importance": "中", "source": "示例"},
                        ],
                    },
                    {
                        "level2": "算力租赁 / 云服务",
                        "level3": "",
                        "stocks": [
                            {"code": "300383", "name": "光环新网", "market": "创业板", "role": "IDC / 云计算", "importance": "中", "source": "示例"},
                            {"code": "603881", "name": "数据港", "market": "主板", "role": "数据中心运营", "importance": "中", "source": "示例"},
                        ],
                    },
                ],
            },
            {
                "level1": "下游 — AI 应用与终端",
                "segments": [
                    {
                        "level2": "大模型应用",
                        "level3": "",
                        "stocks": [
                            {"code": "688111", "name": "金山办公", "market": "科创板", "role": "WPS AI 办公", "importance": "高", "source": "示例"},
                            {"code": "300624", "name": "万兴科技", "market": "创业板", "role": "AI 创意工具", "importance": "中", "source": "示例"},
                        ],
                    },
                ],
            },
        ],
    },
    {
        "theme_name": "低空经济",
        "summary": "以无人机、eVTOL（电动垂直起降飞行器）为核心的低空空域商业化应用。涵盖飞行器制造、空管系统、通航运营、基础设施建设等环节。2024 年写入政府工作报告。",
        "breadth": 78,
        "event_density": 82,
        "capital_flow": 75,
        "sustainability": 70,
        "overall_score": 76,
        "quality_summary": "政策持续加码，多地开放低空试点。亿航智能获全球首张适航证，小鹏汇天等多家企业加速适航取证。",
        "chains": [
            {
                "level1": "上游 — 核心零部件",
                "segments": [
                    {
                        "level2": "电机与电驱",
                        "level3": "",
                        "stocks": [
                            {"code": "300124", "name": "汇川技术", "market": "创业板", "role": "电机/电驱龙头", "importance": "高", "source": "示例"},
                            {"code": "002664", "name": "信质集团", "market": "主板", "role": "电机定转子", "importance": "中", "source": "示例"},
                        ],
                    },
                    {
                        "level2": "电池",
                        "level3": "",
                        "stocks": [
                            {"code": "300750", "name": "宁德时代", "market": "创业板", "role": "航空级电池研发", "importance": "高", "source": "示例"},
                            {"code": "300014", "name": "亿纬锂能", "market": "创业板", "role": "eVTOL 电池供应", "importance": "中", "source": "示例"},
                        ],
                    },
                    {
                        "level2": "飞控/导航",
                        "level3": "",
                        "stocks": [
                            {"code": "300456", "name": "赛微电子", "market": "创业板", "role": "MEMS 惯导", "importance": "中", "source": "示例"},
                            {"code": "002151", "name": "北斗星通", "market": "主板", "role": "卫星导航芯片", "importance": "中", "source": "示例"},
                        ],
                    },
                ],
            },
            {
                "level1": "中游 — 飞行器制造与空管",
                "segments": [
                    {
                        "level2": "eVTOL 整机",
                        "level3": "",
                        "stocks": [
                            {"code": "600760", "name": "中航沈飞", "market": "主板", "role": "军用转民用无人机", "importance": "高", "source": "示例"},
                            {"code": "002389", "name": "航天彩虹", "market": "主板", "role": "无人机整机", "importance": "高", "source": "示例"},
                            {"code": "300900", "name": "广联航空", "market": "创业板", "role": "航空零部件", "importance": "中", "source": "示例"},
                        ],
                    },
                    {
                        "level2": "空管 / 低空智联网",
                        "level3": "",
                        "stocks": [
                            {"code": "002415", "name": "海康威视", "market": "主板", "role": "低空监控系统", "importance": "中", "source": "示例"},
                            {"code": "688568", "name": "中科星图", "market": "科创板", "role": "空天信息平台", "importance": "中", "source": "示例"},
                        ],
                    },
                ],
            },
            {
                "level1": "下游 — 运营与应用",
                "segments": [
                    {
                        "level2": "通航运营",
                        "level3": "",
                        "stocks": [
                            {"code": "000099", "name": "中信海直", "market": "主板", "role": "通航运营龙头", "importance": "高", "source": "示例"},
                            {"code": "600029", "name": "南方航空", "market": "主板", "role": "通航布局", "importance": "中", "source": "示例"},
                        ],
                    },
                ],
            },
        ],
    },
    {
        "theme_name": "人形机器人",
        "summary": "以特斯拉 Optimus 为代表的人形机器人产业链，涵盖减速器、伺服电机、传感器、灵巧手、机器视觉等核心环节。2025 年多家企业进入量产元年。",
        "breadth": 82,
        "event_density": 88,
        "capital_flow": 85,
        "sustainability": 75,
        "overall_score": 83,
        "quality_summary": "特斯拉 Optimus Gen-3 发布，Figure AI、宇树科技等持续迭代。国内优必选、傅利叶等加速量产，零部件国产替代加速。",
        "chains": [
            {
                "level1": "上游 — 核心零部件",
                "segments": [
                    {
                        "level2": "谐波减速器 / RV 减速器",
                        "level3": "",
                        "stocks": [
                            {"code": "688017", "name": "绿的谐波", "market": "科创板", "role": "谐波减速器龙头", "importance": "高", "source": "示例"},
                            {"code": "002472", "name": "双环传动", "market": "主板", "role": "RV/谐波减速器", "importance": "高", "source": "示例"},
                            {"code": "300503", "name": "昊志机电", "market": "创业板", "role": "谐波减速器", "importance": "中", "source": "示例"},
                        ],
                    },
                    {
                        "level2": "伺服电机 / 空心杯电机",
                        "level3": "",
                        "stocks": [
                            {"code": "300124", "name": "汇川技术", "market": "创业板", "role": "伺服系统龙头", "importance": "高", "source": "示例"},
                            {"code": "300660", "name": "江苏雷利", "market": "创业板", "role": "空心杯电机", "importance": "中", "source": "示例"},
                            {"code": "603728", "name": "鸣志电器", "market": "主板", "role": "控制电机", "importance": "中", "source": "示例"},
                        ],
                    },
                    {
                        "level2": "六维力传感器 / 触觉",
                        "level3": "",
                        "stocks": [
                            {"code": "300007", "name": "汉威科技", "market": "创业板", "role": "传感器平台", "importance": "中", "source": "示例"},
                            {"code": "603662", "name": "柯力传感", "market": "主板", "role": "力学传感器", "importance": "中", "source": "示例"},
                        ],
                    },
                ],
            },
            {
                "level1": "中游 — 整机与集成",
                "segments": [
                    {
                        "level2": "人形机器人整机",
                        "level3": "",
                        "stocks": [
                            {"code": "002747", "name": "埃斯顿", "market": "主板", "role": "工业+人形机器人", "importance": "高", "source": "示例"},
                            {"code": "688165", "name": "埃夫特", "market": "科创板", "role": "机器人整机", "importance": "中", "source": "示例"},
                        ],
                    },
                    {
                        "level2": "机器视觉",
                        "level3": "",
                        "stocks": [
                            {"code": "688003", "name": "天准科技", "market": "科创板", "role": "工业视觉", "importance": "中", "source": "示例"},
                            {"code": "300802", "name": "矩子科技", "market": "创业板", "role": "AOI 检测", "importance": "低", "source": "示例"},
                        ],
                    },
                ],
            },
            {
                "level1": "下游 — 应用场景",
                "segments": [
                    {
                        "level2": "智能制造 / 物流",
                        "level3": "",
                        "stocks": [
                            {"code": "300024", "name": "机器人", "market": "创业板", "role": "工业机器人龙头", "importance": "高", "source": "示例"},
                            {"code": "688777", "name": "中控技术", "market": "科创板", "role": "工业自动化", "importance": "中", "source": "示例"},
                        ],
                    },
                ],
            },
        ],
    },
]
