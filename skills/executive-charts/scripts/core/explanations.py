# Complete 45+ McKinsey / Aviation Executive Chart & KPI Explanations Dictionary
import json

CHART_EXPLANATIONS_DATA = {
    "mc01": {
        "title": "民航客货运主营总营收",
        "overview": "反映民航航空集团在考核周期内的客运、货邮运输及航空附加服务的主营业务结算总收入。",
        "type": "指标卡",
        "period": "2025Q1 决算周期",
        "comparison": "当期值与客货运分部构成占比",
        "structure": {
            "xAxis": { "name": "时间截面", "meaning": "季度决算时点", "range": "2025Q1" },
            "yAxis": { "name": "主营收入 (亿元)", "meaning": "含税主营结算总金额", "range": "¥28.5 亿 ~ ¥48.5 亿" },
            "series": [{ "name": "客运业务贡献", "desc": "主营客运收入占比 82.4%" }]
        },
        "metrics": [{
            "name": "客运总收入",
            "definition": "航空公司各航线承运旅客产生的客票销售净结算金额。",
            "formula": "∑ 各航线承运旅客量 × 综合客单票价",
            "rule": "遵循民航总局与权责发生制结算口径。"
        }]
    },
    "mc02": {
        "title": "座公里收益 RASK / 客公里收益",
        "overview": "衡量航空公司每一可用座公里的创收能力，是民航收益管理的核心关键效率指标。",
        "type": "指标卡",
        "period": "2024Q1 ~ 2025Q1 (连续滚动 4 季度)",
        "comparison": "同比增减 (YoY) 与环比变动 (MoM)",
        "structure": {
            "xAxis": { "name": "同比基期", "meaning": "上年同期水平", "range": "2024Q1" },
            "yAxis": { "name": "单位收益 (元/座公里)", "meaning": "可用座公里平均客票收入", "range": "¥0.4500 ~ ¥0.5820" },
            "series": [{ "name": "同比增速", "desc": "红涨绿跌标准配色" }]
        },
        "metrics": [{
            "name": "座公里收益 (RASK)",
            "definition": "主营客运总收入除以可用座公里 (ASK) 总量。",
            "formula": "客运总收入 ÷ 可用座公里 (ASK)",
            "rule": "全航线网络健康阈值建议不低于 ¥0.4800 / 座公里。"
        }]
    },
    "mc03": {
        "title": "综合客座率 PLF / 常旅客留存率",
        "overview": "实时映射过去 12 个滚动自然月机队整体综合客座率的平滑演变轨迹与常旅客粘性。",
        "type": "指标卡",
        "period": "近 12 个滚动自然月",
        "comparison": "月度连续时序波动走势",
        "structure": {
            "xAxis": { "name": "月份序列", "meaning": "M1 ~ M12 连续走势", "range": "滚动 12 个月" },
            "yAxis": { "name": "客座率 (%)", "meaning": "实际承运周转量占运力投入比重", "range": "75% ~ 92%" },
            "series": [{ "name": "12M 客座率火花线", "desc": "渐变填充火花线" }]
        },
        "metrics": [{
            "name": "客座率 (Passenger Load Factor)",
            "definition": "收入客公里 (RPK) 与可用座公里 (ASK) 的比率。",
            "formula": "收入客公里 (RPK) ÷ 可用座公里 (ASK) × 100%",
            "rule": "主干线网络基准线建议维持在 85.0% 以上。"
        }]
    },
    "mc04": {
        "title": "机队运力投入 ASK 年度规划达成进度",
        "overview": "量化考核期内机队可用座公里 (ASK) 运力投放总规模相对于年度预算目标的推进比例。",
        "type": "指标卡",
        "period": "2025 全年度考核期",
        "comparison": "当前实际投放 vs 100% 年度规划线",
        "structure": {
            "xAxis": { "name": "进度区间", "meaning": "0% ~ 100% 达成率", "range": "0% ~ 100%" },
            "yAxis": { "name": "可用座公里", "meaning": "已完成投放运力 (亿座公里)", "range": "0 ~ 525 亿座公里" },
            "series": [{ "name": "运力达成进度条", "desc": "深海蓝填充进度条" }]
        },
        "metrics": [{
            "name": "可用座公里 (ASK)",
            "definition": "各飞行航段可用座位数与该航段飞行距离公里的乘积之和。",
            "formula": "∑ (航段可用座位数 × 航段距离 km)",
            "rule": "衡量航空公司总运力供给的核心标准量纲。"
        }]
    },
    "mc05": {
        "title": "全航网综合航班正常率 (OTP)",
        "overview": "实时监控航空集团全网络每日及季度实际执行航班的正点出港与到港比例。",
        "type": "指标卡",
        "period": "实时 / 季度监控",
        "comparison": "对标民航局五星航司 90.0% 基准线",
        "structure": {
            "xAxis": { "name": "正常率区间", "meaning": "0% ~ 100%", "range": "0% ~ 100%" },
            "yAxis": { "name": "OTP 得分", "meaning": "正点航班比例", "range": "80% ~ 100%" },
            "series": [{ "name": "OTP 仪表", "desc": "半环进度刻度" }]
        },
        "metrics": [{
            "name": "航班正常率 (On-Time Performance)",
            "definition": "正常出港/到港航班架次占实际飞行总架次的比重。",
            "formula": "正常航班架次 ÷ 实际执行总架次 × 100%",
            "rule": "五星级航司考核基准目标不低于 90.0%。"
        }]
    },
    "mc06": {
        "title": "运力供给 (ASK) vs 旅客周转 (RPK) 双维裂变",
        "overview": "成对并列展示运力投入供给规模与有效客运周转转化规模，直观判断供需匹配度。",
        "type": "指标卡",
        "period": "2025Q1 决算周期",
        "comparison": "ASK 与 RPK 同期并列与同比",
        "structure": {
            "xAxis": { "name": "双维指标", "meaning": "ASK vs RPK", "range": "成对比较" },
            "yAxis": { "name": "周转规模 (亿)", "meaning": "座公里 / 客公里", "range": "40 ~ 60 亿" },
            "series": [{ "name": "供给与周转", "desc": "双柱成对" }]
        },
        "metrics": [{
            "name": "周转匹配转化率",
            "definition": "有效完成旅客周转量占总投入运力座公里的百分比。",
            "formula": "RPK ÷ ASK × 100%",
            "rule": "数值越高说明运力投放效率越高，产销匹配越佳。"
        }]
    },
    "mc07": {
        "title": "国内民航总营收战略排位与梯队徽章",
        "overview": "定位航司在全国航空运输市场总营收体量与市场份额的战略顺位及梯队评级。",
        "type": "指标卡",
        "period": "连续 3 季度决算",
        "comparison": "全行业市场占有率与排位",
        "structure": {
            "xAxis": { "name": "排位序列", "meaning": "行业 #1 ~ #10", "range": "#1" },
            "yAxis": { "name": "市场占有率", "meaning": "营收占全行业大盘比重", "range": "0% ~ 40%" },
            "series": [{ "name": "排位徽章", "desc": "S级领跑勋章" }]
        },
        "metrics": [{
            "name": "市场占有率 (Market Share)",
            "definition": "航司主营收入占全国民航客运大盘总额的比例。",
            "formula": "航司营收 ÷ 全行业总营收 × 100%",
            "rule": "达到 30% 以上具备核心枢纽定价话语权。"
        }]
    },
    "mc08": {
        "title": "机场地面保障与延误超支红线监控",
        "overview": "监控各机场配餐、地面摆渡、旅客延误改签安置费用的超支比例，触发 5.0% 红线警示。",
        "type": "指标卡",
        "period": "当期成本管控",
        "comparison": "超支率 vs 5.0% 预算红线",
        "structure": {
            "xAxis": { "name": "支出节点", "meaning": "地面保障与延误支出", "range": "全航网" },
            "yAxis": { "name": "超支率 (%)", "meaning": "超出预算配额百分比", "range": "0% ~ 10%" },
            "series": [{ "name": "超支警示", "desc": "黄牌预警边框" }]
        },
        "metrics": [{
            "name": "保障费用超支率",
            "definition": "实际延误及地面支出超出下达预算的比例。",
            "formula": "(实际支出 - 预算额) ÷ 预算额 × 100%",
            "rule": "超支率 > 5.0% 触发黄牌预警并启动成本追溯。"
        }]
    },
    "mc09": {
        "title": "客运航线网络市场结构 (多段分部占比)",
        "overview": "通过双色阶冷色调复合分段条展示国内干支线与国际远程航线的营收与运力结构。",
        "type": "指标卡",
        "period": "2025Q1 报告期",
        "comparison": "国内 vs 国际 100% 结构",
        "structure": {
            "xAxis": { "name": "结构比例", "meaning": "国内 72% vs 国际 28%", "range": "0% ~ 100%" },
            "yAxis": { "name": "营收金额", "meaning": "国内 ¥34.9亿 vs 国际 ¥13.6亿", "range": "¥48.5 亿" },
            "series": [{ "name": "结构分段条", "desc": "深海蓝与板岩蓝灰" }]
        },
        "metrics": [{
            "name": "国内国际收入比",
            "definition": "国内航线与国际及地区航线收入的构成配比。",
            "formula": "国内营收 : 国际营收",
            "rule": "国际枢纽战略目标国内与国际比重约 7:3。"
        }]
    },
    "mc10": {
        "title": "全网客单实际结算票价 (中位数与离散极差)",
        "overview": "基于全网千万级客票有效样本，量化客单票价的中位数、均值与极值区间离散度。",
        "type": "指标卡",
        "period": "2025Q1 票务大数据",
        "comparison": "中位数 vs 均值 vs 极值区间",
        "structure": {
            "xAxis": { "name": "票价区间", "meaning": "¥320 ~ ¥1,850", "range": "极差空间" },
            "yAxis": { "name": "中位票价", "meaning": "¥680.0 (均值 ¥742.5)", "range": "人民币元" },
            "series": [{ "name": "极差条", "desc": "四分位离散度" }]
        },
        "metrics": [{
            "name": "中位客单票价 (Median Fare)",
            "definition": "全网出票价格序列中处于 50% 分位点的实际结算票价。",
            "formula": "Median(机票价格序列)",
            "rule": "消除极端特价票与高价两舱票对平均价格的扭曲。"
        }]
    },
    "table_airline_main": {
        "title": "民航核心航线与机队运营效能全要素透视表",
        "overview": "全景穿透各主干线及区域航线的运力供给 (ASK)、客座率 (PLF)、座公里收益 (RASK)、单座成本 (CASK) 与航线收益评级。",
        "type": "透视表",
        "period": "2025年Q1 决算周期",
        "comparison": "全网核心航线多维对标",
        "structure": {
            "xAxis": { "name": "航线与机型维度", "meaning": "航线代码、起降城市对、执飞机型、责任机长", "range": "全网核心航线" },
            "yAxis": { "name": "综合运营与收益指标", "meaning": "客票收入、客座率、RASK、CASK、综合票价、毛利率", "range": "全要素" },
            "series": [{ "name": "航线效能", "desc": "全要素咨询级排版" }]
        },
        "metrics": [
            { "name": "座公里收益 RASK", "definition": "单位可用座公里的营业收入，反映航线定价与客座率综合收益水平。", "formula": "客运总收入 ÷ 可用座公里 (ASK)", "rule": "RASK > CASK 时航线实现经营性盈利。" },
            { "name": "座公里成本 CASK", "definition": "单位可用座公里的综合运营成本（含航油、起降费、机组、折旧）。", "formula": "航线总运营成本 ÷ 可用座公里 (ASK)", "rule": "窄体机队基准 CASK 约 ¥0.28~0.35/座公里。" },
            { "name": "客座率 (PLF)", "definition": "实际旅客周转量与总运力提供的比值。", "formula": "RPK ÷ ASK × 100%", "rule": "S级黄金航线客座率通常高于 90.0%。" }
        ]
    },
    "table_airline_routes": {
        "title": "民航航线运营效能交互明细表",
        "overview": "支持按大区枢纽基地进行多维动态筛选与即时检索，实时监控重点航线达成进度与客座率波动。",
        "type": "明细表",
        "period": "2025年Q1 实时监测",
        "comparison": "区域基地横向对比",
        "structure": {
            "xAxis": { "name": "航线明细维度", "meaning": "航线编码、航线名称、所属基地、责任机长", "range": "按枢纽分类" },
            "yAxis": { "name": "收益与增长指标", "meaning": "客运规模、客座率、YoY、MoM、座公里收益", "range": "13 列交互明细" },
            "series": [{ "name": "航线明细", "desc": "支持即时搜索与下拉联动" }]
        },
        "metrics": [{
            "name": "航线达成进度",
            "definition": "当期实际承运收益占季度配额目标的百分比。",
            "formula": "实际客运收入 ÷ 目标配额 × 100%",
            "rule": "达成率 ≥ 95% 评为 S 级领跑航线。"
        }]
    },
    "t01": {
        "title": "民航旅客月度运输总周转量 RPK 走势",
        "overview": "反映民航航空集团全年各月份旅客实际运输总周转量 (RPK) 的平滑连续演进轨迹。",
        "type": "折线图",
        "period": "2024年1月 ~ 12月 (全年)",
        "comparison": "月度环比走势",
        "structure": {
            "xAxis": { "name": "月份", "meaning": "1月 ~ 12月自然月", "range": "12 个月" },
            "yAxis": { "name": "RPK 周转量 (亿客公里)", "meaning": "实际旅客周转量", "range": "100 ~ 240 亿客公里" },
            "series": [{ "name": "RPK 周转量", "desc": "主营收时序走线" }]
        },
        "metrics": [{
            "name": "收入客公里 (RPK)",
            "definition": "承运旅客数量与每位旅客飞行公里的乘积之和。",
            "formula": "∑ (承运旅客人数 × 飞行公里 km)",
            "rule": "直接反映航空公司的有效运输产出。"
        }]
    },
    "t02": {
        "title": "总可用座公里 ASK 历史投放与未来旺季预测",
        "overview": "对比历史实际可用座公里 (ASK) 运力投放规模，并预测未来春运与暑运旺季的情景走廊。",
        "type": "折线图",
        "period": "2024Q1 ~ 2025Q2(E)",
        "comparison": "历史实际 vs 未来预测 (E)",
        "structure": {
            "xAxis": { "name": "季度序列", "meaning": "历史决算期与未来预测期", "range": "6 个季度" },
            "yAxis": { "name": "可用座公里 ASK (亿座公里)", "meaning": "运力投放规模", "range": "0 ~ 12.0 亿座公里" },
            "series": [{ "name": "历史实际运力", "desc": "实线深蓝" }, { "name": "未来预测运力", "desc": "虚线绿色" }]
        },
        "metrics": [{
            "name": "预测走廊 (Forecast Corridor)",
            "definition": "基于历史机队交付与航线申请量构建的未来运力预测模型。",
            "formula": "现有运力 × (1 + 增机率) × 日利用率系数",
            "rule": "辅助机队规划与机组排班。"
        }]
    },
    "t03": {
        "title": "常旅客飞行航段与金银卡升级阶梯门槛",
        "overview": "呈现民航常旅客飞行有效定级航段对应会员等级（普卡、银卡、金卡、白金卡）的阶梯门槛规则。",
        "type": "阶梯折线图",
        "period": "会员定级年度",
        "comparison": "定级航段阶梯",
        "structure": {
            "xAxis": { "name": "定级航段区间", "meaning": "累计有效乘机航段数", "range": "0 ~ 100+ 航段" },
            "yAxis": { "name": "单航段积分兑换率 (元/航段)", "meaning": "里程积分回馈单价", "range": "¥0.18 ~ ¥0.45" },
            "series": [{ "name": "阶梯回馈率", "desc": "阶梯折线" }]
        },
        "metrics": [{
            "name": "定级航段 (Qualifying Segments)",
            "definition": "旅客购买符合累积标准的客票并实际成行所获得的会员升级航段数。",
            "formula": "标准舱位系数 × 飞行航段数",
            "rule": "白金卡需年满 90 定级航段或 16 万定级里程。"
        }]
    },
    "t04": {
        "title": "客运、货邮与航空辅营业务收入结构演变",
        "overview": "追踪头等商务舱客运、经济舱客运、腹舱货邮与航空增值辅营在历史时序中的结构占比演进。",
        "type": "面积图",
        "period": "2024Q1 ~ 2025Q1",
        "comparison": "多业务线堆叠构成",
        "structure": {
            "xAxis": { "name": "季度", "meaning": "连续 5 个季度", "range": "24Q1 ~ 25Q1" },
            "yAxis": { "name": "营收规模 (亿元)", "meaning": "各业务线创收金额", "range": "0 ~ 7.0 亿元" },
            "series": [{ "name": "航空辅营增值服务", "desc": "选座、逾重行李、机上Wi-Fi" }, { "name": "腹舱货邮运输", "desc": "航空货运与跨境物流" }, { "name": "主营客运机票收入", "desc": "两舱与经济舱客票" }]
        },
        "metrics": [{
            "name": "航空辅助收入 (Ancillary Revenue)",
            "definition": "非机票主营收入（如付费选座、预付费行李、机上餐食升舱、积分商城等）。",
            "formula": "∑ 非客票增值服务净结算额",
            "rule": "全球领先航司辅营占比可达 15%~25%。"
        }]
    },
    "t05": {
        "title": "机队机型优化升级前后座公里成本 CASK 对照",
        "overview": "评估机队老旧机型替换为新一代节能宽体机/窄体机（A350/A321neo）前后座公里成本的改善斜率。",
        "type": "斜率图",
        "period": "机队更新前后 (2024 vs 2025)",
        "comparison": "新旧机型能耗成本对比",
        "structure": {
            "xAxis": { "name": "对比时点", "meaning": "机队更新前 (2024) vs 机队更新后 (2025)", "range": "2 个节点" },
            "yAxis": { "name": "座公里成本 CASK (分/座公里)", "meaning": "单位可用座公里综合运营成本", "range": "20 ~ 70 分" },
            "series": [{ "name": "各机队板块斜率走线", "desc": "机型能耗下降幅度" }]
        },
        "metrics": [{
            "name": "座公里成本 (CASK)",
            "definition": "总营业支出除以可用座公里 (ASK)。",
            "formula": "总运营成本 ÷ 可用座公里 (ASK)",
            "rule": "新一代窄体客机 CASK 较上一代下降约 12%~15%。"
        }]
    },
    "t06": {
        "title": "季度客运总收入与客公里收益走势",
        "overview": "按季度追踪民航主营客运收入绝对规模 (亿元) 与客公里收益同比增速 (%) 的复合走势。",
        "type": "柱线复合图",
        "period": "2024Q1 ~ 2024Q4 (全年度)",
        "comparison": "绝对规模与相对增速双轴对比",
        "structure": {
            "xAxis": { "name": "统计季度", "meaning": "2024Q1 ~ 2024Q4", "range": "4 个季度" },
            "yAxis": { "name": "客运收入 (亿元) / 增速 (%)", "meaning": "左轴绝对金额，右轴同比百分比", "range": "左: 0~2.8亿，右: 0~40%" },
            "series": [{ "name": "客运总收入", "desc": "深海蓝柱体" }, { "name": "收益同比增速", "desc": "正向红色折线" }]
        },
        "metrics": [{
            "name": "客公里收益 (Yield per RPK)",
            "definition": "客运收入与收入客公里 (RPK) 的比值，反映平均实际票价水平。",
            "formula": "客运收入 ÷ 收入客公里 (RPK)",
            "rule": "用于衡量航司在不同航线上的实际变现能力。"
        }]
    },
    "c01": {
        "title": "全国各大基地枢纽机场营收贡献对比",
        "overview": "衡量全国各战略基地枢纽（北京大兴/首都、上海虹桥/浦东、广州白云、成都天府、深圳宝安）当期客货运收入规模差异。",
        "type": "柱状图",
        "period": "2025Q1 报告期",
        "comparison": "基地枢纽横向对标",
        "structure": {
            "xAxis": { "name": "基地枢纽", "meaning": "五大核心枢纽机场", "range": "5 个基地" },
            "yAxis": { "name": "营收规模 (亿元)", "meaning": "枢纽港客运结算总额", "range": "0 ~ 6.5 亿元" },
            "series": [{ "name": "基地营收", "desc": "标准垂直柱体" }]
        },
        "metrics": [{
            "name": "枢纽贡献率",
            "definition": "单个枢纽机场始发与经停航班创造的客票收入占集团总收入的比重。",
            "formula": "枢纽营收 ÷ 集团总营收 × 100%",
            "rule": "主基地营收贡献率通常超过 35.0%。"
        }]
    },
    "c02": {
        "title": "主流客运机型机队年度创收排行",
        "overview": "评估航空集团旗下 A350-900、B787-9、A321neo、B737-800 等主要客运机型的总营收贡献顺位。",
        "type": "条形图",
        "period": "2024 全年度",
        "comparison": "机型创收降序排列",
        "structure": {
            "xAxis": { "name": "营收规模 (亿元)", "meaning": "机型累计实现客运收入", "range": "0 ~ 6.0 亿元" },
            "yAxis": { "name": "执飞机型", "meaning": "宽体机与窄体机型", "range": "4 大主流机队" },
            "series": [{ "name": "机队营收", "desc": "横向条形" }]
        },
        "metrics": [{
            "name": "机型日均创收",
            "definition": "该机型全年在册客机创造的总收入除以在册架日数。",
            "formula": "机型年营收 ÷ (在册架数 × 365天)",
            "rule": "远程宽体客机日均创收通常高于窄体机 3~4 倍。"
        }]
    },
    "c03": {
        "title": "四大核心航线集群预算收入 vs 实际完成",
        "overview": "对比京津冀集群、长三角集群、粤港澳大湾区集群、成渝城市群四大战略航线集群的年度预算配额与实际完成情况。",
        "type": "柱状图",
        "period": "2025 全年度",
        "comparison": "预算与实际成对对比",
        "structure": {
            "xAxis": { "name": "航线集群", "meaning": "四大国家级战略城市群", "range": "4 个集群" },
            "yAxis": { "name": "营收规模 (亿元)", "meaning": "预算目标与实际达成金额", "range": "0 ~ 6.5 亿元" },
            "series": [{ "name": "预算目标", "desc": "浅蓝浅色柱" }, { "name": "实际完成", "desc": "深海蓝主柱" }]
        },
        "metrics": [{
            "name": "预算达成率",
            "definition": "实际客运收入占年度下达预算指标的比重。",
            "formula": "实际营收 ÷ 预算目标 × 100%",
            "rule": "≥ 100% 为超额完成，< 90% 需启动收益管控。"
        }]
    },
    "c04": {
        "title": "各机队板块座公里收益相对行业基准偏离",
        "overview": "以民航全行业统一座公里基准收益率为参考线，量化宽体机、窄体机、支线机及全货机板块的超额或滞后幅度。",
        "type": "条形图",
        "period": "2025Q1 报告期",
        "comparison": "双向偏离（红正绿负）",
        "structure": {
            "xAxis": { "name": "偏离基准收益率 (%)", "meaning": "相对行业基准收益率的百分比差额", "range": "-14% ~ +20%" },
            "yAxis": { "name": "机队板块", "meaning": "不同运营机队类型", "range": "4 大机队类别" },
            "series": [{ "name": "偏离幅度", "desc": "正红负绿条形" }]
        },
        "metrics": [{
            "name": "基准偏离度 (Alpha Yield)",
            "definition": "机队实际座公里收益率减去民航行业同期平均基准收益率。",
            "formula": "实际 RASK 收益率 - 行业基准收益率",
            "rule": "用于评估航司相对于行业大盘的超额竞争优势。"
        }]
    },
    "c05": {
        "title": "航司各乘机服务环节 NPS 满意度排行",
        "overview": "对标呈现行李直挂、机上餐食、贵宾厅休息室、快速安检与客舱 Wi-Fi 各环节的旅客净推荐值与满意度评分。",
        "type": "柱状图",
        "period": "2025Q1 旅客调研快照",
        "comparison": "服务触点满意度降序",
        "structure": {
            "xAxis": { "name": "服务触点", "meaning": "旅客全流程乘机环节", "range": "5 大核心触点" },
            "yAxis": { "name": "满意度评分 (分)", "meaning": "百分制旅客满意度得分", "range": "70 ~ 100 分" },
            "series": [{ "name": "满意度评分", "desc": "细柱散点" }]
        },
        "metrics": [{
            "name": "净推荐值 (NPS)",
            "definition": "推荐者比例与贬损者比例的差值，衡量旅客对航司服务的忠诚度。",
            "formula": "(推荐者人数 - 贬损者人数) ÷ 调研总人数 × 100%",
            "rule": "民航服务 NPS 达到 +70 以上属于行业标杆水准。"
        }]
    },
    "c06": {
        "title": "各大基地重点商务航线客座率跃升跨度",
        "overview": "对比京沪、沪深、京广、成渝等核心商务航线在春运淡季基期与商务旺季当期的客座率跃升幅度。",
        "type": "散点图",
        "period": "淡季基期 (2024) vs 旺季当期 (2025)",
        "comparison": "跨度跃升分析",
        "structure": {
            "xAxis": { "name": "航线客座率 (%)", "meaning": "承运旅客占总运力比重", "range": "0 ~ 50%" },
            "yAxis": { "name": "基地大区", "meaning": "四大枢纽基地", "range": "4 个大区" },
            "series": [{ "name": "淡季基期", "desc": "浅灰散点" }, { "name": "旺季当期", "desc": "深蓝散点与连接线" }]
        },
        "metrics": [{
            "name": "客座率跃升幅度",
            "definition": "当期客座率减去基期客座率的百分点差值。",
            "formula": "当期 PLF - 基期 PLF",
            "rule": "衡量航线收益管理与动态定价调节能力。"
        }]
    },
    "c07": {
        "title": "核心航线集群上年度同期 vs 当期运力投放对比",
        "overview": "直观对比四大核心航线集群在上一年度同期基期与当期实际完成的运力投放与营收规模。",
        "type": "柱状图",
        "period": "2024同期 vs 2025当期",
        "comparison": "同期对比 (YoY)",
        "structure": {
            "xAxis": { "name": "航线集群", "meaning": "四大核心航线板块", "range": "4 个集群" },
            "yAxis": { "name": "营收规模 (亿元)", "meaning": "客运收入绝对金额", "range": "0 ~ 6.0 亿元" },
            "series": [{ "name": "2024同期", "desc": "质感灰柱" }, { "name": "2025当期", "desc": "深海蓝主柱" }]
        },
        "metrics": [{
            "name": "同期净增量",
            "definition": "当期客运收入与上年同期收入的绝对差额。",
            "formula": "当期营收 - 同期营收",
            "rule": "正增量反映该航线集群处于扩张增长通道。"
        }]
    },
    "c08": {
        "title": "国内航线 vs 国际及地区航线主要基地客运规模对比",
        "overview": "按大区基地维度对称呈现国内航线网络与国际远程航线网络的客运收入与运力规模分布。",
        "type": "条形图",
        "period": "2024 全年度",
        "comparison": "左右对称横向条形",
        "structure": {
            "xAxis": { "name": "国内营收 (左) vs 国际营收 (右)", "meaning": "单位: 亿元", "range": "左右各 0 ~ 6.5 亿元" },
            "yAxis": { "name": "枢纽基地", "meaning": "四大战略枢纽", "range": "4 个基地" },
            "series": [{ "name": "国内航线", "desc": "左侧深海蓝条形" }, { "name": "国际航线", "desc": "右侧质感灰条形" }]
        },
        "metrics": [{
            "name": "国际航线收入占比",
            "definition": "国际及地区航线收入占基地总客运收入的比重。",
            "formula": "国际营收 ÷ (国内营收 + 国际营收) × 100%",
            "rule": "国际枢纽港（如上海浦东、北京首都）国际占比通常高于 40%。"
        }]
    },
    "k01": {
        "title": "旅客舱位等级与出行客群构成分布",
        "overview": "反映公商务出行、休闲度假、探亲求学与团队政务等不同客群的构成占比及总承运旅客人次。",
        "type": "环形图",
        "period": "2025Q1 决算周期",
        "comparison": "整体构成占比 (100%)",
        "structure": {
            "xAxis": { "name": "环孔中心", "meaning": "总承运旅客数 (5,420 万人次)", "range": "大字号居中" },
            "yAxis": { "name": "客群分类", "meaning": "商务、度假、探亲、政务", "range": "4 大客群" },
            "series": [{ "name": "客群比例", "desc": "多色调环形切片" }]
        },
        "metrics": [{
            "name": "两舱旅客收益贡献率",
            "definition": "头等舱与公务舱旅客客票收入占全航线总收入的比重。",
            "formula": "两舱收入 ÷ 总客运收入 × 100%",
            "rule": "两舱以 10%~15% 的座位数贡献 35%~45% 的利润。"
        }]
    },
    "k02": {
        "title": "各大核心基地直销 vs OTA 渠道销售配比",
        "overview": "横向对比各大基地枢纽在航司官方 App 直销、大客户企业直签与 OTA 在线旅行社渠道的销售占比结构。",
        "type": "条形图",
        "period": "2025Q1 报告期",
        "comparison": "100% 堆叠条形",
        "structure": {
            "xAxis": { "name": "销售占比 (%)", "meaning": "渠道出票金额占总销售额百分比", "range": "0% ~ 100%" },
            "yAxis": { "name": "枢纽基地", "meaning": "四大战略枢纽", "range": "4 个基地" },
            "series": [{ "name": "航司官网/App直销", "desc": "高毛利直销" }, { "name": "大客户企业直签", "desc": "企业商旅协议" }, { "name": "OTA 代理平台", "desc": "携程/飞猪分销" }]
        },
        "metrics": [{
            "name": "直销比例 (Direct Sales Ratio)",
            "definition": "通过自有渠道（官网、App、直营柜台、小程序）销售的机票金额占比。",
            "formula": "自有直销额 ÷ 总客票销售额 × 100%",
            "rule": "民航高质量发展战略目标要求直销比达到 50%~60% 以上。"
        }]
    },
    "k03": {
        "title": "民航机队在册客机资产估值分布",
        "overview": "通过几何矩形面积直观映射 A350、B787、A320/A321 及国产 C919 各机型机队的资产估值体量与机队规模。",
        "type": "矩形树图",
        "period": "2025Q1 资产决算期",
        "comparison": "机队资产估值占比",
        "structure": {
            "xAxis": { "name": "矩形空间", "meaning": "按资产体量递归切分", "range": "全机队" },
            "yAxis": { "name": "资产估值 (亿元)", "meaning": "在册飞机账面净值与重置评估值", "range": "¥2.2 亿 ~ ¥12.5 亿" },
            "series": [{ "name": "机队资产", "desc": "无间隙深色块" }]
        },
        "metrics": [{
            "name": "机队账面净值",
            "definition": "在册飞机原值扣除累计折旧及减值准备后的账面余额。",
            "formula": "机队原值 - 累计折旧",
            "rule": "民航大型客机通常采用 15~20 年直线折旧法。"
        }]
    },
    "k04": {
        "title": "航班延误与服务投诉主因帕累托 80/20 诊断",
        "overview": "依延误与投诉发生频数降序排列并绘制累计百分比曲线，精准识别引发 80% 延误的关键诱因（天气、空域流量、前序晚到等）。",
        "type": "柱线复合图",
        "period": "2025Q1 运行监控",
        "comparison": "帕累托二八定律分析",
        "structure": {
            "xAxis": { "name": "延误诱因", "meaning": "天气流控、前序晚到、跑道保障、机械故障、其他", "range": "5 大诱因" },
            "yAxis": { "name": "发生频次 (架次) / 累计占比 (%)", "meaning": "左轴频数，右轴累计百分比", "range": "左: 0~500，右: 0~100%" },
            "series": [{ "name": "延误频数", "desc": "深海蓝柱体" }, { "name": "累计占比", "desc": "正向红色折线" }]
        },
        "metrics": [{
            "name": "航班正常率 (OTP, On-Time Performance)",
            "definition": "正常出港/到港航班架次占实际飞行总架次的比重。",
            "formula": "正常航班架次 ÷ 实际执行总架次 × 100%",
            "rule": "民航五星航司航班正常率考核目标通常不低于 90.0%。"
        }]
    },
    "k05": {
        "title": "国内航线 vs 国际及地区航线收入占比",
        "overview": "展示国内航线与国际及地区航线在集团客运收入大盘中的份额结构占比（国内 72% vs 国际 28%）。",
        "type": "饼图",
        "period": "2025Q1 决算快照",
        "comparison": "整体二元划分",
        "structure": {
            "xAxis": { "name": "饼图中心", "meaning": "双色对立切片", "range": "100% 构成" },
            "yAxis": { "name": "收入占比 (%)", "meaning": "国内 72% vs 国际 28%", "range": "百分比" },
            "series": [{ "name": "市场分布", "desc": "极简双色饼图" }]
        },
        "metrics": [{
            "name": "国际航线周转量占比",
            "definition": "国际航线 RPK 占全网总 RPK 的比重。",
            "formula": "国际 RPK ÷ 全网总 RPK × 100%",
            "rule": "反映航空公司的国际化经营广度与全球网络通达性。"
        }]
    },
    "k06": {
        "title": "航线网络国内外与区域层级结构",
        "overview": "呈现国内干线/支线与国际远程/周边区域航线的同心多层级客运规模构成。",
        "type": "旭日图",
        "period": "2025Q1 航网结构",
        "comparison": "多层级环形穿透",
        "structure": {
            "xAxis": { "name": "层级同心圆", "meaning": "内环: 国内/国际，外环: 细分区域航线", "range": "两层级" },
            "yAxis": { "name": "客运规模 (亿元)", "meaning": "各层级对应客运结算金额", "range": "多层穿透" },
            "series": [{ "name": "航网层级", "desc": "同心旭日图" }]
        },
        "metrics": [{
            "name": "航线网络通达度",
            "definition": "航司通航城市点对点连接数量及枢纽中转航线覆盖度。",
            "formula": "已开通定期航线总数 (条)",
            "rule": "干支结合、枢纽辐射型网络具有最高的网络外部性溢价。"
        }]
    },
    "d01": {
        "title": "旅客平均机票购票金额频数分布",
        "overview": "展示不同机票价格区间（300-600特价、600-1200标准、1200-2500全价、2500+公务头等）的购票出票笔数频数密度。",
        "type": "直方图",
        "period": "2025Q1 订票分析",
        "comparison": "价格区间连续分布",
        "structure": {
            "xAxis": { "name": "客单金额区间", "meaning": "机票支付价格分档", "range": "5 个价格区间" },
            "yAxis": { "name": "出票笔数 (万张)", "meaning": "该价格区间的出票量", "range": "0 ~ 500 万张" },
            "series": [{ "name": "出票笔数", "desc": "密集柱状分布" }]
        },
        "metrics": [{
            "name": "平均客单票价 (Average Ticket Fare)",
            "definition": "客运总收入除以承运旅客总人数。",
            "formula": "客运总收入 ÷ 承运旅客人数",
            "rule": "用于评估旅客支付意愿与航司动态收益管理定价水平。"
        }]
    },
    "d02": {
        "title": "各大基地航线平均单座票价收益分布特征",
        "overview": "通过箱线图呈现华东、华南、华北、西南各大基地航线单座票价收益的极值、四分位数与中位数分布离散度。",
        "type": "箱线图",
        "period": "2025Q1 航线收益",
        "comparison": "五数概括分布对比",
        "structure": {
            "xAxis": { "name": "枢纽基地", "meaning": "四大核心运营基地", "range": "4 个大区" },
            "yAxis": { "name": "单座收益 (元)", "meaning": "各航线平均单座票价收益", "range": "¥100 ~ ¥900" },
            "series": [{ "name": "票价离散度", "desc": "箱体与须线" }]
        },
        "metrics": [{
            "name": "中位座公里收益",
            "definition": "该基地所有航线 RASK 排序后处于 50% 分位点的收益水平。",
            "formula": "Median(航线 RASK 序列)",
            "rule": "相比均值更能消除极高/极低航线的统计偏差。"
        }]
    },
    "d03": {
        "title": "航线综合客座率离散度概率分布",
        "overview": "拟合全航线网络实际综合客座率 (PLF) 的连续正态分布曲线与偏度特征。",
        "type": "面积图",
        "period": "2025Q1 航班执行",
        "comparison": "概率密度拟合曲线",
        "structure": {
            "xAxis": { "name": "综合客座率 (%)", "meaning": "客座率分档 (-10% ~ +40% 相对基准)", "range": "连续区间" },
            "yAxis": { "name": "概率密度", "meaning": "航班落在该客座率区间的概率密度", "range": "0 ~ 0.12" },
            "series": [{ "name": "正态分布曲线", "desc": "平滑面积走线" }]
        },
        "metrics": [{
            "name": "客座率标准差",
            "definition": "各航线客座率相对于全网平均客座率的离散离差程度。",
            "formula": "SQRT(∑ (PLF_i - 平均PLF)^2 ÷ N)",
            "rule": "标准差越小说明航线网络运力匹配与收益管控越均衡。"
        }]
    },
    "d04": {
        "title": "全周 24 小时航班起降与枢纽港吞吐高峰时刻",
        "overview": "定位一周内（周一至周日）各时段（00:00~24:00）枢纽机场航班波起降频次与停机位负荷密度峰值。",
        "type": "热力图",
        "period": "全周 7×24 小时运行时刻",
        "comparison": "二维时空负荷热力",
        "structure": {
            "xAxis": { "name": "时刻 (小时)", "meaning": "00:00 ~ 21:00 (每3小时分段)", "range": "8 个时段" },
            "yAxis": { "name": "星期", "meaning": "周一 ~ 周日", "range": "7 天" },
            "series": [{ "name": "起降并发指数", "desc": "深浅色块矩阵" }]
        },
        "metrics": [{
            "name": "枢纽航班波吞吐指数 (Hub Wave Index)",
            "definition": "单位小时内进出港航班衔接量与中转旅客规模。",
            "formula": "出港架次 + 进港架次 + 快速中转比率",
            "rule": "高峰时段需强化地面保障、机坪滑行及安检通道资源调度。"
        }]
    },
    "r01": {
        "title": "航线网络战略四象限增长与收益矩阵",
        "overview": "依据客座率增速 (X轴) 与座公里利润率 (Y轴) 划分商务黄金干线、旅游度假热线、培育期支线与收缩航线象限归属。",
        "type": "散点图",
        "period": "2025Q1 航网评估",
        "comparison": "BCG 战略四象限",
        "structure": {
            "xAxis": { "name": "客座率增速 (%)", "meaning": "航线旅客周转增速", "range": "-5% ~ 45%" },
            "yAxis": { "name": "座公里利润率 (%)", "meaning": "航线边际利润率", "range": "0% ~ 80%" },
            "series": [{ "name": "战略航线", "desc": "带标签散点与虚线十字基准" }]
        },
        "metrics": [{
            "name": "航线边际贡献率",
            "definition": "航线客货运收入扣除直接变动成本（航油、起降、旅客餐食等）后的结余比率。",
            "formula": "(航线收入 - 直接变动成本) ÷ 航线收入 × 100%",
            "rule": "用于决定航线增班、减频或机型置换决策。"
        }]
    },
    "r02": {
        "title": "常旅客获客成本 CAC 与生命周期价值 LTV 分布",
        "overview": "量化白金卡高端商旅、金卡高频商务、银卡普通商务与普卡大众旅客的获客成本、生命周期价值与规模关系。",
        "type": "气泡图",
        "period": "会员年度画像",
        "comparison": "三维气泡分布",
        "structure": {
            "xAxis": { "name": "获客成本 CAC (万元)", "meaning": "获取并激活单名会员的营销成本", "range": "¥0 ~ ¥10 万" },
            "yAxis": { "name": "生命周期价值 LTV (万元)", "meaning": "会员全生命周期贡献机票及辅营毛利", "range": "¥0 ~ ¥40 万" },
            "series": [{ "name": "会员客群气泡", "desc": "气泡大小代表该客群会员总人数" }]
        },
        "metrics": [{
            "name": "LTV / CAC 倍数",
            "definition": "旅客全生命周期价值与获客成本的比值。",
            "formula": "生命周期价值 LTV ÷ 获客成本 CAC",
            "rule": "商旅客群 LTV/CAC 通常要求达到 4.0x 以上。"
        }]
    },
    "r03": {
        "title": "民航运营核心要素相关性系数矩阵",
        "overview": "量化客座率、票价指数、飞机日利用率、航班准点率与航线利润率之间的双向皮尔逊相关性强度。",
        "type": "热力图",
        "period": "2024 全年运行大数据",
        "comparison": "5×5 对称相关性矩阵",
        "structure": {
            "xAxis": { "name": "运营要素 A", "meaning": "客座率、票价指数、日利用率、准点率、利润率", "range": "5 大维度" },
            "yAxis": { "name": "运营要素 B", "meaning": "同上维度", "range": "5 大维度" },
            "series": [{ "name": "皮尔逊相关系数", "desc": "数值热力色块 (0.3 ~ 1.0)" }]
        },
        "metrics": [{
            "name": "皮尔逊相关系数 (Pearson r)",
            "definition": "衡量两个民航经营变量之间线性相关程度的统计指标。",
            "formula": "Cov(X, Y) ÷ (σX × σY)",
            "rule": "r > 0.8 表示强正相关（如准点率与常旅客复购率）。"
        }]
    },
    "r04": {
        "title": "全国核心枢纽机场航线网络拓扑关联图",
        "overview": "呈现北京、上海、广州等主枢纽机场与成都、深圳、西安等区域节点的航线协同流向与运力关联强度。",
        "type": "关系图",
        "period": "当前航季网络拓扑",
        "comparison": "网络节点与流向连线",
        "structure": {
            "xAxis": { "name": "拓扑平面", "meaning": "枢纽节点与航线连线", "range": "全国航网" },
            "yAxis": { "name": "节点权重", "meaning": "枢纽吞吐量与航线周转规模", "range": "节点大小" },
            "series": [{ "name": "航网拓扑", "desc": "力导向网络图" }]
        },
        "metrics": [{
            "name": "枢纽中转衔接率",
            "definition": "经由枢纽机场进行跨区域中转的旅客占该枢纽总旅客吞吐量的比重。",
            "formula": "中转旅客人数 ÷ 总吞吐量 × 100%",
            "rule": "国际一流枢纽机场中转率通常在 25%~40% 之间。"
        }]
    },
    "r05": {
        "title": "民航航空集团多维综合运营能力对标透视",
        "overview": "对标民航五星级航司基准，综合评估客座率 PLF、座公里收益 RASK、航班准点率 OTP、飞机日利用率与服务 NPS。",
        "type": "雷达图",
        "period": "2025Q1 综合评估",
        "comparison": "集团实际 vs 行业头部五星基准",
        "structure": {
            "xAxis": { "name": "极坐标轴", "meaning": "5 大综合运营维度", "range": "0 ~ 100 分" },
            "yAxis": { "name": "评估得分", "meaning": "各维度量化综合评分", "range": "0 ~ 100" },
            "series": [{ "name": "集团实际表现", "desc": "深海蓝实线填充" }, { "name": "行业五星基准", "desc": "虚线灰色对标" }]
        },
        "metrics": [{
            "name": "飞机日利用率 (Aircraft Daily Utilization)",
            "definition": "在册飞机每日实际飞行小时数（轮挡小时 Block Hours）。",
            "formula": "机队总飞行小时数 ÷ (在册机队架数 × 天数)",
            "rule": "窄体客机日利用率基准线建议维持在 9.5~10.5 小时/天。"
        }]
    },
    "f01": {
        "title": "航司官方渠道机票预订全链路流转漏斗",
        "overview": "监控旅客自航线航班检索、舱位选择、旅客信息录入、选座辅营增购至最终出票支付的全流程留存与衰减。",
        "type": "漏斗图",
        "period": "2025Q1 线上预订全量数据",
        "comparison": "各预订阶段流转衰减",
        "structure": {
            "xAxis": { "name": "漏斗宽度", "meaning": "进入该预订环节的独立会话量", "range": "5,000 ➔ 600 条" },
            "yAxis": { "name": "预订阶段", "meaning": "检索 ➔ 舱位 ➔ 信息 ➔ 支付", "range": "4 大阶段" },
            "series": [{ "name": "预订留存", "desc": "阶梯递减漏斗" }]
        },
        "metrics": [{
            "name": "出票转化率 (Booking Conversion Rate)",
            "definition": "最终完成支付出票的订单量占初始航班搜索查询量的百分比。",
            "formula": "最终出票订单数 ÷ 航班搜索会话数 × 100%",
            "rule": "航司直销 App 端到端转化率通常在 8%~15% 之间。"
        }]
    },
    "f02": {
        "title": "客货运主营收入向成本与航油分流资金流向",
        "overview": "清晰呈现客货运主营收入如何扣除航油成本、机场起降费、机组薪酬及飞机折旧维修后转化为综合毛利与净利润。",
        "type": "桑基图",
        "period": "2024 全年度决算",
        "comparison": "资金流向节点守恒",
        "structure": {
            "xAxis": { "name": "资金流向链路", "meaning": "总营收 (13.0亿) ➔ 航油/起降/折旧 ➔ 毛利 (8.0亿) ➔ 净利润 (2.5亿)", "range": "全链路" },
            "yAxis": { "name": "资金体量 (亿元)", "meaning": "各流向节点金额", "range": "节点分流" },
            "series": [{ "name": "资金价值流", "desc": "平滑流向带" }]
        },
        "metrics": [{
            "name": "航油成本占比 (Fuel Cost Ratio)",
            "definition": "航油消耗支出占航空公司总运营成本的比重。",
            "formula": "航油总支出 ÷ 总运营支出 × 100%",
            "rule": "航油为航司最大单一运营成本，通常占比 25%~35%。"
        }]
    },
    "f03": {
        "title": "新增常旅客会员批次 M0~M3 乘机复购留存",
        "overview": "追踪各季度新注册常旅客会员批次在入会后前 3 个月的乘机复购留存率与里程积分活跃度演变。",
        "type": "热力图",
        "period": "2024Q1 ~ 2024Q4 会员队列",
        "comparison": "队列时序衰减",
        "structure": {
            "xAxis": { "name": "入会后周期", "meaning": "M0 (首次乘机) ➔ M1 留存 ➔ M2 留存 ➔ M3 留存", "range": "4 个月" },
            "yAxis": { "name": "入会季度批次", "meaning": "24Q1 批次 ~ 24Q4 批次", "range": "4 个批次" },
            "series": [{ "name": "乘机复购留存率 (%)", "desc": "色彩渐变热力矩阵" }]
        },
        "metrics": [{
            "name": "常旅客 M3 复购率",
            "definition": "新入会会员在入会第 3 个月内再次购买客票乘机的比例。",
            "formula": "第3月再次成行会员数 ÷ 该批次新会员总数 × 100%",
            "rule": "优质商旅会员 M3 复购率通常稳定在 75%~85% 以上。"
        }]
    },
    "fn01": {
        "title": "主营客运边际利润形成与航油扣减归因",
        "overview": "穿透客票基础毛利至当期航线边际利润 EBITDA 的核心增益与扣减归因链路（票价上浮、载运量增长 vs 航油上涨、起降费扣减）。",
        "type": "瀑布图",
        "period": "2025Q1 财务归因",
        "comparison": "增减变动桥接归因",
        "structure": {
            "xAxis": { "name": "财务归因要素", "meaning": "基期毛利、综合票价拉动、客运量增长、航油成本上涨、当期EBITDA", "range": "5 大归因项" },
            "yAxis": { "name": "金额 (亿元)", "meaning": "各项对利润的贡献净额", "range": "0 ~ 1.8 亿元" },
            "series": [{ "name": "增减归因", "desc": "悬浮柱状瀑布" }]
        },
        "metrics": [{
            "name": "航线边际 EBITDA",
            "definition": "航线客运收入扣除除折旧与摊销外的直接变动成本与分摊运行费用。",
            "formula": "主营收入 - 航油 - 起降 - 机组 - 运行费用",
            "rule": "衡量航线实际造血能力的关键指标。"
        }]
    },
    "fn02": {
        "title": "季度客运总收入与运营总成本盈亏演变",
        "overview": "反映营业收入与运营总成本（航油、机场起降、飞机折旧、机组薪酬）的收支走势及盈亏平衡剪刀差拐点。",
        "type": "折线图",
        "period": "2024Q1 ~ 2024Q4",
        "comparison": "收入线 vs 成本线双线对比",
        "structure": {
            "xAxis": { "name": "季度", "meaning": "2024Q1 ~ 2024Q4", "range": "4 个季度" },
            "yAxis": { "name": "收支金额 (亿元)", "meaning": "季度营业收入与总运营成本", "range": "0 ~ 2.8 亿元" },
            "series": [{ "name": "客运总收入", "desc": "实线深蓝 (¥2.3亿 当期)" }, { "name": "运营总成本", "desc": "虚线灰色 (¥1.7亿 当期)" }]
        },
        "metrics": [{
            "name": "盈亏平衡客座率 (Break-even Load Factor)",
            "definition": "客运收入刚好覆盖总运营成本时的客座率阈值。",
            "formula": "总运营成本 ÷ (ASK × 客公里收益 Yield)",
            "rule": "当实际客座率高于盈亏平衡客座率时航线产生净利润。"
        }]
    },
    "fn03": {
        "title": "民航经营关键变量敏感性分析",
        "overview": "测试平均客单票价、综合客座率、航油价格与美元汇率波动对民航集团季度净利润的影响弹性。",
        "type": "条形图",
        "period": "2025Q1 敏感性测算 (±10% 变量波动)",
        "comparison": "负向侵蚀 vs 正向增益",
        "structure": {
            "xAxis": { "name": "净利变动 (百万)", "meaning": "对净利润的影响绝对金额", "range": "-60M ~ +60M" },
            "yAxis": { "name": "经营变量", "meaning": "客单票价、客座率、航油采购价、美元汇率", "range": "4 大变量" },
            "series": [{ "name": "负向侵蚀", "desc": "绿色条形" }, { "name": "正向增益", "desc": "红色条形" }]
        },
        "metrics": [{
            "name": "航油价格敏感系数",
            "definition": "国际航空煤油价格每波动 10% 对航司年度净利润的影响金额。",
            "formula": "Δ净利润 ÷ (Δ航油价格 ÷ 基准油价)",
            "rule": "民航大型航司油价每上涨 10% 净利侵蚀约数亿元。"
        }]
    },
    "fn04": {
        "title": "各大基地主营航线收入归一增长指数走势",
        "overview": "消除各基地规模体量差异，以基期为 100 对比华东、华南、北方与西南基地主营航线收入的成长动能。",
        "type": "折线图",
        "period": "2024Q1 ~ 2025Q1 (基期 24Q1=100)",
        "comparison": "基准归一指数对比",
        "structure": {
            "xAxis": { "name": "季度", "meaning": "连续 5 个季度", "range": "5 个节点" },
            "yAxis": { "name": "增长指数 (Base=100)", "meaning": "以基期为 100 的相对增长倍数", "range": "90 ~ 240" },
            "series": [{ "name": "华东基地 (虹桥/浦东)", "desc": "深海蓝领跑走线" }, { "name": "华南基地 (白云/宝安)", "desc": "次主走线" }, { "name": "北方基地 (大兴/首都)", "desc": "稳健走线" }, { "name": "西南基地 (天府/双流)", "desc": "虚线走势" }]
        },
        "metrics": [{
            "name": "定基增长指数 (Base-100 Index)",
            "definition": "报告期客运收入除以基期客运收入乘以 100。",
            "formula": "当期营收 ÷ 基期营收 × 100",
            "rule": "用于横向评估不同体量基地的内生增长活力。"
        }]
    },
    "m01": {
        "title": "民航年度战略关键绩效考核达成情况",
        "overview": "对比航班正常率、综合客座率、飞机日利用率与直销比例的实际考核完成值与目标基准线差距。",
        "type": "子弹图",
        "period": "2025 全年度考核期",
        "comparison": "实际柱 vs 目标刻度线",
        "structure": {
            "xAxis": { "name": "综合达成率 (%)", "meaning": "各项绩效指标完成百分比", "range": "0% ~ 130%" },
            "yAxis": { "name": "考核指标", "meaning": "客运总收入、客座率、航班正常率、直销比例", "range": "4 项核心指标" },
            "series": [{ "name": "实际完成", "desc": "深海蓝条形" }, { "name": "基准目标", "desc": "100% 垂直黑线" }]
        },
        "metrics": [{
            "name": "综合绩效达成指数",
            "definition": "各项民航运营 KPI 实际达成率加权综合得分。",
            "formula": "∑ (指标达成率 × 指标权重)",
            "rule": "总分 ≥ 100% 达标并享有绩效激励。"
        }]
    },
    "m02": {
        "title": "春运及暑运民航客运量预测扩散走廊",
        "overview": "基于历史机队运力与客票预售基线，展示未来春运与暑运客运量在悲观、基准与乐观三档情景下的预测扩散区间。",
        "type": "面积图",
        "period": "2024Q1 ~ 2025Q2(E)",
        "comparison": "三档情景扩散走廊",
        "structure": {
            "xAxis": { "name": "季度", "meaning": "历史实测与未来预测季度", "range": "6 个季度" },
            "yAxis": { "name": "客运收入 (亿元)", "meaning": "不同情景下的创收区间", "range": "0 ~ 14.0 亿元" },
            "series": [{ "name": "历史实测", "desc": "实线深蓝" }, { "name": "乐观情景 (旺季超预期)", "desc": "虚线红色" }, { "name": "基准预测 (平稳发展)", "desc": "虚线深蓝" }, { "name": "悲观情景 (油价高企/需求收缩)", "desc": "虚线绿色" }]
        },
        "metrics": [{
            "name": "情景预测扩散度 (Forecast Variance)",
            "definition": "乐观情景与悲观情景预测值之间的差额区间。",
            "formula": "乐观预测值 - 悲观预测值",
            "rule": "为航司机队租赁调配与临时包机提供风险决策缓冲。"
        }]
    },
    "m03": {
        "title": "各机场地面服务与延误保障费用超支红线监控",
        "overview": "监控各机场配餐、地面摆渡、旅客延误改签安置与除冰保障费用的超支率，并标识 5.0% 预警红线边界。",
        "type": "柱状图",
        "period": "2025Q1 成本管控",
        "comparison": "超支率 vs 5% 红线阈值",
        "structure": {
            "xAxis": { "name": "地面保障节点", "meaning": "航食配餐、地面摆渡、延误赔偿、除冰保障、机坪租赁", "range": "5 个节点" },
            "yAxis": { "name": "超支率 (%)", "meaning": "实际支出超出预算百分比", "range": "0% ~ 10%" },
            "series": [{ "name": "超支率", "desc": "红绿状态柱与 5% 虚线" }]
        },
        "metrics": [{
            "name": "延误保障费用超支率",
            "definition": "因不正常航班产生的旅客食宿安置与改签支出超出预算的比率。",
            "formula": "(实际延误支出 - 预算额) ÷ 预算额 × 100%",
            "rule": "超支率 > 5.0% 触发成本控制黄牌预警。"
        }]
    },
    "m04": {
        "title": "民航年度主营营收预算目标综合达成率",
        "overview": "大字直显机队与客货运全网年度预算目标的综合推进完成比例，辅助高管直观掌握经营节奏。",
        "type": "仪表盘",
        "period": "2025 全年度考核期",
        "comparison": "当前完成率 vs 100% 年度目标",
        "structure": {
            "xAxis": { "name": "刻度区间", "meaning": "0% ~ 100%", "range": "0% ~ 100%" },
            "yAxis": { "name": "达成率", "meaning": "84.5%", "range": "0% ~ 100%" },
            "series": [{ "name": "半环进度", "desc": "深海蓝圆弧" }]
        },
        "metrics": [{
            "name": "年度预算达成率",
            "definition": "考核期内累计客货运主营收入占年度总预算目标的比例。",
            "formula": "累计主营收入 ÷ 年度预算目标 × 100%",
            "rule": "正常推进进度应保持在时间进度 ±3% 以内。"
        }]
    }
}

EXPLANATIONS_JSON_STRING = json.dumps(CHART_EXPLANATIONS_DATA, ensure_ascii=False)

CHART_EXPLANATIONS = CHART_EXPLANATIONS_DATA
