// Reproduce the failed post-merge 4 Nov forecast publication in isolated Git repos.
// The generated-data commit must survive a remote advance even if the build
// leaves tracked and untracked auxiliary files dirty. Never force push.
import assert from "node:assert/strict";
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {execFileSync} from "node:child_process";

const root=mkdtempSync(join(tmpdir(),"ms-forecast-publish-"));
const run=(cwd,...args)=>execFileSync("git",args,{cwd,encoding:"utf8",stdio:["ignore","pipe","pipe"]}).trim();
const file=(base,path,contents)=>{
 const full=join(base,path);
 mkdirSync(full.substring(0,full.lastIndexOf("/")),{recursive:true});
 writeFileSync(full,contents);
};
const configure=dir=>{run(dir,"config","user.name","MIDTERM test bot");run(dir,"config","user.email","bot@localhost")};
try{
 const origin=join(root,"origin.git"),seed=join(root,"seed"),forecast=join(root,"forecast"),results=join(root,"results");
 mkdirSync(seed);
 run(root,"init","--bare",origin);
 run(seed,"init","-b","main");configure(seed);
 file(seed,"public/data/forecast.json",'{"forecast":"frozen original"}\n');
 file(seed,"public/data/observed-results.json",'{"races":0}\n');
 file(seed,"scripts/auxiliary.txt","baseline\n");
 run(seed,"add",".");run(seed,"commit","-m","baseline");
 run(seed,"remote","add","origin",origin);run(seed,"push","-u","origin","main");
 run(origin,"symbolic-ref","HEAD","refs/heads/main");
 run(root,"clone",origin,forecast);run(root,"clone",origin,results);
 configure(forecast);configure(results);
 // The forecast job builds a new, separately staged publication artifact.
 file(forecast,"public/data/forecast.json",'{"forecast":"generated refresh"}\n');
 run(forecast,"add","public/data/forecast.json");
 run(forecast,"commit","-m","data: forecast/browser refresh");
 // Auxiliary tracked/untracked outputs remain after commit (the actual failure).
 file(forecast,"scripts/auxiliary.txt","modified by build pipeline, not published\n");
 file(forecast,"scratch/untracked-diagnostic.txt","temporary test diagnostic\n");
 assert.notEqual(run(forecast,"status","--porcelain"),"","Fixture must be dirty");
 // The results job wins the race and advances main before forecast can publish.
 file(results,"public/data/observed-results.json",'{"races":466}\n');
 run(results,"add","public/data/observed-results.json");
 run(results,"commit","-m","data: observed result refresh");
 run(results,"push","origin","HEAD:main");
 // The v3 run failed here with 'cannot rebase: You have unstaged changes.'
 run(forecast,"stash","push","--include-untracked","-m","auxiliary forecast build outputs (unpublished)");
 assert.equal(run(forecast,"status","--porcelain"),"");
 run(forecast,"fetch","origin","main");
 run(forecast,"rebase","origin/main");
 run(forecast,"push","origin","HEAD:main");
 const verification=join(root,"verify");
 run(root,"clone",origin,verification);
 assert.equal(JSON.parse(readFileSync(join(verification,"public/data/observed-results.json"),"utf8")).races,466);
 assert.equal(JSON.parse(readFileSync(join(verification,"public/data/forecast.json"),"utf8")).forecast,"generated refresh");
 assert.equal(readFileSync(join(verification,"scripts/auxiliary.txt"),"utf8"),"baseline\n");
 assert.equal(run(verification,"log","--oneline","-3").split("\n").length,3);
 assert.match(run(forecast,"stash","list"),/auxiliary forecast build outputs/);
 console.log("Forecast publisher safely rebases after results push with dirty auxiliary worktree; no overwrite/force-push");
}finally{rmSync(root,{recursive:true,force:true})}
