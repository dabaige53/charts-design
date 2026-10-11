"""All original renderers, explicitly labelled fixture data, never a live fallback."""
import copy
import json
from pathlib import Path
import subprocess
import sys
from dashboard_runtime.model import new_document, apply_operations
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'skills/executive-charts/scripts'))
from generate_dashboard import CHARTS_MAP
from core.component_schemas import CHART_PRESENTATION_CONTRACTS, CHART_TABLE_HEADER_COUNTS

def configurations():
    source='const c={'+','.join(json.dumps(k)+':('+v+')' for k,v in CHARTS_MAP.items())+'};console.log(JSON.stringify(c));'
    charts=json.loads(subprocess.run(['node'],input=source,capture_output=True,text=True,check=True).stdout)
    for code,c in charts.items():
        c['code']=code;c['unit']='fixture';d=c['data'];con=CHART_PRESENTATION_CONTRACTS[code]
        p={'axisLabels':{k:'统计维度' if k=='x' else '示例数值' for k in con['axis']}}
        for key,n in [('seriesLabels',con['series']),('tooltipValueLabels',con['tooltip']),('units',con['units']),('labels',con.get('labels',0))]:
            n=len(d.get('lines',[])) if n=='lines' else n
            p[key]=[('fixture' if key=='units' else '示例 '+str(i+1)) for i in range(n)]
        n=CHART_TABLE_HEADER_COUNTS[code]
        if isinstance(n,str):n=len(d[n.split('+')[0]])+1
        p['tableHeaders']=['字段 '+str(i+1) for i in range(n)]
        for parent,key in con.get('numeric',[]):p.setdefault(parent,{})[key]=50
        for parent,key in con.get('domain',[]):
            p.setdefault(parent,{})[key]=[[0,v.get('max',100)] for v in d['indicators']] if code=='r05' else ([-1,1] if code=='r03' else [0,100])
        c['presentation']=p
    return charts

def document():
    charts=configurations();ops=[{'op':'put_source','id':'catalog-fixture','value':{'kind':'fixture','name':'Explicit original catalog demonstration values'}},{'op':'set_status','value':'fixture'}]
    for i in range(1,10):
        code='mc%02d'%i
        config={'id':code,'type':code,'label':code.upper()+' 指标卡','value':'86.5%','yoy':'+2.1 pts','mom':'+0.5 pts','isPositive':True,'subLabel':'同期基准','subVal':'84.4%','statusBadge':'示例','sparkMonths':['1','2','3','4','5'],'sparkData':[70,78,74,82,86.5],'leftVal':'120','rightVal':'104','leftLabel':'示例指标 A','rightLabel':'示例指标 B','percent':86.5,'trendLabel':'示例趋势','rankBadge':'示例等级','thresholdLabel':'示例阈值','segLeftWidth':'60%','segRightWidth':'40%'}
        ops.append({'op':'put_component','id':code,'value':{'kind':'legacy','family':'kpi','title':config['label'],'config':config,'sourceId':'catalog-fixture'}})
    for code,c in sorted(charts.items()):ops.append({'op':'put_component','id':code,'value':{'kind':'legacy','family':'chart','title':c['title'],'config':c,'sourceId':'catalog-fixture'}})
    doc=apply_operations(new_document('all-components','原版组件全量验收 / 40 + 9'),ops)
    for bp,cols in [('desktop',12),('tablet',8),('mobile',4)]:
        positions=[];y=0;x=0;rowh=0
        for key,c in doc['manifest']['components'].items():
            w=cols if bp=='mobile' else (4 if c['family']=='kpi' and bp=='desktop' else cols//2)
            h=5 if c['family']=='kpi' else 10
            if x+w>cols:y+=rowh;x=rowh=0
            positions.append({'id':key,'x':x,'y':y,'w':w,'h':h});x+=w;rowh=max(rowh,h)
        doc=apply_operations(doc,[{'op':'set_layout','breakpoint':bp,'value':positions}])
    return doc
