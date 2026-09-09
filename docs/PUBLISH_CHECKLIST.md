# Checklist перед переводом репозитория в Public

- [ ] Репозиторий сначала создан как **Private**.
- [ ] Запущен `python scripts/prepublish_check.py .`.
- [ ] Нет `chat_users.db`, `.sqlite`, `.db`.
- [ ] Нет API keys / tokens / passwords.
- [ ] Нет `.env`.
- [ ] Нет `web_profile`, cookies, sessions.
- [ ] Нет backups `*.bak*`.
- [ ] Нет production `updates/`.
- [ ] Нет локальных `N:\...`, `C:\Users\...` в публичных dev scripts.
- [ ] Hardcoded server IP заменён на `127.0.0.1` / env/config.
- [ ] В README нет персональных секретов.
- [ ] Проверены права на изображения/аудио.
- [ ] Мемные/чужие MP3 не добавлены без разрешения.
- [ ] `python -m compileall -q .` проходит.
- [ ] Клиент запускается.
- [ ] Сервер запускается.
- [ ] Есть хотя бы один screenshot без приватных данных.
- [ ] Выбрано, нужна ли open-source лицензия.
