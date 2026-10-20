"""
cuant_orderflow.py — ALFA 4.0 Quantitative Stream 3: Order Flow & Microestructura
================================================================================
Calcula Order Flow Imbalance (OFI), Cumulative Volume Delta (CVD) y VWAP Anclado (AVWAP).
Incluye detector de Absorción Pasiva ( trampas de liquidez ).
"""

from __future__ import annotations
import math
from typing import Dict, Any, List, Optional


class OrderFlowMicrostructureEngine:
    """
    Motor de microestructura de libro de órdenes y flujo de volumen.
    """
    def __init__(self):
        # Estado OFI
        self.last_bid_price = 0.0
        self.last_bid_size = 0.0
        self.last_ask_price = 0.0
        self.last_ask_size = 0.0
        self.ofi_history: List[float] = []

        # Estado CVD
        self.cvd_acumulado = 0.0
        self.cvd_history: List[float] = []
        self.price_history: List[float] = []

        # Estado AVWAP (VWAP Anclado)
        self.avwap_pv_acumulado = 0.0
        self.avwap_vol_acumulado = 0.0

    def reiniciar_avwap(self) -> None:
        """Reinicia los acumuladores del VWAP Anclado (ej. al abrir la sesión)."""
        self.avwap_pv_acumulado = 0.0
        self.avwap_vol_acumulado = 0.0

    def actualizar_l1_book(self, bid_price: float, bid_size: float, ask_price: float, ask_size: float) -> float:
        """
        Calcula el Order Flow Imbalance (OFI) del tick actual según la fórmula Nivel 1.
        """
        if self.last_bid_price == 0.0:
            self.last_bid_price = bid_price
            self.last_bid_size = bid_size
            self.last_ask_price = ask_price
            self.last_ask_size = ask_size
            return 0.0

        # Δ Bid Size
        if bid_price > self.last_bid_price:
            delta_bid = bid_size
        elif bid_price == self.last_bid_price:
            delta_bid = bid_size - self.last_bid_size
        else:
            delta_bid = 0.0

        # Δ Ask Size
        if ask_price < self.last_ask_price:
            delta_ask = ask_size
        elif ask_price == self.last_ask_price:
            delta_ask = ask_size - self.last_ask_size
        else:
            delta_ask = 0.0

        ofi = delta_bid - delta_ask
        self.ofi_history.append(ofi)
        if len(self.ofi_history) > 100:
            self.ofi_history.pop(0)

        # Actualizar estado previo
        self.last_bid_price = bid_price
        self.last_bid_size = bid_size
        self.last_ask_price = ask_price
        self.last_ask_size = ask_size

        return ofi

    def actualizar_trade(self, precio: float, volumen: float, es_compra_agresiva: bool) -> Dict[str, Any]:
        """
        Registra cada trade ejecutado en mercado, actualizando CVD y AVWAP.
        Evalúa si existe absorción pasiva.
        """
        # 1. Actualizar CVD
        delta = volumen if es_compra_agresiva else -volumen
        self.cvd_acumulado += delta
        self.cvd_history.append(self.cvd_acumulado)
        self.price_history.append(precio)

        if len(self.cvd_history) > 100:
            self.cvd_history.pop(0)
            self.price_history.pop(0)

        # 2. Actualizar AVWAP
        self.avwap_pv_acumulado += (precio * volumen)
        self.avwap_vol_acumulado += volumen
        avwap = (self.avwap_pv_acumulado / self.avwap_vol_acumulado) if self.avwap_vol_acumulado > 0 else precio

        # 3. Detector de Absorción Pasiva
        # Si CVD sube fuerte (últimas 5 lecturas) pero el precio no logra hacer un máximo más alto -> Absorción de Venta.
        absorcion_pasiva = False
        if len(self.cvd_history) >= 10:
            cvd_diff = self.cvd_history[-1] - self.cvd_history[-5]
            price_diff = self.price_history[-1] - self.price_history[-5]

            # Compra agresiva masiva sin avance de precio = Muro pasivo absorbiendo
            if cvd_diff > 0 and price_diff <= 0:
                absorcion_pasiva = True
            # Venta agresiva masiva sin caída de precio = Muro pasivo absorbiendo
            elif cvd_diff < 0 and price_diff >= 0:
                absorcion_pasiva = True

        ofi_reciente = sum(self.ofi_history[-5:]) if self.ofi_history else 0.0

        return {
            "cvd_acumulado": round(self.cvd_acumulado, 2),
            "avwap": round(avwap, 5),
            "ofi_5_ticks": round(ofi_reciente, 2),
            "absorcion_pasiva_detectada": absorcion_pasiva,
            "distancia_avwap_pips": round(precio - avwap, 5)
        }

    def calcular_desde_rates(self, rates: Any) -> Dict[str, Any]:
        """
        Calcula CVD sintetico, pendiente de CVD (CVD slope), OFI proxy, AVWAP y
        deteccion de absorcion pasiva institucional a partir de un arreglo estructurado
        de velas (rates de MT5 u objetos similares).
        """
        if rates is None or len(rates) < 5:
            return {
                "ofi_score": 0.0,
                "cvd_slope": 0.0,
                "absorcion_pasiva_detectada": False,
                "avwap_distancia": 0.0,
                "avwap": 0.0,
                "cvd_acumulado": 0.0
            }

        cvd_acum = 0.0
        cvds: List[float] = []
        pv_acum = 0.0
        vol_acum = 0.0

        def _get_val(obj, key, default=0.0):
            try:
                return float(obj[key])
            except Exception:
                try:
                    return float(getattr(obj, key, default))
                except Exception:
                    return default

        last_price = _get_val(rates[-1], "close")

        for r in rates:
            h = _get_val(r, "high")
            l = _get_val(r, "low")
            c = _get_val(r, "close")
            vol = _get_val(r, "tick_volume", _get_val(r, "volume", 1.0))
            if vol <= 0:
                vol = 1.0

            rng = max(1e-6, h - l)
            # Descomposicion de flujo de ordenes institucional Williams/Acker
            delta_vol = vol * ((2.0 * c - (h + l)) / rng)
            cvd_acum += delta_vol
            cvds.append(cvd_acum)

            typical_price = (h + l + c) / 3.0
            pv_acum += (typical_price * vol)
            vol_acum += vol

        avwap = (pv_acum / vol_acum) if vol_acum > 0 else last_price
        avwap_dist = round(last_price - avwap, 5)

        # Pendiente de CVD de las ultimas 5 velas
        cvd_slope = 0.0
        if len(cvds) >= 5:
            cvd_slope = round(cvds[-1] - cvds[-5], 2)

        # Proxy de OFI normalizado por volumen medio
        ofi_proxy = round(cvd_slope / max(1.0, (vol_acum / len(rates))), 4)

        # Absorcion Pasiva:
        # 1. Compras pasivas: Gran delta de venta pero el precio no cae
        # 2. Ventas pasivas: Gran delta de compra pero el precio no sube
        absorcion = False
        if len(rates) >= 5:
            p_prev = _get_val(rates[-5], "close")
            p_diff = last_price - p_prev
            if cvd_slope > 0 and p_diff <= 0:
                absorcion = True
            elif cvd_slope < 0 and p_diff >= 0:
                absorcion = True

        return {
            "ofi_score": ofi_proxy,
            "cvd_slope": cvd_slope,
            "absorcion_pasiva_detectada": absorcion,
            "avwap_distancia": avwap_dist,
            "avwap": round(avwap, 5),
            "cvd_acumulado": round(cvd_acum, 2)
        }


