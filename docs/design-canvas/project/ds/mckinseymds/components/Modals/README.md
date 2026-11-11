产品使用官方 Dialog；列配置在桌面使用 Sheet、窄屏使用 Drawer。各浮层提供标题与焦点管理。实现见 [产品 React 组件](../../react-ui.md)。

## PDF 来源参考

仅用于需要集中注意力的关键内容或任务；打开后阻止底层页面交互。

- 遮罩采用 Deep Blue 85% opacity；关闭入口、CTA 或按场景允许的遮罩点击可退出。
- 上下内边距 40px；桌面不超过屏幕的一半；移动端可更大并使用便于点击的 CTA。
- 顶部、内容、底部按需要出现；提供 Information、Success、Danger、Graphic 版本。

原始依据：PDF 第 52 页；来源 PDF 与原始画板保留在资产中。
