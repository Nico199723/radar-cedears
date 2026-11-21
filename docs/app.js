'use strict';
const $ = id => document.getElementById(id);
const storeKey='radar_cedears_watch_v1';
let dataset=null,view='acciones',tracked=new Set(),selected=null,paper=null;
try{tracked=new Set(JSON.parse(localStorage.getItem(storeKey)||'[]'));}catch(e){}
const esc=v=>String(v==null?'—':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const usd=v=>(v==null||!Number.isFinite(Number(v)))?'—':'US$ '+Number(v).toLocaleString('es-AR',{minimumFractionDigits:2,maximumFractionDigits:3});
const fmt=v=>(v==null||!Number.isFinite(Number(v)))?'—':Number(v).toLocaleString('es-AR',{maximumFractionDigits:2});
const tone=t=>(['up','caution','watch','down','wait','hold','neutral'].includes(t)?t:'neutral');
const signalLabel=s=>s==='MANTENER / ESPERAR'||s==='ESPERAR'?'HOLD / ESPERAR':s==='ESPERAR MACRO'?'HOLD / ESPERAR · MACRO':s;
const badge=(s,t)=>{const kind=s==='COMPRA CONDICIONAL'?'up':s==='COMPRA CON PRECAUCIÓN'?'caution':String(s||'').startsWith('VIGILAR COMPRA')?'watch':tone(t);return `<span class="pill ${kind}">${esc(signalLabel(s||'SIN DATOS'))}</span>`;};
const upcomingEarnings=x=>{
 const e=x?.earnings;if(!e?.date||!/^\d{4}-\d{2}-\d{2}$/.test(e.date))return null;
 const today=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Argentina/Buenos_Aires',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 const timestamp=Date.parse(e.date+'T00:00:00Z');
 if(!Number.isFinite(timestamp)||new Date(timestamp).toISOString().slice(0,10)!==e.date)return null;
 const n=Math.round((timestamp-Date.parse(today+'T00:00:00Z'))/86400000);
 return n>=0?{...e,days_until:n}:null;
};
const eventHtml=x=>{
 const e=upcomingEarnings(x), n=e?.days_until, st=String(x?.earnings_status||dataset?.assets?.find(a=>a.ticker===x?.ticker)?.earnings_status||'');
 if(typeof n==='number'&&n>=0){
   const when=e.time_label?' · '+e.time_label:'';
   const old=e.stale?' · dato de caché de '+e.cache_age_days+' días':'';
   const title=esc(e.date+when+' — fecha indicativa ('+(e.source||'calendario gratuito')+old+'); verificar en relaciones con inversores');
   if(n<=14){
     return `<span class="balance-alert ${n<=7?'urgent':'soon'}" title="${title}">⚠ ${esc(day(e.date))} · ${n===0?'HOY':'en '+n+'d'}${e.time==='BMO'?' · AM':e.time==='AMC'?' · PM':''}</span>`;
   }
   return `<span class="muted" title="${title}">${esc(day(e.date))}</span>`;
 }
 if(st.startsWith('ETF')) return '<span class="muted" title="Los ETF no publican balances">ETF</span>';
 if(st.startsWith('SIN FECHA')) return '<span class="muted" title="Consultado: sin fecha futura verificable en las fuentes disponibles; revisar en relaciones con inversores">s/f</span>';
 return '<span class="muted" title="Fecha no verificada: no consultada en esta corrida">—</span>';
};
const barScore=(v)=>v==null?'<span class="muted">—</span>':`<span class="score ${v>=(dataset?.meta?.methodology?.buy??Infinity)?'good':v<35?'bad':''}">${esc(v)}</span>`;
const day=(s)=>{if(!s)return '—';try{return new Date(s+'T12:00:00').toLocaleDateString('es-AR')}catch(e){return s}};
const group=s=>{s=String(s||'');if(s==='COMPRA CONDICIONAL'||s==='COMPRA CON PRECAUCIÓN')return 'compra';if(s.startsWith('VIGILAR COMPRA'))return 'vigilancia';if(s.includes('REDUCIR')||s.includes('SALIR'))return 'venta';if(s.includes('MANTENER'))return 'esperar';if(s.includes('SIN DATOS')||s.includes('SUBYACENTE')||s.includes('VIEJOS'))return 'sindatos';return 'esperar'};
function setTab(t){view=t;document.querySelectorAll('.tab').forEach(x=>{x.classList.toggle('active',x.dataset.tab===t);x.setAttribute('aria-current',x.dataset.tab===t?'page':'false')});[['acciones','pageAcciones'],['rebotes','pageRebotes'],['sectores','pageSectores'],['cartera','pageCartera'],['simulador','pageSimulador'],['metodo','pageMetodo']].forEach(([k,id])=>$(id).classList.toggle('hidden',k!==t));if(t==='cartera')renderTracked();}
function baseline(){return {meta:{source:'Catálogo local · pendiente de ejecución inicial',universe_size:0,mapped_us:0,download_coverage:0},macro:{state:'NO VERIFICADO'},assets:[],sectors:[]}}
function renderHeader(){const m=dataset.meta||{};const a=dataset.assets||[];const generated=m.generated_at_ar?new Date(m.generated_at_ar):null;const age=generated?(Date.now()-generated.getTime())/(3600000):9999;const coverage=Number(m.download_coverage||0);
 const fresh=generated&&age<=36&&age>=-1;const banner=$('criticalBanner');
 if(!generated){banner.className='critical bad';banner.textContent='Sin actualización real todavía. Ejecutá la acción de GitHub «Actualizar radar CEDEARs» para cargar precios USD y señales. Hasta entonces NO hay recomendaciones.'}
 else if(!fresh){banner.className='critical bad';banner.textContent='ATENCIÓN: última actualización de hace '+Math.max(0,Math.round(age))+' horas. Revisá GitHub Actions; no operes basándote en señales desactualizadas.'}
 else{banner.className='critical ok';banner.textContent='Indicadores sobre cierres diarios de EE.UU. en dólares. Señales informativas: no son órdenes ni reemplazan validación de BYMA y fundamentales.'}
 $('macroValue').textContent=dataset.macro?.state||'—';$('macroValue').style.color=dataset.macro?.state==='FAVORABLE'?'#5ee1c2':dataset.macro?.state==='DEFENSIVO'?'#f27b80':'#f6c16b';
 const method=m.methodology||{};
 if($('rankingDescription'))$('rankingDescription').textContent=method.engine?.startsWith('Espectral')?'Score espectral único para ranking y señal. Cupo sectorial suave; mejores disponibles identificados.':'Ranking para estudiar del motor vigente. Puede incluir activos sin compra; verificá la señal de cada ficha.';
 for(const [id,value] of [['methodSummary',method.description],['methodRules',method.description],['methodMacro',method.macro]]){if($(id))$(id).textContent=value||'Reglas no incluidas en este corte; actualizar datos.';}
 const policy=dataset.risk_policy_paper||{};
 $('macroSub').textContent=(policy.mode==='PRUDENTE'?'PRECAUCIÓN: posición máx. US$ 120 · reserva 70% · stop 6% · ':policy.mode==='NORMAL'?'NORMAL: posición máx. US$ 250 · reserva 50% · stop 8% · ':'SIN NUEVAS COMPRAS: datos macro/VIX · ')+(dataset.macro?.vix!=null?'VIX '+fmt(dataset.macro.vix):'sin VIX verificable');
 if(m.methodology?.engine?.startsWith('Espectral'))$('macroSub').textContent=m.methodology.macro;
 const ready=a.filter(x=>group(x.signal)==='compra').length,watch=a.filter(x=>group(x.signal)==='vigilancia').length;
 $('buyCount').textContent=ready;$('buyCaption').textContent=watch+' candidatas en vigilancia (no son compras)';$('assetCount').textContent=m.universe_size||a.length;
 $('mappedCount').textContent=(m.mapped_us||0)+' con subyacente USA candidato';$('coverageCount').textContent=generated?fmt(coverage)+'%':'Sin datos';
 $('heroLast').textContent=generated?'Último procesamiento: '+new Date(m.generated_at_ar).toLocaleString('es-AR',{dateStyle:'short',timeStyle:'short'}):'Pendiente de primer corte';
 const ec=m.earnings_coverage||{};$('footerSource').textContent=(m.source||'Sin fuente')+' · '+(m.generated_at_ar?'corte '+new Date(m.generated_at_ar).toLocaleString('es-AR'):'sin datos')+(ec.stocks?' · balances con fecha: '+ec.with_date+'/'+ec.stocks:'');
 $('liveIndicator').innerHTML=generated&&fresh?'<i style="background:#2bd5bc"></i>Última ejecución registrada':'<i></i>Datos pendientes';
 $('trackedCount').textContent=tracked.size;
}
function fillFilters(){const ss=[...new Set((dataset.assets||[]).map(x=>x.sector).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'es'));
 $('sectorFilter').innerHTML='<option value="">Todos los sectores</option>'+ss.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('');}
function renderAssets(){const q=$('searchInput').value.toLowerCase().trim(),sector=$('sectorFilter').value,sig=$('signalFilter').value,sort=$('sortFilter').value;
 let arr=(dataset.assets||[]).filter(x=>(!q||(x.ticker||'').toLowerCase().includes(q)||(x.usa||'').toLowerCase().includes(q)||(x.sector||'').toLowerCase().includes(q))&&(!sector||x.sector===sector)&&(!sig||group(x.signal)===sig));
 const importance=x=>({compra:0,vigilancia:1,esperar:2,venta:3,sindatos:4}[group(x.signal)]??5);
 arr.sort((a,b)=>sort==='ticker'?a.ticker.localeCompare(b.ticker):sort==='worst'?(a.data?.rank_score??a.data?.score??200)-(b.data?.rank_score??b.data?.score??200):sort==='priority'||sort==='signal'?importance(a)-importance(b)||(b.data?.rank_score??-1)-(a.data?.rank_score??-1):(b.data?.rank_score??b.data?.score??-1)-(a.data?.rank_score??a.data?.score??-1));
 $('rowCount').textContent=arr.length+' / '+(dataset.assets||[]).length+' instrumentos';
 const visible=arr.slice(0,400);
 $('assetRows').innerHTML=visible.length?visible.map(x=>`<tr tabindex="0" data-ticker="${esc(x.ticker)}"><td>${esc(x.ticker)}<span class="ticker-sub">USA: ${esc(x.usa||'NO APLICA')} · ${esc(x.sector)}</span></td><td>${usd(x.data?.price)}</td><td><span class="${x.data?.cross_up21?'sma21-up':x.data?.cross_down21?'sma21-down':'muted'}">${usd(x.data?.ma21)}</span><span class="ticker-sub">${esc(x.data?.sma21_state||'—')}</span></td><td>${fmt(x.data?.rsi14d)}</td><td>${x.data?.macd_hist_d==null?'—':fmt(x.data?.macd_hist_d)}</td><td><span title="${esc((x.data?.rank_penalty_reasons||[]).join(' · ')||'Sin penalizaciones')}">${barScore(x.score_decision??x.data?.rank_score)}</span><span class="ticker-sub">${esc(x.candidate?.level||x.data?.rank_level||'')}</span></td><td>${fmt(x.data?.rvol20)}x</td><td>${eventHtml(x)}</td><td>${esc(x.data?.trend||'NO VERIFICADO')}</td><td>${badge(x.signal,x.tone)}</td></tr>`).join(''):'<tr><td colspan="10" style="padding:30px">No hay resultados para estos filtros.</td></tr>';
 const cards=$('assetCards');if(cards){cards.innerHTML=visible.map(x=>`<button class="asset-card" data-ticker="${esc(x.ticker)}"><strong>${esc(x.ticker)}</strong><span>Score ${esc(x.data?.rank_score)}</span>${badge(x.signal,x.tone)}<span>Balance: ${eventHtml(x)}</span><small>Ver gráfico y detalle ›</small></button>`).join('')||'<p>Sin resultados.</p>';cards.querySelectorAll('[data-ticker]').forEach(el=>el.onclick=()=>openDetails('asset',el.dataset.ticker));}
 $('assetRows').querySelectorAll('tr[data-ticker]').forEach(el=>{const act=()=>openDetails('asset',el.dataset.ticker);el.onclick=act;el.onkeydown=(e)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();act()}}});}
