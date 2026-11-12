'use strict';
const $ = id => document.getElementById(id);
const storeKey='radar_cedears_watch_v1';
let dataset=null,view='acciones',tracked=new Set(),selected=null,paper=null;
try{tracked=new Set(JSON.parse(localStorage.getItem(storeKey)||'[]'));}catch(e){}
const esc=v=>String(v==null?'—':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const usd=v=>(v==null||!Number.isFinite(Number(v)))?'—':'US$ '+Number(v).toLocaleString('es-AR',{minimumFractionDigits:2,maximumFractionDigits:3});
const fmt=v=>(v==null||!Number.isFinite(Number(v)))?'—':Number(v).toLocaleString('es-AR',{maximumFractionDigits:2});
const tone=t=>(['up','down','wait','hold','neutral'].includes(t)?t:'neutral');
const signalLabel=s=>s==='MANTENER / ESPERAR'||s==='ESPERAR'?'HOLD / ESPERAR':s==='ESPERAR MACRO'?'HOLD / ESPERAR · MACRO':s;
const badge=(s,t)=>`<span class="pill ${tone(t)}">${esc(signalLabel(s||'SIN DATOS'))}</span>`;
const eventHtml=x=>{
 const e=x?.earnings, n=e?.days_until;
 if(typeof n==='number'&&n>=0&&n<=14){
   const urgent=n<=7;
   return `<span class="balance-alert ${urgent?'urgent':'soon'}" title="Fecha indicativa Yahoo, verificar en IR">⚠ Balance ${n===0?'HOY':'en '+n+'d'}</span>`;
 }
 return '<span class="muted" title="Fecha no verificada o fuera de 14 días">—</span>';
};
const barScore=(v)=>v==null?'<span class="muted">—</span>':`<span class="score ${v>=72?'good':v<35?'bad':''}">${esc(v)}</span>`;
const day=(s)=>{if(!s)return '—';try{return new Date(s+'T12:00:00').toLocaleDateString('es-AR')}catch(e){return s}};
const group=s=>{s=String(s||'');if(s.includes('COMPRA')||s.includes('VIGILAR'))return 'compra';if(s.includes('REDUCIR')||s.includes('SALIR'))return 'venta';if(s.includes('MANTENER'))return 'esperar';if(s.includes('SIN DATOS')||s.includes('SUBYACENTE')||s.includes('VIEJOS'))return 'sindatos';return 'esperar'};
function setTab(t){view=t;document.querySelectorAll('.tab').forEach(x=>{x.classList.toggle('active',x.dataset.tab===t);x.setAttribute('aria-current',x.dataset.tab===t?'page':'false')});[['acciones','pageAcciones'],['sectores','pageSectores'],['cartera','pageCartera'],['simulador','pageSimulador'],['metodo','pageMetodo']].forEach(([k,id])=>$(id).classList.toggle('hidden',k!==t));if(t==='cartera')renderTracked();}
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
 arr.sort((a,b)=>sort==='ticker'?a.ticker.localeCompare(b.ticker):sort==='worst'?(a.data?.rank_score??a.data?.score??200)-(b.data?.rank_score??b.data?.score??200):sort==='signal'?importance(a)-importance(b)||(b.data?.score??-1)-(a.data?.score??-1):(b.data?.rank_score??b.data?.score??-1)-(a.data?.rank_score??a.data?.score??-1));
 $('rowCount').textContent=arr.length+' / '+(dataset.assets||[]).length+' instrumentos';
 const visible=arr.slice(0,400);
 $('assetRows').innerHTML=visible.length?visible.map(x=>`<tr tabindex="0" data-ticker="${esc(x.ticker)}"><td>${esc(x.ticker)}<span class="ticker-sub">USA: ${esc(x.usa||'NO APLICA')} · ${esc(x.sector)}</span></td><td>${usd(x.data?.price)}</td><td><span class="${x.data?.cross_up21?'sma21-up':x.data?.cross_down21?'sma21-down':'muted'}">${usd(x.data?.ma21)}</span><span class="ticker-sub">${esc(x.data?.sma21_state||'—')}</span></td><td>${fmt(x.data?.rsi14d)}</td><td>${x.data?.macd_hist_d==null?'—':fmt(x.data?.macd_hist_d)}</td><td><span title="${esc((x.data?.rank_penalty_reasons||[]).join(' · ')||'Sin penalizaciones')}">${barScore(x.data?.rank_score)}</span></td><td>${fmt(x.data?.rvol20)}x</td><td>${eventHtml(x)}</td><td>${esc(x.data?.trend||'NO VERIFICADO')}</td><td>${badge(x.signal,x.tone)}</td></tr>`).join(''):'<tr><td colspan="10" style="padding:30px">No hay resultados para estos filtros.</td></tr>';
 $('assetRows').querySelectorAll('tr[data-ticker]').forEach(el=>{const act=()=>openDetails('asset',el.dataset.ticker);el.onclick=act;el.onkeydown=(e)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();act()}}});}
