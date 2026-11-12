-- Compatible with older services: notes remain in charts.boards.notes.
CREATE TABLE charts.annotation_operations (
    project text NOT NULL, board text NOT NULL, operation_id text NOT NULL,
    request jsonb NOT NULL, result jsonb NOT NULL,
    PRIMARY KEY(project,board,operation_id),
    FOREIGN KEY(project,board) REFERENCES charts.boards(project,id)
);
REVOKE ALL ON charts.annotation_operations FROM PUBLIC,anon,authenticated;

CREATE FUNCTION public.charts_annotation(action text, project text, payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,charts AS $$
DECLARE
    b charts.boards%ROWTYPE;
    receipt charts.annotation_operations%ROWTYPE;
    cmd jsonb := payload->'command';
    verb text := cmd->>'action';
    note_id text := cmd->>'annotationId';
    value jsonb := cmd->'value';
    note jsonb;
    updated_notes jsonb;
    pos integer;
    rev bigint := (payload->>'revision')::bigint;
    change_id bigint;
    result jsonb;
    request jsonb := payload-'at';
    target_document jsonb;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'FORBIDDEN' USING ERRCODE='42501';
    END IF;
    IF action IS DISTINCT FROM 'apply' OR verb IS NULL OR
        verb NOT IN ('add','edit','delete','reply','status') OR
        coalesce(cmd->>'operationId','') !~ '^[a-zA-Z0-9_-]{1,100}$' OR
        coalesce(note_id,'') !~ '^[a-zA-Z][a-zA-Z0-9_-]{0,79}$' THEN
        RAISE EXCEPTION 'INVALID_ARGUMENT';
    END IF;
    -- Match existing design commits/deletions; no external I/O while locked.
    PERFORM pg_advisory_xact_lock(hashtextextended('charts:'||project,0));
    SELECT * INTO b FROM charts.boards t WHERE t.project=charts_annotation.project AND t.id=payload->>'board' FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
    SELECT * INTO receipt FROM charts.annotation_operations t WHERE
        t.project=charts_annotation.project AND t.board=b.id AND t.operation_id=cmd->>'operationId';
    IF FOUND THEN
        IF receipt.request IS DISTINCT FROM request THEN RAISE EXCEPTION 'ANNOTATION_CONFLICT'; END IF;
        RETURN receipt.result||jsonb_build_object('annotations',b.notes,'annotationChange',
            (SELECT max(e.id) FROM charts.annotation_events e WHERE e.project=charts_annotation.project AND e.board=b.id));
    END IF;
    IF rev=(b.document->>'revision')::bigint THEN target_document:=b.document;
    ELSE
        SELECT r.document INTO target_document FROM charts.revisions r
            WHERE r.project=charts_annotation.project AND r.board=b.id AND r.revision=rev;
    END IF;
    IF target_document IS NULL THEN RAISE EXCEPTION 'REVISION_CONFLICT'; END IF;
    updated_notes:=b.notes;
    SELECT entry,ordinality::integer-1 INTO note,pos FROM jsonb_array_elements(updated_notes) WITH ORDINALITY a(entry,ordinality)
        WHERE entry->>'id'=note_id;
    IF verb IN ('add','edit','reply') AND
        (jsonb_typeof(value) IS DISTINCT FROM 'object' OR jsonb_typeof(value->'text') IS DISTINCT FROM 'string'
         OR length(btrim(value->>'text'))=0 OR length(value->>'text')>4000)
        THEN RAISE EXCEPTION 'INVALID_ARGUMENT'; END IF;
    IF verb IN ('add','reply') AND (jsonb_typeof(value->'createdAt') IS DISTINCT FROM 'string'
        OR length(value->>'createdAt') NOT BETWEEN 1 AND 100) THEN RAISE EXCEPTION 'INVALID_ARGUMENT'; END IF;
    IF verb='add' THEN
        IF note IS NOT NULL THEN RAISE EXCEPTION 'ANNOTATION_CONFLICT'; END IF;
        IF jsonb_array_length(updated_notes)>=100 THEN RAISE EXCEPTION 'INVALID_ARGUMENT'; END IF;
        SELECT coalesce(jsonb_object_agg(key,v),'{}') INTO note FROM jsonb_each(value) e(key,v)
            WHERE key IN ('text','componentId','anchor','createdAt','view');
        note:=note||jsonb_build_object('componentId',value->'componentId','id',note_id,'contentVersion',1,'context',jsonb_build_object(
            'designRevision',rev,'dataVersions',coalesce(target_document#>'{snapshot,datasetRefs}','{}'),
            'filters',coalesce(value#>'{view,filters}','[]')));
        updated_notes:=updated_notes||jsonb_build_array(note);
    ELSE
        IF note IS NULL THEN RAISE EXCEPTION 'ANNOTATION_NOT_FOUND'; END IF;
        IF verb IN ('edit','delete') AND
            (cmd->'expectedVersion' IS DISTINCT FROM coalesce(note->'contentVersion','0'::jsonb))
            THEN RAISE EXCEPTION 'ANNOTATION_CONFLICT'; END IF;
        IF verb='delete' THEN
            updated_notes:=updated_notes-pos;
        ELSE
            IF verb='edit' THEN
                SELECT note||coalesce(jsonb_object_agg(key,v),'{}') INTO note FROM jsonb_each(value) e(key,v)
                    WHERE key IN ('text','componentId','anchor');
                note:=note||jsonb_build_object('contentVersion',coalesce((note->>'contentVersion')::bigint,0)+1);
            ELSIF verb='reply' THEN
                IF coalesce(note->>'status','open')='resolved' OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements(coalesce(note->'replies','[]')) r WHERE r->>'id'=value->>'id')
                    THEN RAISE EXCEPTION 'ANNOTATION_CONFLICT'; END IF;
                IF coalesce(value->>'id','') !~ '^[a-zA-Z0-9_-]{1,100}$' THEN RAISE EXCEPTION 'INVALID_ARGUMENT'; END IF;
                note:=note||jsonb_build_object('replies',coalesce(note->'replies','[]')||
                    jsonb_build_array(jsonb_build_object('id',value->>'id','text',value->>'text','createdAt',value->>'createdAt')));
            ELSIF verb='status' THEN
                IF cmd->>'status' IS NULL OR cmd->>'status' NOT IN ('open','resolved') THEN RAISE EXCEPTION 'INVALID_ARGUMENT'; END IF;
                IF cmd->>'expectedStatus' IS DISTINCT FROM coalesce(note->>'status','open')
                    THEN RAISE EXCEPTION 'ANNOTATION_CONFLICT'; END IF;
                note:=note||jsonb_build_object('status',cmd->>'status');
            END IF;
            updated_notes:=jsonb_set(updated_notes,ARRAY[pos::text],note);
        END IF;
    END IF;
    PERFORM charts.assert_asset_refs(project,jsonb_build_object('manifest',jsonb_build_object('annotations',updated_notes)));
    UPDATE charts.asset_state s SET epoch=epoch+1 WHERE s.project=charts_annotation.project;
    UPDATE charts.boards t SET notes=updated_notes
        WHERE t.project=charts_annotation.project AND t.id=b.id;
    INSERT INTO charts.annotation_events(project,board,at,revision,payload)
        VALUES(project,b.id,payload->>'at',rev,updated_notes) RETURNING id INTO change_id;
    result:=jsonb_build_object('dashboardId',b.id,'annotations',updated_notes,'annotationChange',change_id);
    INSERT INTO charts.annotation_operations VALUES(project,b.id,cmd->>'operationId',request,result);
    RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.charts_annotation(text,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.charts_annotation(text,text,jsonb) TO service_role;
NOTIFY pgrst,'reload schema';
