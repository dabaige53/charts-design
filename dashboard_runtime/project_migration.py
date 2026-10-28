"""Explicit non-destructive migration from a legacy runtime to project assets."""
import json
from .store import Store
from .project import ProjectStore, write_json
from .model import require, utcnow


def migrate_project(source_root, project_root, runtime_root, board_ids, apply=False):
    source = Store(source_root)
    inventory=[]
    versions={}
    for board in board_ids:
        doc=source.get(board, hydrate=False)
        with source.connect() as db:
            history=[dict(row) for row in db.execute('SELECT * FROM revisions WHERE board_id=? ORDER BY revision', (board,))]
        for value in [doc, *[json.loads(row['document']) for row in history]]:
            for ref in [*value['snapshot'].get('datasetRefs',{}).values(), *value['snapshot'].get('componentDataRefs',{}).values()]:
                versions[ref['version']]=ref
        inventory.append({'board':board,'revision':doc['revision'],'components':len(doc['manifest']['components']),'annotations':len(doc['manifest'].get('annotations',[])),'checkpoints':len(history)})
    summary={'boards':inventory,'dataVersions':len(versions),'rows':sum(r['rowCount'] for r in versions.values()),'applied':False}
    if not apply:
        return summary
    target=ProjectStore(project_root,runtime_root)
    require(not any(r['id'] in board_ids for r in target.list()), 'Destination already contains a selected dashboard')
    for ref in versions.values():
        # Stream only referenced versions. Preserve column order and sparse fields.
        fields={key:ref['fields'][key] for key in ref.get('fieldOrder',ref['fields'])}
        copied=target.data.import_rows(source.data.iter_rows(ref), fields)
        require(copied==ref, 'Migrated dataset differs from source')
    for board in board_ids:
        doc=source.get(board,hydrate=False)
        with source.connect() as old, target.connect() as db:
            histories=list(old.execute('SELECT * FROM revisions WHERE board_id=? ORDER BY revision',(board,)))
            for item in histories:
                historic=json.loads(item['document'])
                notes=historic['manifest'].pop('annotations',[])
                db.execute('INSERT INTO annotation_events VALUES(?,?,?,?)',(board,item['created_at'],item['revision'],json.dumps(notes,ensure_ascii=False)))
                db.execute('INSERT INTO revisions VALUES(?,?,?,?,?)',(board,item['revision'],item['created_at'],item['action'],json.dumps(historic,ensure_ascii=False)))
            notes=doc['manifest'].pop('annotations',[])
            target._save_notes(db,doc,notes)
            db.execute('INSERT INTO boards VALUES(?,?,?)',(board,doc['revision'],json.dumps(doc,ensure_ascii=False)))
        target._files(board)
        restored=target.get(board,hydrate=False)
        expected=source.get(board,hydrate=False)
        require(restored['manifest']['components']==expected['manifest']['components'], 'Component migration mismatch')
        require(restored['snapshot']==expected['snapshot'], 'Data reference migration mismatch')
        require([n['id'] for n in restored['manifest']['annotations']]==[n['id'] for n in expected['manifest'].get('annotations',[])], 'Annotation migration mismatch')
    summary['applied']=True
    write_json(target.project_root/'dashboards/migration-report.json',summary)
    return summary
