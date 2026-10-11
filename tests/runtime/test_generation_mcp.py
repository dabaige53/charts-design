"""Independent MCP caller: discover contracts, then author a report from blank."""
import asyncio
import json
import os
from pathlib import Path
import sys

import pytest

pytest.importorskip('mcp', reason='Install the optional official MCP SDK')
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_discover_and_author_independent_academic_report_over_stdio(tmp_path):
    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=['-m', 'dashboard_runtime', '--root', str(tmp_path / 'state'), 'mcp'],
            env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[2])},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                assert {'chart_declarations', 'generation_examples', 'dashboard_patch'} <= tools.keys()
                assert tools['generation_examples'].annotations.readOnlyHint is True
                assert tools['chart_declarations'].annotations.readOnlyHint is True
                resources = {str(resource.uri) for resource in (await session.list_resources()).resources}
                expected_resources = {'charts://declarations', 'charts://examples',
                    'charts://examples/academic-report', 'charts://examples/executive-dashboard'}
                assert expected_resources <= resources
                for uri in expected_resources:
                    result = await session.read_resource(uri)
                    assert result.contents[0].mimeType == 'application/json'
                    assert json.loads(result.contents[0].text)

                async def call(name, arguments):
                    result = await session.call_tool(name, arguments)
                    assert not result.isError, result
                    return result.structuredContent

                examples = await call('generation_examples', {})
                assert {case['track'] for case in examples['cases']} == {'dashboard', 'report'}
                case = await call('generation_examples', {'caseId': 'academic-report'})
                assert case['synthetic'] and case['operations'] and case['markdown']
                assert (await call('chart_declarations', {}))['summary'] is True
                selected = await call('chart_declarations', {'chartType': 'line'})
                assert selected['nativeCharts']['line']['example']['operations']
                # Reading guidance must not instantiate demo boards or add data.
                assert (await call('dashboard_list', {}))['dashboards'] == []
                created = (await call('dashboard_create', {'dashboardId': 'fresh-report',
                    'title': '独立合成样本分析'}))['document']
                assert created['revision'] == 1
                assert created['manifest']['components'] == {}
                assert created['snapshot']['datasets'] == {}

                markdown = '''# 独立合成样本分析

*——两个月的描述性协议验收样本*

**摘要：** 两个月合成收入分别为 10 和 15 万元，累计 25 万元，第二个月较第一个月增加 50%。[^source]

**关键词：** 合成数据；收入；描述性分析

## 数据与方法

使用本次独立编制的两行数据，收入按月求和。[^metric]

## 收入变化

如[图](#fig-trend)所示，收入由10万元增至15万元，增加5万元，增幅为50%。[^metric]

```chart
{"componentId":"trend","caption":"两个月的合成收入","source":"来源：独立验收合成快照 fresh-data；单位：万元。"}
```

## 结论与局限

本样本只有两个观测点，不支持因果推断或长期趋势判断。

## 附录：复核信息

- 2025-01：10万元；2025-02：15万元。
- 合计25万元；增幅＝（15－10）÷10＝50%。
- 筛选或更新数据后，应人工复核本文结论。

[^source]: 数据来源：本次协议验收显式编制的两行合成数据，不代表真实经营记录。
[^metric]: 收入口径：对 revenue 字段求和，单位万元；增长率＝（本期－上期）÷上期。
'''
                rows = [{'month': '2025-01', 'revenue': 10}, {'month': '2025-02', 'revenue': 15}]
                operations = [
                    {'op': 'put_source', 'id': 'fresh-source', 'value': {
                        'kind': 'fixture', 'name': 'Independent synthetic acceptance data'}},
                    {'op': 'put_dataset', 'id': 'fresh-data', 'meta': {
                        'sourceId': 'fresh-source', 'fields': {
                            'month': {'type': 'string'}, 'revenue': {'type': 'number'}}}, 'rows': rows},
                    {'op': 'put_metric', 'id': 'revenue', 'value': {
                        'datasetId': 'fresh-data', 'field': 'revenue', 'aggregation': 'sum',
                        'label': '收入', 'unit': '万元', 'definition': 'Sum of synthetic revenue',
                        'status': 'unverified'}},
                    {'op': 'put_component', 'id': 'trend', 'value': {
                        'kind': 'chart', 'title': '月度收入', 'datasetId': 'fresh-data',
                        'x': 'month', 'measures': ['revenue'], 'chartType': 'line'}},
                    {'op': 'set_report_markdown', 'value': markdown},
                    {'op': 'set_view_mode', 'value': 'report'},
                    {'op': 'set_status', 'value': 'fixture'},
                ]
                doc = (await call('dashboard_patch', {'dashboardId': 'fresh-report',
                    'expectedRevision': 1, 'operations': operations}))['document']
                assert doc['revision'] == 2
                assert doc['manifest']['viewMode'] == 'report'
                assert doc['manifest']['report']['markdown'] == markdown != case['markdown']
                assert doc['snapshot']['datasets']['fresh-data'] == rows
                assert (await call('dashboard_validate', {'dashboardId': 'fresh-report'}))['valid']
                for tool in ('dashboard_get', 'dashboard_preview'):
                    assert (await call(tool, {'dashboardId': 'fresh-report'}))['document'] == doc
                semantics = await call('semantic_inspect', {'dashboardId': 'fresh-report', 'componentId': 'trend'})
                assert semantics['metrics']['revenue']['definition'] == 'Sum of synthetic revenue'
                invalid = await session.call_tool('dashboard_patch', {'dashboardId': 'fresh-report',
                    'expectedRevision': 2, 'operations': [{'op': 'set_report_markdown',
                        'value': '```chart\n{"componentId":"missing"}\n```'}]})
                assert invalid.isError
                assert (await call('dashboard_get', {'dashboardId': 'fresh-report'}))['document'] == doc
                preview_uri = tools['dashboard_preview'].meta['ui']['resourceUri']
                preview_resource = await session.read_resource(preview_uri)
                assert preview_resource.contents[0].mimeType == 'text/html;profile=mcp-app'
                assert '<html' in preview_resource.contents[0].text.lower()
    asyncio.run(check())
