# Contributing

Проект пока находится в Alpha.

## Перед изменениями

1. Создай отдельную ветку.
2. Проверь запуск `server.py` и `client_qt.py`.
3. Для сетевой функции проверь оба клиента.
4. Не добавляй runtime-БД, ключи и backups.
5. Запусти:

```powershell
python -m compileall -q .
python scripts\prepublish_check.py .
```

## Commit style

Примеры:

```text
feat(chess): add random check sounds
fix(call): restore compatible voice packets
feat(builder): add local developer actions
docs: update architecture guide
```
