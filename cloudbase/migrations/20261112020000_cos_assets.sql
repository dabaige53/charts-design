-- Application payloads live in private COS; PostgreSQL coordinates references.
CREATE TABLE charts.asset_objects (
    project text NOT NULL REFERENCES charts.projects(name), id text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('dataset','document')),
    version text, prefix text NOT NULL, descriptor jsonb NOT NULL DEFAULT '{}',
    state text NOT NULL CHECK (state IN ('uploading','ready','deleting','deleted')),
    created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(project,id)
);
CREATE UNIQUE INDEX asset_dataset_ready ON charts.asset_objects(project,version)
    WHERE kind='dataset' AND state='ready';
CREATE TABLE charts.asset_state (
    project text PRIMARY KEY REFERENCES charts.projects(name),
    epoch bigint NOT NULL DEFAULT 0, format text NOT NULL DEFAULT 'postgres'
);
CREATE TABLE charts.share_refs (
    id text PRIMARY KEY, project text NOT NULL REFERENCES charts.projects(name),
    pages jsonb NOT NULL, state text NOT NULL, expires_at bigint, bytes bigint NOT NULL DEFAULT 0,
    staging_until bigint NOT NULL DEFAULT (extract(epoch FROM now())::bigint+3600)
);
CREATE TABLE charts.delete_plans (
    project text NOT NULL, token text NOT NULL, epoch bigint NOT NULL,
    board text NOT NULL, revision bigint NOT NULL, plan jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(project,token)
);
CREATE TABLE charts.delete_jobs (
    project text NOT NULL, id text NOT NULL, board text NOT NULL, revision bigint NOT NULL,
    state text NOT NULL, plan jsonb NOT NULL, completed jsonb NOT NULL DEFAULT '[]',
    error text, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(project,id)
);
CREATE TABLE charts.version_heads (
    project text NOT NULL, board text NOT NULL, published bigint, PRIMARY KEY(project,board)
);
INSERT INTO charts.version_heads
SELECT DISTINCT ON (project,board) project,board,revision FROM charts.releases ORDER BY project,board,id DESC;

-- A conservative reference view also covers annotation context and old payloads.
CREATE FUNCTION charts.asset_documents(p text)
RETURNS TABLE(source text, board text, revision bigint, document jsonb)
LANGUAGE sql SET search_path=pg_catalog,charts AS $$
    SELECT 'draft',id,(document->>'revision')::bigint,document FROM charts.boards WHERE project=p
    UNION ALL SELECT 'checkpoint',board,revision,document FROM charts.revisions WHERE project=p
    UNION ALL SELECT 'release',board,revision,document FROM charts.releases WHERE project=p
    UNION ALL SELECT 'annotations',id,0,notes FROM charts.boards WHERE project=p
    UNION ALL SELECT 'annotation-history',board,revision,payload FROM charts.annotation_events WHERE project=p
$$;

