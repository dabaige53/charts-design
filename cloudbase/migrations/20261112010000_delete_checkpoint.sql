CREATE FUNCTION public.charts_delete_checkpoint(action text, project text, payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,charts AS $$
DECLARE
    target_board text := payload->>'board';
    target_revision bigint := (payload->>'revision')::bigint;
    draft_revision bigint;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN RAISE EXCEPTION 'FORBIDDEN' USING ERRCODE='42501'; END IF;
    IF action <> 'delete' THEN RAISE EXCEPTION 'UNKNOWN_ACTION'; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('charts:' || project,0));
    SELECT (b.document->>'revision')::bigint INTO draft_revision
      FROM charts.boards b WHERE b.project=charts_delete_checkpoint.project AND b.id=target_board;
    IF draft_revision IS DISTINCT FROM (payload->>'expected')::bigint THEN RAISE EXCEPTION 'REVISION_CONFLICT'; END IF;
    IF target_revision = (SELECT max(r.revision) FROM charts.revisions r
                          WHERE r.project=charts_delete_checkpoint.project AND r.board=target_board)
       OR EXISTS (SELECT 1 FROM charts.releases r WHERE r.project=charts_delete_checkpoint.project
                  AND r.board=target_board AND r.revision=target_revision) THEN
        RAISE EXCEPTION 'CHECKPOINT_IN_USE';
    END IF;
    DELETE FROM charts.revisions r WHERE r.project=charts_delete_checkpoint.project
      AND r.board=target_board AND r.revision=target_revision;
    IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
    RETURN jsonb_build_object('deleted',true,'revision',target_revision);
END $$;
REVOKE ALL ON FUNCTION public.charts_delete_checkpoint(text,text,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.charts_delete_checkpoint(text,text,jsonb) TO service_role;
NOTIFY pgrst, 'reload schema';
