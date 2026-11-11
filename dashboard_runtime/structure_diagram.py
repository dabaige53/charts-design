"""Saved, data-independent structure diagrams shared by every renderer."""
import copy
import math
import re
import xml.etree.ElementTree as ET

TAGS = {'svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline',
        'polygon', 'text', 'tspan', 'title', 'desc'}
ATTRS = {'x', 'y', 'x1', 'y1', 'x2', 'y2', 'cx', 'cy', 'r', 'rx', 'ry',
         'width', 'height', 'd', 'points', 'fill', 'stroke', 'stroke-width',
         'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'opacity',
         'fill-opacity', 'stroke-opacity', 'fill-rule', 'transform',
         'font-size', 'font-weight', 'text-anchor', 'dominant-baseline'}


def presentation(component, *, create=False):
    from .model import require
    owner = component.setdefault('config', {}) if component.get('kind') == 'legacy' else component
    require(isinstance(owner, dict), 'Component config must be an object')
    return owner.setdefault('presentation', {}) if create else owner.get('presentation', {})


def sanitize_svg(svg, view_box):
    from .model import require
    require(isinstance(svg, str) and 0 < len(svg) <= 100000, 'structureDiagram.svg must contain 1–100000 characters')
    require(not re.search(r'<!\s*(DOCTYPE|ENTITY)', svg, re.I), 'SVG declarations and entities are forbidden')
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        require(False, f'Invalid structureDiagram SVG: {exc}')
        raise
    require(root.tag in ('svg', '{http://www.w3.org/2000/svg}svg'), 'structureDiagram.svg must have an SVG root')
    require(sum(1 for _ in root.iter()) <= 2000, 'Structure SVG allows at most 2000 elements')

    def clean(node):
        node.tag = node.tag.removeprefix('{http://www.w3.org/2000/svg}')
        node.attrib = {key: value for key, value in node.attrib.items()
                       if key in ATTRS and not re.search(r'url\s*\(|[<>&\\]|://', value, re.I)}
        for child in list(node):
            tag = child.tag.removeprefix('{http://www.w3.org/2000/svg}')
            if tag not in TAGS or tag == 'svg':
                node.remove(child)
            else:
                clean(child)
    clean(root)
    root.set('xmlns', 'http://www.w3.org/2000/svg')
    root.set('viewBox', ' '.join(str(v) for v in view_box))
    return ET.tostring(root, encoding='unicode')


def normalize(diagram):
    from .model import identifier, require
    require(isinstance(diagram, dict), 'structureDiagram must be an object')
    require(diagram.get('version') == 1, 'structureDiagram.version must be 1')
    box = diagram.get('viewBox')
    require(isinstance(box, list) and len(box) == 4 and
            all(type(v) in (int, float) and math.isfinite(v) for v in box),
            'structureDiagram.viewBox must contain four finite numbers')
    require(box[:2] == [0, 0] and 0 < box[2] <= 10000 and 0 < box[3] <= 10000,
            'structureDiagram.viewBox must be [0, 0, width, height], dimensions 0–10000')
    annotations = diagram.get('annotations')
    require(isinstance(annotations, list) and 1 <= len(annotations) <= 32,
            'structureDiagram requires 1–32 annotations')
    seen = set()
    for item in annotations:
        require(isinstance(item, dict), 'Structure annotation must be an object')
        key = identifier(item.get('id'), 'annotation id')
        require(key not in seen, 'Structure annotation IDs must be unique')
        seen.add(key)
        for point in ('anchor', 'label'):
            value = item.get(point)
            require(isinstance(value, list) and len(value) == 2 and
                    all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= box[i + 2]
                        for i, v in enumerate(value)), f'{key}.{point} must be inside viewBox')
        require(item.get('align', 'center') in ('left', 'center', 'right'), f'{key}: invalid label alignment')
        if 'metricId' in item:
            identifier(item['metricId'], 'metric reference')
            require('name' not in item and 'description' not in item,
                    f'{key}: metric references must not duplicate name or description')
        else:
            require(isinstance(item.get('name'), str) and 0 < len(item['name'].strip()) <= 120,
                    f'{key}: annotation name required (1–120 characters)')
        require(isinstance(item.get('description', ''), str) and len(item.get('description', '')) <= 2000,
                f'{key}: description must be at most 2000 characters')
    require(diagram.get('status', 'ready') in ('ready', 'stale'), 'Invalid structureDiagram status')
    return {**copy.deepcopy(diagram), 'svg': sanitize_svg(diagram.get('svg'), box),
            'status': diagram.get('status', 'ready')}


def update(previous, component):
    """Explicit submission confirms a diagram; omission retains a stale copy."""
    target = presentation(component, create=True)
    from .model import require
    require(isinstance(target, dict), 'Presentation must be an object')
    if 'structureDiagram' in target:
        target['structureDiagram'] = {**normalize(target['structureDiagram']), 'status': 'ready'}
    elif previous:
        old = presentation(previous).get('structureDiagram')
        if old:
            before, after = copy.deepcopy(previous), copy.deepcopy(component)
            presentation(before, create=True).pop('structureDiagram', None)
            presentation(after, create=True).pop('structureDiagram', None)
            target['structureDiagram'] = {**copy.deepcopy(old), 'status': old.get('status', 'ready') if before == after else 'stale'}


def invalidate(component):
    diagram = presentation(component).get('structureDiagram')
    if diagram:
        diagram['status'] = 'stale'


def validate(component):
    from .model import require
    value = presentation(component)
    require(isinstance(value, dict), 'Presentation must be an object')
    if 'structureDiagram' in value:
        value['structureDiagram'] = normalize(value['structureDiagram'])


def schema():
    point = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 2, 'maxItems': 2}
    return {
        'type': 'object', 'required': ['version', 'viewBox', 'svg', 'annotations'],
        'description': 'Data-independent static structure SVG. Submit with the component; omitted diagrams become stale after declaration edits. Same contract for every renderer.',
        'properties': {
            'version': {'const': 1},
            'viewBox': {'type': 'array', 'items': {'type': 'number'}, 'minItems': 4, 'maxItems': 4,
                        'description': '[0,0,width,height], positive dimensions up to 10000. All points use this space.'},
            'svg': {'type': 'string', 'minLength': 1, 'maxLength': 100000,
                    'description': 'Static SVG shapes and text only. No business values, scripts, events, styles, external resources, defs or URL paints. Reserve space for labels.'},
            'annotations': {'type': 'array', 'minItems': 1, 'maxItems': 32, 'items': {
                'type': 'object', 'required': ['id', 'anchor', 'label'],
                'properties': {
                    'id': {'type': 'string', 'pattern': '^[a-zA-Z][a-zA-Z0-9_-]{0,79}$'},
                    'anchor': {**point, 'description': 'Connection point on the graphic, inside viewBox.'},
                    'label': {**point, 'description': 'Label position inside viewBox; reserve space to avoid overlapping labels.'},
                    'align': {'enum': ['left', 'center', 'right'], 'default': 'center',
                              'description': 'Text alignment at label point. Left extends right; right extends left.'},
                    'metricId': {'type': 'string', 'description': 'Canonical metric ID; name and definition are resolved live. Do not duplicate name/description.'},
                    'name': {'type': 'string', 'minLength': 1, 'maxLength': 120},
                    'description': {'type': 'string', 'maxLength': 2000},
                },
                'oneOf': [{'required': ['metricId'], 'not': {'anyOf': [{'required': ['name']}, {'required': ['description']}]}},
                          {'required': ['name'], 'not': {'required': ['metricId']}}],
            }},
        },
    }
