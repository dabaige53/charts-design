import os
import json

# Master Airline Routes Table Dataset (14 full columns, 36 comprehensive realistic routes)
TABLE_COLUMNS = [
    {"key": "code", "title": "航线代码", "align": "left", "sortable": True, "visible": True},
    {"key": "name", "title": "起降城市对", "align": "left", "sortable": True, "visible": True},
    {"key": "hub", "title": "所属基地", "align": "left", "sortable": True, "visible": True},
    {"key": "fleet", "title": "执飞机型", "align": "left", "sortable": True, "visible": True},
    {"key": "routeType", "title": "航网类型", "align": "left", "sortable": True, "visible": True},
    {"key": "captain", "title": "责任机长", "align": "left", "sortable": True, "visible": True},
    {"key": "flights", "title": "周执行班次", "align": "right", "sortable": True, "visible": True},
    {"key": "revenue", "title": "当期客运收入", "align": "right", "sortable": True, "visible": True},
    {"key": "yoy", "title": "收入YoY", "align": "right", "sortable": True, "visible": True},
    {"key": "plf", "title": "综合客座率", "align": "right", "sortable": True, "visible": True},
    {"key": "rask", "title": "座公里RASK", "align": "right", "sortable": True, "visible": True},
    {"key": "cask", "title": "座公里CASK", "align": "right", "sortable": True, "visible": True},
    {"key": "otp", "title": "航班正常率", "align": "right", "sortable": True, "visible": True},
    {"key": "rating", "title": "航线评级", "align": "center", "sortable": True, "visible": True}
]

