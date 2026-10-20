"""Bounded data-only Seaborn rendering. Never accepts code, paths or arbitrary kwargs."""
from __future__ import annotations
import base64
import copy
import hashlib
import io
import json
import threading
from functools import lru_cache
from .model import DashboardError, require, field

PLOT_TYPES = ('histogram', 'boxplot', 'regression')
MAX_STAT_ROWS = 5000
_LOCK = threading.RLock()


def validate_statistical(doc, component):
    require(set(component) <= {'kind','title','subtitle','datasetId','plot','analysis'}, 'Unknown statistical component field')
    require('subtitle' not in component or isinstance(component['subtitle'], str) and len(component['subtitle']) <= 1000, 'Statistical subtitle must be text up to 1000 characters')
    ds = component.get('datasetId')
    require(isinstance(ds, str) and ds in doc['manifest']['datasets'], 'Statistical dataset not found')
    meta = doc['manifest']['datasets'][ds]
    spec = component.get('plot')
    require(isinstance(spec, dict), 'Statistical plot must be an object')
    kind = spec.get('type')
    require(kind in PLOT_TYPES, 'Unsupported statistical plot type')
    allowed = {'type','x','bins'} if kind == 'histogram' else {'type','x','y'}
    require(set(spec) <= allowed, 'Unknown statistical plot option; executable code and arbitrary kwargs are forbidden')
    field(meta, spec.get('x'), kind != 'boxplot')
    if kind == 'histogram':
        require(type(spec.get('bins', 20)) is int and 1 <= spec.get('bins', 20) <= 100, 'Histogram bins must be an integer from 1 to 100')
    else:
        field(meta, spec.get('y'), True)
    if kind == 'boxplot':
        require(meta['fields'][spec['x']]['type'] in ('string','boolean'), 'Boxplot x must be a categorical string or boolean field')
    analysis = component.get('analysis')
    require(isinstance(analysis, dict) and set(analysis) == {'definition','unit'}, 'Statistical analysis requires exactly definition and unit')
    require(isinstance(analysis['definition'], str) and 1 <= len(analysis['definition']) <= 1000, 'Supply the observation grain and measurement definition (1–1000 characters)')
    require(isinstance(analysis['unit'], str) and len(analysis['unit']) <= 100, 'Unit must be text up to 100 characters')
    if ds not in doc['snapshot']['datasets']:
        ref = doc['snapshot'].get('datasetRefs', {}).get(ds)
        require(ref is not None and ref['rowCount'] <= MAX_STAT_ROWS, 'Statistical plots accept at most 5000 raw rows')
        return []  # Store validates the actual immutable observations before saving.
    rows = doc['snapshot']['datasets'][ds]
    require(len(rows) <= MAX_STAT_ROWS, 'Statistical plots accept at most 5000 raw rows')
    used = [r for r in rows if all(r.get(k) is not None for k in (spec['x'],) + ((spec['y'],) if 'y' in spec else ()))]
    require(used, 'Statistical plot requires at least one complete observation')
    for r in used:
        for k in (spec['x'],) + ((spec['y'],) if 'y' in spec else ()):
            v = r[k]
            require(not isinstance(v, str) or len(v) <= 100, 'Statistical category labels are limited to 100 characters')
            if isinstance(v, (int, float)):
                require(abs(v) <= 1e12, 'Statistical numeric values must be within ±1e12')
    if kind == 'boxplot':
        require(len({r[spec['x']] for r in used}) <= 20, 'Boxplot accepts at most 20 categories')
    if kind == 'regression':
        require(len(used) >= 3 and len({r[spec['x']] for r in used}) >= 2, 'Regression needs at least 3 complete observations and distinct x values')
    return used


