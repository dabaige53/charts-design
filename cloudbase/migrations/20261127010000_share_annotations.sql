-- Publication feedback never enters boards, revisions, datasets or MCP state.
-- Only the existing authenticated server gateway may call this RPC.
CREATE TABLE charts.share_annotation_scopes (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    owner text NOT NULL,
    pages jsonb NOT NULL,
    annotation_mode text NOT NULL CHECK (annotation_mode IN ('view','annotate')),
    source_digest text,
    expires_at bigint,
    staging_until bigint NOT NULL,
    state text NOT NULL CHECK (state IN ('uploading','active','revoked','retired'))
);
CREATE TABLE charts.share_annotations (
    share_id text NOT NULL REFERENCES charts.share_annotation_scopes(id) ON DELETE CASCADE,
    board text NOT NULL,
    id text NOT NULL,
    fingerprint text NOT NULL,
    annotation jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (share_id,board,id)
);
REVOKE ALL ON charts.share_annotation_scopes, charts.share_annotations FROM PUBLIC, anon, authenticated;

CREATE FUNCTION public.charts_share_annotations(action text, project text DEFAULT '', payload jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,charts AS $$
#variable_conflict use_variable
DECLARE scope charts.share_annotation_scopes; note charts.share_annotations; page jsonb;
    sid text := payload->>'shareId'; board text := payload->>'dashboardId';
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN RAISE EXCEPTION 'FORBIDDEN' USING ERRCODE='42501'; END IF;
    IF sid IS NULL OR sid !~ '^[0-9a-f]{32}$' THEN RAISE EXCEPTION 'INVALID_ARGUMENT'; END IF;
    IF action='ready' THEN RETURN jsonb_build_object('ready',true); END IF;
    -- Serializes initialize, append, revoke and cleanup even before the row exists.
    PERFORM pg_advisory_xact_lock(hashtextextended('charts:share-annotations:'||sid,0));
    SELECT * INTO scope FROM charts.share_annotation_scopes WHERE id=sid;
    IF action IN ('delete','cleanup_claim') THEN
        IF action='cleanup_claim' AND scope.id IS NOT NULL AND scope.state NOT IN ('revoked','retired')
           AND NOT coalesce((payload->>'revoked')::boolean,false)
           AND ((scope.state='uploading' AND scope.staging_until>(payload->>'now')::bigint)
                OR (scope.state='active' AND (scope.expires_at IS NULL OR scope.expires_at>(payload->>'now')::bigint)))
        THEN RETURN jsonb_build_object('claimed',false,'state',scope.state,'stagingUntil',scope.staging_until); END IF;
        DELETE FROM charts.share_annotations WHERE share_id=sid;
        -- Keep only the opaque, no-longer-authorized ID. A deterministic retry
        -- must never reactivate a link after its content was physically erased.
        INSERT INTO charts.share_annotation_scopes VALUES(sid,'','[]','view',NULL,NULL,0,'retired')
        ON CONFLICT(id) DO UPDATE SET owner='',pages='[]',annotation_mode='view',source_digest=NULL,
            expires_at=NULL,staging_until=0,state='retired';
        RETURN jsonb_build_object('deleted',true,'claimed',true);
    END IF;
    IF action='configure' THEN
        IF scope.id IS NOT NULL THEN
            IF scope.state NOT IN ('uploading','active') THEN RAISE EXCEPTION 'SHARE_EXPIRED'; END IF;
            IF scope.expires_at<=extract(epoch FROM clock_timestamp())
               OR (scope.state='uploading' AND scope.staging_until<=extract(epoch FROM clock_timestamp()))
            THEN RAISE EXCEPTION 'SHARE_EXPIRED'; END IF;
            IF scope.owner IS DISTINCT FROM payload->>'owner'
               OR scope.pages IS DISTINCT FROM payload->'pages'
               OR scope.annotation_mode IS DISTINCT FROM payload->>'annotationMode'
               OR scope.source_digest IS DISTINCT FROM payload->>'sourceDigest'
               OR (scope.source_digest IS NULL AND scope.expires_at IS DISTINCT FROM (payload->>'expiresAt')::bigint)
            THEN RAISE EXCEPTION 'REVISION_CONFLICT'; END IF;
        ELSE
            INSERT INTO charts.share_annotation_scopes VALUES(sid,payload->>'owner',payload->'pages',
                payload->>'annotationMode',payload->>'sourceDigest',(payload->>'expiresAt')::bigint,
                (payload->>'stagingUntil')::bigint,'uploading');
        END IF;
        RETURN jsonb_build_object('ready',true,'expiresAt',
            (SELECT expires_at FROM charts.share_annotation_scopes WHERE id=sid),'stagingUntil',
            (SELECT staging_until FROM charts.share_annotation_scopes WHERE id=sid));
    END IF;
    IF scope.id IS NULL THEN RAISE EXCEPTION 'SHARE_UNAVAILABLE'; END IF;
    IF scope.state='retired' THEN RAISE EXCEPTION 'SHARE_EXPIRED'; END IF;
    IF action='revoke' THEN
        UPDATE charts.share_annotation_scopes SET state='revoked' WHERE id=sid;
        RETURN jsonb_build_object('revoked',true);
    END IF;
    IF action='activate' THEN
        IF scope.state NOT IN ('uploading','active')
           OR scope.expires_at<=extract(epoch FROM clock_timestamp())
           OR (scope.state='uploading' AND scope.staging_until<=extract(epoch FROM clock_timestamp()))
        THEN RAISE EXCEPTION 'SHARE_EXPIRED'; END IF;
        UPDATE charts.share_annotation_scopes SET state='active' WHERE id=sid;
        RETURN jsonb_build_object('active',true);
    END IF;
    IF scope.state<>'active' OR scope.expires_at<=extract(epoch FROM clock_timestamp())
    THEN RAISE EXCEPTION 'SHARE_EXPIRED'; END IF;
    SELECT value INTO page FROM jsonb_array_elements(scope.pages) WHERE value->>'id'=board;
    IF page IS NULL THEN RAISE EXCEPTION 'FORBIDDEN'; END IF;
    IF action='read' THEN
        RETURN coalesce((SELECT jsonb_agg(annotation ORDER BY received_at,id)
            FROM charts.share_annotations WHERE share_id=sid AND share_annotations.board=board),'[]');
    END IF;
    IF action<>'append' THEN RAISE EXCEPTION 'INVALID_ARGUMENT'; END IF;
    IF scope.annotation_mode<>'annotate' THEN RAISE EXCEPTION 'FORBIDDEN'; END IF;
    IF payload#>'{annotation,context,designRevision}' IS DISTINCT FROM page->'revision'
    THEN RAISE EXCEPTION 'REVISION_CONFLICT'; END IF;
    SELECT * INTO note FROM charts.share_annotations
        WHERE share_id=sid AND share_annotations.board=board AND id=payload#>>'{annotation,id}';
    IF note.id IS NOT NULL THEN
        IF note.fingerprint IS DISTINCT FROM payload->>'fingerprint' THEN RAISE EXCEPTION 'ANNOTATION_CONFLICT'; END IF;
        RETURN note.annotation;
    END IF;
    IF (SELECT count(*) FROM charts.share_annotations WHERE share_id=sid AND share_annotations.board=board)>=100
    THEN RAISE EXCEPTION 'ANNOTATION_LIMIT'; END IF;
    INSERT INTO charts.share_annotations(share_id,board,id,fingerprint,annotation)
        VALUES(sid,board,payload#>>'{annotation,id}',payload->>'fingerprint',payload->'annotation');
    RETURN payload->'annotation';
END $$;
REVOKE ALL ON FUNCTION public.charts_share_annotations(text,text,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.charts_share_annotations(text,text,jsonb) TO service_role;