function renderRebounds(){
 const root=$('reboundRows');if(!root)return;
 const rows=Array.isArray(dataset?.rebounds)?dataset.rebounds:[];
 if(!rows.length){root.innerHTML='<tr><td colspan="10">No hay rebotes que superen TODOS los filtros y R:R >=2 en el corte vigente. No se fuerzan oportunidades.</td></tr>';return}
 root.innerHTML=rows.slice(0,8).map(x=>`<tr>
  <td><strong>${esc(x.cedear||x.ticker)}</strong><span class="ticker-sub">${esc(x.ticker)}</span></td>
  <td>${fmt(x.drop_from_high_pct)}%</td><td>${fmt(x.rsi14)}</td>
  <td>${fmt(x.distance_atr)} ATR</td>
  <td><small>${esc(x.turn_signal)}</small><span class="ticker-sub">${esc(x.structure)}</span></td>
  <td>${usd(x.target_usd)}<span class="ticker-sub">${esc(x.target_type)}</span></td>
  <td>${usd(x.stop_usd)}<span class="ticker-sub">7 ruedas máximo</span></td>
  <td><strong>${fmt(x.rr)}R</strong></td>
  <td><small>${esc(x.earnings_status||'No verificado')}</small></td>
  <td><span class="rebound-risk">EXPERIMENTAL · ALTO RIESGO</span></td>
 </tr>`).join('');
}
function renderTop5(){
 const root=$('top5Cards');
 const arr=Array.isArray(dataset.top5)?dataset.top5:[];
 $('top5Generated').textContent=dataset.meta?.generated_at_ar?'Corte '+new Date(dataset.meta.generated_at_ar).toLocaleString('es-AR',{dateStyle:'short',timeStyle:'short'}):'Sin corte válido';
 if(!arr.length){root.innerHTML='<p class="muted">No hay ranking confiable en este corte. Verificá la actualización y la liquidez.</p>';return;}
 root.innerHTML=arr.map((x,i)=>`<article class="top5-card" data-top5="${esc(x.ticker)}" tabindex="0" role="button" aria-label="Ver ficha de ${esc(x.ticker)}">
  <div class="top5-heading"><span class="top5-number">${i+1}</span><div><h3>${esc(x.ticker)} <small>${esc(x.usa)}</small></h3><small>${esc(x.sector)}</small></div><strong class="top5-score">${esc(x.rank_score)}<span>/100</span></strong></div>
  <div class="top5-pills"><span class="top5-tag">${esc(x.tag)}</span>${badge(x.signal)}${eventHtml(x)}</div>
  <div class="top5-stats"><div><span>${dataset.meta?.provisional?'Provisorio USD':'Último cierre USD'}</span><strong>${usd(x.price)}</strong></div><div><span>SMA21 diario</span><strong>${usd(x.ma21)}</strong></div><div><span>RVOL20</span><strong>${fmt(x.rvol20)}x</strong></div><div><span>RS vs SPY (20r)</span><strong>${x.relative_spy20==null?'—':fmt(x.relative_spy20)+' pp'}</strong></div><div><span>RS vs QQQ (20r)</span><strong>${x.relative_qqq20==null?'—':fmt(x.relative_qqq20)+' pp'}</strong></div><div><span>Penalización</span><strong>${x.rank_penalty?'−'+fmt(x.rank_penalty)+' pts':'0 pts'}</strong></div><div><span>Invalidación ref.</span><strong>${usd(x.invalid_usd)}</strong></div></div>
  <div class="top5-footer"><span>${esc(x.candidate?.level||x.rank_level||'Revisar setup')}</span><span>Ver ficha ›</span></div>
 </article>`).join('');
 root.querySelectorAll('[data-top5]').forEach(el=>{
   const act=()=>openDetails('asset',el.dataset.top5);
   el.onclick=act;el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();act()}};
 });
}

