# Blue Sphere

**Blue Sphere** — планировщик учебной нагрузки, предназначенный для отображения расписания, анализа загруженности школьных классов и сбора обратной связи от учеников после учебного дня.

Проект состоит из:
- **Flutter Mini App** — пользовательский интерфейс для MAX WebApp;
- **FastAPI** — REST API и бизнес-логика;
- **PostgreSQL** — основная база данных;
- **MAX Bot** — взаимодействие с пользователями и прохождение опросов;
- **Scheduler** — планирование уведомлений и AI-задач;
- **AI Worker** — обработка очереди AI-анализа;
- **Nginx** — раздача собранного Flutter Web.

В этом README описаны установка, запуск, обслуживание и диагностика всего проекта через Docker Compose.

Документация по отдельным частям:
- [Backend](backend/README.md) — устройство Python backend, API, тесты и служебные скрипты.
- [Frontend](frontend/README.md) — архитектура Flutter-приложения, экраны, модели и сборка.

---

## 1. Структура репозитория

```text
BlueSphere/
├── backend/
│   ├── migrations/             # Миграции Alembic
│   ├── scripts/                # Административные и демонстрационные скрипты
│   ├── tests/                  # Backend-тесты
│   ├── .env.example            # Пример переменных окружения
│   ├── Dockerfile.api
│   ├── Dockerfile.bot
│   ├── Dockerfile.scheduler
│   ├── Dockerfile.ai-worker
│   └── README.md
│
├── frontend/
│   ├── android/                # Android-конфигурация Flutter
│   ├── assets/                 # Изображения и SVG
│   ├── fonts/                  # Шрифты
│   ├── lib/                    # Исходный код Flutter
│   ├── test/                   # Flutter-тесты
│   ├── web/                    # Web entrypoint и MAX WebApp SDK
│   ├── Dockerfile.mini-app     # Сборка и запуск Mini App
│   ├── nginx.conf              # Конфигурация Nginx
│   └── README.md
│
├── docker-compose.yml          # Запуск всех сервисов
├── Dockerfile                  # Универсальный backend Dockerfile
├── requirements.txt            # Зависимости backend для Docker
└── README.md
```

---

## 2. Требования

Для запуска проекта необходимы:

- Docker Engine;
- Docker Compose v2 (`docker compose`);
- Git;
- доступ к репозиторию;
- токен MAX-бота;
- секретный ключ JWT.

Для локальной разработки frontend без Docker дополнительно потребуется Flutter SDK.

Проверка Docker:

```bash
docker --version
docker compose version
```

---

## 3. Подготовка окружения

### 3.1. Клонирование репозитория

```bash
git clone <URL_REPOSITORY>
cd BlueSphere
```

### 3.2. Создание файла окружения

В репозитории находится пример конфигурации:

```text
backend/.env.example
```

Создай на его основе рабочий файл:

```bash
cp backend/.env.example backend/.env
```

Открой `backend/.env` и заполни обязательные значения.

Минимально необходимые параметры:

```env
POSTGRES_USER=bluesphere
POSTGRES_PASSWORD=replace_with_secure_password
POSTGRES_DB=bluesphere

DATABASE_URL=postgresql+psycopg://bluesphere:replace_with_secure_password@postgres:5432/bluesphere

JWT_SECRET_KEY=replace_with_long_random_secret

BOT_TOKEN=replace_with_max_bot_token

FRONTEND_URL=http://localhost:8080

DEMO_MODE=false
SEND_NOTIFICATIONS=false

AI_BASE_URL=
AI_TOKEN=
AI_MODEL=

AI_FALLBACK_BASE_URL=
AI_FALLBACK_TOKEN=
AI_FALLBACK_MODEL=

AI_TIMEOUT_SECONDS=60
AI_MAX_OUTPUT_TOKENS=4000
```

Назначение параметров:

| Переменная | Назначение |
|---|---|
| `POSTGRES_USER` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL |
| `POSTGRES_DB` | Имя базы данных |
| `DATABASE_URL` | Строка подключения backend к PostgreSQL |
| `JWT_SECRET_KEY` | Секрет подписи JWT |
| `BOT_TOKEN` | Токен MAX-бота |
| `FRONTEND_URL` | Разрешённые frontend-origin, через запятую |
| `DEMO_MODE` | Режим демонстрационных данных |
| `SEND_NOTIFICATIONS` | Разрешение реальной отправки уведомлений |
| `AI_BASE_URL` | URL основного AI API |
| `AI_TOKEN` | Токен основного AI API |
| `AI_MODEL` | Название основной модели |
| `AI_FALLBACK_BASE_URL` | URL резервного AI API |
| `AI_FALLBACK_TOKEN` | Токен резервного AI API |
| `AI_FALLBACK_MODEL` | Название резервной модели |
| `AI_TIMEOUT_SECONDS` | Таймаут AI-запроса |
| `AI_MAX_OUTPUT_TOKENS` | Максимальный размер ответа AI |

Для Docker Compose строка `DATABASE_URL` должна использовать имя сервиса `postgres` в качестве хоста:

```text
postgresql+psycopg://USER:PASSWORD@postgres:5432/DB_NAME
```

Не используй `localhost` в адресе PostgreSQL внутри контейнеров: в этом случае backend будет искать базу данных внутри собственного контейнера.

Если пароль содержит специальные символы (`@`, `#`, `/`, `:` и другие), URL-компоненты пароля необходимо кодировать.

Например:

```text
@ → %40
# → %23
/ → %2F
```

### 3.3. Безопасность файла окружения

`backend/.env` содержит секреты и не должен попадать в Git.

Не публикуй:
- токен MAX;
- пароль PostgreSQL;
- JWT secret;
- AI API tokens;
- production connection strings.

Для изменения конфигурации используй локальный `.env`, а в репозитории храни только `.env.example`.

---

## 4. Запуск проекта

Все команды ниже выполняются из корня репозитория.

### 4.1. Проверка конфигурации

```bash
docker compose --env-file backend/.env config -q
```

Если команда завершилась без ошибок, Compose смог прочитать конфигурацию и переменные окружения.

Для просмотра итоговой конфигурации:

```bash
docker compose --env-file backend/.env config
```

Не публикуй вывод этой команды без проверки: в нём могут присутствовать значения переменных окружения.

### 4.2. Сборка образов

```bash
docker compose --env-file backend/.env build
```

Пересборка только конкретного сервиса:

```bash
docker compose --env-file backend/.env build api
docker compose --env-file backend/.env build bot
docker compose --env-file backend/.env build scheduler
docker compose --env-file backend/.env build ai-worker
docker compose --env-file backend/.env build mini-app
```

### 4.3. Запуск всех сервисов

```bash
docker compose --env-file backend/.env up -d
```

Запуск с предварительной сборкой:

```bash
docker compose --env-file backend/.env up -d --build
```

Compose поднимает следующие сервисы:

| Сервис | Назначение | Порт |
|---|---|---|
| `postgres` | PostgreSQL 16 | Внутренний порт 5432 |
| `migrate` | Однократное применение миграций | — |
| `api` | FastAPI | `3000` |
| `bot` | MAX Bot | — |
| `scheduler` | Планировщик | — |
| `ai-worker` | Обработка AI-задач | — |
| `mini-app` | Flutter Web + Nginx | `8080` |

Порт Mini App можно изменить переменной `MINI_APP_PORT`. По умолчанию используется `8080`.

Например:

```env
MINI_APP_PORT=8081
```

После запуска:

- Mini App: http://localhost:8080
- API: http://localhost:3000
- Swagger UI: http://localhost:3000/docs
- OpenAPI JSON: http://localhost:3000/openapi.json

### 4.4. Порядок запуска сервисов

Compose использует проверки готовности и зависимости:

1. Запускается PostgreSQL.
2. Compose ожидает успешный healthcheck PostgreSQL.
3. Сервис `migrate` выполняет `alembic upgrade head`.
4. После успешного завершения миграций запускается API.
5. Compose ожидает успешный healthcheck API.
6. Запускаются MAX Bot, Scheduler и AI Worker.
7. Mini App раздаётся через Nginx.

Сервис `migrate` является одноразовым: после успешного применения миграций он завершает работу с кодом `0`. Это нормальное поведение.

### 4.5. Проверка состояния

```bash
docker compose --env-file backend/.env ps
```

Для просмотра также остановленных контейнеров:

```bash
docker compose --env-file backend/.env ps -a
```

Ожидаемые состояния:
- `postgres` — healthy;
- `api` — healthy;
- `bot`, `scheduler`, `ai-worker`, `mini-app` — running;
- `migrate` — exited (0).

---

## 5. Управление контейнерами

### Просмотр логов всех сервисов

```bash
docker compose --env-file backend/.env logs -f
```

### Просмотр логов конкретного сервиса

```bash
docker compose --env-file backend/.env logs -f postgres
docker compose --env-file backend/.env logs -f migrate
docker compose --env-file backend/.env logs -f api
docker compose --env-file backend/.env logs -f bot
docker compose --env-file backend/.env logs -f scheduler
docker compose --env-file backend/.env logs -f ai-worker
docker compose --env-file backend/.env logs -f mini-app
```

Последние 100 строк:

```bash
docker compose --env-file backend/.env logs --tail=100 api
```

### Перезапуск сервиса

```bash
docker compose --env-file backend/.env restart api
docker compose --env-file backend/.env restart bot
docker compose --env-file backend/.env restart scheduler
docker compose --env-file backend/.env restart ai-worker
docker compose --env-file backend/.env restart mini-app
```

### Остановка проекта

```bash
docker compose --env-file backend/.env down
```

Эта команда останавливает и удаляет контейнеры, но сохраняет Docker volume с данными PostgreSQL.

**Не запускай `docker compose down -v`, если не планируешь удалить данные базы данных.**

### Обновление после изменения исходников

```bash
docker compose --env-file backend/.env up -d --build
```

Если изменился только frontend:

```bash
docker compose --env-file backend/.env up -d --build mini-app
```

Если изменился только backend:

```bash
docker compose --env-file backend/.env up -d --build api bot scheduler ai-worker
```

---

## 6. Миграции базы данных

Миграции управляются Alembic и находятся в:

```text
backend/migrations/versions/
```

При стандартном запуске Compose миграции автоматически выполняются сервисом `migrate`.

Проверить текущую версию схемы:

```bash
docker compose --env-file backend/.env exec api alembic current
```

Посмотреть историю миграций:

```bash
docker compose --env-file backend/.env exec api alembic history
```

Проверить актуальную голову:

```bash
docker compose --env-file backend/.env exec api alembic heads
```

Повторно применить миграции:

```bash
docker compose --env-file backend/.env run --rm --no-deps migrate
```

Не редактируй уже применённые миграции. Для изменения структуры создавай новую миграцию.

**Перед миграциями на рабочей базе:**
1. Проверь, к какой базе подключается `DATABASE_URL`.
2. Сделай резервную копию.
3. Изучи новую миграцию и её `upgrade()` / `downgrade()`.
4. Проверь текущую версию Alembic.
5. Только после проверки запускай миграцию.

Не используй демонстрационные и тестовые скрипты на рабочей базе без отдельной проверки их поведения.

---

## 7. Запуск backend/scripts

Служебные скрипты расположены в `backend/scripts/`.

Для запуска через Docker Compose используй контейнер API: в нём уже установлены backend-зависимости и доступны переменные окружения.

Если API-контейнер запущен:

```bash
docker compose --env-file backend/.env exec api python scripts/ИМЯ_СКРИПТА.py
```

Для интерактивных скриптов:

```bash
docker compose --env-file backend/.env exec -it api python scripts/ИМЯ_СКРИПТА.py
```

