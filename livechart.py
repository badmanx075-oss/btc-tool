"""Browser-side live widgets (no server load, no API key):
  chart_html(positions)  : TradingView-style chart (open-source 'lightweight-charts' by TradingView) for BTC / ETH / SOL with indicators you can switch on/off
                           (EMA20/50/200, Bollinger, VWAP, Volume, RSI, MACD). Your choices (coin, timeframe, indicators) are saved in the browser (localStorage),
                           so a page refresh does NOT reset them. Candles come straight from OKX (fallback Binance, Bybit) and update every 3 seconds. Open paper trades are drawn as lines.
  ticker_html(positions) : live price strip for ETH and SOL (websocket, REST fallback) with the open paper P/L of each coin.
Times are shown in IST. The BTC live-price widget in app.py is separate and untouched."""
import json

LW = "https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"

CHART = r"""<meta charset="utf-8"><div id="wrap" style="font-family:-apple-system,Segoe UI,sans-serif;color:#d1d4dc;background:#131722;border-radius:8px;padding:6px;position:relative">
<style>
.b{background:#1e222d;color:#d1d4dc;border:1px solid #2a2e39;border-radius:5px;padding:4px 9px;margin:2px;cursor:pointer;font-size:13px}
.b.on{background:#2962ff;border-color:#2962ff;color:#fff}.sep{display:inline-block;width:10px}
#last{font-size:20px;font-weight:700;margin-left:10px}
#q{background:#1e222d;color:#d1d4dc;border:1px solid #2a2e39;border-radius:5px;padding:5px 8px;width:230px;font-size:13px}
#res{position:absolute;z-index:20;background:#1e222d;border:1px solid #2a2e39;border-radius:6px;max-height:260px;overflow:auto;display:none;min-width:260px}
#res div{padding:6px 10px;cursor:pointer;font-size:13px}#res div:hover{background:#2962ff}
.chip{display:inline-flex;align-items:center;gap:4px;background:#1e222d;border:1px solid #2a2e39;border-radius:14px;padding:2px 8px;margin:2px;font-size:12px}
.chip input{width:42px;background:#131722;color:#d1d4dc;border:1px solid #2a2e39;border-radius:3px;font-size:11px;padding:1px 3px}
.chip i{cursor:pointer;opacity:.7;font-style:normal;padding:0 2px}.chip i:hover{opacity:1;color:#ef5350}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.pane{margin-top:2px;position:relative}.pt{position:absolute;left:6px;top:2px;font-size:11px;opacity:.75;z-index:5;pointer-events:none}
</style>
<div id="bar"></div><div id="bar2" style="margin-top:2px"></div><div id="chips"></div><div id="res"></div>
<div id="main" style="height:__H1__px;width:100%"></div><div id="panes"></div>
<div id="msg" style="font-size:12px;opacity:.7;padding:3px"></div></div>
<script src="__LW__"></script>
<script>
(function(){
const POS=__POS__, FORCE="__COIN__", COINS=["BTC","ETH","SOL"], TFS=["5m","15m","1H","4H","1D"];
const KEY="btcTool.chart.v2", OFF=19800, COLS=["#f5a623","#2962ff","#e040fb","#00bcd4","#8bc34a","#ff7043","#ffd54f","#90caf9","#f06292","#a1887f"];
let cfg={coin:"BTC",tf:"1H",inds:[{id:1,type:"ema",p:{len:20}},{id:2,type:"ema",p:{len:50}},{id:3,type:"volume",p:{}},{id:4,type:"rsi",p:{len:14}}],draw:{},nid:10};
try{const s=JSON.parse(localStorage.getItem(KEY)||"{}"); Object.keys(s).forEach(k=>{if(k in cfg) cfg[k]=s[k];});}catch(e){}
if(FORCE) cfg.coin=FORCE;
function save(){try{localStorage.setItem(KEY,JSON.stringify(cfg));}catch(e){}}
const $=id=>document.getElementById(id), msg=t=>$("msg").textContent=t;
// ---------- data
const BY={"5m":"5","15m":"15","1H":"60","4H":"240","1D":"D"}, BN={"5m":"5m","15m":"15m","1H":"1h","4H":"4h","1D":"1d"};
async function jget(u){const r=await fetch(u); if(!r.ok) throw new Error(r.status); return r.json();}
async function srcOKX(c,tf,full){const inst=c+"-USDT-SWAP", b="https://www.okx.com/api/v5/market/";
 let j=await jget(b+"candles?instId="+inst+"&bar="+tf+"&limit="+(full?300:2)); let out=j.data||[]; if(!out.length) throw new Error("okx empty");
 if(full) for(let k=0;k<5;k++){const a=out[out.length-1][0]; const h=await jget(b+"history-candles?instId="+inst+"&bar="+tf+"&limit=100&after="+a); if(!h.data||!h.data.length) break; out=out.concat(h.data);}
 return out.map(x=>[+x[0],+x[1],+x[2],+x[3],+x[4],+x[5]]);}
async function srcBN(c,tf,full){const j=await jget("https://fapi.binance.com/fapi/v1/klines?symbol="+c+"USDT&interval="+BN[tf]+"&limit="+(full?1000:2)); return j.map(x=>[+x[0],+x[1],+x[2],+x[3],+x[4],+x[5]]);}
async function srcBY(c,tf,full){const j=await jget("https://api.bybit.com/v5/market/kline?category=linear&symbol="+c+"USDT&interval="+BY[tf]+"&limit="+(full?1000:2)); return j.result.list.map(x=>[+x[0],+x[1],+x[2],+x[3],+x[4],+x[5]]);}
const SRCS=[["OKX",srcOKX],["Binance",srcBN],["Bybit",srcBY]]; let srcIdx=0;
async function fetchBars(c,tf,full){let err; for(let k=0;k<SRCS.length;k++){const i=(srcIdx+k)%SRCS.length; try{const r=await SRCS[i][1](c,tf,full); srcIdx=i; return r.map(x=>({t:x[0]/1000+OFF,o:x[1],h:x[2],l:x[3],c:x[4],v:x[5]})).sort((a,b)=>a.t-b.t);}catch(e){err=e;}} throw err;}
// ---------- indicator maths (arrays aligned with bars, null = not available)
const N=(a)=>a.map(v=>(v===undefined||isNaN(v))?null:v);
function ema(a,n){const k=2/(n+1); let p=null; return a.map((v,i)=>{if(v===null) return null; p=p===null?v:v*k+p*(1-k); return i>=n-1?p:null;});}
function sma(a,n){const o=[]; let s=0,c=0; const q=[]; for(let i=0;i<a.length;i++){const v=a[i]; q.push(v); if(v!==null){s+=v;c++;} if(q.length>n){const x=q.shift(); if(x!==null){s-=x;c--;}} o.push(q.length===n&&c===n?s/n:null);} return o;}
function wma(a,n){return a.map((_,i)=>{if(i<n-1) return null; let s=0,w=0; for(let j=0;j<n;j++){const v=a[i-j]; if(v===null) return null; s+=v*(n-j); w+=n-j;} return s/w;});}
function stdev(a,n){return a.map((_,i)=>{if(i<n-1) return null; let m=0; for(let j=i-n+1;j<=i;j++) m+=a[j]; m/=n; let s=0; for(let j=i-n+1;j<=i;j++) s+=(a[j]-m)**2; return Math.sqrt(s/n);});}
function rma(a,n){let p=null; return a.map((v,i)=>{if(v===null) return null; p=p===null?v:(p*(n-1)+v)/n; return i>=n-1?p:null;});}
function trueRange(B){return B.map((b,i)=>i===0?b.h-b.l:Math.max(b.h-b.l,Math.abs(b.h-B[i-1].c),Math.abs(b.l-B[i-1].c)));}
function atr(B,n){return rma(trueRange(B),n);}
function rsi(a,n){const o=[null]; let g=0,l=0; for(let i=1;i<a.length;i++){const d=a[i]-a[i-1], u=Math.max(d,0), w=Math.max(-d,0); if(i<=n){g+=u;l+=w; if(i<n){o.push(null);continue;} g/=n;l/=n;} else {g=(g*(n-1)+u)/n; l=(l*(n-1)+w)/n;} o.push(l===0?100:100-100/(1+g/l));} return o;}
function vwap(B){let day=-1,pv=0,vv=0; return B.map(b=>{const d=Math.floor(b.t/86400); if(d!==day){day=d;pv=0;vv=0;} pv+=(b.h+b.l+b.c)/3*b.v; vv+=b.v; return vv>0?pv/vv:null;});}
function hh(B,n,f){return B.map((_,i)=>{if(i<n-1) return null; let m=f==="h"?-Infinity:Infinity; for(let j=i-n+1;j<=i;j++) m=f==="h"?Math.max(m,B[j].h):Math.min(m,B[j].l); return m;});}
function supertrend(B,n,m){const a=atr(B,n), up=[], dn=[], tr=[], col=[]; let fu=null,fl=null,dir=1; const out=[];
 for(let i=0;i<B.length;i++){ if(a[i]===null){out.push({v:null});continue;} const hl=(B[i].h+B[i].l)/2; let bu=hl+m*a[i], bl=hl-m*a[i];
  if(fu===null){fu=bu;fl=bl;} else {fu=(bu<fu||B[i-1].c>fu)?bu:fu; fl=(bl>fl||B[i-1].c<fl)?bl:fl; if(dir===1&&B[i].c<fl) dir=-1; else if(dir===-1&&B[i].c>fu) dir=1;}
  out.push({v:dir===1?fl:fu,c:dir===1?"#26a69a":"#ef5350"});} return out;}
function stoch(B,k,d){const K=B.map((b,i)=>{if(i<k-1) return null; let hi=-Infinity,lo=Infinity; for(let j=i-k+1;j<=i;j++){hi=Math.max(hi,B[j].h);lo=Math.min(lo,B[j].l);} return hi===lo?50:(b.c-lo)/(hi-lo)*100;}); return [K,sma(K,d)];}
function adx(B,n){const pdm=[0],ndm=[0]; for(let i=1;i<B.length;i++){const u=B[i].h-B[i-1].h, d=B[i-1].l-B[i].l; pdm.push(u>d&&u>0?u:0); ndm.push(d>u&&d>0?d:0);} const a=atr(B,n), ps=rma(pdm.map((v,i)=>i===0?null:v),n), ns=rma(ndm.map((v,i)=>i===0?null:v),n);
 const pdi=a.map((x,i)=>x&&ps[i]!==null?100*ps[i]/x:null), ndi=a.map((x,i)=>x&&ns[i]!==null?100*ns[i]/x:null); const dx=pdi.map((p,i)=>p===null||ndi[i]===null?null:(p+ndi[i]===0?0:100*Math.abs(p-ndi[i])/(p+ndi[i]))); return [rma(dx,n),pdi,ndi];}
function cci(B,n){const tp=B.map(b=>(b.h+b.l+b.c)/3), m=sma(tp,n); return tp.map((v,i)=>{if(m[i]===null) return null; let d=0; for(let j=i-n+1;j<=i;j++) d+=Math.abs(tp[j]-m[i]); d/=n; return d===0?0:(v-m[i])/(0.015*d);});}
function obv(B){let s=0; return B.map((b,i)=>{if(i>0) s+=b.c>B[i-1].c?b.v:b.c<B[i-1].c?-b.v:0; return s;});}
function mfi(B,n){const tp=B.map(b=>(b.h+b.l+b.c)/3); return B.map((_,i)=>{if(i<n) return null; let p=0,q=0; for(let j=i-n+1;j<=i;j++){const f=tp[j]*B[j].v; if(tp[j]>tp[j-1]) p+=f; else if(tp[j]<tp[j-1]) q+=f;} return q===0?100:100-100/(1+p/q);});}
function roc(a,n){return a.map((v,i)=>i<n||a[i-n]===0?null:(v-a[i-n])/a[i-n]*100);}

function dema(a,n){const e=ema(a,n), e2=ema(e,n); return e.map((v,i)=>v===null||e2[i]===null?null:2*v-e2[i]);}
function tema(a,n){const e=ema(a,n), e2=ema(e,n), e3=ema(e2,n); return e.map((v,i)=>v===null||e2[i]===null||e3[i]===null?null:3*v-3*e2[i]+e3[i]);}
function hma(a,n){const h=Math.max(Math.floor(n/2),1), q=Math.max(Math.round(Math.sqrt(n)),1), w1=wma(a,h), w2=wma(a,n); return wma(w1.map((v,i)=>v===null||w2[i]===null?null:2*v-w2[i]),q);}
function linreg(a,n){return a.map((_,i)=>{if(i<n-1) return null; let sx=0,sy=0,sxy=0,sxx=0; for(let j=0;j<n;j++){const y=a[i-n+1+j]; sx+=j; sy+=y; sxy+=j*y; sxx+=j*j;} const b=(n*sxy-sx*sy)/(n*sxx-sx*sx), c=(sy-b*sx)/n; return c+b*(n-1);});}
function psar(B,st,mx){const o=[]; let up=true, af=st, ep=B[0].h, sar=B[0].l; o.push({v:sar,c:"#26a69a"});
 for(let i=1;i<B.length;i++){sar=sar+af*(ep-sar); if(up){sar=Math.min(sar,B[i-1].l,i>1?B[i-2].l:B[i-1].l); if(B[i].l<sar){up=false; sar=ep; ep=B[i].l; af=st;} else if(B[i].h>ep){ep=B[i].h; af=Math.min(af+st,mx);}}
  else{sar=Math.max(sar,B[i-1].h,i>1?B[i-2].h:B[i-1].h); if(B[i].h>sar){up=true; sar=ep; ep=B[i].h; af=st;} else if(B[i].l<ep){ep=B[i].l; af=Math.min(af+st,mx);}}
  o.push({v:sar,c:up?"#26a69a":"#ef5350"});} return o;}
function willr(B,n){return B.map((b,i)=>{if(i<n-1) return null; let hi=-Infinity,lo=Infinity; for(let j=i-n+1;j<=i;j++){hi=Math.max(hi,B[j].h);lo=Math.min(lo,B[j].l);} return hi===lo?-50:(hi-b.c)/(hi-lo)*-100;});}
function aroon(B,n){const U=[],D=[]; B.forEach((_,i)=>{if(i<n){U.push(null);D.push(null);return;} let hi=-Infinity,lo=Infinity,hi_i=i,lo_i=i; for(let j=i-n;j<=i;j++){if(B[j].h>=hi){hi=B[j].h;hi_i=j;} if(B[j].l<=lo){lo=B[j].l;lo_i=j;}} U.push(100*(n-(i-hi_i))/n); D.push(100*(n-(i-lo_i))/n);}); return [U,D];}
function trix(a,n){const e=ema(ema(ema(a,n),n),n); return e.map((v,i)=>v===null||i===0||e[i-1]===null?null:(v-e[i-1])/e[i-1]*100);}
function cmf(B,n){const m=B.map(b=>b.h===b.l?0:((b.c-b.l)-(b.h-b.c))/(b.h-b.l)*b.v); return B.map((_,i)=>{if(i<n-1) return null; let a=0,v=0; for(let j=i-n+1;j<=i;j++){a+=m[j]; v+=B[j].v;} return v===0?0:a/v;});}
function uo(B,a,b,c){const bp=B.map((x,i)=>x.c-Math.min(x.l,i?B[i-1].c:x.l)), tr=B.map((x,i)=>Math.max(x.h,i?B[i-1].c:x.h)-Math.min(x.l,i?B[i-1].c:x.l)); const sm=(arr,n,i)=>{let s=0; for(let j=i-n+1;j<=i;j++) s+=arr[j]; return s;};
 return B.map((_,i)=>{if(i<c) return null; const A=sm(bp,a,i)/sm(tr,a,i), Bv=sm(bp,b,i)/sm(tr,b,i), Cv=sm(bp,c,i)/sm(tr,c,i); return 100*(4*A+2*Bv+Cv)/7;});}
function ao(B){const m=B.map(b=>(b.h+b.l)/2), a=sma(m,5), c=sma(m,34); return a.map((v,i)=>v===null||c[i]===null?null:v-c[i]);}
function mom(a,n){return a.map((v,i)=>i<n?null:v-a[i-n]);}
function bbw(a,n,m){const s=sma(a,n), d=stdev(a,n); return s.map((v,i)=>v===null?null:2*m*d[i]/v*100);}
function ppo(a,f,s){const x=ema(a,f), y=ema(a,s); return x.map((v,i)=>v===null||y[i]===null?null:(v-y[i])/y[i]*100);}
function tsi(a,r,s){const m=a.map((v,i)=>i?v-a[i-1]:0), am=m.map(Math.abs); const e=x=>emaRaw(emaRaw(x,r),s); const n=e(m), d=e(am); return n.map((v,i)=>i<r+s||d[i]===0?null:100*v/d[i]);}
function emaRaw(a,n){const k=2/(n+1); let p=null; return a.map(v=>p=(p===null?v:v*k+p*(1-k)));}
function stochrsi(a,n,k,d){const r=rsi(a,n), K=r.map((v,i)=>{if(i<n*2-1||v===null) return null; let hi=-Infinity,lo=Infinity; for(let j=i-n+1;j<=i;j++){hi=Math.max(hi,r[j]);lo=Math.min(lo,r[j]);} return hi===lo?50:(v-lo)/(hi-lo)*100;}); const ks=sma(K,k); return [ks,sma(ks,d)];}
function ichi(B,t,k,sb){const hl=(n,i,f)=>{if(i<n-1) return null; let hi=-Infinity,lo=Infinity; for(let j=i-n+1;j<=i;j++){hi=Math.max(hi,B[j].h);lo=Math.min(lo,B[j].l);} return f?hi:lo;}; const mid=(n,i)=>{const h=hl(n,i,1),l=hl(n,i,0); return h===null?null:(h+l)/2;};
 const T=B.map((_,i)=>mid(t,i)), K=B.map((_,i)=>mid(k,i)), A=B.map((_,i)=>T[i]===null||K[i]===null?null:(T[i]+K[i])/2), Bv=B.map((_,i)=>mid(sb,i)); const st=B.length>1?B[1].t-B[0].t:3600, tm=B.map((b,i)=>b.t+k*st); return [T,K,A,Bv,tm];}
function pivots(B,kind,per){const key=b=>{const d=Math.floor(b.t/86400); if(per===1) return Math.floor((d+3)/7); if(per===2){const x=new Date(b.t*1000); return x.getUTCFullYear()*12+x.getUTCMonth();} return d;};
 const g={}; const order=[]; B.forEach(b=>{const q=key(b); if(!g[q]){g[q]={h:b.h,l:b.l,c:b.c}; order.push(q);} else {g[q].h=Math.max(g[q].h,b.h); g[q].l=Math.min(g[q].l,b.l); g[q].c=b.c;}});
 const lv=q=>{const x=g[q]; if(!x) return null; const H=x.h,L=x.l,C=x.c,R=H-L; let P=(H+L+C)/3, r1,r2,r3,s1,s2,s3;
  if(kind===1){r1=P+0.382*R;r2=P+0.618*R;r3=P+R;s1=P-0.382*R;s2=P-0.618*R;s3=P-R;}
  else if(kind===2){r1=C+1.1*R/12;r2=C+1.1*R/6;r3=C+1.1*R/4;s1=C-1.1*R/12;s2=C-1.1*R/6;s3=C-1.1*R/4;}
  else if(kind===3){P=(H+L+2*C)/4; r1=2*P-L;s1=2*P-H;r2=P+R;s2=P-R;r3=H+2*(P-L);s3=L-2*(H-P);}
  else {r1=2*P-L;s1=2*P-H;r2=P+R;s2=P-R;r3=H+2*(P-L);s3=L-2*(H-P);} return [P,r1,r2,r3,s1,s2,s3];};
 const out=[[],[],[],[],[],[],[]]; let prev=null;
 B.forEach((b,i)=>{const q=key(b), idx=order.indexOf(q), p=idx>0?lv(order[idx-1]):null, first=i===0||key(B[i-1])!==q; for(let j=0;j<7;j++) out[j].push(p&&!first?p[j]:null);});
 return out;}
// ---------- catalog: kind overlay (on price) / pane (own chart). out(B,p) -> list of series {t:"line"|"hist", v:[...], c:color or null (cycle), w, pts:[{v,c}] for per-point colors, lines:[levels]}
const C_=B=>B.map(b=>b.c);
const CAT={
 ema:{n:"EMA (exponential moving average)",k:"overlay",p:{len:20},lab:p=>"EMA "+p.len,out:(B,p)=>[{v:ema(C_(B),+p.len)}]},
 sma:{n:"SMA (simple moving average)",k:"overlay",p:{len:50},lab:p=>"SMA "+p.len,out:(B,p)=>[{v:sma(C_(B),+p.len)}]},
 wma:{n:"WMA (weighted moving average)",k:"overlay",p:{len:20},lab:p=>"WMA "+p.len,out:(B,p)=>[{v:wma(C_(B),+p.len)}]},
 bb:{n:"Bollinger Bands",k:"overlay",p:{len:20,mult:2},lab:p=>"BB "+p.len+","+p.mult,out:(B,p)=>{const m=sma(C_(B),+p.len), s=stdev(C_(B),+p.len); return [{v:m.map((x,i)=>x===null?null:x+p.mult*s[i]),c:"#78909c"},{v:m,c:"#546e7a"},{v:m.map((x,i)=>x===null?null:x-p.mult*s[i]),c:"#78909c"}];}},
 vwap:{n:"VWAP (daily)",k:"overlay",p:{},lab:p=>"VWAP",out:B=>[{v:vwap(B)}]},
 supertrend:{n:"Supertrend",k:"overlay",p:{len:10,mult:3},lab:p=>"Supertrend "+p.len+","+p.mult,out:(B,p)=>[{pts:supertrend(B,+p.len,+p.mult),w:2}]},
 donchian:{n:"Donchian Channel",k:"overlay",p:{len:20},lab:p=>"Donchian "+p.len,out:(B,p)=>[{v:hh(B,+p.len,"h")},{v:hh(B,+p.len,"l")}]},
 keltner:{n:"Keltner Channel",k:"overlay",p:{len:20,mult:2},lab:p=>"Keltner "+p.len,out:(B,p)=>{const m=ema(C_(B),+p.len), a=atr(B,+p.len); return [{v:m.map((x,i)=>x===null||a[i]===null?null:x+p.mult*a[i])},{v:m},{v:m.map((x,i)=>x===null||a[i]===null?null:x-p.mult*a[i])}];}},
 volume:{n:"Volume",k:"overlay",p:{},lab:p=>"Volume",out:B=>[{t:"vol"}]},
 rsi:{n:"RSI (relative strength)",k:"pane",p:{len:14},lab:p=>"RSI "+p.len,out:(B,p)=>[{v:rsi(C_(B),+p.len),lines:[70,30]}]},
 macd:{n:"MACD",k:"pane",p:{fast:12,slow:26,sig:9},lab:p=>"MACD "+p.fast+","+p.slow+","+p.sig,out:(B,p)=>{const a=ema(C_(B),+p.fast), b=ema(C_(B),+p.slow), m=a.map((x,i)=>x===null||b[i]===null?null:x-b[i]), s=ema(m,+p.sig); return [{t:"hist",v:m.map((x,i)=>x===null||s[i]===null?null:x-s[i])},{v:m,c:"#2962ff"},{v:s,c:"#ff9800"}];}},
 stoch:{n:"Stochastic",k:"pane",p:{k:14,d:3},lab:p=>"Stoch "+p.k+","+p.d,out:(B,p)=>{const r=stoch(B,+p.k,+p.d); return [{v:r[0],c:"#2962ff",lines:[80,20]},{v:r[1],c:"#ff9800"}];}},
 atr:{n:"ATR (average true range)",k:"pane",p:{len:14},lab:p=>"ATR "+p.len,out:(B,p)=>[{v:atr(B,+p.len)}]},
 adx:{n:"ADX (trend strength, +DI / -DI)",k:"pane",p:{len:14},lab:p=>"ADX "+p.len,out:(B,p)=>{const r=adx(B,+p.len); return [{v:r[0],c:"#f5a623",w:2,lines:[25]},{v:r[1],c:"#26a69a"},{v:r[2],c:"#ef5350"}];}},
 cci:{n:"CCI",k:"pane",p:{len:20},lab:p=>"CCI "+p.len,out:(B,p)=>[{v:cci(B,+p.len),lines:[100,-100]}]},
 obv:{n:"OBV (on balance volume)",k:"pane",p:{},lab:p=>"OBV",out:B=>[{v:obv(B)}]},
 mfi:{n:"MFI (money flow index)",k:"pane",p:{len:14},lab:p=>"MFI "+p.len,out:(B,p)=>[{v:mfi(B,+p.len),lines:[80,20]}]},
 roc:{n:"ROC (rate of change %)",k:"pane",p:{len:12},lab:p=>"ROC "+p.len,out:(B,p)=>[{v:roc(C_(B),+p.len),lines:[0]}]},
 dema:{n:"DEMA (double EMA)",k:"overlay",p:{len:20},lab:p=>"DEMA "+p.len,out:(B,p)=>[{v:dema(C_(B),+p.len)}]},
 tema:{n:"TEMA (triple EMA)",k:"overlay",p:{len:20},lab:p=>"TEMA "+p.len,out:(B,p)=>[{v:tema(C_(B),+p.len)}]},
 hma:{n:"HMA (Hull moving average)",k:"overlay",p:{len:21},lab:p=>"HMA "+p.len,out:(B,p)=>[{v:hma(C_(B),+p.len)}]},
 linreg:{n:"Linear Regression line",k:"overlay",p:{len:50},lab:p=>"LinReg "+p.len,out:(B,p)=>[{v:linreg(C_(B),+p.len)}]},
 psar:{n:"Parabolic SAR",k:"overlay",p:{step:0.02,max:0.2},lab:p=>"PSAR",out:(B,p)=>[{pts:psar(B,+p.step,+p.max),dots:1}]},
 ichimoku:{n:"Ichimoku Cloud (lines)",k:"overlay",p:{tenkan:9,kijun:26,spanB:52},lab:p=>"Ichimoku",out:(B,p)=>{const r=ichi(B,+p.tenkan,+p.kijun,+p.spanB); return [{v:r[0],c:"#2962ff"},{v:r[1],c:"#e040fb"},{v:r[2],c:"#26a69a",tm:r[4]},{v:r[3],c:"#ef5350",tm:r[4]}];}},
 pivot:{n:"Pivot Points Standard (kind: 0 Traditional, 1 Fibonacci, 2 Camarilla, 3 Woodie | period: 0 day, 1 week, 2 month)",k:"overlay",p:{kind:0,period:0},lab:p=>"Pivot",out:(B,p)=>{const r=pivots(B,+p.kind,+p.period), cs=["#ffd54f","#ef5350","#e57373","#ffcdd2","#26a69a","#81c784","#c8e6c9"]; return r.map((v,i)=>({v:v,c:cs[i],ptitle:["P","R1","R2","R3","S1","S2","S3"][i]}));}},
 willr:{n:"Williams %R",k:"pane",p:{len:14},lab:p=>"Williams %R "+p.len,out:(B,p)=>[{v:willr(B,+p.len),lines:[-20,-80]}]},
 ao:{n:"Awesome Oscillator",k:"pane",p:{},lab:p=>"AO",out:B=>[{t:"hist",v:ao(B)}]},
 aroon:{n:"Aroon (up / down)",k:"pane",p:{len:25},lab:p=>"Aroon "+p.len,out:(B,p)=>{const r=aroon(B,+p.len); return [{v:r[0],c:"#26a69a"},{v:r[1],c:"#ef5350"}];}},
 trix:{n:"TRIX",k:"pane",p:{len:15},lab:p=>"TRIX "+p.len,out:(B,p)=>[{v:trix(C_(B),+p.len),lines:[0]}]},
 cmf:{n:"Chaikin Money Flow",k:"pane",p:{len:20},lab:p=>"CMF "+p.len,out:(B,p)=>[{v:cmf(B,+p.len),lines:[0]}]},
 uo:{n:"Ultimate Oscillator",k:"pane",p:{a:7,b:14,c:28},lab:p=>"UO",out:(B,p)=>[{v:uo(B,+p.a,+p.b,+p.c),lines:[70,30]}]},
 stochrsi:{n:"Stochastic RSI",k:"pane",p:{len:14,k:3,d:3},lab:p=>"StochRSI "+p.len,out:(B,p)=>{const r=stochrsi(C_(B),+p.len,+p.k,+p.d); return [{v:r[0],c:"#2962ff",lines:[80,20]},{v:r[1],c:"#ff9800"}];}},
 mom:{n:"Momentum",k:"pane",p:{len:10},lab:p=>"Momentum "+p.len,out:(B,p)=>[{v:mom(C_(B),+p.len),lines:[0]}]},
 bbw:{n:"Bollinger Band Width",k:"pane",p:{len:20,mult:2},lab:p=>"BB Width",out:(B,p)=>[{v:bbw(C_(B),+p.len,+p.mult)}]},
 ppo:{n:"PPO (percentage price oscillator)",k:"pane",p:{fast:12,slow:26},lab:p=>"PPO",out:(B,p)=>[{v:ppo(C_(B),+p.fast,+p.slow),lines:[0]}]},
 tsi:{n:"TSI (true strength index)",k:"pane",p:{long:25,short:13},lab:p=>"TSI",out:(B,p)=>[{v:tsi(C_(B),+p.long,+p.short),lines:[0]}]}
};
// ---------- charts
const base={layout:{background:{color:"#131722"},textColor:"#d1d4dc"},grid:{vertLines:{color:"#1e222d"},horzLines:{color:"#1e222d"}},rightPriceScale:{borderColor:"#2a2e39"},timeScale:{borderColor:"#2a2e39",timeVisible:true,secondsVisible:false},crosshair:{mode:0}};
const W=()=>Math.max($("wrap").clientWidth-12,200);
const cM=LightweightCharts.createChart($("main"),Object.assign({width:W(),height:__H1__},base));
const candle=cM.addCandlestickSeries({upColor:"#26a69a",downColor:"#ef5350",borderVisible:false,wickUpColor:"#26a69a",wickDownColor:"#ef5350"});
const inst={};          // id -> {chart, el, series:[...], lines:[...]}
let syncing=false, bars=[], lines=[], draws=[], tok=0, mode="";
const allCharts=()=>[cM].concat(Object.values(inst).filter(x=>x.chart).map(x=>x.chart));
function syncAdd(ch){ch.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(syncing||!r) return; syncing=true; allCharts().forEach(o=>{if(o!==ch){try{o.timeScale().setVisibleLogicalRange(r);}catch(e){}}}); syncing=false;});}
syncAdd(cM);
function colorFor(i,j){return COLS[(i*3+j)%COLS.length];}
function build(it){const d=CAT[it.type]; if(!d) return; let o={series:[],lines:[]}; inst[it.id]=o; let chart=cM;
 if(d.k==="pane"){const el=document.createElement("div"); el.className="pane"; el.style.height="125px"; el.innerHTML="<div class=pt></div>"; $("panes").appendChild(el); chart=LightweightCharts.createChart(el,Object.assign({width:W(),height:125},base)); o.chart=chart; o.el=el; syncAdd(chart);
  const r=cM.timeScale().getVisibleLogicalRange(); if(r) try{chart.timeScale().setVisibleLogicalRange(r);}catch(e){}}
 const specs=d.out(bars.length?bars:[{t:0,o:1,h:1,l:1,c:1,v:1}],it.p); o.nspec=specs.length;
 specs.forEach((sp,j)=>{let s; const col=sp.c||colorFor(it.id%7,j);
  if(sp.t==="vol"){s=cM.addHistogramSeries({priceFormat:{type:"volume"},priceScaleId:"vol",priceLineVisible:false,lastValueVisible:false}); cM.priceScale("vol").applyOptions({scaleMargins:{top:0.82,bottom:0}});}
  else if(sp.t==="hist") s=chart.addHistogramSeries({priceLineVisible:false,lastValueVisible:false});
  else s=chart.addLineSeries({color:col,lineWidth:sp.w||1,lineStyle:sp.dots?3:0,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false,title:sp.ptitle||''});
  o.series.push(s); if(sp.lines&&d.k==="pane") sp.lines.forEach(v=>o.lines.push(s.createPriceLine({price:v,color:"#555d6e",lineWidth:1,lineStyle:2,axisLabelVisible:false})));});
 if(o.el) o.el.firstChild.textContent=d.lab(it.p);}
function destroy(id){const o=inst[id]; if(!o) return; if(o.chart){try{o.chart.remove();}catch(e){} if(o.el) o.el.remove();} else o.series.forEach(s=>{try{cM.removeSeries(s);}catch(e){}}); delete inst[id];}
function feed(it,full){const d=CAT[it.type], o=inst[it.id]; if(!d||!o||!bars.length) return; const specs=d.out(bars,it.p), n=bars.length, from=full?0:Math.max(n-2,0);
 specs.forEach((sp,j)=>{const s=o.series[j]; if(!s) return; let data;
  if(sp.t==="vol") data=bars.map(b=>({time:b.t,value:b.v,color:b.c>=b.o?"#26a69a66":"#ef535066"}));
  else if(sp.t==="hist") data=bars.map((b,i)=>sp.v[i]===null?{time:b.t}:{time:b.t,value:sp.v[i],color:sp.v[i]>=0?"#26a69a":"#ef5350"});
  else if(sp.pts) data=bars.map((b,i)=>sp.pts[i].v===null||sp.pts[i].v===undefined?{time:b.t}:{time:b.t,value:sp.pts[i].v,color:sp.pts[i].c});
  else data=bars.map((b,i)=>sp.v[i]===null||sp.v[i]===undefined||isNaN(sp.v[i])?{time:b.t}:{time:b.t,value:sp.v[i]});
  if(sp.tm) data=data.map((p,i)=>Object.assign({},p,{time:sp.tm[i]}));
  if(sp.pts&&sp.dots) data=data.map(p=>p);
  if(sp.tm||full){s.setData(data.filter(p=>p.value!==undefined));} else {data=data.slice(from); data.forEach(p=>{if(p.value!==undefined) s.update(p);});}});}
function feedAll(full){cM; const cd=bars.map(b=>({time:b.t,open:b.o,high:b.h,low:b.l,close:b.c})); if(full) candle.setData(cd); else cd.slice(-2).forEach(p=>candle.update(p)); cfg.inds.forEach(it=>feed(it,full));
 const n=bars.length; if(!n) return; const b=bars[n-1], p=bars[n-2]; const ch=p?(b.c-p.c)/p.c*100:0; const l=$("last"); if(l){l.textContent=b.c.toLocaleString("en-US",{maximumFractionDigits:b.c>=1000?1:3})+"  "+(ch>=0?"▲":"▼")+Math.abs(ch).toFixed(2)+"%"; l.style.color=ch>=0?"#26a69a":"#ef5350";}}
function resize(){const w=W(); allCharts().forEach(c=>c.applyOptions({width:w}));}
window.addEventListener("resize",resize);
// ---------- drawings (saved per coin)
function clearDraw(){lines.forEach(l=>{try{candle.removePriceLine(l);}catch(e){}}); lines=[]; draws.forEach(s=>{try{cM.removeSeries(s);}catch(e){}}); draws=[];}
function drawAll(){clearDraw(); POS.filter(p=>p.sym===cfg.coin).forEach(p=>{
 lines.push(candle.createPriceLine({price:p.entry,color:"#2962ff",lineWidth:2,lineStyle:0,axisLabelVisible:true,title:"ENTRY "+p.id}));
 lines.push(candle.createPriceLine({price:p.sl,color:"#ef5350",lineWidth:1,lineStyle:2,axisLabelVisible:true,title:"STOP"})); if(p.tp) lines.push(candle.createPriceLine({price:p.tp,color:"#26a69a",lineWidth:1,lineStyle:2,axisLabelVisible:true,title:"TARGET"}));});
 (cfg.draw[cfg.coin]||[]).forEach(d=>{ if(d.k==="h") lines.push(candle.createPriceLine({price:d.p,color:"#ffd54f",lineWidth:1,lineStyle:0,axisLabelVisible:true,title:"line"}));
  else if(d.k==="t"){const s=cM.addLineSeries({color:"#ffd54f",lineWidth:2,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false}); const a=[{time:d.t1,value:d.p1},{time:d.t2,value:d.p2}].sort((x,y)=>x.time-y.time); if(a[0].time!==a[1].time) s.setData(a); draws.push(s);}});}
let pend=null;
cM.subscribeClick(param=>{if(!mode||!param.point||!param.time) return; const price=candle.coordinateToPrice(param.point.y); if(price===null) return; const L=(cfg.draw[cfg.coin]=cfg.draw[cfg.coin]||[]);
 if(mode==="h"){L.push({k:"h",p:price}); mode=""; save(); drawAll(); tools();}
 else if(mode==="t"){ if(!pend){pend={t:param.time,p:price}; msg("Trend line: ab doosra point click karo");} else {L.push({k:"t",t1:pend.t,p1:pend.p,t2:param.time,p2:price}); pend=null; mode=""; save(); drawAll(); tools(); msg(info());} }});
// ---------- UI
function info(){return cfg.coin+"/USDT perpetual · "+cfg.tf+" · "+SRCS[srcIdx][0]+" · IST · live 3s · indicators, drawings aur coin/timeframe browser mein save rehte hain (refresh par reset nahi)";}
function buttons(){const bar=$("bar"); bar.innerHTML="";
 const mk=(t,on,fn,host)=>{const b=document.createElement("button"); b.className="b"+(on?" on":""); b.textContent=t; b.onclick=fn; (host||bar).appendChild(b); return b;};
 COINS.forEach(c=>mk(c,cfg.coin===c,()=>{cfg.coin=c; save(); buttons(); load();})); bar.insertAdjacentHTML("beforeend","<span class=sep></span>");
 TFS.forEach(t=>mk(t,cfg.tf===t,()=>{cfg.tf=t; save(); buttons(); load();})); bar.insertAdjacentHTML("beforeend","<span id=last></span>"); tools();}
function tools(){const b2=$("bar2"); b2.innerHTML="<input id=q placeholder='🔍 Indicator search: rsi, ema, bollinger, macd...' autocomplete=off> "; 
 const mk=(t,on,fn)=>{const b=document.createElement("button"); b.className="b"+(on?" on":""); b.textContent=t; b.onclick=fn; b2.appendChild(b);};
 mk("━ Horizontal line",mode==="h",()=>{mode=mode==="h"?"":"h"; pend=null; tools(); msg(mode?"Chart par jahan line chahiye wahan click karo":info());});
 mk("╱ Trend line",mode==="t",()=>{mode=mode==="t"?"":"t"; pend=null; tools(); msg(mode?"Trend line: pehla point click karo":info());});
 mk("🗑 Drawings hatao",false,()=>{cfg.draw[cfg.coin]=[]; save(); drawAll();});
 const q=$("q"); q.oninput=()=>{const v=q.value.trim().toLowerCase(), r=$("res"); const hits=Object.keys(CAT).filter(k=>!v||(k+" "+CAT[k].n).toLowerCase().includes(v)); r.innerHTML=""; hits.forEach(k=>{const d=document.createElement("div"); d.textContent=CAT[k].n+(CAT[k].k==="pane"?"  (neeche alag pane)":"  (price par)"); d.onclick=()=>{addInd(k); q.value=""; r.style.display="none";}; r.appendChild(d);}); const rc=q.getBoundingClientRect(), wc=$("wrap").getBoundingClientRect(); r.style.left=(rc.left-wc.left)+"px"; r.style.top=(rc.bottom-wc.top+2)+"px"; r.style.display=hits.length?"block":"none";};
 q.onfocus=q.oninput; q.onblur=()=>setTimeout(()=>{$("res").style.display="none";},180);}
function chips(){const c=$("chips"); c.innerHTML=""; cfg.inds.forEach((it,i)=>{const d=CAT[it.type]; if(!d) return; const e=document.createElement("span"); e.className="chip"; e.innerHTML="<span class=dot style='background:"+colorFor(it.id%7,0)+"'></span>"+d.n.split(" (")[0];
  Object.keys(d.p).forEach(k=>{const lb=document.createElement("span"); lb.style.cssText="opacity:.6;font-size:10px"; lb.textContent=k; e.appendChild(lb); const inp=document.createElement("input"); inp.type="number"; inp.step="any"; inp.value=it.p[k]; inp.title=k; inp.onchange=()=>{const v=parseFloat(inp.value); if(isNaN(v)||v<0){inp.value=it.p[k]; return;} it.p[k]=v; save(); rebuild(it);}; e.appendChild(inp);});
  const x=document.createElement("i"); x.textContent="✕"; x.title="hatao"; x.onclick=()=>{destroy(it.id); cfg.inds=cfg.inds.filter(z=>z!==it); save(); chips(); resize();}; e.appendChild(x); c.appendChild(e);});}
function addInd(type){const it={id:cfg.nid++,type:type,p:Object.assign({},CAT[type].p)}; cfg.inds.push(it); save(); build(it); feed(it,true); chips(); resize();}
function rebuild(it){destroy(it.id); build(it); feed(it,true); const o=inst[it.id]; if(o&&o.el) o.el.firstChild.textContent=CAT[it.type].lab(it.p); resize();}
async function load(){const my=++tok; msg("loading "+cfg.coin+" "+cfg.tf+" ..."); try{const b=await fetchBars(cfg.coin,cfg.tf,true); if(my!==tok) return; bars=b; Object.keys(inst).forEach(id=>destroy(+id)); cfg.inds.forEach(build); feedAll(true); drawAll(); const n=bars.length; cM.timeScale().setVisibleLogicalRange({from:Math.max(n-120,0),to:n+6}); msg(info());}
 catch(e){msg("Data nahi aa raha ("+e+"). Thodi der baad dobara try hoga.");}}
setInterval(async()=>{if(!bars.length||document.hidden) return; const my=tok; try{const r=await fetchBars(cfg.coin,cfg.tf,false); if(my!==tok) return; r.forEach(x=>{const last=bars[bars.length-1]; if(x.t===last.t) bars[bars.length-1]=x; else if(x.t>last.t) bars.push(x);}); feedAll(false);}catch(e){}},3000);
buttons(); chips(); load();
})();
</script>"""

