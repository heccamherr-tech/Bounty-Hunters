"""
alfa_orb_momentum_sniper.py — ALFA CAPITAL
==========================================
Modulo de Trading Algoritmico de Alta Precision: Ruptura de Rango de Apertura (ORB)
y Momentum Sniper con Piramidacion Dinamica (Ingenieria Inversa Optimizada de MS27).

Cobertura Integral:
  1. Multi-Activo (16 activos homologados):
     - Metales: XAUUSD (Oro), XAGUSD (Plata)
     - Indices: NDXUSD (Nasdaq 100), DJIUSD (Dow Jones 30), SPXUSD (S&P 500)
     - Forex Majors y Crosses: EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, USDCAD, USDCHF, GBPJPY, EURGBP
     - Crypto: BTCUSD, ETHUSD
  2. Killzones Quirurgicas Institucionales (Horas UTC):
     - Tokyo Open: 23:00 a 01:00 UTC (Apertura Asia)
     - London Open: 06:00 a 09:30 UTC (Apertura Europa / Londres)
     - New York Open: 13:30 a 16:30 UTC (Apertura Wall Street)
  3. Filtro de Direccion Macro Institucional ALFA (EMA 50/200 en H1) para filtrar falsos quiebres.
  4. Apertura ORB: Calculo del High y Low de los primeros 15 minutos de la sesion.
  5. Disparo por quiebre de tick con expansion de volumen tick_volume > SMA(Vol, 20) * 1.10.
  6. Gestion de Riesgo Rigida:
     - Stop Loss asimetrico ultra-ajustado (15 pips en Oro, 25 pts en Nasdaq).
     - Trailing a Break-Even en +1.5R.
     - Piramidacion en +1.2R hacia el mismo TP unificado.
     - Hard Drawdown Circuit Breaker: Maximo 3.5% diario (limite broker: 4.0%).
"""

from __future__ import annotations
import os
import sys
import time
import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError("MT5 local fallo")
except Exception:
    import alfa_mt5_bridge
    mt5 = alfa_mt5_bridge.instalar()

try:
    from alfa_nvidia_alpha import calcular_alpha_sovereign
except ImportError:
    calcular_alpha_sovereign = None

log = logging.getLogger("ALFA.ORB_SNIPER")
if not log.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.setLevel(logging.INFO)


