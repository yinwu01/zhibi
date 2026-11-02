// Pure synthetic logic tests. No live browser or network requests.
const assert=require('node:assert/strict');
const fs=require('node:fs');
globalThis.crypto=require('node:crypto').webcrypto;
let calls=0;
globalThis.fetch=()=>{calls++;throw new Error('unexpected network');};
const extras=require('../src/zhibi/assets/browser-extras.js');
(async()=>{
  const off=await extras.collect({});assert(Object.values(off.checks).every(v=>v.status==='skipped'));assert.equal(calls,0);
  let variant=0;
  globalThis.document={createElement(){return {getContext(kind){if(kind==='webgl')return null;return {clearRect(){},fillRect(){},fillText(){},getImageData(){return {data:new Uint8Array([variant,1,2,3])};}};}};}};
  let r=await extras.collect({canvas:true,webgl:true,audio:true,dns:true});
  assert.equal(r.checks.canvas.status,'ok');assert.equal(r.checks.canvas.facts.repeated_equal,true);
  assert.equal(r.checks.webgl.status,'unsupported');assert.equal(r.checks.audio.status,'unsupported');assert.equal(r.checks.dns.status,'configuration_required');assert.equal(calls,0);
  globalThis.document={createElement(){return {getContext(){return {clearRect(){},fillRect(){},fillText(){},getImageData(){return {data:new Uint8Array([variant++,1,2,3])};}};}};}};
  r=await extras.collect({canvas:true});assert.equal(r.checks.canvas.facts.repeated_equal,false);
  r=await extras.collect({tls:true});assert.equal(r.checks.tls.status,'error');assert.equal(calls,1);
  // Parse scripts without running a page. This catches broken generated probe syntax.
  if(process.argv[2]){const page=fs.readFileSync(process.argv[2],'utf8');for(const m of page.matchAll(/<script>([\s\S]*?)<\/script>/g))new Function(m[1]);}
  console.log('Browser extras passed: opt-in isolation, rendering comparison, unsupported APIs, DNS configuration, TLS failure and generated script syntax.');
})().catch(e=>{console.error(e);process.exitCode=1;});
