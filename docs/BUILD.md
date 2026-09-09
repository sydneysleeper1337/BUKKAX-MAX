# Запуск и сборка

## Python

Рекомендуется Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Опциональные модули:

```powershell
pip install -r requirements-optional.txt
```

PyInstaller:

```powershell
pip install -r requirements-dev.txt
```

## Запуск сервера

```powershell
python server.py
```

## Запуск клиента

Локально:

```powershell
$env:BUKKAX_SERVER_IP="127.0.0.1"
python client_qt.py
```

## EXE

```powershell
.\scripts\build_client.ps1
.\scripts\build_server.ps1
```

Скрипт клиента автоматически добавляет известные hidden-import и asset folders только если они реально существуют.

## Auto-update

Runtime update files не должны храниться в GitHub source repo.

Production server:

```text
server.exe
chat_users.db
updates/
├── version.txt
└── Bukkax.exe
```

`updates/` находится в `.gitignore`.
