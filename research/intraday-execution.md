# Ejecución intradiaria — paper-15m-v1

Autorización: el usuario aceptó el comparativo 2.1 y pidió más actividad durante la rueda. La señal diaria continúa siendo `2.1-gradual-confirmations`: no se calcula un segundo score ni se extrapola volumen parcial. Se cambia el reloj de ejecución y valuación del mismo libro simulado. No son órdenes a brokers.

- Corridas cada 30 minutos en ventana ampliada de mercado USA, con velas completas de 15 minutos (Yahoo). GitHub Actions y Yahoo pueden demorar: no es un servicio en tiempo real.
- Observación se fecha después de descargar datos. Una orden sólo se ejecuta en un OPEN estrictamente posterior a ese instante, y se registra al recibir la vela completa. Nunca se toma el open de la vela que ya estaba transcurriendo.
- Se conserva capital, posiciones y fills existentes. Una sola migración cierra el procesamiento diario pendiente y luego evita reejecutarlo. Las órdenes pendientes se revalidan/re-fechan; no se atribuyen operaciones intradiarias anteriores a la activación.
- Stops existentes se procesan con lows de velas completas y gaps adversos. El trailing conserva la actualización por cierre diario. La hora del stop es el cierre de la ventana que lo contiene, no el instante exacto desconocido.
- Se mantienen reservas, comisiones, slippage, límites sectoriales, presupuestos y tres tramos. Máximo una compra por activo y rueda; no se recompra en el mismo día después de salir. El pedido de mayor frecuencia no autoriza aumentar riesgo ni forzar rotación.
- Elegibilidad y contexto macro siguen al último cierre diario. Se requiere SPY intradiario reciente y barra sincronizada del activo para generar nuevas órdenes. No se usan precios parciales para crear otro motor.
- Símbolos descargados: posiciones abiertas, órdenes pendientes y hasta 20 candidatos elegibles. Una interrupción de barras bloquea el avance del símbolo; una fuente caída no reinicia el ledger ni inventa valuaciones.
- Misma persistencia en artefactos de Actions; metadata separa versión de decisión y versión de ejecución. No hay otra cartera ni saldo inicial nuevo.
- Curva histórica conservada y nueva curva por corte intradiario; marcas no verificadas se informan. El máximo drawdown refleja las valuaciones registradas, no todos los ticks.

Validación de ejecución: migración sin backfill, barras cerradas, timestamps posteriores a señal, no duplicación, gaps, feeds ausentes, cotizaciones antiguas, señal diaria verificable y conservación de capital. No se presenta un rendimiento histórico intradiario: el ensayo previo de entradas usa velas diarias y no demuestra una ventaja de ejecutar en 15 minutos. La nueva ejecución se evalúa forward desde su activación.