function renderSectors(){const arr=[...(dataset.sectors||[])].sort((a,b)=>(b.data?.rank_score??-1)-(a.data?.rank_score??-1));$('sectorCards').innerHTML=arr.length?arr.map(x=>`<article class="sector-card" data-sector="${esc(x.sector)}" tabindex="0"><div class="sector-heading"><div><h3>${esc(x.sector)}</h3><small>ETF proxy: ${esc(x.proxy)} · USD</small></div><div class="sector-score">${x.data?.rank_score??'—'}<span>/100</span></div></div><div class="meter"><span style="width:${Math.min(100,Math.max(0,x.data?.rank_score??0))}%"></span></div><p class="sector-info">${esc(x.data?.trend||'Sin lectura')} · RSI14 ${fmt(x.data?.rsi14d)} · ROC20 ${fmt(x.data?.roc20)}%</p><div class="sector-action">${badge(x.signal,x.tone)}<span class="muted">Detalle ›</span></div></article>`).join(''):'<p class="muted">Pendiente del primer corte automático.</p>';
 $('sectorCards').querySelectorAll('[data-sector]').forEach(el=>{const act=()=>openDetails('sector',el.dataset.sector);el.onclick=act;el.onkeydown=(e)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();act()}}});}
function renderTracked(){const arr=(dataset.assets||[]).filter(x=>tracked.has(x.ticker));$('trackedCount').textContent=tracked.size;$('watchRows').innerHTML=arr.length?arr.map(x=>`<div class="watch-card" data-watch="${esc(x.ticker)}" tabindex="0"><div><h3>${esc(x.ticker)} · ${esc(x.usa||'sin USD')}</h3><small>${esc(x.sector)}</small></div><div>${badge(x.signal,x.tone)}</div><div class="muted">Score ${x.data?.score??'—'}/100 · cierre ${day(x.data?.date)}</div></div>`).join(''):'<p class="muted">Todavía no marcaste instrumentos. Elegí un ticker en «Acciones y ETFs» y tocá «Seguir».</p>';$('watchRows').querySelectorAll('[data-watch]').forEach(el=>{el.onclick=()=>openDetails('asset',el.dataset.watch);el.onkeydown=e=>{if(e.key==='Enter'){openDetails('asset',el.dataset.watch)}}})}
function tickerChart(d){
 const points=(d.price_history||[]).filter(p=>p.close!=null&&Number.isFinite(Number(p.close)));
 if(points.length<2)return '<p class="muted">Gráfico pendiente de un corte con histórico.</p>';
 const W=760,H=290,L=70,R=85,T=22,B=40,colors={close:'#e5eeee',sma21:'#5ee1c2',sma50:'#f6c16b',sma200:'#9f9aff'};
 const values=points.flatMap(p=>Object.keys(colors).map(k=>p[k])).concat([d.invalid_usd,d.target_2r]).filter(v=>v!=null&&Number.isFinite(Number(v))).map(Number);
 const lo=Math.min(...values),hi=Math.max(...values),pad=Math.max((hi-lo)*.08,hi*.005),min=lo-pad,max=hi+pad;
 const x=i=>L+i*(W-L-R)/(points.length-1), y=v=>T+(max-v)*(H-T-B)/(max-min);
 let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="90 ruedas con medias móviles, stop y objetivo"><title>Precio del subyacente en USD</title>`;
 for(let i=0;i<5;i++){const v=min+(max-min)*i/4;svg+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#28404a"/><text x="${L-8}" y="${y(v)+4}" text-anchor="end" fill="#a5b9c5" font-size="10">${esc(usd(v))}</text>`;}
 for(const [k,color] of Object.entries(colors)){let path='',previous=false;points.forEach((p,i)=>{const valid=p[k]!=null&&Number.isFinite(Number(p[k]));if(valid)path+=`${previous?'L':'M'}${x(i)},${y(p[k])} `;previous=valid;});svg+=`<path d="${path}" fill="none" stroke="${color}" stroke-width="${k==='close'?2:1.3}"/>`;}
 for(const [key,label,color] of [['invalid_usd','Stop ref.','#f27b80'],['target_2r','Objetivo 2R','#5ee1c2']]){const v=d[key];if(v!=null&&Number.isFinite(Number(v)))svg+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="${color}" stroke-dasharray="4 4"/><text x="${W-R+5}" y="${y(v)+4}" font-size="10" fill="${color}">${esc(label)}</text>`;}
 points.forEach((p,i)=>{svg+=`<circle cx="${x(i)}" cy="${y(p.close)}" r="4" fill="transparent"><title>${esc(day(p.date)+' · '+usd(p.close))}</title></circle>`;});
 [...new Set([0,Math.floor((points.length-1)/2),points.length-1])].forEach(i=>svg+=`<text x="${x(i)}" y="${H-12}" text-anchor="middle" fill="#a5b9c5" font-size="11">${esc(day(points[i].date))}</text>`);
 return '<section class="ticker-chart"><h3>Últimas 90 ruedas · USD</h3><div class="chart-scroll">'+svg+'</svg></div><p class="muted">Precio · <span style="color:#5ee1c2">SMA21</span> · <span style="color:#f6c16b">SMA50</span> · <span style="color:#9f9aff">SMA200</span> · Stop y objetivo de referencia del corte, no históricos.</p></section>';
}

function detailContent(x,type){const d=x.data||{},ticker=type==='sector'?x.proxy:x.ticker,name=type==='sector'?x.sector:x.ticker;
 const isAsset=type==='asset';const title=isAsset?`${esc(name)} <span style="color:#7fc0c0;font-size:15px">/ ${esc(x.usa||'sin subyacente')}</span>`:esc(name);
 const what=x.reasons&&x.reasons.length?x.reasons:['Sin histórico suficiente para interpretar el activo'];
 let plan='No hay gatillo automático confirmado. Esperar confluencia diaria/4H y validación del mercado.';
 if(group(x.signal)==='compra')plan='Entrada eventual en 3 tramos 40% / 35% / 25%, sólo tras confirmar reacción, volumen y concentración de cartera.';
 if(x.signal==='COMPRA CON PRECAUCIÓN'&&!d.spectrum)plan='Macro adverso: NO impide operar con fuerza propia. Papel simulado hasta US$ 120, reserva del 70%, stop de referencia 6% y máximo 2 posiciones; primer tramo del 40% y los restantes sólo con confirmación. Los gaps pueden superar el stop.';
 const earnings=upcomingEarnings(x);
 const balanceInfo=isAsset?'<div class="detail-note"><strong>Próximo balance:</strong> '+(earnings ? esc(day(earnings.date)+(earnings.time_label?' · '+earnings.time_label:'')+' (dentro de '+earnings.days_until+' días) — '+earnings.status) : esc(x.earnings_status||'Fecha sin verificar'))+'. Fuente: '+esc(earnings?earnings.source+(earnings.stale?' · dato de caché de '+earnings.cache_age_days+' días':''):'calendarios gratuitos (Nasdaq y Yahoo Finance)')+'; fecha indicativa, contrastar en IR. No es un bloqueo automático.</div>':'';
 const status=x.candidate||{};
 const candidateInfo='<div class="detail-note">'+esc(dataset.meta?.methodology?.description||'Configuración no disponible')+'</div>';
 const spectral=d.spectrum;
 const spectrumInfo=spectral?'<div class="detail-note"><strong>'+esc(spectral.stage)+'</strong><div class="meter"><span style="width:'+Math.min(100,Math.max(0,Number(d.rank_score)||0))+'%"></span></div><p>'+esc((spectral.narrative||[]).join(' · '))+'</p><p>Tamaño relativo: '+esc(fmt(spectral.size_mult*100))+'% · Fricciones: '+esc((spectral.frictions||[]).join(' · ')||'ninguna')+'</p></div>':'';
 const atrPlan=d.atr_risk_preview;
 const atrInfo=atrPlan?'<div class="detail-note"><strong>Ensayo ATR · no ejecutado:</strong> stop '+usd(atrPlan.stop)+' · '+fmt(atrPlan.shares)+' acciones · riesgo estimado '+usd(atrPlan.risk_usd)+' sobre US$ 2.000. Hasta 0,5%; límite de exposición 50%, costos incluidos; gaps pueden excederlo. Sizing de referencia desde el cierre, se recalcula al open.</div>':'';
 const penalties=Array.isArray(d.rank_penalty_reasons)?d.rank_penalty_reasons:[];
 const penaltyInfo='<div class="detail-note"><strong>Score Oportunidad:</strong> '
    +esc(d.rank_score==null?'Sin datos':d.rank_score+'/100')
    +' · Fuerza relativa SPY/QQQ 30%, volumen 20%, SMA21 '
    +(d.asset_kind==='ACCION'?'20%, técnico 30%':'15%, técnico 35%')
    +'. <strong>Descuentos:</strong> '+(penalties.length?esc(penalties.join(' · ')):'ninguno')
    +'. <strong>Timing SMA21:</strong> '+esc(d.sma21_state||'Sin cálculo')
    +' · recién cruzada vale más que 10+ cierres arriba, si RSI/MACD pierden pendiente se restan puntos.</div>';
 const rp=x.risk_plan_paper;
 const riskPlan=isAsset&&rp?'<div class="detail-note"><strong>Régimen de exposición SIMULADA:</strong> '+esc(rp.mode)+' · posición máxima '+usd(rp.max_position_usd)+' · reserva '+fmt(rp.reserve_pct)+'% · stop de referencia '+(rp.stop_pct==null?'sin nuevas compras':fmt(rp.stop_pct)+'%')+'. No es una instrucción a tu broker.</div>':'';
 const objective=d.target_2r!=null?`${usd(d.target_2r)} (2R) · ${usd(d.target_3r)} (3R)`:'No definido: la relación riesgo/beneficio aún no es adecuada.';
 const riskNote=isAsset?`<div class="detail-note"><strong>Operabilidad BYMA pendiente:</strong> este motor NO certifica ratio, listado vigente, liquidez, spread ni disponible en Bull/IOL. Confirmá <a class="mini-link" target="_blank" rel="noopener noreferrer" href="https://www.byma.com.ar/productos/productos-financieros/cedears">el PDF oficial de BYMA</a> antes de cualquier orden. Los indicadores son del subyacente USA en USD.</div>`:'<div class="detail-note">El ETF es proxy de fortaleza sectorial. La señal sectorial no convierte automáticamente cada CEDEAR del grupo en compra.</div>';
 return `<div class="detail-top"><span class="eyebrow">${isAsset?'CEDEAR · SUBYACENTE EN USD':'ROTACIÓN Y LIDERAZGO SECTORIAL'}</span><h2>${title}</h2><p>${esc(isAsset?x.sector:'ETF proxy de EE.UU.: '+x.proxy)} · ${x.provisional?'PROVISORIO · barra '+esc(x.quote_at||'sin dato'):'Último cierre confirmado '+esc(day(d.date))}</p><div class="detail-badges">${badge(x.signal,x.tone)} ${badge(d.trend||'SIN TENDENCIA','neutral')} ${badge('SCORE O. '+(d.rank_score??'—')+'/100','hold')}</div><div class="detail-price">${usd(d.price)}<small>del activo en EE.UU., no del CEDEAR en ARS</small></div></div>
 ${tickerChart(d)}
 <div class="detail-metrics"><div class="detail-metric"><label>SMA21 · USD</label><strong>${usd(d.ma21)}</strong><small class="${d.cross_up21?'sma21-up':d.cross_down21?'sma21-down':'muted'}">${esc(d.sma21_state||'Sin lectura')}</small></div>
 <div class="detail-metric"><label>Edad sobre SMA21</label><strong>${d.sma21_age==null?'—':fmt(d.sma21_age)+' ruedas'}</strong></div>
 <div class="detail-metric"><label>Pendiente SMA21 (3r)</label><strong class="${d.sma21_slope_pct3<0?'sma21-down':'sma21-up'}">${d.sma21_slope_pct3==null?'—':fmt(d.sma21_slope_pct3)+'%'}</strong></div>
 <div class="detail-metric"><label>RSI14 · Δ 3 ruedas</label><strong class="${d.rsi_delta3<0?'sma21-down':'sma21-up'}">${d.rsi_delta3==null?'—':fmt(d.rsi_delta3)+' pts'}</strong></div>
 <div class="detail-metric"><label>MACD hist. · Δ 3r</label><strong class="${d.macd_delta3_pct<0?'sma21-down':'sma21-up'}">${d.macd_delta3_pct==null?'—':fmt(d.macd_delta3_pct)+'% del precio'}</strong></div><div class="detail-metric"><label>SMA20 · USD</label><strong>${usd(d.ma20)}</strong></div><div class="detail-metric"><label>SMA50 · USD</label><strong>${usd(d.ma50)}</strong></div><div class="detail-metric"><label>SMA200 · USD</label><strong>${usd(d.ma200)}</strong></div><div class="detail-metric"><label>RSI14 diario</label><strong>${fmt(d.rsi14d)}</strong></div><div class="detail-metric"><label>MACD hist. D</label><strong>${fmt(d.macd_hist_d)}</strong></div><div class="detail-metric"><label>RSI21 semanal</label><strong>${fmt(d.rsi21w)}</strong></div><div class="detail-metric"><label>RSI21 mensual</label><strong>${fmt(d.rsi21m)}</strong></div><div class="detail-metric"><label>ADX14 diario</label><strong>${fmt(d.adx14)}</strong></div><div class="detail-metric"><label>RS vs SPY (20r)</label><strong>${d.rs_spy20==null?'—':fmt(d.rs_spy20)+' pp'}</strong></div><div class="detail-metric"><label>RS vs QQQ (20r)</label><strong>${d.rs_qqq20==null?'—':fmt(d.rs_qqq20)+' pp'}</strong></div><div class="detail-metric"><label>Volumen confirmado</label><strong>${fmt(d.volume_confirm_score)}/100</strong></div><div class="detail-metric"><label>RVOL20</label><strong>${fmt(d.rvol20)}x</strong></div><div class="detail-metric"><label>Volumen 20r USD</label><strong>${d.dollar_volume20==null?'—':usd(d.dollar_volume20)}</strong></div><div class="detail-metric"><label>OBV (10 ruedas)</label><strong>${d.obv_up10==null?'—':d.obv_up10?'Confirmando':'Sin confirmar'}</strong></div><div class="detail-metric"><label>Extensión / ATR14</label><strong>${fmt(d.stretch_atr20)} ATR</strong></div></div>
 <div class="detail-section"><h3>Por qué aparece esta señal</h3><ul>${what.map(t=>`<li>${esc(t)}</li>`).join('')}</ul></div>
 <div class="detail-section"><h3>Plan informativo / control de riesgo</h3><p>${esc(plan)}</p><div class="detail-metrics"><div class="detail-metric"><label>Nivel de referencia / soporte</label><strong>${usd(d.ma20)}</strong></div><div class="detail-metric"><label>Invalidación de referencia</label><strong>${usd(d.invalid_usd)}</strong></div><div class="detail-metric" style="grid-column:span 2"><label>Objetivos hipotéticos desde cierre USD</label><strong>${esc(objective)}</strong></div></div><p class="muted">La invalidación es aproximada: revisar estructura 4H/diaria y catalizadores. Los objetivos R son escenarios, no pronósticos.</p></div>
 ${candidateInfo} ${spectral?spectrumInfo:penaltyInfo} ${atrInfo} ${balanceInfo} ${riskPlan} ${riskNote}<p class="muted" style="font-size:11px">Calidad: último cierre USD ${day(d.date)} · Macroeconomía: ${esc(dataset.macro?.state||'NO VERIFICADO')} · fuente: Yahoo/yfinance.</p>
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
function linePaper(points, fills=[], initial=2000){
 const finite=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v));
 const dateKey=v=>/^\d{4}-\d{2}-\d{2}/.test(String(v))?String(v).slice(0,10):'';
 const byDay=new Map();
 for(const p of points||[]){const date=dateKey(p?.date);if(date&&finite(p.equity))byDay.set(date,{...p,date,equity:Number(p.equity)});}
 const a=[...byDay.values()].sort((x,y)=>x.date.localeCompare(y.date));
 if(a.length<2)return '<p class="muted">La curva del patrimonio aparecerá con los próximos cierres registrados.</p>';
 initial=finite(initial)&&Number(initial)>0?Number(initial):2000;
 const money=(v,dec=2)=>'US$ '+Number(v).toLocaleString('es-AR',{minimumFractionDigits:0,maximumFractionDigits:dec});
 const signed=v=>(v<0?'−':v>0?'+':'')+money(Math.abs(v));
 const shortDate=s=>{const [y,m,d]=s.split('-');return d+'/'+m+(a[0].date.slice(0,4)!==a.at(-1).date.slice(0,4)?'/'+y.slice(2):'');};
 const eventName=v=>String(v||'').replace(/COMPRA\s+\d+\s*\/\s*\d+/gi,'COMPRA');
 const events=new Map();
 for(const f of fills||[]){const k=dateKey(f.date);if(!events.has(k))events.set(k,[]);events.get(k).push(f);}
 const values=[initial,...a.map(p=>p.equity)],min=Math.min(...values),max=Math.max(...values);
 const margin=Math.max(initial*.01,(max-min)*.12,1);
 const nice=v=>{const n=10**Math.floor(Math.log10(v));return [1,2,2.5,5,10].find(k=>k*n>=v-1e-10)*n;};
 let step=nice((max-min+2*margin)/4),lo=Math.floor((min-margin)/step)*step;
 while(lo+4*step<max+margin){step=nice(step*1.01);lo=Math.floor((min-margin)/step)*step;}
 const hi=lo+4*step,dec=step<1?Math.min(6,Math.ceil(-Math.log10(step))+1):0;
 const W=900,H=330,L=115,R=740,T=45,B=250;
 const xx=i=>L+i*(R-L)/(a.length-1),yy=v=>B-(v-lo)/(hi-lo)*(B-T);
 const num=v=>Number(v).toFixed(2);
 const titleAt=p=>{
   const ops=(events.get(p.date)||[]).map(f=>eventName(f.action)+' · '+(finite(f.shares)?Number(f.shares).toLocaleString('es-AR',{maximumFractionDigits:6}):'—')+' acc. · '+(finite(f.amount_usd)?money(f.amount_usd):'monto no informado'));
   return shortDate(p.date)+' · Patrimonio '+money(p.equity)+' · Efectivo '+(finite(p.cash)?money(p.cash):'no informado')+' · Diferencia '+signed(p.equity-initial)+' · '+(ops.length?ops.join('; '):'Sin operaciones');
 };
 let svg=`<svg class="paper-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Patrimonio simulado por rueda, con referencia al capital inicial"><title>${esc('Patrimonio simulado · '+shortDate(a[0].date)+' a '+shortDate(a.at(-1).date))}</title>`;
 svg+='<text x="16" y="22" fill="#b7cbdc" font-size="13">Patrimonio (US$)</text>';
 for(let i=0;i<5;i++){const v=lo+i*step,y=num(yy(v));svg+=`<line x1="${L}" y1="${y}" x2="${R}" y2="${y}" stroke="#2a3b50"/><text x="${L-12}" y="${num(yy(v)+4)}" text-anchor="end" fill="#9eb4c9" font-size="12">${esc(money(v,dec))}</text>`;}
 const ticks=new Set(Array.from({length:Math.min(7,a.length)},(_,i)=>Math.round(i*(a.length-1)/(Math.min(7,a.length)-1))));
 for(const i of ticks){svg+=`<line x1="${num(xx(i))}" y1="${B}" x2="${num(xx(i))}" y2="${B+6}" stroke="#76899d"/><text x="${num(xx(i))}" y="${B+25}" text-anchor="middle" fill="#9eb4c9" font-size="12">${esc(shortDate(a[i].date))}</text>`;}
 svg+=`<text x="${(L+R)/2}" y="310" text-anchor="middle" fill="#b7cbdc" font-size="13">Rueda (fecha)</text><line x1="${L}" y1="${num(yy(initial))}" x2="${R}" y2="${num(yy(initial))}" stroke="#b9c8d6" stroke-dasharray="6 5"/><text x="${L+8}" y="${num(yy(initial)-12)}" fill="#d4e0eb" font-size="12">${esc('Capital inicial '+money(initial))}</text>`;
 const segment=(x1,y1,x2,y2,color)=>`<path d="M${num(x1)} ${num(yy(y1))} L${num(x2)} ${num(yy(y2))}" stroke="${color}" stroke-width="2.8" fill="none"/>`;
 for(let i=1;i<a.length;i++){
   const v=a[i-1].equity,w=a[i].equity,x=xx(i-1),z=xx(i);
   if((v-initial)*(w-initial)<0){const cross=x+(initial-v)*(z-x)/(w-v);svg+=segment(x,v,cross,initial,v>=initial?'#48d7bd':'#f27b80')+segment(cross,initial,z,w,w>=initial?'#48d7bd':'#f27b80');}
   else svg+=segment(x,v,z,w,(v+w)/2>=initial?'#48d7bd':'#f27b80');
 }
 for(let i=0;i<a.length;i++){
   const p=a[i],x=xx(i),y=yy(p.equity),title=esc(titleAt(p));
   svg+=`<circle cx="${num(x)}" cy="${num(y)}" r="4" fill="${p.equity>=initial?'#48d7bd':'#f27b80'}" tabindex="0"><title>${title}</title></circle>`;
   const types=[...new Set((events.get(p.date)||[]).map(f=>String(f.action).includes('STOP')?'stop':String(f.action).startsWith('COMPRA')?'buy':'sell'))];
   types.forEach((type,j)=>{const dx=x+(j-(types.length-1)/2)*15,dy=y+18;
     const shape=type==='stop'?`<rect x="${num(dx-4)}" y="${num(dy-4)}" width="8" height="8" fill="#f6c16b">`:type==='buy'?`<path d="M${num(dx)} ${num(dy-5)} l5 9 h-10 Z" fill="#48d7bd">`:`<path d="M${num(dx)} ${num(dy+5)} l5 -9 h-10 Z" fill="#f27b80">`;
     svg+=shape+`<title>${title}</title>`+(type==='stop'?'</rect>':'</path>');});
 }
 const last=a.at(-1);
 svg+=`<text x="${R+12}" y="${num(yy(last.equity)+4)}" fill="${last.equity>=initial?'#48d7bd':'#f27b80'}" font-size="14" font-weight="700">${esc(money(last.equity))}</text></svg>`;
 return '<div class="paper-chart-scroll">'+svg+'</div><div class="paper-legend"><span>┄ Capital inicial</span><span class="sma21-up">▲ Compra · patrimonio sobre el inicial</span><span class="sma21-down">▼ Venta · patrimonio bajo el inicial</span><span>■ Stop loss</span></div><p class="paper-graph-caption">'+esc('De '+shortDate(a[0].date)+' a '+shortDate(last.date)+' · Patrimonio final '+money(last.equity)+' · Variación '+signed(last.equity-initial))+'</p>';
}
function renderPaper(){
 const root=$('paperStatus');
 if(!paper){root.className='paper-status paper-warn';root.textContent='Todavía no hay ledger simulado publicado, o no se pudo recuperar el archivo. No inventamos operaciones.';return;}
 const p=paper, pos=p.open_positions||[], closed=[...(p.closed_trades||[])].reverse(),fills=[...(p.fills||[])].reverse();
 const valid=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v));
 const money=v=>valid(v)?'US$ '+Number(v).toLocaleString('es-AR',{minimumFractionDigits:0,maximumFractionDigits:2}):'—';
 const signed=v=>valid(v)?(v<0?'−':v>0?'+':'')+money(Math.abs(v)):'—';
 const pct=v=>valid(v)?(v<0?'−':v>0?'+':'')+Math.abs(v).toLocaleString('es-AR',{maximumFractionDigits:2})+'%':'—';
 const qty=v=>valid(v)?Number(v).toLocaleString('es-AR',{maximumFractionDigits:6}):'—';
 const num=v=>valid(v)?Number(v):null;
 const sum=(arr,fn)=>arr.reduce((n,x)=>n+(num(fn(x))??0),0);
 const ratio=(a,b)=>valid(a)&&valid(b)&&b>0?100*a/b:null;
 const color=v=>!valid(v)?'':v>=0?'sma21-up':'sma21-down';
 const clean=v=>String(v||'').replace(/COMPRA\s+\d+\s*\/\s*\d+/gi,'COMPRA').replace(/AGREGAR TRAMO/gi,'AGREGAR ACCIONES').replace(/\bTRAMOS?\b/gi,'partes');
 const sub=t=>`<span class="ticker-sub">${esc(t)}</span>`;
 const td=(v,cls='')=>`<td class="paper-num ${cls}">${esc(v)}</td>`;
 const date=v=>esc(day(v));
 const period=(a,b)=>{const short=v=>/^\d{4}-\d{2}-\d{2}$/.test(String(v))?String(v).slice(8,10)+'/'+String(v).slice(5,7)+(String(a).slice(0,4)!==String(b).slice(0,4)?'/'+String(v).slice(2,4):''):'—';return esc(short(a)+' → '+short(b));};
 const initial=num(p.initial_capital_usd)??2000,equity=num(p.equity_usd),cash=num(p.cash_usd);
 const invested=sum(pos,x=>x.market_value_usd),cost=sum(pos,x=>valid(x.shares)&&valid(x.avg_cost_usd)?x.shares*x.avg_cost_usd:null),floating=sum(pos,x=>x.unrealized_usd);
 const result=equity===null?null:equity-initial, n=Number(p.closed_count)||0, partial=Number(p.partial_exit_count)||0;
 const outdated=Date.now()-Date.parse((p.last_closed_session||'')+'T23:59:59Z')>6*86400000;
 root.className='paper-status'+(outdated?' paper-warn':'');
 root.textContent=(outdated?'Registro con último cierre antiguo. ':'')+'Cartera 100% ficticia · se ejecuta al OPEN siguiente · no son órdenes reales';
 $('paperCut').textContent='Última rueda registrada: '+day(p.last_closed_session);
 $('paperEquity').textContent=money(equity);$('paperEquitySub').textContent='Capital inicial '+money(initial);
 $('paperCash').textContent=money(cash);$('paperCashSub').textContent=(equity>0?fmt(ratio(cash,equity))+'%':'—')+' del patrimonio';
 $('paperInvested').textContent=money(invested);$('paperInvestedSub').textContent=pos.length+' posiciones · '+(equity>0?fmt(ratio(invested,equity))+'%':'—')+' del patrimonio';
 $('paperReturn').textContent=signed(result)+' ('+pct(p.return_pct)+')';$('paperReturn').className=color(result);
 $('paperReturnSub').textContent='Realizado '+signed(p.realized_pnl_usd)+' · Flotante '+signed(floating);
 $('paperTrades').textContent=n+' '+(n===1?'cerrada':'cerradas')+' · '+partial+' '+(partial===1?'parcial':'parciales');
 $('paperTradesSub').textContent=n>=10&&valid(p.win_rate_pct)?'Acierto '+fmt(p.win_rate_pct)+'%':'sin dato útil todavía (hay '+n+' de 10)';
 $('paperDD').textContent=pct(p.max_drawdown_pct);
 $('paperGraph').innerHTML=linePaper(p.equity_history||[],p.fills||[],initial);
 const waiting=p.pending_orders||[];
 $('paperPending').innerHTML=waiting.length?waiting.map(x=>{
   let action;
   if(x.side==='BUY'){
     const weight=[.40,.35,.25][Number(x.tranche)-1];
     action=valid(x.budget)&&weight!==undefined?'COMPRA · hasta '+money(Number(x.budget)*weight):'COMPRA · importe no informado';
   }else{
     const position=pos.find(a=>a.usa===x.usa),fraction=Number(x.fraction??1);
     action=(fraction<1?'VENTA PARCIAL '+qty(fraction*100)+'%':'VENTA TOTAL')+' · '+(position&&valid(position.shares)&&fraction>0&&fraction<=1?'≈ '+qty(position.shares*fraction)+' acc.':'cantidad no informada');
   }
   return `<tr><td>${date(x.issued_day)}</td><td>${esc(x.ticker||x.usa)}</td><td>${esc(action)}</td><td>${esc(clean(x.reason))}</td></tr>`;
 }).join(''):'<tr><td colspan="4">Sin órdenes pendientes para la próxima apertura.</td></tr>';
 $('paperPositions').innerHTML=pos.length?pos.map(x=>{
   const c=valid(x.shares)&&valid(x.avg_cost_usd)?x.shares*x.avg_cost_usd:null, r=ratio(x.unrealized_usd,c),distance=valid(x.stop_usd)&&x.last_price_usd>0?100*(x.stop_usd/x.last_price_usd-1):null;
   return `<tr><td>${esc(x.ticker||x.usa)}${sub(x.usa)}</td>${td(qty(x.shares))}${td(money(x.avg_cost_usd))}${td(money(x.last_price_usd))}${td(money(x.market_value_usd))}${td(valid(ratio(x.market_value_usd,equity))?fmt(ratio(x.market_value_usd,equity))+'%':'—')}<td class="paper-num ${color(x.unrealized_usd)}">${esc(signed(x.unrealized_usd))}${sub(pct(r))}</td><td class="paper-num">${esc(money(x.stop_usd))}${sub(pct(distance)+' al último · '+(x.risk_mode||'No informado'))}</td><td>${date(x.entry_date)}${sub((x.sessions_held??'—')+' ruedas')}</td></tr>`;
 }).join('')+`<tr class="paper-totals"><th scope="row">Totales</th><td></td><td class="paper-num" colspan="2">${esc('Costo '+money(cost))}</td>${td(money(invested))}${td(equity>0?fmt(ratio(invested,equity))+'%':'—')}${td(signed(floating),color(floating))}<td colspan="2"></td></tr>`:'<tr><td colspan="9">Sin posiciones abiertas. El efectivo queda en reserva mientras no aparezcan condiciones.</td></tr>';
 $('paperClosed').innerHTML=closed.length?closed.map(x=>`<tr><td>${esc(x.ticker||x.usa||'—')}</td><td>${period(x.entry_date,x.exit_date)}${sub((x.holding_sessions??'—')+' ruedas')}</td>${td(qty(x.shares))}${td(money(x.cost_usd))}<td class="paper-num">${esc(money(x.exit_usd))}${sub('por acción')}</td><td class="paper-num ${color(x.pnl_usd)}">${esc(signed(x.pnl_usd))}${sub(pct(x.return_pct))}</td><td><strong>${esc(x.partial?'PARCIAL '+qty(x.exit_fraction_pct)+'%':'FINAL')}</strong>${sub(clean(x.reason))}</td></tr>`).join(''):'<tr><td colspan="7">Todavía no hubo salidas parciales ni finales simuladas.</td></tr>';
 $('paperFills').innerHTML=fills.length?fills.map(x=>`<tr><td>${date(x.date)}</td><td>${esc(x.usa)}</td><td><span class="pill ${String(x.action).includes('STOP')?'down':String(x.action).startsWith('COMPRA')?'up':'hold'}">${esc(clean(x.action))}</span></td>${td(qty(x.shares))}${td(money(x.price_usd))}${td(money(x.amount_usd))}<td>${esc(clean(x.reason))}</td></tr>`).join(''):'<tr><td colspan="7">Sin operaciones: todavía no hay compras ni ventas ejecutadas en la simulación.</td></tr>';
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

