import assert from "node:assert/strict";
import {modelKeyFromSource,twoPartyMargin,assemble,totals,filterRows,exportCsv,signed} from "../public/results/desk-core.mjs";
import {normaliseClient} from "../public/results/live-adapter.mjs";
assert.equal(modelKeyFromSource("H-PA-07"),"PA-07");
assert.equal(modelKeyFromSource("H-AK-00"),"AK-01");
assert.equal(modelKeyFromSource("H-CA-00"),null);
assert.equal(modelKeyFromSource("S-OH-sp"),"OH-SEN");
assert.equal(modelKeyFromSource("G-TX"),null);
assert.equal(twoPartyMargin([{party:"D",votes:60},{party:"R",votes:40}]),20);
assert.equal(twoPartyMargin([{party:"I",votes:60},{party:"R",votes:40}]),null);
assert.equal(twoPartyMargin([{party:"D",votes:0},{party:"R",votes:0}]),null);
assert.equal(signed(null),"—");
const mock={races:Array.from({length:435},(_,i)=>({
  race_code:"ST-"+String(i+1).padStart(2,"0"),race_type:"house",state:"ST",
  district:String(i+1),dem_candidate:"Candidate D",rep_candidate:"Candidate R",
  forecast_margin_d_minus_r:3,dem_probability:.54
}))};
const observed={races:[{model_code:"ST-01",votes_total:100,
  candidates:[{party:"D",votes:60},{party:"R",votes:40}],
  leader:{name:"Candidate D",party:"D"},called:false,winner:null,called_by:null}]};
const rows=assemble(mock,observed),sum=totals(rows);
assert.equal(sum.reporting,1);
assert.equal(sum.called,0);
assert.equal(sum.house.calledD,0);
assert.equal(sum.leadsD,1);
assert.equal(rows[0].gap,17);
assert.equal(rows[1].votes,null);
assert.equal(rows[1].observed_margin,null);
assert.equal(filterRows(rows,{reported:true}).length,1);
assert.equal(filterRows(rows,{query:"ST-01"}).length,1);
assert.equal(filterRows(rows,{chamber:"senate"}).length,0);
const duplicate={races:[...observed.races,observed.races[0]]};
assert.equal(assemble(mock,duplicate)[0].observed,null,"Duplicate race mapping must not guess");
const csv=exportCsv(rows.slice(0,1));
assert.match(csv,/ST-01/);
const live=normaliseClient({generated_at:"2026-11-04T01:00:00Z",races:{
  "H-PA-07":{cands:[{name:"D",party:"D",votes:60},{name:"R",party:"R",votes:40}],called_by:"",url:"https://example.org"}
}});
assert.equal(live.races[0].votes_total,100);
assert.equal(live.races[0].called,false);
assert.equal(live.races[0].model_code,"PA-07");
const misleading=normaliseClient({races:{"S-OH-sp":{cands:[{name:"D",party:"D",votes:500,winner:true}],called_by:""}}});
assert.equal(misleading.races[0].called,false,"Winner flag without named caller is not a call");
console.log("Results Desk JavaScript invariants passed");
