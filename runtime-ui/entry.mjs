import * as echarts from './echarts.mjs';
import { GridStack } from 'gridstack';
import { HostApp as App } from './host-app.mjs';
import 'gridstack/dist/gridstack.min.css';
import '../dashboard_runtime/web/styles.css';
import '../dashboard_runtime/web/icons.css';
import '../dashboard_runtime/web/original-global.css';
import '../dashboard_runtime/web/reviews.css';
import { configureAnnotationCharts } from '../dashboard_runtime/web/annotation-points.mjs';
import { start } from '../dashboard_runtime/web/app.mjs';
configureAnnotationCharts(echarts);
start({echarts,GridStack,App}).catch(error=>{
  const pre=document.createElement('pre');pre.textContent=error.message;document.body.append(pre);
});
