import json
from pathlib import Path
import subprocess
import sys


SCRIPTS = Path(__file__).parents[1] / "skills" / "executive-charts" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core.runtime_bundle import render_runtime_bundle


def _run_lifecycle_scenario(script):
    runtime = render_runtime_bundle().split("// runtime:bootstrap", 1)[0]
    program = f"""
const document = {{ name: 'document' }};
const window = {{ DASHBOARD_CONFIG: {{ id: 'fallback' }} }};
const constructions = [];
class DashboardApp {{
  constructor(config, root) {{
    this.config = config;
    this.root = root;
    this._mounted = false;
    constructions.push({{ config, root }});
  }}
  init() {{ this._mounted = true; return this; }}
  destroy() {{ this._mounted = false; }}
}}
{runtime}
{script}
"""
    completed = subprocess.run(
        ["node", "-e", program],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_runtime_preserves_explicit_root_across_update_destroy_and_remount():
    result = _run_lifecycle_scenario(
        """
const root = { name: 'dashboard-root' };
const runtime = window.createDashboardRuntime({ id: 'first' }, root);
const first = runtime.mount();
const second = runtime.update({ id: 'second' });
runtime.destroy();
const third = runtime.mount();
console.log(JSON.stringify({
  runtimeRoot: runtime.root.name,
  roots: constructions.map(item => item.root?.name),
  configs: constructions.map(item => item.config.id),
  identities: [first === second, second === third],
  mounted: [first._mounted, second._mounted, third._mounted]
}));
"""
    )

    assert result == {
        "runtimeRoot": "dashboard-root",
        "roots": ["dashboard-root", "dashboard-root", "dashboard-root"],
        "configs": ["first", "second", "second"],
        "identities": [False, False],
        "mounted": [False, False, True],
    }


def test_scoped_runtime_does_not_replace_document_singleton():
    result = _run_lifecycle_scenario(
        """
const documentRuntime = window.createDashboardRuntime({ id: 'document' }, document);
const documentApp = documentRuntime.mount();
const scopedRoot = { name: 'scoped-root' };
const scopedRuntime = window.createDashboardRuntime({ id: 'scoped' }, scopedRoot);
const scopedApp = scopedRuntime.mount();
scopedRuntime.destroy();
console.log(JSON.stringify({
  documentSingletonPreserved: window.App === documentApp,
  scopedWasDistinct: scopedApp !== documentApp,
  scopedDestroyed: scopedApp._mounted === false
}));
"""
    )

    assert result == {
        "documentSingletonPreserved": True,
        "scopedWasDistinct": True,
        "scopedDestroyed": True,
    }


def test_element_resolution_returns_the_app_owned_by_each_root():
    result = _run_lifecycle_scenario(
        """
const leftRoot = { name: 'left', parentNode: null };
const rightRoot = { name: 'right', parentNode: null };
const leftChild = { parentNode: leftRoot };
const rightChild = { parentNode: rightRoot };
const leftRuntime = window.createDashboardRuntime({ id: 'left-app' }, leftRoot);
const rightRuntime = window.createDashboardRuntime({ id: 'right-app' }, rightRoot);
const leftApp = leftRuntime.mount();
const rightApp = rightRuntime.mount();
leftRoot.__dashboardApp = leftApp;
rightRoot.__dashboardApp = rightApp;
console.log(JSON.stringify({
  left: window.getDashboardAppForElement(leftChild).config.id,
  right: window.getDashboardAppForElement(rightChild).config.id,
  distinct: window.getDashboardAppForElement(leftChild) !== window.getDashboardAppForElement(rightChild)
}));
"""
    )

    assert result == {"left": "left-app", "right": "right-app", "distinct": True}
