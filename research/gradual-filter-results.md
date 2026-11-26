# Filtros graduales — comparación del 26/11/2026

Estado: candidato 2.1 preparado, NO activado. Referencia: 2.0-unified-decision-active.

Mismo score y mismo tamaño de riesgo; cambia la elegibilidad técnica. No se optimizaron parámetros. Datos almacenados: 2021-11-17 a 2026-11-17.

| Métrica | Vigente | Gradual |
|---|---:|---:|
| Señales nuevas | 114.000 | 239.000 |
| Operaciones completas | 78.000 | 139.000 |
| Acierto (%) | 48.718 | 48.921 |
| R promedio | 0.651 | 0.464 |
| Peor drawdown individual (%) | -2.433 | -3.895 |
| Peor racha individual | 5.000 | 5.000 |

## Dispersión por activo

| Activo | Operaciones actual / gradual | R medio actual / gradual |
|---|---:|---:|
| AMZN | 10 / 18 | 0.235 / -0.080 |
| COPX | 10 / 15 | 0.509 / 0.791 |
| GOOGL | 4 / 17 | -0.419 / 0.089 |
| IREN | 13 / 18 | 1.974 / 1.196 |
| JPM | 3 / 12 | -0.268 / 0.600 |
| META | 5 / 9 | 0.526 / 0.491 |
| MSFT | 2 / 5 | 1.728 / 1.082 |
| NVDA | 9 / 13 | 0.358 / 0.183 |
| TGT | 10 / 12 | 0.180 / 0.491 |
| TQQQ | 12 / 20 | 0.755 / 0.285 |

## Lectura y límites

La flexibilización más que duplica las señales. Conserva acierto parecido, pero disminuye el R medio y aumenta la peor caída individual. No se promueve automáticamente; la decisión de aceptar más actividad a cambio de esos resultados queda explícita. No demuestra una mejora estadística.

Diez activos de conveniencia, sesgo de supervivencia, incluye ETF apalancado. Ensayo de ENTRADAS con salidas homogéneas 2ATR/20 ruedas; no replica salidas REDUCIR/SALIR ni cartera multiactivo del simulador. Entrada t+1; 5bp comisión y 10bp slippage por lado. Riesgo nominal 0,5%, máximo 50% por cartera individual. Las ventanas sin 20 ruedas completas quedan fuera de la estadística de operaciones, incluso si ya tocaron stop. El drawdown es de carteras individuales, NO agregado. No hay balances históricos ni costos BYMA/CCL. La muestra ya fue examinada y NO es fuera de muestra.

## Reproducir

```bash
OPENBLAS_NUM_THREADS=1 python research/run_gradual_study.py --market /ruta/market-cache --out /tmp/gradual-study
python -m unittest discover -s tests -v
npm test
node --check docs/app.js
```

El protocolo previo está en `gradual-filter-protocol.md`. Los datos y los CSV de resultados no se agregan al repositorio. Se conserva referencia 2.0 en `reference_decision_v2.py` solo para investigación; la web tiene un único motor.

Tests actualizados intencionalmente: un MACD negativo verificado y OBV descendente ya no prueban un veto duro; se reemplazan por ausencia de dato para conservar la prueba de integridad. Nuevos tests verifican precaución, umbral 70, score cero, salidas estructurales, timing y controles de riesgo.