Если API-контейнер не запущен, но PostgreSQL работает:

```bash
docker compose --env-file backend/.env run --rm --no-deps api python scripts/ИМЯ_СКРИПТА.py
```

Для интерактивного запуска одноразового контейнера:

```bash
docker compose --env-file backend/.env run --rm -it --no-deps api python scripts/ИМЯ_СКРИПТА.py
```

### 7.1. Подготовка демонстрационной школы и классов

```bash
docker compose --env-file backend/.env exec api python scripts/seed.py
```

Создаёт или находит демонстрационную школу № 1, учебный год `2026-2027` и классы с 1-го по 11-й (параллели А, Б, В и Г).

### 7.2. Генерация расписания

```bash
docker compose --env-file backend/.env exec api python scripts/seed_schedule.py \
  --start-date 2026-09-01 \
  --end-date 2026-09-30
```

Создаёт демонстрационных учителей, предметы, назначения и расписание на будние дни указанного периода.

Скрипт использует заранее заданную демонстрационную школу и учебный год. Для 9 сентября предусмотрены специальные планы для классов 5А, 5Б и 5В.

### 7.3. Создание шаблонов опросов

```bash
docker compose --env-file backend/.env exec api python scripts/seed_survey_questions.py
```

Создаёт или обновляет три шаблона:
- общая оценка состояния после учебного дня;
- предметы, на которых было тревожно;
- предметы, которые давались легко.

Повторный запуск обновляет существующие шаблоны и не должен создавать их дубликаты.

### 7.4. Создание экземпляров опросов

Сначала выполни предварительный просмотр:

```bash
docker compose --env-file backend/.env exec api python scripts/create_survey_instances.py \
  --date 2026-09-09
```

Для фактической записи в базу добавь `--create`:

```bash
docker compose --env-file backend/.env exec api python scripts/create_survey_instances.py \
  --date 2026-09-09 \
  --create
```

Без `--create` база не изменяется.

Экземпляры создаются для классов, у которых есть расписание на указанную дату. Время открытия и закрытия рассчитывается с учётом часового пояса школы.

### 7.5. Создание тестового ученика

```bash
docker compose --env-file backend/.env exec -it api python scripts/create_test_student.py
```

Скрипт интерактивно запрашивает:
- MAX user ID;
- ФИО;
- ID школы;
- учебный год;
- код класса;
- дату зачисления.

Если дата не указана, используется `2026-09-01`.

### 7.6. Добавление администратора

```bash
docker compose --env-file backend/.env exec -it api python scripts/add_admin.py
```

Запрашивает MAX user ID, ФИО и ID школы.

### 7.7. Создание или перенос учителя

```bash
docker compose --env-file backend/.env exec -it api python scripts/create_teacher.py
```

Скрипт позволяет:
- создать учётную запись учителя;
- перенести выбранные предметные назначения на нового учителя;
- выдать доступ к выбранным классам без изменения предметных назначений.

Перед подтверждением скрипт показывает выбранные классы и последствия операции.

### 7.8. Проверка конфликтов расписания

```bash
docker compose --env-file backend/.env exec api python scripts/check_schedule_conflicts.py
```

Проверяет расписание на конфликты и выводит найденные проблемы с указанием школы, класса, предмета, учителя, кабинета и подгруппы.

### 7.9. Корректировка демонстрационного расписания

```bash
docker compose --env-file backend/.env exec api python scripts/fix_demo_schedule.py
```

Скрипт исправляет заранее заданный демонстрационный набор занятий.

```bash
docker compose --env-file backend/.env exec api python scripts/update_demo_schedule.py
```

Скрипт обновляет демонстрационное занятие по английскому языку для 5А, 5Б и 5В, включая разделение на подгруппы и назначение учителей.

Эти два скрипта рассчитаны на конкретные демонстрационные данные. Не запускай их на произвольной базе.

### 7.10. Режим работы скриптов

Скрипты используют `DEMO_MODE` для определения типа создаваемых пользователей.

