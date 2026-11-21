# Revisión del radar — 21/11/2026

## Decisión: no promover el motor espectral todavía

Misma muestra histórica de 10 activos (AMZN, NVDA, MSFT, META, GOOGL, JPM, TGT, COPX, IREN y TQQQ), señales del 17/11/2021 al 17/11/2026. Son datos locales conservados del A/B anterior, no cotizaciones del 21/11/2026.

Esta comparación aísla las entradas: ambos motores usan ahora 2 ATR y salida por stop o al cierre de 20 ruedas. No equivale a cambiar el simulador de producción, ni compara las salidas REDUCIR/SALIR. Entrada t+1, costos 5 pb y slippage 10 pb por lado. Riesgo máximo nominal 0,5%, exposición máxima 50%, por cartera individual. No hay posiciones simultáneas del mismo ticker.

| Métrica | Vigente + ATR | Espectral + ATR |
|---|---:|---:|
| Señales nuevas (cambio a compra) | 114.000 | 880.000 |
| Operaciones maduras | 78.000 | 481.000 |
| Acierto (%) | 48.718 | 44.699 |
| R medio | 0.651 | 0.128 |
| Peor DD individual (%) | -2.433 | -7.359 |
| Peor racha individual | 5.000 | 10.000 |

El espectral genera más señales, pero el R medio cae, aumenta el drawdown y empeora la racha. No se lo activa en producción. El tamaño fijo de la cartera ocultaba movimientos en el saldo; al normalizar el riesgo, la debilidad del candidato persiste.

## Retorno de señal a plazo fijo, sin aplicar stop

| Motor | Ruedas | Maduras | Retorno medio (%) | Exceso vs SPY (pp) | R medio |
|---|---:|---:|---:|---:|---:|
| Vigente | 5 | 114 | 0.748 | 0.765 | 0.074 |
| Vigente | 10 | 114 | 1.719 | 1.414 | 0.188 |
| Vigente | 20 | 114 | 5.313 | 4.429 | 0.619 |
| Espectral | 5 | 879 | -0.016 | 0.140 | -0.006 |
| Espectral | 10 | 877 | 0.613 | 0.559 | 0.056 |
| Espectral | 20 | 870 | 2.239 | 1.373 | 0.235 |

Los eventos forward pueden solaparse y no son independientes. Una nueva señal es el primer día de un estado de compra; no se cuentan todos los días verdes como nuevas entradas. Las ventanas inmaduras se excluyen del promedio, incluso si ya alcanzaron el stop.

## Sensibilidad de stop en el espectral

| Stop | Operaciones | Acierto (%) | R medio | Peor DD individual (%) | Peor racha |
|---|---:|---:|---:|---:|---:|
| fixed6 | 504 | 39.683 | 0.137 | -9.494 | 11 |
| fixed8 | 467 | 44.111 | 0.124 | -6.901 | 8 |
| atr | 481 | 44.699 | 0.128 | -7.359 | 10 |

DD con marcas a cierre diario y fondos/proceeds de cada operación; no es drawdown agregado de una cartera multiactivo. El peor DD no necesariamente pertenece al ticker de la peor racha. Los gaps pueden superar 1R. No se ajustaron parámetros para favorecer resultados. Muestra de conveniencia, sesgo de supervivencia, incluye ETFs apalancados; sin calendario histórico de balances ni costos BYMA/CCL. Treinta señales maduras son un punto de partida descriptivo, no evidencia suficiente de ventaja estadística.

## Implementación preparada

- Motor de referencia integrado como candidato explícito; la configuración activa permanece `unified`. Comparador legado congelado en `decision_engine_legacy.py`.
- Vistas separadas por `?engine=active`, `?engine=spectrum`, `?engine=intraday`; el simulador sigue perteneciendo al motor vigente. No hay ejecución intradía en el ledger.
- R/retornos contra SPY en un registro forward independiente. Persistencia por caché; pérdida del caché inicia un registro nuevo con fecha y conteo explícitos, sin resetear el ledger.
- Barras horarias completas, máximo 75 minutos de antigüedad, secuencia desde apertura. Vela diaria provisoria y semana cerrada. No se extrapola el volumen; las medias diarias con volumen parcial siguen siendo experimentales.
- Nasdaq/Yahoo de balances conservados; precios horarios usan Yahoo y degradan a vista no disponible ante fallo. Sin validación en una rueda real de esta nueva vista; 21/11 es sábado.
- Gráfico de 90 ruedas, tarjetas móviles, textos derivados de configuración, humor al pie e indicador de carga.

## Reproducir con la muestra conservada

```bash
python scripts/study_baseline.py --readings /ruta/lecturas-diarias.csv --market /ruta/market-cache --out /tmp/baseline.csv
python scripts/signal_study.py --readings /tmp/baseline.csv --market /ruta/market-cache --out /tmp/study-active
python scripts/signal_study.py --readings /ruta/lecturas-diarias.csv --market /ruta/market-cache --out /tmp/study-spectral
python -m unittest discover -s tests -v
node tests/chart_presentation.cjs
```

El gráfico se valida ejecutando el SVG real en Node. El navegador local no pudo arrancar por restricción de sockets; no se afirma una revisión visual completa en Chromium.