"""Discoverable operation documentation; the Python validator is authoritative."""
from .service import TOOLS
CONTRACT = {
    'schemaVersion': 2,
    'tools': {key: {'description': value[0], 'inputSchema': value[1]} for key, value in TOOLS.items()},
    'operations': {
        'put_source': {'id': 'source id', 'value': {'kind': 'file|query|fixture|declared', 'name': 'source description'}},
        'put_dataset': {'id': 'dataset id', 'meta': {'fields': {'field': {'type': 'string|number|date|boolean', 'label': 'Display name'}}, 'sourceId': 'source id'}, 'rows': [{'field': 'value'}]},
        'put_metric': {'id': 'metric id', 'value': {'datasetId': 'dataset id', 'field': 'numeric field', 'aggregation': 'sum|avg|min|max|count|ratio', 'label': 'Name', 'unit': '', 'definition': 'Business definition', 'status': 'unverified|reviewed'}},
        'put_component': {'id': 'component id', 'value': {'kind': 'chart|kpi|table|text|legacy', 'title': 'Title', 'datasetId': 'dataset id', 'x': 'category field', 'measures': ['metric id'], 'chartType': 'bar|line|area|pie|scatter|heatmap|funnel|waterfall'}},
        'remove_component': {'id': 'component id'},
        'set_chart': {'id': 'component id', 'chartType': 'compatible chart type'},
        'set_layout': {'breakpoint': 'desktop|tablet|mobile', 'value': [{'id': 'component id', 'x': 0, 'y': 0, 'w': 6, 'h': 6}]},
        'set_filters': {'value': [{'id': 'region', 'field': 'region', 'op': 'in|range', 'values': [], 'componentIds': ['component id']}]},
        'set_title': {'value': 'Dashboard title'}, 'set_theme': {'value': 'light|dark'},
        'set_status': {'value': 'ready|partial|blocked|fixture'}
    },
    'rules': [
        'Read dashboard_get before mutation and supply its expectedRevision.',
        'Every operation object must include its op name.',
        'Operations are atomic. References are checked after the entire batch.',
        'Dataset rows live only in snapshot.datasets. Metadata lives in manifest.datasets.',
        'Metric aggregation=ratio requires numerator and denominator numeric fields; sum(numerator)/sum(denominator), never avg(ratios).',
        'format=percent requires scale=fraction. Raw 0.98 displays as 98%.',
        'Waterfall requires metric semantic=delta and aggregation=sum.',
        'All breakpoints must place each component exactly once; placement is automatically added for new components.',
        'CLI writes to files; MCP never accepts arbitrary filesystem paths.',
        'Legacy chart configs require explicit data and presentation from the existing catalog.',
        'Source verification supplied is not proof of execution or certification.'
    ]
}
