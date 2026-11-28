// npm/npx prepares the pinned runtime at install time, before any MCP session.
import {fileURLToPath} from 'node:url';
import {ensureNative} from './install-native.mjs';

try {
  const receipt = await ensureNative({root: fileURLToPath(new URL('..', import.meta.url))});
  if (!receipt.skipped) console.log(`Charts Design Rust Runtime ${receipt.version} ${receipt.reused ? '已就绪' : '已安装'}。`);
} catch (error) {
  console.error(`${error.message}\n可安装后显式运行 charts-design-runtime install-native；源码开发使用 bun run setup 和 bun run native:build。`);
  process.exitCode = 1;
}
