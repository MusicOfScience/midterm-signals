import assert from "node:assert/strict";
import {SENATE_HOLDOVERS,controlDesk,reconcileReference} from "../public/results/control-core.mjs";
import {readFileSync} from "node:fs";
const benchmark=JSON.parse(readFileSync("public/data/newsroom-checkpoints.json","utf8"));
const at="2026-11-04T08:33:49.695Z";
function candidate(party,votes,win=false){return {party,name:party+" candidate",votes,winner:win}}
function race(chamber,index,party,called=true){
 const code=(chamber==="house"?"H-":"S-")+String(index).padStart(3,"0");
 const votes=called?1000:800;
 return {race_id:code,model_code:code,chamber,votes_total:votes,
  candidates:[candidate(party,700,called),candidate(party==="D"?"R":"D",votes-700)],
  leader:{party,name:"Leader"},winner:called?candidate(party,700,true):null,
  called,called_by:called?"civicAPI decision desk":null,
  source_updated_at:at};
}
const H=[
 ...Array.from({length:225},(_,i)=>race("house",i+1,"D")),
 ...Array.from({length:140},(_,i)=>race("house",i+226,"R")),
 ...Array.from({length:66},(_,i)=>race("house",i+366,i%2?"D":"R",false))
];
const S=[
 ...Array.from({length:20},(_,i)=>race("senate",i+1,"D")),
 ...Array.from({length:13},(_,i)=>race("senate",i+21,"R")),
 race("senate",34,"D",false),race("senate",35,"R",false)
];
const source={source:"civicAPI",source_updated_at:at,fetched_at:"2026-11-04T08:34:05Z",races:[...H,...S]};
const board=controlDesk(source);
assert.deepEqual(SENATE_HOLDOVERS,{D:34,R:31,democrats:32,independentCaucusD:2,total:65});
assert.equal(board.house.called,365);
assert.equal(board.house.D,225);
assert.equal(board.house.R,140);
assert.equal(board.house.uncalled,70);
assert.equal(board.house.verdict.party,"D");
assert.equal(board.house.segments.reduce((a,b)=>a+b.count,0),435);
assert.equal(board.senate.called,33);
assert.equal(board.senate.D,54);
assert.equal(board.senate.R,44);
assert.equal(board.senate.uncalled,2);
assert.equal(board.senate.verdict.party,"D");
assert.equal(board.senate.segments.reduce((a,b)=>a+b.count,0),100);
assert.equal(board.senate.leads.D,1);assert.equal(board.senate.leads.R,1);
const near=reconcileReference(source,benchmark);
assert.equal(near.state,"near-time-difference");
assert.equal(near.deltas.house.D,0);
assert.equal(near.deltas.house.R,3);
assert.equal(near.deltas.house.called,3);
assert.deepEqual(near.deltas.senate,{D:0,R:0,called:0});
assert.match(near.note,/cannot identify/);
const late={...source,source_updated_at:"2026-11-04T09:20:00Z"};
const historical=reconcileReference(late,benchmark);
assert.equal(historical.state,"historical-only");
assert.equal(historical.deltas,null);
assert.match(historical.note,/withheld/);
assert.equal(reconcileReference({source:"civicAPI",races:[]},benchmark).state,"source-unavailable");
assert.equal(reconcileReference(source,null).state,"reference-unavailable");
const noCalls=controlDesk({source:"thepeoplestally",races:[race("house",1,"D",false)]});
assert.equal(noCalls.house.D,0);
assert.equal(noCalls.house.uncalled,435);
assert.equal(noCalls.senate.D,34);
assert.equal(noCalls.senate.R,31);
assert.equal(noCalls.house.leads.D,1);
const noCaller=race("senate",1,"D");noCaller.called_by=null;
assert.equal(controlDesk({races:[noCaller]}).senate.called,0,"Unnamed calls cannot become wins");
const independent=race("senate",1,"I");
assert.equal(controlDesk({races:[independent]}).senate.other,1,"Do not invent independent caucus affiliation");
assert.equal(controlDesk({races:[independent]}).senate.D,34);
const duplicate=[race("house",7,"D"),race("house",7,"R")];
assert.equal(controlDesk({races:duplicate}).house.called,0,"Duplicate source keys must be suppressed");
assert.equal(controlDesk({races:[race("house",7,"D")],ambiguous_keys:["H-007"]}).house.called,0);
assert.equal(board.house.called+board.house.uncalled,435);
assert.equal(board.senate.called+board.senate.uncalled,35);
console.log("Results Desk v3 holdovers, thresholds, unresolved leads, timestamp guard and screenshot reconciliation passed");
