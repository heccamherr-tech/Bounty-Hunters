"""
cuant_volatility.py — ALFA 4.0 Quantitative Stream 1: Volatility Breakout Asimétrico
===================================================================================
Calcula Z-Score de Amplitud (Log-Range) y Rate of Change (ROC) de alta velocidad.
Implementa validación asimétrica para entradas Long vs Short.
"""

from __future__ import annotations
import math
from collections import deque
from typing import Dict, Any, Tuple, Optional

try:
    import numpy as np
except ImportError:
    np = None


class VolatilityBreakoutEngine:
    """
    Evaluador de Volatilidad Asimétrica.
    Calcula:
      1. Amplitud Logarítmica: R_t = ln(High_t) - ln(Low_t)
      2. Z-Score de Amplitud: Z = (R_t - mean(R)) / std(R)
      3. Rate of Change (ROC): ROC = ((P_t - P_{t-dt}) / P_{t-dt}) * 100
    """
    def __init__(
        self,
        ventana_zscore: int = 200,
        alpha_base: float = 2.5,
        beta_base: float = 0.05
    ):
        self.n = ventana_zscore
        self.alpha_base = alpha_base
        self.beta_base = beta_base
        
        # Colas circulares O(1)
        self.log_ranges: deque = deque(maxlen=self.n)
        self.precios_tick: deque = deque(maxlen=50)

    def actualizar_precio(self, high: float, low: float, close: float) -> Dict[str, Any]:
        """
        Ingresa una nueva vela/tick y calcula Z-Score y ROC en tiempo real.
        """
        # 1. Amplitud del rango logarítmico
        if high > 0 and low > 0 and high >= low:
            r_t = math.log(high) - math.log(low)
        else:
            r_t = 0.0
            
        self.log_ranges.append(r_t)
        self.precios_tick.append(close)
        
        # 2. Z-Score de Amplitud
        z_score = 0.0
        n_elem = len(self.log_ranges)
        if n_elem >= 10:
            if np is not None:
                arr = np.array(self.log_ranges)
                mu = float(np.mean(arr))
                sigma = float(np.std(arr))
            else:
                mu = sum(self.log_ranges) / n_elem
                variance = sum((x - mu) ** 2 for x in self.log_ranges) / n_elem
                sigma = math.sqrt(variance)
            if sigma > 1e-8:
                z_score = (r_t - mu) / sigma
                
        # 3. Rate of Change (ROC)
        roc = 0.0
        if len(self.precios_tick) >= 2:
            p_actual = self.precios_tick[-1]
            p_prev = self.precios_tick[0]
            if p_prev > 0:
                roc = ((p_actual - p_prev) / p_prev) * 100.0
                
        # 4. Evaluación Asimétrica
        # Condición Long: Z > alpha  AND  ROC > beta
        # Condición Short: Z > (alpha * 1.2)  AND  ROC < -(beta * 0.8)
        umbral_z_short = self.alpha_base * 1.2
        umbral_roc_short = - (self.beta_base * 0.8)
        
        long_pass = (z_score >= self.alpha_base) and (roc >= self.beta_base)
        short_pass = (z_score >= umbral_z_short) and (roc <= umbral_roc_short)
        
        return {
            "r_t": round(r_t, 6),
            "z_score_amplitud": round(z_score, 4),
            "roc_pct": round(roc, 4),
            "long_pass": long_pass,
            "short_pass": short_pass,
            "ventana_llena": len(self.log_ranges) >= self.n
        }


if __name__ == "__main__":
    # Test básico del motor de volatilidad
    engine = VolatilityBreakoutEngine(ventana_zscore=50, alpha_base=2.0, beta_base=0.03)
    import random
    precio = 100.0
    for i in range(60):
        h = precio + random.uniform(0.1, 0.5)
        l = precio - random.uniform(0.1, 0.5)
        precio += random.uniform(-0.3, 0.3)
        res = engine.actualizar_precio(h, l, precio)
        if i % 10 == 0:
            print(f"Paso {i}: Z-Score={res['z_score_amplitud']}, ROC={res['roc_pct']}%, LongPass={res['long_pass']}, ShortPass={res['short_pass']}")
    print("[OK] cuant_volatility.py verificado.")
