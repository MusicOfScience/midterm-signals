import {chromium} from "playwright";
import assert from "node:assert/strict";
const browser=await chromium.launch({headless:true});
const base=process.env.BASE_URL||"http://127.0.0.1:4173";
const asof="2026-11-04T02:30:00Z";
try{
 const page=await browser.newPage({viewport:{width:1280,height:920}});
 page.route("https://thepeoplestally.com/**",route=>route.fulfill({
   status:200,contentType:"application/json",body:JSON.stringify({generated_at:"2026-11-03T20:00:00Z",
     races:{"H-PA-07":{cands:[{name:"Older D",party:"D",votes:1100,winner:false},{name:"Older R",party:"R",votes:900,winner:false}],src:"PA test archive",asof:"2026-11-03T20:00:00Z",called_by:""}}})
 }));
 page.route("https://openamerica.io/elections/results.json?year=2026&office=House",route=>route.fulfill({
  status:200,contentType:"application/json",headers:{"access-control-allow-origin":"*"},
  body:JSON.stringify({api:1,year:2026,office:"House",as_of:asof,races:{
   "PA-07":{pct_in:94,total:3400,cands:[{n:"Source D",p:"D",v:2100},{n:"Source R",p:"R",v:1300}]}
  }})
 }));
 page.route("https://openamerica.io/elections/results.json?year=2026&office=Senate",route=>route.fulfill({
  status:200,contentType:"application/json",headers:{"access-control-allow-origin":"*"},
  body:JSON.stringify({api:1,year:2026,office:"Senate",as_of:asof,races:{
   "GA":{pct_in:85,total:6100,cands:[{n:"Senate D",p:"D",v:3200},{n:"Senate R",p:"R",v:2900}]}
  }})
 }));
 await page.goto(base+"/results/",{waitUntil:"domcontentloaded"});
 await page.waitForFunction(()=>document.querySelector("#mReporting")?.textContent?.startsWith("2 /"),null,{timeout:30000});
 await page.locator("#state").selectOption("PA");
 await page.waitForFunction(()=>
   document.querySelector("#state")?.value==="PA" &&
   document.querySelector("#rowCount")?.textContent?.match(/^\d+ of 470 races$/) &&
   document.querySelector("#raceRows")?.textContent?.includes("PA-07") &&
   document.querySelector("#raceRows")?.textContent?.includes("3,400"),
   null,{timeout:12000}).catch(async e=>{
     const diag=await page.evaluate(()=>({
       status:document.querySelector("#feedStatus")?.textContent,
       selection:document.querySelector("#state")?.value,
       rowCount:document.querySelector("#rowCount")?.textContent,
       reporting:document.querySelector("#mReporting")?.textContent,
       sourceLedger:document.querySelector("#sourceLedger")?.textContent,
       matchingRows:[...document.querySelectorAll("#raceRows tr")].filter(x=>/PA-07|GA-SEN/.test(x.textContent)).map(x=>x.textContent.slice(0,250))
     }));
     throw new Error("PA live-count test did not settle: "+JSON.stringify(diag)+" / "+e.message);
   });
 const content=await page.locator("#raceRows").innerText();
 assert.match(content,/3,400/,"Fresher official count should supersede older tally");
 assert.doesNotMatch(content,/2,000/,"Stale publisher count must not be mistaken for the newer feed");
 assert.doesNotMatch(content,/6,100/,"PA filter must not contain a different state's Senate votes");
 await page.locator("#state").selectOption("GA");
 const senateText=await page.locator("#raceRows").innerText();
 assert.match(senateText,/6,100/,"Georgia statewide Senate counts should appear");
 await page.locator("#state").selectOption("PA");
 assert.match(senateText,/Uncalled/,"Official feed supplies no named calls");
 assert.match(await page.locator("#countQuality").innerText(),/2 \/ 470/);
 const PA=page.locator("#raceRows tr").filter({hasText:"PA-07"});
 await PA.locator("button.inspect-race").click();
 const lens=await page.locator("#raceLensContent").innerText();
 assert.match(lens,/Source D/);assert.match(lens,/2,100/);
 assert.match(lens,/94/,"Provider reporting units should be exposed as qualified context");
 assert.match(lens,/Uncalled/);
 console.log("Results Desk v2 synthetic direct-feed positive-count and source arbitration integration passed");
}finally{await browser.close()}
