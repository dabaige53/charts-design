# 更新 analyst-workspace 的本地 MCP

在 charts-design 本项目的 Codex 本地环境中执行 **更新 charts-design MCP**。analyst-workspace 是更新目标，不放置该操作按钮。
该操作从本仓源码构建并打包到本机 Documents 的现有工具目录，验证 MCP 启动和预览资源后，仅替换 analyst-workspace 的 `mcp_servers.charts-design.args[0]`。

- 继续使用原来的 Node 命令、启动参数、启用状态和看板数据目录。
- 不提交或推送 Git，不修改看板数据，不创建配置备份。
- 构建或启动检查失败时不切换配置；配置在构建期间发生变化时停止。
- 配置采用临时文件原子替换，完成后不保留临时配置。
- 已运行的 Codex 会话需重新连接 MCP 并重新打开预览。脚本不强行重启 Codex。

命令入口：

```bash
node bin/python-runtime.js bin/update_local_mcp.py --workspace /Users/w/code/analyst-workspace
```

## 测试取舍

按 Test Value Cleaner 清理，仅检查配置更新这一稳定合同：

- MERGE：单行与多行 TOML 参数归为同一项参数化检查，验证仅替换入口，其他服务器和数据目录不变。
- KEEP：拒绝未知入口，防止错误目标配置被修改。
- 复用已完成的真实 MCP 启动检查；不重复打包，不运行全仓测试，不新增界面截图或临时测试报告。

验证命令：`node bin/python-runtime.js -m pytest tests/test_local_mcp_update.py -q`。