# Matriz de Parametrizacion por Activo (16 Activos Oficiales)
ORB_CONFIG = {
    # Metales
    "XAUUSD": {
        "sl_pts": 1.50,         # 15 pips en Oro
        "tp_ratio": 2.5,
        "base_lot": 0.50,
        "scaled_lot": 1.00,
        "contract_size": 100.0,
        "magic": 165901,
        "allow_pyramid": True,
        "sessions": ["LONDON", "NEW_YORK", "TOKYO"]
    },
    "XAGUSD": {
        "sl_pts": 0.25,
        "tp_ratio": 2.5,
        "base_lot": 0.10,
        "scaled_lot": 0.20,
        "contract_size": 5000.0,
        "magic": 165902,
        "allow_pyramid": True,
        "sessions": ["LONDON", "NEW_YORK"]
    },
    # Indices
    "NDXUSD": {
        "sl_pts": 25.0,         # 25 pts en Nasdaq
        "tp_ratio": 2.8,
        "base_lot": 0.50,
        "scaled_lot": 1.00,
        "contract_size": 10.0,
        "magic": 165903,
        "allow_pyramid": True,
        "sessions": ["NEW_YORK", "LONDON"]
    },
    "DJIUSD": {
        "sl_pts": 40.0,         # 40 pts en Dow Jones
        "tp_ratio": 2.8,
        "base_lot": 0.50,
        "scaled_lot": 1.00,
        "contract_size": 10.0,
        "magic": 165904,
        "allow_pyramid": True,
        "sessions": ["NEW_YORK"]
    },
    "SPXUSD": {
        "sl_pts": 6.0,          # 6 pts en S&P 500
        "tp_ratio": 2.8,
        "base_lot": 0.50,
        "scaled_lot": 1.00,
        "contract_size": 10.0,
        "magic": 165905,
        "allow_pyramid": True,
        "sessions": ["NEW_YORK"]
    },
    # Forex Majors
    "EURUSD": {
        "sl_pts": 0.0012,       # 12 pips en EURUSD
        "tp_ratio": 2.2,
        "base_lot": 0.50,
        "scaled_lot": 1.00,
        "contract_size": 100000.0,
        "magic": 165906,
        "allow_pyramid": False,
        "sessions": ["LONDON", "NEW_YORK"]
    },
    "GBPUSD": {
        "sl_pts": 0.0015,       # 15 pips en GBPUSD
        "tp_ratio": 2.2,
        "base_lot": 0.50,
        "scaled_lot": 1.00,
        "contract_size": 100000.0,
        "magic": 165907,
        "allow_pyramid": False,
        "sessions": ["LONDON", "NEW_YORK"]
    },
    "USDJPY": {
        "sl_pts": 0.150,        # 15 pips en USDJPY
        "tp_ratio": 2.2,
        "base_lot": 0.50,
        "scaled_lot": 1.00,
        "contract_size": 100000.0,
        "magic": 165908,
        "allow_pyramid": False,
        "sessions": ["TOKYO", "LONDON", "NEW_YORK"]
    },
    "AUDUSD": {
        "sl_pts": 0.0012,       # 12 pips en AUDUSD
        "tp_ratio": 2.2,
        "base_lot": 0.50,
        "scaled_lot": 1.00,
        "contract_size": 100000.0,
        "magic": 165909,
        "allow_pyramid": False,
        "sessions": ["TOKYO", "LONDON"]
    },
    "NZDUSD": {
        "sl_pts": 0.0012,       # 12 pips en NZDUSD
        "tp_ratio": 2.2,
        "base_lot": 0.50,
        "scaled_lot": 1.00,
        "contract_size": 100000.0,
        "magic": 165910,
        "allow_pyramid": False,
        "sessions": ["TOKYO", "LONDON"]
    },
    "USDCAD": {
        "sl_pts": 0.0014,       # 14 pips en USDCAD
        "tp_ratio": 2.2,
        "base_lot": 0.50,
        "scaled_lot": 1.00,
        "contract_size": 100000.0,
        "magic": 165911,
        "allow_pyramid": False,
        "sessions": ["NEW_YORK"]
    },
    "USDCHF": {
        "sl_pts": 0.0012,       # 12 pips en USDCHF
        "tp_ratio": 2.2,
        "base_lot": 0.50,
        "scaled_lot": 1.00,
        "contract_size": 100000.0,
        "magic": 165912,
        "allow_pyramid": False,
        "sessions": ["LONDON", "NEW_YORK"]
    },
    # Forex Crosses
    "GBPJPY": {
        "sl_pts": 0.220,        # 22 pips en GBPJPY
        "tp_ratio": 2.5,
        "base_lot": 0.30,
        "scaled_lot": 0.60,
        "contract_size": 100000.0,
        "magic": 165913,
        "allow_pyramid": True,
        "sessions": ["LONDON", "TOKYO"]
    },
    "EURGBP": {
        "sl_pts": 0.0010,       # 10 pips en EURGBP
        "tp_ratio": 2.0,
        "base_lot": 0.50,
        "scaled_lot": 1.00,
        "contract_size": 100000.0,
        "magic": 165914,
        "allow_pyramid": False,
        "sessions": ["LONDON"]
    },
    # Crypto
    "BTCUSD": {
        "sl_pts": 450.0,        # 450 USD en BTC
        "tp_ratio": 2.5,
        "base_lot": 0.10,
        "scaled_lot": 0.20,
        "contract_size": 1.0,
        "magic": 165915,
        "allow_pyramid": True,
        "sessions": ["TOKYO", "LONDON", "NEW_YORK"]
    },
    "ETHUSD": {
        "sl_pts": 25.0,         # 25 USD en ETH
        "tp_ratio": 2.5,
        "base_lot": 0.20,
        "scaled_lot": 0.50,
        "contract_size": 1.0,
        "magic": 165916,
        "allow_pyramid": True,
        "sessions": ["TOKYO", "LONDON", "NEW_YORK"]
    }
}


