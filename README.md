# ReconcileHub

ReconcileHub — внутренняя платформа банковских и финансовых сверок.

## Активная архитектура

```text
React / TypeScript / Vite
          ↓
       FastAPI
          ↓
 RBAC / Audit / Modules
          ↓
 SQLite + reconciliation engines
```

Основной production-код:

- `src/` — React frontend;
- `api.py` — FastAPI backend и HTTP API;
- `modules/` — подключаемые модули сверок;
- `core/` — общая бизнес-логика парсинга и сверки;
- `utils/` — backend-инфраструктура: БД, permissions, auth sessions;
- `tests/` — backend regression tests;
- `scripts/` — служебные developer scripts;
- `.github/workflows/` — CI.

## Что лежит в archive/

`archive/` не является частью рабочего приложения.

Там хранится старый код и документы только как историческая справка / «на всякий
случай». Новый production-код не должен импортировать файлы из `archive/`.

Сейчас там находятся:

- `archive/legacy_streamlit/` — старый Streamlit UI;
- `archive/legacy_docs/` — документы завершённой миграции архитектуры.

## Локальный запуск

### Windows

Запустите:

```bat
start.bat
```

Скрипт проверит Python/Node, соберёт React и запустит FastAPI на:

```text
http://localhost:8000
```

### Вручную

```bash
python -m pip install -r requirements.txt
npm ci
npm run build
python api.py
```

## Разработка frontend

```bash
npm ci
npm run dev
```

TypeScript check:

```bash
npm run lint
```

Production build:

```bash
npm run build
```

## Tests

```bash
python -m pytest -q
```

GitHub Actions автоматически проверяет:

- backend pytest;
- TypeScript;
- production frontend build;
- black-box E2E critical workflows.

## Excel / CSV источники

В Bank RRN и Конструкторе сверок после загрузки файла можно выбрать:

- конкретный лист Excel;
- номер строки, которая содержит заголовки;
- предпросмотр первых строк уже после применения этих настроек.

Например, если лист `Transactions` содержит служебный заголовок в строках 1–3,
а таблица начинается со строки 4, выберите лист `Transactions`, укажите
`Заголовок = 4` и нажмите `Применить`. Те же параметры передаются backend,
поэтому preview и фактическая сверка читают один и тот же диапазон.

Для CSV выбор листа отключён, но строка заголовков поддерживается.

## Экспериментальная AI-сводка Bank RRN

После выполнения банковской сверки в рабочем месте Bank RRN доступна кнопка
`AI-сводка`. Анализ работает в двух режимах:

- без внешнего ключа — локальные детерминированные гипотезы по агрегатам
  (граница месяца, концентрация unmatched по датам, комиссия, дубликаты,
  качество данных);
- при наличии `OPENAI_API_KEY` — те же агрегаты дополнительно интерпретируются
  через OpenAI Responses API.

Для внешнего AI не отправляются RRN и raw-строки исходных файлов: backend
формирует только агрегированные показатели и диагностические признаки.

Переменные окружения:

```text
OPENAI_API_KEY=...
RECONCILEHUB_AI_MODEL=gpt-6-astra
```

`RECONCILEHUB_AI_MODEL` необязателен. Если внешний AI недоступен, интерфейс
автоматически показывает локальные гипотезы.

## Production-lite

Основные runtime-настройки задаются переменными окружения:

```text
RECONCILEHUB_ENV=production
RECONCILEHUB_DB_PATH=database/reconcile_hub.db
RECONCILEHUB_ADMIN_PASSWORD=<strong-password>

# Пусто = только same-origin frontend, что является безопасным default в production.
# Для отдельного frontend укажите разрешённые origins через запятую.
RECONCILEHUB_ALLOWED_ORIGINS=https://reconcile.example.com

RECONCILEHUB_LOG_LEVEL=INFO
RECONCILEHUB_LOG_DIR=logs

RECONCILEHUB_BACKUP_ENABLED=true
RECONCILEHUB_BACKUP_DIR=backups
RECONCILEHUB_BACKUP_INTERVAL_HOURS=24
RECONCILEHUB_BACKUP_RETENTION_DAYS=14
```

В development CORS остаётся открытым для удобства локальной разработки. В
production wildcard CORS по умолчанию отключён.

Логи пишутся в консоль и в ротируемый `logs/reconcilehub.log` (до 10 МБ,
5 файлов). API добавляет `X-Request-ID` и логирует method/path/status/duration;
необработанные production-ошибки возвращают request ID без stack trace клиенту.

При `RECONCILEHUB_BACKUP_ENABLED=true` сервер делает безопасную SQLite backup
через SQLite Backup API при старте и далее по расписанию. Старые копии удаляются
по retention. Ручной backup:

```bash
python scripts/backup_db.py
```

Liveness:

```text
GET /api/health
```

Readiness (доступность БД + загрузка модулей):

```text
GET /api/ready
```

## Repository hygiene

Не коммитить сгенерированные или локальные файлы:

- `dist/`;
- `node_modules/`;
- `__pycache__/`;
- `*.pyc`;
- `*.db`;
- `*.zip`;
- `.env*`.

Они уже исключены через `.gitignore`.

Если старый код больше не используется, но его хочется сохранить для справки,
переносите его в `archive/`, а не оставляйте рядом с production-кодом.
