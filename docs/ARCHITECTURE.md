# Архитектура BUKKAX

## 1. Главные компоненты

### `client_qt.py`
Основное desktop-приложение на PySide6. Отвечает за:

- подключение и авторизацию;
- общий чат / ЛС;
- отображение пользователей и профилей;
- отправку файлов;
- управление звонками;
- UDP audio/video sockets;
- updater;
- вызов дополнительных модулей.

### `server.py`
Центральный сервер:

- принимает TCP клиентов;
- хранит/читает SQLite;
- маршрутизирует сообщения;
- управляет online-состоянием;
- пересылает call signaling;
- relays UDP voice/video;
- отдаёт update-файлы через HTTP;
- хранит опубликованный Builder config.

### `protocol.py`
Минимальный framing поверх TCP:

```text
[4 bytes header length][JSON header][optional payload]
```

Если `header["size"] > 0`, `recv_frame()` читает ровно указанное количество payload bytes.

## 2. Порты

| Порт | Протокол | Назначение |
|---|---|---|
| 55555 | TCP | основной protocol / chat / signaling / payload |
| 55556 | HTTP/TCP | auto-update |
| 55557 | UDP | voice |
| 55558 | UDP | camera/video |

Порты могут отличаться, если ты изменишь локальную сборку.

## 3. Дополнительные модули

### `bukkax_chess_qt.py`
Шахматный движок и PySide6 UI:

- legal moves;
- check / mate;
- board orientation;
- bot;
- history / openings;
- sounds / check effects.

### `bukkax_dev_builder.py`
Developer Studio / visual Builder:

- runtime widgets;
- local developer actions;
- layout/design config.

### `bukkax_builder_sync.py`
Синхронизация публичной части Builder через server.

### `bukkax_screen_share.py`
Захват экрана / окна и отображение screen share.

### `bukkax_call_quality.py`
Дополнительная обработка / буферизация голоса.

### `music_player.py`
Отдельное музыкальное окно на QtWebEngine.

## 4. Поток обычного сообщения

```text
QLineEdit
   │
   ▼
client_qt.send_message()
   │
   ▼
protocol.send_frame()
   │ TCP
   ▼
server.py
   │
   ├─ сохранить / проверить
   │
   └─ send_frame()
          │
          ▼
     other clients
          │
          ▼
 NetworkWorker
          │ Signal
          ▼
 MainWindow._handle_frame()
```

## 5. Звонок

```text
Client A ── TCP call signaling ──► Server ──► Client B

Client A ── UDP voice/video ─────► media relay ─────► Client B
Client B ── UDP voice/video ─────► media relay ─────► Client A
```

GUI нельзя обновлять напрямую из worker thread. Сетевые данные должны возвращаться в GUI thread через Qt signal / queued connection.

## 6. Screen Share

Текущая архитектура может отличаться между версиями. В последних патчах screen-share frame data передавались надёжным TCP path, а voice/camera оставались на UDP.

## 7. Builder security boundary

Публичные widgets могут синхронизироваться через server.

Локальные developer actions (произвольный Python, EXE, локальные файлы) должны оставаться только у разработчика и не рассылаться другим клиентам.
