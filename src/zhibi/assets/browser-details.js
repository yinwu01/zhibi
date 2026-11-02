/* Optional local observations. Font probing and UA token lists adapted from
 * CheckCC (MIT), client-engine.ts @ 078e7baa1d2a08df28da3f25dacb90e687f4c79f.
 * Copyright (c) 2026 yacuo / CheckCC. Full license is bundled in this page.
 * No network, location request, installed-font enumeration or persistent hash. */
(function (root) {
  "use strict";
  const FONTS = ["Microsoft YaHei", "Microsoft JhengHei", "PingFang SC", "Hiragino Sans GB", "STHeiti", "STSong", "SimSun", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "PingFang TC", "Heiti TC", "Hiragino Sans CNS", "Noto Sans CJK TC", "Source Han Sans TC", "MingLiU", "PMingLiU", "MiSans", "HarmonyOS Sans", "OPPO Sans", "vivo Sans", "Honor Sans", "Alibaba PuHuiTi", "WPS Fangzheng", "FZLanTingHeiS"];
  const MODULES = ["locale", "identity", "runtime", "hardware", "fonts", "permissions"];
  const LABELS = {locale:"时区偏移与语言变体",identity:"浏览器与设备识别",runtime:"浏览器运行容器",hardware:"浏览器可用 CPU",fonts:"固定字体探测",permissions:"本页定位权限"};
  const BROWSERS = ["micromessenger", "mqqbrowser", "qqbrowser", "quark", "ucbrowser", "ucweb", "baiduboxapp", "baidubrowser", "miuibrowser", "mibrowser", "huaweibrowser", "heytapbrowser", "oppobrowser", "vivobrowser", "360se", "360ee", "qihoobrowser", "sogoumobilebrowser", "2345browser", "lbbrowser"];
  const DEVICES = ["harmonyos", "huawei", "honor", "xiaomi", "redmi", "oppo", "vivo", "realme", "oneplus", "miui"];
  const result = (status, facts=null) => ({status, facts});
  function languageVariants(languages) {
    const found = new Set();
    for (const value of languages) {
      const lang = String(value).toLowerCase();
      if (!/^zh(?:-|$)/.test(lang)) continue;
      // Explicit script takes precedence; bare zh cannot establish a script.
      found.add(/-hant(?:-|$)/.test(lang) ? "traditional" : /-hans(?:-|$)/.test(lang) ? "simplified" : /^zh-(tw|hk|mo)(?:-|$)/.test(lang) ? "traditional" : /^zh-(cn|sg)(?:-|$)/.test(lang) ? "simplified" : "unspecified");
    }
    return [...found].sort();
  }
  function identity(nav) {
    const ua = String(nav.userAgent || "").slice(0,1000), lower=ua.toLowerCase();
    const platform=String(nav.userAgentData?.platform || nav.platform || "");
    let browser="unknown", version=null;
    for (const [name, pattern] of [["Edge",/Edg(?:A|iOS)?\/([\d.]+)/], ["Opera",/OPR\/([\d.]+)/], ["Firefox",/(?:Firefox|FxiOS)\/([\d.]+)/], ["Chrome",/(?:Chrome|CriOS)\/([\d.]+)/], ["Safari",/Version\/([\d.]+).*Safari/]]) {
      const m=ua.match(pattern); if(m) {browser=name;version=m[1].slice(0,40);break;}
    }
    const probe=(ua+" "+platform).toLowerCase();
    const os=/harmonyos/.test(probe)?"HarmonyOS":/android/.test(probe)?"Android":/iphone|ipad|ipod/.test(probe)?"iOS":/mac os|macintosh|macintel/.test(probe)?"macOS":/windows/.test(probe)?"Windows":/linux/.test(probe)?"Linux":"unknown";
    const engine=/(?:iphone|ipad|ipod)/i.test(ua)?"WebKit":/Firefox\//.test(ua)?"Gecko":/(?:Chrome|Chromium|Edg|OPR)\//.test(ua)?"Blink":/AppleWebKit\//.test(ua)?"WebKit":"unknown";
    const brands=(nav.userAgentData?.brands || []).slice(0,10).map(x=>({brand:String(x.brand||"").slice(0,80),version:String(x.version||"").slice(0,40)}));
    const tokenProbe=(ua+" "+brands.map(x=>x.brand).join(" ")).toLowerCase();
    return {browser,version,engine,os,device:/ipad|tablet/i.test(ua)?"tablet":/mobile|iphone|ipod/i.test(ua)?"mobile":["macOS","Windows","Linux"].includes(os)?"desktop":"unknown",
      browserToken:BROWSERS.find(x=>tokenProbe.includes(x))||null,deviceToken:DEVICES.find(x=>probe.includes(x))||null,
      brands,emojiFamily:["macOS","iOS"].includes(os)?"Apple":os==="Android"?"Android":os==="Windows"?"Windows":"unknown"};
  }
  function fonts(doc) {
    const ctx=doc.createElement("canvas").getContext("2d");
    if(!ctx) return result("unsupported");
    const text="中文字体检测ABCabc012", bases=["monospace","sans-serif","serif"];
    const width=font=>{ctx.font="72px "+font;const n=ctx.measureText(text).width;if(!Number.isFinite(n)||n<=0)throw new Error("measurement");return n;};
    const baseline=bases.map(b=>width(b));
    // Privacy randomization or unstable metrics must not turn into 26 false matches.
    if(bases.some((b,i)=>Math.abs(width(b)-baseline[i])>0.5)) return result("error");
    const detected=FONTS.filter(font=>bases.some((base,i)=>Math.abs(width('"'+font+'", '+base)-baseline[i])>0.5));
    return result("ok",{detected,tested:FONTS.length});
  }
  async function permission(nav, timeoutMs) {
    if(!nav.permissions?.query) return result("unsupported");
    let timer;
    try {
      const value=await Promise.race([nav.permissions.query({name:"geolocation"}),new Promise(resolve=>{timer=setTimeout(()=>resolve(null),timeoutMs);})]);
      if(value===null)return result("timeout");
      return ["granted","denied","prompt"].includes(value.state)?result("ok",{geolocation:value.state}):result("error");
    } catch(e) {return result(e?.name==="TypeError"?"unsupported":"error");}
    finally {clearTimeout(timer);}
  }
  async function collect(selected={}, deps={}) {
    const nav=deps.navigator || root.navigator, doc=deps.document || root.document;
    const checks={};
    for (const key of MODULES) {
      if(selected[key]!==true){checks[key]=result("skipped");continue;}
      try {
        if(key==="locale")checks[key]=result("ok",{utcOffsetMinutes:-(deps.date || new Date()).getTimezoneOffset(),variants:languageVariants(nav.languages || [nav.language].filter(Boolean))});
        if(key==="identity")checks[key]=result("ok",identity(nav));
        if(key==="runtime"){const ua=String(nav.userAgent||"");checks[key]=result("ok",{webdriver:nav.webdriver===true,webview:/;\s*wv\)|\bWebView\b|MicroMessenger|FBAN|FBAV/i.test(ua),headless:/HeadlessChrome/i.test(ua)});}
        if(key==="hardware"){const n=nav.hardwareConcurrency;checks[key]=Number.isInteger(n)&&n>0&&n<=65536?result("ok",{logicalProcessors:n}):result("unsupported");}
        if(key==="fonts")checks[key]=fonts(doc);
        if(key==="permissions")checks[key]=await permission(nav,deps.timeoutMs ?? 2000);
      } catch {checks[key]=result("error");}
    }
    return {at:new Date().toISOString(),checks};
  }
  function reading(key,f) {
    if(!f)return "没有取得读数";
    if(key==="locale")return "UTC"+(f.utcOffsetMinutes>=0?"+":"")+(f.utcOffsetMinutes/60)+"；中文变体："+(f.variants.map(v=>({simplified:"简体",traditional:"繁体",unspecified:"未指定"}[v])).join(" / ")||"未自报中文");
    if(key==="identity")return f.browser+" "+(f.version||"")+" / "+f.engine+" / "+f.os+"；设备 "+f.device+"；UA 标记 "+[f.browserToken,f.deviceToken].filter(Boolean).join(" / ");
    if(key==="runtime")return "自动化自报 "+f.webdriver+"；内嵌浏览器标记 "+f.webview+"；无头标记 "+f.headless;
    if(key==="hardware")return f.logicalProcessors+" 个逻辑处理器（浏览器报告值）";
    if(key==="fonts")return f.detected.length+" / "+f.tested+" 个固定候选有字体匹配迹象";
    return {granted:"本页已获授权",denied:"本页被拒绝定位",prompt:"本页需询问授权"}[f.geolocation];
  }
  const api={collect,languageVariants,identity,FONTS,MODULES,LABELS,reading};
  root.ZhibiDetails=api;if(typeof module!=="undefined"&&module.exports)module.exports=api;
})(typeof globalThis!=="undefined"?globalThis:this);