def render_statistical(doc, component_id, format='svg'):
    require(format in ('svg','png'), 'Statistical format must be svg or png')
    c = doc['manifest']['components'].get(component_id)
    require(c is not None and c['kind'] == 'statistical', 'Statistical component not found')
    assert c is not None
    used = validate_statistical(doc, c)
    meta = doc['manifest']['datasets'][c['datasetId']]
    source = doc['manifest']['sources'][meta['sourceId']]
    columns = [c['plot']['x']] + ([c['plot']['y']] if 'y' in c['plot'] else [])
    payload = {'component': c, 'rows': [{key: row[key] for key in columns} for row in used], 'fields': {key: {'label': str(meta['fields'][key].get('label',key))[:200]} for key in columns}}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False)
    encoded, versions = _render(raw, format)
    dropped = len(doc['snapshot']['datasets'][c['datasetId']]) - len(used)
    methods = {'histogram': f"Counts; {c['plot'].get('bins',20)} equal-width bins", 'boxplot': 'Median, quartiles, 1.5×IQR whiskers; outliers shown', 'regression': 'Ordinary least-squares line; confidence interval not computed; association does not establish causation'}
    caption = f"{methods[c['plot']['type']]}. Raw observations; n={len(used)}; missing observations omitted={dropped}. Definition: {c['analysis']['definition']}. Unit: {c['analysis']['unit'] or 'unitless'}. Source: {source.get('name',meta['sourceId'])} ({source['kind']}; {source.get('verification','supplied')}, not certified). Snapshot: {doc['snapshot']['updatedAt']}."
    return {'dataUri': f"data:image/{'svg+xml' if format == 'svg' else 'png'};base64,{encoded}", 'mimeType': 'image/svg+xml' if format == 'svg' else 'image/png', 'caption': caption, 'provenance': {'datasetId': c['datasetId'], 'sourceId': meta['sourceId'], 'source': copy.deepcopy(source), 'snapshotUpdatedAt': doc['snapshot']['updatedAt'], 'inputSha256': hashlib.sha256(raw.encode()).hexdigest(), 'rowsUsed': len(used), 'rowsDropped': dropped, 'versions': versions, 'aggregation': 'none; raw observations'}}


@lru_cache(maxsize=24)
def _render(raw, format):
    with _LOCK:
        try:
            import matplotlib as mpl
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            import seaborn as sns
            import pandas as pd
            from matplotlib import font_manager
        except ImportError as exc:
            raise DashboardError('SEABORN_NOT_INSTALLED', 'Install the optional statistical backend: pip install "charts-design-runtime[statistics]"', 503) from exc
        value = json.loads(raw)
        c, rows = value['component'], value['rows']
        p = c['plot']
        # Disable external TeX and math interpretation. SVG paths avoid font dependencies in viewers.
        with mpl.rc_context({'text.usetex': False, 'text.parse_math': False, 'svg.fonttype':'path', 'svg.hashsalt':'charts-design-statistical', 'font.family':(['Noto Serif CJK SC','DejaVu Sans'] if any(f.name == 'Noto Serif CJK SC' for f in font_manager.fontManager.ttflist) else ['DejaVu Sans']), 'axes.spines.top':False, 'axes.spines.right':False}):
            fig = Figure(figsize=(8,4.5), dpi=144, facecolor='white')
            FigureCanvasAgg(fig)
            ax = fig.subplots()
            data = pd.DataFrame(rows)
            try:
                if p['type'] == 'histogram':
                    sns.histplot(data=data, x=p['x'], bins=p.get('bins',20), stat='count', color='#555555', ax=ax)
                elif p['type'] == 'boxplot':
                    sns.boxplot(data=data, x=p['x'], y=p['y'], color='#aaaaaa', whis=1.5, fliersize=3, ax=ax)
                else:
                    sns.scatterplot(data=data, x=p['x'], y=p['y'], color='#444444', s=22, alpha=0.65, ax=ax)
                    line_x, line_y = regression_line(data[p['x']].to_numpy(), data[p['y']].to_numpy())
                    ax.plot(line_x, line_y, color='#444444', linewidth=1.5)
                def label(key):
                    return str(value['fields'][key].get('label', key))[:200]
                unit = f" ({c['analysis']['unit']})" if c['analysis']['unit'] else ''
                ax.set_xlabel(label(p['x']) + (unit if p['type']=='histogram' else ''))
                ax.set_ylabel('Count' if p['type']=='histogram' else label(p['y']) + unit)
                ax.grid(axis='y', alpha=0.2)
                fig.tight_layout()
                stream = io.BytesIO()
                fig.savefig(stream, format=format, metadata={'Date':None} if format=='svg' else {})
                encoded = base64.b64encode(stream.getvalue()).decode('ascii')
            except (ValueError, TypeError, OverflowError) as exc:
                raise DashboardError('STATISTICAL_RENDER_FAILED', 'Statistical rendering failed; review the declared values and fields') from exc
            finally:
                fig.clear()
        return encoded, {'seaborn':sns.__version__, 'matplotlib':mpl.__version__}


