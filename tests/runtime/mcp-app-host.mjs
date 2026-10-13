// Acceptance fixture: official MCP Apps host bridge, not a replacement App SDK.
import {AppBridge,PostMessageTransport} from '../../runtime-ui/node_modules/@modelcontextprotocol/ext-apps/dist/src/app-bridge.js';
const frame=document.createElement('iframe');
frame.id='app';frame.title='Charts MCP App';frame.style='width:100%;height:900px;border:0';
frame.setAttribute('sandbox','allow-scripts allow-same-origin');document.body.append(frame);
const bridge=new AppBridge(null,{name:'Charts acceptance host',version:'1.0.0'},{serverTools:{}});
bridge.oncalltool=params=>window.mcpCallTool(params);
bridge.onrequestdisplaymode=async({mode})=>{
  document.body.dataset.displayMode=mode;
  bridge.setHostContext({displayMode:mode,availableDisplayModes:['inline','fullscreen']});
  return {mode};
};
bridge.oninitialized=async()=>{
  await bridge.sendToolInput({arguments:{dashboardId:'embedded'}});
  await bridge.sendToolResult(window.initialResult);
};
window.deliverToolResult=result=>bridge.sendToolResult(result);
await bridge.connect(new PostMessageTransport(frame.contentWindow,frame.contentWindow));
bridge.setHostContext({displayMode:'inline',availableDisplayModes:['inline','fullscreen']});
frame.src='/app';
