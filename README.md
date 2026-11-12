# RADAR CEDEARs — listo para GitHub Pages

**Sitio estático con actualización automática diaria a las 13:00 y 18:05 (hora Argentina).** Las señales se calculan **únicamente con los precios en USD del subyacente de EE. UU.**, no con el CEDEAR en pesos. No requiere Twelve Data ni cargar una API key.

## Qué vas a tener

- 271 instrumentos de un **catálogo curado** extraído del Dashboard de Cartera 2026, distribuidos en 17 sectores. **No es todavía la lista oficial completa de BYMA** (Caja de Valores indica más de 400). Al incorporarlos, se debe verificar el ticker de origen antes de permitir señales.
- 254 tickers con **mapeo candidato** a EE. UU. (que no garantiza histórico). El resto aparece **sin subyacente USA**, no se usa un ticker local por parecido.
- Cierres diarios USA en USD; SMA20/50/200, RSI14 diario, RSI21 semanal y mensual, MACD 12/26/9 diario y 6/13/5 semanal y mensual, ADX, ROC20 y volatilidad.
- Semáforo técnico: **COMPRA CONDICIONAL, VIGILAR COMPRA, MANTENER/ESPERAR, ESPERAR, REDUCIR/EVITAR y SALIR/EVITAR**, con invalidación y objetivos hipotéticos de 2R/3R cuando corresponda.
- Filtro de mercado SPY/QQQ/VIX. Si el mercado no habilita compras o faltan datos, no presenta nuevas compras.
- Watchlist local en el navegador. No se publican datos personales, saldos, PPC, cantidad de CEDEARs ni acceso a brokers.

**Límite honesto:** los 271 códigos no están cotejados uno a uno con la última planilla oficial de BYMA, y el sitio **no valida** ratio, liquidez, spread, resultados trimestrales o valuación fundamental. Es un primer filtro técnico, no un sistema autónomo de recomendaciones ejecutables. La fuente Yahoo Finance vía `yfinance` es gratuita pero **no oficial** y puede fallar. Si falla una ejecución, sigue publicada la anterior pero las señales quedan bloqueadas por antigüedad.

## Paso a paso para publicarlo en GitHub — sin programar

### A. Crear repositorio

1. Abrí https://github.com/new e iniciá sesión con tu cuenta.
2. En **Repository name**, escribí `radar-cedears`.
3. En **Visibility**, elegí **Public**: GitHub Pages es accesible públicamente. No cargues claves ni datos privados.
4. Para simplificar, **no marques** `Add a README file`, `.gitignore` ni licencia (el ZIP ya contiene un README). Si ya creaste el repositorio con README, podés subir todos los demás archivos y conservar el README existente.
5. Hacé clic en **Create repository**.

### B. Subir los archivos

6. Descargá `radar-cedears-github.zip` de ChatGPT.
7. En Windows, hacé clic derecho sobre el ZIP > **Extraer todo**. Abrí la carpeta extraída.
8. Volvé al repositorio de GitHub. Elegí **Add file → Upload files** (en un repositorio vacío puede decir **uploading an existing file**).
9. Arrastrá **el contenido INTERNO de la carpeta** al cuadro de subida: `.github`, `config`, `docs`, `scripts`, `tests`, `requirements.txt`, `README.md`. **No subas el ZIP cerrado**, ni una carpeta extra de nivel superior.
10. Esperá a que se termine la carga. Abajo, en **Commit changes**, poné `Primera versión radar CEDEARs` y confirmá con **Commit changes**.
11. En la pestaña **Code**, verificá que aparezcan estas rutas: `.github/workflows/actualizar.yml`, `config/universo.csv`, `docs/index.html`, `docs/app.js`, `docs/style.css`, `scripts/actualizar.py`, `tests/test_radar.py` y `requirements.txt`.

Si **no aparece `.github`** en el navegador, no quedó cargada la automatización. Entrá a **Add file → Create new file**, escribí el nombre completo `.github/workflows/actualizar.yml`, copiá el contenido de ese archivo del ZIP con Bloc de notas y guardá con **Commit changes**. GitHub crea las carpetas automáticamente.

### C. Activar la página

