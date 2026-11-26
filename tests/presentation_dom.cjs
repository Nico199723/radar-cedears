'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const {JSDOM,VirtualConsole}=require('jsdom');
const html=fs.readFileSync('docs/index.html','utf8'),source=fs.readFileSync('docs/app.js','utf8');
const now=new Date().toISOString(),today=now.slice(0,10);
const nvda={ticker:'NVDA',usa:'NVDA',sector:'Semiconductores',signal:'HOLD / ESPERAR',tone:'hold',score_decision:0,
 data:{score:4,rank_score:90,rank_score_signal:88,price:125.5,date:today,ma21:124,rsi14d:45,macd_hist_d:-.1,rank_penalty:5,rank_penalty_reasons:['Prueba'],invalid_usd:120,target_2r:129,target_3r:999},reasons:['Prueba']};
const other={...nvda,ticker:'AMD',usa:'AMD',score_decision:10,data:{...nvda.data,score:99,rank_score:1}};
const fixture={meta:{generated_at_utc:now,generated_at_ar:now,universe_size:2,mapped_us:2,download_coverage:100,
 rules:{thresholds:{watch:61,buy:71,priority:76},policy_prudent:{max_position_usd:123,reserve_pct:69,stop_pct:5,max_positions:3}}},
 assets:[nvda,other],sectors:[{...nvda,sector:'Semiconductores',proxy:'SMH'}],top5:[{...nvda.data,ticker:'NVDA',usa:'NVDA',signal:nvda.signal}],rebounds:[],macro:{state:'FAVORABLE'}};
const chart={d:['2026-11-18','2026-11-19','2026-11-20'],c:[125,126,130],m21:[124,125,126],m50:[122,123,124],m200:[null,121,122]};
const response=x=>({ok:true,json:async()=>structuredClone(x)});
const tick=()=>new Promise(r=>setTimeout(r,0));
function boot({fail=false}={}){
 const errors=[],requests=[];let resolveData;
 const dataGate=new Promise(r=>resolveData=r);
 const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e));vc.on('error',e=>errors.push(e));
 const dom=new JSDOM(html,{url:'https://radar.test/',runScripts:'outside-only',virtualConsole:vc});
 const w=dom.window;w.matchMedia=()=>({matches:true});
 w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
 w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');this.dispatchEvent(new w.Event('close'));};
 w.localStorage.setItem('radar_cedears_watch_v1','["NVDA"]');
 w.fetch=async url=>{if(url.startsWith('./data.json')){await dataGate;if(fail)throw new Error('red caída');return response(fixture);}
  if(url.startsWith('./paper.json'))return {ok:false,status:404};
  return new Promise(resolve=>requests.push({url,resolve}));};
 w.addEventListener('error',e=>errors.push(e.error));w.eval(source+"\nwindow.radarTest={openDetails,visibleScore,badge};");
 return {dom,w,errors,requests,resolveData};
}
(async()=>{
 const {dom,w,errors,requests,resolveData}=boot();const d=w.document;
 assert(d.body.classList.contains('is-loading'));assert(d.getElementById('assetRows').textContent.includes('Cargando señales'));
 resolveData();await tick();await tick();
 assert(!d.body.classList.contains('is-loading'));assert.equal(d.querySelector('main').getAttribute('aria-busy'),'false');
 assert.equal(d.querySelectorAll('.signals-table thead th').length,9);
 assert.equal(d.querySelector('#assetRows tr').dataset.ticker,'AMD');
 assert.equal(d.querySelector('#assetRows tr[data-ticker="NVDA"] .score').textContent,'0');
 assert(d.getElementById('watchRows').textContent.includes('Score 0/100'));
 assert.equal(d.querySelector('.top5-score').textContent,'0/100');
 assert.equal(d.querySelector('.sector-score').textContent,'0/100');
 assert(d.querySelector('.meter span').getAttribute('style').includes('width:0%'));
 assert.equal(d.querySelector('[data-rule="thresholds.buy"]').textContent,'71');
 assert.equal(d.querySelector('[data-rule="policy_prudent.reserve_pct"]').textContent,'69');
 assert.equal(d.getElementById('martinTitle').closest('details').open,false);
 assert(d.getElementById('martinTitle').compareDocumentPosition(d.getElementById('assetRows')) & w.Node.DOCUMENT_POSITION_PRECEDING);
 w.radarTest.openDetails('asset','NVDA');
 assert.equal(d.querySelector('.score-label').textContent,'Score 0/100');
 assert.equal(d.querySelector('.score-diagnostic').open,false);
 assert(d.querySelector('.score-diagnostic').textContent.includes('anterior: 4'));
 assert(d.getElementById('priceChart').textContent.includes('Cargando gráfico'));
 assert(requests[0].url.startsWith('./charts/NVDA.json?v='));
 w.radarTest.openDetails('sector','Semiconductores');
 assert(requests[1].url.startsWith('./charts/SMH.json?v='));
 requests[0].resolve(response(chart));await tick();
 assert(!d.querySelector('#priceChart svg'),'old response must not overwrite the new card');
 requests[1].resolve(response(chart));await tick();
 assert(d.querySelector('#priceChart svg'));
 assert(d.getElementById('priceChart').textContent.includes('US$ '));
 assert(d.querySelector('[data-level="target_2r"]'));
 assert(!d.querySelector('[data-level="target_3r"]'));
 const target=d.querySelector('[data-chart-tip]');target.dispatchEvent(new w.Event('mouseenter'));
 assert(d.querySelector('.chart-tooltip').textContent.includes('SMA200'));
 assert(!/NaN|Infinity|undefined/.test(d.getElementById('priceChart').innerHTML));
 w.radarTest.openDetails('asset','NVDA');requests[2].resolve({ok:false,status:404});await tick();
 assert.equal(d.getElementById('priceChart').textContent,'Gráfico no disponible en este corte');
 for(const [signal,prefix] of [['COMPRA CONDICIONAL','▲'],['COMPRA CON PRECAUCIÓN','△'],['VIGILAR COMPRA · SCORE','◆'],['SALIR / EVITAR','▼'],['HOLD / ESPERAR','●']]){
  const pill=w.radarTest.badge(signal);assert(pill.includes(prefix));assert(pill.includes('aria-label='));
 }
 const trackedCode=source.slice(source.indexOf('function renderTracked'),source.indexOf('function detailContent'));
 assert(!/data\??\.score\b/.test(trackedCode));
 assert.equal(w.radarTest.visibleScore({score_decision:0,data:{rank_score:99}}),0);
 assert.equal(w.radarTest.visibleScore({data:{rank_score:12,score:4}}),12);
 assert.deepEqual(errors,[]);dom.window.close();
 const failed=boot({fail:true});failed.resolveData();await tick();await tick();
 assert(!failed.w.document.body.classList.contains('is-loading'));
 assert(failed.w.document.getElementById('criticalBanner').textContent.includes('red caída'));
 assert.deepEqual(failed.errors,[]);failed.dom.window.close();
 console.log('Presentation DOM: zero score across views, ordering, rules, chart races/failure, loading, symbols and accessibility OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
