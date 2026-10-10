import json
from pathlib import Path
import pytest
from dashboard_runtime.legacy import REPO,render

@pytest.mark.skipif(not (REPO/'skills/executive-charts/scripts/generate_chart.py').exists(),reason='Original repository is needed for legacy adapter acceptance')
def test_legacy_template_uses_explicit_data():
    config={'id':'regions','code':'c01','title':'Real values <not markup>','unit':'USD',
        'data':{'categories':['East','South'],'values':[12,10],'unit':'USD'},
        'presentation':{'axisLabels':{'x':'Revenue','y':'Region'},'seriesLabels':['Revenue'],
        'tooltipValueLabels':['Revenue'],'units':['USD'],'tableHeaders':['Region','Revenue']}}
    html=render(config)
    assert '__CHART_CONFIG_JS__' not in html
    assert 'Real values &lt;not markup&gt;' in html
    assert 'Content-Security-Policy' in html

    assert 'echarts@6.1.0/' in html
    assert 'echarts@5.5.0/' not in html
