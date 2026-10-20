"""Refreshing uses current definitions and preserves unsaved reader selections."""
import copy

import pytest

from dashboard_runtime.model import DashboardError

from dashboard_runtime.demo import document
from dashboard_runtime.service import Service


def test_refresh_uses_latest_filter_labels_without_saving_reader_values(tmp_path):
    service = Service(tmp_path)
    doc = service.store.create('refresh', 'Refresh', document())
    reader = copy.deepcopy(doc['manifest']['filters'])
    reader[0]['values'] = ['East']
    latest = copy.deepcopy(doc['manifest']['filters'])
    latest[0]['label'] = '区域'
    updated = service.call('dashboard_patch', {'dashboardId': 'refresh', 'expectedRevision': doc['revision'],
                           'operations': [{'op': 'set_filters', 'value': latest}]})['document']
    result = service.call('dashboard_refresh', {'dashboardId': 'refresh', 'filters': reader})['document']
    assert result['revision'] == updated['revision']
    assert result['manifest']['filters'][0]['label'] == '区域'
    assert result['manifest']['filters'][0]['values'] == ['East']
    assert result['computed']['components']['total']['value'].startswith('278')
    saved = service.store.get('refresh', hydrate=False)
    assert saved['manifest']['filters'][0]['values'] == []
    info = service.call('runtime_info', {'dashboardId': 'refresh'})
    assert info['dashboardRevision'] == updated['revision']
    assert len(info['uiBuildId']) == 12


def test_refresh_rejects_invalid_single_selection_and_malformed_ids(tmp_path):
    service = Service(tmp_path)
    doc = document()
    doc['manifest']['filters'][0]['selectionMode'] = 'single'
    service.store.create('single', 'Single', doc)
    for overrides in [[{'id': [], 'values': []}], [{'id': doc['manifest']['filters'][0]['id'], 'values': ['East', 'West']}]]:
        with pytest.raises(DashboardError):
            service.call('dashboard_refresh', {'dashboardId': 'single', 'filters': overrides})
