# AGENTS.md - ALFA Quant Lab

Reglas obligatorias para cualquier agente (Google Jules incluido) que trabaje en este repositorio.

1. Sin emojis en codigo, logs, reportes ni commits.
2. Python 3.11. Dependencias permitidas: pandas, numpy, scipy, numba (opcional), pyarrow (opcional), pytest. Nada que requiera GPU ni claves.
3. Ninguna credencial, token o clave en el repositorio. Este laboratorio es 100% offline sobre datos historicos versionados en `data/`.
4. Prohibido el look-ahead: toda senal en la barra t solo puede usar informacion cerrada hasta t. Las entradas se ejecutan al open de t+1. Hay tests que lo verifican y deben seguir pasando.
5. Costos siempre activos: spread historico por barra (columna `spread` en puntos, ver `data/symbol_specs_bullfy_mt5.json`) + slippage + comision. Ningun resultado sin costos es valido.
6. Ningun parametro se elige por el maximo de un grid. Se elige por estabilidad (meseta) y se valida fuera de muestra (walk-forward). El periodo HOLDOUT (ultimas 6 semanas de datos) no se toca hasta la evaluacion final.
7. Todo resultado reportado debe ser reproducible con un comando documentado en `reports/DEEPTEST_REPORT.md`.
8. Mision completa en `MISSION.md`. Leerla entera antes de empezar.
