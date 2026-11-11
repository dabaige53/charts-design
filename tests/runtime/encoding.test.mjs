import { test } from 'bun:test';
import assert from 'node:assert/strict';
import {encodingRecords,encodingTable} from '../../dashboard_runtime/web/encoding.mjs';

const metric=field=>({field,aggregation:'sum',label:field});
function fixture(){
  return {manifest:{filters:[],metrics:{market:metric('market'),ho:metric('ho'),share:{aggregation:'ratio',numerator:'ho',denominator:'market'}},
    components:{plot:{datasetId:'data',binding:{categoryField:'od',measures:{x:'market',y:'ho',share:'share'},attributes:{grade:{field:'grade',aggregation:'unique'}}}}}},
    snapshot:{datasets:{data:[{od:'A',market:100,ho:10,grade:'好'},{od:'A',market:900,ho:180,grade:'好'},{od:'B',market:0,ho:0,grade:null}]}}};
}

// @wu-test type=behavior | scope=encodingRecords | protects=比例按百分比平均或空筛选产生虚假记录
test('ratios use grouped totals and retain missing values',()=>{
  const doc=fixture(),records=encodingRecords(doc,'plot');
  assert.deepEqual(records[0],{category:'A',series:null,values:{x:1000,y:190,share:.19,grade:'好'}});
  assert.equal(records[1].values.share,null);
  doc.manifest.filters=[{field:'od',op:'in',values:['absent'],componentIds:['plot']}];
  assert.deepEqual(encodingRecords(doc,'plot'),[]);
});

// @wu-test type=behavior | scope=encodingRecords | protects=更换维度或筛选后系列聚合错误
test('category and series grouping follow the selected dimension and filter',()=>{
  const doc=fixture();
  doc.manifest.components.plot.binding={categoryField:'region',seriesField:'product',measures:{value:'market'}};
  doc.snapshot.datasets.data=[{region:'North',product:'Coffee',agent:'Store A',market:0},{region:'South',product:'Tea',agent:'Store B',market:24},{region:null,product:'Cocoa',agent:'Store B',market:12}];
  assert.deepEqual(encodingRecords(doc,'plot').map(record=>record.category),['North','South',null]);
  doc.manifest.components.plot.binding.categoryField='agent';
  doc.manifest.filters=[{field:'agent',op:'in',values:['Store B'],componentIds:['plot']}];
  assert.deepEqual(encodingRecords(doc,'plot'),[
    {category:'Store B',series:'Tea',values:{value:24}},
    {category:'Store B',series:'Cocoa',values:{value:12}},
  ]);
});

// @wu-test type=behavior | scope=encodingRecords attributes | protects=冲突属性被误认为单一属性值
test('conflicting attributes remain missing',()=>{
  const doc=fixture();doc.snapshot.datasets.data[1].grade='different';
  assert.equal(encodingRecords(doc,'plot')[0].values.grade,null);
});

// @wu-test type=integration | scope=encodingTable | protects=转换表格时丢失度量属性或缺失值
test('table data preserves aggregated measures and attributes',()=>{
  const doc=fixture(),table=encodingTable(doc,'plot',encodingRecords(doc,'plot'));
  assert.deepEqual(table.headers,['od','market','ho','share','grade']);
  assert.deepEqual(table.rows,[['A',1000,190,.19,'好'],['B',0,0,null,null]]);
});
