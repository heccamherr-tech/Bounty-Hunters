# ALFA QUANT v4.5 — ESPECIFICACIÓN ARQUITECTÓNICA DE CALIBRACIÓN INSTITUCIONAL
## Síntesis Matemática y Estructural de Smart Money Concepts (Basada en Club Capital Trading / Cris Campoz)

---

### 1. Filosofía Operativa y Principio de "Gráficos Limpios"

El sistema de trading de ALFA INC se fundamenta en la mecánica del **Algoritmo Interbancario** (IPDA - Interbank Price Delivery Algorithm). Los mercados financieros no se mueven por cruces de medias móviles, sobrecompras/sobreventas de RSI ni patrones minoristas lineales. El precio se desplaza exclusivamente por dos motivos:
1. **Buscar Liquidez**: Activar los Stop Loss de los operadores retail para obtener volumen de contrapartida.
2. **Rebalancear Ineficiencias**: Rellenar vacíos de liquidez (Fair Value Gaps / Imbalances) dejados por inyecciones institucionales previas.

---

### 2. Anatomía Fractal: Jerarquía de Temporalidades (HTF vs. LTF)

La cascada multitemporal alinea tres estratos independientes pero interconectados:

```
[MARCO MACRO: D1 / H4] ────► Define la Tendencia y el Rango Operativo
                             (Strong High/Low ──► Weak High/Low)
                             Identifica el Inducement (IDM) y los Bloques Extremos
                                    │
[MARCO ESTRUCTURAL: H1 / M15] ──► Mapea el Order Flow Interno y Zonas Decisionales
                                    │
[MARCO TÁCTICO: M5 / M1] ──────► Infiltración Quirúrgica del ACTOR_SICARIO
                                  (Barrido Micro + ChoCh con Cuerpo + Micro-FVG)
```

#### A. Rango Operativo Fractal (Strong vs. Weak Points)
* **Strong Low (Mínimo Fuerte)**: Aquel mínimo que tomó liquidez previa (Sweep) y logró romper con cuerpo (BOS) un máximo estructural anterior. Es un nivel protegido por las instituciones; si se vulnera, cambia la tendencia.
* **Weak High (Máximo Débil)**: Aquel máximo que no logró romper estructura y carece de inyección de volumen. Es el **Take Profit objetivo** de una compra, ya que está cargado de liquidez de compra (Buy-Side Liquidity - BSL).
* **Strong High (Máximo Fuerte)**: Aquel máximo que barrió liquidez y rompió con cuerpo un mínimo anterior.
* **Weak Low (Mínimo Débil)**: El objetivo de toma de ganancias en ventas (Sell-Side Liquidity - SSL).

---

### 3. Fórmulas Matemáticas de Calibración

#### Regla 1: Ruptura Estructural (BOS) vs. Barrido de Liquidez (Sweep)
Un fallo crítico en sistemas retail es considerar cualquier cruce de precio como rompimiento de estructura. La regla estricta de Capital Trading establece:

$$\text{BOS Alcista Confirmado} \iff \text{Vela.close} > \text{Máximo Fractal Previsto}$$
$$\text{BOS Bajista Confirmado} \iff \text{Vela.close} < \text{Mínimo Fractal Previsto}$$

Si el precio rebasa el nivel pero el cuerpo cierra dentro del rango:

$$\text{Sweep Alcista} \iff (\text{Vela.high} > \text{Máximo Fractal}) \land (\text{Vela.close} \le \text{Máximo Fractal})$$
$$\text{Sweep Bajista} \iff (\text{Vela.low} < \text{Mínimo Fractal}) \land (\text{Vela.close} \ge \text{Mínimo Fractal})$$

* **Interpretación Operativa**:
  - Un **BOS** valida la continuación tendencial.
  - Un **Sweep** invalida el BOS y se clasifica como absorción institucional para reversión inmediata.

---

#### Regla 2: El Algoritmo de Inducción de Liquidez (Inducement / IDM)
Tras confirmarse un BOS genuino, el primer retroceso generado por el mercado **NO es un Bloque de Órdenes operable**. Es la inducción (IDM) diseñada para atrapar a los primeros compradores/vendedores retail.

$$\text{IDM Alcista} = \text{Mínimo más reciente del retroceso posterior al BOS}$$
$$\text{POI Habilitado} \iff \text{Precio Actual} \le \text{IDM Alcista}$$

* El sistema solo autoriza la búsqueda de compras una vez que el precio ha tomado el IDM y alcanza:
  1. **Bloque Decisional**: El bloque de órdenes responsable de haber provocado el quiebre hacia el nuevo máximo.
  2. **Bloque Extremo**: El bloque de órdenes originario en la base absoluta del fractal (máxima probabilidad).

---

#### Regla 3: Validación Obligatoria de Imbalance (Fair Value Gap - FVG)
Un Bloque de Órdenes carece de validez institucional si la vela de expansión subsecuente no dejó un vacío de liquidez de 3 velas.

* **Condición FVG Alcista (Entre Vela $i-1$ y Vela $i+1$):**
  $$\text{Gap} = \text{Low}(\text{Vela}_{i+1}) - \text{High}(\text{Vela}_{i-1})$$
  $$\text{FVG Válido} \iff \text{Gap} > 0$$

* **Condición FVG Bajista (Entre Vela $i-1$ y Vela $i+1$):**
  $$\text{Gap} = \text{Low}(\text{Vela}_{i-1}) - \text{High}(\text{Vela}_{i+1})$$
  $$\text{FVG Válido} \iff \text{Gap} > 0$$

* **Filtro de Descarte**: Si $\text{Gap} \le 0$, el bloque de órdenes se marca como **MITIGADO** en origen y el motor lo ignora.

---

#### Regla 4: Entrada por Confirmación del Sicario (Paso Cero W/M Refinado)
Cero órdenes límite a ciegas en marcos macro. El protocolo de ejecución táctica en M1/M5 sigue 4 pasos secuenciales:

1. **Llegada al POI**: El precio penetra el límite proximal del bloque H4/H1 tras haber barrido el Inducement.
2. **Barrido de Liquidez Interna (Sweep LTF)**: En M1/M5, el precio realiza un último barrido con mecha por debajo del mínimo del pullback.
3. **Cambio de Carácter (ChoCh Micro con Cuerpo)**: El precio quiebra con cuerpo de vela el último máximo estructural menor de M1/M5.
4. **Gatillo en Micro-OB**: El Sicario coloca orden límite al 50% de Fibonacci del micro-bloque generado por el ChoCh con Stop Loss milimétrico (apenas 3 a 5 pips en Forex, 15 a 30 USD en Oro) por debajo del mínimo del barrido.
5. **R:R Asimétrico Dinámico**:
   $$\text{Target} = \text{Weak High Macro}$$
   $$\text{Ratio R:R} = \frac{|\text{Weak High} - \text{Entrada}|}{|\text{Entrada} - \text{SL}|} \ge 4.0$$
   (Permitiendo capturar expansiones de 1:4 hasta 1:13).

---

### 4. Killzones Horarias y Silencio Operativo
Forex y Metales respetan estrictamente la inyección de liquidez interbancaria:
* **Killzone Londres**: 08:00 - 12:00 UTC+2 (Apertura europea, búsqueda del Judas Swing barriendo el rango de Asia).
* **Killzone New York**: 13:00 - 18:00 UTC+2 (Volumen máximo y mitigación de bloques diarios).
* **Fuera de Killzone**: Silencio operativo absoluto en divisas y metales (Cero entradas).
* **Cripto (BTC/ETH)**: Escaneo continuo 24/7/365 con adaptación de spreads.
