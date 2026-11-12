'use strict';
const $ = id => document.getElementById(id);
const storeKey='radar_cedears_watch_v1';
let dataset=null,view='acciones',tracked=new Set(),selected=null;
try{tracked=new Set(JSON.parse(localStorage.getItem(storeKey)||'[]'));}catch(e){}
const esc=v=>String(v==null?'—':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const usd=v=>(v==null||!Number.isFinite(Number(v)))?'—':'US$ '+Number(v).toLocaleString('es-AR',{minimumFractionDigits:2,maximumFractionDigits:3});
const fmt=v=>(v==null||!Number.isFinite(Number(v)))?'—':Number(v).toLocaleString('es-AR',{maximumFractionDigits:2});
const tone=t=>(['up','down','wait','hold','neutral'].includes(t)?t:'neutral');
const signalLabel=s=>s==='MANTENER / ESPERAR'||s==='ESPERAR'?'HOLD / ESPERAR':s==='ESPERAR MACRO'?'HOLD / ESPERAR · MACRO':s;
const badge=(s,t)=>`<span class="pill ${tone(t)}">${esc(signalLabel(s||'SIN DATOS'))}</span>`;
const barScore=(v)=>v==null?'<span class="muted">—</span>':`<span class="score ${v>=72?'good':v<35?'bad':''}">${esc(v)}</span>`;
const day=(s)=>{if(!s)return '—';try{return new Date(s+'T12:00:00').toLocaleDateString('es-AR')}catch(e){return s}};
const group=s=>{s=String(s||'');if(s.includes('COMPRA')||s.includes('VIGILAR'))return 'compra';if(s.includes('REDUCIR')||s.includes('SALIR'))return 'venta';if(s.includes('MANTENER'))return 'esperar';if(s.includes('SIN DATOS')||s.includes('SUBYACENTE')||s.includes('VIEJOS'))return 'sindatos';return 'esperar'};
function setTab(t){view=t;document.querySelectorAll('.tab').forEach(x=>{x.classList.toggle('active',x.dataset.tab===t);x.setAttribute('aria-current',x.dataset.tab===t?'page':'false')});[['acciones','pageAcciones'],['sectores','pageSectores'],['cartera','pageCartera'],['metodo','pageMetodo']].forEach(([k,id])=>$(id).classList.toggle('hidden',k!==t));if(t==='cartera')renderTracked();}
function baseline(){return {meta:{source:'Catálogo local · pendiente de ejecución inicial',universe_size:0,mapped_us:0,download_coverage:0},macro:{state:'NO VERIFICADO'},assets:[],sectors:[]}}
function renderHeader(){const m=dataset.meta||{};const a=dataset.assets||[];const generated=m.generated_at_ar?new Date(m.generated_at_ar):null;const age=generated?(Date.now()-generated.getTime())/(3600000):9999;const coverage=Number(m.download_coverage||0);
 const fresh=generated&&age<=36&&age>=-1;const banner=$('criticalBanner');
 if(!generated){banner.className='critical bad';banner.textContent='Sin actualización real todavía. Ejecutá la acción de GitHub «Actualizar radar CEDEARs» para cargar precios USD y señales. Hasta entonces NO hay recomendaciones.'}
 else if(!fresh){banner.className='critical bad';banner.textContent='ATENCIÓN: última actualización de hace '+Math.max(0,Math.round(age))+' horas. Revisá GitHub Actions; no operes basándote en señales desactualizadas.'}
 else{banner.className='critical ok';banner.textContent='Indicadores sobre cierres diarios de EE.UU. en dólares. Señales informativas: no son órdenes ni reemplazan validación de BYMA y fundamentales.'}
 $('macroValue').textContent=dataset.macro?.state||'—';$('macroValue').style.color=dataset.macro?.state==='FAVORABLE'?'#5ee1c2':dataset.macro?.state==='DEFENSIVO'?'#f27b80':'#f6c16b';
 $('macroSub').textContent='SPY / QQQ / VIX · '+(dataset.macro?.vix!=null?'VIX '+fmt(dataset.macro.vix):'sin corte verificado');
 $('buyCount').textContent=a.filter(x=>group(x.signal)==='compra').length;$('assetCount').textContent=m.universe_size||a.length;
 $('mappedCount').textContent=(m.mapped_us||0)+' con subyacente USA candidato';$('coverageCount').textContent=generated?fmt(coverage)+'%':'Sin datos';
 $('heroLast').textContent=generated?'Último procesamiento: '+new Date(m.generated_at_ar).toLocaleString('es-AR',{dateStyle:'short',timeStyle:'short'}):'Pendiente de primer corte';
 $('footerSource').textContent=(m.source||'Sin fuente')+' · '+(m.generated_at_ar?'corte '+new Date(m.generated_at_ar).toLocaleString('es-AR'):'sin datos');
 $('liveIndicator').innerHTML=generated&&fresh?'<i style="background:#2bd5bc"></i>Última ejecución registrada':'<i></i>Datos pendientes';
 $('trackedCount').textContent=tracked.size;
}
function fillFilters(){const ss=[...new Set((dataset.assets||[]).map(x=>x.sector).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'es'));
 $('sectorFilter').innerHTML='<option value="">Todos los sectores</option>'+ss.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('');}
function renderAssets(){const q=$('searchInput').value.toLowerCase().trim(),sector=$('sectorFilter').value,sig=$('signalFilter').value,sort=$('sortFilter').value;
 let arr=(dataset.assets||[]).filter(x=>(!q||(x.ticker||'').toLowerCase().includes(q)||(x.usa||'').toLowerCase().includes(q)||(x.sector||'').toLowerCase().includes(q))&&(!sector||x.sector===sector)&&(!sig||group(x.signal)===sig));
 const importance=x=>({compra:0,esperar:1,venta:2,sindatos:3}[group(x.signal)]??5);
 arr.sort((a,b)=>sort==='ticker'?a.ticker.localeCompare(b.ticker):sort==='worst'?(a.data?.score??200)-(b.data?.score??200):sort==='signal'?importance(a)-importance(b)||(b.data?.score??-1)-(a.data?.score??-1):(b.data?.score??-1)-(a.data?.score??-1));
 $('rowCount').textContent=arr.length+' / '+(dataset.assets||[]).length+' instrumentos';
 const visible=arr.slice(0,400);
 $('assetRows').innerHTML=visible.length?visible.map(x=>`<tr tabindex="0" data-ticker="${esc(x.ticker)}"><td>${esc(x.ticker)}<span class="ticker-sub">USA: ${esc(x.usa||'NO APLICA')} · ${esc(x.sector)}</span></td><td>${usd(x.data?.price)}</td><td>${fmt(x.data?.rsi14d)}</td><td>${x.data?.macd_hist_d==null?'—':fmt(x.data?.macd_hist_d)}</td><td>${barScore(x.data?.score)}</td><td>${esc(x.data?.trend||'NO VERIFICADO')}</td><td>${badge(x.signal,x.tone)}</td></tr>`).join(''):'<tr><td colspan="7" style="padding:30px">No hay resultados para estos filtros.</td></tr>';
 $('assetRows').querySelectorAll('tr[data-ticker]').forEach(el=>{const act=()=>openDetails('asset',el.dataset.ticker);el.onclick=act;el.onkeydown=(e)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();act()}}});}