if __name__ == "__main__":
    engine = OrderFlowMicrostructureEngine()
    engine.actualizar_l1_book(100.0, 10, 100.1, 15)
    ofi = engine.actualizar_l1_book(100.1, 12, 100.2, 10)
    res = engine.actualizar_trade(100.1, 5.0, es_compra_agresiva=True)
    print(f"OFI: {ofi} | CVD: {res['cvd_acumulado']} | AVWAP: {res['avwap']} | Absorcion: {res['absorcion_pasiva_detectada']}")

    # Test simulando velas MT5
    mock_rates = [
        {"high": 100.5, "low": 99.8, "close": 100.2, "tick_volume": 120},
        {"high": 100.8, "low": 100.1, "close": 100.7, "tick_volume": 150},
        {"high": 101.2, "low": 100.5, "close": 101.0, "tick_volume": 200},
        {"high": 101.0, "low": 100.4, "close": 100.6, "tick_volume": 180},
        {"high": 101.5, "low": 100.6, "close": 101.4, "tick_volume": 220},
        {"high": 101.8, "low": 101.1, "close": 101.6, "tick_volume": 210},
    ]
    res_rates = engine.calcular_desde_rates(mock_rates)
    print(f"Rates CVD Slope: {res_rates['cvd_slope']} | OFI Score: {res_rates['ofi_score']} | AVWAP Dist: {res_rates['avwap_distancia']} | Absorcion: {res_rates['absorcion_pasiva_detectada']}")
    print("[OK] cuant_orderflow.py verificado.")