def statistical_artifacts(doc):
    artifacts = {}
    for key, component in doc['manifest']['components'].items():
        if component['kind'] == 'statistical':
            try:
                artifacts[key] = render_statistical(doc, key)
            except DashboardError as exc:
                artifacts[key] = {'error':str(exc), 'code':exc.code}
    return artifacts


def statistical_declarations():
    return {'componentSchema': statistical_schema(), 'backend':'seaborn', 'types': list(PLOT_TYPES), 'component': {'kind':'statistical','title':'Measurement distribution','datasetId':'observations','plot':{'type':'histogram','x':'value','bins':20},'analysis':{'definition':'One row per observed item; value is its measured quantity.','unit':'units'}}, 'rules':['Optional install: pip install "charts-design-runtime[statistics]".', 'Histogram requires numeric x and optional integer bins 1–100; boxplot requires categorical x and numeric y; regression requires numeric x and y, at least 3 complete rows and distinct x values.', 'Raw observations, never metric aggregates. analysis.definition describes grain and meaning; analysis.unit labels the measured axis. Include x units in dataset field labels for regression.', 'At most 5000 rows and 20 boxplot categories. Null/missing observations are omitted and counted. No interactive filters for statistical components in this version.', 'Static SVG in preview and offline export; statistical_render also supports PNG. No paths, URLs, Python code, arbitrary kwargs, or automatic hypothesis tests. Regression uses OLS without a confidence interval.', 'Use ordinary Markdown chart fences. Derived artifacts are not persisted in the canonical document; rendering keys include data and specification.']}


def statistical_schema():
    field_name = {'type':'string','minLength':1,'maxLength':199}
    variants=[]
    for kind in PLOT_TYPES:
        properties={'type':{'const':kind},'x':field_name}
        if kind=='histogram':
            properties['bins']={'type':'integer','minimum':1,'maximum':100,'default':20}
        else:
            properties['y']=field_name
        variants.append({'type':'object','additionalProperties':False,'properties':properties,'required':['type','x']+([] if kind=='histogram' else ['y'])})
    return {'type':'object','additionalProperties':False,'required':['kind','title','datasetId','plot','analysis'],'properties':{
        'kind':{'const':'statistical'},'title':{'type':'string','maxLength':240},'subtitle':{'type':'string','maxLength':1000},
        'datasetId':{'type':'string'},'plot':{'oneOf':variants},
        'analysis':{'type':'object','additionalProperties':False,'required':['definition','unit'],'properties':{'definition':{'type':'string','minLength':1,'maxLength':1000},'unit':{'type':'string','maxLength':100}}}}}


def regression_line(x, y):
    """Centered/scaled OLS avoids the large-offset pinv([1,x]) instability."""
    import numpy as np
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    dx = x-x[0]
    dy = y-y[0]
    center_x, center_y = dx.mean(), dy.mean()
    scale = np.max(np.abs(dx-center_x))
    require(scale > 0, 'Regression requires distinct x values')
    z = (dx-center_x)/scale
    slope = np.dot(z,dy-center_y)/np.dot(z,z)
    line_x = np.array([x.min(),x.max()])
    line_y = y[0]+(center_y+slope*((np.array([dx.min(),dx.max()])-center_x)/scale))
    require(np.isfinite(line_y).all(), 'Regression produced non-finite predictions')
    return line_x, line_y