12. En el repositorio, abrí **Settings** (si no lo ves, abrí el menú `...` superior).
13. En la columna izquierda, buscá **Pages**.
14. Dentro de **Build and deployment**, elegí **Source: GitHub Actions**. No selecciones `Deploy from a branch`: nuestro flujo genera los indicadores antes de desplegar.
15. Volvé a la pestaña **Actions**. Si GitHub ofrece habilitar los workflows, tocá **I understand my workflows, go ahead and enable them**.
16. En el menú izquierdo de **Actions**, elegí **Actualizar radar CEDEARs**. A la derecha, tocá **Run workflow** y después el botón verde **Run workflow** (rama `main`).
17. Se iniciará el trabajo **actualizar-y-publicar**. Entrá en la ejecución para ver las etapas: instalar dependencias → validar configuración → tests → descargar mercado USD → publicar sitio. Para que funcione, debe finalizar con **tilde verde**. Si falla, revisá el paso marcado en rojo y su log.
18. Volvé a **Settings → Pages**. GitHub mostrará el enlace público del sitio. Con tu usuario, la dirección esperada es: `https://nico199723.github.io/radar-cedears/`. **Usá el enlace real de Pages; no se considera publicada hasta que GitHub lo confirme.**
19. Abrí el sitio. Al principio mostrará datos pendientes hasta que la primera actualización finalice. Después verificá que el último procesamiento sea reciente, que haya porcentaje de cobertura y que el listado muestre cotizaciones USA en USD.

### D. Qué queda automático

El archivo `.github/workflows/actualizar.yml` contiene:

```yaml
schedule:
  - cron: "0 13 * * *"
    timezone: "America/Argentina/Buenos_Aires"
  - cron: "5 18 * * *"
    timezone: "America/Argentina/Buenos_Aires"
```

- **13:00 ARG:** durante la sesión estadounidense. Para evitar señales falsas, utiliza el **último cierre diario completo**; NO convierte la vela intradiaria en cierre confirmado.
- **18:05 ARG:** después del horario regular de cierre de Wall Street. Puede mostrar el cierre previo si Yahoo todavía no consolidó la rueda; la fecha real del dato aparece en cada ficha.
- Se ejecuta **todos los días**, inclusive sábados y domingos; fines de semana no generan velas nuevas.
- GitHub puede demorar o no ejecutar un evento programado; las señales **se suspenden** en la interfaz si la publicación es antigua.
- Los workflows programados de repositorios públicos pueden desactivarse después de 60 días sin actividad. Si deja de actualizar, abrí **Actions**, revisá el estado y volvé a activar el workflow.

### E. Soluciones rápidas

| Problema | Qué hacer |
| --- | --- |
| 404 en la página | Revisar **Settings → Pages → Source: GitHub Actions** y el estado de **Actions**. |
| La automatización no aparece | Verificar que el archivo exista en `.github/workflows/actualizar.yml` y esté en `main`. |
| Error instalando `yfinance` | Abrí el log; repetí manualmente si fue error de conexión temporal. |
| Error «cobertura insuficiente» | Yahoo puede haber bloqueado o entregado historiales incompletos. Reintentar manualmente; no hay garantía de servicio. |
| No se actualiza a la hora exacta | GitHub Actions usa colas: son horas **programadas**, no una SLA. |
| Sale «SIN DATOS» para cierto ticker | Historial o mapeo USA no disponible; nunca reemplazar por CEDEAR ARS. |
| Ratio o disponibilidad CEDEAR | Verificar en [BYMA oficial](https://www.byma.com.ar/productos/productos-financieros/cedears) y [Caja de Valores](https://cajadevalores.com.ar/Servicios/Cedears). |
| Quiero agregar más acciones | Editar `config/universo.csv` en GitHub (botón lápiz). Agregar una fila con sector y un ticker **verdaderamente negociado en EE.UU., USD**, o dejar subyacente en blanco si no lo hay. Al guardar, se ejecuta de nuevo. |

## Estructura de archivos

```
.github/workflows/actualizar.yml  # automatización + publicación GitHub Pages
config/universo.csv               # lista editable de CEDEARs y mapeos USA
scripts/actualizar.py             # RSI, MACD, tendencias, score, señales
site: docs/index.html             # página
      docs/style.css              # diseño
      docs/app.js                 # filtros, sectores y fichas
      docs/data.json              # datos iniciales sin precios inventados
requirements.txt                  # librerías Python
tests/test_radar.py               # tests offline
```

## Alcance y riesgos

`HECHO` = último cierre USD y métricas descargadas; `INTERPRETACIÓN` = score y reglas técnicas; `ESCENARIO` = nivel de entrada/invalidez/objetivo teórico. **No hay confirmación 4H**, ni Koncorde, ni verificación automatizada de fundamentales, ratios o noticias. La etiqueta «SALIR / EVITAR» no conoce tu precio promedio; vos definís la ejecución y tamaño. Para opciones GGAL rigen reglas independientes y este sitio no opera opciones.

**Fuentes útiles:** https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site · https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax · https://www.byma.com.ar/productos/productos-financieros/cedears
