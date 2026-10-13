"""Single source of the executive-charts color tokens.

Signed changes follow the Chinese market convention 红涨绿跌: ``positive`` is red
for increases and ``negative`` is green for decreases. Status badges, series
identity, and target markers use brand, neutral, or ``attention`` tokens so red
and green keep their up/down meaning.
"""
import json
import re

PALETTE = {
    "primary": "#123B5D",        # 旗舰深海蓝：主序列与核心强调
    "primaryStrong": "#0B2A42",  # 墨蓝黑：高对比标题与关键标签
    "primarySoft": "#DCE8F0",    # 冰川淡蓝：辅助对比与底槽
    "secondary": "#2C6485",      # 钢蓝：次级对比序列
    "tertiary": "#628EA8",       # 浅灰蓝：第三对比序列、预测延伸
    "slate": "#8C9DAE",          # 雾板岩灰：第四对比序列
    "ink": "#17212B",            # 炭黑：正文与关键数值
    "inkMuted": "#52606D",       # 板岩深灰：副标题与坐标刻度
    "inkSubtle": "#7B8794",      # 板岩淡灰：注脚与量纲
    "positive": "#A4453C",       # 红：上涨、增加、正向变动
    "negative": "#2F6B55",       # 绿：下跌、减少、负向变动
    "attention": "#9A6A18",      # 琥珀金：预警与重点关注
    "canvas": "#FFFFFF",
    "surfaceGround": "#F8FAFC",
    "gridline": "#E6EAED",
    "rule": "#C9D1D8",
}

# Series identity only: slots avoid the red/green change colors. Slots 6-7 (#7867AD dusty violet,
# #634B36 warm brown) were picked with the dataviz palette validator for CVD and contrast separation.
CATEGORICAL = ["#123B5D", "#2C6485", "#628EA8", "#8C9DAE", "#9A6A18", "#7867AD", "#634B36", "#BDD0DC"]

# Tailwind already ships a `slate-*` scale used throughout the shell markup.
_TAILWIND_EXCLUDED = {"slate"}


def _kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def _tailwind_entries() -> dict[str, str]:
    return {_kebab(key): value for key, value in PALETTE.items() if key not in _TAILWIND_EXCLUDED}


def tailwind_colors_js() -> str:
    """Return the Tailwind v3 `theme.extend.colors` object literal."""
    return json.dumps(_tailwind_entries())


def tailwind_theme_css() -> str:
    """Return the Tailwind v4 `@theme` block that defines the same color utilities."""
    variables = " ".join(f"--color-{key}: {value};" for key, value in _tailwind_entries().items())
    return f"@theme {{ {variables} }}"


def echarts_palette_js() -> str:
    """Return the `TOKENS.palette` object literal consumed by chart renderers."""
    return json.dumps({**PALETTE, "categorical": CATEGORICAL})


def categorical_js() -> str:
    return json.dumps(CATEGORICAL)
