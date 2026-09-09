# Первый push на GitHub

## 1. Подготовь чистую копию из ТЕКУЩЕЙ папки BUKKAX

Скопируй папку `BUKKAX_GITHUB_READY_TEMPLATE` внутрь/рядом с проектом или запусти:

```powershell
python prepare_github_repo.py --source "N:\bukaka2" --destination "N:\BUKKAX_GITHUB_READY"
```

По умолчанию аудио не копируется.

## 2. Проверка

```powershell
cd N:\BUKKAX_GITHUB_READY
python scripts\prepublish_check.py .
python -m compileall -q .
```

Не продолжай, если scanner показывает `ERRORS`.

## 3. Создай Private repository на GitHub

Например:

```text
bukkax
```

Не добавляй GitHub README/.gitignore автоматически, потому что они уже есть.

## 4. Git

```powershell
git init
git branch -M main
git add .
git status
git commit -m "Initial BUKKAX GitHub release"
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

## 5. Только после проверки сделай Public

Перед переключением:

- открой GitHub → Code и вручную просмотри файлы;
- поищи `API_KEY`, `TOKEN`, `PASSWORD`, `SERVER_IP`;
- убедись, что нет `.db`;
- убедись, что нет личных логов/backup;
- проверь лицензии аудио/изображений.
