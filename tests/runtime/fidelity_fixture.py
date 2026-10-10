"""Explicit review fixture from the original catalog. Never used as live data."""
import copy
import json
from pathlib import Path
import subprocess
import sys
from dashboard_runtime.model import apply_operations,new_document

SCRIPTS=Path(__file__).resolve().parents[2]/'skills'/'executive-charts'/'scripts'
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
from generate_dashboard import CHARTS_MAP,PRESET_CONFIGS

def document(board_id='original-review'):
    selected=['t06','c01','c02','c08']
    code='const charts={'+','.join(json.dumps(k)+':('+CHARTS_MAP[k]+')' for k in selected)+'}; console.log(JSON.stringify(charts));'
    charts=json.loads(subprocess.run(['node','-e',code],capture_output=True,text=True,check=True).stdout)
    preset=copy.deepcopy(PRESET_CONFIGS['executive_report'])
    ops=[{'op':'put_source','id':'original-fixture','value':{'kind':'fixture','name':'Original charts-design catalog preview values; not real business data'}},{'op':'set_status','value':'fixture'}]
    for i,card in enumerate(preset['kpis']):
        if card['type']=='mc03':card['sparkData']=card['sparkline'];card['sparkMonths']=[str(i+1) for i in range(len(card['sparkData']))]
        if card['type']=='mc04':card['value']='86.5%'
        ops.append({'op':'put_component','id':card['id'],'value':{'kind':'legacy','family':'kpi','title':card['label'],'config':card,'sourceId':'original-fixture'}})
    for k in selected:
        c=charts[k];c['unit']='\u4ebf\u5143'
        p={'axisLabels':{'x':'\u7edf\u8ba1\u5468\u671f' if k=='t06' else '\u4e1a\u52a1\u57fa\u5730','y':'\u5ba2\u8fd0\u6536\u5165'},'seriesLabels':['\u5ba2\u8fd0\u6536\u5165'],'tooltipValueLabels':['\u5ba2\u8fd0\u6536\u5165'],'units':['\u4ebf\u5143'],'tableHeaders':['\u4e1a\u52a1\u57fa\u5730','\u5ba2\u8fd0\u6536\u5165 (\u4ebf\u5143)']}
        if k=='t06':p.update(axisLabels={'x':'\u7edf\u8ba1\u5468\u671f','leftY':'\u5ba2\u8fd0\u6536\u5165','rightY':'\u6536\u76ca\u589e\u957f'},seriesLabels=['\u5ba2\u8fd0\u6536\u5165','\u6536\u76ca\u589e\u957f'],tooltipValueLabels=['\u5ba2\u8fd0\u6536\u5165','\u6536\u76ca\u589e\u957f'],units=['\u4ebf\u5143','%'],tableHeaders=['\u5468\u671f','\u5ba2\u8fd0\u6536\u5165 (\u4ebf\u5143)','\u6536\u76ca\u589e\u957f (%)'])
        if k=='c02':p['axisLabels']={'x':'\u5ba2\u8fd0\u6536\u5165','y':'\u673a\u578b'};p['tableHeaders'][0]='\u673a\u578b'
        if k=='c08':p.update(seriesLabels=['\u56fd\u5185','\u56fd\u9645'],tooltipValueLabels=['\u56fd\u5185\u6536\u5165','\u56fd\u9645\u6536\u5165'],units=['\u4ebf\u5143','\u4ebf\u5143'],tableHeaders=['\u4e1a\u52a1\u57fa\u5730','\u56fd\u5185\u6536\u5165','\u56fd\u9645\u6536\u5165','\u5408\u8ba1'])
        c['presentation']=p
        ops.append({'op':'put_component','id':k,'value':{'kind':'legacy','family':'chart','title':c['title'],'config':c,'sourceId':'original-fixture'}})
    ops.append({'op':'put_component','id':'original-table','value':{'kind':'legacy','family':'table','title':preset['table']['title'],'config':preset['table'],'sourceId':'original-fixture'}})
    doc=apply_operations(new_document(board_id,'\u822a\u7ebf\u4e0e\u673a\u961f\u8fd0\u8425\u5206\u6790 \u00b7 \u539f\u7248\u7ec4\u4ef6\u9a8c\u6536'),ops)
    for bp,cols in [('desktop',12),('tablet',8),('mobile',4)]:
        positions=[];x=y=h=0
        for key,c in doc['manifest']['components'].items():
            w=(cols//4 if bp=='desktop' else cols//2) if c['family']=='kpi' else (cols if c['family']=='table' else cols//2)
            if bp=='mobile':w=cols
            height=4 if c['family']=='kpi' else 12 if c['family']=='table' else 8
            if x+w>cols:y+=h;x=h=0
            positions.append({'id':key,'x':x,'y':y,'w':w,'h':height});x+=w;h=max(h,height)
        doc=apply_operations(doc,[{'op':'set_layout','breakpoint':bp,'value':positions}])
    return doc
