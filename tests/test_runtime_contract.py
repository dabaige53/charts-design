from pathlib import Path
import sys


SCRIPTS = Path(__file__).parents[1] / "skills" / "executive-charts" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from generate_dashboard import CHARTS_MAP, generate_dashboard
from core.component_schemas import CHART_SCHEMA_REGISTRY, KPI_TYPES
from core.html_inspector import inspect_html


def _generate(tmp_path, charts):
    output = tmp_path / "dashboard.html"
    generate_dashboard(
        config_dict={"meta": {"title": "Runtime contract"}, "charts": charts},
        output_path=str(output),
        allow_preset_fallback=False,
    )
    return output.read_text(encoding="utf-8")


def test_duplicate_chart_codes_use_instance_identity_in_dom_registry_and_actions(tmp_path):
    html = _generate(tmp_path, ["c01", "c01"])

    assert "chart-c01-1" in html
    assert "chart-c01-2" in html
    assert 'data-component-id="${chart.instanceId}"' in html
    assert 'data-card-code="${chart.instanceId}"' not in html
    assert "this.state.chartInstances[chartCfg.instanceId] = inst" in html


def test_generated_html_exposes_idempotent_runtime_lifecycle(tmp_path):
    html = _generate(tmp_path, ["c01"])

    assert "window.createDashboardRuntime" in html
    assert "createDashboardRuntime(initialConfig, root = document)" in html
    assert "mount(root = this.root, config = this.config)" in html
    assert "this.root = root" in html
    assert "new DashboardApp(this.config, root)" in html
    assert "window.getDashboardAppForElement" in html
    assert "this.root.__dashboardApp = this" in html
    assert "window.App." not in html
    assert "update(config, root = this.root)" in html
    assert "destroy()" in html
    assert "this._mounted" in html
    assert "inst?.dispose()" in html


def test_cross_filter_uses_canonical_state_field(tmp_path):
    html = _generate(tmp_path, ["c01"])

    assert "this.state.chartCrossFilter = val" in html
    assert "this.state.chartCrossFilter = null" in html
    assert "this.state.filters.chartCrossFilter =" not in html


def test_explicit_workspace_component_id_is_preserved(tmp_path):
    html = _generate(tmp_path, [{
        "id": "regional-sales",
        "code": "c01",
        "title": "Regional sales",
        "unit": "万元",
        "data": {"categories": ["华东"], "values": [10]},
    }])

    assert "const requestedId = chart.instanceId || chart.id ||" in html


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
