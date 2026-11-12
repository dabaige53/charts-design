-- Reuse persisted deletion jobs for document objects abandoned between saves.
-- The same project lock guards commits, reference checks and cleanup claims.
DO $migration$
DECLARE definition text;
BEGIN
    definition := pg_get_functiondef('public.charts_assets(text,text,jsonb)'::regprocedure);
    definition := replace(definition, 'objbytes bigint:=0;',
        'cleanup_project text; objbytes bigint:=0;');
    definition := replace(definition, '    IF action=''pending'' THEN', $collector$
    IF action='collect_drafts' THEN
        FOR cleanup_project IN
            SELECT DISTINCT o.project FROM charts.asset_objects o
            WHERE o.kind='document' AND o.state='ready'
              AND o.created_at < now()-interval '1 hour'
            ORDER BY o.project
        LOOP
            PERFORM pg_advisory_xact_lock(hashtextextended('charts:'||cleanup_project,0));
            FOR obj IN
                SELECT o.* FROM charts.asset_objects o
                WHERE o.project=cleanup_project AND o.kind='document' AND o.state='ready'
                  AND o.created_at < now()-interval '1 hour'
                  AND NOT EXISTS (SELECT 1 FROM charts.asset_documents(cleanup_project) d
                                  WHERE d.document->>'cosObject'=o.id)
            LOOP
                UPDATE charts.asset_objects o SET state='deleting'
                    WHERE o.project=cleanup_project AND o.id=obj.id;
                INSERT INTO charts.delete_jobs(project,id,board,revision,state,plan)
                    VALUES(cleanup_project,'orphan-'||obj.id,'',0,'deleting',
                        jsonb_build_object('revision',0,'objects',jsonb_build_array(
                            jsonb_build_object('id',obj.id,'prefix',obj.prefix)),
                            'shares','[]'::jsonb,'datasets','[]'::jsonb));
                UPDATE charts.asset_state s SET epoch=epoch+1 WHERE s.project=cleanup_project;
            END LOOP;
        END LOOP;
        RETURN 'true';
    END IF;
    IF action='pending' THEN$collector$);
    IF position('IF action=''collect_drafts'' THEN' IN definition)=0 THEN
        RAISE EXCEPTION 'Asset function differs; inspect before adding draft cleanup';
    END IF;
    EXECUTE definition;
END $migration$;
NOTIFY pgrst,'reload schema';
