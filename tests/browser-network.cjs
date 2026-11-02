// Adapted parsing/request cases from CCBaga browser-network.test.ts (MIT).
// Additional Zhibi tests cover actual UI, export contract and isolated external scope.
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),os=require("node:os");
const {pathToFileURL}=require("node:url");
const {spawnSync}=require("node:child_process");
const probe=require("../src/zhibi/assets/network-probe.js");
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||"playwright");
const root=path.resolve(__dirname,"..");
(async()=>{
  for(const ip of ["999.2.3.4","::1]:80/#","1::2]/x","2001:db8::1]@host","::1 ","fe80::1%25eth0"])assert.equal(probe.validIp(ip),false);
  for(const ip of ["8.8.8.8","2001:db8::1","::ffff:203.0.113.1"])assert.equal(probe.validIp(ip),true);
  assert.throws(()=>probe.parseAddress({success:false,ip:"8.8.8.8"},4));
  assert.throws(()=>probe.parseAddress({ip:"2001:db8::1"},4));
  let requests=[];
  let result=await probe.probeBrowserExit(4,async(url,options)=>{requests.push([url,options]);return Response.json({ip:"8.8.8.8"});});
  assert.equal(result.ip,"8.8.8.8");assert.equal(requests[0][1].credentials,"omit");assert.equal(requests[0][1].redirect,"error");assert.equal(requests[0][1].referrerPolicy,"no-referrer");
  result=await probe.probeBrowserExit(4,async()=>new Response("",{status:429}));assert.equal(result.status,"quota_exceeded");
  result=await probe.probeBrowserExit(6,async()=>Response.json({ip:"8.8.8.8"}));assert.equal(result.status,"invalid_response");
  result=await probe.probeBrowserExit(4,async()=>new Response("x".repeat(32769)));assert.equal(result.status,"invalid_response");
  assert.deepEqual(probe.parseCandidate({candidate:"candidate:1 1 udp 123 a.local 42 typ host"}),{type:"host",protocol:"udp",address:null,mdns:true});
  assert.equal(probe.parseCandidate({candidate:"candidate:1 1 udp 123 bad 42 typ srflx"}),null);
  let closed=false;
  class BrokenPeer{createDataChannel(){} createOffer(){return Promise.reject(new Error("secret"));}close(){closed=true;}}
  result=await probe.probeWebRTC(BrokenPeer);assert.equal(result.status,"error");assert.equal(closed,true);
  assert.equal((await probe.probeWebRTC(null)).status,"unsupported");

  const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),"zhibi-probe-"));
  try {
    const page=await browser.newPage({viewport:{width:1280,height:1000}}),calls=[],errors=[];
    page.on("request",r=>{if(r.url().startsWith("http"))calls.push(r.url());});page.on("pageerror",e=>errors.push(e.message));
    const standalone=path.join(tmp,"probe.html");fs.copyFileSync(path.join(root,".preview/network.html"),standalone);
    await page.goto(pathToFileURL(standalone).href);assert.equal(calls.length,0);
    // Exercise native ICE collection without contacting STUN: the constructor is real,
    // with only iceServers replaced for this offline acceptance case.
    const nativeRTC=await page.evaluate(async()=>{
      const RealPeer=RTCPeerConnection;
      class LocalOnlyPeer extends RealPeer{constructor(config){super({...config,iceServers:[]});}}
      const result=await ZhibiNetwork.probeWebRTC(LocalOnlyPeer);
      return {status:result.status,complete:result.complete,count:result.candidates.length};
    });
    assert.ok(["ok","no_candidates","timeout"].includes(nativeRTC.status));
    if(nativeRTC.status!=="timeout")assert.equal(nativeRTC.complete,true);
    await page.screenshot({path:path.join(root,".preview/network-desktop.png")});
    await page.getByRole("button",{name:"开始检查"}).click();await page.waitForFunction(()=>!document.querySelector("#run").disabled);
    let bundle=JSON.parse(await page.locator("#preview").textContent());assert.equal(bundle.schema_version,"4");assert.equal(bundle.network.webrtc.status,"skipped");assert(Object.values(bundle.details.checks).every(x=>x.status==="skipped"));assert(Object.values(bundle.extras.checks).every(x=>x.status==="skipped"));assert.equal(calls.length,0);
    await page.route(probe.ENDPOINTS.ipv4,route=>route.fulfill({status:200,contentType:"application/json",headers:{"Access-Control-Allow-Origin":"*"},body:'{"ip":"8.8.8.8"}'}));
    await page.route(probe.ENDPOINTS.ipv6,route=>route.fulfill({status:200,contentType:"application/json",headers:{"Access-Control-Allow-Origin":"*"},body:'{"ip":"2606:4700::1111"}'}));
    await page.locator("#ipv4").check();await page.locator("#ipv6").check();
    await page.getByRole("button",{name:"开始检查"}).click();await page.waitForFunction(()=>!document.querySelector("#run").disabled);
    bundle=JSON.parse(await page.locator("#preview").textContent());assert.equal(bundle.network.ipv4.ip,"8.8.8.8");assert.equal(bundle.network.ipv6.ip,"2606:4700::1111");assert.equal(calls.length,2);
    const downloaded=page.waitForEvent("download");await page.locator("#download").click();const file=path.join(tmp,"browser.json");await (await downloaded).saveAs(file);
    const python=process.env.ZHIBI_TEST_PYTHON||path.join(root,".venv/bin/python");
    const checked=spawnSync(python,["-c","from zhibi.browser import parse_bundle; from zhibi.models import read_json; import sys; parse_bundle(read_json(sys.argv[1]))",file],{cwd:root,encoding:"utf8"});assert.equal(checked.status,0,checked.stderr);
    await page.unroute(probe.ENDPOINTS.ipv4);await page.route(probe.ENDPOINTS.ipv4,route=>route.fulfill({status:503,body:"unavailable"}));
    await page.locator("#ipv6").uncheck();await page.getByRole("button",{name:"开始检查"}).click();await page.waitForFunction(()=>!document.querySelector("#run").disabled);
    bundle=JSON.parse(await page.locator("#preview").textContent());assert.equal(bundle.network.ipv4.ip,null);assert.equal(calls.length,3,"No fallback or retry");
    await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:path.join(root,".preview/network-mobile.png"),fullPage:true});
    assert.deepEqual(errors,[]);
    console.log("Advanced probe passed: migrated IP validation, credential omission, response bounds, ICE parsing/cleanup, standalone offline UI, dual-stack, real download/Python import, errors and mobile.");
  }finally{await browser.close();fs.rmSync(tmp,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
