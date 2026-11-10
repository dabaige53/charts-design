import csv
import io
from pathlib import Path

import pytest

from dashboard_runtime.demo import document
from dashboard_runtime.model import DashboardError, validate
from dashboard_runtime.service import Service


# @wu-test type=boundary | scope=搜索筛选 | protects=非字符串多值或数值字段搜索被接受
def test_search_contract_rejects_wrong_values_and_fields():
    for field, values in [("region", [2]), ("region", ["a", "b"]), ("revenue", ["8"])]:
        doc = document()
        doc["manifest"]["filters"] = [
            {"id": "search", "op": "contains", "field": field, "values": values, "componentIds": ["total"]}
        ]
        with pytest.raises(DashboardError):
            validate(doc)


# @wu-test type=integration | scope=搜索筛选与CSV导出 | protects=多数据集筛选候选漏项或导出未遵守搜索范围
def test_filters_union_search_and_table_export(tmp_path):
    doc = document()
    doc["manifest"]["datasets"]["other"] = doc["manifest"]["datasets"]["sales"].copy()
    doc["snapshot"]["datasets"]["other"] = [
        dict(doc["snapshot"]["datasets"]["sales"][0], region="North")
    ]
    doc["manifest"]["components"]["details"]["datasetId"] = "other"
    doc["manifest"]["filters"].append({
        "id": "search", "op": "contains", "field": "region", "values": [],
        "componentIds": ["total", "load", "trend", "regions", "details"],
    })
    service = Service(tmp_path / "state")
    service.store.create("demo", "Demo", doc)
    options = service.call("dashboard_filter_options", {"dashboardId": "demo", "filterId": "region"})
    assert "North" in options["values"]
    filters = [{**item, "values": ["nor"]} if item["id"] == "search" else item for item in doc["manifest"]["filters"]]
    result = service.call("dataset_export", {
        "dashboardId": "demo", "componentId": "details", "filters": filters, "columns": ["region", "revenue"],
    })["export"]
    content = Path(result["path"]).read_text(encoding="utf-8-sig")
    assert list(csv.DictReader(io.StringIO(content))) == [{"region": "North", "revenue": "80"}]
    assert service.store.get("demo")["revision"] == 1
    assert service.store.get("demo")["manifest"]["filters"] == doc["manifest"]["filters"]