TABLE_ROWS = [
    # --- 华东基地 (East China Hub - SHA/PVG) ---
    {
        "code": "MU5101/02", "name": "京沪黄金快线 (SHA-PEK)", "hub": "华东基地", "fleet": "A350-900 (宽体)", "routeType": "国内干线 (Trunk)", "captain": "张建国 (教员)",
        "flights": "56 班/周", "revenue": "¥4.90 亿", "rawRevenue": 4.90, "yoy": "+18.5%", "rawYoy": 18.5, "plf": "92.4%", "rawPlf": 92.4,
        "rask": "¥0.5820", "rawRask": 0.5820, "cask": "¥0.3810", "rawCask": 0.3810, "otp": "94.2%", "rawOtp": 94.2, "rating": "S 级", "pax": 38.5
    },
    {
        "code": "MU5401/02", "name": "沪蓉公商务线 (PVG-TFU)", "hub": "华东基地", "fleet": "A321neo (窄体)", "routeType": "国内干线 (Trunk)", "captain": "孙伟 (机长)",
        "flights": "28 班/周", "revenue": "¥1.65 亿", "rawRevenue": 1.65, "yoy": "+11.2%", "rawYoy": 11.2, "plf": "86.0%", "rawPlf": 86.0,
        "rask": "¥0.4920", "rawRask": 0.4920, "cask": "¥0.3480", "rawCask": 0.3480, "otp": "90.4%", "rawOtp": 90.4, "rating": "A 级", "pax": 14.8
    },
    {
        "code": "MU9191/92", "name": "沪穗国产大飞机快线 (SHA-CAN)", "hub": "华东基地", "fleet": "C919 (国产)", "routeType": "国内干线 (Trunk)", "captain": "吴航 (试飞员/教员)",
        "flights": "21 班/周", "revenue": "¥1.35 亿", "rawRevenue": 1.35, "yoy": "+28.4%", "rawYoy": 28.4, "plf": "95.1%", "rawPlf": 95.1,
        "rask": "¥0.5640", "rawRask": 0.5640, "cask": "¥0.3550", "rawCask": 0.3550, "otp": "96.5%", "rawOtp": 96.5, "rating": "S 级", "pax": 12.0
    },
    {
        "code": "MU587/88", "name": "上海纽约远程洲际线 (PVG-JFK)", "hub": "华东基地", "fleet": "B777-300ER (宽体)", "routeType": "国际远程 (Intl)", "captain": "林海 (资深机长)",
        "flights": "14 班/周", "revenue": "¥4.20 亿", "rawRevenue": 4.20, "yoy": "+22.0%", "rawYoy": 22.0, "plf": "88.5%", "rawPlf": 88.5,
        "rask": "¥0.6120", "rawRask": 0.6120, "cask": "¥0.4150", "rawCask": 0.4150, "otp": "89.0%", "rawOtp": 89.0, "rating": "S 级", "pax": 28.0
    },
    {
        "code": "MU553/54", "name": "上海巴黎时尚商务线 (PVG-CDG)", "hub": "华东基地", "fleet": "A350-900 (宽体)", "routeType": "国际远程 (Intl)", "captain": "钱程 (教员)",
        "flights": "14 班/周", "revenue": "¥3.60 亿", "rawRevenue": 3.60, "yoy": "+19.4%", "rawYoy": 19.4, "plf": "89.2%", "rawPlf": 89.2,
        "rask": "¥0.5980", "rawRask": 0.5980, "cask": "¥0.4020", "rawCask": 0.4020, "otp": "91.5%", "rawOtp": 91.5, "rating": "S 级", "pax": 24.5
    },
    {
        "code": "MU2151/52", "name": "沪陕丝路干线 (SHA-XIY)", "hub": "华东基地", "fleet": "A320neo (窄体)", "routeType": "国内干线 (Trunk)", "captain": "高健 (机长)",
        "flights": "24 班/周", "revenue": "¥1.10 亿", "rawRevenue": 1.10, "yoy": "+7.5%", "rawYoy": 7.5, "plf": "83.5%", "rawPlf": 83.5,
        "rask": "¥0.4680", "rawRask": 0.4680, "cask": "¥0.3420", "rawCask": 0.3420, "otp": "88.6%", "rawOtp": 88.6, "rating": "B 级", "pax": 9.8
    },
    {
        "code": "FM9311/12", "name": "上海厦门海峡快线 (SHA-XMN)", "hub": "华东基地", "fleet": "B737-800 (窄体)", "routeType": "国内干线 (Trunk)", "captain": "谢涛 (机长)",
        "flights": "28 班/周", "revenue": "¥1.25 亿", "rawRevenue": 1.25, "yoy": "+9.0%", "rawYoy": 9.0, "plf": "87.8%", "rawPlf": 87.8,
        "rask": "¥0.4880", "rawRask": 0.4880, "cask": "¥0.3390", "rawCask": 0.3390, "otp": "93.0%", "rawOtp": 93.0, "rating": "A 级", "pax": 11.2
    },
    {
        "code": "MU2301/02", "name": "上海井冈山红色支线 (PVG-JGS)", "hub": "华东基地", "fleet": "ARJ21-700 (国产)", "routeType": "区域支线 (Regional)", "captain": "郭雷 (机长)",
        "flights": "14 班/周", "revenue": "¥0.45 亿", "rawRevenue": 0.45, "yoy": "+12.8%", "rawYoy": 12.8, "plf": "81.2%", "rawPlf": 81.2,
        "rask": "¥0.4250", "rawRask": 0.4250, "cask": "¥0.3200", "rawCask": 0.3200, "otp": "95.0%", "rawOtp": 95.0, "rating": "B 级", "pax": 3.6
    },
    {
        "code": "MU5613/14", "name": "上海武夷山旅游线 (SHA-WUS)", "hub": "华东基地", "fleet": "A320neo (窄体)", "routeType": "区域支线 (Regional)", "captain": "马腾 (机长)",
        "flights": "14 班/周", "revenue": "¥0.58 亿", "rawRevenue": 0.58, "yoy": "+5.2%", "rawYoy": 5.2, "plf": "82.6%", "rawPlf": 82.6,
        "rask": "¥0.4380", "rawRask": 0.4380, "cask": "¥0.3350", "rawCask": 0.3350, "otp": "89.2%", "rawOtp": 89.2, "rating": "B 级", "pax": 4.8
    },

    # --- 华南基地 (South China Hub - CAN/SZX) ---
    {
        "code": "CZ3101/02", "name": "沪深商务快线 (SHA-SZX)", "hub": "华南基地", "fleet": "B787-9 (宽体)", "routeType": "国内干线 (Trunk)", "captain": "李振华 (机长)",
        "flights": "42 班/周", "revenue": "¥3.40 亿", "rawRevenue": 3.40, "yoy": "+14.2%", "rawYoy": 14.2, "plf": "89.6%", "rawPlf": 89.6,
        "rask": "¥0.5410", "rawRask": 0.5410, "cask": "¥0.3650", "rawCask": 0.3650, "otp": "91.8%", "rawOtp": 91.8, "rating": "S 级", "pax": 26.5
    },
    {
        "code": "CZ3501/02", "name": "广深成渝互通线 (CAN-CTU)", "hub": "华南基地", "fleet": "B737-800 (窄体)", "routeType": "国内干线 (Trunk)", "captain": "周明 (教员)",
        "flights": "32 班/周", "revenue": "¥1.45 亿", "rawRevenue": 1.45, "yoy": "+8.0%", "rawYoy": 8.0, "plf": "85.4%", "rawPlf": 85.4,
        "rask": "¥0.4780", "rawRask": 0.4780, "cask": "¥0.3420", "rawCask": 0.3420, "otp": "87.6%", "rawOtp": 87.6, "rating": "B 级", "pax": 12.8
    },
    {
        "code": "CZ307/08", "name": "广州阿姆斯特丹枢纽线 (CAN-AMS)", "hub": "华南基地", "fleet": "B787-9 (宽体)", "routeType": "国际远程 (Intl)", "captain": "何文 (教员)",
        "flights": "14 班/周", "revenue": "¥3.20 亿", "rawRevenue": 3.20, "yoy": "+16.8%", "rawYoy": 16.8, "plf": "87.2%", "rawPlf": 87.2,
        "rask": "¥0.5750", "rawRask": 0.5750, "cask": "¥0.3950", "rawCask": 0.3950, "otp": "90.2%", "rawOtp": 90.2, "rating": "A 级", "pax": 21.0
    },
    {
        "code": "CZ325/26", "name": "广州悉尼袋鼠航线 (CAN-SYD)", "hub": "华南基地", "fleet": "A350-900 (宽体)", "routeType": "国际远程 (Intl)", "captain": "许峰 (机长)",
        "flights": "14 班/周", "revenue": "¥3.50 亿", "rawRevenue": 3.50, "yoy": "+21.5%", "rawYoy": 21.5, "plf": "91.0%", "rawPlf": 91.0,
        "rask": "¥0.5890", "rawRask": 0.5890, "cask": "¥0.3980", "rawCask": 0.3980, "otp": "92.4%", "rawOtp": 92.4, "rating": "S 级", "pax": 23.4
    },
    {
        "code": "CZ3301/02", "name": "广州北京大兴快线 (CAN-PKX)", "hub": "华南基地", "fleet": "B787-9 (宽体)", "routeType": "国内干线 (Trunk)", "captain": "梁宇 (机长)",
        "flights": "35 班/周", "revenue": "¥2.40 亿", "rawRevenue": 2.40, "yoy": "+13.5%", "rawYoy": 13.5, "plf": "88.6%", "rawPlf": 88.6,
        "rask": "¥0.5250", "rawRask": 0.5250, "cask": "¥0.3620", "rawCask": 0.3620, "otp": "91.0%", "rawOtp": 91.0, "rating": "A 级", "pax": 18.2
    },
    {
        "code": "CZ3851/52", "name": "深圳杭州电商快线 (SZX-HGH)", "hub": "华南基地", "fleet": "A321neo (窄体)", "routeType": "国内干线 (Trunk)", "captain": "冯强 (机长)",
        "flights": "28 班/周", "revenue": "¥1.50 亿", "rawRevenue": 1.50, "yoy": "+10.4%", "rawYoy": 10.4, "plf": "86.5%", "rawPlf": 86.5,
        "rask": "¥0.4950", "rawRask": 0.4950, "cask": "¥0.3450", "rawCask": 0.3450, "otp": "89.5%", "rawOtp": 89.5, "rating": "A 级", "pax": 13.0
    },
    {
        "code": "CZ6701/02", "name": "广州海口热带海岛线 (CAN-HAK)", "hub": "华南基地", "fleet": "B737-800 (窄体)", "routeType": "区域支线 (Regional)", "captain": "叶晨 (机长)",
        "flights": "28 班/周", "revenue": "¥0.85 亿", "rawRevenue": 0.85, "yoy": "+6.8%", "rawYoy": 6.8, "plf": "84.0%", "rawPlf": 84.0,
        "rask": "¥0.4420", "rawRask": 0.4420, "cask": "¥0.3300", "rawCask": 0.3300, "otp": "93.5%", "rawOtp": 93.5, "rating": "B 级", "pax": 8.0
    },
    {
        "code": "CZ3899/00", "name": "揭阳潮汕直飞北京 (SWA-PKX)", "hub": "华南基地", "fleet": "ARJ21-700 (国产)", "routeType": "区域支线 (Regional)", "captain": "彭斌 (机长)",
        "flights": "14 班/周", "revenue": "¥0.48 亿", "rawRevenue": 0.48, "yoy": "+14.0%", "rawYoy": 14.0, "plf": "82.5%", "rawPlf": 82.5,
        "rask": "¥0.4310", "rawRask": 0.4310, "cask": "¥0.3250", "rawCask": 0.3250, "otp": "94.0%", "rawOtp": 94.0, "rating": "B 级", "pax": 4.1
    },
    {
        "code": "CZ6881/82", "name": "深圳百色乡村振兴线 (SZX-AEB)", "hub": "华南基地", "fleet": "ARJ21-700 (国产)", "routeType": "区域支线 (Regional)", "captain": "黄明 (机长)",
        "flights": "14 班/周", "revenue": "¥0.38 亿", "rawRevenue": 0.38, "yoy": "+8.5%", "rawYoy": 8.5, "plf": "79.8%", "rawPlf": 79.8,
        "rask": "¥0.4120", "rawRask": 0.4120, "cask": "¥0.3180", "rawCask": 0.3180, "otp": "96.0%", "rawOtp": 96.0, "rating": "B 级", "pax": 3.2
    },

    # --- 北方基地 (North China Hub - PEK/PKX) ---
    {
        "code": "CA1501/02", "name": "京广商务干线 (PEK-CAN)", "hub": "北方基地", "fleet": "A350-900 (宽体)", "routeType": "国内干线 (Trunk)", "captain": "王志刚 (教员)",
        "flights": "38 班/周", "revenue": "¥2.80 亿", "rawRevenue": 2.80, "yoy": "+9.8%", "rawYoy": 9.8, "plf": "87.5%", "rawPlf": 87.5,
        "rask": "¥0.5180", "rawRask": 0.5180, "cask": "¥0.3720", "rawCask": 0.3720, "otp": "89.5%", "rawOtp": 89.5, "rating": "A 级", "pax": 22.0
    },
    {
        "code": "ZH9101/02", "name": "京深创新干线 (PEK-SZX)", "hub": "北方基地", "fleet": "A321neo (窄体)", "routeType": "国内干线 (Trunk)", "captain": "陈宏 (机长)",
        "flights": "30 班/周", "revenue": "¥1.80 亿", "rawRevenue": 1.80, "yoy": "+15.0%", "rawYoy": 15.0, "plf": "88.2%", "rawPlf": 88.2,
        "rask": "¥0.5260", "rawRask": 0.5260, "cask": "¥0.3580", "rawCask": 0.3580, "otp": "92.0%", "rawOtp": 92.0, "rating": "S 级", "pax": 15.5
    },
    {
        "code": "CA981/82", "name": "北京纽约极地洲际线 (PEK-JFK)", "hub": "北方基地", "fleet": "B777-300ER (宽体)", "routeType": "国际远程 (Intl)", "captain": "沈伟 (资深教员)",
        "flights": "14 班/周", "revenue": "¥4.50 亿", "rawRevenue": 4.50, "yoy": "+17.5%", "rawYoy": 17.5, "plf": "90.5%", "rawPlf": 90.5,
        "rask": "¥0.6250", "rawRask": 0.6250, "cask": "¥0.4200", "rawCask": 0.4200, "otp": "91.0%", "rawOtp": 91.0, "rating": "S 级", "pax": 30.0
    },
    {
        "code": "CA931/32", "name": "北京法兰克福枢纽线 (PEK-FRA)", "hub": "北方基地", "fleet": "A350-900 (宽体)", "routeType": "国际远程 (Intl)", "captain": "韩磊 (机长)",
        "flights": "14 班/周", "revenue": "¥3.80 亿", "rawRevenue": 3.80, "yoy": "+18.0%", "rawYoy": 18.0, "plf": "89.0%", "rawPlf": 89.0,
        "rask": "¥0.6050", "rawRask": 0.6050, "cask": "¥0.4080", "rawCask": 0.4080, "otp": "93.0%", "rawOtp": 93.0, "rating": "S 级", "pax": 25.5
    },
    {
        "code": "CA1405/06", "name": "京蓉精品商务线 (PEK-TFU)", "hub": "北方基地", "fleet": "A321neo (窄体)", "routeType": "国内干线 (Trunk)", "captain": "刘洋 (机长)",
        "flights": "35 班/周", "revenue": "¥2.10 亿", "rawRevenue": 2.10, "yoy": "+11.0%", "rawYoy": 11.0, "plf": "87.0%", "rawPlf": 87.0,
        "rask": "¥0.5100", "rawRask": 0.5100, "cask": "¥0.3550", "rawCask": 0.3550, "otp": "90.0%", "rawOtp": 90.0, "rating": "A 级", "pax": 17.5
    },
    {
        "code": "CA1831/32", "name": "北京西安古都商旅线 (PEK-XIY)", "hub": "北方基地", "fleet": "B737-800 (窄体)", "routeType": "国内干线 (Trunk)", "captain": "杜强 (机长)",
        "flights": "28 班/周", "revenue": "¥1.30 亿", "rawRevenue": 1.30, "yoy": "+8.2%", "rawYoy": 8.2, "plf": "85.0%", "rawPlf": 85.0,
        "rask": "¥0.4820", "rawRask": 0.4820, "cask": "¥0.3450", "rawCask": 0.3450, "otp": "89.0%", "rawOtp": 89.0, "rating": "B 级", "pax": 11.0
    },
    {
        "code": "CA1289/90", "name": "北京海拉尔草原旅游线 (PEK-HLD)", "hub": "北方基地", "fleet": "C919 (国产)", "routeType": "区域支线 (Regional)", "captain": "丁一 (机长)",
        "flights": "14 班/周", "revenue": "¥0.72 亿", "rawRevenue": 0.72, "yoy": "+22.5%", "rawYoy": 22.5, "plf": "91.5%", "rawPlf": 91.5,
        "rask": "¥0.5350", "rawRask": 0.5350, "cask": "¥0.3500", "rawCask": 0.3500, "otp": "95.5%", "rawOtp": 95.5, "rating": "S 级", "pax": 6.2
    },
    {
        "code": "CA1115/16", "name": "北京延安红色经典线 (PKX-ENY)", "hub": "北方基地", "fleet": "ARJ21-700 (国产)", "routeType": "区域支线 (Regional)", "captain": "薛飞 (机长)",
        "flights": "14 班/周", "revenue": "¥0.42 亿", "rawRevenue": 0.42, "yoy": "+9.5%", "rawYoy": 9.5, "plf": "80.5%", "rawPlf": 80.5,
        "rask": "¥0.4180", "rawRask": 0.4180, "cask": "¥0.3220", "rawCask": 0.3220, "otp": "94.5%", "rawOtp": 94.5, "rating": "B 级", "pax": 3.5
    },
    {
        "code": "CA1681/82", "name": "北京哈尔滨冰雪旅游线 (PEK-HRB)", "hub": "北方基地", "fleet": "A320neo (窄体)", "routeType": "国内干线 (Trunk)", "captain": "任杰 (机长)",
        "flights": "21 班/周", "revenue": "¥1.15 亿", "rawRevenue": 1.15, "yoy": "+16.2%", "rawYoy": 16.2, "plf": "89.5%", "rawPlf": 89.5,
        "rask": "¥0.5050", "rawRask": 0.5050, "cask": "¥0.3480", "rawCask": 0.3480, "otp": "91.2%", "rawOtp": 91.2, "rating": "A 级", "pax": 10.0
    },

    # --- 西南基地 (Southwest Hub - TFU/CTU/CKG) ---
    {
        "code": "3U8881/82", "name": "蓉京高原干线 (TFU-PKX)", "hub": "西南基地", "fleet": "A321neo (窄体)", "routeType": "国内干线 (Trunk)", "captain": "赵立新 (机长)",
        "flights": "35 班/周", "revenue": "¥1.90 亿", "rawRevenue": 1.90, "yoy": "+6.4%", "rawYoy": 6.4, "plf": "84.2%", "rawPlf": 84.2,
        "rask": "¥0.4850", "rawRask": 0.4850, "cask": "¥0.3540", "rawCask": 0.3540, "otp": "88.0%", "rawOtp": 88.0, "rating": "A 级", "pax": 15.0
    },
    {
        "code": "3U8633/34", "name": "成都拉萨高原生命线 (TFU-LXA)", "hub": "西南基地", "fleet": "A319neo (高原型)", "routeType": "国内干线 (Trunk)", "captain": "刘传健 (英雄机长/教员)",
        "flights": "28 班/周", "revenue": "¥2.20 亿", "rawRevenue": 2.20, "yoy": "+15.8%", "rawYoy": 15.8, "plf": "91.5%", "rawPlf": 91.5,
        "rask": "¥0.5850", "rawRask": 0.5850, "cask": "¥0.3950", "rawCask": 0.3950, "otp": "95.0%", "rawOtp": 95.0, "rating": "S 级", "pax": 16.5
    },
    {
        "code": "3U3837/38", "name": "成都洛杉矶直飞航线 (TFU-LAX)", "hub": "西南基地", "fleet": "A350-900 (宽体)", "routeType": "国际远程 (Intl)", "captain": "唐俊 (教员)",
        "flights": "14 班/周", "revenue": "¥3.10 亿", "rawRevenue": 3.10, "yoy": "+16.0%", "rawYoy": 16.0, "plf": "86.8%", "rawPlf": 86.8,
        "rask": "¥0.5680", "rawRask": 0.5680, "cask": "¥0.4050", "rawCask": 0.4050, "otp": "88.5%", "rawOtp": 88.5, "rating": "A 级", "pax": 20.5
    },
    {
        "code": "3U8901/02", "name": "成都广州蓉穗快线 (TFU-CAN)", "hub": "西南基地", "fleet": "A321neo (窄体)", "routeType": "国内干线 (Trunk)", "captain": "胡斌 (机长)",
        "flights": "35 班/周", "revenue": "¥1.75 亿", "rawRevenue": 1.75, "yoy": "+9.2%", "rawYoy": 9.2, "plf": "85.5%", "rawPlf": 85.5,
        "rask": "¥0.4880", "rawRask": 0.4880, "cask": "¥0.3480", "rawCask": 0.3480, "otp": "89.0%", "rawOtp": 89.0, "rating": "A 级", "pax": 14.5
    },
    {
        "code": "3U8695/96", "name": "成都西双版纳热带线 (TFU-JHG)", "hub": "西南基地", "fleet": "C919 (国产)", "routeType": "国内干线 (Trunk)", "captain": "罗勇 (机长)",
        "flights": "21 班/周", "revenue": "¥1.15 亿", "rawRevenue": 1.15, "yoy": "+24.0%", "rawYoy": 24.0, "plf": "93.0%", "rawPlf": 93.0,
        "rask": "¥0.5420", "rawRask": 0.5420, "cask": "¥0.3520", "rawCask": 0.3520, "otp": "94.0%", "rawOtp": 94.0, "rating": "S 级", "pax": 10.5
    },
    {
        "code": "3U8005/06", "name": "成都林芝高原生态线 (TFU-LZY)", "hub": "西南基地", "fleet": "A319neo (高原型)", "routeType": "区域支线 (Regional)", "captain": "严峻 (机长)",
        "flights": "14 班/周", "revenue": "¥0.95 亿", "rawRevenue": 0.95, "yoy": "+18.2%", "rawYoy": 18.2, "plf": "88.0%", "rawPlf": 88.0,
        "rask": "¥0.5750", "rawRask": 0.5750, "cask": "¥0.3880", "rawCask": 0.3880, "otp": "92.0%", "rawOtp": 92.0, "rating": "A 级", "pax": 7.2
    },
    {
        "code": "EU2201/02", "name": "成都格萨尔高原支线 (TFU-GYS)", "hub": "西南基地", "fleet": "ARJ21-700 (国产)", "routeType": "区域支线 (Regional)", "captain": "段超 (机长)",
        "flights": "14 班/周", "revenue": "¥0.35 亿", "rawRevenue": 0.35, "yoy": "+11.5%", "rawYoy": 11.5, "plf": "78.5%", "rawPlf": 78.5,
        "rask": "¥0.4100", "rawRask": 0.4100, "cask": "¥0.3200", "rawCask": 0.3200, "otp": "96.5%", "rawOtp": 96.5, "rating": "B 级", "pax": 2.8
    },
    {
        "code": "3U8751/52", "name": "重庆深圳山海快线 (CKG-SZX)", "hub": "西南基地", "fleet": "A320neo (窄体)", "routeType": "国内干线 (Trunk)", "captain": "魏明 (机长)",
        "flights": "28 班/周", "revenue": "¥1.40 亿", "rawRevenue": 1.40, "yoy": "+7.8%", "rawYoy": 7.8, "plf": "84.8%", "rawPlf": 84.8,
        "rask": "¥0.4750", "rawRask": 0.4750, "cask": "¥0.3400", "rawCask": 0.3400, "otp": "90.5%", "rawOtp": 90.5, "rating": "B 级", "pax": 12.0
    }
]

