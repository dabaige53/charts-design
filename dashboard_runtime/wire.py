"""Opt-in lossless column encoding for repeated chart record keys."""
def compact_records(result):
    computed = result.get('computed', result.get('document', {}).get('computed', {}))
    for component in computed.get('components', {}).values():
        data = component.get('data', {})
        records = data.get('records')
        if not records or len(records) < 20:
            continue
        keys = list(records[0]['values'])
        if any(set(row) != {'category','series','values'} or list(row['values']) != keys for row in records):
            continue
        data['packedRecords'] = {'keys': keys, 'rows': [[row['category'], row['series'], *row['values'].values()] for row in records]}
        del data['records']