TICKER = r"""<div style="font-family:-apple-system,Segoe UI,sans-serif;color:#e6e6e6;padding:2px"><div id="row" style="display:flex;gap:34px;flex-wrap:wrap"></div><div id="note" style="font-size:11px;opacity:.6;margin-top:2px"></div></div>
<script>
(function(){const POS=__POS__, C=["ETH","SOL"], px={}, prev={}, seen={}; let last=0;
const row=document.getElementById("row"); C.forEach(c=>{const d=document.createElement("div"); d.innerHTML="<div style='font-size:12px;opacity:.7'>"+c+" perpetual live</div><div id='p"+c+"' style='font-size:32px;font-weight:700'>\u2026</div><div id='l"+c+"' style='font-size:14px'></div>"; row.appendChild(d);});
const dec=p=>p>=1000?1:3;
function show(c,p){seen[c]=Date.now(); const e=document.getElementById("p"+c); e.textContent="$"+p.toLocaleString("en-US",{minimumFractionDigits:dec(p)>1?2:1,maximumFractionDigits:dec(p)>1?2:1}); e.style.color=prev[c]===undefined||p===prev[c]?"#e6e6e6":(p>prev[c]?"#2ecc71":"#e74c3c"); prev[c]=p;
 const o=POS.find(x=>x.sym===c); const l=document.getElementById("l"+c); if(!o){l.textContent=""; return;} const inr=(p-o.entry)*o.side*o.qty*o.fx, R=(p-o.entry)*o.side/o.risk;
 l.innerHTML="Open P/L: <b style='color:"+(inr>=0?"#2ecc71":"#e74c3c")+"'>"+(inr>=0?"+":"-")+"\u20b9"+Math.abs(inr).toFixed(0)+"</b> ("+R.toFixed(2)+"R) \u00b7 stop $"+o.sl.toLocaleString("en-US",{maximumFractionDigits:2})+" \u00b7 target $"+o.tp.toLocaleString("en-US",{maximumFractionDigits:2});}
function go(){let ws; try{ws=new WebSocket("wss://ws.okx.com:8443/ws/v5/public");}catch(e){setTimeout(go,3000);return;}
 ws.onopen=()=>ws.send(JSON.stringify({op:"subscribe",args:C.map(c=>({channel:"tickers",instId:c+"-USDT-SWAP"}))}));
 ws.onmessage=e=>{try{const m=JSON.parse(e.data); if(m.data&&m.data[0]&&m.arg){const c=m.arg.instId.split("-")[0]; if(Date.now()-last>200||true) show(c,+m.data[0].last);}}catch(x){}};
 ws.onclose=ws.onerror=()=>setTimeout(go,2500);}
go();
setInterval(()=>{C.forEach(c=>{if(Date.now()-(seen[c]||0)<8000) return; fetch("https://fapi.binance.com/fapi/v1/ticker/price?symbol="+c+"USDT").then(r=>r.json()).then(j=>show(c,+j.price)).catch(()=>{});});},3000);
document.getElementById("note").textContent="OKX live (websocket); band hone par Binance REST ~3s";})();
</script>"""


def _pos(positions):
    out = []
    for t in positions or []:
        try: out.append(dict(id=t["id"], sym=t.get("sym", "BTC"), side=int(t["side"]), entry=float(t["entry"]), sl=float(t["sl"]), tp=float(t.get("tp") or t.get("t2") or t["entry"]), qty=float(t.get("qty", 0)) * float(t.get("remaining", 1)), fx=float(t.get("fx", 88)), risk=float(t["risk"])))
        except Exception: pass
    return out


def chart_html(positions, height=430, coin=""): return CHART.replace("__LW__", LW).replace("__POS__", json.dumps(_pos(positions))).replace("__H1__", str(height)).replace("__COIN__", coin if coin in ("BTC", "ETH", "SOL") else "")
def ticker_html(positions): return TICKER.replace("__POS__", json.dumps(_pos(positions)))
