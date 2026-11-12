# 独立静态网页导出

调用 `dashboard_export_site`，传入 `projectRoot` 与 `dashboardId`，取得受管 ZIP。网页使用与 MCP 相同的 React 组件和共享查询 Worker，通过普通静态 HTTP 服务提供，不连接 MCP。

## 文件结构

| 文件 | 用途 |
| --- | --- |
| `index.html` | 静态网页入口 |
| `app.js`、`app.css` | 已构建的应用与样式 |
| `static-worker.js` | 筛选、汇总、表格搜索、排序和分页 |
| `document.json` | 组件、布局、指标和数据分片相对路径 |
| `data/*.json.gz` | 使用中的数据集，每片最多 5000 条，解压后的 JSON 不超过 16 MiB |
| `export-manifest.json` | 看板 revision、前后端构建标识、数据集记录数 |
| `README.txt` | 使用方式和数据范围 |

ZIP 保存于运行目录 `exports/<id>/<dashboardId>.zip`。MCP 内使用 `dashboard_export_read` 分块读取并核对完整字节数，再交给宿主下载。服务器下载链接沿用受管导出授权，见 [自托管服务器](self-hosted-server.md)。

## 数据和操作

导出包含页面使用的数据集全部记录；未使用的数据集不导出。来源连接、SQL、本机数据引用和批注会被移除。统计图保留导出时生成的结果。

多页云分享在同一个副本中复用内容完全相同的数据分片，页面继续按各自的字段与指标定义读取，避免重复上传相同分片。

已迁移到 `cos-v1` 的云项目创建新分享时，使用相同的网页查询 worker 和版本描述，数据文件经私有网关复用项目的不可变 COS 包。离线部署使用包含实际数据文件的 ZIP 导出。历史分享继续使用创建时的格式。

网页按组件加载所需数据集，同一数据集复用。首次使用一个数据集需要读取它的全部分片，之后在本机计算筛选、图表和表格。读者可以搜索、排序、分页、调整临时列配置和导出 CSV。布局和设计只读；数据更新需重新导出。

## 构建与使用

已安装的交付包包含 UI 资源，直接导出。仅从源码本地运行且需要准备资源时执行：

```sh
bun install --cwd runtime-ui --frozen-lockfile
bun run ui:prepare
```

然后导出 ZIP，解压并把内容放入普通静态 HTTP 服务。通过 `index.html` 访问；`file://` 无法读取 Worker 和 JSON 分片。导出包已包含运行资源，部署时无需安装 Bun、Python 或原始仓库。

HTML 快照与静态网页用途不同：`dashboard_export` 的 HTML 仅保存当前计算视图；静态网页保存使用中的完整数据集，可以继续在浏览器中筛选。