class AlfaOrbMomentumSniper:
    def __init__(self, mt5_instance=None):
        self.mt5 = mt5_instance or mt5
        self.session_data: Dict[str, Dict[str, Any]] = {}
        self.daily_start_balance = 5000.0
        self.last_check_day = None
        self.circuit_breaker_active = False

    def actualizar_estado_cuenta(self) -> Tuple[float, float]:
        """Obtiene balance y equidad viva."""
        acct = self.mt5.account_info()
        if acct is None:
            return 5000.0, 5000.0
        return float(acct.balance), float(acct.equity)

    def verificar_circuit_breaker(self) -> bool:
        """Protege la cuenta: maximo 3.5% de drawdown diario (limite broker: 4.0%)."""
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        
        balance, equity = self.actualizar_estado_cuenta()
        
        if self.last_check_day != today_str:
            self.last_check_day = today_str
            self.daily_start_balance = equity
            self.circuit_breaker_active = False
            log.info(f"[ORB_SNIPER] Nuevo dia operativo. Balance base fijado: ${self.daily_start_balance:,.2f} USD")

        loss_today = self.daily_start_balance - equity
        loss_pct = (loss_today / self.daily_start_balance) * 100.0 if self.daily_start_balance > 0 else 0.0

        if loss_pct >= 3.5:
            if not self.circuit_breaker_active:
                log.warning(f"[CIRCUIT_BREAKER] Drawdown diario alcanzado: {loss_pct:.2f}% (${loss_today:.2f} USD). Operativa pausada por proteccion de capital.")
                self.circuit_breaker_active = True
            return True
            
        return self.circuit_breaker_active

    def obtener_direccion_macro(self, symbol: str) -> str:
        """Calcula alineacion tendencial EMA50 / EMA200 en H1."""
        rates = self.mt5.copy_rates_from_pos(symbol, self.mt5.TIMEFRAME_H1, 0, 220)
        if rates is None or len(rates) < 200:
            return "NEUTRAL"
            
        closes = [float(r["close"]) for r in rates]
        
        def calc_ema(vals, span):
            alpha = 2.0 / (span + 1.0)
            res = [vals[0]]
            for v in vals[1:]:
                res.append(alpha * v + (1.0 - alpha) * res[-1])
            return res[-1]
            
        ema50 = calc_ema(closes, 50)
        ema200 = calc_ema(closes, 200)
        last_price = closes[-1]
        
        if last_price > ema200 and ema50 >= ema200:
            return "COMPRAS"
        elif last_price < ema200 and ema50 <= ema200:
            return "VENTAS"
        return "NEUTRAL"

    def detectar_sesion_activa(self) -> Tuple[Optional[str], bool, bool]:
        """
        Determina si estamos en una Killzone activa (en UTC).
        Retorna: (nombre_sesion, es_ventana_orb, es_ventana_trading)
        """
        now = datetime.now(timezone.utc)
        h = now.hour
        m = now.minute
        
        # 1. London Open: 06:00 a 09:30 UTC
        if h == 6 and 0 <= m < 15:
            return "LONDON", True, False
        elif (h == 6 and 15 <= m <= 59) or (7 <= h <= 9 and not (h == 9 and m > 30)):
            return "LONDON", False, True

        # 2. New York Open: 13:30 a 16:30 UTC
        elif h == 13 and 30 <= m < 45:
            return "NEW_YORK", True, False
        elif (h == 13 and 45 <= m <= 59) or (14 <= h <= 16 and not (h == 16 and m > 30)):
            return "NEW_YORK", False, True

        # 3. Tokyo Open: 23:00 a 01:30 UTC
        elif h == 23 and 0 <= m < 15:
            return "TOKYO", True, False
        elif (h == 23 and 15 <= m <= 59) or (h == 0) or (h == 1 and m <= 30):
            return "TOKYO", False, True
            
        return None, False, False

    def resolver_simbolo_broker(self, symbol: str) -> Optional[str]:
        """Resuelve el simbolo existente en el broker (con o sin sufijo m)."""
        candidates = [symbol, symbol.rstrip("m"), symbol + "m"]
        for c in candidates:
            info = self.mt5.symbol_info(c)
            if info is not None:
                return c
        return None

    def procesar_activo(self, raw_symbol: str):
        """Ciclo de evaluacion ORB por activo."""
        clean_sym = raw_symbol.rstrip("m")
        if clean_sym not in ORB_CONFIG:
            return

        spec = ORB_CONFIG[clean_sym]
        ses_name, is_or_window, is_trade_window = self.detectar_sesion_activa()
        
        if not ses_name or ses_name not in spec["sessions"]:
            return

        if self.verificar_circuit_breaker():
            return

        symbol = self.resolver_simbolo_broker(raw_symbol)
        if not symbol:
            return

        now = datetime.now(timezone.utc)
        day_str = now.strftime("%Y-%m-%d")
        key = f"{clean_sym}_{day_str}_{ses_name}"
        
        if key not in self.session_data:
            self.session_data[key] = {
                "high": -1e9,
                "low": 1e9,
                "complete": False,
                "trades_count": 0,
                "bars_seen": set()
            }
            
        state = self.session_data[key]
        
        # 1. Construccion del Rango de Apertura (ORB M5)
        rates_m5 = self.mt5.copy_rates_from_pos(symbol, self.mt5.TIMEFRAME_M5, 0, 10)
        if rates_m5 is None or len(rates_m5) == 0:
            return

        if is_or_window:
            for r in rates_m5[-3:]:
                t = int(r["time"])
                if t not in state["bars_seen"]:
                    state["bars_seen"].add(t)
                    state["high"] = max(state["high"], float(r["high"]))
                    state["low"] = min(state["low"], float(r["low"]))
            if len(state["bars_seen"]) >= 3:
                state["complete"] = True
                log.info(f"[ORB_SNIPER] Rango ORB consolidado para {symbol} ({ses_name}): High={state['high']} | Low={state['low']}")
            return

        # 2. Disparo de Ruptura (Ventana de Trading)
        if is_trade_window and state["complete"] and state["trades_count"] < 1:
            positions = self.mt5.positions_get(symbol=symbol)
            if positions is not None and len(positions) > 0:
                self.gestionar_posiciones_activas(symbol, positions, spec)
                return

            tick = self.mt5.symbol_info_tick(symbol)
            if tick is None or tick.bid == 0 or tick.ask == 0:
                return

            macro_dir = self.obtener_direccion_macro(symbol)
            
            # Filtro de volumen en M5
            last_m5 = rates_m5[-1]
            vols = [float(r["tick_volume"]) for r in rates_m5]
            avg_vol = sum(vols) / len(vols) if vols else 1.0
            vol_ok = float(last_m5["tick_volume"]) >= (avg_vol * 1.10)

            # Filtro de Señal Alpha Cuantitativa (NVIDIA Discovery Agent)
            alpha_info = calcular_alpha_sovereign(list(rates_m5)) if calcular_alpha_sovereign else {"alpha": 0.0, "signal": "NEUTRAL"}
            alpha_val = alpha_info.get("alpha", 0.0)

            balance, equity = self.actualizar_estado_cuenta()
            lot = spec["base_lot"] if equity < 6500.0 else spec["scaled_lot"]
            sl_dist = spec["sl_pts"]
            tp_dist = sl_dist * spec["tp_ratio"]

            # DISPARO BUY (Validado si no hay agotamiento adverso: alpha > -0.40)
            if tick.ask > state["high"] and macro_dir == "COMPRAS" and vol_ok and alpha_val > -0.40:
                sl = tick.ask - sl_dist
                tp = tick.ask + tp_dist
                res = self.enviar_orden(symbol, self.mt5.ORDER_TYPE_BUY, tick.ask, sl, tp, lot, spec["magic"], f"ORB_{ses_name}_BUY")
                if res and res.retcode == self.mt5.TRADE_RETCODE_DONE:
                    state["trades_count"] += 1
                    log.info(f"[ORB_SNIPER] [DISPARO OK] {symbol} BUY {lot}L @ {tick.ask} | Alpha={alpha_val:+.2f} | SL: {sl} | TP: {tp} | Ticket: {res.order}")
                    
            # DISPARO SELL (Validado si no hay agotamiento adverso: alpha < +0.40)
            elif tick.bid < state["low"] and macro_dir == "VENTAS" and vol_ok and alpha_val < +0.40:
                sl = tick.bid + sl_dist
                tp = tick.bid - tp_dist
                res = self.enviar_orden(symbol, self.mt5.ORDER_TYPE_SELL, tick.bid, sl, tp, lot, spec["magic"], f"ORB_{ses_name}_SELL")
                if res and res.retcode == self.mt5.TRADE_RETCODE_DONE:
                    state["trades_count"] += 1
                    log.info(f"[ORB_SNIPER] [DISPARO OK] {symbol} SELL {lot}L @ {tick.bid} | Alpha={alpha_val:+.2f} | SL: {sl} | TP: {tp} | Ticket: {res.order}")

    def gestionar_posiciones_activas(self, symbol: str, positions: tuple, spec: Dict[str, Any]):
        """Gestiona Trailing Stop a Break-Even y Piramidacion Dinamica."""
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            return

        sl_dist = spec["sl_pts"]
        spread = tick.ask - tick.bid

        for pos in positions:
            pos_dict = pos._asdict() if hasattr(pos, "_asdict") else dict(pos.__dict__)
            magic = pos_dict.get("magic", 0)
            if magic != spec["magic"]:
                continue

            ticket = pos_dict["ticket"]
            pos_type = pos_dict["type"]
            open_p = float(pos_dict["price_open"])
            current_sl = float(pos_dict["sl"])
            tp = float(pos_dict["tp"])
            lot = float(pos_dict["volume"])

            # 1. Trailing Dinamico Soberano: Asegura Break-Even a +1.0R y bloquea ganancias conforme el precio corre
            if pos_type == self.mt5.ORDER_TYPE_BUY:
                gain = tick.bid - open_p
                # Mover a Break-Even inmediato a +1.0R
                if gain >= (sl_dist * 1.0) and current_sl < open_p:
                    new_sl = open_p + spread
                    self.modificar_sl_tp(ticket, symbol, new_sl, tp)
                    log.info(f"[ORB_SNIPER] [TRAILING BE] {symbol} Ticket {ticket} asegurado a Break-Even ({new_sl:.2f})")
                
                # Trailing Stop dinamico protector cuando la ganancia supera +1.8R
                elif gain >= (sl_dist * 1.8):
                    dynamic_sl = tick.bid - (sl_dist * 0.8)
                    if dynamic_sl > current_sl:
                        self.modificar_sl_tp(ticket, symbol, dynamic_sl, tp)
                        log.info(f"[ORB_SNIPER] [TRAILING PROFIT] {symbol} Ticket {ticket} SL protegido al alza ({dynamic_sl:.2f})")

                # Salida soberana por agotamiento de micro-momentum (si retrocede mas de 40% del pico maximo tras ganar +1.5R)
                if gain >= (sl_dist * 1.5) and tick.bid < (open_p + gain * 0.65):
                    log.info(f"[ORB_SNIPER] [EXIT AGOTAMIENTO] {symbol} Ticket {ticket} cerrando por frenado de momentum (Gain: +{gain:.2f})")
                    self.cerrar_posicion(ticket, symbol, lot, self.mt5.ORDER_TYPE_SELL, tick.bid, "ORB_MOMENTUM_EXIT")
                    continue

                # 2. Piramidacion Soberana (+1.2R)
                if spec["allow_pyramid"] and len(positions) < 2 and gain >= (sl_dist * 1.2):
                    p_entry = tick.ask
                    p_sl = open_p
                    res = self.enviar_orden(symbol, self.mt5.ORDER_TYPE_BUY, p_entry, p_sl, tp, lot, spec["magic"], "ORB_PYRAMID_BUY")
                    if res and res.retcode == self.mt5.TRADE_RETCODE_DONE:
                        log.info(f"[ORB_SNIPER] [PIRAMIDACION OK] {symbol} Ticket secundario {res.order} @ {p_entry} anclado al TP {tp}")

            elif pos_type == self.mt5.ORDER_TYPE_SELL:
                gain = open_p - tick.ask
                # Mover a Break-Even inmediato a +1.0R
                if gain >= (sl_dist * 1.0) and (current_sl == 0 or current_sl > open_p):
                    new_sl = open_p - spread
                    self.modificar_sl_tp(ticket, symbol, new_sl, tp)
                    log.info(f"[ORB_SNIPER] [TRAILING BE] {symbol} Ticket {ticket} asegurado a Break-Even ({new_sl:.2f})")

                # Trailing Stop dinamico protector cuando la ganancia supera +1.8R
                elif gain >= (sl_dist * 1.8):
                    dynamic_sl = tick.ask + (sl_dist * 0.8)
                    if current_sl == 0 or dynamic_sl < current_sl:
                        self.modificar_sl_tp(ticket, symbol, dynamic_sl, tp)
                        log.info(f"[ORB_SNIPER] [TRAILING PROFIT] {symbol} Ticket {ticket} SL protegido a la baja ({dynamic_sl:.2f})")

                # Salida soberana por agotamiento de micro-momentum
                if gain >= (sl_dist * 1.5) and tick.ask > (open_p - gain * 0.65):
                    log.info(f"[ORB_SNIPER] [EXIT AGOTAMIENTO] {symbol} Ticket {ticket} cerrando por frenado de momentum (Gain: +{gain:.2f})")
                    self.cerrar_posicion(ticket, symbol, lot, self.mt5.ORDER_TYPE_BUY, tick.ask, "ORB_MOMENTUM_EXIT")
                    continue

                if spec["allow_pyramid"] and len(positions) < 2 and gain >= (sl_dist * 1.2):
                    p_entry = tick.bid
                    p_sl = open_p
                    res = self.enviar_orden(symbol, self.mt5.ORDER_TYPE_SELL, p_entry, p_sl, tp, lot, spec["magic"], "ORB_PYRAMID_SELL")
                    if res and res.retcode == self.mt5.TRADE_RETCODE_DONE:
                        log.info(f"[ORB_SNIPER] [PIRAMIDACION OK] {symbol} Ticket secundario {res.order} @ {p_entry} anclado al TP {tp}")

    def cerrar_posicion(self, ticket: int, symbol: str, lot: float, order_type: int, price: float, comment: str) -> Any:
        """Cierra una posicion soberana a mercado."""
        req = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "position": int(ticket),
            "symbol": symbol,
            "volume": float(lot),
            "type": order_type,
            "price": float(price),
            "deviation": 20,
            "comment": comment,
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        return self.mt5.order_send(req)

    def enviar_orden(self, symbol: str, order_type: int, price: float, sl: float, tp: float, 
                     volume: float, magic: int, comment: str) -> Any:
        """Envia orden a mercado mediante el puente MT5."""
        req = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": float(price),
            "sl": float(sl),
            "tp": float(tp),
            "deviation": 20,
            "magic": int(magic),
            "comment": str(comment),
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        res = self.mt5.order_send(req)
        return res

    def modificar_sl_tp(self, ticket: int, symbol: str, sl: float, tp: float) -> Any:
        """Modifica SL y TP de una posicion existente."""
        req = {
            "action": self.mt5.TRADE_ACTION_SLTP,
            "position": int(ticket),
            "symbol": symbol,
            "sl": float(sl),
            "tp": float(tp)
        }
        return self.mt5.order_send(req)

    def ejecutar_ciclo(self):
        """Metodo invocado periodicamente por el Director."""
        for symbol in ORB_CONFIG.keys():
            try:
                self.procesar_activo(symbol)
            except Exception as e:
                log.error(f"[ORB_SNIPER] Error procesando {symbol}: {e}")


if __name__ == "__main__":
    log.info("[ALFA.ORB_SNIPER] Arrancando ejecutor autonomo...")
    sniper = AlfaOrbMomentumSniper()
    while True:
        sniper.ejecutar_ciclo()
        time.sleep(2)