AIRLINE_TABLE_COLUMNS = TABLE_COLUMNS
AIRLINE_TABLE_ROWS = TABLE_ROWS

# =============================================================================
# 零售连锁与电商行业全要素数据集 (Retail & E-Commerce Dataset)
# =============================================================================
RETAIL_TABLE_COLUMNS = [
    {"key": "code", "title": "门店编码", "align": "left", "sortable": True, "visible": True},
    {"key": "name", "title": "门店/大区名称", "align": "left", "sortable": True, "visible": True},
    {"key": "region", "title": "所属大区", "align": "left", "sortable": True, "visible": True},
    {"key": "format", "title": "门店业态", "align": "left", "sortable": True, "visible": True},
    {"key": "manager", "title": "店长/负责人", "align": "left", "sortable": True, "visible": True},
    {"key": "traffic", "title": "周进店客流", "align": "right", "sortable": True, "visible": True},
    {"key": "gmv", "title": "当期GMV", "align": "right", "sortable": True, "visible": True},
    {"key": "yoy", "title": "GMV同比", "align": "right", "sortable": True, "visible": True},
    {"key": "salesPerSqm", "title": "日均坪效", "align": "right", "sortable": True, "visible": True},
    {"key": "conversion", "title": "客流转化率", "align": "right", "sortable": True, "visible": True},
    {"key": "basketSize", "title": "平均客单价", "align": "right", "sortable": True, "visible": True},
    {"key": "repurchase", "title": "会员复购率", "align": "right", "sortable": True, "visible": True},
    {"key": "margin", "title": "经营利润率", "align": "right", "sortable": True, "visible": True},
    {"key": "rating", "title": "运营评级", "align": "center", "sortable": True, "visible": True}
]

