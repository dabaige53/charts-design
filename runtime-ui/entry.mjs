import * as echarts from 'echarts/core';
import {BarChart,LineChart,PieChart,ScatterChart,BoxplotChart,FunnelChart,GaugeChart,GraphChart,HeatmapChart,RadarChart,SankeyChart,SunburstChart,TreemapChart} from 'echarts/charts';
import {GridComponent,TooltipComponent,LegendComponent,TitleComponent,DataZoomComponent,VisualMapComponent,MarkLineComponent,MarkAreaComponent,MarkPointComponent,ToolboxComponent,DatasetComponent,TransformComponent,GraphicComponent,AriaComponent,RadarComponent,PolarComponent} from 'echarts/components';
import {LabelLayout,UniversalTransition,LegacyGridContainLabel,AxisBreak,ScatterJitter} from 'echarts/features';
import {CanvasRenderer,SVGRenderer} from 'echarts/renderers';
echarts.use([BarChart,LineChart,PieChart,ScatterChart,BoxplotChart,FunnelChart,GaugeChart,GraphChart,HeatmapChart,RadarChart,SankeyChart,SunburstChart,TreemapChart,GridComponent,TooltipComponent,LegendComponent,TitleComponent,DataZoomComponent,VisualMapComponent,MarkLineComponent,MarkAreaComponent,MarkPointComponent,ToolboxComponent,DatasetComponent,TransformComponent,GraphicComponent,AriaComponent,RadarComponent,PolarComponent,LabelLayout,UniversalTransition,LegacyGridContainLabel,AxisBreak,ScatterJitter,CanvasRenderer,SVGRenderer]);
import { GridStack } from 'gridstack';
import { App } from '@modelcontextprotocol/ext-apps';
import 'gridstack/dist/gridstack.min.css';
import '../dashboard_runtime/web/styles.css';
import '../dashboard_runtime/web/icons.css';
import '../dashboard_runtime/web/original-global.css';
import { start } from '../dashboard_runtime/web/app.mjs';
start({echarts,GridStack,App}).catch(error=>{
  const pre=document.createElement('pre');pre.textContent=error.message;document.body.append(pre);
});
