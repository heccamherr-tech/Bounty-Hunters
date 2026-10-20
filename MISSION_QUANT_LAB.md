# MISSION.md - Deeptest continuo de estrategias por instrumento (un solo turno)

## 0. Contexto (lee esto primero)

- El 2026-10-20 la cuenta de torneo Bullfy #162511 (balance inicial 5,000 USD) fue descalificada por perder 4.04% en un dia (limite del broker: 4.00%). Deals completos en `data/forensics/bullfy_162511_deals_30d.csv`.
  Causa directa: 5 posiciones ORB de 0.50 lotes fijos abiertas en pocas horas sobre instrumentos correlacionados (GBPJPY, USDJPY, EURUSD, XAUUSD, GBPUSD). Cada una arriesgaba ~1.5%; juntas sumaron 4%. El circuit breaker solo miraba PnL cerrado.
- El antiguo lider del torneo, MS27 (login 162871), paso de 5,000 a ~24,300 USD en 6 dias y tambien fue eliminado. Su historial completo esta en `data/forensics/trader_162871.json` (campo `operaciones`: lado, activo, apertura, precioApertura, cierre, precioCierre, gananciaNeta). Win rate 86%, ratio 0.75. Tenia ventaja real de entrada; murio por sizing (rafagas de 3-10 posiciones, lotes de hasta varios lotes).
- El lider actual (161934, Papi_bu506) y otros top traders estan en `data/forensics/trader_*.json`. Ranking completo en `bullfy_ranking_1029_snapshot.json`.
- Hallazgo previo con el blueprint NVIDIA (ver `vendor/nvidia_blueprint/`): la ruptura ORB de 1 hora en M5 tiene IC de rango negativo (aprox -0.05 a 15-30 min) y su inverso (fade) positivo, PERO esa medicion fue cross-sectional con solo 6 activos y 17 dias de datos, con t-stats sobrestimados por horizontes solapados. Tratala como hipotesis, no como hecho. Tu trabajo es medirlo bien, por instrumento, con 13 meses.
- Codigo legado de referencia (no ejecutable aqui, depende de MT5): `legacy_strategies/`.

## 1. Datos disponibles

- `data/ohlcv_m5/<SYMBOL>_M5.csv.gz`: columnas `time (UTC), open, high, low, close, tick_volume, spread (en puntos), real_volume`. 80,000 barras M5 por simbolo (aprox sep-2025 a oct-2026; cripto desde ene-2026).
  Simbolos: XAUUSD XAGUSD NDXUSD DJIUSD SPXUSD EURUSD GBPUSD USDJPY AUDUSD NZDUSD USDCAD USDCHF GBPJPY EURGBP BTCUSD ETHUSD.
- `data/symbol_specs_bullfy_mt5.json`: point, digits, contract size, tick value, volume step, swaps. Usalo para convertir movimiento de precio a USD por lote.
- Opcional: si tienes red, puedes bajar klines 5m de `https://data.binance.vision` (BTCUSDT, ETHUSDT, SOLUSDT) para extender cripto a 2+ anios. Si no hay red, sigue sin ello.

## 2. Objetivo

Construir, en este mismo turno y sin detenerte a preguntar, un laboratorio que descubra y valide fuera de muestra **un reglamento de juego por instrumento** mas **reglas cruzadas** y un **controlador de riesgo de portafolio dinamico**, y que deje todo listo para que el nodo ALFA lo ejecute en Exness demo y Binance testnet.

Principio rector del CEO: nada de una regla fija para todo el portafolio (eso es sobreajuste disfrazado). Cada instrumento tiene su propio comportamiento: sesiones, volatilidad, tendencia vs reversion, respuesta a barridos de liquidez. Las reglas cruzadas gobiernan la interaccion entre instrumentos. Todo parametro de riesgo es funcion de estado observable (volatilidad realizada, correlacion rodante, salud reciente de la estrategia), no una constante.

## 3. Entregables (todos en este turno)

### 3.1 Motor de backtest (`lab/engine/`)
- Event/vectorized hibrido en numpy/numba. Entrada al open de t+1. SL/TP intrabar resueltos de forma conservadora (si en la misma barra se tocan SL y TP, cuenta SL).
- Costos: spread de la barra de entrada y salida, slippage = 0.5 * spread mediano del simbolo, comision configurable.
- Sizing por riesgo: lotes = (riesgo_usd) / (distancia_SL_en_precio * valor_por_punto_por_lote), redondeado a volume_step. Nunca lotes fijos.
- Simulacion de cuenta de 5,000 USD con regla de broker: perdida diaria (cerrado + flotante, medida contra equity de inicio de dia UTC) >= 4% = cuenta muerta. Reportar si alguna configuracion la habria matado y cuando.
- Tests en `tests/`: no look-ahead (permutar el futuro no cambia senales pasadas), costos aplicados, sizing correcto, regla de 4%.

