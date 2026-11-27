const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('docs/app.js','utf8');
const fixture={is_simulated:true,initial_capital_usd:2000,equity_usd:1996.06,cash_usd:1896.06,return_pct:-.197,
 realized_pnl_usd:-2,max_drawdown_pct:-.197,closed_count:1,partial_exit_count:1,win_rate_pct:0,last_closed_session:'2026-11-19',
 equity_history:[{date:'2026-11-16',equity:2000,cash:2000},{date:'2026-11-17',equity:1999.2,cash:1899.2},{date:'2026-11-18',equity:1997.8,cash:1897.8},{date:'2026-11-19',equity:1996.06,cash:1896.06}],
 open_positions:[{ticker:'AAA',usa:'AAA',sector:'Tech',entry_date:'2026-11-17',shares:2,avg_cost_usd:51.0,last_price_usd:50,market_value_usd:100,unrealized_usd:-2,stop_usd:47,stop_pct:8,risk_mode:'NORMAL',sessions_held:2}],
 closed_trades:[{usa:'BBB',entry_date:'2026-11-17',exit_date:'2026-11-19',holding_sessions:2,shares:1.5,cost_usd:90,exit_usd:59,pnl_usd:-1.5,return_pct:-1.667,partial:false,exit_fraction_pct:100,reason:'SALIR <img src=x>'}],
 fills:[{date:'2026-11-17',usa:'AAA',action:'COMPRA 1/3',price_usd:51,shares:2,amount_usd:102,reason:'COMPRA 1/3'},
 {date:'2026-11-18',usa:'BBB',action:'VENTA PARCIAL',price_usd:59,shares:.5,amount_usd:29.5,reason:'REDUCIR'},
 {date:'2026-11-19',usa:'BBB',action:'STOP LOSS',price_usd:59,shares:1,amount_usd:59,reason:'STOP'}],
 pending_orders:[{side:'BUY',usa:'CCC',ticker:'CCC',tranche:2,budget:250,issued_day:'2026-11-19',reason:'AGREGAR TRAMO <script>'},
 {side:'SELL',usa:'AAA',ticker:'AAA',fraction:.5,issued_day:'2026-11-19',reason:'REDUCIR'},
 {side:'SELL',usa:'AAA',fraction:1,issued_day:'2026-11-19',reason:'SALIR'},
 {side:'BUY',usa:'AAA',tranche:3,issued_day:'2026-11-19',reason:'AGREGAR TRAMO'}]};
function context(src,p=fixture){
 const nodes={};const ctx={paper:p,Intl,Date,Map,Set,Number,Math,console,$:id=>nodes[id]??=( {innerHTML:'',textContent:'',className:''})};
 const helpers=src.split('\n').filter(x=>/^const (esc|usd|fmt|day|signedUsd|signedPct)=/.test(x)).join('\n');
 vm.createContext(ctx);vm.runInContext(helpers+'\n'+src.slice(src.indexOf('function linePaper('),src.indexOf('async function loadPaper()')),ctx);return {ctx,nodes};
}
const {ctx,nodes}=context(source);vm.runInContext('renderPaper()',ctx);
const graph=nodes.paperGraph.innerHTML;
assert(graph.includes('Patrimonio (US$)')&&graph.includes('Rueda (fecha)'));
assert(graph.includes('US$ 2.000')&&graph.includes('US$ 1.996,06'));
assert(graph.includes('16/11')&&graph.includes('19/11'));
assert(graph.includes('stroke-dasharray')&&graph.includes('Efectivo'));
assert(graph.includes('▲ Compra')&&graph.includes('▼ Venta')&&graph.includes('■ Stop'));
assert(graph.includes('stroke="#f27b80"'));
assert(!graph.includes('NaN')&&!graph.includes('Infinity'));
for(const id of ['paperPending','paperPositions','paperClosed','paperFills']){
 assert(!/Tramos|COMPRA \d\/\d|undefined|<script>|<img/i.test(nodes[id].innerHTML),id);
}
assert(nodes.paperPending.innerHTML.includes('COMPRA · hasta US$ 87,5'));
assert(nodes.paperPending.innerHTML.includes('VENTA PARCIAL 50% · ≈ 1 acc.'));
assert(nodes.paperPending.innerHTML.includes('VENTA TOTAL · ≈ 2 acc.'));
assert(nodes.paperPending.innerHTML.includes('importe no informado'));
assert(nodes.paperPending.innerHTML.includes('&lt;script&gt;'));
assert(nodes.paperTradesSub.textContent.includes('hay 1 de 10'));
assert(!nodes.paperTradesSub.textContent.includes('Acierto'));
assert.strictEqual(nodes.paperInvested.textContent,'US$ 100');
assert(nodes.paperPositions.innerHTML.includes('Costo US$ 102'));
assert(nodes.paperClosed.innerHTML.includes('17/11 → 19/11'));
assert(nodes.paperReturn.textContent.includes('−US$ 3,94'));
ctx.paper={...fixture,closed_count:10,win_rate_pct:60};vm.runInContext('renderPaper()',ctx);assert(nodes.paperTradesSub.textContent.includes('Acierto 60%'));
assert(vm.runInContext('linePaper([])',ctx).includes('próximos cierres'));
const cross=vm.runInContext("linePaper([{date:'2026-12-31',equity:1999,cash:1900},{date:'2027-01-04',equity:2001,cash:1900}],[],2000)",ctx);
assert(cross.includes('31/12/26')&&cross.includes('04/01/27'));
assert(cross.includes('stroke="#48d7bd"')&&cross.includes('stroke="#f27b80"'));
const empty=context(source,{...fixture,open_positions:[],pending_orders:[],closed_trades:[],fills:[]});vm.runInContext('renderPaper()',empty.ctx);assert(empty.nodes.paperPositions.innerHTML.includes('Sin posiciones'));
if(process.argv[2]){
 fs.mkdirSync(process.argv[2],{recursive:true});
 const before=context(fs.readFileSync('/tmp/track-before/app.js','utf8'));
 const old=vm.runInContext('linePaper(paper.equity_history)',before.ctx);
 fs.writeFileSync(process.argv[2]+'/before.html',old);fs.writeFileSync(process.argv[2]+'/after.html',graph);fs.writeFileSync(process.argv[2]+'/fixture.json',JSON.stringify(fixture,null,2));
}
console.log('Track presentation: rendering, quantities, bounds, dates, escaping, empty states and 10-close gate OK');

const intraday={...fixture,execution_mode:'paper-15m-v1',observed_at:'2026-11-27T16:37:00Z',valued_at:'2026-11-27T16:30:00Z',intraday_status:'Velas recientes disponibles',unpriced_symbols:[],intraday_equity:[{date:'2026-11-27T16:00:00Z',equity:2000,cash:1900},{date:'2026-11-27T16:30:00Z',equity:2001,cash:1900}],fills:[{...fixture.fills[0],timestamp:'2026-11-27T16:15:00Z',date:'2026-11-27'}]};
const live=context(source,intraday);vm.runInContext('renderPaper()',live.ctx);
assert(live.nodes.paperStatus.textContent.includes('señal diaria'));
assert(live.nodes.paperCut.textContent.includes('Hora ARG'));
assert(live.nodes.paperIntradayGraph.innerHTML.includes('Fecha y hora ARG'));
assert(live.nodes.paperIntradayGraph.innerHTML.includes('13:00'));
assert(live.nodes.paperFills.innerHTML.includes('13:15'));
assert(!/NaN|undefined|Infinity/.test(live.nodes.paperIntradayGraph.innerHTML));
console.log('Intraday ledger UI: times, separate intraday curve and daily eligibility OK');
