import tkinter as tk
from tkinter import ttk, messagebox
import MetaTrader5 as mt5
import pandas as pd
import threading
import json
import math
from datetime import datetime

# ==========================================
#  NÚCLEO MATEMÁTICO (La Calculadora)
# ==========================================
class MotorAritmetico:
    """
    Núcleo de Punto Fijo y Suma Compensada para ALFA 4.0.
    Erradica el error de coma flotante IEEE 754.
    """
    def __init__(self, tipo_activo="FOREX"):
        self.escala = 100000 if tipo_activo == "FOREX" else 100000000

    def a_entero(self, valor_float):
        if valor_float is None or math.isnan(valor_float): return 0
        return int(round(valor_float * self.escala))

    def a_humano(self, valor_entero):
        return valor_entero / self.escala

    def suma_kahan(self, valores_float):
        suma = 0.0
        c = 0.0 
        for v in valores_float:
            y = v - c
            t = suma + y
            c = (t - suma) - y
            suma = t
        return suma


# ==========================================
# ️‍️ EMPLEADO 1: MOTOR ESTRUCTURAL (El Analista Cuantitativo)
# ==========================================
class MotorEstructural:
    """
    Topógrafo de ALFA Inc. 
    Ejecuta el escaneo en cascada: D1 -> H4 (Freno Paso Cero + Liquidez) -> H1.
    """
    def __init__(self, motor_aritmetico, logger_callback, vars_ui=None):
        self.motor = motor_aritmetico
        self.log = logger_callback
        self.vars = vars_ui if vars_ui else {}

    # ==========================================
    # ️ HERRAMIENTAS DE AUDITORÍA Y MATEMÁTICA
    # ==========================================
    def _pips_a_precio(self, symbol, valor_ui):
        """ Traductor Multi-Activo Inteligente """
        info = mt5.symbol_info(symbol)
        if not info: 
            return 0.0002
            
        multiplicador = 10
        if "BTC" in symbol or "ETH" in symbol:
            multiplicador = 1000
        elif "XAU" in symbol:
            multiplicador = 100
        elif "JPY" in symbol:
            multiplicador = 10
            
        return valor_ui * multiplicador * info.point
    
    def _ts_a_fecha(self, timestamp):
        """ Convierte el Unix Time de MT5 a Fecha Legible para el CEO """
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')

    def auditar_bos(self, vela_ruptura, nivel_muro, timeframe, tipo_bos="bullish"):
        """
        Auditoria de BOS Institucional (Regla Capital Trading / Cris Campoz):
        El quiebre estructural REQUIERE cierre estricto de cuerpo por fuera del nivel en todas
        las temporalidades. Rupturas unicamente con mecha son clasificadas como Sweep (toma de liquidez).
        """
        if tipo_bos == "bullish":
            return float(vela_ruptura['close']) > float(nivel_muro)
        else:
            return float(vela_ruptura['close']) < float(nivel_muro)

    def auditar_sweep(self, vela_ruptura, nivel_muro, tipo_sweep="bullish", max_pips=10.0, point_size=0.0001):
        """
        Auditoria de Sweep / Barrido de Liquidez Institucional (Regla de los 10 Pips - Cris Campoz):
        Detecta cuando la mecha cruza el nivel pero el cuerpo cierra por dentro del rango.
        Si max_pips esta definido, valida que la penetracion de la mecha no exceda el umbral
        de neutralizacion controlada (10 pips estandar en Forex Majors).
        """
        cierre = float(vela_ruptura['close'])
        nivel = float(nivel_muro)

        if tipo_sweep == "bullish":
            alto = float(vela_ruptura['high'])
            if alto > nivel and cierre <= nivel:
                penetracion_pips = (alto - nivel) / (point_size if point_size > 0 else 0.0001)
                return penetracion_pips <= max_pips
            return False
        else:
            bajo = float(vela_ruptura['low'])
            if bajo < nivel and cierre >= nivel:
                penetracion_pips = (nivel - bajo) / (point_size if point_size > 0 else 0.0001)
                return penetracion_pips <= max_pips
            return False

    def _mapear_fractales(self, df, sensibilidad):
        fractales = {"maximos": [], "minimos": []}
        for i in range(sensibilidad, len(df) - sensibilidad):
            ventana_high = df['high'].iloc[i-sensibilidad : i+sensibilidad+1]
            ventana_low = df['low'].iloc[i-sensibilidad : i+sensibilidad+1]
            vela_centro = df.iloc[i]
            
            if vela_centro['high'] == ventana_high.max():
                fractales["maximos"].append({"time": vela_centro['time'], "precio": vela_centro['high'], "indice": i, "vela": vela_centro})
            if vela_centro['low'] == ventana_low.min():
                fractales["minimos"].append({"time": vela_centro['time'], "precio": vela_centro['low'], "indice": i, "vela": vela_centro})
        return fractales

    # ==========================================
    #  EL FRENO ESTRUCTURAL Y LA LIQUIDEZ
    # ==========================================
    def _identificar_paso_cero(self, df, timeframe, direccion, fractales, mitigacion_d1=None):
        minimos = fractales["minimos"]
        maximos = fractales["maximos"]
        candidatos = [] 

        # =================================================================
        # ️ FASE 1: TU MOTOR EXACTO E INTOCABLE (Asegura ChoCh 1 y 2)
        # =================================================================
        if direccion == "COMPRAS":
            if len(minimos) >= 2:
                for i in range(len(minimos) - 1, 0, -1):
                    L2 = minimos[i]; L1 = minimos[i-1]    
                    if L2['precio'] >= L1['precio']: continue 
                    
                    H1_candidatos = [m for m in maximos if L1['indice'] < m['indice'] < L2['indice']]
                    if not H1_candidatos: continue
                    H1 = max(H1_candidatos, key=lambda x: x['precio']) 
                    
                    df_post_L2 = df.iloc[L2['indice'] + 1:]
                    for idx, vela in df_post_L2.iterrows():
                        if self.auditar_bos(vela, H1['precio'], timeframe, "bullish"): 
                            candidatos.append({
                                "indice_origen": L1['indice'], 
                                "tipo": "W (ChoCh Alcista)",
                                "coordenadas": {
                                    "Pierna_Izq_L1": self.motor.a_humano(self.motor.a_entero(L1['precio'])),
                                    "Vertice_H1": self.motor.a_humano(self.motor.a_entero(H1['precio'])),
                                    "Barrido_L2": self.motor.a_humano(self.motor.a_entero(L2['precio']))
                                },
                                "fechas_mt5": {
                                    "Fecha_L1": self._ts_a_fecha(L1['time']),
                                    "Fecha_H1": self._ts_a_fecha(H1['time']),
                                    "Fecha_L2": self._ts_a_fecha(L2['time'])
                                }
                            })
                            break 
            
            if candidatos:
                candidatos_ordenados = sorted(candidatos, key=lambda x: x['indice_origen'], reverse=True)
                mejor_choch = candidatos_ordenados[0]
                
                # Sellamos los 2 primeros ChoChs generados por tu motor
                historial_base = []
                for c in candidatos_ordenados:
                    if not historial_base or c['indice_origen'] < historial_base[-1]['indice_origen']:
                        historial_base.append(c)
                        if len(historial_base) == 2:
                            break

                # =================================================================
                #  FASE 2: RESCATE AISLADO DEL 3ER CHOCH (El del 24 de feb)
                # =================================================================
                if len(historial_base) == 2:
                    techo = historial_base[-1]['indice_origen']
                    minimos_hist = [m for m in minimos if m['indice'] < techo]
                    
                    if len(minimos_hist) >= 2:
                        for i in range(len(minimos_hist) - 1, 0, -1):
                            L2_hist = minimos_hist[i]
                            
                            # Miramos hasta 5 velas atrás solo en el pasado para saltar el micro-bache
                            for j in range(i-1, max(-1, i-6), -1):
                                L1_hist = minimos_hist[j]
                                if L2_hist['precio'] >= L1_hist['precio']: continue
                                
                                H1_cands = [m for m in maximos if L1_hist['indice'] < m['indice'] < L2_hist['indice']]
                                if not H1_cands: continue
                                H1_hist = max(H1_cands, key=lambda x: x['precio'])
                                
                                df_post = df.iloc[L2_hist['indice'] + 1 : techo + 10]
                                roto = False
                                for _, v in df_post.iterrows():
                                    if self.auditar_bos(v, H1_hist['precio'], timeframe, "bullish"):
                                        roto = True; break
                                        
                                if roto:
                                    historial_base.append({
                                        "indice_origen": L1_hist['indice'],
                                        "coordenadas": {
                                            "Pierna_Izq_L1": self.motor.a_humano(self.motor.a_entero(L1_hist['precio'])),
                                            "Vertice_H1": self.motor.a_humano(self.motor.a_entero(H1_hist['precio'])),
                                            "Barrido_L2": self.motor.a_humano(self.motor.a_entero(L2_hist['precio']))
                                        },
                                        "fechas_mt5": {
                                            "Fecha_L1": self._ts_a_fecha(L1_hist['time']),
                                            "Fecha_H1": self._ts_a_fecha(H1_hist['time']),
                                            "Fecha_L2": self._ts_a_fecha(L2_hist['time'])
                                        }
                                    })
                                    break 
                            
                            if len(historial_base) == 3: break

                # Empaquetado final forzado
                mejor_choch['historial_figuras_detectadas'] = []
                for h in historial_base:
                    mejor_choch['historial_figuras_detectadas'].append({
                        "coordenadas": h['coordenadas'],
                        "fechas": h['fechas_mt5']
                    })
                return mejor_choch

        elif direccion == "VENTAS":
            if len(maximos) >= 2:
                for i in range(len(maximos) - 1, 0, -1):
                    H2 = maximos[i]; H1 = maximos[i-1]    
                    if H2['precio'] <= H1['precio']: continue 
                    
                    L1_candidatos = [m for m in minimos if H1['indice'] < m['indice'] < H2['indice']]
                    if not L1_candidatos: continue
                    L1 = min(L1_candidatos, key=lambda x: x['precio']) 
                    
                    df_post_H2 = df.iloc[H2['indice'] + 1:]
                    for idx, vela in df_post_H2.iterrows():
                        if self.auditar_bos(vela, L1['precio'], timeframe, "bearish"): 
                            candidatos.append({
                                "indice_origen": H1['indice'], 
                                "tipo": "M (ChoCh Bajista)",
                                "coordenadas": {
                                    "Pierna_Izq_H1": self.motor.a_humano(self.motor.a_entero(H1['precio'])),
                                    "Vertice_L1": self.motor.a_humano(self.motor.a_entero(L1['precio'])),
                                    "Barrido_H2": self.motor.a_humano(self.motor.a_entero(H2['precio']))
                                },
                                "fechas_mt5": {
                                    "Fecha_H1": self._ts_a_fecha(H1['time']),
                                    "Fecha_L1": self._ts_a_fecha(L1['time']),
                                    "Fecha_H2": self._ts_a_fecha(H2['time'])
                                }
                            })
                            break 
            
            if candidatos:
                candidatos_ordenados = sorted(candidatos, key=lambda x: x['indice_origen'], reverse=True)
                mejor_choch = candidatos_ordenados[0]
                
                historial_base = []
                for c in candidatos_ordenados:
                    if not historial_base or c['indice_origen'] < historial_base[-1]['indice_origen']:
                        historial_base.append(c)
                        if len(historial_base) == 2:
                            break

                if len(historial_base) == 2:
                    techo = historial_base[-1]['indice_origen']
                    maximos_hist = [m for m in maximos if m['indice'] < techo]
                    
                    if len(maximos_hist) >= 2:
                        for i in range(len(maximos_hist) - 1, 0, -1):
                            H2_hist = maximos_hist[i]
                            
                            for j in range(i-1, max(-1, i-6), -1):
                                H1_hist = maximos_hist[j]
                                if H2_hist['precio'] <= H1_hist['precio']: continue
                                
                                L1_cands = [m for m in minimos if H1_hist['indice'] < m['indice'] < H2_hist['indice']]
                                if not L1_cands: continue
                                L1_hist = min(L1_cands, key=lambda x: x['precio'])
                                
                                df_post = df.iloc[H2_hist['indice'] + 1 : techo + 10]
                                roto = False
                                for _, v in df_post.iterrows():
                                    if self.auditar_bos(v, L1_hist['precio'], timeframe, "bearish"):
                                        roto = True; break
                                        
                                if roto:
                                    historial_base.append({
                                        "indice_origen": H1_hist['indice'],
                                        "coordenadas": {
                                            "Pierna_Izq_H1": self.motor.a_humano(self.motor.a_entero(H1_hist['precio'])),
                                            "Vertice_L1": self.motor.a_humano(self.motor.a_entero(L1_hist['precio'])),
                                            "Barrido_H2": self.motor.a_humano(self.motor.a_entero(H2_hist['precio']))
                                        },
                                        "fechas_mt5": {
                                            "Fecha_H1": self._ts_a_fecha(H1_hist['time']),
                                            "Fecha_L1": self._ts_a_fecha(L1_hist['time']),
                                            "Fecha_H2": self._ts_a_fecha(H2_hist['time'])
                                        }
                                    })
                                    break 
                            
                            if len(historial_base) == 3: break

                mejor_choch['historial_figuras_detectadas'] = []
                for h in historial_base:
                    mejor_choch['historial_figuras_detectadas'].append({
                        "coordenadas": h['coordenadas'],
                        "fechas": h['fechas_mt5']
                    })
                return mejor_choch
                            
        return {"indice_origen": 0, "tipo": None, "coordenadas": {}}
    
    def escanear_trampas(self, symbol, df, rango_max, rango_min, fibo_50, direccion, fractales, idx_inicio):
        """ MOTOR DE LIQUIDEZ INSTITUCIONAL: GEOMETRÍA ELÁSTICA (TradingView Matched) """
        try:
            # Ampliamos la tolerancia base para BTC basado en el gap de 81 pts de tu análisis
            tol_eqh = self._pips_a_precio(symbol, float(self.vars.get('sp_tol_eqh', 15.0))) 
            tol_arro = self._pips_a_precio(symbol, float(self.vars.get('sp_tol_arro', 10.0)))
            min_velas = int(self.vars.get('sp_min_arro', 4))
        except Exception:
            tol_eqh, tol_arro, min_velas = 85.0, 50.0, 4 # Tolerancias fuertes por defecto para BTC

        mapa = {
            "induccion_n": [], "picos_v": [], "trendline": [], 
            "arrogante": [], "equal_nodes": [], "consolidada": [],
            "liquidez_externa": {"equal_nodes": [], "picos_v": []} 
        }

        #  CAJA DE TIEMPO (Muro Fantasma)
        max_int = [m for m in fractales["maximos"] if m['indice'] >= idx_inicio]
        min_int = [m for m in fractales["minimos"] if m['indice'] >= idx_inicio]
        nodos = max_int if direccion == "VENTAS" else min_int

        if not nodos: return mapa

        # =================================================================
        #  1. EQUAL NODES (Tolerancia Dinámica)
        # Permite detectar los Equal Lows con el gap de 81 puntos que marcaste
        # =================================================================
        usados = set()
        for i in range(len(nodos)):
            if i in usados: continue
            grupo_actual = [nodos[i]]
            for j in range(i + 1, len(nodos)):
                if j in usados: continue
                if abs(nodos[i]['precio'] - nodos[j]['precio']) <= tol_eqh:
                    grupo_actual.append(nodos[j])
                    usados.add(j)
            
            if len(grupo_actual) >= 2:
                # Se itera la temporalidad para dar contexto al CEO
                p_fmt = " / ".join([str(self.motor.a_humano(self.motor.a_entero(n['precio']))) for n in grupo_actual])
                f_fmt = " / ".join([str(self._ts_a_fecha(n['time'])) for n in grupo_actual])
                eq_data = {"precios": p_fmt, "fechas": f_fmt}
                
                mapa["equal_nodes"].append(eq_data)
                mapa["liquidez_externa"]["equal_nodes"].append(eq_data)
                mapa["consolidada"].extend([n['precio'] for n in grupo_actual])

        # =================================================================
        #  2. INDUCCIÓN EN N (El último respiro)
        # =================================================================
        if direccion == "VENTAS":
            inductores = [m for m in max_int if m['precio'] < fibo_50]
            if inductores:
                nodo_reciente = max(inductores, key=lambda x: x['time']) # El más reciente temporalmente
                mapa["induccion_n"].append({"precio": self.motor.a_humano(self.motor.a_entero(nodo_reciente['precio'])), "fecha": self._ts_a_fecha(nodo_reciente['time'])})
                mapa["consolidada"].append(nodo_reciente['precio'])
        else:
            inductores = [m for m in min_int if m['precio'] > fibo_50]
            if inductores:
                nodo_reciente = max(inductores, key=lambda x: x['time']) # El más reciente temporalmente
                mapa["induccion_n"].append({"precio": self.motor.a_humano(self.motor.a_entero(nodo_reciente['precio'])), "fecha": self._ts_a_fecha(nodo_reciente['time'])})
                mapa["consolidada"].append(nodo_reciente['precio'])

        # =================================================================
        #  3. PICOS V (El Barrido Agresivo)
        # Basado en tu pico de 76011. Buscamos rechazo fuerte en la mecha.
        # =================================================================
        for nodo in nodos:
            vela = nodo['vela']
            cuerpo = abs(vela['close'] - vela['open'])
            mecha_sup = vela['high'] - max(vela['close'], vela['open'])
            mecha_inf = min(vela['close'], vela['open']) - vela['low']
            
            es_pico = False
            if direccion == "VENTAS" and mecha_sup > (cuerpo * 1.5): es_pico = True
            elif direccion == "COMPRAS" and mecha_inf > (cuerpo * 1.5): es_pico = True

            if es_pico:
                pico_data = {"precio": self.motor.a_humano(self.motor.a_entero(nodo['precio'])), "fecha": self._ts_a_fecha(nodo['time'])}
                mapa["picos_v"].append(pico_data)
                mapa["liquidez_externa"]["picos_v"].append(pico_data)
                mapa["consolidada"].append(nodo['precio'])

        # =================================================================
        #  4. TRENDLINE (Geometría Elástica)
        # Permite que la línea se "curve" o acelere como en tus datos de TV.
        # =================================================================
        if len(nodos) >= 3:
            trend_actual = [nodos[0], nodos[1]]
            for i in range(2, len(nodos)):
                n1, n2, n3 = trend_actual[-2], trend_actual[-1], nodos[i]
                
                # Verificamos dirección básica (mínimos más altos o máximos más bajos)
                dir_ok = False
                if direccion == "VENTAS" and n2['precio'] < n1['precio'] and n3['precio'] < n2['precio']: dir_ok = True
                elif direccion == "COMPRAS" and n2['precio'] > n1['precio'] and n3['precio'] > n2['precio']: dir_ok = True
                
                if dir_ok:
                    # Cálculo de aceleración elástica
                    velas_d1 = max(1, n2['indice'] - n1['indice'])
                    m1 = abs(n2['precio'] - n1['precio']) / velas_d1
                    
                    velas_d2 = max(1, n3['indice'] - n2['indice'])
                    m2 = abs(n3['precio'] - n2['precio']) / velas_d2
                    
                    #  Tolerancia de distorsión armónica (Acepta entre 40% más lento o 200% más rápido)
                    if m1 > 0 and (0.4 <= (m2 / m1) <= 3.0):
                        trend_actual.append(n3)
                        continue

                # Si se rompe la armonía o la dirección, cerramos la línea y evaluamos si sirve
                if len(trend_actual) >= 3:
                    p_ini = self.motor.a_humano(self.motor.a_entero(trend_actual[0]['precio']))
                    p_fin = self.motor.a_humano(self.motor.a_entero(trend_actual[-1]['precio']))
                    f_ini = self._ts_a_fecha(trend_actual[0]['time'])
                    f_fin = self._ts_a_fecha(trend_actual[-1]['time'])
                    
                    mapa["trendline"].append({"conexion_precios": f"{p_ini} -> {p_fin}", "conexion_fechas": f"{f_ini} -> {f_fin}", "toques": len(trend_actual)})
                    mapa["consolidada"].extend([n['precio'] for n in trend_actual])
                
                # Reiniciamos la búsqueda con los últimos dos nodos
                trend_actual = [nodos[i-1], nodos[i]]

            # Validación final por si la línea llegó viva hasta el final
            if len(trend_actual) >= 3:
                p_ini = self.motor.a_humano(self.motor.a_entero(trend_actual[0]['precio']))
                p_fin = self.motor.a_humano(self.motor.a_entero(trend_actual[-1]['precio']))
                f_ini = self._ts_a_fecha(trend_actual[0]['time'])
                f_fin = self._ts_a_fecha(trend_actual[-1]['time'])
                
                mapa["trendline"].append({"conexion_precios": f"{p_ini} -> {p_fin}", "conexion_fechas": f"{f_ini} -> {f_fin}", "toques": len(trend_actual)})
                mapa["consolidada"].extend([n['precio'] for n in trend_actual])

        # =================================================================
        #  5. ARROGANTE (Compresión)
        # Basado en tu escalera 70491 -> 70490 (agrupación en el tiempo)
        # =================================================================
        for i in range(idx_inicio, len(df) - min_velas):
            ventana = df.iloc[i : i + min_velas]
            if direccion == "VENTAS":
                idx_max = ventana['high'].idxmax()
                vela_max = ventana.loc[idx_max]
                max_abs = vela_max['high']
                
                # Tolerancia de compresión (las velas no superan la barrera por X pips)
                if all(max_abs - vela['high'] <= tol_arro for _, vela in ventana.iterrows()):
                    mapa["arrogante"].append({"precio": self.motor.a_humano(self.motor.a_entero(max_abs)), "fecha": self._ts_a_fecha(vela_max['time'])})
                    mapa["consolidada"].append(max_abs)
            else:
                idx_min = ventana['low'].idxmin()
                vela_min = ventana.loc[idx_min]
                min_abs = vela_min['low']
                
                if all(vela['low'] - min_abs <= tol_arro for _, vela in ventana.iterrows()):
                    mapa["arrogante"].append({"precio": self.motor.a_humano(self.motor.a_entero(min_abs)), "fecha": self._ts_a_fecha(vela_min['time'])})
                    mapa["consolidada"].append(min_abs)

        # Limpiar diccionarios duplicados manteniendo el orden para JSON
        for clave in ["induccion_n", "arrogante"]:
            mapa[clave] = [dict(t) for t in {tuple(d.items()) for d in mapa[clave]}]
            
        import json
        mapa["equal_nodes"] = [json.loads(t) for t in {json.dumps(d, sort_keys=True) for d in mapa["equal_nodes"]}]
        mapa["trendline"] = [json.loads(t) for t in {json.dumps(d, sort_keys=True) for d in mapa["trendline"]}]
        mapa["liquidez_externa"]["equal_nodes"] = [json.loads(t) for t in {json.dumps(d, sort_keys=True) for d in mapa["liquidez_externa"]["equal_nodes"]}]
        mapa["liquidez_externa"]["picos_v"] = [dict(t) for t in {tuple(d.items()) for d in mapa["liquidez_externa"]["picos_v"]}]
            
        mapa["consolidada"] = sorted(list(set(mapa["consolidada"])))
        return mapa

    def auditar_order_flow(self, fractales, direccion_actual, indice_choch, symbol):
        maximos = fractales["maximos"]
        minimos = fractales["minimos"]
        
        bos_tendencia_previa = 0
        bos_tendencia_actual = 0
        coordenadas_rupturas = []
        
        def _formatear_bos(nodo):
            return {
                "precio": self.motor.a_humano(self.motor.a_entero(nodo['precio'])),
                "fecha": self._ts_a_fecha(nodo['time'])
            }

        if direccion_actual == "COMPRAS":
            max_previos = [m for m in maximos if m['indice'] < indice_choch][-5:]
            if len(max_previos) >= 2:
                for i in range(1, len(max_previos)):
                    if max_previos[i]['precio'] > max_previos[i-1]['precio']:
                        bos_tendencia_previa += 1
                        coordenadas_rupturas.append(_formatear_bos(max_previos[i-1]))
                        
            max_actuales = [m for m in maximos if m['indice'] >= indice_choch]
            if len(max_actuales) >= 2:
                for i in range(1, len(max_actuales)):
                    if max_actuales[i]['precio'] > max_actuales[i-1]['precio']:
                        bos_tendencia_actual += 1
                        coordenadas_rupturas.append(_formatear_bos(max_actuales[i-1]))
                        
        elif direccion_actual == "VENTAS":
            min_previos = [m for m in minimos if m['indice'] < indice_choch][-5:]
            if len(min_previos) >= 2:
                for i in range(1, len(min_previos)):
                    if min_previos[i]['precio'] < min_previos[i-1]['precio']:
                        bos_tendencia_previa += 1
                        coordenadas_rupturas.append(_formatear_bos(min_previos[i-1]))
                        
            min_actuales = [m for m in minimos if m['indice'] >= indice_choch]
            if len(min_actuales) >= 2:
                for i in range(1, len(min_actuales)):
                    if min_actuales[i]['precio'] < min_actuales[i-1]['precio']:
                        bos_tendencia_actual += 1
                        coordenadas_rupturas.append(_formatear_bos(min_actuales[i-1]))

        try:
            limite_bos = int(self.vars.get('bos_cripto', 1)) if ("BTC" in symbol or "ETH" in symbol) else int(self.vars.get('bos_forex', 1))
        except Exception:
            limite_bos = 1 

        es_valido = (bos_tendencia_previa >= limite_bos and bos_tendencia_actual >= 1)
        coords_recientes = coordenadas_rupturas[-4:] if coordenadas_rupturas else []
        
        self.log(f"    [ORDER FLOW] Previos: {bos_tendencia_previa} | Actuales: {bos_tendencia_actual} -> {' VÁLIDO' if es_valido else ' INVÁLIDO'}")

        return es_valido, bos_tendencia_previa, bos_tendencia_actual, coords_recientes

    # ==========================================
    #  ORQUESTADOR PRINCIPAL TOP-DOWN
    # ==========================================
    def generar_reporte_topografico(self, activo):
        self.log(f"️‍️ Analista iniciando escaneo Top-Down para {activo}...")
        
        direccion_d1, mitigacion_d1, liquidez_macro = self._analizar_d1(activo)
        if direccion_d1 == "INDECISIÓN":
            self.log("️ D1 no muestra dirección clara. Analista aborta misión.")
            return None

        estado_mit = "VALIDADA" if mitigacion_d1["estado"] else "NO MITIGADO"
        self.log(f" D1 Direccionalidad: {direccion_d1} | Mitigación: {estado_mit}")
        if mitigacion_d1["estado"]:
            self.log(f" Coordenadas D1 Mitigado -> Proximal: {mitigacion_d1['proximal']} | Distal: {mitigacion_d1['distal']}")

        zonas_h4, reporte_order_flow, limites_fractal, paso_cero, mapa_liquidez = self._buscar_zonas_con_sweep(activo, mt5.TIMEFRAME_H4, direccion_d1, velas_historia=500)
        
        if not paso_cero.get("tipo"):
            self.log("   ️ No se detectó un Paso Cero (W/M) reciente. Abortando por seguridad.")
            return None

        self.log(f"    PASO CERO DETECTADO -> {paso_cero['tipo']} | LIMITES: {limites_fractal['maximo']['precio']} - {limites_fractal['minimo']['precio']}")

        if not reporte_order_flow["valido"] or not zonas_h4:
            self.log("️ Estructura o Liquidez de H4 INVÁLIDA. Abortando.")
            return None

        self.log(f" H4 Zonas validadas por Sweep en Fractal Activo: {len(zonas_h4)}")

        zonas_h1_refinadas = self._refinar_en_temporalidad_menor(activo, mt5.TIMEFRAME_H1, zonas_h4, direccion_d1, mapa_liquidez, activo)
        
        if not zonas_h1_refinadas:
            self.log("️ H1 no confirmó micro-bloques válidos interactuando con la liquidez. Abortando.")
            return None

        self.log(f" H1 Zonas refinadas y listas para el Comandante: {len(zonas_h1_refinadas)}")

        mapa_json = mapa_liquidez.copy()
        if "consolidada" in mapa_json:
            del mapa_json["consolidada"]

        reporte = {
            "direccion_macro": direccion_d1,
            "mitigacion_d1": mitigacion_d1,
            "paso_cero_h4": paso_cero,
            "fractal_actual_limites": limites_fractal,
            "order_flow_h4": reporte_order_flow,
            "mapa_liquidez_h4": mapa_json, 
            "liquidez_externa": liquidez_macro, #  AHORA IMPRIME EL DICCIONARIO DIRECTO (PRECIO Y FECHA)
            "zonas_validas": zonas_h1_refinadas
        }
        
        self.log(" Escaneo completo. Reporte Topográfico sellado.")
        return reporte
    # ==========================================
    #  LÓGICA DE FASES
    # ==========================================
    def _analizar_d1(self, activo):
        velas = mt5.copy_rates_from_pos(activo, mt5.TIMEFRAME_D1, 0, 500)
        if velas is None: return "INDECISIÓN", {"estado": False}, {}
        df = pd.DataFrame(velas)
        fractales = self._mapear_fractales(df, sensibilidad=2)

        if len(fractales["maximos"]) < 2 or len(fractales["minimos"]) < 2:
            return "INDECISIÓN", {"estado": False}, {}

        ultimos_max = fractales["maximos"][-2:]
        ultimos_min = fractales["minimos"][-2:]
        
        ultimo_max_precio = ultimos_max[-1]['precio']
        ultimo_max_time = ultimos_max[-1]['time']
        prev_max_precio = ultimos_max[-2]['precio']
        
        ultimo_min_precio = ultimos_min[-1]['precio']
        ultimo_min_time = ultimos_min[-1]['time']
        prev_min_precio = ultimos_min[-2]['precio']

        if ultimo_max_precio > prev_max_precio:
            direccion = "COMPRAS"
        elif ultimo_min_precio < prev_min_precio:
            direccion = "VENTAS"
        else:
            direccion = "COMPRAS" if df['close'].iloc[-1] > df['close'].iloc[-5] else "VENTAS"

        #  NUEVO: Fechas en la Liquidez Externa
        liquidez_externa = {
            "precio": self.motor.a_humano(self.motor.a_entero(ultimo_max_precio if direccion == "COMPRAS" else ultimo_min_precio)),
            "fecha": self._ts_a_fecha(ultimo_max_time if direccion == "COMPRAS" else ultimo_min_time)
        }

        mitigacion_datos = {"estado": False, "proximal": 0, "distal": 0, "fecha_ob": ""}
        idx_actual = len(df) - 1

        if direccion == "COMPRAS":
            for i in range(idx_actual - 10, max(0, idx_actual - 300), -1):
                if df['close'].iloc[i] < df['open'].iloc[i]: 
                    ob_alto = df['high'].iloc[i]
                    ob_bajo = df['low'].iloc[i]
                    if ob_bajo <= ultimo_min_precio <= ob_alto:
                        mitigacion_datos = {
                            "estado": True,
                            "fecha_ob": self._ts_a_fecha(df['time'].iloc[i]), #  NUEVO: Fecha del OB de D1
                            "proximal": self.motor.a_humano(self.motor.a_entero(ob_alto)),
                            "distal": self.motor.a_humano(self.motor.a_entero(ob_bajo))
                        }
                        break
        else:
            for i in range(idx_actual - 10, max(0, idx_actual - 300), -1):
                if df['close'].iloc[i] > df['open'].iloc[i]: 
                    ob_alto = df['high'].iloc[i]
                    ob_bajo = df['low'].iloc[i]
                    if ob_bajo <= ultimo_max_precio <= ob_alto:
                        mitigacion_datos = {
                            "estado": True,
                            "fecha_ob": self._ts_a_fecha(df['time'].iloc[i]), #  NUEVO: Fecha del OB de D1
                            "proximal": self.motor.a_humano(self.motor.a_entero(ob_bajo)),
                            "distal": self.motor.a_humano(self.motor.a_entero(ob_alto))
                        }
                        break

        return direccion, mitigacion_datos, liquidez_externa

    def _escanear_obs_institucionales(self, df, idx_inicio, direccion, fractales):
        """
        RADAR INSTITUCIONAL:
        1. Busca FVG (Imbalance).
        2. Retrocede para atrapar la última vela contraria (OB Real).
        3. Audita si existe Inducement (Liquidez Interna previa al OB).
        """
        obs_detectados = []
        tiempos_procesados = set()

        if direccion == "COMPRAS":
            # Buscamos FVG Alcista (Vacío entre Vela 1 y Vela 3)
            for i in range(idx_inicio + 1, len(df) - 2):
                vela1 = df.iloc[i-1]
                vela2 = df.iloc[i]   # Vela de expansión
                vela3 = df.iloc[i+1]
                
                # Regla Matemática del FVG Alcista: Low(3) > High(1)
                if vela3['low'] > vela1['high']:
                    
                    #  Encontramos Imbalance. Ahora buscamos el OB (última vela bajista)
                    ob_encontrado = None
                    for j in range(i-1, max(idx_inicio-1, i-6), -1):
                        vela_cand = df.iloc[j]
                        if vela_cand['close'] < vela_cand['open']: # Vela bajista estricta
                            ob_encontrado = vela_cand
                            break
                    
                    if ob_encontrado is not None and ob_encontrado['time'] not in tiempos_procesados:
                        # ️ RASTREO DE INDUCEMENT (Liquidez Interna)
                        # ¿Hay mínimos fractales recientes que flotan por encima de este OB?
                        minimos_posteriores = [m for m in fractales['minimos'] if m['indice'] > i+1]
                        inducement_valido = any(m['precio'] > ob_encontrado['high'] for m in minimos_posteriores)
                        
                        obs_detectados.append({
                            "time": int(ob_encontrado['time']),
                            "vela_idx": j,
                            "proximal_float": ob_encontrado['high'],
                            "distal_float": ob_encontrado['low'],
                            "proximal": self.motor.a_humano(self.motor.a_entero(ob_encontrado['high'])),
                            "distal": self.motor.a_humano(self.motor.a_entero(ob_encontrado['low'])),
                            "fvg_detectado": True,
                            "inducement_previo": inducement_valido
                        })
                        tiempos_procesados.add(ob_encontrado['time'])

        elif direccion == "VENTAS":
            # Buscamos FVG Bajista (Vacío entre Vela 1 y Vela 3)
            for i in range(idx_inicio + 1, len(df) - 2):
                vela1 = df.iloc[i-1]
                vela2 = df.iloc[i]   
                vela3 = df.iloc[i+1]
                
                # Regla Matemática del FVG Bajista: High(3) < Low(1)
                if vela3['high'] < vela1['low']:
                    
                    #  Encontramos Imbalance. Buscamos el OB (última vela alcista)
                    ob_encontrado = None
                    for j in range(i-1, max(idx_inicio-1, i-6), -1):
                        vela_cand = df.iloc[j]
                        if vela_cand['close'] > vela_cand['open']: # Vela alcista estricta
                            ob_encontrado = vela_cand
                            break
                    
                    if ob_encontrado is not None and ob_encontrado['time'] not in tiempos_procesados:
                        # ️ RASTREO DE INDUCEMENT (Liquidez Interna)
                        maximos_posteriores = [m for m in fractales['maximos'] if m['indice'] > i+1]
                        inducement_valido = any(m['precio'] < ob_encontrado['low'] for m in maximos_posteriores)
                        
                        obs_detectados.append({
                            "time": int(ob_encontrado['time']),
                            "vela_idx": j,
                            "proximal_float": ob_encontrado['low'],
                            "distal_float": ob_encontrado['high'],
                            "proximal": self.motor.a_humano(self.motor.a_entero(ob_encontrado['low'])),
                            "distal": self.motor.a_humano(self.motor.a_entero(ob_encontrado['high'])),
                            "fvg_detectado": True,
                            "inducement_previo": inducement_valido
                        })
                        tiempos_procesados.add(ob_encontrado['time'])

        return obs_detectados


    def _buscar_zonas_con_sweep(self, activo, timeframe, direccion, velas_historia):
        velas = mt5.copy_rates_from_pos(activo, timeframe, 0, velas_historia)
        if velas is None: return [], {"valido": False}, {"maximo": 0, "minimo": 0}, {}, {}
        df = pd.DataFrame(velas)
        
        try:
            sens_min = int(self.vars.get('sp_sens_min', 2))
            sens_max = int(self.vars.get('sp_sens_max', 15))
        except Exception:
            sens_min, sens_max = 2, 15

        sensibilidad_optima = 0
        fractales_optimos = None
        paso_cero_optimo = {"indice_origen": 0, "tipo": None, "coordenadas": {}}
        reporte_of_optimo = {"valido": False}
        limites_finales = {"maximo": {}, "minimo": {}}
        mapa_liquidez_final = {}

        for sens in range(sens_min, sens_max + 1):
            fractales = self._mapear_fractales(df, sensibilidad=sens)
            if not fractales["maximos"] or not fractales["minimos"]: continue
            
            paso_cero = self._identificar_paso_cero(df, timeframe, direccion, fractales)
            idx_inicio_fractal = paso_cero["indice_origen"]
            if idx_inicio_fractal == 0: continue 
            
            of_valido, bos_prev, bos_act, coords_of = self.auditar_order_flow(fractales, direccion, idx_inicio_fractal, activo)
            
            if of_valido:
                sensibilidad_optima = sens
                fractales_optimos = fractales
                paso_cero_optimo = paso_cero
                
                df_fractal = df.iloc[idx_inicio_fractal:]
                
                #  Extracción matemática de precio y fecha para los límites
                idx_max = df_fractal['high'].idxmax()
                precio_maximo = float(df_fractal.loc[idx_max, 'high'])
                fecha_maximo = self._ts_a_fecha(df_fractal.loc[idx_max, 'time'])
                
                idx_min = df_fractal['low'].idxmin()
                precio_minimo = float(df_fractal.loc[idx_min, 'low'])
                fecha_minimo = self._ts_a_fecha(df_fractal.loc[idx_min, 'time'])
                
                fibo_50 = (precio_maximo + precio_minimo) / 2
                
                limites_finales = {
                    "maximo": {"precio": self.motor.a_humano(self.motor.a_entero(precio_maximo)), "fecha": fecha_maximo},
                    "minimo": {"precio": self.motor.a_humano(self.motor.a_entero(precio_minimo)), "fecha": fecha_minimo}
                }
                
                mapa_liquidez_bruto = self.escanear_trampas(activo, df, precio_maximo, precio_minimo, fibo_50, direccion, fractales, idx_inicio_fractal)
                mapa_liquidez_final = mapa_liquidez_bruto.copy()
                if "consolidada" in mapa_liquidez_final: 
                    del mapa_liquidez_final["consolidada"]
                
                reporte_of_optimo = {
                    "valido": True,
                    "sensibilidad_usada": sensibilidad_optima,
                    "bos_previos_encontrados": bos_prev,
                    "bos_actuales_encontrados": bos_act,
                    "coordenadas_rupturas": coords_of
                }
                break

        if sensibilidad_optima == 0:
            self.log("   ️ Respiración Fractal agotada.")
            return [], {"valido": False}, limites_finales, paso_cero_optimo, {}

        self.log(f"    Respiración Fractal Exitosa en Sensibilidad {sensibilidad_optima}")
        
        zonas_brutas = []
        idx_inicio = paso_cero_optimo["indice_origen"]

        # Escaneo institucional prioritario: OBs con FVG e Inducement (Regla Capital Trading)
        obs_institucionales = self._escanear_obs_institucionales(df, idx_inicio, direccion, fractales_optimos)
        if obs_institucionales:
            zonas_brutas = obs_institucionales
        else:
            if direccion == "COMPRAS":
                nodos_activos = [m for m in fractales_optimos["minimos"] if m['indice'] >= idx_inicio]
                for nodo in nodos_activos:
                    min_previos = [m for m in fractales_optimos["minimos"] if m['indice'] < nodo['indice']]
                    if not min_previos: continue
                    if any(nodo['precio'] <= m_prev['precio'] for m_prev in min_previos[-5:]):
                        vela = df.iloc[nodo['indice']]
                        zonas_brutas.append({
                            "time": int(vela['time']),
                            "proximal_float": vela['high'], "distal_float": vela['low'],
                            "proximal": self.motor.a_humano(self.motor.a_entero(vela['high'])),
                            "distal": self.motor.a_humano(self.motor.a_entero(vela['low'])),
                            "fvg_detectado": False,
                            "inducement_previo": False
                        })
            elif direccion == "VENTAS":
                nodos_activos = [m for m in fractales_optimos["maximos"] if m['indice'] >= idx_inicio]
                for nodo in nodos_activos:
                    max_previos = [m for m in fractales_optimos["maximos"] if m['indice'] < nodo['indice']]
                    if not max_previos: continue
                    if any(nodo['precio'] >= m_prev['precio'] for m_prev in max_previos[-5:]):
                        vela = df.iloc[nodo['indice']]
                        zonas_brutas.append({
                            "time": int(vela['time']),
                            "proximal_float": vela['low'], "distal_float": vela['high'],
                            "proximal": self.motor.a_humano(self.motor.a_entero(vela['low'])),
                            "distal": self.motor.a_humano(self.motor.a_entero(vela['high'])),
                            "fvg_detectado": False,
                            "inducement_previo": False
                        })

        zonas_h4_filtradas = []
        if zonas_brutas:
            if direccion == "COMPRAS":
                extremo = min(zonas_brutas, key=lambda x: x['distal_float'])
                extremo["tipo"] = "EXTREMO_H4"
                zonas_h4_filtradas.append(extremo)
                candidatos_decisional = [z for z in zonas_brutas if z != extremo]
                if candidatos_decisional:
                    decisional = max(candidatos_decisional, key=lambda x: x['time'])
                    decisional["tipo"] = "DECISIONAL_H4"
                    zonas_h4_filtradas.append(decisional)
            else:
                extremo = max(zonas_brutas, key=lambda x: x['distal_float'])
                extremo["tipo"] = "EXTREMO_H4"
                zonas_h4_filtradas.append(extremo)
                candidatos_decisional = [z for z in zonas_brutas if z != extremo]
                if candidatos_decisional:
                    decisional = max(candidatos_decisional, key=lambda x: x['time'])
                    decisional["tipo"] = "DECISIONAL_H4"
                    zonas_h4_filtradas.append(decisional)

        for z in zonas_h4_filtradas:
            del z['proximal_float']; del z['distal_float']

        return zonas_h4_filtradas, reporte_of_optimo, limites_finales, paso_cero_optimo, mapa_liquidez_final

    def _refinar_en_temporalidad_menor(self, activo, timeframe, zonas_macro, direccion, mapa_liquidez, symbol):
        velas = mt5.copy_rates_from_pos(activo, timeframe, 0, 1000)
        if velas is None: return []
        df = pd.DataFrame(velas)
        fractales = self._mapear_fractales(df, sensibilidad=2)
        
        liquidez_institucional = mapa_liquidez.get("consolidada", [])
        tolerancia = self._pips_a_precio(symbol, 2.0)
        zonas_finales = []

        for zona in zonas_macro:
            prox_macro = zona['proximal']
            dist_macro = zona['distal']
            tiempo_inicio = zona['time'] - (4 * 3600) 
            tiempo_fin = zona['time'] + (8 * 3600)    
            
            velas_validas = []

            if direccion == "COMPRAS":
                nodos_internos = [m for m in fractales["minimos"] if dist_macro <= m['precio'] <= prox_macro and tiempo_inicio <= m['vela']['time'] <= tiempo_fin]
                for nodo in nodos_internos:
                    if not liquidez_institucional or any(nodo['vela']['low'] <= (liq + tolerancia) for liq in liquidez_institucional):
                        velas_validas.append(nodo['vela'])
                        
                if velas_validas:
                    mejor_vela = min(velas_validas, key=lambda x: x['low'])
                    zonas_finales.append({
                        "origen": zona['tipo'],
                        "tipo": "H1_REFINADO", 
                        "fecha_vela_mt5": self._ts_a_fecha(mejor_vela['time']), #  NUEVO: Fecha en el Output Final
                        "proximal": self.motor.a_humano(self.motor.a_entero(mejor_vela['high'])), 
                        "distal": self.motor.a_humano(self.motor.a_entero(mejor_vela['low']))
                    })

            else:
                nodos_internos = [m for m in fractales["maximos"] if prox_macro <= m['precio'] <= dist_macro and tiempo_inicio <= m['vela']['time'] <= tiempo_fin]
                for nodo in nodos_internos:
                    if not liquidez_institucional or any(nodo['vela']['high'] >= (liq - tolerancia) for liq in liquidez_institucional):
                        velas_validas.append(nodo['vela'])
                        
                if velas_validas:
                    mejor_vela = max(velas_validas, key=lambda x: x['high'])
                    zonas_finales.append({
                        "origen": zona['tipo'],
                        "tipo": "H1_REFINADO", 
                        "fecha_vela_mt5": self._ts_a_fecha(mejor_vela['time']), #  NUEVO: Fecha en el Output Final
                        "proximal": self.motor.a_humano(self.motor.a_entero(mejor_vela['low'])), 
                        "distal": self.motor.a_humano(self.motor.a_entero(mejor_vela['high']))
                    })

        return zonas_finales


