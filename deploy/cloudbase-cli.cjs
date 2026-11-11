// Pass sensitive CLI arguments through stdin, never through the OS command line.
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const cli = require.resolve('@cloudbase/cli', { paths: [process.argv[2]] });
process.env.CI = '1';
process.env.CLOUDBASE_CI = '1';
process.argv = [process.execPath, cli, ...input.args];
require(cli);