function renderSectors(){const arr=[...(dataset.sectors||[])].sort((a,b)=>(b.data?.score??-1)-(a.data?.score??-1));$('sectorCards').innerHTML=arr.length?arr.map(x=>`<article class="sector-card" data-sector="${esc(x.sector)}" tabindex="0"><div class="sector-heading"><div><h3>${esc(x.sector)}</h3><small>ETF proxy: ${esc(x.proxy)} · USD</small></div><div class="sector-score">${x.data?.score??'—'}<span>/100</span></div></div><div class="meter"><span style="width:${Math.min(100,Math.max(0,x.data?.score??0))}%"></span></div><p class="sector-info">${esc(x.data?.trend||'Sin lectura')} · RSI14 ${fmt(x.data?.rsi14d)} · ROC20 ${fmt(x.data?.roc20)}%</p><div class="sector-action">${badge(x.signal,x.tone)}<span class="muted">Detalle ›</span></div></article>`).join(''):'<p class="muted">Pendiente del primer corte automático.</p>';
 $('sectorCards').querySelectorAll('[data-sector]').forEach(el=>{const act=()=>openDetails('sector',el.dataset.sector);el.onclick=act;el.onkeydown=(e)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();act()}}});}
function renderTracked(){const arr=(dataset.assets||[]).filter(x=>tracked.has(x.ticker));$('trackedCount').textContent=tracked.size;$('watchRows').innerHTML=arr.length?arr.map(x=>`<div class="watch-card" data-watch="${esc(x.ticker)}" tabindex="0"><div><h3>${esc(x.ticker)} · ${esc(x.usa||'sin USD')}</h3><small>${esc(x.sector)}</small></div><div>${badge(x.signal,x.tone)}</div><div class="muted">Score ${x.data?.score??'—'}/100 · cierre ${day(x.data?.date)}</div></div>`).join(''):'<p class="muted">Todavía no marcaste instrumentos. Elegí un ticker en «Acciones y ETFs» y tocá «Seguir».</p>';$('watchRows').querySelectorAll('[data-watch]').forEach(el=>{el.onclick=()=>openDetails('asset',el.dataset.watch);el.onkeydown=e=>{if(e.key==='Enter'){openDetails('asset',el.dataset.watch)}}})}
function detailContent(x,type){const d=x.data||{},ticker=type==='sector'?x.proxy:x.ticker,name=type==='sector'?x.sector:x.ticker;
 const isAsset=type==='asset';const title=isAsset?`${esc(name)} <span style="color:#7fc0c0;font-size:15px">/ ${esc(x.usa||'sin subyacente')}</span>`:esc(name);
 const what=x.reasons&&x.reasons.length?x.reasons:['Sin histórico suficiente para interpretar el activo'];
 let plan='No hay gatillo automático confirmado. Esperar confluencia diaria/4H y validación del mercado.';
 if(group(x.signal)==='compra')plan='Entrada eventual en 3 tramos 40% / 35% / 25%, sólo tras confirmar reacción, volumen, filtro macro y concentración de cartera.';
 const objective=d.target_2r!=null?`${usd(d.target_2r)} (2R) · ${usd(d.target_3r)} (3R)`:'No definido: la relación riesgo/beneficio aún no es adecuada.';
 const riskNote=isAsset?`<div class="detail-note"><strong>Operabilidad BYMA pendiente:</strong> este motor NO certifica ratio, listado vigente, liquidez, spread ni disponible en Bull/IOL. Confirmá <a class="mini-link" target="_blank" rel="noopener noreferrer" href="https://www.byma.com.ar/productos/productos-financieros/cedears">el PDF oficial de BYMA</a> antes de cualquier orden. Los indicadores son del subyacente USA en USD.</div>`:'<div class="detail-note">El ETF es proxy de fortaleza sectorial. La señal sectorial no convierte automáticamente cada CEDEAR del grupo en compra.</div>';
 return `<div class="detail-top"><span class="eyebrow">${isAsset?'CEDEAR · SUBYACENTE EN USD':'ROTACIÓN Y LIDERAZGO SECTORIAL'}</span><h2>${title}</h2><p>${esc(isAsset?x.sector:'ETF proxy de EE.UU.: '+x.proxy)} · Último cierre confirmado ${day(d.date)}</p><div class="detail-badges">${badge(x.signal,x.tone)} ${badge(d.trend||'SIN TENDENCIA','neutral')} ${badge('SCORE '+(d.score??'—')+'/100','hold')}</div><div class="detail-price">${usd(d.price)}<small>del activo en EE.UU., no del CEDEAR en ARS</small></div></div>
 <div class="detail-metrics"><div class="detail-metric"><label>SMA20 · USD</label><strong>${usd(d.ma20)}</strong></div><div class="detail-metric"><label>SMA50 · USD</label><strong>${usd(d.ma50)}</strong></div><div class="detail-metric"><label>SMA200 · USD</label><strong>${usd(d.ma200)}</strong></div><div class="detail-metric"><label>RSI14 diario</label><strong>${fmt(d.rsi14d)}</strong></div><div class="detail-metric"><label>MACD hist. D</label><strong>${fmt(d.macd_hist_d)}</strong></div><div class="detail-metric"><label>RSI21 semanal</label><strong>${fmt(d.rsi21w)}</strong></div><div class="detail-metric"><label>RSI21 mensual</label><strong>${fmt(d.rsi21m)}</strong></div><div class="detail-metric"><label>ADX14 diario</label><strong>${fmt(d.adx14)}</strong></div></div>
 <div class="detail-section"><h3>Por qué aparece esta señal</h3><ul>${what.map(t=>`<li>${esc(t)}</li>`).join('')}</ul></div>
 <div class="detail-section"><h3>Plan informativo / control de riesgo</h3><p>${esc(plan)}</p><div class="detail-metrics"><div class="detail-metric"><label>Nivel de referencia / soporte</label><strong>${usd(d.ma20)}</strong></div><div class="detail-metric"><label>Invalidación de referencia</label><strong>${usd(d.invalid_usd)}</strong></div><div class="detail-metric" style="grid-column:span 2"><label>Objetivos hipotéticos desde cierre USD</label><strong>${esc(objective)}</strong></div></div><p class="muted">La invalidación es aproximada: revisar estructura 4H/diaria y catalizadores. Los objetivos R son escenarios, no pronósticos.</p></div>
 ${riskNote}<p class="muted" style="font-size:11px">Calidad: último cierre USD ${day(d.date)} · Macroeconomía: ${esc(dataset.macro?.state||'NO VERIFICADO')} · fuente: Yahoo/yfinance.</p>
 ${isAsset?`<div class="detail-buttons"><button id="trackingButton" class="btn">${tracked.has(x.ticker)?'✓ Dejar de seguir':'＋ Seguir / mi lista'}</button><button id="goSheet" class="btn btn-outline">Ver reglas</button></div>`:''}`;
}
function openDetails(type,key){const x=type==='asset'?(dataset.assets||[]).find(v=>v.ticker===key):(dataset.sectors||[]).find(v=>v.sector===key);if(!x)return;selected={type,key};$('detailBody').innerHTML=detailContent(x,type);$('detailModal').showModal();const b=$('trackingButton');if(b)b.onclick=()=>{if(tracked.has(x.ticker))tracked.delete(x.ticker);else tracked.add(x.ticker);try{localStorage.setItem(storeKey,JSON.stringify([...tracked]))}catch(e){}renderHeader();renderTracked();b.textContent=tracked.has(x.ticker)?'✓ Dejar de seguir':'＋ Seguir / mi lista';};if($('goSheet'))$('goSheet').onclick=()=>{ $('detailModal').close();setTab('metodo')};}
// Humor editorial visible; no depende del motor, precios ni datos privados.
const martinQuotes=[
  'Martín compró ASTS para ir a la Luna. El -40% lo dejó en el subsuelo.',
  'Martín no promedia a la baja: está haciendo turismo por todos los pisos.',
  'Cuando Martín dice «es una corrección sana», el broker pide certificado médico.',
  'ASTS prometía conexión satelital. Martín terminó buscando señal en el sótano.',
  'Su stop loss no saltó. Aparentemente pidió vacaciones sin avisar.',
  'Martín no busca el piso: está financiando una excavación arqueológica.',
  'El RSI de ASTS estaba sobrevendido. El optimismo de Martín, sobrecomprado.',
  'Martín compró la ruptura. La que se rompió fue la calculadora del rendimiento.',
  'En su diccionario HODL significa «Hoy Otra Derrota Latente».',
  'Martín miró el MACD; el MACD vio el -40% y bajó la vista.',
  'La tesis era espacial. El gráfico eligió minería subterránea.',
  'Cuando Martín dijo «voy largo», nadie sabía que hablaba del tiempo de recuperación.'
];
let martinIndex=0;
function showMartinQuote(index){
  const label=$('martinQuote'),counter=$('martinCount');
  if(!label||!counter)return;
  martinIndex=((index%martinQuotes.length)+martinQuotes.length)%martinQuotes.length;
  label.textContent='«'+martinQuotes[martinIndex]+'»';
  counter.textContent=String(martinIndex+1).padStart(2,'0')+' / '+String(martinQuotes.length).padStart(2,'0');
  counter.setAttribute('aria-label','Frase '+(martinIndex+1)+' de '+martinQuotes.length);
}
if($('martinNext')){
  $('martinNext').addEventListener('click',()=>showMartinQuote(martinIndex+1));
  showMartinQuote(0);
  const reduceMotion=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(!reduceMotion)window.setInterval(()=>{
    if(!document.hidden)showMartinQuote(martinIndex+1);
  },12000);
}