RETAIL_TABLE_ROWS = [
    # 华东大区
    {"code": "SH001", "name": "上海陆家嘴旗舰超级店", "region": "华东大区", "format": "大型综合超市", "manager": "陈晓东", "traffic": "12.8 万人", "gmv": "¥8,450 万", "rawRevenue": 0.845, "yoy": "+18.2%", "rawYoy": 18.2, "salesPerSqm": "¥142/㎡/天", "conversion": "68.5%", "rawPlf": 68.5, "basketSize": "¥186.5", "rawRask": 186.5, "repurchase": "62.4%", "margin": "24.8%", "rating": "S 级"},
    {"code": "SH002", "name": "上海静安南京西路精品店", "region": "华东大区", "format": "精品超市", "manager": "王梓萌", "traffic": "8.5 万人", "gmv": "¥5,920 万", "rawRevenue": 0.592, "yoy": "+14.6%", "rawYoy": 14.6, "salesPerSqm": "¥198/㎡/天", "conversion": "74.2%", "rawPlf": 74.2, "basketSize": "¥245.0", "rawRask": 245.0, "repurchase": "71.0%", "margin": "28.5%", "rating": "S 级"},
    {"code": "HZ001", "name": "杭州西湖湖滨银泰店", "region": "华东大区", "format": "标准超市", "manager": "刘阳", "traffic": "9.2 万人", "gmv": "¥4,860 万", "rawRevenue": 0.486, "yoy": "+12.8%", "rawYoy": 12.8, "salesPerSqm": "¥125/㎡/天", "conversion": "62.0%", "rawPlf": 62.0, "basketSize": "¥152.0", "rawRask": 152.0, "repurchase": "58.6%", "margin": "21.4%", "rating": "A 级"},
    {"code": "NJ001", "name": "南京新街口中心商业店", "region": "华东大区", "format": "大型综合超市", "manager": "张伟", "traffic": "10.4 万人", "gmv": "¥5,340 万", "rawRevenue": 0.534, "yoy": "+9.5%", "rawYoy": 9.5, "salesPerSqm": "¥118/㎡/天", "conversion": "59.8%", "rawPlf": 59.8, "basketSize": "¥138.0", "rawRask": 138.0, "repurchase": "54.2%", "margin": "19.5%", "rating": "A 级"},
    {"code": "SZ001", "name": "苏州园区时代广场社区店", "region": "华东大区", "format": "便利店/社区店", "manager": "李敏", "traffic": "4.2 万人", "gmv": "¥1,850 万", "rawRevenue": 0.185, "yoy": "+22.4%", "rawYoy": 22.4, "salesPerSqm": "¥165/㎡/天", "conversion": "82.5%", "rawPlf": 82.5, "basketSize": "¥42.5", "rawRask": 42.5, "repurchase": "78.2%", "margin": "23.0%", "rating": "S 级"},
    # 华北大区
    {"code": "BJ001", "name": "北京国贸CBD核心旗舰店", "region": "华北大区", "format": "精品超市", "manager": "赵一鸣", "traffic": "9.8 万人", "gmv": "¥7,200 万", "rawRevenue": 0.720, "yoy": "+16.5%", "rawYoy": 16.5, "salesPerSqm": "¥210/㎡/天", "conversion": "71.5%", "rawPlf": 71.5, "basketSize": "¥268.0", "rawRask": 268.0, "repurchase": "69.4%", "margin": "27.2%", "rating": "S 级"},
    {"code": "BJ002", "name": "北京中关村科技园区店", "region": "华北大区", "format": "标准超市", "manager": "周航", "traffic": "11.2 万人", "gmv": "¥6,100 万", "rawRevenue": 0.610, "yoy": "+13.2%", "rawYoy": 13.2, "salesPerSqm": "¥135/㎡/天", "conversion": "64.0%", "rawPlf": 64.0, "basketSize": "¥160.0", "rawRask": 160.0, "repurchase": "61.5%", "margin": "22.0%", "rating": "A 级"},
    {"code": "TJ001", "name": "天津和平金街购物中心店", "region": "华北大区", "format": "大型综合超市", "manager": "吴大勇", "traffic": "8.6 万人", "gmv": "¥3,950 万", "rawRevenue": 0.395, "yoy": "+6.8%", "rawYoy": 6.8, "salesPerSqm": "¥95/㎡/天", "conversion": "56.0%", "rawPlf": 56.0, "basketSize": "¥122.0", "rawRask": 122.0, "repurchase": "51.0%", "margin": "17.8%", "rating": "B 级"},
    {"code": "QD001", "name": "青岛市南万象城海景店", "region": "华北大区", "format": "标准超市", "manager": "孙悦", "traffic": "7.8 万人", "gmv": "¥4,200 万", "rawRevenue": 0.420, "yoy": "+11.0%", "rawYoy": 11.0, "salesPerSqm": "¥112/㎡/天", "conversion": "60.5%", "rawPlf": 60.5, "basketSize": "¥145.0", "rawRask": 145.0, "repurchase": "55.8%", "margin": "20.5%", "rating": "A 级"},
    # 华南大区
    {"code": "GZ001", "name": "广州天河城全渠道体验店", "region": "华南大区", "format": "大型综合超市", "manager": "郭栋", "traffic": "13.5 万人", "gmv": "¥8,100 万", "rawRevenue": 0.810, "yoy": "+15.0%", "rawYoy": 15.0, "salesPerSqm": "¥138/㎡/天", "conversion": "66.0%", "rawPlf": 66.0, "basketSize": "¥175.0", "rawRask": 175.0, "repurchase": "64.0%", "margin": "23.5%", "rating": "S 级"},
    {"code": "SZ002", "name": "深圳南山万象天地智能店", "region": "华南大区", "format": "精品超市", "manager": "郑凯", "traffic": "10.6 万人", "gmv": "¥7,650 万", "rawRevenue": 0.765, "yoy": "+21.4%", "rawYoy": 21.4, "salesPerSqm": "¥225/㎡/天", "conversion": "76.0%", "rawPlf": 76.0, "basketSize": "¥255.0", "rawRask": 255.0, "repurchase": "73.5%", "margin": "29.0%", "rating": "S 级"},
    {"code": "FS001", "name": "佛山千灯湖商圈社区店", "region": "华南大区", "format": "便利店/社区店", "manager": "何俊", "traffic": "5.1 万人", "gmv": "¥2,100 万", "rawRevenue": 0.210, "yoy": "+19.0%", "rawYoy": 19.0, "salesPerSqm": "¥158/㎡/天", "conversion": "80.0%", "rawPlf": 80.0, "basketSize": "¥38.5", "rawRask": 38.5, "repurchase": "76.0%", "margin": "22.5%", "rating": "A 级"},
    # 西南大区
    {"code": "CD001", "name": "成都春熙路太古里概念店", "region": "西南大区", "format": "大型综合超市", "manager": "杨帆", "traffic": "14.2 万人", "gmv": "¥7,800 万", "rawRevenue": 0.780, "yoy": "+17.5%", "rawYoy": 17.5, "salesPerSqm": "¥140/㎡/天", "conversion": "67.2%", "rawPlf": 67.2, "basketSize": "¥168.0", "rawRask": 168.0, "repurchase": "65.0%", "margin": "24.0%", "rating": "S 级"},
    {"code": "CQ001", "name": "重庆解放碑步行街旗舰店", "region": "西南大区", "format": "大型综合超市", "manager": "梁博", "traffic": "11.8 万人", "gmv": "¥5,800 万", "rawRevenue": 0.580, "yoy": "+10.2%", "rawYoy": 10.2, "salesPerSqm": "¥115/㎡/天", "conversion": "61.0%", "rawPlf": 61.0, "basketSize": "¥142.0", "rawRask": 142.0, "repurchase": "57.5%", "margin": "20.0%", "rating": "A 级"},
    {"code": "KM001", "name": "昆明顺城购物中心生鲜店", "region": "西南大区", "format": "标准超市", "manager": "许峰", "traffic": "6.9 万人", "gmv": "¥3,200 万", "rawRevenue": 0.320, "yoy": "+8.4%", "rawYoy": 8.4, "salesPerSqm": "¥98/㎡/天", "conversion": "58.0%", "rawPlf": 58.0, "basketSize": "¥115.0", "rawRask": 115.0, "repurchase": "53.0%", "margin": "18.5%", "rating": "B 级"}
]

