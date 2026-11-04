// Publicly documented state-outline GeoJSON. The map is STATE-level only:
// congressional district boundaries are intentionally not implied.
import {stateInsight,signedMargin} from "./v2-core.mjs";
const NS="http://www.w3.org/2000/svg";
export const FIPS_TO_STATE={};
const PALETTE={missing:"#d7d4cb",low:"#c7dce3",mid:"#7daec0",high:"#357c95",full:"#15546d",
  dem1:"#a6bfd3",dem2:"#648fb0",dem3:"#315d82",
  rep1:"#d4b0a6",rep2:"#bb7569",rep3:"#9c453e"};
const stateByName={Alabama:"AL",Alaska:"AK",Arizona:"AZ",Arkansas:"AR",California:"CA",Colorado:"CO",Connecticut:"CT",Delaware:"DE",Florida:"FL",Georgia:"GA",Hawaii:"HI",Idaho:"ID",Illinois:"IL",Indiana:"IN",Iowa:"IA",Kansas:"KS",Kentucky:"KY",Louisiana:"LA",Maine:"ME",Maryland:"MD",Massachusetts:"MA",Michigan:"MI",Minnesota:"MN",Mississippi:"MS",Missouri:"MO",Montana:"MT",Nebraska:"NE",Nevada:"NV",NewHampshire:"NH",NewJersey:"NJ",NewMexico:"NM",NewYork:"NY",NorthCarolina:"NC",NorthDakota:"ND",Ohio:"OH",Oklahoma:"OK",Oregon:"OR",Pennsylvania:"PA",RhodeIsland:"RI",SouthCarolina:"SC",SouthDakota:"SD",Tennessee:"TN",Texas:"TX",Utah:"UT",Vermont:"VT",Virginia:"VA",Washington:"WA",WestVirginia:"WV",Wisconsin:"WI",Wyoming:"WY","District of Columbia":"DC"};
const compactName=name=>String(name||"").replaceAll(" ","");
export function project([lon,lat],state){
  if(state==="AK")return [25+(lon+180)*4.3,442+(73-lat)*3.1];
  if(state==="HI")return [295+(lon+162)*12.2,453+(23-lat)*10.8];
  return [56+(lon+125)*15.1,25+(50-lat)*16.0];
}
export function geometryPath(geometry,state){
  const polygons=geometry?.type==="Polygon"?[geometry.coordinates]:geometry?.type==="MultiPolygon"?geometry.coordinates:[];
  return polygons.map(poly=>poly.map(ring=>ring.map((point,i)=>{
    const xy=project(point,state);return (i===0?"M":"L")+xy[0].toFixed(1)+","+xy[1].toFixed(1);
  }).join(" ")+" Z").join(" ")).join(" ");
}
export function mapFill(info,layer){
  if(!info?.tracked||info.counted===0)return PALETTE.missing;
  if(layer==="coverage"){
    const p=info.coverage;return p>=100?PALETTE.full:p>=75?PALETTE.high:p>=35?PALETTE.mid:PALETTE.low;
  }
  const m=info.margin;
  if(!Number.isFinite(m))return PALETTE.missing;
  const degree=Math.abs(m);const tier=degree>=15?3:degree>=5?2:1;
  return PALETTE[(m>=0?"dem":"rep")+tier];
}
function svg(tag,attrs={},text){
 const node=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))node.setAttribute(k,String(v));
 if(text!==undefined)node.textContent=text;return node;
}
function description(info,layer,name){
 if(!info.tracked)return name+": no tracked voting contest in this layer";
 const base=name+": "+info.counted+" of "+info.tracked+" tracked races have reported votes";
 if(!info.counted||layer==="coverage")return base;
 if(info.margin===null)return base+". Two-party margin unavailable";
 return base+". Aggregate D−R "+signedMargin(info.margin)+" from reported "+(layer==="house"?"House districts":"Senate race")+" only, provisional";
}
export async function drawStateMap(container,{rows,layer="coverage",selected="all",onSelect}) {
 let geo;
 try {const r=await fetch("/results/states.geojson",{cache:"force-cache"});if(!r.ok)throw new Error("Map geography unavailable");geo=await r.json()}
 catch(e){container.textContent="State outline map unavailable. The accessible state selector below remains usable.";return}
 const visual=svg("svg",{viewBox:"0 0 1000 535",role:"img","aria-label":"Interactive US state map. Select a state to filter the House and Senate results."});
 const frag=document.createDocumentFragment();
 for(const feature of geo.features||[]){
   const name=feature?.properties?.name||"";
   const code=stateByName[name]||stateByName[compactName(name)];
   if(!code)continue;
   const info=stateInsight(rows,code,layer),title=description(info,layer,name);
   const path=svg("path",{d:geometryPath(feature.geometry,code),fill:mapFill(info,layer),stroke:"#f7f3ec","stroke-width":code==="DC"?"1.7":"1.1",
     "fill-rule":"evenodd",tabindex:"0",role:"button","aria-label":code+" "+title,"data-state":code,
     class:code===selected?"selected":"",style:"cursor:pointer"});
   path.append(svg("title",{},title));
   path.addEventListener("click",()=>onSelect(code));
   path.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();onSelect(code)}});
   frag.append(path);
 }
 visual.append(frag);
 const desc=document.createElement("p");
 desc.className="map-caption";
 desc.textContent=layer==="coverage"?"Darker blue = more tracked contests with reported votes, not greater vote-count completeness."
    :layer==="house"?"Blue = D lead; red = R lead. Two-party margins aggregate only districts reporting votes; this is not a statewide election projection."
    :"Blue = D lead; red = R lead. Only the matched statewide Senate contest is shown; no result is inferred for uncovered states.";
 container.replaceChildren(visual,desc);
}
