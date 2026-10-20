import MetaTrader5 as mt5
import pandas as pd
import json
import math
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk
import threading

# ==========================================
#  ACTOR 3: EL SICARIO (Micro-Scalper Autónomo)
#
#  Dependencias:
#    - motor_estructural_micro_corregido.MotorAritmetico
#    - motor_estructural_micro_corregido.MotorEstructural
#
#  Cascada de Temporalidades:
#    Macro context  : H1  (leído por el Topógrafo/Motor Micro)
#    Calibración    : M5  o  M15  (Fase 1 — según tamaño del POI)
#    Infiltración   : M5  /  M1   (Fase 3 — Micro POI y ChoCh de regreso)
#    Gestión        : M5  /  M1   (Fase 4 — trailing fractal en vivo)
# ==========================================
class ActorSicario:
    """
    Clase autónoma que hereda la inteligencia del MotorEstructural.
    Misión: Infiltración en POI, combate en trinchera (pullback), 
    confirmación micro (ChoCh -> Micro POI) y auto-gestión fractal.
    """
    def __init__(self, motor_aritmetico, motor_estructural, comunicaciones, auditor_csv):
        self.motor = motor_aritmetico
        self.estructura = motor_estructural
        self.telegram = comunicaciones
        self.auditor = auditor_csv
        
        # El estado mental en tiempo real que se convertirá en JSON auditable
        self.estado_mental = {}

    # ==========================================
    #  ORQUESTADOR PRINCIPAL
    # ==========================================
    def patrullaje_autonomo(self, symbol, precio_actual, poi_macro, liquidez_objetivo, obtener_velas_func):
        """
        Evalúa en qué fase se encuentra el precio respecto al POI
        y deriva la ejecución a la fase correspondiente.

        Flujo de fases:
          F1 → Calibración balística (siempre)
          F2 → Combate en trinchera (pullback activo)
          F3 → Infiltración y gatillo (precio en proximal)
          F4 → Gestión armónica (posición ya abierta)
        """
        direccion_macro = poi_macro.get('direccion', 'COMPRAS')

        # 1. Inicializamos la memoria del Sicario para este activo
        self.estado_mental = {
            "id_mision":                  f"{symbol}_ASALTO_MICRO",
            "timestamp_actualizacion":    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "fase_actual":                "FASE_1_CALIBRACION",
            "contexto_macro": {
                "activo":                 symbol,
                "precio_actual":          precio_actual,
                "direccion_macro":        direccion_macro,
                "poi_macro": {
                    "tf_origen":          poi_macro.get('tf_macro', 'H1'),
                    "tipo":               poi_macro.get('tipo', 'DESCONOCIDO'),
                    "proximal":           poi_macro.get('proximal', 0.0),
                    "distal":             poi_macro.get('distal',   0.0)
                },
                "liquidez_objetivo_macro": liquidez_objetivo
            },
            "fase_1_calibracion":  {},
            "fase_2_trinchera":    {},
            "fase_3_infiltracion": {},
            "fase_4_gestion":      {}
        }

        # ── FASE 1: Calibración (siempre se ejecuta) ──────────────────────
        tf_micro = self._fase_1_calibrar_temporalidad(symbol, poi_macro)
        if not tf_micro:
            self.estado_mental["fase_actual"] = "MISION_ABORTADA (Fallo de calibración)"
            return

        # ── ENRUTADOR DE FASE ────────────────────────────────────────────
        # Si ya hay posición abierta del Sicario → Fase 4 (gestión)
        posiciones = mt5.positions_get(symbol=symbol)
        pos_sicario = [p for p in (posiciones or []) if p.magic == 777]

        if pos_sicario:
            self.estado_mental["fase_actual"] = "FASE_4_GESTION_ARMONICA"
            self._fase_4_gestion_armonica(symbol, direccion_macro, obtener_velas_func)
            return

        # Sin posición abierta: decidimos por proximidad al POI
        proximal = poi_macro.get('proximal', 0.0)
        distal   = poi_macro.get('distal',   0.0)
        info     = mt5.symbol_info(symbol)
        holgura  = abs(proximal - distal) * 0.5  # 50% de la caja como zona de alerta

        en_zona_proximal = False
        if info:
            if direccion_macro == "COMPRAS":
                en_zona_proximal = precio_actual <= (proximal + holgura)
            else:
                en_zona_proximal = precio_actual >= (proximal - holgura)

        if en_zona_proximal:
            # Precio tocando el proximal → Fase 3 (infiltración)
            self.estado_mental["fase_actual"] = "FASE_3_INFILTRACION"
            self._fase_3_infiltracion_y_gatillo(symbol, poi_macro, tf_micro, obtener_velas_func)
        else:
            # Precio aún lejos → Fase 2 (monitorear pullback)
            self.estado_mental["fase_actual"] = "FASE_2_EVALUACION_TRINCHERA"
            self._fase_2_operar_trinchera(symbol, precio_actual, poi_macro, tf_micro, obtener_velas_func)

    # ==========================================
    #  FASE 1: RECEPCIÓN Y CALIBRACIÓN BALÍSTICA
    # ==========================================
    def _fase_1_calibrar_temporalidad(self, symbol, poi_macro):
        """
        Mide el tamaño del POI en puntos del broker.
        Decisión puramente matemática para ajustar la mira a M1, M5 o M15.

        Umbrales:
          CRIPTO   : > 1000 pts → M5  |  <= 1000 pts → M15
          METALES  : > 300  pts → M5  |  <= 300  pts → M15
          FOREX JPY: > 150  pts → M5  |  <= 150  pts → M15
          FOREX    : > 150  pts → M5  |  <= 150  pts → M15
          (POI ultra-masivo > 3x umbral → desciende a M1 para máxima precisión)
        """
        info = mt5.symbol_info(symbol)
        if not info:
            self.estado_mental["fase_1_calibracion"] = {"error": "Activo no encontrado en el broker."}
            return None

        # 1. Clasificación del activo (igual que MotorAritmetico.from_symbol)
        s = symbol.upper()
        if any(c in s for c in ("BTC", "ETH", "LTC", "XRP", "DOGE", "SOL")):
            tipo_mercado = "CRIPTO"
            umbral_masivo = 1000
        elif any(c in s for c in ("XAU", "XAG")):
            tipo_mercado = "METALES"
            umbral_masivo = 300
        elif any(c in s for c in ("NAS", "US30", "SPX", "DAX", "UK100")):
            tipo_mercado = "INDICES"
            umbral_masivo = 300
        elif "JPY" in s:
            tipo_mercado = "FOREX JPY"
            umbral_masivo = 150
        else:
            tipo_mercado = "FOREX"
            umbral_masivo = 150

        # 2. Tamaño del POI en puntos reales del broker
        tamano_precio = abs(poi_macro['proximal'] - poi_macro['distal'])
        tamano_puntos = tamano_precio / info.point

        # 3. Selección del lente — tres niveles de zoom
        if tamano_puntos > umbral_masivo * 3:
            tf_micro = mt5.TIMEFRAME_M1
            tf_nombre = "M1"
            motivo = (f"POI Ultra-Masivo ({tamano_puntos:.1f} pts > {umbral_masivo * 3}). "
                      f"Lente de máxima precisión para minimizar drawdown de entrada.")
        elif tamano_puntos > umbral_masivo:
            tf_micro = mt5.TIMEFRAME_M5
            tf_nombre = "M5"
            motivo = (f"POI Masivo ({tamano_puntos:.1f} pts > {umbral_masivo}). "
                      f"Lente milimétrico para evitar drawdown profundo en la caja.")
        else:
            tf_micro = mt5.TIMEFRAME_M15
            tf_nombre = "M15"
            motivo = (f"POI Concentrado ({tamano_puntos:.1f} pts <= {umbral_masivo}). "
                      f"Lente estándar — caja ajustada no requiere mayor resolución.")

        # 4. Grabado en la Memoria del Sicario
        self.estado_mental["fase_1_calibracion"] = {
            "tipo_mercado_detectado": tipo_mercado,
            "tamano_poi_puntos": round(tamano_puntos, 1),
            "umbral_evaluacion": umbral_masivo,
            "temporalidad_asignada": tf_nombre,
            "poi_evaluado": {
                "proximal": poi_macro.get('proximal', 0.0),
                "distal":   poi_macro.get('distal',   0.0),
                "tipo":     poi_macro.get('tipo', 'DESCONOCIDO'),
                "tf_origen": poi_macro.get('tf_macro', 'H1')
            },
            "motivo_tactico": motivo,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        return tf_micro
    # ==========================================
    #  FASE 2: EXPLOTACIÓN DEL VACÍO (COMBATE EN TRINCHERA)
    # ==========================================
    def _fase_2_operar_trinchera(self, symbol, precio_actual, poi_macro, tf_micro, obtener_velas_func):
        direccion_macro = poi_macro.get('direccion', 'COMPRAS')
        direccion_trinchera = "VENTAS" if direccion_macro == "COMPRAS" else "COMPRAS"

        # 1. Ingesta Masiva (Mapa Completo para no perderse)
        df_micro = obtener_velas_func(symbol, tf_micro, 4500)
        if df_micro is None or df_micro.empty:
            self.estado_mental["fase_2_trinchera"] = {"estado": "ERROR", "mensaje": "Sin datos en micro."}
            return

        # 2. Búsqueda del Paso Cero en Contra-Tendencia (Origen del Pullback)
        fractales_base = self.estructura._mapear_fractales(df_micro, sensibilidad=2)
        choch_contra = self.estructura._identificar_paso_cero(df_micro, tf_micro, direccion_trinchera, fractales_base)

        if not choch_contra or not choch_contra.get("tipo"):
            #  NOTA APLICADA: Si no hay ChoCh, imprimimos los límites absolutos que el Sicario está viendo
            idx_max_abs = df_micro['high'].idxmax()
            idx_min_abs = df_micro['low'].idxmin()
            
            self.estado_mental["fase_2_trinchera"] = {
                "direccion_combate": f"{direccion_trinchera} (Buscando Pullback)",
                "diagnostico_estructural": {
                    "velas_analizadas": len(df_micro), 
                    "paso_cero_contra_tendencia": "NO_DETECTADO"
                },
                "entorno_absoluto": {
                    "techo_actual": f"{df_micro.loc[idx_max_abs, 'high']} ({self.estructura._ts_a_fecha(df_micro.loc[idx_max_abs, 'time'])})",
                    "suelo_actual": f"{df_micro.loc[idx_min_abs, 'low']} ({self.estructura._ts_a_fecha(df_micro.loc[idx_min_abs, 'time'])})"
                },
                "estado_combate": "ESPERANDO_PULLBACK",
                "decision_tactica": "Aún no hay ChoCh en contra validado. El precio fluye a favor de Macro."
            }
            return

        # 3. Geometría Estática del Vacío (Fibo Institucional)
        idx_origen = choch_contra.get('indice_origen', len(df_micro)-1)
        vela_origen = df_micro.loc[idx_origen]
        vertice_pullback = vela_origen['high'] if direccion_trinchera == "VENTAS" else vela_origen['low']
        
        fibo_50_estatico = (vertice_pullback + poi_macro['proximal']) / 2

        # 4. Respiración Fractal y Escáner de Trinchera (Aceleración)
        sens_optima = 0
        of_micro_valido = False
        bos_clasicos = []
        bos_acel = []

        #  NOTA APLICADA: Iteramos buscando armonía y extraemos fechas/precios exactos para no ver fantasmas.
        for sens in range(2, 8):
            fractales_respirados = self.estructura._mapear_fractales(df_micro, sensibilidad=sens)
            valido, b_clas, b_acel = self._auditar_order_flow_trinchera(df_micro, fractales_respirados, direccion_trinchera, idx_origen, tf_micro)
            
            if valido:
                sens_optima = sens
                of_micro_valido = True
                bos_clasicos = b_clas
                bos_acel = b_acel
                break 

        # 5. Dictamen de Combate
        total_bos = len(bos_clasicos) + len(bos_acel)
        if of_micro_valido and total_bos > 0:
            estado_combate = "PALEANDO_PULLBACK"
            accion = f"Armonía validada (ChoCh + OF Acelerado). Caza de retailers hacia {poi_macro['proximal']}."
        else:
            estado_combate = "ESPERANDO_ARMONIA_CONTRA"
            accion = f"ChoCh detectado pero Order Flow sucio/desfasado. Esperando confirmación estricta."

        # 6. Memoria Auditable
        self.estado_mental["fase_2_trinchera"] = {
            "direccion_combate": f"{direccion_trinchera} (Pullback de {direccion_macro})",
            "diagnostico_estructural": {
                "velas_analizadas": len(df_micro),
                "paso_cero_contra_tendencia": {
                    "estado": "DETECTADO",
                    "tipo": choch_contra['tipo'],
                    "vertice_origen_pullback": float(vertice_pullback),
                    "fecha_origen": self.estructura._ts_a_fecha(vela_origen['time']) if 'time' in vela_origen else "Desconocida"
                },
                "respiracion_fractal": {"sensibilidad_optima_encontrada": sens_optima if of_micro_valido else "FALLIDA"}
            },
            "geometria_del_vacio": {
                "techo_pullback" if direccion_trinchera == "VENTAS" else "suelo_pullback": float(vertice_pullback),
                "objetivo_poi_macro": float(poi_macro['proximal']),
                "fibo_50_estatico": float(fibo_50_estatico)
            },
            "order_flow_acelerado_micro": {
                "valido": of_micro_valido,
                "bos_escalera_clasica": bos_clasicos, # Imprime la lista de fechas y precios
                "bos_por_aceleracion": bos_acel,      # Imprime la lista de fechas y precios
                "total_bos_validados": total_bos
            },
            "estado_combate": estado_combate,
            "decision_tactica": accion
        }

    # ==========================================
    # ️ MOTOR INTERNO: Escáner de Trinchera (Aceleración Fractal)
    # ==========================================
    def _auditar_order_flow_trinchera(self, df, fractales, direccion, idx_origen, timeframe):
        bos_clasicos_detalle = []
        bos_acelerados_detalle = []
        
        lista_fractales = fractales["minimos"] if direccion == "VENTAS" else fractales["maximos"]
        #  NOTA APLICADA: Operamos estrictamente desde el origen del ChoCh en contra
        frac_validos = [f for f in lista_fractales if f['indice'] > idx_origen] 
        
        if len(frac_validos) < 1: 
            return False, [], []

        ultimo_precio_roto = frac_validos[0]['precio']
        vela_actual = df.iloc[-1]
        
        for i in range(1, len(frac_validos)):
            frac_actual = frac_validos[i]
            
            #  Auditoría Clásica: Verificamos ruptura con la regla de cuerpos/mechas de tu Motor Estructural
            roto_clasico = False
            if direccion == "VENTAS" and frac_actual['precio'] < ultimo_precio_roto:
                roto_clasico = True
            elif direccion == "COMPRAS" and frac_actual['precio'] > ultimo_precio_roto:
                roto_clasico = True
                
            if roto_clasico:
                bos_clasicos_detalle.append({
                    "precio_roto": self.motor.a_humano(self.motor.a_entero(ultimo_precio_roto)),
                    "fecha_ruptura": self.estructura._ts_a_fecha(frac_actual['time'])
                })
                ultimo_precio_roto = frac_actual['precio']
            
            #  NOTA APLICADA: BOS de Aceleración con Patrones M/W
            # Si el precio vivo rompe el fractal actual violentamente, verificamos que la vela viva sea válida
            tipo_bos = "bearish" if direccion == "VENTAS" else "bullish"
            if self.estructura.auditar_bos(vela_actual, frac_actual['precio'], timeframe, tipo_bos):
                # Validamos que no sea el mismo fractal que acabamos de romper clásicamente
                if frac_actual['precio'] != ultimo_precio_roto:
                    bos_acelerados_detalle.append({
                        "precio_acelerado_roto": self.motor.a_humano(self.motor.a_entero(frac_actual['precio'])),
                        "fecha_ruptura_viva": self.estructura._ts_a_fecha(vela_actual['time'])
                    })

        # Criterio de validez táctica
        of_valido = (len(bos_clasicos_detalle) + len(bos_acelerados_detalle)) >= 1
        return of_valido, bos_clasicos_detalle, bos_acelerados_detalle
    # ==========================================
    #  FASE 3: INFILTRACIÓN ÓPTIMA (ENTRADA POR CONFIRMACIÓN)
    # ==========================================
    def _fase_3_infiltracion_y_gatillo(self, symbol, poi_macro, tf_micro, obtener_velas_func):
        """
        Se activa al tocar la línea Proximal o la liquidez previa al POI.

        Flujo:
          1. Descarga velas en la temporalidad micro calibrada (M5 o M1).
          2. Respiración Fractal: busca armonía en la dirección MACRO.
          3. Detección del ChoCh de regreso (la 'W' o 'M' que confirma que
             el pullback terminó y la macro retoma el control).
          4. Micro POI: NO entra a mercado en el ChoCh.
             Usa _escanear_obs_institucionales del motor para localizar
             el OB inmediato anterior en la temporalidad micro.
             Prioridad: FVG confirmado → OB con inducement → OB limpio.
          5. Calcula entrada (Fibo 50% del Micro OB), SL (distal del OB),
             TP (liquidez objetivo macro) y graba todo en estado_mental.
        """
        direccion_macro = poi_macro.get('direccion', 'COMPRAS')

        # Bajamos un nivel más si el lente calibrado es M5: entramos en M1
        _mapa_micro_a_nano = {
            mt5.TIMEFRAME_M5:  (mt5.TIMEFRAME_M1,  "M1"),
            mt5.TIMEFRAME_M15: (mt5.TIMEFRAME_M5,  "M5"),
            mt5.TIMEFRAME_M1:  (mt5.TIMEFRAME_M1,  "M1"),   # ya en el piso
        }
        tf_nano, tf_nano_nombre = _mapa_micro_a_nano.get(tf_micro, (mt5.TIMEFRAME_M5, "M5"))

        # 1. Ingesta en la temporalidad de infiltración
        df_nano = obtener_velas_func(symbol, tf_nano, 500)
        if df_nano is None or df_nano.empty:
            self.estado_mental["fase_3_infiltracion"] = {
                "estado": "ERROR",
                "mensaje": f"Sin datos en {tf_nano_nombre} para infiltración."
            }
            return

        # 2. Respiración Fractal buscando ChoCh de regreso a MACRO
        choch_macro_regreso = None
        sens_infiltracion = 0

        for sens in range(2, 8):
            frac = self.estructura._mapear_fractales(df_nano, sensibilidad=sens)
            if not frac["maximos"] or not frac["minimos"]:
                continue
            candidato = self.estructura._identificar_paso_cero(
                df_nano, tf_nano, direccion_macro, frac
            )
            if candidato and candidato.get("tipo"):
                choch_macro_regreso = candidato
                sens_infiltracion = sens
                break

        if not choch_macro_regreso:
            self.estado_mental["fase_3_infiltracion"] = {
                "estado": "ESPERANDO_CHOCH_MACRO",
                "temporalidad_infiltracion": tf_nano_nombre,
                "mensaje": (f"No hay ChoCh {direccion_macro} confirmado en {tf_nano_nombre}. "
                             "El pullback aún no terminó — esperar sin disparar.")
            }
            return

        idx_choch = choch_macro_regreso.get("indice_origen", 0)

        # 3. Micro POI — OB institucional inmediato en la zona del ChoCh
        frac_optimos = self.estructura._mapear_fractales(df_nano, sensibilidad=sens_infiltracion)
        obs_institucionales = self.estructura._escanear_obs_institucionales(
            df_nano, max(0, idx_choch - 30), direccion_macro, frac_optimos
        )

        # Prioridad institucional SMC (Cris Campoz / Capital Trading):
        # 1. FVG_CONFIRMADO + INDUCEMENT (Maxima calidad institucional)
        # 2. FVG_CONFIRMADO (Order Block con desbalance / inyeccion institucional)
        # 3. OB_CON_INDUCEMENT (Liquidez previa capturada)
        # 4. OB_LIMPIO (Fallback si no se restringe por configuracion)
        exigir_fvg = True
        try:
            from alfa_config_loader import cfg
            exigir_fvg = bool(cfg("motor.exigir_fvg_en_ob", True))
        except Exception:
            exigir_fvg = True

        filtros = [
            ("FVG_CON_INDUCEMENT", lambda o: o.get("fvg_detectado") and o.get("inducement_previo")),
            ("FVG_CONFIRMADO",     lambda o: o.get("fvg_detectado")),
            ("OB_CON_INDUCEMENT",  lambda o: o.get("inducement_previo")),
        ]
        if not exigir_fvg:
            filtros.append(("OB_LIMPIO", lambda o: True))

        micro_ob = None
        for prioridad, filtro in filtros:
            candidatos = [o for o in obs_institucionales if filtro(o)]
            if candidatos:
                # El mas reciente que aun no fue perforado por el precio actual
                precio_actual = df_nano['close'].iloc[-1]
                validos = []
                for o in candidatos:
                    if direccion_macro == "COMPRAS" and precio_actual > o['distal_float']:
                        validos.append(o)
                    elif direccion_macro == "VENTAS" and precio_actual < o['distal_float']:
                        validos.append(o)
                if validos:
                    micro_ob = max(validos, key=lambda o: o['time'])
                    micro_ob['calidad'] = prioridad
                    break

        if not micro_ob:
            self.estado_mental["fase_3_infiltracion"] = {
                "estado": "MICRO_OB_NO_ENCONTRADO",
                "choch_macro_detectado": {
                    "tipo": choch_macro_regreso['tipo'],
                    "coordenadas": choch_macro_regreso.get('coordenadas', {}),
                    "fechas": choch_macro_regreso.get('fechas_mt5', {})
                },
                "mensaje": (f"ChoCh {direccion_macro} confirmado en {tf_nano_nombre} "
                             "pero no hay Micro OB institucional disponible conforme a reglas SMC — "
                             "esperar retroceso al siguiente fractal.")
            }
            return

        # 4. Balistica de la entrada con Buffer Protector contra Caceria de Spreads (NVIDIA Blueprint)
        entrada = (micro_ob['proximal_float'] + micro_ob['distal_float']) / 2  # Fibo 50% del OB
        tamano_ob = abs(micro_ob['proximal_float'] - micro_ob['distal_float'])
        buffer_proteccion = tamano_ob * 0.35  # Holgura de 35% para absorber micro-repruebas
        
        if direccion_macro == "COMPRAS":
            sl = micro_ob['distal_float'] - buffer_proteccion
        else:
            sl = micro_ob['distal_float'] + buffer_proteccion
            
        tp_target = poi_macro.get('tp_liquidez', 0.0)

        riesgo  = abs(entrada - sl)
        if riesgo <= 0:
            self.estado_mental["fase_3_infiltracion"] = {
                "estado": "ERROR_SL_INVALIDO",
                "mensaje": f"Entrada y SL identicos ({entrada}). Operacion abortada."
            }
            return

        # Target de liquidez macro institucional (Weak High / Weak Low)
        if direccion_macro == "COMPRAS":
            if tp_target <= entrada:
                tp_alt = poi_macro.get('limite_superior', 0.0)
                tp_target = tp_alt if tp_alt > entrada else entrada + (riesgo * 4.0)
        else: # VENTAS
            if tp_target >= entrada or tp_target <= 0.0:
                tp_alt = poi_macro.get('limite_inferior', 0.0)
                tp_target = tp_alt if (tp_alt < entrada and tp_alt > 0.0) else entrada - (riesgo * 4.0)

        recompensa = abs(tp_target - entrada)
        rr = round(recompensa / riesgo, 2) if riesgo > 0 else 0.0

        # Filtro de Ratio Riesgo-Beneficio Institucional SMC (Cris Campoz: R:R >= 3.5 hasta 1:13)
        rr_minimo = 3.5
        try:
            from alfa_config_loader import cfg
            rr_minimo = float(cfg("sicario.ratio_minimo_rr", 3.5))
        except Exception:
            rr_minimo = 3.5

        if rr < rr_minimo:
            self.estado_mental["fase_3_infiltracion"] = {
                "estado": "RATIO_RR_INSUFICIENTE",
                "temporalidad_infiltracion": tf_nano_nombre,
                "balistica": {
                    "direccion":               direccion_macro,
                    "entrada_fibo50_ob":       round(entrada, 6),
                    "stop_loss_distal":        round(sl, 6),
                    "take_profit_liq_macro":   round(tp_target, 6),
                    "ratio_riesgo_recompensa": rr,
                    "ratio_minimo_requerido":  rr_minimo
                },
                "mensaje": (f"Micro OB descartado: Ratio R:R {rr} es inferior al umbral "
                            f"institucional de {rr_minimo}. Se exige asimetria matematica.")
            }
            return

        tipo_orden_mt5 = mt5.ORDER_TYPE_BUY if direccion_macro == "COMPRAS" else mt5.ORDER_TYPE_SELL

        # 5. Grabado en la Memoria del Sicario
        self.estado_mental["fase_3_infiltracion"] = {
            "estado": "GATILLO_LISTO",
            "temporalidad_infiltracion": tf_nano_nombre,
            "choch_macro_confirmado": {
                "tipo":                 choch_macro_regreso['tipo'],
                "sensibilidad_fractal": sens_infiltracion,
                "coordenadas":          choch_macro_regreso.get('coordenadas', {}),
                "fechas_mt5":           choch_macro_regreso.get('fechas_mt5', {}),
                "historial_figuras":    choch_macro_regreso.get('historial_figuras_detectadas', [])
            },
            "micro_ob_seleccionado": {
                "calidad":           micro_ob['calidad'],
                "fvg_detectado":     micro_ob.get('fvg_detectado', False),
                "inducement_previo": micro_ob.get('inducement_previo', False),
                "proximal":          micro_ob['proximal'],
                "distal":            micro_ob['distal'],
                "fecha_ob":          self.estructura._ts_a_fecha(micro_ob['time'])
            },
            "balistica": {
                "direccion":               direccion_macro,
                "tipo_orden":              "BUY" if tipo_orden_mt5 == mt5.ORDER_TYPE_BUY else "SELL",
                "entrada_fibo50_ob":       round(entrada, 6),
                "stop_loss_distal":        round(sl, 6),
                "take_profit_liq_macro":   round(tp_target, 6),
                "ratio_riesgo_recompensa": rr
            },
            "decision_tactica": (
                f"Micro OB ({micro_ob['calidad']}) confirmado en {tf_nano_nombre}. "
                f"Entrada en Fibo50% del OB. R:R = {rr}. Gatillo institucional listo."
            )
        }

        # 6. Guardamos la balística en el contexto para que Fase 4 y 5 puedan leerla
        self._balistica_activa = {
            "entrada":    entrada,
            "sl":         sl,
            "tp":         tp_target,
            "tipo_orden": tipo_orden_mt5,
            "tf_gestion": tf_nano,
            "tf_nombre":  tf_nano_nombre
        }

    # ==========================================
    # ️ FASE 4: GESTIÓN POR ARMONÍA ORGÁNICA (AUTO-PALEAR)
    # ==========================================
    def _fase_4_gestion_armonica(self, symbol, direccion_macro, obtener_velas_func):
        """
        Gestión continua de posición abierta usando la misma lógica del motor estructural.

        Regla 1 — Avance de Escudos:
          Si hay un nuevo BOS a favor (fractal en dirección macro superado),
          el SL avanza al último mínimo/máximo fractal validado.

        Regla 2 — Protección de Capital (Cierre Automático):
          Si se detecta un ChoCh en CONTRA de la dirección macro en M5/M1,
          la posición se cierra al instante sin esperar al Comandante.
          El Comandante recibirá el reporte posterior vía Fase 5.

        El motor estructural ya sabe hacer todo esto — solo hay que
        conectar sus herramientas (_mapear_fractales, auditar_bos,
        _identificar_paso_cero) al contexto de la posición abierta.
        """
        # Recuperamos la temporalidad de gestión desde la balística de Fase 3
        bal = getattr(self, '_balistica_activa', None)
        tf_gestion  = bal['tf_gestion']  if bal else mt5.TIMEFRAME_M5
        tf_nombre   = bal['tf_nombre']   if bal else "M5"

        # 1. Verificar que hay posición abierta del Sicario
        posiciones = mt5.positions_get(symbol=symbol)
        pos_sicario = [p for p in (posiciones or []) if p.magic == 777]

        if not pos_sicario:
            self.estado_mental["fase_4_gestion"] = {
                "estado": "SIN_POSICION_ACTIVA",
                "mensaje": "No hay posición del Sicario en este activo."
            }
            return

        pos = pos_sicario[0]  # El Sicario opera 1 posición por activo

        # 2. Descarga de velas para leer estructura viva
        df_gestion = obtener_velas_func(symbol, tf_gestion, 200)
        if df_gestion is None or df_gestion.empty:
            self.estado_mental["fase_4_gestion"] = {
                "estado": "ERROR_DATOS",
                "mensaje": f"No se pudieron descargar velas de {tf_nombre}."
            }
            return

        fractales = self.estructura._mapear_fractales(df_gestion, sensibilidad=3)
        precio_actual = mt5.symbol_info_tick(symbol)
        if not precio_actual:
            return
        precio_bid = precio_actual.bid
        precio_ask = precio_actual.ask

        # ─── REGLA 1: AVANCE DE ESCUDOS (Trailing fractal condicionado a BOS con cuerpo) ───
        nuevo_sl = None
        razon_sl = ""

        minimos = sorted(fractales["minimos"], key=lambda x: x['indice'])
        maximos = sorted(fractales["maximos"], key=lambda x: x['indice'])

        if direccion_macro == "COMPRAS":
            # Para compras: un minimo se convierte en Strong Low solo si las velas posteriores
            # generaron un BOS con cierre de cuerpo por encima del maximo precedente
            for m in minimos:
                if m['precio'] <= pos.sl or m['precio'] >= precio_bid:
                    continue
                max_posteriores = [mx for mx in maximos if mx['indice'] > m['indice']]
                if not max_posteriores:
                    continue
                primer_max = max_posteriores[0]
                df_post = df_gestion.iloc[primer_max['indice']:]
                bos_confirmado = False
                for _, v in df_post.iterrows():
                    if self.estructura.auditar_bos(v, primer_max['precio'], tf_gestion, "bullish"):
                        bos_confirmado = True
                        break
                if bos_confirmado:
                    nuevo_sl = m['precio']
                    razon_sl = (f"BOS alcista con cuerpo confirmado sobre {self.motor.a_humano(self.motor.a_entero(primer_max['precio']))}. "
                                f"SL avanza a minimo fractal protegido {self.motor.a_humano(self.motor.a_entero(nuevo_sl))} "
                                f"({self.estructura._ts_a_fecha(m['time'])})")
        else:  # VENTAS
            # Para ventas: un maximo se convierte en Strong High solo si las velas posteriores
            # generaron un BOS con cierre de cuerpo por debajo del minimo precedente
            for m in maximos:
                if (pos.sl > 0 and m['precio'] >= pos.sl) or m['precio'] <= precio_ask:
                    continue
                min_posteriores = [mn for mn in minimos if mn['indice'] > m['indice']]
                if not min_posteriores:
                    continue
                primer_min = min_posteriores[0]
                df_post = df_gestion.iloc[primer_min['indice']:]
                bos_confirmado = False
                for _, v in df_post.iterrows():
                    if self.estructura.auditar_bos(v, primer_min['precio'], tf_gestion, "bearish"):
                        bos_confirmado = True
                        break
                if bos_confirmado:
                    nuevo_sl = m['precio']
                    razon_sl = (f"BOS bajista con cuerpo confirmado bajo {self.motor.a_humano(self.motor.a_entero(primer_min['precio']))}. "
                                f"SL avanza a maximo fractal protegido {self.motor.a_humano(self.motor.a_entero(nuevo_sl))} "
                                f"({self.estructura._ts_a_fecha(m['time'])})")

        sl_modificado = False
        if nuevo_sl is not None:
            req_sl = {
                "action":   mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "sl":       float(nuevo_sl),
                "tp":       float(pos.tp)
            }
            res_sl = mt5.order_send(req_sl)
            sl_modificado = (res_sl is not None and res_sl.retcode == mt5.TRADE_RETCODE_DONE)

        # ─── REGLA 2: CIERRE POR ChoCh EN CONTRA ─────────────────────────
        direccion_contra = "VENTAS" if direccion_macro == "COMPRAS" else "COMPRAS"
        choch_contra = None

        for sens in range(2, 6):
            frac_choch = self.estructura._mapear_fractales(df_gestion, sensibilidad=sens)
            candidato = self.estructura._identificar_paso_cero(
                df_gestion, tf_gestion, direccion_contra, frac_choch
            )
            if candidato and candidato.get("tipo"):
                choch_contra = candidato
                break

        cierre_ejecutado = False
        motivo_cierre = ""

        if choch_contra:
            # ChoCh en contra detectado → cierre automático inmediato
            precio_cierre = precio_bid if pos.type == mt5.ORDER_TYPE_BUY else precio_ask
            req_cierre = {
                "action":      mt5.TRADE_ACTION_DEAL,
                "symbol":      symbol,
                "volume":      pos.volume,
                "type":        mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                "price":       float(precio_cierre),
                "position":    pos.ticket,
                "magic":       777,
                "comment":     "SICARIO_CHOCH_CONTRA",
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res_cierre = mt5.order_send(req_cierre)
            cierre_ejecutado = (res_cierre is not None and res_cierre.retcode == mt5.TRADE_RETCODE_DONE)
            motivo_cierre = (
                f"ChoCh {direccion_contra} detectado en {tf_nombre}. "
                f"Figura: {choch_contra['tipo']}. Armonía rota — capital protegido."
            )

        # 3. Resultado de ganancia/pérdida flotante
        ganancia_flotante = pos.profit

        # 4. Grabado en la Memoria del Sicario
        self.estado_mental["fase_4_gestion"] = {
            "estado": "CERRADO_POR_CHOCH" if cierre_ejecutado else "POSICION_ACTIVA",
            "posicion": {
                "ticket":         pos.ticket,
                "tipo":           "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                "precio_apertura": pos.price_open,
                "sl_anterior":    pos.sl,
                "tp":             pos.tp,
                "ganancia_flotante_usd": round(ganancia_flotante, 2)
            },
            "avance_de_escudos": {
                "sl_modificado":  sl_modificado,
                "nuevo_sl":       round(nuevo_sl, 6) if nuevo_sl else None,
                "razon":          razon_sl if sl_modificado else "Sin nuevo BOS a favor."
            },
            "choch_en_contra": {
                "detectado":      choch_contra is not None,
                "tipo":           choch_contra['tipo'] if choch_contra else None,
                "coordenadas":    choch_contra.get('coordenadas', {}) if choch_contra else {},
                "fechas_mt5":     choch_contra.get('fechas_mt5', {}) if choch_contra else {}
            },
            "cierre_automatico": {
                "ejecutado":      cierre_ejecutado,
                "motivo":         motivo_cierre,
                "timestamp":      datetime.now().strftime('%Y-%m-%d %H:%M:%S') if cierre_ejecutado else None
            },
            "timestamp_actualizacion": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # Emitimos comunicación si hubo evento relevante
        if cierre_ejecutado:
            resultado = "GANANCIA" if ganancia_flotante > 0 else "PÉRDIDA"
            self._fase_5_emitir_comunicacion(
                "CIERRE",
                {"symbol": symbol, "resultado": resultado,
                 "ganancia_usd": round(ganancia_flotante, 2), "motivo": motivo_cierre}
            )
        elif sl_modificado:
            self._fase_5_emitir_comunicacion(
                "PROTECCION",
                {"symbol": symbol, "nuevo_sl": round(nuevo_sl, 6), "razon": razon_sl}
            )

    # ==========================================
    #  FASE 5: PROTOCOLO DE COMUNICACIONES Y AUDITORÍA
    # ==========================================
    def _fase_5_emitir_comunicacion(self, tipo_alerta, datos_operacion):
        """
        Silencio de radio por defecto. Solo emite 3 tipos de alerta permitidas:

          "ASALTO"     → "Asalto ejecutado en el POI. Dinero en juego."
          "PROTECCION" → "Protección activada (BOS micro validado, riesgo cero)."
          "CIERRE"     → "Operación cerrada (Ganancia/Pérdida de X USD)."

        Modo Interactivo: si self._modo_interactivo es True,
          envía la alerta y espera confirmación del trader antes de ejecutar
          el asalto. Si no responde en self._timeout_interactivo segundos,
          el Sicario procede solo.
        """
        if self.telegram is None:
            return  # Sin canal de comunicación — silencio total

        symbol = datos_operacion.get("symbol", "???")

        if tipo_alerta == "ASALTO":
            bal = datos_operacion.get("balistica", {})
            mensaje = (
                f"[SICARIO] <b>ASALTO EJECUTADO: {symbol}</b>\n"
                f"Dirección: {bal.get('tipo_orden', '?')} | "
                f"Entrada: {bal.get('entrada_fibo50_ob', '?')}\n"
                f"SL: {bal.get('stop_loss_distal', '?')} | "
                f"TP: {bal.get('take_profit_liq_macro', '?')}\n"
                f"R:R = {bal.get('ratio_riesgo_recompensa', '?')}\n"
                f"Micro OB ({datos_operacion.get('calidad_ob', '?')}) — "
                f"Capital en mercado."
            )

        elif tipo_alerta == "PROTECCION":
            mensaje = (
                f"[SICARIO] <b>PROTECCION ACTIVADA: {symbol}</b>\n"
                f"BOS micro validado — riesgo cero (Break Even).\n"
                f"Nuevo SL: {datos_operacion.get('nuevo_sl', '?')}\n"
                f"Razón: {datos_operacion.get('razon', '?')}"
            )

        elif tipo_alerta == "CIERRE":
            tag_res = "[GANANCIA]" if datos_operacion.get("resultado") == "GANANCIA" else "[PERDIDA]"
            mensaje = (
                f"[SICARIO] {tag_res} <b>OPERACION CERRADA: {symbol}</b>\n"
                f"Resultado: {datos_operacion.get('resultado', '?')} "
                f"| {datos_operacion.get('ganancia_usd', 0)} USD\n"
                f"Motivo: {datos_operacion.get('motivo', 'No especificado')}"
            )

        else:
            return  # Tipo de alerta desconocido — silencio

        self.telegram.enviar_telegram(mensaje)

    def _modo_interactivo_esperar_confirmacion(self, symbol, balistica):
        """
        En modo interactivo: envía la alerta de asalto y espera
        self._timeout_interactivo segundos antes de proceder solo.
        Devuelve True si debe ejecutar, False si se canceló externamente.
        (La cancelación externa se implementará vía flag compartido con el Comandante.)
        """
        self._fase_5_emitir_comunicacion("ASALTO", {
            "symbol": symbol,
            "balistica": balistica,
            "calidad_ob": self.estado_mental.get("fase_3_infiltracion", {})
                              .get("micro_ob_seleccionado", {}).get("calidad", "?")
        })

        if not getattr(self, '_modo_interactivo', False):
            return True  # Modo autónomo — ejecuta directamente

        timeout = getattr(self, '_timeout_interactivo', 30)
        self.telegram.enviar_telegram(
            f"[MODO INTERACTIVO] <b>CONFIRMACION REQUERIDA: {symbol}</b>\n"
            f"Esperando confirmación del operador ({timeout}s).\n"
            f"Sin respuesta -> ejecución automática institucional."
        )
        time.sleep(timeout)
        return True  # Por seguridad, si nadie cancela, ejecuta

    def generar_json_estado_mental(self):
        """
        Empaqueta la variable self.estado_mental en un JSON estructurado 
        para que pueda ser auditado visualmente antes o durante la ejecución.
        """
        return json.dumps(self.estado_mental, indent=4, ensure_ascii=False)

    def _generar_reporte_csv(self, datos_mision):
        """
        Genera el reporte final de la actuación del Sicario y lo envía
        al AuditorCSV de ALFA para actualizar el historial de ML.

        Columnas: símbolo, dirección, fase_max_alcanzada, calidad_ob,
                  rr, resultado_usd, timestamp_apertura, timestamp_cierre.
        """
        if self.auditor is None:
            return  # Sin auditor configurado — operamos en silencio

        f4  = self.estado_mental.get("fase_4_gestion", {})
        f3  = self.estado_mental.get("fase_3_infiltracion", {})
        bal = f3.get("balistica", {})
        ob  = f3.get("micro_ob_seleccionado", {})

        self.auditor.registrar_evento(
            fecha       = datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            activo      = datos_mision.get("symbol", "?"),
            tf_macro    = datos_mision.get("tf_macro", "H1"),
            direccion   = datos_mision.get("direccion", "?"),
            sens        = f3.get("choch_macro_confirmado", {}).get("sensibilidad_fractal", 0),
            bos         = 0,  # Rellenado por el AuditorCSV según contexto
            mitigacion  = ob.get("calidad", "NO_OB"),
            spread      = 0,  # El Sicario no mide spread — lo hace el Comandante
            resultado   = f"{'GANANCIA' if f4.get('posicion', {}).get('ganancia_flotante_usd', 0) > 0 else 'PERDIDA'}"
                          f"_{round(f4.get('posicion', {}).get('ganancia_flotante_usd', 0), 2)}_USD"
        )

 # ==========================================
#  INTERFAZ GRÁFICA DEL SICARIO (Zona de Pruebas)
# ==========================================
class InterfazAuditoriaSicario:
    def __init__(self, root):
        self.root = root
        self.root.title("ALFA INC. - Auditoría del Sicario (Micro-Scalper)")
        self.root.geometry("700x750")
        self.root.configure(bg="#050505")
        
        self.activo_var = tk.StringVar(value="BTCUSDm")
        self._construir_ui()

    def _construir_ui(self):
        f_top = tk.Frame(self.root, bg="#111", pady=15)
        f_top.pack(fill=tk.X)
        tk.Label(f_top, text=" PRUEBA DE EMPLEADO: EL SICARIO", font=("Segoe UI", 14, "bold"), bg="#111", fg="#ff0055").pack()

        f_controles = tk.Frame(self.root, bg="#0a0a0a", pady=10)
        f_controles.pack(fill=tk.X, padx=15)
        tk.Label(f_controles, text="Activo a infiltrar:", bg="#0a0a0a", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Entry(f_controles, textvariable=self.activo_var, bg="#1a1a1a", fg="white").pack(side=tk.LEFT, padx=5)
        
        tk.Button(f_controles, text="EJECUTAR PATRULLAJE AUTÓNOMO", bg="#ff003c", fg="white", font=("Segoe UI", 10, "bold"), command=self.detonar_prueba).pack(side=tk.RIGHT, padx=5)

        self.txt_consola = tk.Text(self.root, height=12, bg="#0a0a0a", fg="#aaaaaa", font=("Consolas", 9), relief=tk.FLAT)
        self.txt_consola.pack(fill=tk.X, padx=15, pady=5)

        tk.Label(self.root, text=" ESTADO MENTAL DEL SICARIO (JSON EN VIVO)", bg="#050505", fg="#ffaa00", font=("Segoe UI", 10, "bold")).pack(pady=5)
        
        self.txt_json = tk.Text(self.root, height=18, bg="#001100", fg="#00ff00", font=("Consolas", 10), relief=tk.FLAT)
        self.txt_json.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

    def log(self, msg):
        self.txt_consola.insert(tk.END, msg + "\n")
        self.txt_consola.see(tk.END)
        self.root.update()

    def detonar_prueba(self):
        self.txt_consola.delete(1.0, tk.END)
        self.txt_json.delete(1.0, tk.END)
        
        if not mt5.initialize():
            self.log("️ ERROR: MetaTrader 5 no conectado.")
            return

        activo = self.activo_var.get()
        # Lanzamos el proceso en un hilo secundario para no congelar la UI
        threading.Thread(target=self._hilo_sicario, args=(activo,), daemon=True).start()

    def _hilo_sicario(self, simbolo_prueba):
        self.log(f"Iniciando auditoría Fase 1 para {simbolo_prueba}...\n")
        
        try:
            #  Intentamos importar tu Motor Heredado que sí funciona
            try:
                from MOTOR_ESTRUCTURAL_MICRO_HEREDADO import MotorAritmetico, MotorEstructural
            except ImportError:
                # Fallback al nombre que tenías originalmente
                from motor_estructural_micro_corregido import MotorAritmetico, MotorEstructural

            calculadora = MotorAritmetico(tipo_activo="CRIPTO" if "BTC" in simbolo_prueba else "FOREX")

            vars_ui_mock = {
                'bos_cripto':  1, 'bos_forex':  1,
                'sp_sens_min': 2, 'sp_sens_max': 15,
                'sp_tol_eqh':  2.0, 'sp_tol_arro': 1.5, 'sp_min_arro': 4
            }

            def puente_obtener_velas(sim, tf, cant):
                r = mt5.copy_rates_from_pos(sim, tf, 0, cant)
                return pd.DataFrame(r) if r is not None else None

            # Conectamos el log del Topógrafo a la consola de la UI
            topografo = MotorEstructural(
                calculadora,
                lambda x: self.log(f"   [Topógrafo] {x}"),
                vars_ui_mock
            )

            self.log("️ Solicitando escaneo macro al Topógrafo (H1/M15)...")
            reporte_macro = topografo.generar_reporte_topografico(simbolo_prueba)

            if reporte_macro and reporte_macro.get("zonas_validas"):
                poi_real = reporte_macro["zonas_validas"][0]
                poi_real['tf_macro']   = "H1"
                poi_real['direccion']  = reporte_macro["direccion_macro"]
                poi_real['tp_liquidez'] = reporte_macro["liquidez_externa"].get("precio", 0.0)
                liquidez_real = reporte_macro.get("mapa_liquidez_h1", {})

                tick = mt5.symbol_info_tick(simbolo_prueba)
                precio_vivo = tick.last if tick.last > 0 else tick.bid

                self.log(f"\n Datos reales extraídos. Precio vivo: {precio_vivo}")
                self.log(f"POI recibido: {poi_real.get('tipo', 'Desconocido')} -> {poi_real.get('proximal', 0)} / {poi_real.get('distal', 0)}")
                self.log("Despertando al Sicario...\n")

                # Inyección directa de datos al Sicario
                sicario = ActorSicario(calculadora, topografo, None, None)
                sicario.patrullaje_autonomo(
                    simbolo_prueba, precio_vivo, poi_real, liquidez_real, puente_obtener_velas
                )

                self.log(" ESTADO MENTAL DEL SICARIO -> Generado en panel inferior.")
                payload_formateado = sicario.generar_json_estado_mental()
                self.txt_json.insert(tk.END, payload_formateado)
            else:
                self.log("\n️ El Topógrafo no encontró zonas válidas en este momento.")

        except Exception as e:
            self.log(f" Error durante la ejecución: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = InterfazAuditoriaSicario(root)
    root.mainloop()