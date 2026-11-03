"""Browser-side live widgets (no server load, no API key):
  chart_html(positions)  : TradingView-style chart (open-source 'lightweight-charts' by TradingView) for BTC / ETH / SOL with indicators you can switch on/off
                           (EMA20/50/200, Bollinger, VWAP, Volume, RSI, MACD). Your choices (coin, timeframe, indicators) are saved in the browser (localStorage),
                           so a page refresh does NOT reset them. Candles come straight from OKX (fallback Binance, Bybit) and update every 3 seconds. Open paper trades are drawn as lines.
  ticker_html(positions) : live price strip for ETH and SOL (websocket, REST fallback) with the open paper P/L of each coin.
Times are shown in IST. The BTC live-price widget in app.py is separate and untouched."""
import json

LW = "https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"

CHART = r"""<div id="wrap" style="font-family:-apple-system,Segoe UI,sans-serif;color:#d1d4dc;background:#131722;border-radius:8px;padding:6px">
<style>
.b{background:#1e222d;color:#d1d4dc;border:1px solid #2a2e39;border-radius:5px;padding:4px 9px;margin:2px;cursor:pointer;font-size:13px}
.b.on{background:#2962ff;border-color:#2962ff;color:#fff}.sep{display:inline-block;width:10px}
#last{font-size:20px;font-weight:700;margin-left:10px}
</style>
<div id="bar"></div>
<div id="main" style="height:__H1__px;width:100%"></div><div id="rsiw" style="height:110px;width:100%"></div><div id="macdw" style="height:130px;width:100%"></div>
<div id="msg" style="font-size:12px;opacity:.7;padding:3px"></div></div>
<script src="__LW__"></script>
<script>
(function(){
const POS=__POS__, COINS=["BTC","ETH","SOL"], TFS=["5m","15m","1H","4H","1D"], IND=[["ema20","EMA 20"],["ema50","EMA 50"],["ema200","EMA 200"],["bb","Bollinger"],["vwap","VWAP"],["vol","Volume"],["rsi","RSI"],["macd","MACD"]];
const KEY="btcTool.chart.v1", OFF=19800; let cfg={coin:"BTC",tf:"1H",ind:{ema20:1,ema50:1,vol:1,rsi:1}};
try{const s=JSON.parse(localStorage.getItem(KEY)||"{}"); if(s.coin) cfg.coin=s.coin; if(s.tf) cfg.tf=s.tf; if(s.ind) cfg.ind=s.ind;}catch(e){}
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
// ---------- indicators
function ema(a,n){const k=2/(n+1); const o=[]; let p=null; for(let i=0;i<a.length;i++){p=p===null?a[i]:a[i]*k+p*(1-k); o.push(i>=n-1?p:null);} return o;}
function emaRaw(a,n){const k=2/(n+1); let p=null; return a.map(v=>p=(p===null?v:v*k+p*(1-k)));}
function sma(a,n){const o=[]; let s=0; for(let i=0;i<a.length;i++){s+=a[i]; if(i>=n) s-=a[i-n]; o.push(i>=n-1?s/n:null);} return o;}
function bb(a,n,m){const mid=sma(a,n), up=[], lo=[]; for(let i=0;i<a.length;i++){if(mid[i]===null){up.push(null);lo.push(null);continue;} let s=0; for(let j=i-n+1;j<=i;j++) s+=(a[j]-mid[i])**2; const sd=Math.sqrt(s/n); up.push(mid[i]+m*sd); lo.push(mid[i]-m*sd);} return [up,mid,lo];}
function vwap(B){let day=-1,pv=0,vv=0; return B.map(b=>{const d=Math.floor(b.t/86400); if(d!==day){day=d;pv=0;vv=0;} const tp=(b.h+b.l+b.c)/3; pv+=tp*b.v; vv+=b.v; return vv>0?pv/vv:null;});}
function rsi(a,n){const o=[null]; let g=0,l=0; for(let i=1;i<a.length;i++){const d=a[i]-a[i-1], u=Math.max(d,0), w=Math.max(-d,0); if(i<=n){g+=u;l+=w; if(i<n){o.push(null);continue;} g/=n;l/=n;} else {g=(g*(n-1)+u)/n; l=(l*(n-1)+w)/n;} o.push(l===0?100:100-100/(1+g/l));} return o;}
function macd(a){const e12=emaRaw(a,12), e26=emaRaw(a,26), m=e12.map((v,i)=>v-e26[i]), s=emaRaw(m,9); return [m,s,m.map((v,i)=>v-s[i])];}
// ---------- charts
const base={layout:{background:{color:"#131722"},textColor:"#d1d4dc"},grid:{vertLines:{color:"#1e222d"},horzLines:{color:"#1e222d"}},rightPriceScale:{borderColor:"#2a2e39"},timeScale:{borderColor:"#2a2e39",timeVisible:true,secondsVisible:false},crosshair:{mode:0}};
const W=()=>$("wrap").clientWidth-12;
const cM=LightweightCharts.createChart($("main"),Object.assign({width:W(),height:__H1__},base)), cR=LightweightCharts.createChart($("rsiw"),Object.assign({width:W(),height:110},base)), cD=LightweightCharts.createChart($("macdw"),Object.assign({width:W(),height:130},base));
const candle=cM.addCandlestickSeries({upColor:"#26a69a",downColor:"#ef5350",borderVisible:false,wickUpColor:"#26a69a",wickDownColor:"#ef5350"});
const L=(c,col,w,ps)=>c.addLineSeries({color:col,lineWidth:w||1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
const S={ema20:L(cM,"#f5a623",1),ema50:L(cM,"#2962ff",1),ema200:L(cM,"#e040fb",2),bbU:L(cM,"#78909c",1),bbM:L(cM,"#546e7a",1),bbL:L(cM,"#78909c",1),vwap:L(cM,"#00bcd4",1)};
const vol=cM.addHistogramSeries({priceFormat:{type:"volume"},priceScaleId:"vol",priceLineVisible:false,lastValueVisible:false}); cM.priceScale("vol").applyOptions({scaleMargins:{top:0.82,bottom:0}});
const rsiS=L(cR,"#b39ddb",1.5); rsiS.createPriceLine({price:70,color:"#ef5350",lineWidth:1,lineStyle:2,axisLabelVisible:false}); rsiS.createPriceLine({price:30,color:"#26a69a",lineWidth:1,lineStyle:2,axisLabelVisible:false});
const mH=cD.addHistogramSeries({priceLineVisible:false,lastValueVisible:false}), mL=L(cD,"#2962ff",1), mS=L(cD,"#ff9800",1);
let syncing=false; function link(a,bs){a.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(syncing||!r) return; syncing=true; bs.forEach(b=>{try{b.timeScale().setVisibleLogicalRange(r);}catch(e){}}); syncing=false;});}
link(cM,[cR,cD]); link(cR,[cM,cD]); link(cD,[cM,cR]);
let bars=[], lines=[];
const pt=(B,arr)=>B.map((b,i)=>arr[i]===null||arr[i]===undefined||isNaN(arr[i])?{time:b.t}:{time:b.t,value:arr[i]});
function compute(){const c=bars.map(b=>b.c); const R={}; R.ema20=ema(c,20); R.ema50=ema(c,50); R.ema200=ema(c,200); const x=bb(c,20,2); R.bbU=x[0]; R.bbM=x[1]; R.bbL=x[2]; R.vwap=vwap(bars); R.rsi=rsi(c,14); const m=macd(c); R.mL=m[0]; R.mS=m[1]; R.mH=m[2]; return R;}
function apply(full){ if(!bars.length) return; const R=compute(), n=bars.length, from=full?0:Math.max(n-2,0), B=bars.slice(from);
 const put=(s,a)=>{const d=pt(B,a.slice(from)); full?s.setData(d.filter(p=>p.value!==undefined)):d.forEach(p=>{if(p.value!==undefined) s.update(p);});};
 const cd=B.map(b=>({time:b.t,open:b.o,high:b.h,low:b.l,close:b.c})); full?candle.setData(cd):cd.forEach(p=>candle.update(p));
 put(S.ema20,R.ema20); put(S.ema50,R.ema50); put(S.ema200,R.ema200); put(S.bbU,R.bbU); put(S.bbM,R.bbM); put(S.bbL,R.bbL); put(S.vwap,R.vwap); put(rsiS,R.rsi); put(mL,R.mL); put(mS,R.mS);
 const vd=B.map(b=>({time:b.t,value:b.v,color:b.c>=b.o?"#26a69a66":"#ef535066"})); full?vol.setData(vd):vd.forEach(p=>vol.update(p));
 const hd=B.map((b,i)=>({time:b.t,value:R.mH[from+i],color:R.mH[from+i]>=0?"#26a69a":"#ef5350"})); full?mH.setData(hd):hd.forEach(p=>mH.update(p));
 const b=bars[n-1], p=bars[n-2]; const ch=p?(b.c-p.c)/p.c*100:0; $("last").textContent=b.c.toLocaleString("en-US",{maximumFractionDigits:b.c>=1000?1:3})+"  "+(ch>=0?"\u25B2":"\u25BC")+Math.abs(ch).toFixed(2)+"%"; $("last").style.color=ch>=0?"#26a69a":"#ef5350";}
function vis(){const I=cfg.ind; S.ema20.applyOptions({visible:!!I.ema20}); S.ema50.applyOptions({visible:!!I.ema50}); S.ema200.applyOptions({visible:!!I.ema200}); ["bbU","bbM","bbL"].forEach(k=>S[k].applyOptions({visible:!!I.bb})); S.vwap.applyOptions({visible:!!I.vwap}); vol.applyOptions({visible:!!I.vol});
 $("rsiw").style.display=I.rsi?"block":"none"; $("macdw").style.display=I.macd?"block":"none"; resize();}
function resize(){const w=W(); cM.applyOptions({width:w}); cR.applyOptions({width:w}); cD.applyOptions({width:w});}
window.addEventListener("resize",resize);
function levels(){lines.forEach(l=>{try{candle.removePriceLine(l);}catch(e){}}); lines=[]; POS.filter(p=>p.sym===cfg.coin).forEach(p=>{
 lines.push(candle.createPriceLine({price:p.entry,color:"#2962ff",lineWidth:2,lineStyle:0,axisLabelVisible:true,title:"ENTRY "+p.id}));
 lines.push(candle.createPriceLine({price:p.sl,color:"#ef5350",lineWidth:1,lineStyle:2,axisLabelVisible:true,title:"STOP"})); if(p.tp) lines.push(candle.createPriceLine({price:p.tp,color:"#26a69a",lineWidth:1,lineStyle:2,axisLabelVisible:true,title:"TARGET"}));});}
function buttons(){const bar=$("bar"); bar.innerHTML="";
 const mk=(t,on,fn)=>{const b=document.createElement("button"); b.className="b"+(on?" on":""); b.textContent=t; b.onclick=fn; bar.appendChild(b);};
 COINS.forEach(c=>mk(c,cfg.coin===c,()=>{cfg.coin=c; save(); buttons(); load();})); bar.insertAdjacentHTML("beforeend","<span class=sep></span>");
 TFS.forEach(t=>mk(t,cfg.tf===t,()=>{cfg.tf=t; save(); buttons(); load();})); bar.insertAdjacentHTML("beforeend","<span class=sep></span>");
 IND.forEach(([k,l])=>mk(l,!!cfg.ind[k],()=>{cfg.ind[k]=cfg.ind[k]?0:1; save(); buttons(); vis();})); bar.insertAdjacentHTML("beforeend","<span id=last></span>");}
let tok=0;
async function load(){const my=++tok; msg("loading "+cfg.coin+" "+cfg.tf+" ..."); try{const b=await fetchBars(cfg.coin,cfg.tf,true); if(my!==tok) return; bars=b; apply(true); levels(); cM.timeScale().fitContent(); const n=bars.length; cM.timeScale().setVisibleLogicalRange({from:Math.max(n-120,0),to:n+6}); msg(cfg.coin+"/USDT perpetual \u00b7 "+cfg.tf+" \u00b7 "+SRCS[srcIdx][0]+" \u00b7 IST \u00b7 live update every 3s \u00b7 tumhare chune hue indicators browser mein save rehte hain (refresh par reset nahi hote)");}
 catch(e){msg("Data nahi aa raha ("+e+"). Thodi der baad dobara try hoga.");}}
setInterval(async()=>{if(!bars.length||document.hidden) return; const my=tok; try{const r=await fetchBars(cfg.coin,cfg.tf,false); if(my!==tok) return; r.forEach(x=>{const last=bars[bars.length-1]; if(x.t===last.t) bars[bars.length-1]=x; else if(x.t>last.t) bars.push(x);}); apply(false);}catch(e){}},3000);
buttons(); vis(); load();
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


def chart_html(positions, height=430): return CHART.replace("__LW__", LW).replace("__POS__", json.dumps(_pos(positions))).replace("__H1__", str(height))
def ticker_html(positions): return TICKER.replace("__POS__", json.dumps(_pos(positions)))
