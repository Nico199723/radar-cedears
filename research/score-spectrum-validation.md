# Un único motor con lectura gradual

Estado: historial y presentación activos; propuestas de reglas NO activas.
Referencia: `2.0-unified-decision-active`. El historial no alimenta decisiones ni paper.

## Arquitectura

1. Fortaleza: usar el score de decisión existente (0–100), no otra suma de indicadores.
2. Evolución: cambio observado del mismo score; no añade puntos ni habilita compras.
3. Timing: la señal y el gatillo del motor vigente, separados de la fortaleza.
4. Riesgo: tamaño según capital, volatilidad y concentración; no adulterar el score por liquidez personal.
5. Calidad: desconocido no equivale a malo ni a cero. Mantener filtros de integridad de datos.

La presentación no convierte un veto actual en una penalización. Suavizar restricciones técnicas requiere comparar resultados antes de cambiar producción. No activar el antiguo candidato espectral: en la muestra disponible aumentó actividad y empeoró calidad.

## Experimentos propuestos, uno por vez

- **Calibración:** agrupar el score de entrada en bandas predefinidas de 10 puntos, publicar cantidad, retorno neto mediano/medio y exceso vs SPY/QQQ a 5/10/20 ruedas. No presentar probabilidades sin calibración fuera de muestra. Controlar observaciones superpuestas y concentración por activo.
- **Timing:** vigente vs exigir gatillo aun con score >= PRIORITY_FLOOR. Mismos stops, tamaño, universo y costos. No variar umbrales simultáneamente.
- **Confirmaciones:** quitar solo veto de OBV; en una prueba separada quitar solo veto de MACD semanal. No agregar puntos compensatorios. Preservar vigencia y verificabilidad; documentar luego si conviene una penalización gradual en vez del veto.
- **Volatilidad:** con entradas idénticas, comparar política vigente vs distancia técnica/ATR y cantidad ajustada a riesgo monetario igual. Dos ATR es hipótesis, no parámetro validado. Reportar gaps y pérdidas superiores a 1R.
- **Concentración:** comparar carteras agregadas con igual presupuesto de riesgo, límite por grupo correlacionado estimado con datos anteriores a la operación y exposiciones observadas. No confundir sectores distintos con apuestas independientes.

## Puerta de promoción

Congelar protocolo antes del siguiente ensayo. Ejecución t+1, costos y deslizamiento explícitos, balances históricos cuando existan; declarar sus ausencias. Separar cronológicamente desarrollo, validación y tramo final intacto; purgar resultados superpuestos entre cortes. Validar también por activo y régimen. No elegir un ganador solo por acierto o R medio: publicar drawdown de cartera, peor racha, mediana, sensibilidad a outliers, exposición y retorno neto frente a benchmarks comparables. Un período ya revisado no vuelve a ser fuera de muestra.

No cambiar `rules_version` por modificaciones puramente visuales. Cada futura modificación de reglas debe tener su propia versión y comparación aprobada antes de promoverse. La historia conserva versiones y no conecta ni calcula variación entre metodologías distintas.

## Registro de puntajes

Persistencia en artefactos de Actions sin commits de datos. Cada archivo separa activos de proxies sectoriales. Hasta 90 registros recientes por serie, último corte por fecha de cierre y versión. No se reconstruyen scores con precios actuales. Los datos faltantes producen null; una fecha regresiva no reescribe el pasado. La restauración fallida o un artefacto expirado detiene la publicación para no reiniciar silenciosamente el historial. Retención de artefactos: 90 días desde cada corrida; más de 90 días sin actividad requiere backup externo.