function renderTop5(){
 const root=$('top5Cards');
 const arr=Array.isArray(dataset.top5)?dataset.top5:[];
 $('top5Generated').textContent=dataset.meta?.generated_at_ar?'Corte '+new Date(dataset.meta.generated_at_ar).toLocaleString('es-AR',{dateStyle:'short',timeStyle:'short'}):'Sin corte válido';
 if(!arr.length){root.innerHTML='<p class="muted">No hay ranking confiable en este corte. Verificá la actualización y la liquidez.</p>';return;}
 root.innerHTML=arr.map((x,i)=>`<article class="top5-card" data-top5="${esc(x.ticker)}" tabindex="0" role="button" aria-label="Ver ficha de ${esc(x.ticker)}">
  <div class="top5-heading"><span class="top5-number">${i+1}</span><div><h3>${esc(x.ticker)} <small>${esc(x.usa)}</small></h3><small>${esc(x.sector)}</small></div><strong class="top5-score">${esc(x.rank_score)}<span>/100</span></strong></div>
  <div class="top5-pills"><span class="top5-tag">${esc(x.tag)}</span>${eventHtml(x)}</div>
  <div class="top5-stats"><div><span>Último cierre USD</span><strong>${usd(x.price)}</strong></div><div><span>SMA21 diario</span><strong>${usd(x.ma21)}</strong></div><div><span>RVOL20</span><strong>${fmt(x.rvol20)}x</strong></div><div><span>RS vs SPY (20r)</span><strong>${x.relative_spy20==null?'—':fmt(x.relative_spy20)+' pp'}</strong></div><div><span>RS vs QQQ (20r)</span><strong>${x.relative_qqq20==null?'—':fmt(x.relative_qqq20)+' pp'}</strong></div><div><span>Penalización</span><strong>${x.rank_penalty?'−'+fmt(x.rank_penalty)+' pts':'0 pts'}</strong></div><div><span>Invalidación ref.</span><strong>${usd(x.invalid_usd)}</strong></div></div>
  <div class="top5-footer"><span>${esc(signalLabel(x.signal))}</span><span>Ver ficha ›</span></div>
 </article>`).join('');
 root.querySelectorAll('[data-top5]').forEach(el=>{
   const act=()=>openDetails('asset',el.dataset.top5);
   el.onclick=act;el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();act()}};
 });
}

function renderSectors(){const arr=[...(dataset.sectors||[])].sort((a,b)=>(b.data?.rank_score??-1)-(a.data?.rank_score??-1));$('sectorCards').innerHTML=arr.length?arr.map(x=>`<article class="sector-card" data-sector="${esc(x.sector)}" tabindex="0"><div class="sector-heading"><div><h3>${esc(x.sector)}</h3><small>ETF proxy: ${esc(x.proxy)} · USD</small></div><div class="sector-score">${x.data?.rank_score??'—'}<span>/100</span></div></div><div class="meter"><span style="width:${Math.min(100,Math.max(0,x.data?.rank_score??0))}%"></span></div><p class="sector-info">${esc(x.data?.trend||'Sin lectura')} · RSI14 ${fmt(x.data?.rsi14d)} · ROC20 ${fmt(x.data?.roc20)}%</p><div class="sector-action">${badge(x.signal,x.tone)}<span class="muted">Detalle ›</span></div></article>`).join(''):'<p class="muted">Pendiente del primer corte automático.</p>';
 $('sectorCards').querySelectorAll('[data-sector]').forEach(el=>{const act=()=>openDetails('sector',el.dataset.sector);el.onclick=act;el.onkeydown=(e)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();act()}}});}
