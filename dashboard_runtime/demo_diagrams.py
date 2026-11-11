"""Authored schematic assets for bundled examples, not chart-type adapters."""
import copy
from .structure_diagram import presentation


def _diagram(shapes, annotations):
    return {'version': 1, 'viewBox': [0, 0, 600, 360],
            'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 360">' + shapes + '</svg>',
            'annotations': annotations}


def _metric(key, anchor, label, align='left'):
    return {'id': key, 'metricId': key, 'anchor': anchor, 'label': label, 'align': align}


def _label(key, name, description, anchor, label, align='left'):
    return {'id': key, 'name': name, 'description': description, 'anchor': anchor, 'label': label, 'align': align}


_AXIS = '<path d="M160 70V280H440" fill="none" stroke="#8093a0"/>'
_BARS = '<path d="M200 280V200H230V280ZM280 280V130H310V280ZM360 280V165H390V280Z" fill="#123b5d"/>'
_LINE = '<path d="M215 230L295 110L375 155" fill="none" stroke="#a74439" stroke-width="3"/><g fill="white" stroke="#a74439" stroke-width="3"><circle cx="215" cy="230" r="4"/><circle cx="295" cy="110" r="4"/><circle cx="375" cy="155" r="4"/></g>'
_CARD = '<rect x="160" y="85" width="280" height="190" rx="8" fill="#f5f5f4" stroke="#8093a0"/><path d="M190 130H275M190 170H335" stroke="#123b5d" stroke-width="12"/>'
_FOOTER = '<path d="M190 245H265" stroke="#8093a0" stroke-width="5"/>'
_PERIOD = _label('period', '周期', '按绑定的时间字段排列；月度与季度共用同一结构。', [300, 280], [300, 330], 'center')
_REGION = _label('region', '基地', '各柱分别对应一个基地。', [300, 280], [300, 330], 'center')