async function load(){dataset=baseline();try{const r=await fetch('./data.json?refresh='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const j=await r.json();if(!Array.isArray(j.assets)||!Array.isArray(j.sectors))throw new Error('Formato inválido');
 // Si falla GitHub Actions y el sitio quedó con datos de una ejecución vieja,
 // se BLOQUEAN las señales de compra/venta, no alcanza sólo con un aviso arriba.
 const stamp=Date.parse(j.meta?.generated_at_utc||'');
 const batchStale=!Number.isFinite(stamp)||(Date.now()-stamp)/3600000>36;
 const staleDate=d=>!d||!Number.isFinite(Date.parse(d+'T23:59:59Z'))||(Date.now()-Date.parse(d+'T23:59:59Z'))/86400000>5;
 for(const x of [...j.assets,...j.sectors]){
   if(batchStale||(x.data&&staleDate(x.data.date))){
     x.signal='DATOS VIEJOS';x.tone='neutral';
     x.reasons=['Señal suspendida: falta una actualización reciente del mercado estadounidense. Revisar GitHub Actions y fecha de cierre USA.'];
   }
 }
 dataset=j;}catch(e){$('criticalBanner').textContent='Sin datos. Si abriste el archivo local, publicalo en GitHub Pages. Error de lectura: '+e.message;}fillFilters();renderHeader();renderAssets();renderSectors();renderTracked();}
for(const el of document.querySelectorAll('.tab'))el.onclick=()=>setTab(el.dataset.tab);
for(const id of ['searchInput','sectorFilter','signalFilter','sortFilter'])$(id).addEventListener(id==='searchInput'?'input':'change',renderAssets);
$('modalClose').onclick=()=>$('detailModal').close();$('detailModal').addEventListener('click',e=>{if(e.target===$('detailModal'))$('detailModal').close()});
load();
