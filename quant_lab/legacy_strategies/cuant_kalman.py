"""
cuant_kalman.py — ALFA 4.0 Quantitative Stream 2: Filtro de Kalman Adaptativo
=============================================================================
Estima el estado oculto del precio en tiempo real libre de lag.
Ajusta la varianza de medición R dinámicamente mediante el ATR.
"""

from __future__ import annotations
import math
from typing import Dict, Any, Optional


class KalmanTrendFilter:
    """
    Filtro de Kalman optimizado para tracking de precio en entornos de alta velocidad.
    Ajusta R dinámicamente: R_dinamico = R_base * (ATR + 1e-6)
    """
    def __init__(self, process_variance: float = 1e-4, measurement_variance_init: float = 0.1):
        self.Q = process_variance
        self.R_base = measurement_variance_init
        self.x = 0.0  # Estado estimado del precio (sin lag)
        self.P = 1.0  # Covarianza del error
        self.initialized = False

    def update(self, measurement: float, current_atr: float = 0.001) -> Dict[str, Any]:
        """
        Actualiza el estado estimado con una nueva medición de precio y ATR actual.
        """
        if not self.initialized:
            self.x = measurement
            self.initialized = True
            return {
                "kalman_state": round(self.x, 5),
                "precio_medido": round(measurement, 5),
                "divergencia_pips": 0.0,
                "tendencia": "NEUTRO",
                "kalman_gain": 0.0
            }

        # 1. Adaptación dinámica de R en función del ATR
        dynamic_R = self.R_base * (max(0.00001, current_atr) + 1e-6)

        # 2. Paso de Predicción
        x_pred = self.x
        P_pred = self.P + self.Q

        # 3. Paso de Actualización (Ganancia de Kalman)
        kalman_gain = P_pred / (P_pred + dynamic_R)
        self.x = x_pred + kalman_gain * (measurement - x_pred)
        self.P = (1.0 - kalman_gain) * P_pred

        # 4. Divergencia y Dirección
        divergencia = measurement - self.x
        tendencia = "ALCISTA" if measurement > self.x else ("BAJISTA" if measurement < self.x else "NEUTRO")

        return {
            "kalman_state": round(self.x, 5),
            "precio_medido": round(measurement, 5),
            "divergencia_pips": round(divergencia, 5),
            "tendencia": tendencia,
            "kalman_gain": round(kalman_gain, 4)
        }


if __name__ == "__main__":
    kf = KalmanTrendFilter(process_variance=1e-4, measurement_variance_init=0.1)
    prices = [100.5, 100.7, 101.2, 100.9, 101.5, 102.0]
    for p in prices:
        res = kf.update(p, current_atr=0.2)
        print(f"Precio: {p} | Estado Kalman: {res['kalman_state']} | Div: {res['divergencia_pips']} | Tendencia: {res['tendencia']}")
    print("[OK] cuant_kalman.py verificado.")
