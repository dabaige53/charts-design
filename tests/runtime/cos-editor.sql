-- @wu-test type=integration | scope=charts_assets/charts_runtime | protects=删除预览变量解析失败或误删其他页面及草稿，新项目未使用COS
BEGIN;
SELECT set_config('request.jwt.claims', '{"role":"service_role"}', true);
DO $test$
DECLARE p text := 'cos-editor-test-' || md5(random()::text);
    result jsonb;
BEGIN
    result := public.charts_runtime('ensure',p,'{"config":{}}');
    ASSERT result->>'storageFormat'='cos-v1', 'New project must default to COS';
    INSERT INTO charts.boards(project,id,document) VALUES
        (p,'a','{"id":"a","revision":3,"manifest":{"title":"Draft"},"snapshot":{}}'),
        (p,'b','{"id":"b","revision":1,"manifest":{"title":"Other"},"snapshot":{}}');
    INSERT INTO charts.revisions(project,board,revision,document,created_at,action) VALUES
        (p,'a',1,'{"id":"a","revision":1,"snapshot":{}}','2026-11-12','test'),
        (p,'a',2,'{"id":"a","revision":2,"snapshot":{}}','2026-11-12','test'),
        (p,'b',1,'{"id":"b","revision":1,"snapshot":{}}','2026-11-12','test');
    INSERT INTO charts.version_heads VALUES(p,'a',1);
    INSERT INTO charts.batches VALUES(p,'a','current-edit',2);
    result := public.charts_assets('delete_preview',p,'{"board":"a","revision":1,"expected":3,"token":"test-plan"}');
    ASSERT (result->>'nextSavedRevision')::bigint=2, 'Retain latest saved version';
    ASSERT (result->>'clearsPublication')::boolean, 'Report publication removal';
    result := public.charts_assets('delete_begin',p,'{"board":"a","revision":1,"expected":3,"token":"test-plan"}');
    ASSERT result->>'state'='deleting', 'Start persisted deletion';
    result := public.charts_assets('delete_finish',p,'{"id":"test-plan"}');
    ASSERT result->>'state'='complete', 'Finish persisted deletion';
    ASSERT NOT EXISTS(SELECT 1 FROM charts.revisions WHERE project=p AND board='a' AND revision=1), 'Old version deleted';
    ASSERT EXISTS(SELECT 1 FROM charts.revisions WHERE project=p AND board='a' AND revision=2), 'Latest version retained';
    ASSERT EXISTS(SELECT 1 FROM charts.revisions WHERE project=p AND board='b' AND revision=1), 'Other page retained';
    ASSERT (SELECT document->>'revision' FROM charts.boards WHERE project=p AND id='a')='3', 'Draft retained';
    ASSERT EXISTS(SELECT 1 FROM charts.batches WHERE project=p AND board='a' AND batch_id='current-edit'), 'Current edit batch retained';
END $test$;
ROLLBACK;
