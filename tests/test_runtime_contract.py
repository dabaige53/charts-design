from pathlib import Path
import json
import sys


SCRIPTS = Path(__file__).parents[1] / "skills" / "executive-charts" / "scripts"
sys.path.insert(0, str(SCRIPTS))

# Standalone skill modules need the source path installed above.
from generate_dashboard import CHARTS_MAP, generate_dashboard  # noqa: E402
from core.component_schemas import CHART_SCHEMA_REGISTRY, KPI_TYPES  # noqa: E402
from core.html_inspector import inspect_html  # noqa: E402
from test_generation import dashboard_config  # noqa: E402
from test_palette import run_renderer  # noqa: E402


def _generate(tmp_path, charts):
    output = tmp_path / "dashboard.html"
    generate_dashboard(
        config_dict={"meta": {"title": "Runtime contract"}, "charts": charts},
        output_path=str(output),
        allow_preset_fallback=False,
    )
    return output.read_text(encoding="utf-8")








# @wu-test type=integration | scope=图表实例ID | protects=业务指定ID在生成后丢失
def test_explicit_workspace_component_id_is_preserved(tmp_path):
    _generate(tmp_path, [{
        "id": "regional-sales",
        "code": "c01",
        "title": "Regional sales",
        "unit": "万元",
        "data": {"categories": ["华东"], "values": [10]},
    }])

    config = json.dumps(dashboard_config(tmp_path / "dashboard.html"), ensure_ascii=False)
    chart = run_renderer(f"const config = {config};" + """
const chart = new StateStore(config).config.charts[0];
console.log(JSON.stringify({id: chart.id, instanceId: chart.instanceId, code: chart.code}));
""")
    assert chart == {"id": "regional-sales", "instanceId": "regional-sales", "code": "c01"}


# @wu-test type=integration | scope=组件生成检查 | protects=支持组件生成后无法通过页面检查 | debt=D3
def test_every_registered_component_is_covered_by_schema_and_generated_html_gate(tmp_path):
    assert set(CHART_SCHEMA_REGISTRY) == set(CHARTS_MAP)
    assert KPI_TYPES == {f"mc{index:02d}" for index in range(1, 10)}

    output = tmp_path / "all-components.html"
    generate_dashboard(
        config_dict={"meta": {"title": "All components"}, "charts": list(CHARTS_MAP)},
        output_path=str(output),
        allow_preset_fallback=False,
    )

    inspection = inspect_html(output, strict=True)
    assert inspection["ok"] is True