# =============================================================================
# SaaS 业务分析全要素数据集 (SaaS & Cloud Dataset)
# =============================================================================
SAAS_TABLE_COLUMNS = [
    {"key": "code", "title": "租户ID", "align": "left", "sortable": True, "visible": True},
    {"key": "name", "title": "企业租户名称", "align": "left", "sortable": True, "visible": True},
    {"key": "segment", "title": "客户层级", "align": "left", "sortable": True, "visible": True},
    {"key": "tier", "title": "订阅版本", "align": "left", "sortable": True, "visible": True},
    {"key": "csm", "title": "客户成功顾问", "align": "left", "sortable": True, "visible": True},
    {"key": "mau", "title": "活跃席位(MAU)", "align": "right", "sortable": True, "visible": True},
    {"key": "arr", "title": "当期ARR", "align": "right", "sortable": True, "visible": True},
    {"key": "yoy", "title": "ARR增速", "align": "right", "sortable": True, "visible": True},
    {"key": "ndr", "title": "净留存率(NDR)", "align": "right", "sortable": True, "visible": True},
    {"key": "cacPayback", "title": "CAC回收期", "align": "right", "sortable": True, "visible": True},
    {"key": "ltvCac", "title": "LTV/CAC", "align": "right", "sortable": True, "visible": True},
    {"key": "nps", "title": "NPS推荐值", "align": "right", "sortable": True, "visible": True},
    {"key": "health", "title": "健康度评级", "align": "center", "sortable": True, "visible": True}
]

