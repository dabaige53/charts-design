-- Fix qualification of local variables (only function parameters have the
-- implicit function label). Keep all existing reference/deletion safeguards.
DO $migration$
DECLARE definition text;
BEGIN
    definition := pg_get_functiondef('public.charts_assets(text,text,jsonb)'::regprocedure);
    definition := replace(definition, 'charts_assets.board', '(payload->>''board'')');
    definition := replace(definition, 'charts_assets.token', '(payload->>''token'')');
    definition := replace(definition,
        'DELETE FROM charts.batches b WHERE b.project=charts_assets.project AND b.board=(payload->>''board'');',
        'DELETE FROM charts.batches b WHERE b.project=charts_assets.project AND b.board=(payload->>''board'') AND b.base_revision=rev;');
    EXECUTE definition;
END $migration$;

-- New cloud projects use COS immediately. Existing projects retain their
-- recorded format until an explicit, verified migration switches references.
DO $migration$
DECLARE definition text;
BEGIN
    definition := pg_get_functiondef('public.charts_runtime(text,text,jsonb)'::regprocedure);
    IF position('new_project boolean' in definition) = 0 THEN
        definition := replace(definition, 'writing boolean;', 'writing boolean; new_project boolean;');
        definition := replace(definition,
            'SELECT format INTO fmt FROM charts.asset_state',
            'new_project := action=''ensure'' AND NOT EXISTS (SELECT 1 FROM charts.projects p WHERE p.name=project);
    SELECT format INTO fmt FROM charts.asset_state');
        definition := replace(definition,
            'IF action=''ensure'' THEN result:=result',
            'IF new_project THEN
        UPDATE charts.asset_state s SET format=''cos-v1'' WHERE s.project=charts_runtime.project;
        fmt:=''cos-v1'';
    END IF;
    IF action=''ensure'' THEN result:=result');
        IF position('IF new_project THEN' in definition) = 0 THEN
            RAISE EXCEPTION 'Runtime function differs; inspect before applying COS default';
        END IF;
        EXECUTE definition;
    END IF;
END $migration$;
