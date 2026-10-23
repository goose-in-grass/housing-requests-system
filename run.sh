#!/usr/bin/env bash
# Локальный запуск одной командой: ./run.sh [порт]
# Создаёт .venv (если его нет), применяет миграции, добавляет демо-данные и запускает сервер.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-8000}"
DB="${POSTGRES_DB:-zhkh_tickets}"

if [ ! -x .venv/bin/python ]; then
  echo "→ Создаю виртуальное окружение и ставлю зависимости"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

if ! pg_isready -q; then
  echo "PostgreSQL не запущен. Запустите его (например: brew services start postgresql@18) и повторите." >&2
  exit 1
fi

if ! psql -lqt | cut -d'|' -f1 | grep -qw "$DB"; then
  echo "→ Создаю базу $DB"
  createdb "$DB"
fi

.venv/bin/python manage.py migrate -v0
.venv/bin/python manage.py seed_demo
echo "→ Сайт: http://localhost:$PORT  (админка: /admin/login/)"
exec .venv/bin/python manage.py runserver "$PORT"
