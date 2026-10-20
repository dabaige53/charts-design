"""Single selection remains a server-side constraint as well as a UI control."""
import copy

import pytest

from dashboard_runtime.demo import document
from dashboard_runtime.model import DashboardError, apply_operations


def test_single_filter_rejects_multiple_values_and_can_clear():
    doc = document()
    filters = copy.deepcopy(doc['manifest']['filters'])
    filters[0]['selectionMode'] = 'single'
    filters[0]['values'] = ['East', 'West']
    with pytest.raises(DashboardError, match='at most one value'):
        apply_operations(doc, [{'op': 'set_filters', 'value': filters}])
    for values in [['East'], []]:
        filters[0]['values'] = values
        result = apply_operations(doc, [{'op': 'set_filters', 'value': filters}])
        assert result['manifest']['filters'][0]['values'] == values