SAAS_TABLE_ROWS = [
    {"code": "CUST-1001", "name": "字节跳动科技云中心", "segment": "头部战略 KA", "tier": "企业私有化/旗舰版", "csm": "张文浩", "mau": "12,500 席", "arr": "¥1,850 万", "rawRevenue": 0.185, "yoy": "+45.0%", "rawYoy": 45.0, "ndr": "138.5%", "rawPlf": 138.5, "cacPayback": "4.2 个月", "rawRask": 4.2, "ltvCac": "8.5x", "nps": "+82", "health": "S 级"},
    {"code": "CUST-1002", "name": "招商银行金融科技部", "segment": "头部战略 KA", "tier": "金融合规专有版", "csm": "刘慧玲", "mau": "8,200 席", "arr": "¥1,420 万", "rawRevenue": 0.142, "yoy": "+28.0%", "rawYoy": 28.0, "ndr": "124.0%", "rawPlf": 124.0, "cacPayback": "5.8 个月", "rawRask": 5.8, "ltvCac": "6.2x", "nps": "+78", "health": "S 级"},
    {"code": "CUST-1003", "name": "理想汽车智能制造链", "segment": "腰部行业成长", "tier": "高级专业版", "csm": "王明阳", "mau": "3,400 席", "arr": "¥680 万", "rawRevenue": 0.068, "yoy": "+32.5%", "rawYoy": 32.5, "ndr": "118.0%", "rawPlf": 118.0, "cacPayback": "7.1 个月", "rawRask": 7.1, "ltvCac": "5.0x", "nps": "+68", "health": "A 级"},
    {"code": "CUST-1004", "name": "喜茶全渠道运营总部", "segment": "腰部行业成长", "tier": "高级专业版", "csm": "陈静", "mau": "2,100 席", "arr": "¥450 万", "rawRevenue": 0.045, "yoy": "+22.0%", "rawYoy": 22.0, "ndr": "112.5%", "rawPlf": 112.5, "cacPayback": "8.4 个月", "rawRask": 8.4, "ltvCac": "4.2x", "nps": "+64", "health": "A 级"},
    {"code": "CUST-1005", "name": "极客时间数字教育网", "segment": "标准 SMB 客户", "tier": "标准团队版", "csm": "赵磊", "mau": "650 席", "arr": "¥120 万", "rawRevenue": 0.012, "yoy": "+12.0%", "rawYoy": 12.0, "ndr": "96.5%", "rawPlf": 96.5, "cacPayback": "11.2 个月", "rawRask": 11.2, "ltvCac": "2.8x", "nps": "+45", "health": "B 级"},
    {"code": "CUST-1006", "name": "元气森林数字营销部", "segment": "腰部行业成长", "tier": "高级专业版", "csm": "王明阳", "mau": "1,800 席", "arr": "¥380 万", "rawRevenue": 0.038, "yoy": "+18.5%", "rawYoy": 18.5, "ndr": "108.0%", "rawPlf": 108.0, "cacPayback": "9.0 个月", "rawRask": 9.0, "ltvCac": "3.8x", "nps": "+58", "health": "A 级"}
]