async function load(){dataset=baseline();const engine=new URLSearchParams(location.search).get('engine');const preview=['spectrum','intraday'].includes(engine);try{const r=await fetch((engine==='intraday'?'./data-intraday.json?refresh=':preview?'./data-spectrum.json?refresh=':'./data.json?refresh=')+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const j=await r.json();if(!Array.isArray(j.assets)||!Array.isArray(j.sectors))throw new Error('Formato inválido');
 // Si falla GitHub Actions y el sitio quedó con datos de una ejecución vieja,
 // se BLOQUEAN las señales de compra/venta, no alcanza sólo con un aviso arriba.
 const stamp=Date.parse(j.meta?.generated_at_utc||'');
 const batchStale=!Number.isFinite(stamp)||(Date.now()-stamp)/3600000>36;
 const staleDate=d=>!d||!Number.isFinite(Date.parse(d+'T23:59:59Z'))||(Date.now()-Date.parse(d+'T23:59:59Z'))/86400000>5;
 for(const x of [...j.assets,...j.sectors]){
   if(batchStale||(j.meta?.provisional&&(!x.quote_at||Date.now()-Date.parse(x.quote_at)>75*60000))||(x.data&&staleDate(x.data.date))){
     x.signal='DATOS VIEJOS';x.tone='neutral';
     x.reasons=['Señal suspendida: falta una actualización reciente del mercado estadounidense. Revisar GitHub Actions y fecha de cierre USA.'];
   }
 }
 if(j.meta?.provisional)j.top5=(j.top5||[]).filter(t=>j.assets.some(x=>x.ticker===t.ticker&&x.signal!=='DATOS VIEJOS'));
 if(batchStale||j.assets.every(x=>x.data&&staleDate(x.data.date))){j.top5=[];j.rebounds=[];}
 dataset=j;}catch(e){$('criticalBanner').textContent='Sin datos. Si abriste el archivo local, publicalo en GitHub Pages. Error de lectura: '+e.message;}fillFilters();renderHeader();renderTop5();renderAssets();renderRebounds();renderSectors();renderTracked();document.querySelector('main')?.setAttribute('aria-busy','false');if(preview){$('criticalBanner').textContent=(dataset.meta?.unavailable?'Sin observación intradía válida en este horario. ':engine==='intraday'?'PROVISORIO · última barra horaria cerrada; vela diaria en formación. ':'')+'CANDIDATO ESPECTRAL · sin activar. El track record pertenece al motor vigente.';}}
for(const el of document.querySelectorAll('.tab'))el.onclick=()=>setTab(el.dataset.tab);
for(const id of ['searchInput','sectorFilter','signalFilter','sortFilter'])$(id).addEventListener(id==='searchInput'?'input':'change',renderAssets);
$('modalClose').onclick=()=>$('detailModal').close();$('detailModal').addEventListener('click',e=>{if(e.target===$('detailModal'))$('detailModal').close()});
load();
loadPaper();

async function loadSignalQuality(){
 const root=$('signalQuality');if(!root)return;
 try{const response=await fetch('./signal-quality.json?refresh='+Date.now(),{cache:'no-store'});if(!response.ok)throw new Error('Sin registro');const data=await response.json();
 root.innerHTML='<p>Registro iniciado: '+esc(data.started_at)+'. Medición independiente del capital invertido.</p><div class="tablebox"><table><thead><tr><th>Motor</th><th>Ruedas</th><th>Maduras / pendientes</th><th>Retorno</th><th>Exceso vs SPY</th><th>R medio</th></tr></thead><tbody>'+Object.entries(data.summaries||{}).flatMap(([engine,hs])=>Object.entries(hs).map(([h,v])=>'<tr><td>'+esc(engine)+'</td><td>'+esc(h)+'</td><td>'+esc(v.matured)+' / '+esc(v.pending)+'</td><td>'+esc(fmt(v.return))+'%</td><td>'+esc(fmt(v.excess_spy))+' pp</td><td>'+esc(fmt(v.r))+'</td></tr>')).join('')+'</tbody></table></div><p>'+esc(data.note)+'</p>';
 }catch(e){root.textContent='Medición todavía no disponible. No se inventan señales históricas ni se muestra 0% como resultado.';}
}
loadSignalQuality();
