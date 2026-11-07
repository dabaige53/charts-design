"""Named, role-aware dashboard layouts computed for every breakpoint.

Agents used to add components one at a time; each new card was stacked full
width, so most generated dashboards looked the same unless every coordinate
was written by hand. Templates arrange the same components into distinct
compositions (hero focus, bento mosaic, sidebar metrics, small multiples,
commentary beside charts, KPI walls) and stay consistent on tablet and phone.

Placement is plain data: x/y/w/h integers on the 12/8/4-column grids. A
template only orders and sizes existing components; it never changes content.
"""
from __future__ import annotations

COLS = {'desktop': 12, 'tablet': 8, 'mobile': 4}
# GridStack rows are 48 px. Charts need ~8 rows (~380 px) to keep their axes legible.
HEIGHT = {'kpi': 4, 'chart': 8, 'table': 8, 'text': 5}
# KPI shapes that carry two values or a wide bar read better with more width.
WIDE_KPIS = {'mc06', 'mc09'}
# On phones these shapes take the full row even in a 2-up KPI grid.
MOBILE_FULL_KPIS = WIDE_KPIS | {'mc10', 'mc11', 'mc13', 'mc14', 'mc15', 'mc16'}
# List and hero-with-takeaway cards need one more row; a KPI row takes its tallest card's height.
TALL_KPIS = {'mc15', 'mc16'}

TEMPLATES = {
    'executive': {
        'name': '经典三段式', 'nameEn': 'Executive three-tier',
        'description': 'KPI row(s), charts in two balanced columns, detail tables full width.',
        'bestFor': 'Monthly reviews with 3-4 headline metrics and 2-6 evidence charts.',
    },
    'focus': {
        'name': '主图聚焦', 'nameEn': 'Hero focus',
        'description': 'KPI strip, then the first chart full width and tall as the hero; supporting charts in three columns.',
        'bestFor': 'One decisive trend or comparison with several supporting views.',
    },
    'bento': {
        'name': '便当格拼贴', 'nameEn': 'Bento mosaic',
        'description': 'Charts alternate wide/narrow rows (8+4, 4+8, 6+6, 4+4+4) for a varied, magazine-like rhythm.',
        'bestFor': 'Mixed evidence of different importance; 4-9 charts.',
    },
    'sidebar': {
        'name': '侧栏指标', 'nameEn': 'Sidebar metrics',
        'description': 'KPIs stacked in a left column beside a wide chart column; tables full width below.',
        'bestFor': 'Monitoring pages where metrics stay visible next to long charts.',
    },
    'grid3': {
        'name': '三列小多图', 'nameEn': 'Small multiples',
        'description': 'Compact charts three per row for side-by-side comparison of the same measure across segments.',
        'bestFor': 'Regional/product splits of one measure; 3, 6 or 9 similar charts.',
    },
    'narrative': {
        'name': '图文叙事', 'nameEn': 'Narrative briefing',
        'description': 'Reading order top to bottom; a text component that follows a chart sits beside it as commentary (8+4).',
        'bestFor': 'Briefings where each chart carries a written takeaway.',
    },
    'scorecard': {
        'name': '指标墙', 'nameEn': 'KPI wall',
        'description': 'Dense KPI grid (up to 6 per row on desktop, 2 per row on phones), then compact charts.',
        'bestFor': 'Operations scorecards with 6-12 metrics and few charts.',
    },
}


def role(component: dict) -> str:
    kind = component.get('kind')
    if kind == 'legacy':
        return {'kpi': 'kpi', 'table': 'table'}.get(component.get('family', 'chart'), 'chart')
    if kind in ('kpi', 'table', 'text'):
        return kind
    return 'chart'  # chart and statistical


def kpi_type(component: dict) -> str:
    config = component.get('config', {}) if component.get('kind') == 'legacy' else component.get('presentation', {})
    return config.get('type', 'mc01') if isinstance(config, dict) else 'mc01'


def split(cols: int, count: int) -> list[int]:
    """Integer widths summing to cols, as even as possible (wider first)."""
    base, extra = divmod(cols, count)
    return [base + (1 if index < extra else 0) for index in range(count)]


