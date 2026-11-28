#!/usr/bin/env node
try {
  const args = process.argv.slice(2);
  if (args[0] === 'install-native') {
    if (args.length !== 1) throw Error('用法：charts-design-runtime install-native');
    import('./install-native.mjs').then(({ensureNative}) => ensureNative({root: require('node:path').resolve(__dirname, '..')}))
      .then(receipt => console.log(receipt.skipped ? '已按 CHARTS_SKIP_NATIVE_INSTALL 跳过原生安装。'
        : `Rust Runtime ${receipt.version} ${receipt.reused ? '已就绪' : '已安装'}。`))
      .catch(error => {console.error(error.message); process.exitCode = 1;});
  } else if (require('./native-runtime.js').nativeCommand(args) === 'mcp') require('./mcp-runtime.js').runMcp(args);
  else require('./native-runtime.js').runNative(args);
} catch (error) { console.error(error.message); process.exitCode = 1; }
