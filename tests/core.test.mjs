import assert from 'node:assert/strict';
import {probabilityFromMargin,filterRaces,runScenario,searchRecords,buildElectionSummary} from '../public/core.mjs';
assert(Math.abs(probabilityFromMargin(0,6)-.5)<.001);
assert(probabilityFromMargin(6,6)>.8);
const model={summary:{house:{expected_dem_seats:220},senate:{expected_dem_seats:50,fixed_not_up_dem_seats:34}},races:[
 {race_code:'MI-07',race_type:'house',state:'MI',dem_candidate:'D Example',rep_candidate:'R Example',dem_probability:.52,forecast_margin_d_minus_r:.3,seat_holder:'REP'},
 {race_code:'TX-SEN',race_type:'senate',state:'TX',dem_candidate:'D Senate',rep_candidate:'R Senate',dem_probability:.4,forecast_margin_d_minus_r:-1.8,seat_holder:'REP'},
]};
assert.equal(filterRaces(model.races,{chamber:'house'}).length,1);
assert.equal(filterRaces(model.races,{party:'dem-flip'}).length,1);
assert(searchRecords(model).some(x=>x.label==='MI-07'));
const sc=runScenario(model,{genericBallotShift:2},500);
assert(sc.house.dem_control_probability>=0&&sc.house.dem_control_probability<=1);
assert(Math.abs(Object.values(sc.joint_control).reduce((a,b)=>a+b,0)-1)<1e-9);
const assignments={'MI-07':'D','TX-SEN':'R'};
const built=buildElectionSummary(assignments,model.races,model.summary);
assert.equal(built.houseDem,1);
console.log('core tests passed');