def balanced(items: list, per_row: int) -> list[list]:
    """Rows of at most per_row items with sizes differing by at most one."""
    if not items:
        return []
    rows = -(-len(items) // per_row)
    sizes = split(len(items), rows)
    result, start = [], 0
    for size in sizes:
        result.append(items[start:start + size])
        start += size
    return result


class Flow:
    def __init__(self, cols: int):
        self.cols, self.y, self.placements = cols, 0, []

    def place(self, key, x, y, w, h):
        self.placements.append({'id': key, 'x': x, 'y': y, 'w': w, 'h': h})

    def row(self, keys, widths, height):
        x = 0
        for key, width in zip(keys, widths):
            self.place(key, x, self.y, width, height)
            x += width
        self.y += height

    def grid(self, keys, per_row, height):
        for chunk in balanced(keys, per_row):
            self.row(chunk, split(self.cols, len(chunk)), height)

    def full(self, keys, height):
        for key in keys:
            self.row([key], [self.cols], height)


def kpi_height(component: dict) -> int:
    return HEIGHT['kpi'] + (1 if kpi_type(component) in TALL_KPIS else 0)


def kpi_size(component: dict, per_row: int, breakpoint: str) -> int:
    kind = kpi_type(component)
    if breakpoint == 'mobile':
        return per_row if kind in MOBILE_FULL_KPIS else 1
    return 2 if kind in WIDE_KPIS and per_row >= 3 else 1


def kpi_rows(flow: Flow, kpis: list, per_row: int, components: dict, breakpoint: str = 'desktop'):
    """Balanced KPI rows; wide shapes claim two slots (the full row on phones)."""
    if not kpis:
        return
    sizes = {key: kpi_size(components[key], per_row, breakpoint) for key in kpis}
    if all(size == 1 for size in sizes.values()):
        rows = [[(key, 1) for key in chunk] for chunk in balanced(kpis, per_row)]
    else:
        rows, current, weight = [], [], 0
        for key in kpis:
            size = sizes[key]
            if current and weight + size > per_row:
                rows.append(current)
                current, weight = [], 0
            current.append((key, size))
            weight += size
        if current:
            rows.append(current)
    for row_items in rows:
        units = sum(size for _, size in row_items)
        unit_widths = split(flow.cols, units)
        widths, index = [], 0
        for _, size in row_items:
            widths.append(sum(unit_widths[index:index + size]))
            index += size
        flow.row([key for key, _ in row_items], widths, max(kpi_height(components[key]) for key, _ in row_items))


def sequence_rows(flow: Flow, items: list, chart_per_row: int, chart_height: int, roles: dict):
    """Charts in balanced rows; text and tables break the row and span the width."""
    pending = []

    def flush():
        if pending:
            flow.grid(list(pending), chart_per_row, chart_height)
            pending.clear()
    for key in items:
        if roles[key] == 'chart':
            pending.append(key)
        else:
            flush()
            flow.full([key], HEIGHT[roles[key]])
    flush()


def compute_layout(manifest: dict, template: str, order=None) -> dict:
    """Return {breakpoint: placements} for every component in the manifest."""
    if template not in TEMPLATES:
        raise ValueError(f'Unknown layout template: {template}')
    components = manifest['components']
    ordered = [key for key in (order or []) if key in components]
    ordered += [key for key in components if key not in ordered]
    roles = {key: role(components[key]) for key in ordered}
    kpis = [key for key in ordered if roles[key] == 'kpi']
    body = [key for key in ordered if roles[key] in ('chart', 'text')]
    tables = [key for key in ordered if roles[key] == 'table']
    charts = [key for key in body if roles[key] == 'chart']
    result = {}
    for breakpoint, cols in COLS.items():
        flow = Flow(cols)
        desktop, tablet = breakpoint == 'desktop', breakpoint == 'tablet'
        kpi_per_row = 4 if desktop else 2 if tablet else (2 if template == 'scorecard' else 1)
        if template == 'scorecard':
            kpi_per_row = 6 if desktop else 4 if tablet else 2
        if template == 'sidebar' and desktop and kpis:
            # Left metric column (3/12), wide chart column (9/12).
            top = 0
            for key in kpis:
                flow.place(key, 0, top, 3, kpi_height(components[key]))
                top += kpi_height(components[key])
            y = 0
            for key in body:
                height = HEIGHT[roles[key]]
                flow.place(key, 3, y, 9, height)
                y += height
            flow.y = max(top, y)
            flow.full(tables, HEIGHT['table'])
            result[breakpoint] = flow.placements
            continue
        kpi_rows(flow, kpis, kpi_per_row, components, breakpoint)
        if template == 'focus' and charts:
            hero = charts[0]
            rest = [key for key in body if key != hero]
            flow.full([hero], 10 if cols > 4 else HEIGHT['chart'])
            sequence_rows(flow, rest, 3 if desktop else 2 if tablet else 1, HEIGHT['chart'], roles)
        elif template == 'bento' and cols > 4:
            patterns = ([[8, 4], [4, 8], [6, 6], [4, 4, 4]] if desktop else [[8], [4, 4]])
            pattern_index, pending = 0, []

            def flush_bento():
                nonlocal pattern_index
                index = 0
                while index < len(pending):
                    widths = patterns[pattern_index % len(patterns)]
                    chunk = pending[index:index + len(widths)]
                    if len(chunk) < len(widths):
                        widths = split(cols, len(chunk))
                    flow.row(chunk, widths, HEIGHT['chart'])
                    index += len(chunk)
                    pattern_index += 1
                pending.clear()
            for key in body:
                if roles[key] == 'chart':
                    pending.append(key)
                else:
                    flush_bento()
                    flow.full([key], HEIGHT[roles[key]])
            flush_bento()
        elif template == 'narrative' and cols > 4:
            index = 0
            while index < len(body):
                key = body[index]
                following = body[index + 1] if index + 1 < len(body) else None
                if roles[key] == 'chart' and following and roles[following] == 'text':
                    wide = 8 if desktop else 5
                    flow.row([key, following], [wide, cols - wide], HEIGHT['chart'])
                    index += 2
                    continue
                flow.full([key], HEIGHT[roles[key]])
                index += 1
        else:
            per_row = {'executive': 2, 'focus': 3, 'grid3': 3, 'scorecard': 3, 'sidebar': 2, 'bento': 2, 'narrative': 1}[template]
            if tablet:
                per_row = 2 if template in ('grid3', 'scorecard') else 1
            elif not desktop:
                per_row = 1
            sequence_rows(flow, body, per_row, HEIGHT['chart'], roles)
        flow.full(tables, HEIGHT['table'])
        result[breakpoint] = flow.placements
    return result


def auto_place(manifest: dict, key: str, component: dict):
    """Append one new component without re-flowing existing cards.

    KPIs join a trailing row of KPIs; charts pair up two per desktop row;
    tables and text span the width. Rows stay homogeneous so a KPI never
    lands beside a chart.
    """
    kind = role(component)
    for breakpoint, cols in COLS.items():
        layout = manifest['layout'][breakpoint]
        height = kpi_height(component) if kind == 'kpi' else HEIGHT[kind]
        if kind == 'kpi':
            width = {'desktop': 3, 'tablet': 4, 'mobile': 4}[breakpoint]
            if kpi_type(component) in WIDE_KPIS and breakpoint == 'desktop':
                width = 6
        elif kind == 'chart':
            width = {'desktop': 6, 'tablet': 8, 'mobile': 4}[breakpoint]
        else:
            width = cols
        bottom = max((p['y'] + p['h'] for p in layout), default=0)
        placement = {'id': key, 'x': 0, 'y': bottom, 'w': width, 'h': height}
        if layout and width < cols:
            top = max(p['y'] for p in layout)
            band = [p for p in layout if p['y'] == top]
            same = all(p['id'] in manifest['components'] and role(manifest['components'][p['id']]) == kind and p['h'] == height
                       for p in band)
            used = max(p['x'] + p['w'] for p in band)
            candidate = {'id': key, 'x': used, 'y': top, 'w': width, 'h': height}
            if same and used + width <= cols and not any(overlaps(candidate, p) for p in layout):
                placement = candidate
        layout.append(placement)


def overlaps(a: dict, b: dict) -> bool:
    return a['x'] < b['x'] + b['w'] and b['x'] < a['x'] + a['w'] and a['y'] < b['y'] + b['h'] and b['y'] < a['y'] + a['h']


def templates_catalog() -> dict:
    return {'templates': [{'id': key, **value} for key, value in TEMPLATES.items()],
            'usage': {'operation': {'op': 'apply_layout_template', 'template': 'bento', 'order': ['optional component ids in reading order']},
                      'notes': ['The template is applied after every other operation in the same patch, so components created in that patch are included.',
                                'The choice is saved as manifest.layoutTemplate; later put_component/remove_component patches re-flow the template automatically.',
                                'An explicit set_layout (including dragging cards in the editor) replaces the template with the manual layout.',
                                'Vary the composition with the content: do not default every dashboard to executive.']}}
