# 独立网页部署包


交付物：

- `dist/`：HTML、打包 JS/CSS、网页设计 JSON、数据分片；可部署到普通静态网站或 Cloudflare Pages。
- `site.zip`：只含可发布文件。
- 完整项目 ZIP：包含 dist、source、固定依赖与构建命令。
- `export-manifest.json`：看板版本、后端构建版本、所用数据集与记录数量。

网页无需 MCP、Codex、Python 或数据库服务。需要随看板版本实时更新、可分享并可撤销的在线预览时，使用 [自托管服务器](self-hosted-server.md)。筛选、同比环比、图表和表格计算沿用共享浏览器实现。数据集按可见组件加载，分片最多 4 个请求并行，同一数据集复用；首次使用一个数据集仍需读取其全部分片，之后筛选在本机计算。大数据集会占用浏览器内存，不等同于服务端按筛选取数。

数据包含页面使用的数据集全部记录，不局限于当前筛选；未使用的数据集不导出。默认移除批注和本机数据引用、来源连接及 SQL 参数。部署是只读设计，不提供在线编辑、批注写回或上游数据刷新。统计 SVG 为导出时结果。

页面保留“打印”按钮，Ctrl/Cmd+P 使用同一入口。打印前等待当前页面所有组件的数据分片、图表、字体和图片，不要求先滚动整页。直接使用浏览器菜单打印时，若数据尚未完成，打印预览只显示准备提示，不输出缺图页面；关闭窗口后使用页面打印按钮即可。

## 重建与发布

解压完整项目后，执行 `npm ci`、`npm run build`；构建只需 Node.js，无需原始 MCP 仓库。修改 `source/` 可更新网页实现，`dist/document.json` 保存设计与数据相对路径。通过 HTTP 服务预览，不能以 file:// 读取 JSON 分片。

上传 `dist/`，或执行 `npm run deploy:cloudflare -- --project-name <已有项目名>`。认证由部署环境提供，导出包不含认证信息。Cloudflare 的 [Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/) 支持预构建静态资源。

## 本次验收

真实看板 revision 29：独立静态服务下营业部由全部切换到西安，市场净销量从 998,140 更新为 28,629；页面未请求后端 API，无脚本错误。滚动触发下方数据加载。`npm ci` 与包内 `npm run build` 已完成。尚未上传 Cloudflare。