BASE = {
    'total': _diagram(_CARD, [_metric('revenue', [250, 170], [20, 170])]),
    'load': _diagram(_CARD, [_metric('load-factor', [250, 170], [20, 170])]),
    'trend': _diagram(_AXIS + _LINE, [_metric('revenue', [295, 110], [20, 110]), _PERIOD]),
    'regions': _diagram(_AXIS + _BARS, [_metric('revenue', [215, 230], [20, 180]), _REGION]),
    'details': _diagram('<rect x="160" y="85" width="280" height="190" fill="none" stroke="#8093a0"/><path d="M160 125H440M160 175H440M160 225H440M250 85V275M345 85V275" stroke="#8093a0"/>', [
        _label('columns', '字段', '每列对应数据集中的一个字段，名称和单位见表头。', [295, 105], [20, 80]),
        _label('rows', '记录', '每行是一条符合当前筛选条件的数据记录。', [200, 200], [20, 200]),
    ]),
}
EXECUTIVE = {
    **BASE,
    'total': _diagram(_CARD + _FOOTER, [_metric('revenue', [250, 170], [20, 130]), _metric('baseline-revenue', [225, 245], [20, 260])]),
    'load': _diagram(_CARD + _FOOTER, [_metric('load-factor', [250, 170], [20, 130]), _metric('seats', [225, 245], [20, 260])]),
    'passengers': _diagram(_CARD + _FOOTER + '<path d="M325 230L355 200L390 215" fill="none" stroke="#123b5d" stroke-width="2"/>', [
        _metric('passengers', [250, 170], [20, 130]), _metric('seats', [225, 245], [20, 260]),
        _label('trend', '月度趋势', '同一旅客运输量指标按月份排列。', [355, 200], [580, 200], 'right')]),
    'goal': _diagram(_CARD + _FOOTER + '<path d="M190 210H410" stroke="#dbe3e8" stroke-width="8"/><path d="M190 210H340" stroke="#123b5d" stroke-width="8"/>', [
        _metric('attainment', [250, 170], [20, 130]), _metric('budget', [225, 245], [20, 260]),
        _label('progress', '完成进度', '进度条表示收入相对于预算的完成程度。', [340, 210], [580, 210], 'right')]),
    'trend': _diagram(
        '<path d="M135 95H465M135 155H465M135 215H465M135 275H465" fill="none" stroke="#e5eaed"/>'
        '<path d="M135 85V275H465V85" fill="none" stroke="#8093a0"/>'
        '<g fill="#123b5d"><rect x="190" y="195" width="32" height="80"/>'
        '<rect x="284" y="140" width="32" height="135"/><rect x="378" y="160" width="32" height="115"/></g>'
        '<path d="M206 210L300 125L394 155" fill="none" stroke="#a74439" stroke-width="3"/>'
        '<g fill="white" stroke="#a74439" stroke-width="3"><circle cx="206" cy="210" r="4"/>'
        '<circle cx="300" cy="125" r="4"/><circle cx="394" cy="155" r="4"/></g>'
        '<g fill="#66717a" font-size="12" text-anchor="middle"><text x="206" y="296">7月</text>'
        '<text x="300" y="296">8月</text><text x="394" y="296">9月</text></g>', [
        _metric('revenue', [206, 235], [15, 180]), _metric('yield-growth', [394, 155], [585, 180], 'right'),
        _label('period', '周期', '按绑定的时间字段排列；月度与季度共用同一结构。', [300, 275], [300, 335], 'center'),
        _label('left-axis', '收入 · 万元', '左轴对应收入柱形。', [135, 95], [15, 35]),
        _label('right-axis', '变动率 · %', '右轴对应收益变动率折线。', [465, 95], [585, 35], 'right'),
    ]),
    'regions': _diagram(
        '<path d="M125 100H475M125 160H475M125 220H475M125 280H475" fill="none" stroke="#e5eaed"/>'
        '<path d="M125 90V280H475" fill="none" stroke="#8093a0"/>'
        '<g fill="#123b5d"><rect x="205" y="125" width="45" height="155"/>'
        '<rect x="350" y="165" width="45" height="115"/></g>'
        '<g fill="#66717a" font-size="12" text-anchor="middle">'
        '<text x="227" y="302">华东基地</text><text x="372" y="302">华南基地</text></g>', [
        _metric('revenue', [227, 200], [15, 130]),
        _label('region', '基地', '各柱分别对应一个基地。', [300, 280], [300, 340], 'center'),
        _label('axis', '收入 · 万元', '纵轴对应各基地营业收入。', [125, 100], [15, 35]),
    ]),
}
OPERATIONS = {
    'north-star': _diagram(_CARD + _FOOTER, [_metric('revenue', [250, 170], [20, 130]), _metric('budget', [225, 245], [20, 260])]),
    'budget-ring': _diagram('<circle cx="300" cy="175" r="80" fill="none" stroke="#dbe3e8" stroke-width="18"/><path d="M300 95A80 80 0 1 1 220 175" fill="none" stroke="#123b5d" stroke-width="18"/>', [
        _metric('attainment', [365, 220], [580, 220], 'right'), _metric('revenue', [300, 175], [20, 110]), _metric('budget', [220, 175], [20, 260])]),
    'budget-bullet': _diagram('<path d="M160 180H440" stroke="#dbe3e8" stroke-width="30"/><path d="M160 180H350" stroke="#123b5d" stroke-width="16"/><path d="M395 155V205" stroke="#051c2c" stroke-width="3"/>', [
        _metric('revenue', [260, 180], [20, 100]), _metric('budget', [395, 180], [580, 260], 'right')]),
    'period-compare': _diagram('<path d="M205 270V135H260V270Z" fill="#123b5d"/><path d="M340 270V180H395V270Z" fill="#8093a0"/>', [
        _metric('revenue', [230, 200], [20, 130]), _metric('baseline-revenue', [365, 220], [580, 220], 'right')]),
    'passenger-bars': _diagram(_AXIS + _BARS, [_metric('passengers', [295, 160], [20, 110]), _PERIOD]),
    'load-gauge': _diagram('<path d="M180 240A120 120 0 0 1 420 240" fill="none" stroke="#dbe3e8" stroke-width="20"/><path d="M180 240A120 120 0 0 1 360 136" fill="none" stroke="#123b5d" stroke-width="20"/><path d="M300 240L345 170" stroke="#051c2c" stroke-width="3"/>', [
        _metric('load-factor', [345, 170], [580, 120], 'right'), _metric('seats', [180, 240], [20, 240])]),
    'region-rank': _diagram('<path d="M170 80V270H440" fill="none" stroke="#8093a0"/><path d="M170 120H400V155H170ZM170 200H340V235H170Z" fill="#123b5d"/>', [
        _metric('revenue', [300, 137], [580, 120], 'right'), _label('bases', '基地', '每一横行对应一个基地，按收入排序。', [170, 215], [20, 220])]),
    'budget-actual': _diagram(_AXIS + '<path d="M200 280V120H225V280ZM330 280V150H355V280Z" fill="#8093a0"/><path d="M230 280V150H255V280ZM360 280V180H385V280Z" fill="#123b5d"/>', [
        _metric('budget', [210, 170], [20, 110]), _metric('revenue', [370, 220], [580, 220], 'right'), _REGION]),
    'passenger-trend': _diagram(_AXIS + _LINE, [_metric('passengers', [295, 110], [20, 110]), _PERIOD]),
}


def attach(operations, assets):
    """Include authored assets in the same edit batch as example components."""
    for operation in operations:
        if operation['op'] == 'put_component' and operation['id'] in assets:
            presentation(operation['value'], create=True)['structureDiagram'] = copy.deepcopy(assets[operation['id']])
