// Pure logic tests; no browser, network, user settings or credentials.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const d = require('../src/zhibi/assets/browser-details.js');
(async () => {
  const forbidden = new Proxy({}, {get(){throw Error('unselected capability accessed');}});
  const off = await d.collect({}, {navigator:forbidden, document:forbidden});
  assert(Object.values(off.checks).every(x=>x.status==='skipped'&&x.facts===null));
  assert.deepEqual(d.languageVariants(['zh','zh-Hant-CN','zh-Hans-TW','en-US']), ['simplified','traditional','unspecified']);
  assert.deepEqual(d.languageVariants(['en-US','fr-FR']), []);
  const nav={userAgent:'Mozilla/5.0 (Linux; Android 13; wv) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36 MicroMessenger/8.0',
    platform:'Linux',languages:['zh-Hant'],webdriver:false,hardwareConcurrency:8,
    userAgentData:{platform:'Android',brands:[{brand:'Chromium',version:'120'}]},
    permissions:{query:async args=>{assert.deepEqual(args,{name:'geolocation'});return {state:'prompt'};}},
    geolocation:forbidden};
  const ctx={font:'',measureText(){return {width:this.font.includes('"PingFang SC"')?120:100};}};
  const doc={createElement(name){assert.equal(name,'canvas');return {getContext(kind){assert.equal(kind,'2d');return ctx;}};}};
  const selected=Object.fromEntries(d.MODULES.map(k=>[k,true]));
  const complete=await d.collect(selected,{navigator:nav,document:doc,date:{getTimezoneOffset:()=>-345}});
  assert(Object.values(complete.checks).every(x=>x.status==='ok'));
  assert.equal(complete.checks.locale.facts.utcOffsetMinutes,345);
  assert.equal(complete.checks.identity.facts.browserToken,'micromessenger');
  assert.equal(complete.checks.identity.facts.engine,'Blink');
  assert.equal(complete.checks.runtime.facts.webview,true);
  assert.deepEqual(complete.checks.fonts.facts.detected,['PingFang SC']);
  assert.equal(complete.checks.fonts.facts.tested,26);
  assert.equal(complete.checks.permissions.facts.geolocation,'prompt');
  const ios=d.identity({userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 CriOS/120.0 Mobile Safari/604.1'});
  assert.equal(ios.engine,'WebKit');assert.equal(ios.os,'iOS');
  const failed=await d.collect(selected,{navigator:{...nav,hardwareConcurrency:0,permissions:{query(){throw new TypeError();}}},document:{createElement(){return {getContext(){return null;}}}}});
  assert.equal(failed.checks.fonts.status,'unsupported');assert.equal(failed.checks.hardware.status,'unsupported');assert.equal(failed.checks.permissions.status,'unsupported');
  const timeout=await d.collect({permissions:true},{navigator:{permissions:{query:()=>new Promise(()=>{})}},timeoutMs:5});
  assert.equal(timeout.checks.permissions.status,'timeout');
  let n=100;
  const unstable=await d.collect({fonts:true},{document:{createElement(){return {getContext(){return {measureText:()=>({width:n++})};}}}}});
  assert.equal(unstable.checks.fonts.status,'error');
  for(const item of Object.values(failed.checks))if(item.status!=='ok')assert.equal(item.facts,null);
  if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify(complete));
  console.log('Browser details passed: opt-in isolation, six modules, UA precedence, language variants, permission timeout, unsupported APIs and unstable fonts.');
})().catch(error=>{console.error(error);process.exitCode=1;});