### 3.2 Evaluador de senales con el blueprint (`lab/signals/`)
- Reutiliza los operadores y la logica de `vendor/nvidia_blueprint/` (Rank IC, IR, decaimiento por horizonte). Agrega IC de serie de tiempo **por instrumento** (Spearman entre senal y retorno futuro de ese mismo instrumento), con errores estandar Newey-West o bloques no solapados.
- Biblioteca de familias de senal (cada una parametrizada y documentada):
  1. ORB breakout y ORB fade por sesion (Tokyo 23:00, London 06:00/07:00, NY 13:30 UTC; ventanas 15/30/60 min).
  2. Liquidity sweep: mecha que perfora maximo/minimo de N barras y cierra dentro, con filtro de volumen relativo y tamano de mecha.
  3. Estructura SMC: BOS con cuerpo vs sweep, ChoCh en M5 tras sweep en M15/H1 (agrega M5 a M15/H1 sin look-ahead), FVG como zona de reentrada.
  4. Momentum/burst: z-score de retorno de k barras, continuacion vs agotamiento.
  5. Reversion: z-score vs media movil/VWAP de sesion, bandas de Kalman.
  6. Regimen: volatilidad realizada por percentil, eficiencia de Kaufman, Hurst rodante; usar como filtro/condicionante, no como senal sola.
- Para cada (instrumento, familia, horizonte) reporta IC, t-stat robusto, estabilidad por mes.

### 3.3 Ingenieria inversa de MS27 (`lab/forensics/ms27.py`)
- Infiere el huso horario del sitio de rankings: para cada operacion, prueba offsets de -12h a +12h y elige el que maximiza la fraccion de `precioApertura` contenidos en el rango high-low de la barra M5 correspondiente. Documenta el offset.
- Para cada operacion extrae el contexto de mercado en la barra de entrada: sesion, minutos desde apertura de sesion, distancia a maximo/minimo de 12/48/288 barras, si hubo sweep en las ultimas N barras, z-score, volatilidad, direccion H1, posicion relativa al rango ORB, tiempo de tenencia, si era parte de una rafaga (varias entradas en < 15 min en el mismo activo).
- Compara esa distribucion contra barras aleatorias del mismo activo y sesion (lift por feature). Responde con datos: que condiciones estaban presentes en sus entradas que no estan en una barra cualquiera.
- Convierte ese perfil en una senal reproducible y evaluala con 3.1/3.2 sobre los 13 meses completos (no solo los 6 dias de MS27). Haz lo mismo, mas breve, con 161934 y los otros top traders si sus historiales lo permiten.
- Analiza tambien por que MS27 fue eliminado: reconstruye su curva intradia y su exposicion agregada.

### 3.4 Forense de nuestra perdida (`lab/forensics/alfa_loss_2026_10_20.py`)
- Reconstruye la exposicion agregada en el tiempo del 2026-10-20 con los deals reales. Mide la correlacion rodante entre los instrumentos abiertos en ese momento.
- Demuestra cuantitativamente que reglas del controlador de 3.6 habrian evitado la descalificacion, y cuanto habrian costado en oportunidades en el resto del historial.

### 3.5 Busqueda de reglamento por instrumento (`lab/search/`)
- Walk-forward anclado: entrenamiento minimo 4 meses, paso 1 mes, prueba 1 mes. HOLDOUT final = ultimas 6 semanas, intocable hasta el paso final.
- En cada ventana de entrenamiento busca por instrumento: familia(s) de senal, sesiones permitidas, filtro de regimen, SL y TP en multiplos de ATR, salida por tiempo, max trades por dia, gestion (break-even, parcial, trailing). Espacio de busqueda acotado (no mas de unos cientos de combinaciones por instrumento por ventana) y con preferencia por mesetas: puntua cada combinacion por la mediana del desempeno de sus vecinos en el grid, no por su valor puntual.
- Control de sobreajuste obligatorio: Deflated Sharpe Ratio (Bailey y Lopez de Prado) considerando el numero de pruebas, y Probability of Backtest Overfitting via CSCV. Minimo 60 trades fuera de muestra para declarar una regla valida.
- Si un instrumento no tiene ninguna regla que sobreviva, su reglamento debe decir explicitamente `"tradable": false`. Es un resultado valido y deseable frente a forzar algo.