CREATE FUNCTION charts.assert_asset_refs(p text, doc jsonb)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,charts AS $$
DECLARE item record;
BEGIN
    IF doc ? 'cosObject' AND NOT EXISTS (
        SELECT 1 FROM charts.asset_objects WHERE project=p AND id=doc->>'cosObject' AND state='ready'
    ) THEN RAISE EXCEPTION 'ASSET_UNAVAILABLE'; END IF;
    FOR item IN SELECT key,value FROM jsonb_each(coalesce(doc#>'{snapshot,datasetRefs}','{}'))
        UNION ALL SELECT key,value FROM jsonb_each(coalesce(doc#>'{snapshot,componentDataRefs}','{}'))
    LOOP
        IF NOT EXISTS (SELECT 1 FROM charts.datasets WHERE project=p AND version=item.value->>'version')
           OR EXISTS (SELECT 1 FROM charts.asset_objects WHERE project=p AND version=item.value->>'version'
                      AND state='deleting')
           OR EXISTS (SELECT 1 FROM charts.delete_jobs WHERE project=p AND state<>'complete'
                      AND plan->'datasets' ? (item.value->>'version'))
        THEN RAISE EXCEPTION 'ASSET_UNAVAILABLE'; END IF;
    END LOOP;
    -- Annotation contexts and legacy embedded references are conservative too.
    IF EXISTS (SELECT 1 FROM charts.asset_objects o WHERE o.project=p AND o.kind='dataset'
               AND o.state='deleting' AND position(o.version IN doc::text)>0)
       OR EXISTS (SELECT 1 FROM charts.delete_jobs j, jsonb_array_elements_text(j.plan->'datasets') v
                  WHERE j.project=p AND j.state<>'complete' AND position(v IN doc::text)>0)
    THEN RAISE EXCEPTION 'ASSET_UNAVAILABLE'; END IF;
END $$;

-- Retain the legacy RPC for projects not explicitly migrated. Every mutation
-- participates in the same project lock and invalidates deletion previews.
ALTER FUNCTION public.charts_runtime(text,text,jsonb) RENAME TO charts_runtime_legacy;
DO $$ BEGIN
    EXECUTE replace(pg_get_functiondef('public.charts_runtime_legacy(text,text,jsonb)'::regprocedure),
                    'charts_runtime.', 'charts_runtime_legacy.');
END $$;
CREATE FUNCTION public.charts_runtime(action text, project text DEFAULT '', payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,charts AS $$
#variable_conflict use_variable
DECLARE result jsonb; fmt text; writing boolean;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN RAISE EXCEPTION 'FORBIDDEN' USING ERRCODE='42501'; END IF;
    writing := action IN ('ensure','create','commit','checkpoint','begin','label','revoke',
                         'data_chunk_put','data_finish','file_put');
    IF writing THEN PERFORM pg_advisory_xact_lock(hashtextextended('charts:'||project,0)); END IF;
    SELECT format INTO fmt FROM charts.asset_state s WHERE s.project=charts_runtime.project;
    IF fmt='cos-v1' AND action IN ('data_chunk_put','data_finish') THEN RAISE EXCEPTION 'STORAGE_MIGRATED'; END IF;
    IF action IN ('data_chunk_put','data_finish') AND EXISTS (
        SELECT 1 FROM charts.delete_jobs j WHERE j.project=charts_runtime.project AND j.state<>'complete'
        AND j.plan->'datasets' ? coalesce(payload->>'version',payload#>>'{metadata,version}')
    ) THEN RAISE EXCEPTION 'ASSET_UNAVAILABLE'; END IF;
    IF action IN ('create','commit') THEN
        IF fmt='cos-v1' AND NOT (payload->'document' ? 'cosObject') THEN RAISE EXCEPTION 'STORAGE_MIGRATED'; END IF;
        PERFORM charts.assert_asset_refs(project,payload->'document');
    END IF;
    IF action='checkpoint' AND EXISTS (SELECT 1 FROM charts.delete_jobs j WHERE j.project=charts_runtime.project
        AND j.board=payload->>'board' AND j.revision=(payload->>'expected')::bigint) THEN
        RAISE EXCEPTION 'REVISION_DELETED';
    END IF;
    -- User-confirmed deletion replaces implicit history pruning.
    IF action='checkpoint' THEN payload:=payload||jsonb_build_object('keep',2147483647); END IF;
    result:=public.charts_runtime_legacy(action,project,payload);
    IF action='readable' AND result IS NULL THEN RAISE EXCEPTION 'NO_SAVED_VERSION'; END IF;
    IF writing THEN
        INSERT INTO charts.asset_state(project,epoch) VALUES(project,1)
        ON CONFLICT ON CONSTRAINT asset_state_pkey DO UPDATE SET epoch=charts.asset_state.epoch+1;
    END IF;
    IF action='ensure' THEN result:=result||jsonb_build_object('storageFormat',coalesce(fmt,'postgres')); END IF;
    RETURN result;
END $$;

ALTER FUNCTION public.charts_release(text,text,jsonb) RENAME TO charts_release_legacy;
DO $$ BEGIN
    EXECUTE replace(pg_get_functiondef('public.charts_release_legacy(text,text,jsonb)'::regprocedure),
                    'charts_release.', 'charts_release_legacy.');
END $$;
CREATE FUNCTION public.charts_release(action text, project text, payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,charts AS $$
#variable_conflict use_variable
DECLARE result jsonb; doc jsonb; current_revision bigint;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN RAISE EXCEPTION 'FORBIDDEN' USING ERRCODE='42501'; END IF;
    IF action='publish' THEN
        PERFORM pg_advisory_xact_lock(hashtextextended('charts:'||project,0));
        doc:=public.charts_release_legacy('read',project,payload);
        PERFORM charts.assert_asset_refs(project,doc);
        IF EXISTS (SELECT 1 FROM charts.delete_jobs j WHERE j.project=charts_release.project
                   AND j.board=payload->>'board' AND j.revision=(payload->>'revision')::bigint) THEN
            RAISE EXCEPTION 'REVISION_DELETED';
        END IF;
    END IF;
    result:=public.charts_release_legacy(action,project,payload);
    IF action='publish' THEN
        INSERT INTO charts.version_heads VALUES(project,payload->>'board',(payload->>'revision')::bigint)
        ON CONFLICT ON CONSTRAINT version_heads_pkey DO UPDATE SET published=excluded.published;
        UPDATE charts.asset_state s SET epoch=epoch+1 WHERE s.project=charts_release.project;
    END IF;
    IF action IN ('status','publish') THEN
        SELECT published INTO current_revision FROM charts.version_heads h
            WHERE h.project=charts_release.project AND h.board=payload->>'board';
        result:=result||jsonb_build_object('publishedRevision',current_revision,'frozen',true,
            'deletionJobs',coalesce((SELECT jsonb_agg(jsonb_build_object('id',j.id,'revision',j.revision,
                'state',j.state,'error',j.error)) FROM charts.delete_jobs j
                WHERE j.project=charts_release.project AND j.board=payload->>'board' AND j.state<>'complete'),'[]'));
    END IF;
    RETURN result;
END $$;

CREATE FUNCTION public.charts_assets(action text, project text DEFAULT '', payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,charts AS $$
#variable_conflict use_variable
DECLARE result jsonb; obj charts.asset_objects%ROWTYPE; item jsonb; target jsonb;
    token text:=payload->>'token'; board text:=payload->>'board';
    rev bigint:=(payload->>'revision')::bigint; current_epoch bigint;
    plan charts.delete_plans%ROWTYPE; job charts.delete_jobs%ROWTYPE;
    objects jsonb:='[]'; retained jsonb:='[]'; shares jsonb; refs jsonb; datasets jsonb:='[]';
    objbytes bigint:=0; pgbytes bigint:=0; next_saved bigint; published bigint;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN RAISE EXCEPTION 'FORBIDDEN' USING ERRCODE='42501'; END IF;
    IF action='share_access' THEN
        RETURN (SELECT jsonb_build_object('state',s.state,'project',s.project,
                    'expiresAt',s.expires_at,'stagingUntil',s.staging_until)
                FROM charts.share_refs s WHERE s.id=payload->>'id');
    END IF;
    IF action='pending' THEN
        RETURN coalesce((SELECT jsonb_agg(jsonb_build_object('project',j.project,'id',j.id,'board',j.board))
            FROM charts.delete_jobs j WHERE j.state<>'complete'),'[]');
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('charts:'||project,0));
    INSERT INTO charts.asset_state(project) VALUES(project) ON CONFLICT DO NOTHING;
    SELECT epoch INTO current_epoch FROM charts.asset_state s WHERE s.project=charts_assets.project;
    IF action='object_get' THEN
        RETURN (SELECT to_jsonb(o) FROM charts.asset_objects o WHERE o.project=charts_assets.project
            AND o.state='ready' AND ((payload ? 'id' AND o.id=payload->>'id')
            OR (NOT payload ? 'id' AND o.kind=coalesce(payload->>'kind','dataset') AND o.version=payload->>'version'))
            ORDER BY o.created_at LIMIT 1);
    ELSIF action='reserve' THEN
        IF payload->>'id' !~ '^[0-9a-f]{32}$' THEN RAISE EXCEPTION 'INVALID_ARGUMENT'; END IF;
        INSERT INTO charts.asset_objects(project,id,kind,version,prefix,state)
            VALUES(project,payload->>'id',payload->>'kind',payload->>'version',
                   project||'/objects/'||(payload->>'id')||'/','uploading') RETURNING * INTO obj;
        result:=to_jsonb(obj);
    ELSIF action='ready' THEN
        SELECT * INTO obj FROM charts.asset_objects o WHERE o.project=charts_assets.project
            AND o.id=payload->>'id' AND o.state='uploading';
        IF NOT FOUND THEN RAISE EXCEPTION 'ASSET_UNAVAILABLE'; END IF;
        IF obj.kind='dataset' THEN
            IF EXISTS (SELECT 1 FROM charts.asset_objects o WHERE o.project=charts_assets.project
                       AND o.version=obj.version AND o.state='deleting')
               OR EXISTS (SELECT 1 FROM charts.delete_jobs j WHERE j.project=charts_assets.project
                          AND j.state<>'complete' AND j.plan->'datasets' ? obj.version)
            THEN RAISE EXCEPTION 'ASSET_UNAVAILABLE'; END IF;
            SELECT to_jsonb(o) INTO result FROM charts.asset_objects o WHERE o.project=charts_assets.project
                AND o.version=obj.version AND o.kind='dataset' AND o.state='ready';
            IF result IS NOT NULL THEN RETURN result; END IF;
            INSERT INTO charts.datasets VALUES(project,obj.version,payload#>'{descriptor,metadata}') ON CONFLICT DO NOTHING;
            IF (SELECT metadata FROM charts.datasets d WHERE d.project=charts_assets.project AND d.version=obj.version)
                IS DISTINCT FROM payload#>'{descriptor,metadata}' THEN RAISE EXCEPTION 'DATA_CONFLICT'; END IF;
        END IF;
        UPDATE charts.asset_objects o SET descriptor=payload->'descriptor',state='ready'
            WHERE o.project=charts_assets.project AND o.id=obj.id RETURNING to_jsonb(o) INTO result;
    ELSIF action='share_register' THEN
        FOR item IN SELECT value FROM jsonb_array_elements(payload->'pages') LOOP
            IF NOT EXISTS (SELECT 1 FROM charts.revisions r WHERE r.project=charts_assets.project AND r.board=item->>'id'
                           AND r.revision=(item->>'revision')::bigint)
               AND NOT EXISTS (SELECT 1 FROM charts.releases r WHERE r.project=charts_assets.project AND r.board=item->>'id'
                           AND r.revision=(item->>'revision')::bigint) THEN RAISE EXCEPTION 'REVISION_DELETED'; END IF;
        END LOOP;
        INSERT INTO charts.share_refs(id,project,pages,state,expires_at,bytes,staging_until)
            VALUES(payload->>'id',project,payload->'pages',payload->>'state',(payload->>'expiresAt')::bigint,
                   coalesce((payload->>'bytes')::bigint,0),
                   coalesce((payload->>'stagingUntil')::bigint,extract(epoch FROM now())::bigint+3600))
        ON CONFLICT (id) DO UPDATE SET
            state=CASE WHEN charts.share_refs.state='active' AND excluded.state='uploading'
                       THEN charts.share_refs.state ELSE excluded.state END,
            pages=excluded.pages,
            bytes=CASE WHEN charts.share_refs.state='active' AND excluded.state='uploading'
                       THEN charts.share_refs.bytes ELSE excluded.bytes END
            WHERE charts.share_refs.project=excluded.project AND charts.share_refs.state<>'revoked';
        IF NOT FOUND THEN RAISE EXCEPTION 'REVISION_DELETED'; END IF;
        result:='true';
    ELSIF action='share_cleanup_claim' THEN
        -- Publication and cleanup decide under the same project lock. A stale
        -- staging observation cannot revoke a share that just became active.
        UPDATE charts.share_refs s SET state='revoked'
            WHERE s.project=charts_assets.project AND s.id=payload->>'id'
            AND (s.state='revoked'
                 OR (s.state='uploading' AND s.staging_until<=(payload->>'now')::bigint)
                 OR (s.state='active' AND s.expires_at<=(payload->>'now')::bigint));
        IF NOT FOUND THEN RETURN 'false'; END IF;
        result:='true';
    ELSIF action='share_revoke' THEN
        UPDATE charts.share_refs s SET state='revoked' WHERE s.project=charts_assets.project AND s.id=payload->>'id';
        result:='true';
    ELSIF action='inventory' OR action='migration_snapshot' THEN
        RETURN jsonb_build_object('epoch',current_epoch,'format',(SELECT format FROM charts.asset_state s WHERE s.project=charts_assets.project),
            'objects',coalesce((SELECT jsonb_agg(to_jsonb(o)) FROM charts.asset_objects o WHERE o.project=charts_assets.project),'[]'),
            'datasets',coalesce((SELECT jsonb_agg(d.metadata) FROM charts.datasets d WHERE d.project=charts_assets.project),'[]'),
            'unfinishedChunks',(SELECT count(*) FROM charts.data_chunks c WHERE c.project=charts_assets.project
                AND NOT EXISTS(SELECT 1 FROM charts.datasets d WHERE d.project=c.project AND d.version=c.version)),
            'documents',coalesce((SELECT jsonb_agg(to_jsonb(d)) FROM charts.asset_documents(project) d),'[]'));
    ELSIF action='migration_commit' THEN
        IF current_epoch<>(payload->>'epoch')::bigint THEN RAISE EXCEPTION 'PLAN_CHANGED'; END IF;
        IF EXISTS (SELECT 1 FROM charts.data_chunks c WHERE c.project=charts_assets.project
            AND NOT EXISTS(SELECT 1 FROM charts.datasets d WHERE d.project=c.project AND d.version=c.version))
        THEN RAISE EXCEPTION 'DATA_INCOMPLETE'; END IF;
        FOR item IN SELECT value FROM jsonb_array_elements(payload->'documents') LOOP
            PERFORM charts.assert_asset_refs(project,item->'document');
            IF item->>'source'='draft' THEN
                UPDATE charts.boards b SET document=item->'document' WHERE b.project=charts_assets.project AND b.id=item->>'board';
            ELSIF item->>'source'='checkpoint' THEN
                UPDATE charts.revisions r SET document=item->'document' WHERE r.project=charts_assets.project
                    AND r.board=item->>'board' AND r.revision=(item->>'revision')::bigint;
            ELSIF item->>'source'='release' THEN
                UPDATE charts.releases r SET document=item->'document' WHERE r.project=charts_assets.project
                    AND r.board=item->>'board' AND r.revision=(item->>'revision')::bigint;
            END IF;
        END LOOP;
        IF EXISTS (SELECT 1 FROM charts.asset_documents(project) d
            WHERE source IN ('draft','checkpoint','release') AND NOT document ? 'cosObject')
           OR EXISTS (SELECT 1 FROM charts.datasets d WHERE d.project=charts_assets.project AND NOT EXISTS
            (SELECT 1 FROM charts.asset_objects o WHERE o.project=d.project AND o.version=d.version AND o.kind='dataset' AND state='ready'))
        THEN RAISE EXCEPTION 'DATA_INCOMPLETE'; END IF;
        DELETE FROM charts.data_chunks d WHERE d.project=charts_assets.project;
        UPDATE charts.asset_state s SET format='cos-v1' WHERE s.project=charts_assets.project;
        UPDATE charts.projects p SET config=config||jsonb_build_object('storage',
            jsonb_build_object('partitionFields',payload->'partitionFields')) WHERE p.name=project;
        result:=jsonb_build_object('format','cos-v1');
    ELSIF action='delete_preview' THEN
        SELECT jsonb_agg(d.document) INTO target FROM charts.asset_documents(project) d
            WHERE d.board=charts_assets.board AND d.revision=rev AND d.source IN ('checkpoint','release');
        IF target IS NULL THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
        IF (SELECT (b.document->>'revision')::bigint FROM charts.boards b WHERE b.project=charts_assets.project AND b.id=board)
           IS DISTINCT FROM (payload->>'expected')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT'; END IF;
        FOR obj IN SELECT * FROM charts.asset_objects o WHERE o.project=charts_assets.project AND o.state='ready'
            AND ((o.kind='document' AND EXISTS (SELECT 1 FROM charts.asset_documents(project) d
                  WHERE d.board=charts_assets.board AND d.revision=rev AND d.source IN ('checkpoint','release')
                  AND d.document->>'cosObject'=o.id))
                OR (o.kind='dataset' AND position(o.version IN target::text)>0))
        LOOP
            SELECT coalesce(jsonb_agg(jsonb_build_object('source',d.source,'dashboardId',d.board,'revision',d.revision)),'[]')
                INTO refs FROM charts.asset_documents(project) d
                WHERE NOT (d.board=charts_assets.board AND d.revision=rev AND d.source IN ('checkpoint','release'))
                AND ((obj.kind='document' AND d.document->>'cosObject'=obj.id)
                     OR (obj.kind='dataset' AND position(obj.version IN d.document::text)>0));
            IF jsonb_array_length(refs)>0 THEN
                retained:=retained||jsonb_build_array(jsonb_build_object('id',obj.id,'version',obj.version,'references',refs));
            ELSE
                objects:=objects||jsonb_build_array(jsonb_build_object('id',obj.id,'prefix',obj.prefix,'version',obj.version));
                objbytes:=objbytes+coalesce((obj.descriptor->>'bytes')::bigint,0);
            END IF;
        END LOOP;
        FOR item IN SELECT metadata FROM charts.datasets d WHERE d.project=charts_assets.project
            AND position(d.version IN target::text)>0 LOOP
            SELECT coalesce(jsonb_agg(jsonb_build_object('source',d.source,'dashboardId',d.board,'revision',d.revision)),'[]')
                INTO refs FROM charts.asset_documents(project) d
                WHERE NOT (d.board=charts_assets.board AND d.revision=rev AND d.source IN ('checkpoint','release'))
                  AND position((item->>'version') IN d.document::text)>0;
            IF jsonb_array_length(refs)=0 THEN
                datasets:=datasets||jsonb_build_array(item->>'version');
                pgbytes:=pgbytes+coalesce((SELECT sum(octet_length(c.rows::text)) FROM charts.data_chunks c
                    WHERE c.project=charts_assets.project AND c.version=item->>'version'),0);
            ELSIF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(retained) x WHERE x->>'version'=item->>'version') THEN
                retained:=retained||jsonb_build_array(jsonb_build_object('version',item->>'version','references',refs));
            END IF;
        END LOOP;
        SELECT coalesce(jsonb_agg(jsonb_build_object('shareId',s.id,'pages',s.pages,'state',s.state,'bytes',s.bytes)),'[]')
            INTO shares FROM charts.share_refs s WHERE s.project=charts_assets.project AND s.state<>'uploading' AND EXISTS
                (SELECT 1 FROM jsonb_array_elements(s.pages) x WHERE x->>'id'=board AND (x->>'revision')::bigint=rev);
        SELECT max(r.revision) INTO next_saved FROM charts.revisions r WHERE r.project=charts_assets.project AND r.board=charts_assets.board AND r.revision<>rev;
        SELECT h.published INTO published FROM charts.version_heads h WHERE h.project=charts_assets.project AND h.board=charts_assets.board;
        result:=jsonb_build_object('revision',rev,'objects',objects,'datasets',datasets,'retained',retained,'shares',shares,
            'cosBytes',objbytes+coalesce((SELECT sum((x->>'bytes')::bigint) FROM jsonb_array_elements(shares) x),0),
            'postgresBytes',pgbytes+octet_length(target::text),'nextSavedRevision',next_saved,
            'clearsPublication',published=rev,'token',token,'checkedAt',now());
        INSERT INTO charts.delete_plans VALUES(project,token,current_epoch,board,rev,result,now());
        RETURN result;
    ELSIF action='delete_begin' THEN
        SELECT * INTO job FROM charts.delete_jobs j WHERE j.project=charts_assets.project AND j.id=token;
        IF FOUND THEN
            IF job.board IS DISTINCT FROM board OR job.revision IS DISTINCT FROM rev THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
            RETURN to_jsonb(job);
        END IF;
        SELECT * INTO plan FROM charts.delete_plans p WHERE p.project=charts_assets.project AND p.token=charts_assets.token;
        IF NOT FOUND OR plan.epoch<>current_epoch OR plan.created_at<now()-interval '15 minutes'
            OR plan.board IS DISTINCT FROM board OR plan.revision IS DISTINCT FROM rev THEN RAISE EXCEPTION 'PLAN_CHANGED'; END IF;
        UPDATE charts.share_refs s SET state='revoked' WHERE s.project=charts_assets.project
            AND s.id IN (SELECT x->>'shareId' FROM jsonb_array_elements(plan.plan->'shares') x);
        UPDATE charts.asset_objects o SET state='deleting' WHERE o.project=charts_assets.project
            AND o.id IN (SELECT x->>'id' FROM jsonb_array_elements(plan.plan->'objects') x);
        DELETE FROM charts.revisions r WHERE r.project=charts_assets.project AND r.board=charts_assets.board AND r.revision=rev;
        DELETE FROM charts.releases r WHERE r.project=charts_assets.project AND r.board=charts_assets.board AND r.revision=rev;
        UPDATE charts.boards b SET document=jsonb_set(document,'{revision}',to_jsonb(rev+1))
            WHERE b.project=charts_assets.project AND b.id=board AND (document->>'revision')::bigint=rev;
        DELETE FROM charts.batches b WHERE b.project=charts_assets.project AND b.board=charts_assets.board;
        UPDATE charts.version_heads h SET published=NULL WHERE h.project=charts_assets.project AND h.board=charts_assets.board AND h.published=rev;
        INSERT INTO charts.delete_jobs(project,id,board,revision,state,plan) VALUES(project,token,board,rev,'deleting',plan.plan)
            RETURNING * INTO job;
        result:=to_jsonb(job);
    ELSIF action='delete_status' THEN
        SELECT * INTO job FROM charts.delete_jobs j WHERE j.project=charts_assets.project AND j.id=payload->>'id' AND j.board=board;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
        RETURN to_jsonb(job);
    ELSIF action='delete_progress' THEN
        SELECT * INTO job FROM charts.delete_jobs j WHERE j.project=charts_assets.project AND j.id=payload->>'id';
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
        IF job.state='complete' THEN RETURN to_jsonb(job); END IF;
        UPDATE charts.delete_jobs j SET completed=(SELECT coalesce(jsonb_agg(DISTINCT v),'[]')
            FROM jsonb_array_elements(j.completed||(payload->'completed')) v),error=payload->>'error',
            state=CASE WHEN payload->>'error' IS NULL THEN 'deleting' ELSE 'failed' END
            WHERE j.project=charts_assets.project AND j.id=payload->>'id' AND j.state<>'complete' RETURNING * INTO job;
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
        RETURN to_jsonb(job);
    ELSIF action='delete_finish' THEN
        SELECT * INTO job FROM charts.delete_jobs j WHERE j.project=charts_assets.project AND j.id=payload->>'id';
        IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
        IF job.state='complete' THEN RETURN to_jsonb(job); END IF;
        IF jsonb_array_length(job.completed)<>jsonb_array_length(job.plan->'objects')+jsonb_array_length(job.plan->'shares')
        THEN RAISE EXCEPTION 'DATA_INCOMPLETE'; END IF;
        DELETE FROM charts.data_chunks c WHERE c.project=charts_assets.project AND c.version IN
            (SELECT jsonb_array_elements_text(job.plan->'datasets'));
        DELETE FROM charts.datasets d WHERE d.project=charts_assets.project AND d.version IN
            (SELECT jsonb_array_elements_text(job.plan->'datasets'));
        UPDATE charts.asset_objects o SET state='deleted',descriptor='{}' WHERE o.project=charts_assets.project
            AND o.id IN (SELECT x->>'id' FROM jsonb_array_elements(job.plan->'objects') x);
        UPDATE charts.delete_jobs j SET state='complete',error=NULL,plan=jsonb_build_object('revision',j.revision)
            WHERE j.project=charts_assets.project AND j.id=job.id RETURNING to_jsonb(j) INTO result;
        DELETE FROM charts.delete_plans p WHERE p.project=charts_assets.project AND p.token=job.id;
    ELSE RAISE EXCEPTION 'UNKNOWN_ACTION';
    END IF;
    UPDATE charts.asset_state s SET epoch=epoch+1 WHERE s.project=charts_assets.project;
    RETURN result;
END $$;
-- Old deletion APIs must not bypass the impact confirmation.
CREATE OR REPLACE FUNCTION public.charts_delete_checkpoint(action text, project text, payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,charts AS $$
BEGIN RAISE EXCEPTION 'CONFIRMATION_REQUIRED'; END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA charts FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.charts_runtime_legacy(text,text,jsonb),public.charts_release_legacy(text,text,jsonb)
    FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION charts.asset_documents(text),charts.assert_asset_refs(text,jsonb) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.charts_runtime(text,text,jsonb),public.charts_release(text,text,jsonb),
    public.charts_assets(text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.charts_runtime(text,text,jsonb),public.charts_release(text,text,jsonb),
    public.charts_assets(text,text,jsonb) TO service_role;
NOTIFY pgrst,'reload schema';
