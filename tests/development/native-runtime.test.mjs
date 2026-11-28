import {test,afterEach} from 'bun:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,copyFileSync,writeFileSync,rmSync} from 'node:fs';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url),roots=[];
const original={binary:process.env.CHARTS_CORE_BIN,ui:process.env.CHARTS_UI_DIST};
afterEach(()=>{for(const dir of roots.splice(0))rmSync(dir,{recursive:true,force:true});for(const[key,value]of [['CHARTS_CORE_BIN',original.binary],['CHARTS_UI_DIST',original.ui]])if(value===undefined)delete process.env[key];else process.env[key]=value;});
function fixture(){const root=mkdtempSync(path.join(tmpdir(),'charts-native-'));roots.push(root);mkdirSync(path.join(root,'bin'));copyFileSync(new URL('../../bin/native-runtime.js',import.meta.url),path.join(root,'bin/native-runtime.js'));delete process.env.CHARTS_CORE_BIN;delete process.env.CHARTS_UI_DIST;return {root,runtime:require(path.join(root,'bin/native-runtime.js')).nativeRuntime};}
test('missing runtime fails explicitly without installing dependencies',()=>{const{runtime}=fixture();assert.throws(runtime,/Rust Runtime 尚未安装/);});
test('the package runtime and its UI share one installation root',()=>{const{root,runtime}=fixture();const dir=path.join(root,'runtime-core/native',`${process.platform}-${process.arch}`);mkdirSync(dir,{recursive:true});const name=`charts-design-core${process.platform==='win32'?'.exe':''}`;writeFileSync(path.join(dir,name),'native fixture');const result=runtime();assert.equal(result.binary,path.join(dir,name));assert.equal(result.env.CHARTS_PACKAGE_ROOT,root);assert.equal(result.env.CHARTS_UI_DIST,path.join(root,'runtime-ui/dist'));});
test('an explicit native binary and UI artifact can be selected for verification',()=>{const{root,runtime}=fixture();const binary=path.join(root,'candidate');writeFileSync(binary,'native fixture');process.env.CHARTS_CORE_BIN=binary;process.env.CHARTS_UI_DIST=path.join(root,'verified-ui');assert.equal(runtime().binary,binary);assert.equal(runtime().env.CHARTS_UI_DIST,process.env.CHARTS_UI_DIST);});
