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
