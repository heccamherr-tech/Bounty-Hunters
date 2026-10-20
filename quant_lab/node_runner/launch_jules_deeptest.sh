#!/usr/bin/env bash
# Publica el laboratorio en GitHub y lanza la sesion unica de deeptest en Google Jules.
# Requisito previo (manual, una sola vez): repo privado vacio heccamherr-tech/alfa-quant-lab
# con la GitHub App de Jules autorizada sobre el.
set -euo pipefail
REPO="heccamherr-tech/alfa-quant-lab"
cd /home/hector/alfa_quant_lab

git remote get-url origin >/dev/null 2>&1 || git remote add origin "git@github.com:${REPO}.git"
git push -u origin main

jules new --repo "${REPO}" "Lee AGENTS.md y MISSION.md completos y ejecuta la mision entera en este unico turno, sin detenerte a pedir confirmacion: motor de backtest con costos y regla de 4% diario, forense de la perdida del 2026-10-20, controlador de riesgo de portafolio dinamico con correlacion rodante, ingenieria inversa de MS27 sobre los 13 meses de datos M5, busqueda walk-forward de un reglamento por instrumento con Deflated Sharpe y PBO, reglas cruzadas derivadas de datos, lector de cambios de patron con correccion en caliente, rulebooks JSON con schema, rulebook_engine con interfaz BrokerAdapter y test de paridad, y reports/DEEPTEST_REPORT.md. Si un instrumento no tiene ventaja fuera de muestra, marcalo tradable=false. Sin emojis. Commits frecuentes y pytest en verde al final." | tee /home/hector/alfa_quant_lab/.jules_session.txt