# =============================================================================
# 财务分析与经营归因数据集 (Financial & Management Dataset)
# =============================================================================
FINANCIAL_TABLE_COLUMNS = [
    {"key": "code", "title": "事业部代码", "align": "left", "sortable": True, "visible": True},
    {"key": "name", "title": "事业部/核算单元", "align": "left", "sortable": True, "visible": True},
    {"key": "segment", "title": "业务板块", "align": "left", "sortable": True, "visible": True},
    {"key": "costCenter", "title": "成本中心代码", "align": "left", "sortable": True, "visible": True},
    {"key": "cfo", "title": "财务负责人", "align": "left", "sortable": True, "visible": True},
    {"key": "revenue", "title": "当期营收", "align": "right", "sortable": True, "visible": True},
    {"key": "yoy", "title": "营收YoY", "align": "right", "sortable": True, "visible": True},
    {"key": "grossMargin", "title": "毛利率", "align": "right", "sortable": True, "visible": True},
    {"key": "opex", "title": "运营费用(OPEX)", "align": "right", "sortable": True, "visible": True},
    {"key": "ebitdaMargin", "title": "EBITDA利润率", "align": "right", "sortable": True, "visible": True},
    {"key": "fcf", "title": "自由现金流", "align": "right", "sortable": True, "visible": True},
    {"key": "roic", "title": "资本回报率(ROIC)", "align": "right", "sortable": True, "visible": True},
    {"key": "budgetAchieve", "title": "预算达成率", "align": "right", "sortable": True, "visible": True},
    {"key": "auditRating", "title": "风控评级", "align": "center", "sortable": True, "visible": True}
]

