BEGIN;
SELECT set_config('request.jwt.claims', '{"role":"service_role"}', true);
-- @wu-test type=regression | scope=charts_assets document cleanup | protects=防止 audit-7 复发：中间草稿永久残留或清理仍引用和正在提交的文档
DO $test$
DECLARE p text := 'draft-cleanup-' || md5(random()::text);
    obj text; orphan text := md5('abandoned'); current_doc text := md5('current');
    saved text := md5('saved'); released text := md5('released'); recent text := md5('recent');
    outcome jsonb; rejected boolean := false;
BEGIN
    PERFORM public.charts_runtime('ensure',p,'{"config":{}}');
    FOREACH obj IN ARRAY ARRAY[orphan,current_doc,saved,released,recent] LOOP
        INSERT INTO charts.asset_objects(project,id,kind,prefix,state,created_at)
            VALUES(p,obj,'document',p||'/objects/'||obj||'/','ready',
                   CASE WHEN obj=recent THEN now() ELSE now()-interval '2 hours' END);
    END LOOP;
    INSERT INTO charts.boards(project,id,document) VALUES
        (p,'board',jsonb_build_object('id','board','revision',3,'cosObject',current_doc,'snapshot','{}'::jsonb));
    INSERT INTO charts.revisions(project,board,revision,document,created_at,action) VALUES
        (p,'board',1,jsonb_build_object('id','board','revision',1,'cosObject',saved),'2026-11-12','test');
    INSERT INTO charts.releases(project,board,revision,document,created_at) VALUES
        (p,'board',2,jsonb_build_object('id','board','revision',2,'cosObject',released),'2026-11-12');
    PERFORM public.charts_assets('collect_drafts');
    ASSERT (SELECT state FROM charts.asset_objects WHERE project=p AND id=orphan)='deleting',
        'Abandoned draft must enter durable cleanup';
    ASSERT (SELECT count(*) FROM charts.asset_objects WHERE project=p AND state='ready')=4,
        'Current, saved, published and recent objects must remain';
    PERFORM public.charts_assets('collect_drafts');
    ASSERT (SELECT count(*) FROM charts.delete_jobs WHERE project=p)=1, 'Claim must not create duplicate jobs';
    BEGIN
        PERFORM charts.assert_asset_refs(p,jsonb_build_object('cosObject',orphan));
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM='ASSET_UNAVAILABLE' THEN rejected:=true; ELSE RAISE; END IF;
    END;
    ASSERT rejected, 'A concurrent commit must not revive a claimed object';
    outcome:=public.charts_assets('delete_progress',p,jsonb_build_object(
        'id','orphan-'||orphan,'completed','[]'::jsonb,'error','TEMPORARY_STORAGE_FAILURE'));
    ASSERT outcome->>'state'='failed', 'Storage failure must remain retryable';
    outcome:=public.charts_assets('delete_progress',p,jsonb_build_object(
        'id','orphan-'||orphan,'completed',jsonb_build_array('object:'||orphan)));
    outcome:=public.charts_assets('delete_finish',p,jsonb_build_object('id','orphan-'||orphan));
    ASSERT outcome->>'state'='complete', 'Existing deletion worker must finish orphan jobs';
    ASSERT (SELECT state FROM charts.asset_objects WHERE project=p AND id=orphan)='deleted',
        'Completed cleanup must remove the readable object record';
    ASSERT (SELECT document->>'cosObject' FROM charts.boards WHERE project=p AND id='board')=current_doc,
        'Cleanup must not change the draft';
END $test$;
ROLLBACK;
