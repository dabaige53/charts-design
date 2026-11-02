import {App, McpUiInitializeResultSchema} from '@modelcontextprotocol/ext-apps';
// SDK 1.1.2 strips unknown experimental capabilities. Preserve vendor keys
// while retaining validation of the standard initialization result.
const capabilities=McpUiInitializeResultSchema.shape.hostCapabilities;
const initializeResult=McpUiInitializeResultSchema.extend({hostCapabilities:capabilities.extend({
  experimental:capabilities.shape.experimental.unwrap().passthrough().optional()
})});
export class HostApp extends App {
  request(request,schema,options){
    return super.request(request,request.method==='ui/initialize'?initializeResult:schema,options);
  }
}
export {initializeResult};
