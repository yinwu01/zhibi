/* Zhibi optional local rendering observations. No microphone, coordinates or account data. */
(function(root){
  "use strict";
  const MODULES=["canvas","webgl","audio","tls","dns"],LABELS={canvas:"Canvas 渲染一致性",webgl:"WebGL 图形信息",audio:"离线 Audio 渲染",tls:"浏览器 TLS / HTTP 观测",dns:"浏览器 DNS 权威观测"};
  const item=(status,facts=null)=>({status,facts});
  async function digest(bytes){return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))).map(b=>b.toString(16).padStart(2,"0")).join("");}
  async function canvas(doc){
    const c=doc.createElement("canvas");c.width=240;c.height=80;const x=c.getContext("2d");if(!x)return item("unsupported");
    const draw=()=>{x.clearRect(0,0,240,80);x.fillStyle="#3150a0";x.fillRect(0,0,240,80);x.font="20px sans-serif";x.fillStyle="#f9ab33";x.fillText("知彼 / Zhibi 012 🎨",10,40);return x.getImageData(0,0,240,80).data;};
    const first=await digest(draw()),second=await digest(draw());return item("ok",{sha256:first,repeated_equal:first===second,width:240,height:80});
  }
  function webgl(doc){
    const c=doc.createElement("canvas"),gl=c.getContext("webgl");if(!gl)return item("unsupported");
    try{const debug=gl.getExtension("WEBGL_debug_renderer_info"),read=p=>String(gl.getParameter(p)||"").slice(0,300);
      return item("ok",{vendor:read(debug?debug.UNMASKED_VENDOR_WEBGL:gl.VENDOR),renderer:read(debug?debug.UNMASKED_RENDERER_WEBGL:gl.RENDERER),version:read(gl.VERSION),max_texture_size:gl.getParameter(gl.MAX_TEXTURE_SIZE),unmasked:!!debug});
    }finally{gl.getExtension("WEBGL_lose_context")?.loseContext();}
  }
  async function audio(){
    const Context=root.OfflineAudioContext||root.webkitOfflineAudioContext;if(!Context)return item("unsupported");
    const ctx=new Context(1,5000,44100),o=ctx.createOscillator(),gain=ctx.createGain();o.type="triangle";o.frequency.value=1000;gain.gain.value=0.1;o.connect(gain);gain.connect(ctx.destination);o.start();o.stop(5000/44100);
    const buffer=await ctx.startRendering(),data=buffer.getChannelData(0);let sum=0;for(let i=0;i<data.length;i++)sum+=Math.abs(data[i]);
    return item("ok",{samples:data.length,sample_rate:buffer.sampleRate,absolute_sum:Number(sum.toFixed(6))});
  }
  async function tls(){
    const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),8000);
    try{const r=await fetch("https://tls.peet.ws/api/all",{credentials:"omit",cache:"no-store",referrerPolicy:"no-referrer",redirect:"error",signal:ctrl.signal});
      if(!r.ok)return item("error");const data=JSON.parse(await root.ZhibiNetwork.limitedText(r,65536)),t=data.tls||{};
      const facts={http_version:data.http_version||null,tls_version:t.tls_version_negotiated||null,ja3:t.ja3_hash||null,ja4:t.ja4||null};
      if(Object.values(facts).some(v=>v!==null&&(typeof v!=="string"||v.length>200))||!Object.values(facts).some(Boolean))return item("error");return item("ok",facts);
    }catch{return item(ctrl.signal.aborted?"timeout":"error");}finally{clearTimeout(timer);}
  }
  async function dns(endpoint){
    if(!endpoint)return item("configuration_required");
    const base=new URL(endpoint);if(base.protocol!=="https:"||base.username||base.password||base.search||base.hash||base.pathname!=="/"||base.port)return item("error");
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
    const request=async url=>{const r=await fetch(url,{credentials:"omit",cache:"no-store",referrerPolicy:"no-referrer",redirect:"error",signal:controller.signal});if(!r.ok)throw new Error();return JSON.parse(await root.ZhibiNetwork.limitedText(r,8192));};
    try{const ticket=await request(base.origin+"/ticket");if(!/^[a-f0-9]{32}$/.test(ticket.token)||ticket.zone!==base.hostname)throw new Error();
      try{await request("https://"+ticket.token+"."+base.hostname+"/ping");}catch{}
      const data=await request(base.origin+"/result?token="+ticket.token);
      if(data.token!==ticket.token||!Array.isArray(data.resolvers)||data.resolvers.length>16||data.resolvers.some(ip=>!root.ZhibiNetwork.validIp(ip))||!Array.isArray(data.ecs)||data.ecs.length>16)throw new Error();
      return item(data.resolvers.length?"ok":"no_record",{observer:base.origin,resolvers:data.resolvers,ecs:data.ecs,transport_from_browser:"not_observable"});
    }catch{return item(controller.signal.aborted?"timeout":"error");}finally{clearTimeout(timer);}
  }
  async function collect(selected, dnsEndpoint=""){
    const checks={};for(const k of MODULES){if(!selected[k]){checks[k]=item("skipped");continue;}let timer;
      try{checks[k]=await Promise.race([(k==="canvas"?canvas(root.document):k==="webgl"?Promise.resolve(webgl(root.document)):k==="audio"?audio():k==="dns"?dns(dnsEndpoint):tls()),new Promise(resolve=>{timer=setTimeout(()=>resolve(item("timeout")),10000);})]);}
      catch{checks[k]=item("error");}finally{clearTimeout(timer);}}
    return {at:new Date().toISOString(),checks};
  }
  function reading(k,f){if(!f)return "没有取得读数";if(k==="canvas")return f.repeated_equal?"两次渲染相同":"两次渲染不同";if(k==="webgl")return f.renderer;if(k==="audio")return f.samples+" 个离线样本；未使用麦克风";if(k==="dns")return f.resolvers.length+" 个递归解析器；无法从权威侧判断浏览器是否使用 DoH";return [f.http_version,f.tls_version].filter(Boolean).join(" / ");}
  const api={MODULES,LABELS,collect,reading};root.ZhibiExtras=api;if(typeof module!=="undefined")module.exports=api;
})(globalThis);