# ==========================================
#  INTERFAZ GRÁFICA (CEO / Pruebas)
# ==========================================
class InterfazAuditoriaAnalista:
    def __init__(self, root):
        self.root = root
        self.root.title("ALFA INC. - Auditoría del Analista Cuantitativo")
        self.root.geometry("650x700")
        self.root.configure(bg="#050505")
        
        self.activo_var = tk.StringVar(value="BTCUSDm")
        self._construir_ui()

    def _construir_ui(self):
        f_top = tk.Frame(self.root, bg="#111", pady=15)
        f_top.pack(fill=tk.X)
        tk.Label(f_top, text="️‍️ PRUEBA DE EMPLEADO: EL ANALISTA", font=("Segoe UI", 14, "bold"), bg="#111", fg="#00ffcc").pack()

        f_controles = tk.Frame(self.root, bg="#0a0a0a", pady=10)
        f_controles.pack(fill=tk.X, padx=15)
        tk.Label(f_controles, text="Activo a escanear:", bg="#0a0a0a", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Entry(f_controles, textvariable=self.activo_var, bg="#1a1a1a", fg="white").pack(side=tk.LEFT, padx=5)
        
        tk.Button(f_controles, text="EJECUTAR ANÁLISIS TOP-DOWN", bg="#ff003c", fg="white", font=("Segoe UI", 10, "bold"), command=self.detonar_prueba).pack(side=tk.RIGHT, padx=5)

        self.txt_consola = tk.Text(self.root, height=12, bg="#0a0a0a", fg="#aaaaaa", font=("Consolas", 9), relief=tk.FLAT)
        self.txt_consola.pack(fill=tk.X, padx=15, pady=5)

        tk.Label(self.root, text=" REPORTE TOPOGRÁFICO (PAYLOAD FINAL)", bg="#050505", fg="#ffaa00", font=("Segoe UI", 10, "bold")).pack(pady=5)
        
        self.txt_json = tk.Text(self.root, height=16, bg="#001100", fg="#00ff00", font=("Consolas", 10), relief=tk.FLAT)
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
        calculadora = MotorAritmetico(tipo_activo="CRIPTO" if "BTC" in activo else "FOREX")
        
        #  Simulamos TODAS las variables de la UI (BOS, Respiración Fractal y Liquidez)
        simulacion_vars_ui = {
            'bos_cripto': 1, 
            'bos_forex': 1,
            'sp_sens_min': 2, 
            'sp_sens_max': 15,
            'sp_tol_eqh': 2.0,
            'sp_tol_arro': 1.5,
            'sp_min_arro': 4
        }
        
        analista = MotorEstructural(motor_aritmetico=calculadora, logger_callback=self.log, vars_ui=simulacion_vars_ui)
        threading.Thread(target=self._hilo_analista, args=(analista, activo), daemon=True).start()

    def _hilo_analista(self, analista, activo):
        reporte = analista.generar_reporte_topografico(activo)
        
        if reporte:
            payload_formateado = json.dumps(reporte, indent=4, ensure_ascii=False)
            self.txt_json.insert(tk.END, payload_formateado)
        else:
            self.txt_json.insert(tk.END, "{ \n  'estado': 'MISIÓN ABORTADA POR FALTA DE ESTRUCTURA' \n}")

if __name__ == "__main__":
    root = tk.Tk()
    app = InterfazAuditoriaAnalista(root)
    root.mainloop()