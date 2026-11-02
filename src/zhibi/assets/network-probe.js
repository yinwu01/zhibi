/*
 * IP validation and bounded fetch adapted from CCBaga src/browser-network.ts
 * Copyright (c) 2026 CCBaga contributors; MIT, see THIRD_PARTY_NOTICES.md.
 * Browser environment collection adapted from CheckCC src/detection/client-engine.ts
 * Copyright (c) 2026 yacuo / CheckCC; MIT, see THIRD_PARTY_NOTICES.md.
 * Zhibi changes: separate address families, explicit recipients, omit credentials,
 * bounded streaming reads, no automatic fallback, fixed errors, optional ICE observation.
 */
(function (root) {
  "use strict";
  const ENDPOINTS = Object.freeze({ipv4:"https://api.ipify.org?format=json",ipv6:"https://api6.ipify.org?format=json"});
  const STUN = "stun:stun.l.google.com:19302";
  function validIp(ip) {
    if(typeof ip!=="string") return false;
    if(ip.includes(":")) {
      if(!/^[0-9A-Fa-f:.]+$/.test(ip)) return false;
      try {return new URL(`http://[${ip}]/`).hostname.startsWith("[");} catch {return false;}
    }
    return ip.split(".").length===4 && ip.split(".").every(x=>/^(0|[1-9]\d{0,2})$/.test(x)&&Number(x)<=255);
  }
  function parseAddress(value, family) {
    if(!value || value.success===false || value.error || !validIp(value.ip) || (value.ip.includes(":")?6:4)!==family) throw new Error("invalid_response");
    return value.ip;
  }
  async function limitedText(response, limit=32768) {
    if(!response.body || !response.body.getReader) {
      const text=await response.text(); if(text.length>limit) throw new Error("invalid_response"); return text;
    }
    const reader=response.body.getReader(), chunks=[]; let size=0;
    try {
      for(;;) {const {value,done}=await reader.read(); if(done)break;size+=value.byteLength;
        if(size>limit)throw new Error("invalid_response");chunks.push(value);}
    } finally {await reader.cancel().catch(()=>{});reader.releaseLock();}
    const joined=new Uint8Array(size); let offset=0;
    for(const chunk of chunks){joined.set(chunk,offset);offset+=chunk.byteLength;}
    return new TextDecoder("utf-8",{fatal:true}).decode(joined);
  }
  async function probeBrowserExit(family, request=fetch) {
    const endpoint=ENDPOINTS["ipv"+family];
    if(!endpoint)throw new Error("unsupported_family");
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),8000);
    const at=new Date().toISOString();
    try {
      const response=await request(endpoint,{cache:"no-store",signal:controller.signal,credentials:"omit",referrerPolicy:"no-referrer",redirect:"error"});
      if(!response.ok)return {family,endpoint,at,status:response.status===429?"quota_exceeded":"error",ip:null};
      const data=JSON.parse(await limitedText(response));
      return {family,endpoint,at,status:"ok",ip:parseAddress(data,family)};
    } catch(error) {
      return {family,endpoint,at,status:controller.signal.aborted?"timeout":error.message==="invalid_response"?"invalid_response":"error",ip:null};
    } finally {clearTimeout(timer);}
  }
  function collectBrowserEnvironment(nav=navigator) {
    let timezone=null, locale=null;
    try {const options=Intl.DateTimeFormat().resolvedOptions();timezone=options.timeZone||null;locale=options.locale||null;}catch{}
    return {languages:(nav.languages?.length?[...nav.languages]:[nav.language].filter(Boolean)).slice(0,20),
      timezone,locale,userAgent:String(nav.userAgent||"").slice(0,1000),
      platform:nav.userAgentData?.platform||null,
      brands:nav.userAgentData?.brands?.map(item=>item.brand).join(" / ")||null};
  }
  function parseCandidate(candidate) {
    if(!candidate || typeof candidate.candidate!=="string")return null;
    const words=candidate.candidate.trim().split(/\s+/);
    const type=words[7], address=words[4], protocol=(words[2]||"").toLowerCase();
    if(!["host","srflx","relay","prflx"].includes(type)||!["udp","tcp"].includes(protocol))return null;
    const mdns=typeof address==="string"&&/^[a-zA-Z0-9.-]+\.local$/.test(address);
    if(!mdns&&!validIp(address))return null;
    return {type,protocol,address:mdns?null:address,mdns};
  }
  function probeWebRTC(Peer=globalThis.RTCPeerConnection) {
    const at=new Date().toISOString();
    if(!Peer)return Promise.resolve({status:"unsupported",at,endpoint:STUN,candidates:[],complete:false});
    return new Promise(resolve=>{
      let peer,timer,finished=false;const candidates=[];
      const finish=(status,complete=false)=>{
        if(finished)return;finished=true;clearTimeout(timer);
        if(peer){peer.onicecandidate=null;peer.onicegatheringstatechange=null;peer.close();}
        resolve({status,at,endpoint:STUN,candidates,complete});
      };
      try {
        peer=new Peer({iceServers:[{urls:STUN}],iceCandidatePoolSize:0});
        peer.onicecandidate=event=>{
          if(!event.candidate){finish(candidates.length?"ok":"no_candidates",true);return;}
          const parsed=parseCandidate(event.candidate);
          if(parsed && candidates.length<64 && !candidates.some(c=>JSON.stringify(c)===JSON.stringify(parsed)))candidates.push(parsed);
        };
        peer.onicegatheringstatechange=()=>{if(peer.iceGatheringState==="complete")finish(candidates.length?"ok":"no_candidates",true);};
        timer=setTimeout(()=>finish("timeout",false),8000);
        peer.createDataChannel("zhibi-network-observation");
        Promise.resolve(peer.createOffer()).then(offer=>peer.setLocalDescription(offer)).catch(()=>finish("error"));
      } catch {finish("error");}
    });
  }
  const api={ENDPOINTS,STUN,validIp,parseAddress,limitedText,probeBrowserExit,collectBrowserEnvironment,parseCandidate,probeWebRTC};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  else root.ZhibiNetwork=api;
})(globalThis);
