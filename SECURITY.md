# Security

## Не публикуй приватные данные

До каждого `git push` в публичный репозиторий проверь, что отсутствуют:

- API keys, access tokens, passwords;
- рабочие IP/домены, если ты не хочешь их публиковать;
- `chat_users.db`;
- рабочие SQLite-файлы;
- `web_profile`, cookies и browser sessions;
- backups (`*.bak*`);
- updater leftovers (`*.new`, `*.download`);
- Developer Studio scripts с локальными путями;
- логи и crash dumps.

Запуск локальной проверки:

```powershell
python scripts\prepublish_check.py .
```

## Если секрет уже попал в Git

Простого удаления файла новым commit недостаточно: значение остаётся в истории Git.

1. Немедленно отозвать / перевыпустить ключ.
2. Удалить секрет из текущих файлов.
3. Очистить историю Git специальным инструментом (`git filter-repo` или BFG).
4. Force-push очищенную историю только после понимания последствий.

Не открывай issue с настоящими ключами, токенами, БД или приватными логами.