FINANCIAL_TABLE_ROWS = [
    {"code": "BU-01", "name": "数字化智能与云服务部", "segment": "核心科技主营", "costCenter": "CC-101-TECH", "cfo": "周立新 (CPA)", "revenue": "¥42.50 亿", "rawRevenue": 42.50, "yoy": "+28.4%", "rawYoy": 28.4, "grossMargin": "68.5%", "opex": "¥12.80 亿", "ebitdaMargin": "34.2%", "rawPlf": 34.2, "fcf": "¥11.50 亿", "rawRask": 11.50, "roic": "24.8%", "budgetAchieve": "112.5%", "auditRating": "A+ 优秀"},
    {"code": "BU-02", "name": "消费电子与智能终端部", "segment": "高端硬件制造", "costCenter": "CC-201-HW", "cfo": "钱雪梅 (CPA)", "revenue": "¥68.20 亿", "rawRevenue": 68.20, "yoy": "+12.0%", "rawYoy": 12.0, "grossMargin": "32.0%", "opex": "¥9.60 亿", "ebitdaMargin": "18.5%", "rawPlf": 18.5, "fcf": "¥8.20 亿", "rawRask": 8.20, "roic": "16.4%", "budgetAchieve": "104.0%", "auditRating": "A 良好"},
    {"code": "BU-03", "name": "全球供应链与智能物流", "segment": "基础设施运营", "costCenter": "CC-301-LOG", "cfo": "孙志刚", "revenue": "¥24.80 亿", "rawRevenue": 24.80, "yoy": "+18.6%", "rawYoy": 18.6, "grossMargin": "22.4%", "opex": "¥4.20 亿", "ebitdaMargin": "14.2%", "rawPlf": 14.2, "fcf": "¥3.10 亿", "rawRask": 3.10, "roic": "12.8%", "budgetAchieve": "98.5%", "auditRating": "A 良好"},
    {"code": "BU-04", "name": "新零售与智慧全渠道", "segment": "消费与零售板块", "costCenter": "CC-401-RET", "cfo": "李宏图", "revenue": "¥35.60 亿", "rawRevenue": 35.60, "yoy": "+21.5%", "rawYoy": 21.5, "grossMargin": "29.8%", "opex": "¥6.10 亿", "ebitdaMargin": "16.8%", "rawPlf": 16.8, "fcf": "¥4.80 亿", "rawRask": 4.80, "roic": "15.2%", "budgetAchieve": "106.8%", "auditRating": "A 良好"}
]

