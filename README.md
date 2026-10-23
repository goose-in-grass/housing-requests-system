# Система учёта заявок жильцов УК

Веб-система приёма и контроля заявок жильцов управляющей компании по ТЗ
(`ТЗ Система учёта заявок жильцов УК.md`). Django 5.2 LTS, PostgreSQL, Bootstrap 5.

## Запуск в Docker

```
docker compose up
```

Сайт: http://localhost:8000. При старте применяются миграции и создаются демо-данные.

## Локальный запуск

Одной командой (создаст окружение и базу при необходимости, применит миграции, добавит демо-данные и запустит сайт):

```
./run.sh          # порт 8000
./run.sh 8001     # другой порт
```

Требуется запущенный PostgreSQL. То же самое по шагам:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
createdb zhkh_tickets
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo
.venv/bin/python manage.py createsuperuser   # администратор для /admin/
.venv/bin/python manage.py runserver
```

Подключение к БД задаётся переменными `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_HOST`, `POSTGRES_PORT`. Секреты и режим: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`,
`DJANGO_ALLOWED_HOSTS`, `TIME_ZONE` (по умолчанию Europe/Kaliningrad).

Письма в прототипе печатаются в консоль (`EMAIL_BACKEND`); для SMTP переопределите бэкенд.

## Демо-пользователи

Пароль у всех: `Demo-pass-2026`.

| Роль | Логин |
| --- | --- |
| Жилец | resident@uk.local |
| Диспетчер | dispatcher@uk.local |
| Мастер | master1@uk.local, master2@uk.local |
| Начальник участка | chief@uk.local (участок 1), chief2@uk.local (участок 2) |

## Устройство

| Приложение | Назначение |
| --- | --- |
| `accounts` | Жильцы, сотрудники, роли (группы Django), регистрация, вход |
| `directory` | Участки, дома, категории с нормативными сроками |
| `tickets` | Заявки; бизнес-логика только в `tickets/services.py` |
| `reports` | Четыре отчёта начальника и выгрузка в Excel |

Правила: все смены статуса идут через `tickets/services.py` в одной транзакции с блокировкой
строки (`select_for_update`) и записью в историю; права проверяются на сервере; фото отдаются
только тем, кто видит заявку; просрочка вычисляется по текущему времени, а не хранится.

## Проверки

```
.venv/bin/ruff check .
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
```