- `DEMO_MODE=true` — демонстрационные пользователи;
- `DEMO_MODE=false` — обычные пользователи.

В `scripts/user_mode.py` предусмотрена дополнительная защита: база `bluesphere_restore_test` запрещена для скриптов, изменяющих данные.

Перед запуском любого скрипта:
1. Проверь `DATABASE_URL`.
2. Проверь `DEMO_MODE`.
3. Убедись, что выбрана нужная база.
4. Изучи действие скрипта, если он изменяет пользователей, роли или расписание.

---

## 8. Работа с AI

AI-компонент состоит из планировщика задач и отдельного worker.

- Scheduler создаёт задачи анализа.
- AI Worker получает задачи из очереди, подготавливает контекст, обращается к AI API и сохраняет результат.
- Основной и резервный провайдеры настраиваются через переменные окружения.

Для работы AI необходимо заполнить:

```env
AI_BASE_URL=
AI_TOKEN=
AI_MODEL=
```

При необходимости можно указать резервного провайдера:

```env
AI_FALLBACK_BASE_URL=
AI_FALLBACK_TOKEN=
AI_FALLBACK_MODEL=
```

Если AI-переменные не заполнены, AI Worker не сможет выполнять полноценный анализ.

Проверка логов:

```bash
docker compose --env-file backend/.env logs -f ai-worker
docker compose --env-file backend/.env logs -f scheduler
```

Наличие запущенного контейнера не означает, что внешний AI API доступен. Работоспособность зависит от URL, токена, модели, квот и ограничений провайдера.

---

## 9. MAX и уведомления

Для авторизации и работы MAX Bot требуется действительный `BOT_TOKEN`.

По умолчанию в конфигурации рекомендуется:

```env
SEND_NOTIFICATIONS=false
```

Это отключает реальную отправку уведомлений планировщиком.

Для включения отправки:

```env
SEND_NOTIFICATIONS=true
```

Перед включением:
- проверь токен бота;
- проверь целевую базу данных;
- проверь режим `DEMO_MODE`;
- убедись, что в базе находятся нужные пользователи;
- изучи логи планировщика.

Не включай реальные массовые уведомления в тестовом окружении.

---

## 10. Резервное копирование PostgreSQL

Данные контейнера PostgreSQL хранятся в Docker volume `postgres_data`.

Для создания SQL-дампа:

```bash
docker compose --env-file backend/.env exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > bluesphere_backup.sql
```

Для восстановления из дампа:

