import {chromium} from "playwright";
import assert from "node:assert/strict";
import axe from "axe-core";
const browser=await chromium.launch({headless:true});
const base=process.env.BASE_URL||"http://127.0.0.1:4173";
const party=(p,v,win=false)=>({name:"Candidate "+p,party:p,votes:v,winner:win});
const source={schema_version:1,source:"civicAPI",source_updated_at:"2026-11-04T08:33:49.695Z",fetched_at:"2026-11-04T08:34:05Z",state:"reporting",races:[
 {race_id:"H-PA-07",model_code:"PA-07",chamber:"house",state:"PA",votes_total:1400,
  candidates:[party("D",900,true),party("R",500)],leader:party("D",900,true),called:true,
  winner:party("D",900,true),called_by:"civicAPI decision desk"},
 {race_id:"H-VA-01",model_code:"VA-01",chamber:"house",state:"VA",votes_total:1000,
  candidates:[party("D",450),party("R",550)],leader:party("R",550),called:false,winner:null,called_by:null},
 {race_id:"S-GA",model_code:"GA-SEN",chamber:"senate",state:"GA",votes_total:2200,
  candidates:[party("D",1200,true),party("R",1000)],leader:party("D",1200,true),called:true,
  winner:party("D",1200,true),called_by:"civicAPI decision desk"}
]};
try{
 const page=await browser.newPage({viewport:{width:390,height:844}});
 await page.route("**/data/observed-results.json*",r=>r.fulfill({status:200,contentType:"application/json",body:JSON.stringify(source)}));
 await page.route("https://thepeoplestally.com/**",r=>r.abort());
 await page.route("https://openamerica.io/**",r=>r.abort());
 const errors=[];page.on("pageerror",e=>errors.push(String(e)));
 await page.goto(base+"/results/",{waitUntil:"domcontentloaded"});
 await page.waitForFunction(()=>document.querySelector("#compareState")?.textContent==="NEAR-TIME DISCREPANCY",{timeout:15000});
 assert.equal(await page.locator("#houseD").innerText(),"1");
 assert.equal(await page.locator("#houseR").innerText(),"0");
 assert.equal(await page.locator("#senateD").innerText(),"35");
 assert.equal(await page.locator("#senateR").innerText(),"31");
 assert.match(await page.locator("#senateBreakdown").innerText(),/34 D-aligned holdovers/);
 assert.match(await page.locator("#houseVerdict").innerText(),/not yet determined/i);
 assert.match(await page.locator("#houseUncalled").innerText(),/1 R leads/);
 assert.match(await page.locator("#senateUncalled").innerText(),/34 uncalled/);
 assert.match(await page.locator("#compareDelta").innerText(),/civicAPI − Guardian/);
 assert.equal(await page.locator("#compareRows tr").count(),4);
 assert.equal(await page.locator("#senateSegments span").count(),4);
 assert.equal(await page.locator("#houseSegments span").count(),2);
 const width=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
 assert(width<4,"Control board must not overflow 390px mobile layout: "+width);
 await page.addScriptTag({content:axe.source});
 const report=await page.evaluate(async()=>axe.run(document));
 const severe=report.violations.filter(v=>["serious","critical"].includes(v.impact));
 assert.equal(severe.length,0,JSON.stringify(severe.map(v=>({id:v.id,targets:v.nodes.slice(0,2).map(n=>n.target)}))));
 assert.deepEqual(errors,[]);
 console.log("Results Desk v3 390px control-board, timestamped comparison and a11y tests passed");
}finally{await browser.close()}
