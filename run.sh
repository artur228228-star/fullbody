#!/usr/bin/env bash
# Запуск в одну команду: ./run.sh
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "Впиши BOT_TOKEN в .env и запусти снова"; exit 1; }
python bot.py