function renderTracked(){const arr=(dataset.assets||[]).filter(x=>tracked.has(x.ticker));$('trackedCount').textContent=tracked.size;$('watchRows').innerHTML=arr.length?arr.map(x=>`<div class="watch-card" data-watch="${esc(x.ticker)}" tabindex="0"><div><h3>${esc(x.ticker)} · ${esc(x.usa||'sin USD')}</h3><small>${esc(x.sector)}</small></div><div>${badge(x.signal,x.tone)}</div><div class="muted">Score ${x.data?.score??'—'}/100 · cierre ${day(x.data?.date)}</div></div>`).join(''):'<p class="muted">Todavía no marcaste instrumentos. Elegí un ticker en «Acciones y ETFs» y tocá «Seguir».</p>';$('watchRows').querySelectorAll('[data-watch]').forEach(el=>{el.onclick=()=>openDetails('asset',el.dataset.watch);el.onkeydown=e=>{if(e.key==='Enter'){openDetails('asset',el.dataset.watch)}}})}
function detailContent(x,type){const d=x.data||{},ticker=type==='sector'?x.proxy:x.ticker,name=type==='sector'?x.sector:x.ticker;
 const isAsset=type==='asset';const title=isAsset?`${esc(name)} <span style="color:#7fc0c0;font-size:15px">/ ${esc(x.usa||'sin subyacente')}</span>`:esc(name);
 const what=x.reasons&&x.reasons.length?x.reasons:['Sin histórico suficiente para interpretar el activo'];
 let plan='No hay gatillo automático confirmado. Esperar confluencia diaria/4H y validación del mercado.';
 if(group(x.signal)==='compra')plan='Entrada eventual en 3 tramos 40% / 35% / 25%, sólo tras confirmar reacción, volumen, filtro macro y concentración de cartera.';
 const earnings=x.earnings||null;
 const balanceInfo=isAsset?'<div class="detail-note"><strong>Próximo balance:</strong> '+(earnings ? esc(day(earnings.date)+' (dentro de '+earnings.days_until+' días) — '+earnings.status) : esc(x.earnings_status||'Fecha sin verificar'))+'. Fuente: Yahoo Finance (fecha indicativa, contrastar en IR). No es un bloqueo automático.</div>':'';
 const penalties=Array.isArray(d.rank_penalty_reasons)?d.rank_penalty_reasons:[];
 const penaltyInfo='<div class="detail-note"><strong>Score Oportunidad:</strong> '
    +esc(d.rank_score==null?'Sin datos':d.rank_score+'/100')
    +' · Fuerza relativa SPY/QQQ 30%, volumen 20%, SMA21 '
    +(d.asset_kind==='ACCION'?'20%, técnico 30%':'15%, técnico 35%')
    +'. <strong>Descuentos:</strong> '+(penalties.length?esc(penalties.join(' · ')):'ninguno')
    +'. <strong>Timing SMA21:</strong> '+esc(d.sma21_state||'Sin cálculo')
    +' · recién cruzada vale más que 10+ cierres arriba, si RSI/MACD pierden pendiente se restan puntos.</div>';
 const objective=d.target_2r!=null?`${usd(d.target_2r)} (2R) · ${usd(d.target_3r)} (3R)`:'No definido: la relación riesgo/beneficio aún no es adecuada.';
 const riskNote=isAsset?`<div class="detail-note"><strong>Operabilidad BYMA pendiente:</strong> este motor NO certifica ratio, listado vigente, liquidez, spread ni disponible en Bull/IOL. Confirmá <a class="mini-link" target="_blank" rel="noopener noreferrer" href="https://www.byma.com.ar/productos/productos-financieros/cedears">el PDF oficial de BYMA</a> antes de cualquier orden. Los indicadores son del subyacente USA en USD.</div>`:'<div class="detail-note">El ETF es proxy de fortaleza sectorial. La señal sectorial no convierte automáticamente cada CEDEAR del grupo en compra.</div>';
 return `<div class="detail-top"><span class="eyebrow">${isAsset?'CEDEAR · SUBYACENTE EN USD':'ROTACIÓN Y LIDERAZGO SECTORIAL'}</span><h2>${title}</h2><p>${esc(isAsset?x.sector:'ETF proxy de EE.UU.: '+x.proxy)} · Último cierre confirmado ${day(d.date)}</p><div class="detail-badges">${badge(x.signal,x.tone)} ${badge(d.trend||'SIN TENDENCIA','neutral')} ${badge('SCORE O. '+(d.rank_score??'—')+'/100','hold')}</div><div class="detail-price">${usd(d.price)}<small>del activo en EE.UU., no del CEDEAR en ARS</small></div></div>
 <div class="detail-metrics"><div class="detail-metric"><label>SMA21 · USD</label><strong>${usd(d.ma21)}</strong><small class="${d.cross_up21?'sma21-up':d.cross_down21?'sma21-down':'muted'}">${esc(d.sma21_state||'Sin lectura')}</small></div>
 <div class="detail-metric"><label>Edad sobre SMA21</label><strong>${d.sma21_age==null?'—':fmt(d.sma21_age)+' ruedas'}</strong></div>
 <div class="detail-metric"><label>Pendiente SMA21 (3r)</label><strong class="${d.sma21_slope_pct3<0?'sma21-down':'sma21-up'}">${d.sma21_slope_pct3==null?'—':fmt(d.sma21_slope_pct3)+'%'}</strong></div>
 <div class="detail-metric"><label>RSI14 · Δ 3 ruedas</label><strong class="${d.rsi_delta3<0?'sma21-down':'sma21-up'}">${d.rsi_delta3==null?'—':fmt(d.rsi_delta3)+' pts'}</strong></div>
 <div class="detail-metric"><label>MACD hist. · Δ 3r</label><strong class="${d.macd_delta3_pct<0?'sma21-down':'sma21-up'}">${d.macd_delta3_pct==null?'—':fmt(d.macd_delta3_pct)+'% del precio'}</strong></div><div class="detail-metric"><label>SMA20 · USD</label><strong>${usd(d.ma20)}</strong></div><div class="detail-metric"><label>SMA50 · USD</label><strong>${usd(d.ma50)}</strong></div><div class="detail-metric"><label>SMA200 · USD</label><strong>${usd(d.ma200)}</strong></div><div class="detail-metric"><label>RSI14 diario</label><strong>${fmt(d.rsi14d)}</strong></div><div class="detail-metric"><label>MACD hist. D</label><strong>${fmt(d.macd_hist_d)}</strong></div><div class="detail-metric"><label>RSI21 semanal</label><strong>${fmt(d.rsi21w)}</strong></div><div class="detail-metric"><label>RSI21 mensual</label><strong>${fmt(d.rsi21m)}</strong></div><div class="detail-metric"><label>ADX14 diario</label><strong>${fmt(d.adx14)}</strong></div><div class="detail-metric"><label>RS vs SPY (20r)</label><strong>${d.rs_spy20==null?'—':fmt(d.rs_spy20)+' pp'}</strong></div><div class="detail-metric"><label>RS vs QQQ (20r)</label><strong>${d.rs_qqq20==null?'—':fmt(d.rs_qqq20)+' pp'}</strong></div><div class="detail-metric"><label>Volumen confirmado</label><strong>${fmt(d.volume_confirm_score)}/100</strong></div><div class="detail-metric"><label>RVOL20</label><strong>${fmt(d.rvol20)}x</strong></div><div class="detail-metric"><label>Volumen 20r USD</label><strong>${d.dollar_volume20==null?'—':usd(d.dollar_volume20)}</strong></div><div class="detail-metric"><label>OBV (10 ruedas)</label><strong>${d.obv_up10==null?'—':d.obv_up10?'Confirmando':'Sin confirmar'}</strong></div><div class="detail-metric"><label>Extensión / ATR14</label><strong>${fmt(d.stretch_atr20)} ATR</strong></div></div>
 <div class="detail-section"><h3>Por qué aparece esta señal</h3><ul>${what.map(t=>`<li>${esc(t)}</li>`).join('')}</ul></div>
 <div class="detail-section"><h3>Plan informativo / control de riesgo</h3><p>${esc(plan)}</p><div class="detail-metrics"><div class="detail-metric"><label>Nivel de referencia / soporte</label><strong>${usd(d.ma20)}</strong></div><div class="detail-metric"><label>Invalidación de referencia</label><strong>${usd(d.invalid_usd)}</strong></div><div class="detail-metric" style="grid-column:span 2"><label>Objetivos hipotéticos desde cierre USD</label><strong>${esc(objective)}</strong></div></div><p class="muted">La invalidación es aproximada: revisar estructura 4H/diaria y catalizadores. Los objetivos R son escenarios, no pronósticos.</p></div>
 ${penaltyInfo} ${balanceInfo} ${riskNote}<p class="muted" style="font-size:11px">Calidad: último cierre USD ${day(d.date)} · Macroeconomía: ${esc(dataset.macro?.state||'NO VERIFICADO')} · fuente: Yahoo/yfinance.</p>
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


const signedUsd=v=>(v==null?'—':(Number(v)>=0?'+':'−')+usd(Math.abs(Number(v))));
const signedPct=v=>(v==null?'—':(Number(v)>0?'+':'')+fmt(v)+'%');
function linePaper(points){
 const a=points.filter(x=>x&&Number.isFinite(Number(x.equity)));
 if(a.length<2)return '<p class="muted">La curva del patrimonio aparecerá con los próximos cierres registrados.</p>';
 const values=a.map(x=>Number(x.equity));
 const lo=Math.min(...values),hi=Math.max(...values);
 const span=Math.max(1,hi-lo),N=a.length;
 const path=a.map((x,i)=>{
   const xx=(15+i*570/(N-1)).toFixed(2);
   const yy=(120-(Number(x.equity)-lo)/span*105).toFixed(2);
   return (i?'L':'M')+xx+' '+yy;
 }).join(' ');
 return '<svg class="paper-svg" viewBox="0 0 600 140" role="img" aria-label="Evolución del patrimonio simulado USD"><line x1="15" y1="120" x2="585" y2="120" stroke="#395168" stroke-width="1"/><path fill="none" stroke="#48d7bd" stroke-width="2.4" d="'+path+'"/></svg><div class="paper-graph-caption">Desde '+esc(day(a[0].date))+' hasta '+esc(day(a[a.length-1].date))+' · '+fmt(lo)+' a '+fmt(hi)+' USD</div>';
}
function renderPaper(){
 const root=$('paperStatus');
 if(!paper){
   root.className='paper-status paper-warn';
   root.textContent='Todavía no hay ledger simulado publicado, o no se pudo recuperar el archivo. No inventamos operaciones.';
   return;
 }
 const p=paper;
 const outdated=Date.now()-Date.parse((p.last_closed_session||'')+'T23:59:59Z')>6*86400000;
 root.className='paper-status'+(outdated?' paper-warn':'');
 root.textContent=(outdated?'Registro con último cierre antiguo. ':'')+'Cartera 100% ficticia. Señales de cierre, ejecución al OPEN siguiente, stop 8% con posible gap adverso. No son órdenes reales.';
 $('paperCut').textContent='Última rueda registrada: '+day(p.last_closed_session);
 $('paperEquity').textContent=usd(p.equity_usd);
 $('paperCash').textContent=usd(p.cash_usd);
 $('paperReturn').textContent=signedPct(p.return_pct)+' ('+signedUsd(p.equity_usd-p.initial_capital_usd)+')';
 $('paperReturn').className=Number(p.return_pct)>=0?'sma21-up':'sma21-down';
 $('paperTrades').textContent=String(p.closed_count??0)+(p.win_rate_pct==null?'':' · acierto '+fmt(p.win_rate_pct)+'%');
 $('paperDD').textContent=fmt(p.max_drawdown_pct)+'%';
 $('paperGraph').innerHTML=linePaper(p.equity_history||[]);
 const pos=p.open_positions||[];
 $('paperPositions').innerHTML=pos.length?pos.map(x=>`<tr><td>${esc(x.ticker)}<span class="ticker-sub">${esc(x.usa)}</span></td><td>${day(x.entry_date)}</td><td>${esc(x.tranches)}/3</td><td>${usd(x.avg_cost_usd)}</td><td>${usd(x.last_price_usd)}</td><td>${usd(x.stop_usd)}</td><td class="${x.unrealized_usd>=0?'sma21-up':'sma21-down'}">${signedUsd(x.unrealized_usd)}</td><td>${esc(x.sessions_held)}</td></tr>`).join(''):'<tr><td colspan="8">Sin posiciones abiertas. El efectivo queda en reserva mientras no aparezcan condiciones.</td></tr>';
 const closed=[...(p.closed_trades||[])].reverse();
 $('paperClosed').innerHTML=closed.length?closed.map(x=>`<tr><td>${esc(x.ticker)}<span class="ticker-sub">${esc(x.usa)}</span></td><td>${day(x.entry_date)}</td><td>${day(x.exit_date)}</td><td>${esc(x.holding_sessions)}</td><td>${esc(x.tranches)}/3</td><td>${usd(x.avg_cost_usd)}</td><td>${usd(x.exit_usd)}</td><td class="${x.pnl_usd>=0?'sma21-up':'sma21-down'}">${signedUsd(x.pnl_usd)}</td><td>${signedPct(x.return_pct)}</td><td>${esc(x.reason)}</td></tr>`).join(''):'<tr><td colspan="10">Todavía no se cerraron operaciones simuladas.</td></tr>';
 const fills=[...(p.fills||[])].reverse();
 $('paperFills').innerHTML=fills.length?fills.map(x=>`<tr><td>${day(x.date)}</td><td>${esc(x.usa)}</td><td><span class="pill ${x.action==='STOP LOSS'?'down':x.action.startsWith('COMPRA')?'up':'hold'}">${esc(x.action)}</span></td><td>${usd(x.price_usd)}</td><td>${fmt(x.shares)}</td><td>${usd(x.amount_usd)}</td><td>${esc(x.reason)}</td></tr>`).join(''):'<tr><td colspan="7">Todavía no hay compras ni ventas ejecutadas en la simulación.</td></tr>';
 const waiting=p.pending_orders||[];
 $('paperPending').innerHTML=waiting.length?waiting.map(x=>`<tr><td>${day(x.issued_day)}</td><td>${esc(x.ticker||x.usa)}</td><td>${esc(x.side==='BUY'?'COMPRA '+(x.tranche||1)+'/3':'VENTA')}</td><td>${esc(x.reason)}</td></tr>`).join(''):'<tr><td colspan="4">Sin órdenes pendientes para el próximo open.</td></tr>';
}
async function loadPaper(){
 try{
   const r=await fetch('./paper.json?refresh='+Date.now(),{cache:'no-store'});
   if(!r.ok)throw new Error('HTTP '+r.status);
   const j=await r.json();
   if(j.is_simulated!==true||j.initial_capital_usd!==2000)throw new Error('Estado inválido');
   paper=j;
 }catch(e){paper=null}
 renderPaper();
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
 if(batchStale||j.assets.every(x=>x.data&&staleDate(x.data.date))){j.top5=[];}
 dataset=j;}catch(e){$('criticalBanner').textContent='Sin datos. Si abriste el archivo local, publicalo en GitHub Pages. Error de lectura: '+e.message;}fillFilters();renderHeader();renderTop5();renderAssets();renderSectors();renderTracked();}
for(const el of document.querySelectorAll('.tab'))el.onclick=()=>setTab(el.dataset.tab);
for(const id of ['searchInput','sectorFilter','signalFilter','sortFilter'])$(id).addEventListener(id==='searchInput'?'input':'change',renderAssets);
$('modalClose').onclick=()=>$('detailModal').close();$('detailModal').addEventListener('click',e=>{if(e.target===$('detailModal'))$('detailModal').close()});
load();
loadPaper();
