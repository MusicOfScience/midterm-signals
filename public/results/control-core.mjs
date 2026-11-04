// Results Desk v3: pure seat accounting; observation-only, no model changes.
// All counts describe projected members of the next Congress, NOT certified officeholders.
export const SENATE_HOLDOVERS=Object.freeze({D:34,R:31,democrats:32,independentCaucusD:2,total:65});
export const HOUSE_TOTAL=435,SENATE_TOTAL=100,SENATE_CONTESTED=35;
const number=v=>typeof v==="number"&&Number.isSafeInteger(v)&&v>=0;
const party=v=>v==="D"||v==="R"?v:"other";

function contestCounts(feed,chamber){
 const expected=chamber==="house"?HOUSE_TOTAL:SENATE_CONTESTED;
 const seen=new Set(),duplicates=new Set(),valid=[];
 for(const row of feed?.races||[]){
  if(!row||row.chamber!==chamber||typeof row.model_code!=="string")continue;
  const key=row.model_code;
  if(seen.has(key)){duplicates.add(key);continue}
  seen.add(key);
  valid.push(row);
 }
 const ambiguous=new Set(feed?.ambiguous_keys||[]);
 for(const key of duplicates)ambiguous.add(key);
 const counts={D:0,R:0,other:0},leads={D:0,R:0,other:0},calls=[];
 let withVotes=0,notReporting=0;
 for(const row of valid){
  if(ambiguous.has(row.model_code))continue;
  if(row.called===true&&typeof row.called_by==="string"&&row.called_by.trim()&&row.winner){
   const key=party(row.winner.party);
   counts[key]++;calls.push({key:row.model_code,party:key,caller:row.called_by});
   continue;
  }
  if(number(row.votes_total)&&row.votes_total>0){
   withVotes++;
   const lead=party(row.leader?.party);
   if(row.leader)leads[lead]++;
   else notReporting++;
  }else notReporting++;
 }
 const called=Object.values(counts).reduce((a,b)=>a+b,0);
 if(called>expected)throw new Error("Provider calls exceed the number of "+chamber+" contests");
 return {expected,called,calls,calledByParty:counts,leads,uncalled:expected-called,
  withVotes,notReporting,ambiguous:ambiguous.size};
}

function verdict(D,R,total,thresholdD,thresholdR,chamber){
 if(D>=thresholdD)return {party:"D",text:"Democratic control projected",reason:"Based on named-source calls; not certified"};
 if(R>=thresholdR)return {party:"R",text:"Republican control projected",reason:chamber==="senate"?"At 50–50, the Republican vice-president holds the casting vote":"Based on named-source calls; not certified"};
 return {party:null,text:"Control not yet determined",reason:"No party has reached the threshold on called races"};
}
export function controlDesk(feed){
 const house=contestCounts(feed,"house"),senate=contestCounts(feed,"senate");
 const HD=house.calledByParty.D,HR=house.calledByParty.R,HO=house.calledByParty.other;
 const SD=SENATE_HOLDOVERS.D+senate.calledByParty.D;
 const SR=SENATE_HOLDOVERS.R+senate.calledByParty.R;
 const SO=senate.calledByParty.other;
 const H=Object.assign(house,{D:HD,R:HR,other:HO,total:HOUSE_TOTAL,
  segments:[{id:"Dcalled",label:"Democratic calls",count:HD},
            {id:"unresolved",label:"Uncalled seats",count:house.uncalled},
            {id:"other",label:"Other-party calls",count:HO},
            {id:"Rcalled",label:"Republican calls",count:HR}],
  verdict:verdict(HD,HR,HOUSE_TOTAL,218,218,"house")});
 const S=Object.assign(senate,{D:SD,R:SR,other:SO,total:SENATE_TOTAL,
  segments:[{id:"Dhold",label:"Democratic-aligned seats not up",count:SENATE_HOLDOVERS.D},
            {id:"Dcalled",label:"Democratic calls this election",count:senate.calledByParty.D},
            {id:"unresolved",label:"Uncalled contested seats",count:senate.uncalled},
            {id:"other",label:"Other-party calls",count:SO},
            {id:"Rcalled",label:"Republican calls this election",count:senate.calledByParty.R},
            {id:"Rhold",label:"Republican seats not up",count:SENATE_HOLDOVERS.R}],
  verdict:verdict(SD,SR,SENATE_TOTAL,51,50,"senate")});
 for(const c of [H,S]){
  if(c.segments.reduce((s,x)=>s+x.count,0)!==c.total)throw new Error("Seat-accounting invariant failed");
 }
 return {house:H,senate:S,source:feed?.source||"unknown",
  sourceUpdatedAt:feed?.source_updated_at||null,
  fetchedAt:feed?.fetched_at||null,
  hasObservedCalls:house.called+senate.called>0};
}

const validDate=x=>typeof x==="string"&&Number.isFinite(Date.parse(x));
const validRef=(s,ch)=>s&&number(s[ch]?.D)&&number(s[ch]?.R)&&number(s[ch]?.called);
const diff=(a,b)=>a-b;
// The Guardian data are a user-supplied fixed point-in-time screenshot, not an AP feed.
// Only compare aggregate totals when the source times are close; differing calls cannot
// be attributed to either counting progress or call policy without per-race AP evidence.
export function reconcileReference(feed,reference,maxMinutes=15){
 const desk=controlDesk(feed);
 if(!reference||!validDate(reference.captured_at)||!validRef(reference,"house")||!validRef(reference,"senate"))
   return {state:"reference-unavailable",desk,reference};
 if(!validDate(desk.sourceUpdatedAt)||!desk.hasObservedCalls)
   return {state:"source-unavailable",desk,reference,minutesApart:null};
 const minutesApart=Math.round(Math.abs(Date.parse(desk.sourceUpdatedAt)-Date.parse(reference.captured_at))/60000);
 const comparable=minutesApart<=maxMinutes;
 const H=desk.house,S=desk.senate;
 const summary={
  house:{D:diff(H.D,reference.house.D),R:diff(H.R,reference.house.R),called:diff(H.called,reference.house.called)},
  senate:{D:diff(S.D,reference.senate.D),R:diff(S.R,reference.senate.R),called:diff(S.called,reference.senate.called)}
 };
 const allEqual=Object.values(summary).every(s=>s.D===0&&s.R===0&&s.called===0);
 return {state:comparable?(allEqual?"aligned":"near-time-difference"):"historical-only",
   desk,reference,minutesApart,
   deltas:comparable?summary:null,
   note:comparable
   ?"The feeds are close in time, not synchronised; aggregate differences cannot identify which individual races disagree."
   :"The newsroom reference is an earlier screenshot; differences now mainly reflect elapsed counting time, so comparison deltas are withheld."};
}
