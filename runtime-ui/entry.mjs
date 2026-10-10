import * as echarts from 'echarts';
import { GridStack } from 'gridstack';
import { App } from '@modelcontextprotocol/ext-apps';
import 'gridstack/dist/gridstack.min.css';
import '../dashboard_runtime/web/styles.css';
import '../dashboard_runtime/web/original-global.css';
import { start } from '../dashboard_runtime/web/app.mjs';
start({echarts,GridStack,App}).catch(error=>{
  const pre=document.createElement('pre');pre.textContent=error.message;document.body.append(pre);
});