```bash
cat bluesphere_backup.sql | \
docker compose --env-file backend/.env exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Восстановление может перезаписать или дополнить существующие данные. Перед восстановлением проверь целевую базу и сделай отдельную резервную копию.

Не храни дампы с реальными персональными данными в публичном репозитории.

---

## 11. Диагностика и возможные проблемы

### 11.1. `POSTGRES_USER is required` или другая обязательная переменная

Причина: Compose не получил переменные окружения.

Проверь:
- существует ли `backend/.env`;
- правильно ли указано имя файла;
- заполнены ли обязательные переменные.

Запускай Compose с явным файлом:

```bash
docker compose --env-file backend/.env config -q
```

### 11.2. Backend не подключается к PostgreSQL

Проверь `DATABASE_URL`.

Внутри Docker Compose хост должен быть `postgres`, а не `localhost`.

Правильный пример:

```text
postgresql+psycopg://bluesphere:password@postgres:5432/bluesphere
```

Проверь состояние базы:

```bash
docker compose --env-file backend/.env ps postgres
docker compose --env-file backend/.env logs postgres
```

### 11.3. `migrate` завершился с ошибкой

Проверь:

```bash
docker compose --env-file backend/.env logs migrate
docker compose --env-file backend/.env exec api alembic current
docker compose --env-file backend/.env exec api alembic heads
```

Типичные причины:
- неправильный `DATABASE_URL`;
- база ещё не готова;
- ошибка в миграции;
- база находится на неожиданной версии схемы;
- подключение направлено не к той базе.

Не пытайся исправлять проблему удалением volume или пересозданием базы, пока не проверены данные и причина ошибки.

### 11.4. API не становится healthy

Проверь:

```bash
docker compose --env-file backend/.env logs api
docker compose --env-file backend/.env ps -a
```

Проверь доступность:

```bash
curl http://localhost:3000/openapi.json
```

Если API не запускается, сначала проверь миграции и подключение к PostgreSQL.

### 11.5. Порт уже занят

Если порт `3000` занят, измени проброс порта в `docker-compose.yml`.

Если порт `8080` занят, задай:

```env
MINI_APP_PORT=8081
```

После изменения пересоздай сервис:

```bash
docker compose --env-file backend/.env up -d
```

### 11.6. Mini App открывается, но не загружает данные

Проверь:
- доступность API;
- авторизацию через MAX;
- `initData`;
- JWT в ответе API;
- адрес backend в `frontend/lib/data/api_service.dart`;
- CORS-конфигурацию backend.

В текущем frontend адрес API задан константой:

```dart
static const String baseUrl = 'https://blue-sphere-bot.bothost.tech';
```

Поэтому локальная сборка Mini App не переключает API на `localhost:3000` автоматически.

Кроме того, запуск в обычном браузере вне MAX не предоставляет настоящий `initData`. В таком случае авторизация через MAX Mini App не пройдёт.

### 11.7. MAX Bot не запускается

Проверь:

```bash
docker compose --env-file backend/.env logs bot
```

Убедись, что:
- `BOT_TOKEN` действителен;
- токен относится к нужному боту;
- база доступна;
- нет второго конфликтующего экземпляра бота, использующего тот же способ получения обновлений.

### 11.8. Уведомления не отправляются

Проверь:

```env
SEND_NOTIFICATIONS=false
```

При `false` планировщик не должен отправлять реальные уведомления.

Если отправка разрешена, проверь токен, логи Scheduler и настройки пользователей.

### 11.9. AI Worker запущен, но задачи не выполняются

Проверь:
- `AI_BASE_URL`;
- `AI_TOKEN`;
- `AI_MODEL`;
- резервные настройки;
- квоты и доступность провайдера;
- логи `ai-worker`.

Контейнер может быть запущен, даже если внешний AI API не отвечает или модель недоступна.

### 11.10. После изменения исходников контейнер использует старый код

Пересобери соответствующий образ:

```bash
docker compose --env-file backend/.env up -d --build api
```

Для frontend:

```bash
docker compose --env-file backend/.env up -d --build mini-app
```

---

## 12. Полезные команды

Проверить конфигурацию:

```bash
docker compose --env-file backend/.env config -q
```

Собрать образы:

```bash
docker compose --env-file backend/.env build
```

Запустить:

```bash
docker compose --env-file backend/.env up -d
```

Проверить состояние:

```bash
docker compose --env-file backend/.env ps -a
```

Посмотреть логи:

```bash
docker compose --env-file backend/.env logs --tail=100
```

Проверить API:

```bash
curl http://localhost:3000/openapi.json
```

Проверить Mini App:

```bash
curl -I http://localhost:8080
```

Остановить:

```bash
docker compose --env-file backend/.env down
```

---

## 13. Важные правила эксплуатации

1. Не коммить `.env` и секреты.
2. Не запускай демонстрационные скрипты на production без проверки.
3. Не применяй миграции к рабочей базе без резервной копии и проверки.
4. Не используй `docker compose down -v`, если требуется сохранить PostgreSQL.
5. Не включай реальные уведомления без проверки целевого окружения.
6. Не считай успешный запуск контейнера подтверждением работоспособности внешнего AI API.
7. Перед обновлением рабочей версии проверяй миграции, конфигурацию и логи.
8. После изменения backend или frontend пересобирай соответствующие Docker-образы.

---

**Blue Sphere** — единая система отображения расписания и учебной нагрузки, сбора обратной связи и поддержки принятия решений на основе агрегированных данных.