CREATE FUNCTION public.charts_data_inventory(action text, project text, payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,charts AS $$
DECLARE
    result jsonb;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN RAISE EXCEPTION 'FORBIDDEN' USING ERRCODE='42501'; END IF;
    IF action <> 'inventory' THEN RAISE EXCEPTION 'UNKNOWN_ACTION'; END IF;
    WITH versions AS (
        SELECT d.version, true AS complete, d.metadata, count(c.part) AS chunks,
               coalesce(sum(pg_column_size(c.rows)),0) AS chunk_bytes
          FROM charts.datasets d LEFT JOIN charts.data_chunks c
            ON c.project=d.project AND c.version=d.version
         WHERE d.project=charts_data_inventory.project
         GROUP BY d.version,d.metadata
        UNION ALL
        SELECT c.version, false, NULL::jsonb, count(c.part), sum(pg_column_size(c.rows))
          FROM charts.data_chunks c
         WHERE c.project=charts_data_inventory.project
           AND NOT EXISTS (SELECT 1 FROM charts.datasets d WHERE d.project=c.project AND d.version=c.version)
         GROUP BY c.version
    ), documents AS (
        SELECT 'draft' AS source, b.id AS board, NULL::bigint AS revision, b.document::text AS body
          FROM charts.boards b WHERE b.project=charts_data_inventory.project
        UNION ALL SELECT 'annotations',b.id,NULL::bigint,b.notes::text
          FROM charts.boards b WHERE b.project=charts_data_inventory.project
        UNION ALL SELECT 'checkpoint',r.board,r.revision,r.document::text
          FROM charts.revisions r WHERE r.project=charts_data_inventory.project
        UNION ALL SELECT 'release',r.board,r.revision,r.document::text
          FROM charts.releases r WHERE r.project=charts_data_inventory.project
        UNION ALL SELECT 'annotation_history',a.board,a.revision,a.payload::text
          FROM charts.annotation_events a WHERE a.project=charts_data_inventory.project
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'version',v.version,'complete',v.complete,'rowCount',v.metadata->'rowCount',
        'chunks',v.chunks,'chunkBytes',v.chunk_bytes,
        'references',coalesce((SELECT jsonb_agg(jsonb_build_object('source',d.source,'dashboardId',d.board,'revision',d.revision))
            FROM documents d WHERE position(v.version in d.body)>0),'[]'::jsonb),
        'reviewRequired',true) ORDER BY v.chunk_bytes DESC),'[]'::jsonb)
      INTO result FROM versions v;
    RETURN jsonb_build_object('project',project,'checkedAt',clock_timestamp(),'versions',result,
        'sizeMeaning','Stored JSON chunk bytes; excludes indexes and database overhead. Not a guaranteed reclaim amount.',
        'note','References are conservative text matches. Incomplete or unreferenced versions require review; no deletion is performed.');
END $$;
REVOKE ALL ON FUNCTION public.charts_data_inventory(text,text,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.charts_data_inventory(text,text,jsonb) TO service_role;
NOTIFY pgrst, 'reload schema';
