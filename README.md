# BUKKAX

**BUKKAX** — desktop-мессенджер на Python / PySide6.

> Статус: Alpha / personal project.

В проекте используются собственный TCP-протокол сообщений, UDP для медиа, SQLite на сервере и PySide6 для интерфейса.

## Возможности

- общий чат и личные сообщения;
- отправка файлов, изображений и содержимого буфера обмена;
- профили пользователей, аватары, подарки и новости;
- голосовые и видеозвонки;
- демонстрация экрана;
- шахматы с другом и локальным ботом;
- музыкальное окно;
- автообновление клиента;
- Developer Studio / визуальный Builder для интерфейса.

## Архитектура

```text
                         ┌──────────────────┐
                         │    client_qt.py  │
                         │     PySide6 UI   │
                         └───────┬──────────┘
                                 │
                  TCP 55555      │
                                 ▼
                         ┌──────────────────┐
                         │     server.py    │
                         │ users / chat /   │
                         │ calls / routing  │
                         └───────┬──────────┘
                                 │
                     ┌───────────┼───────────┐
                     │           │           │
                     ▼           ▼           ▼
                  SQLite      UDP media   HTTP update
                               55557/58       55556
```

Бинарный TCP framing вынесен в `protocol.py`.

## Быстрый запуск

Требуется Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

В отдельном окне:

```powershell
python server.py
```

Клиент:

```powershell
$env:BUKKAX_SERVER_IP="127.0.0.1"
python client_qt.py
```

Для подключения к удалённому серверу укажи его адрес через переменную окружения `BUKKAX_SERVER_IP`.

## Сборка EXE

Готовые скрипты:

```powershell
.\scripts\build_client.ps1
.\scripts\build_server.ps1
```

Результат появляется в `dist\`.

## Перед публикацией

Обязательно запусти:

```powershell
python scripts\prepublish_check.py .
```

Скрипт проверит, что в репозиторий не попали базы данных, backups, ключи, токены и некоторые другие приватные данные.

Полный чек-лист: [`docs/PUBLISH_CHECKLIST.md`](docs/PUBLISH_CHECKLIST.md).

## Структура

```text
BUKKAX/
├── client_qt.py
├── server.py
├── protocol.py
├── bukkax_chess_qt.py
├── bukkax_dev_builder.py
├── bukkax_builder_sync.py
├── bukkax_screen_share.py
├── bukkax_call_quality.py
├── music_player.py
├── bukkax_chess_assets/
├── sounds/
├── docs/
├── scripts/
├── .github/workflows/
├── requirements.txt
└── README.md
```

Не все модули обязательны: `prepare_github_repo.py` копирует только те, которые реально есть в твоей текущей локальной сборке.

## Документация

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — как связаны клиент, сервер и модули.
- [`docs/BUILD.md`](docs/BUILD.md) — запуск и сборка.
- [`docs/PUBLISH_CHECKLIST.md`](docs/PUBLISH_CHECKLIST.md) — что проверить перед Public.
- [`docs/FULL_CODE_GUIDE.md`](docs/FULL_CODE_GUIDE.md) — большой разбор кода BUKKAX (snapshot).

## Безопасность

Никогда не коммить:

- `chat_users.db` и другие рабочие БД;
- API keys / tokens / passwords;
- `.env`;
- cookies / `web_profile`;
- `updates/` с production EXE;
- логи, `.bak`, `.new`, `.download`;
- личные пути и локальные Developer Studio scripts.

Подробнее: [`SECURITY.md`](SECURITY.md).

## Лицензия

Лицензия специально **не выбрана автоматически**. Если репозиторий нужен только как портфолио, можно оставить код без open-source лицензии. Если хочешь разрешить другим использовать и изменять код — выбери, например, MIT или Apache-2.0.

См. [`LICENSE_NOT_SELECTED.md`](LICENSE_NOT_SELECTED.md).

---

### English

BUKKAX is an experimental Python/PySide6 desktop messenger with chat, calls, screen sharing, chess, media features and a visual Developer Studio.