### 3.6 Controlador de riesgo de portafolio dinamico (`lab/risk/`)
- Presupuesto diario de riesgo (por defecto 2.0% de equity de inicio de dia, con freno duro a 3.0% medido sobre cerrado + flotante + riesgo abierto hasta SL; el broker mata a 4.0%).
- Riesgo por operacion = f(confianza del reglamento del instrumento en walk-forward, salud reciente, volatilidad actual). Rango orientativo 0.15% a 0.75%.
- Riesgo agregado de posiciones abiertas calculado con la matriz de correlacion rodante (por ejemplo 20 dias de retornos M5 o H1): riesgo_portafolio = sqrt(w' Sigma w) donde w = riesgo hasta SL firmado por posicion. Nueva orden solo si cabe en el presupuesto restante.
- Reglas cruzadas derivadas de datos, no listas fijas: clusters por correlacion rodante (bloque USD, bloque JPY, indices US, metales, cripto) recalculados cada dia; limite de exposicion neta por cluster proporcional a su volatilidad; prohibicion de entradas en la misma direccion del mismo factor si ya hay riesgo abierto en ese factor por encima de un umbral dinamico.
- Valida el controlador corriendo todos los reglamentos juntos en walk-forward y en HOLDOUT: dias de cuenta muerta = 0 es requisito.

### 3.7 Lector de cambios de patron y correccion en caliente (`lab/adaptive/`)
- Por instrumento y por regla: detector de deriva sobre la serie de R por trade (CUSUM y Page-Hinkley) y sobre IC rodante; detector de cambio de regimen de volatilidad.
- Acciones: reducir riesgo a la mitad, pausar la regla, o re-calibrar (re-ejecutar la busqueda 3.5 solo con datos hasta hoy). Las acciones deben dispararse por estado, con histeresis, y estar simuladas dentro del walk-forward (sin mirar el futuro).
- Reporta cuanto mejora o empeora el walk-forward con la capa adaptativa activada vs desactivada.

### 3.8 Artefactos para ejecucion en vivo
- `rulebooks/<SYMBOL>.json` (uno por instrumento) y `rulebooks/cross_rules.json`, `rulebooks/portfolio_risk.json`. Define y valida un JSON Schema en `rulebooks/schema.json`.
- `lab/live/rulebook_engine.py`: funciones puras sin dependencias de broker: `on_bar(symbol, bars_df, state) -> list[Intent]` y `risk_gate(intents, open_positions, account_state) -> list[Order]`. Interfaz `BrokerAdapter` abstracta (get_bars, get_positions, get_account, send_order, modify, close). No implementes adaptadores de broker reales; el nodo ALFA implementara MT5 (Exness demo) y Binance testnet sobre esa interfaz.
- `lab/live/replay.py`: reproduce barra a barra el HOLDOUT a traves de `rulebook_engine` y debe dar los mismos trades que el backtest (test de paridad).

### 3.9 Reporte (`reports/DEEPTEST_REPORT.md`)
- Tabla por instrumento: tradable si/no, reglas elegidas, trades OOS, win rate, expectativa en R, profit factor, max drawdown, DSR, PBO, peor dia.
- Portafolio combinado con controlador: curva OOS y HOLDOUT, peor dia, dias muertos, retorno.
- Resultados de MS27 (que se puede reproducir de su ventaja y que no).
- Lista honesta de lo que no funciono.
- Comandos exactos para reproducir todo.

## 4. Forma de trabajo en este turno

- No te detengas a pedir confirmacion. Si algo es ambiguo, toma la decision mas conservadora, documentala en el reporte y sigue.
- Prioriza en este orden si el tiempo no alcanza: 3.1 -> 3.4 -> 3.6 -> 3.3 -> 3.5 -> 3.8 -> 3.7 -> 3.9 (el reporte siempre se escribe, aunque sea parcial).
- Haz commits frecuentes con mensajes descriptivos. Todos los tests deben pasar al final (`pytest -q`).
- Computo limitado: vectoriza, cachea features en parquet/npz bajo `cache/` (ignorado por git), limita grids.
