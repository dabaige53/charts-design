"""Bounded field-level changes to business semantics; no dataset rows."""

def semantic_diff(before, after):
    changes = []
    def compare(path, old, new):
        if old == new:
            return
        if isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(old.keys() | new.keys()):
                compare(path + [key], old.get(key), new.get(key))
        else:
            changes.append({'path': path, 'change': 'removed' if new is None else 'added' if old is None else 'changed'})
    a, b = before['manifest'], after['manifest']
    compare(['metrics'], a.get('metrics', {}), b.get('metrics', {}))
    compare(['filters'], a.get('filters', []), b.get('filters', []))
    for cid in sorted(a.get('components', {}).keys() | b.get('components', {}).keys()):
        old, new = a.get('components', {}).get(cid), b.get('components', {}).get(cid)
        if old is None or new is None:
            compare(['components', cid], bool(old) or None, bool(new) or None)
            continue
        for field in ('binding', 'datasetId', 'measures', 'analysis'):
            compare(['components', cid, field], old.get(field), new.get(field))
        for field in ('explanation', 'presentation', 'encoding'):
            compare(['components', cid, 'config', field], old.get('config', {}).get(field), new.get('config', {}).get(field))
    return {'count': len(changes), 'changes': changes[:200], 'truncated': len(changes) > 200}
