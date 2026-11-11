-- Qualify local PL/pgSQL variables through the explicit block label.
CREATE OR REPLACE FUNCTION public.charts_runtime(action text, project text DEFAULT '', payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, charts
AS $$
#variable_conflict use_variable
<<runtime>>
DECLARE
    b charts.boards%ROWTYPE;
    r charts.revisions%ROWTYPE;
    result jsonb;
    board text := payload->>'board';
    expected bigint := (payload->>'expected')::bigint;
    doc jsonb := payload->'document';
BEGIN
    -- CloudBase's gateway may not enforce function EXECUTE grants. Check the
    -- signed JWT role inside the definer function before accessing any state.
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'FORBIDDEN' USING ERRCODE='42501';
    END IF;
    -- Serialize a project's state changes across instances. The lock is released
    -- at transaction end; reads remain MVCC reads.
    IF action IN ('ensure','create','commit','checkpoint','begin','label','revoke','data_finish','file_put') THEN
        PERFORM pg_advisory_xact_lock(hashtextextended('charts:' || project, 0));
    END IF;
    IF action = 'projects' THEN
        SELECT coalesce(jsonb_agg(name ORDER BY name),'[]') INTO result FROM charts.projects;
        RETURN result;
    ELSIF action = 'ensure' THEN
        IF project !~ '^[a-zA-Z0-9_-]{1,64}$' THEN RAISE EXCEPTION 'INVALID_PROJECT'; END IF;
        INSERT INTO charts.projects VALUES(project,payload->'config') ON CONFLICT DO NOTHING;
        RETURN (SELECT config FROM charts.projects p WHERE p.name=project);
    ELSIF action = 'list' THEN
        SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'revision',document->'revision','title',document#>>'{manifest,title}') ORDER BY id),'[]')
          INTO result FROM charts.boards t WHERE t.project=charts_runtime.project;
        RETURN result;
    ELSIF action IN ('generation','revoke') THEN
        IF action='revoke' THEN
            INSERT INTO charts.generations VALUES(project,board,1)
            ON CONFLICT ON CONSTRAINT generations_pkey DO UPDATE SET generation=charts.generations.generation+1;
        END IF;
        RETURN to_jsonb(coalesce((SELECT generation FROM charts.generations t WHERE t.project=charts_runtime.project AND t.board=runtime.board),0));
    ELSIF action = 'data_chunk_put' THEN
        IF payload->>'version' !~ '^[0-9a-f]{64}$' OR (payload->>'part')::integer < 0 OR jsonb_typeof(payload->'rows') <> 'array' THEN
            RAISE EXCEPTION 'INVALID_ARGUMENT';
        END IF;
        INSERT INTO charts.data_chunks VALUES(project,payload->>'version',(payload->>'part')::integer,payload->'rows')
        ON CONFLICT DO NOTHING;
        IF (SELECT rows FROM charts.data_chunks t WHERE t.project=charts_runtime.project AND t.version=payload->>'version' AND t.part=(payload->>'part')::integer) <> payload->'rows' THEN
            RAISE EXCEPTION 'DATA_CONFLICT';
        END IF;
        RETURN 'true';
    ELSIF action = 'data_finish' THEN
        IF (SELECT coalesce(sum(jsonb_array_length(rows)),0) FROM charts.data_chunks t WHERE t.project=charts_runtime.project AND t.version=payload#>>'{metadata,version}')
            <> (payload#>>'{metadata,rowCount}')::bigint THEN RAISE EXCEPTION 'DATA_INCOMPLETE'; END IF;
        INSERT INTO charts.datasets VALUES(project,payload#>>'{metadata,version}',payload->'metadata') ON CONFLICT DO NOTHING;
        RETURN (SELECT metadata FROM charts.datasets t WHERE t.project=charts_runtime.project AND t.version=payload#>>'{metadata,version}');
    ELSIF action = 'data_get' THEN
        RETURN (SELECT metadata FROM charts.datasets t WHERE t.project=charts_runtime.project AND t.version=payload->>'version');
    ELSIF action = 'data_chunk_get' THEN
        RETURN (SELECT rows FROM charts.data_chunks t WHERE t.project=charts_runtime.project AND t.version=payload->>'version' AND t.part=(payload->>'part')::integer);
    ELSIF action = 'file_put' THEN
        INSERT INTO charts.files VALUES(project,payload->>'path',payload->>'key')
        ON CONFLICT ON CONSTRAINT files_pkey DO UPDATE SET object_key=excluded.object_key;
        RETURN 'true';
    ELSIF action = 'file_get' THEN
        RETURN to_jsonb((SELECT object_key FROM charts.files t WHERE t.project=charts_runtime.project AND t.path=payload->>'path'));
    ELSIF action = 'create' THEN
        IF EXISTS(SELECT 1 FROM charts.boards t WHERE t.project=charts_runtime.project AND t.id=board) THEN RAISE EXCEPTION 'ALREADY_EXISTS'; END IF;
        INSERT INTO charts.boards VALUES(project,board,doc,coalesce(doc#>'{manifest,annotations}','[]'));
        INSERT INTO charts.revisions(project,board,revision,document,created_at,action)
            VALUES(project,board,1,doc,payload->>'at','create');
        RETURN doc;
    END IF;
    SELECT * INTO b FROM charts.boards t WHERE t.project=charts_runtime.project AND t.id=board;
    IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
    IF action='get' THEN RETURN jsonb_set(b.document,'{manifest,annotations}',b.notes);
    ELSIF action='readable' THEN
        SELECT * INTO r FROM charts.revisions t WHERE t.project=charts_runtime.project AND t.board=runtime.board ORDER BY revision DESC LIMIT 1;
        RETURN jsonb_set(r.document,'{manifest,annotations}',b.notes);
    ELSIF action='revision_get' THEN
        SELECT * INTO r FROM charts.revisions t WHERE t.project=charts_runtime.project AND t.board=runtime.board AND t.revision=(payload->>'revision')::bigint;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
        RETURN r.document;
    ELSIF action='history' THEN
        SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]') INTO result FROM
          (SELECT t.revision,t.created_at,t.action,t.name,t.protected::integer AS published
           FROM charts.revisions t WHERE t.project=charts_runtime.project AND t.board=runtime.board
           ORDER BY revision DESC LIMIT (payload->>'limit')::integer OFFSET (payload->>'offset')::integer) t;
        RETURN result;
    END IF;
    IF (b.document->>'revision')::bigint <> expected THEN RAISE EXCEPTION 'REVISION_CONFLICT'; END IF;
    IF action='commit' THEN
        IF payload->'previousNotes' IS DISTINCT FROM b.notes THEN RAISE EXCEPTION 'ANNOTATION_CONFLICT'; END IF;
        IF b.notes IS DISTINCT FROM doc#>'{manifest,annotations}' THEN
            INSERT INTO charts.annotation_events(project,board,at,revision,payload)
                VALUES(project,board,payload->>'at',(doc->>'revision')::bigint,doc#>'{manifest,annotations}');
        END IF;
        UPDATE charts.boards t SET document=doc, notes=doc#>'{manifest,annotations}'
            WHERE t.project=charts_runtime.project AND t.id=board;
        IF payload->>'restore' = 'true' THEN
            INSERT INTO charts.revisions(project,board,revision,document,created_at,action)
                VALUES(project,board,(doc->>'revision')::bigint,doc,payload->>'at','restore:'||(payload->>'revision'));
        END IF;
        RETURN doc;
    ELSIF action='begin' THEN
        INSERT INTO charts.batches VALUES(project,board,payload->>'batch',expected) ON CONFLICT DO NOTHING;
        RETURN (SELECT jsonb_build_object('board_id',t.board,'batch_id',batch_id,'base_revision',base_revision) FROM charts.batches t WHERE t.project=charts_runtime.project AND t.board=runtime.board);
    ELSIF action='checkpoint' THEN
        IF payload->>'batch' IS NOT NULL AND NOT EXISTS(SELECT 1 FROM charts.batches t WHERE t.project=charts_runtime.project AND t.board=runtime.board AND t.batch_id=payload->>'batch') THEN RAISE EXCEPTION 'INVALID_BATCH'; END IF;
        INSERT INTO charts.revisions(project,board,revision,document,created_at,action)
            VALUES(project,board,expected,b.document,payload->>'at','checkpoint') ON CONFLICT DO NOTHING;
        DELETE FROM charts.batches t WHERE t.project=charts_runtime.project AND t.board=runtime.board;
        IF coalesce(payload->>'name','') <> '' OR (payload->>'protected')::boolean THEN
            UPDATE charts.revisions t SET name=payload->>'name',protected=(payload->>'protected')::boolean WHERE t.project=charts_runtime.project AND t.board=runtime.board AND t.revision=expected;
        END IF;
        DELETE FROM charts.revisions t WHERE t.project=charts_runtime.project AND t.board=runtime.board AND t.revision IN
          (SELECT s.revision FROM charts.revisions s WHERE s.project=charts_runtime.project AND s.board=runtime.board AND s.name='' AND NOT s.protected ORDER BY s.revision DESC OFFSET (payload->>'keep')::integer);
        RETURN 'true';
    ELSIF action='label' THEN
        UPDATE charts.revisions t SET name=payload->>'name',protected=(payload->>'protected')::boolean
          WHERE t.project=charts_runtime.project AND t.board=runtime.board AND t.revision=(payload->>'revision')::bigint;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
        RETURN 'true';
    END IF;
    RAISE EXCEPTION 'UNKNOWN_ACTION';
END $$;
REVOKE ALL ON FUNCTION public.charts_runtime(text,text,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.charts_runtime(text,text,jsonb) TO service_role;
REVOKE ALL ON SCHEMA charts FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA charts FROM PUBLIC, anon, authenticated;
NOTIFY pgrst, 'reload schema';
