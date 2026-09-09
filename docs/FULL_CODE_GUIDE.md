# BUKKAX — полный гайд по коду и архитектуре

Версия гайда: 1.0 · 08.09.2026

Основа: рабочий снимок, собранный из файлов проекта и цепочки актуальных патчей, доступных в этой переписке. Номера строк в приложениях относятся к этому снимку и могут отличаться от твоей локальной папки после ручных правок.

Важно: в старых архивных копиях server.py/client_qt.py встречаются legacy-блоки ИИ/API. В текущем локальном BUKKAX они удалены; этот гайд не считает их частью действующей архитектуры и не рекомендует возвращать их из старых backup-файлов.

## 1. Архитектура в одном рисунке

```text
Bukkax.exe / client_qt.py
        │
        ├── TCP 55555 ───────────────► server.py / server.exe
        │      JSON + payload              │
        │                                  ├── SQLite chat_users.db
        │                                  ├── Builder config JSON
        │                                  └── маршрутизация сообщений
        │
        ├── UDP 55557 (голос PCM) ───► voice relay ───► другой клиент
        ├── UDP 55558 (камера JPEG) ─► video relay ───► другой клиент
        │
        └── HTTP 55556 ──────────────► updates/version.txt + updates/Bukkax.exe

Внутри клиента:
client_qt.py
 ├── protocol.py
 ├── bukkax_chess_qt.py
 ├── bukkax_dev_builder.py
 ├── bukkax_builder_sync.py
 ├── bukkax_screen_share.py
 ├── bukkax_call_quality.py
 └── music_player.py
```

## 2. Главные файлы проекта

| Файл | Строк в снимке | Роль |

| --- | --- | --- |

| client_qt.py | 4278 | Главный GUI-клиент: интерфейс, чаты, звонки, файлы, профили, обновление, интеграция модулей. |

| server.py | 2423 | Сетевой сервер: TCP-чат, SQLite, UDP-релеи, обновления, звонки, Builder Sync, шахматы. |

| protocol.py | 44 | Общий фрейминг TCP-сообщений: JSON-заголовок + бинарный payload. |

| bukkax_chess_qt.py | 4008 | Шахматный движок и интерфейс: правила, бот, история, дебюты, звуки, координаты. |

| bukkax_dev_builder.py | 1579 | Developer Studio V2: визуальный конструктор, локальные Python/EXE-действия, дизайн. |

| bukkax_builder_sync.py | 186 | Синхронизация публичной части Developer Studio через сервер. |

| bukkax_screen_share.py | 1492 | Демонстрация экрана/окна, 720p/1080p, просмотр, GUI-thread bridge. |

| bukkax_call_quality.py | 428 | Безопасная стабилизация 1-to-1 голоса: 10-мс PCM-пакеты и jitter buffer. |

| music_player.py | 380 | Встроенный браузер музыки/видео на QtWebEngine с историей SQLite. |



### Рекомендуемая структура папки клиента

```text
BUKKAX/
├── Bukkax.exe                 # после сборки
├── version.txt                # локальная версия
├── nickname.txt               # сохранённый ник
├── device_id.txt              # идентификатор устройства
├── bukkax_builder_config.json # локальный Developer Studio config
├── bukkax_chess_assets/       # PNG фигур
├── bukkax_chess_sounds/       # звуки ходов/шаха
└── sounds/                    # ringtone/уведомления
```

### Рекомендуемая структура сервера

```text
BUKKAX_SERVER/
├── server.exe
├── chat_users.db
├── version.txt
├── builder_config_server.json
└── updates/
    ├── version.txt
    └── Bukkax.exe
```

## 3. Порты и транспорт

| Порт | Протокол | Назначение | Что идёт внутри |

| --- | --- | --- | --- |

| 55555 | TCP | Основной сервер | чат, файлы, профили, шахматы, signaling звонков, Builder Sync, Screen Share JPEG |

| 55556 | HTTP/TCP | Автообновление | version.txt и Bukkax.exe |

| 55557 | UDP | Голос | сырой PCM mono Int16 48 kHz с 17-байтовым call prefix |

| 55558 | UDP | Камера | JPEG-кадры камеры; старые compatibility-хуки screen share остаются, но V2 screen share отправляет кадры по TCP |



Критично: порт 55555 отвечает за надёжные команды. UDP выбран для живого аудио/видео, потому что задержка важнее повторной доставки. Демонстрация экрана V2 перенесена на TCP, чтобы не терять большие кадры.

## 4. protocol.py — общий язык клиента и сервера

protocol.py маленький, но это один из самых важных файлов. И клиент, и сервер импортируют send_frame/recv_frame.

```text
[4 байта: длина JSON header, uint32 big-endian]
[JSON header UTF-8]
[payload ровно header["size"] байт, если size > 0]
```

recv_exact(sock, n) решает типичную проблему TCP: один recv() не обязан вернуть все запрошенные байты. send_frame() сначала отправляет длину заголовка, потом сам JSON, потом payload. recv_frame() делает обратную операцию.

Пример обычного сообщения:

```python
send_frame(sock, {'type': 'dm', 'target': 'Friend', 'text': 'Привет'})
```

Пример сообщения с картинкой:

```python
send_frame(sock, {'type': 'avatar_set', 'size': len(data)}, data)
```

Отдельно от framed protocol существует стартовый nickname-handshake: сервер сначала отправляет сырой текст NICK, клиент отвечает JSON с nickname/device_id, затем сервер отвечает NICK_OK/NICK_TAKEN/NICK_INVALID/NICK_BANNED. Только после NICK_OK начинается protocol.py.

## 5. server.py — сердце BUKKAX

ChatServer держит TCP-сокет, список online-клиентов, SQLite, pending/active calls и UDP relay. После запуска конструктор открывает 55555, инициализирует БД и поднимает UDP 55557/55558. Затем start_update_server() поднимает HTTP 55556, а receive() принимает клиентов.

### 5.1. Основное состояние ChatServer

| Поле | Назначение |

| --- | --- |

| clients / nicknames | Параллельные списки TCP-сокетов и ников. |

| pending_calls | Звонки, где получатель ещё не ответил. |

| active_calls | Активные 1-to-1 звонки и найденные UDP endpoint-адреса. |

| active_group_calls | Групповые звонки и member_id → nick/UDP address. |

| calls_lock | Защита состояния звонков между потоками. |

| db / db_lock | SQLite connection check_same_thread=False + lock. |



### 5.2. SQLite: что хранится на сервере

| Таблица | Ключевые поля | Назначение |

| --- | --- | --- |

| users | nickname, device_id, last_ip, first_seen, last_seen | Привязка ника к устройству и история входов. |

| messages | room, sender, msg_type, text, filename, timestamp | История сообщений комнат. |

| friends | owner_nick, friend_nick | Списки друзей. |

| dms | sender, recipient, text, timestamp, msg_type, filename | История личных сообщений и файлов. |

| avatars | nickname, image_data BLOB | Аватары пользователей. |

| rooms | name, creator, created_at | Публичные комнаты. |

| private_chats | id, name, creator, created_at | Приватные беседы. |

| private_chat_members | chat_id, nickname | Состав приватных бесед. |

| profiles | nickname, bio, status, updated_at | Профиль и статус. |

| gifts | recipient, sender, note, image_data, timestamp | Подарки пользователей. |

| news | author, text, image_data, timestamp | Лента новостей. |

| banned | nickname, device_id, banned_at, banned_by | Блокировки. |



Файлы сообщений как бинарные данные в таблицы messages/dms не сохраняются: в истории сохраняются metadata/filename, а передача самого файла происходит через payload текущего TCP frame. Аватары, подарки и изображения новостей хранятся BLOB.

### 5.3. Handshake ника

Ник привязан к device_id. Если ник новый — register_nickname(). Если уже принадлежит тому же device_id — touch_nickname() и вход разрешён. Если device_id другой — NICK_TAKEN. Бан проверяется по nickname или device_id.

### 5.4. Потоки

Каждый TCP-клиент обслуживается отдельным daemon-thread через handle_client(). Update HTTP использует ThreadingTCPServer. Voice/video relays тоже работают в отдельных daemon-thread. Поэтому всё общее состояние должно защищаться lock-ами; особенно SQLite и calls.

### 5.5. Серверные команды client → server

| type | Основные поля | Что делает сервер |

| --- | --- | --- |

| text | room, text | Текст в общей/публичной/приватной комнате. |

| file | room, filename, size + payload | Файл в комнате. |

| friend_add | target | Добавить друга. |

| friend_list_request | — | Запрос списка друзей. |

| dm | target, text | Личное сообщение. |

| dm_file | target, filename, size + payload | Файл в ЛС. |

| dm_history_request | target | История ЛС. |

| room_create | name | Создать комнату. |

| room_list_request | — | Список комнат. |

| room_history_request | room | История комнаты. |

| private_chat_create | name, members | Создать приватную беседу. |

| private_chat_list_request | — | Список приватных бесед. |

| private_chat_history_request | chat_id | История приватной беседы. |

| private_chat_invite_member | chat_id, target | Добавить участника. |

| private_chat_remove_member | chat_id, target | Удалить участника. |

| profile_set | bio, status | Сохранить профиль. |

| profile_request | target | Запрос профиля. |

| user_send_gift | target, note, size + image | Отправить подарок; сервер валидирует картинку и лимит. |

| gift_image_request | gift_id | Получить изображение подарка. |

| news_list_request | — | Запрос новостей. |

| news_image_request | news_id | Получить картинку новости. |

| admin_user_list_request | — | Админ: список пользователей. |

| admin_send_gift | target, note, image | Админ: подарок. |

| admin_kick | target | Админ: кик/бан в текущей реализации. |

| admin_post_news | text, image | Админ: публикация новости. |

| chess_invite | target, game_id | Приглашение в шахматы. |

| chess_accept | target, game_id, accepted, white, black | Ответ на приглашение. |

| chess_move | target, game_id, src, dst, promotion | Ход. |

| chess_restart | target, game_id | Новая партия. |

| chess_resign | target, game_id | Сдаться. |

| chess_close | target, game_id | Синхронно закрыть сетевую доску. |

| builder_config_request | — | Получить опубликованный Builder-config. |

| builder_config_publish | size + JSON payload | Опубликовать безопасную публичную часть Studio. |

| screen_share_state | call_id, active, quality, fps | Сигнал старта/остановки демонстрации. |

| screen_share_frame | call_id, width, height, fps, size + JPEG | Кадр демонстрации по TCP. |

| call_offer | target, video | Начать 1-to-1 звонок. |

| call_answer | call_id, accepted | Принять/отклонить звонок. |

| call_end | call_id | Завершить звонок. |

| group_call_start | chat_id | Старт группового звонка приватной беседы. |

| group_call_join | call_id | Войти в групповой звонок. |

| group_call_leave | call_id | Выйти из группового звонка. |

| avatar_set | size + image | Сохранить аватар. |

| avatar_request | target | Получить аватар. |



Legacy note: ветка call_quality_capability может остаться в server.py от старой версии медиа-патча, но текущий bukkax_call_quality.py V2 SAFE не использует новый wire-protocol/capability negotiation; голос снова совместим со старым PCM-форматом.

### 5.6. Голос и камера на сервере

UDP relay не декодирует аудио/видео. Он читает первые 17 байт datagram: 16 ASCII-байт call_id + 1 байт роли/member_id, запоминает фактический UDP address отправителя и пересылает datagram другому участнику. Это простой relay, а не медиасервер с кодеками.

```text
1-to-1 packet:
[call_id: 16 ASCII bytes][role: 1 byte, b"0"/b"1"][media bytes]

group packet:
[call_id: 16 ASCII bytes][member_id: 1 byte][media bytes]
```

### 5.7. Автообновление

UpdateRequestHandler разрешает version.txt и canonical Bukkax.exe. Для перехода со старых клиентов сервер понимает legacy-запрос старого имени и отдаёт тот же Bukkax.exe. Клиент сравнивает версии как tuple(int).

```text
updates/
├── version.txt     # например 1.0.8
└── Bukkax.exe      # новая сборка
```

### 5.8. Developer Studio Sync на сервере

Сервер хранит builder_config_server.json и перед сохранением санитизирует JSON: ограничивает число widgets, типы, размеры, цвета, visibility и список разрешённых action. Python-код, EXE paths и visibility=me не являются публичным форматом и на сервер не должны попадать.

## 6. client_qt.py — главный клиент

MainWindow — самый крупный класс проекта. Он объединяет GUI, network worker, чаты, медиа, обновление, профили и точки интеграции модулей.

### 6.1. Запуск клиента

```text
QApplication
  ↓
MainWindow.__init__
  ├─ создаёт локальное состояние
  ├─ создаёт UDP sockets на случайных локальных портах
  ├─ строит UI
  └─ QTimer.singleShot(300, connect_to_server)
  ↓
connect_to_server → nickname handshake → NetworkWorker(QThread)
```

NetworkWorker блокирующе вызывает recv_frame(sock) в отдельном QThread и эмитит frame_received(dict, bytes). GUI-обновления должны возвращаться в main Qt thread. Именно поэтому Screen Share использует QObject bridge + QueuedConnection.

### 6.2. Основные части интерфейса

Интерфейс строится в _build_ui(): боковые списки комнат/ЛС/друзей, центральный QTextBrowser, строка ввода, верхняя панель функций, кнопки файлов/эмодзи/голоса, профиль/новости/шахматы и dev-кнопка. Developer Studio может добавлять свои widgets в topbar или свободно поверх centralWidget.

### 6.3. Чаты и история

current_view хранит тип текущего экрана и target. Для истории есть отдельные словари room_texts/dm_texts. _render_current_view() берёт соответствующий HTML и устанавливает его в chat_view. Входящие frames разбираются в _handle_frame(), затем вызываются специализированные методы.

send_message() понимает текущий view: room/private room → type=text, DM → type=dm. Есть команды управления приватной беседой, вставка файлов/картинок через clipboard, отправка URL-картинки, emoji picker и rich HTML-отрисовка media.

### 6.4. Файлы и медиа

_send_file_from_path() читает файл и передаёт payload. Полученные файлы сохраняются локально. Изображения отображаются inline, видео/аудио открываются в собственных диалогах QMediaPlayer. Video-message recorder использует Qt Multimedia.

### 6.5. Профиль, аватар, подарки, новости

ProfileDialog показывает bio/status/joined/last_seen и подарки. Аватар отправляется server-side через avatar_set и кешируется локально. Обычный пользователь может отправить подарок-картинку (сервер ограничивает размер до 10 MiB и проверяет Pillow). NewsFeedDialog показывает новости; публиковать их может админ.

### 6.6. Админка

ADMIN_NICKNAME определяет наличие админ-функций в клиенте; server.py дополнительно проверяет ADMIN_NICKNAMES для защищённых команд. Это важно: скрытая кнопка в UI не является защитой сама по себе — серверная проверка обязательна.

### 6.7. Голос 1-to-1

Базовый формат аудио: 48 kHz, mono, Int16. QAudioSource читает микрофон, QAudioSink пишет в динамик. mic_gain/speaker_gain применяются программно. pyrnnoise + numpy — опциональный шумодав.

Текущий bukkax_call_quality.py V2 SAFE перехватывает _on_mic_data/_on_call_udp_data только для 1-to-1: дробит PCM на 10-мс chunks, сохраняет старый wire-format и использует небольшой receive jitter-buffer. PREBUFFER около 70 ms, max buffer около 350 ms, target около 100 ms. Групповые звонки оставлены на старой логике.

### 6.8. Камера и видео

QCamera → QVideoSink. Камерный кадр уменьшается и JPEG-кодируется; UDP 55558 передаёт его через relay. CallStatusDialog умеет показывать локальный и удалённый кадр и менять размеры video labels.

### 6.9. Групповые звонки

Групповой звонок привязан к private chat. Сервер выдаёт каждому member_id; audio/video UDP relay использует этот byte для маршрутизации. На клиенте GroupCallDialog строит tiles участников и хранит отдельные audio buffers.

### 6.10. Ringtone

Входящий/исходящий звонок использует persistent QMediaPlayer/QAudioOutput. Основной файл: sounds/ringtone.wav. Плеер останавливается при accept/decline/call_started/cleanup.

### 6.11. Автообновление клиента

UpdateCheckWorker проверяет HTTP version.txt. UpdateDownloadWorker скачивает Bukkax.exe рядом с текущим exe как .download/.new. После завершения клиент создаёт _bukkax_update.bat, закрывает себя, batch-файл заменяет executable и version.txt, затем запускает новую версию. Python у конечного пользователя для updater не нужен.

## 7. bukkax_chess_qt.py — шахматы

### 7.1. ChessRules

ChessRules хранит board 8×8, turn, castling flags и result. Цвет 0 = белые, 1 = чёрные. Основные методы: legal_moves(), is_check(), checkmate_status(), move(). move() проверяет легальность, выполняет рокировку/превращение и переключает turn.

### 7.2. ChessDialog

ChessDialog — сетевое окно. При игре чёрными display ↔ board координаты разворачиваются, поэтому фигуры всегда смотрятся с точки зрения игрока. Снизу/слева подписываются a-h/1-8. Всплывающие tooltips координат можно оставлять отключёнными.

### 7.3. Цвета PvP

Цвета назначает сервер в chess_invite: список [sender_nick, target] перемешивается random.shuffle(), затем white_nick/black_nick передаются обоим клиентам. Поэтому инициатор приглашения не должен автоматически быть белым. Если всегда белый — обычно запущен старый server.exe.

### 7.4. Бот

ChessBotDialog — локальная партия. Цвет игрока случайный. Бот перебирает легальные ходы, оценивает взятия/продвижение пешек/развитие и добавляет небольшой random, поэтому не играет абсолютно одинаково.

### 7.5. История и дебюты

Патчи добавляют панель истории, SAN/упрощённую нотацию и распознавание набора популярных дебютных последовательностей. Это эвристический справочник, не полноценная шахматная база.

### 7.6. Звуки

Ход имеет отдельный move sound. Шах подсвечивает короля красным и запускает случайный файл из bukkax_chess_sounds/check_random/. Текущий Random Check V4 не повторяет один и тот же файл два шаха подряд и останавливает предыдущий длинный check-sound перед новым.

## 8. Developer Studio V2 — визуальный конструктор

bukkax_dev_builder.py хранит локальный config bukkax_builder_config.json и умеет создавать runtime widgets. Основная идея: UI-конфиг — данные; встроенные действия — код уже внутри Bukkax; произвольный Python/EXE — только локально у разработчика.

### 8.1. Типы widgets

| type | Что создаётся |

| --- | --- |

| button | QPushButton |

| input | QLineEdit |

| label | QLabel |

| image | QLabel с QPixmap |



### 8.2. Placement и дизайн

placement=topbar вставляет widget в dev_top_bar. placement=floating создаёт child центрального окна и задаёт geometry x/y/w/h. StudioCanvas использует QGraphicsScene: item можно таскать и resize-ить за правый нижний угол. Свойства: radius, font_size, bold, bg/text/border colors, icon_data, icon_size.

### 8.3. Видимость

| visibility | Смысл |

| --- | --- |

| all | Виден всем клиентам после публикации. |

| admin | Виден только админу; можно публиковать. |

| me | Только локальному разработчику; не публикуется. |



### 8.4. Действия

Публичные built-in actions: музыка, шахматы, профиль, новости, звук, фон, админка, подарки, открыть ЛС/профиль, звонок/видеозвонок, заполнить/отправить текст, сообщение, URL, очистить widget.

Локальные actions: python_code, python_file, run_program, open_file, open_folder. Если выбран локальный action, Studio автоматически принудительно ставит visibility=me. public_config() удаляет code/path/action_args и вообще пропускает local-only элементы.

### 8.5. Python code editor

Код выполняется через exec(compile(...)) только локально. В environment доступны main_window/window, argument, QMessageBox, os, sys, subprocess. Это мощный режим разработчика: ошибка в коде может сломать текущую сессию клиента, поэтому сначала тестировать на dev-кнопке и держать backup config.

## 9. bukkax_builder_sync.py — синхронизация Studio

Модуль monkey-patch-ит MainWindow перед созданием окна. После connect_to_server запрашивает builder config. При публикации вызывает public_config(), сериализует JSON и отправляет builder_config_publish. При получении server config вызывает merge_public_into_local(): публичная часть заменяется, но visibility=me/Python/EXE widgets разработчика сохраняются локально.

Онлайн пользователи получают builder_config_updated сразу; офлайн клиент получит builder_config_data после следующего подключения.

## 10. bukkax_screen_share.py — демонстрация экрана

Поддерживает весь экран или видимое окно приложения Windows. Окна перечисляются через ctypes/Win32, без pywin32. QScreen.grabWindow() получает изображение. Некоторые GPU/protected/minimized окна могут давать чёрный кадр — тогда лучше выбрать весь монитор.

### 10.1. Качество

| Профиль | Разрешение | JPEG quality | Рекомендуемый FPS |

| --- | --- | --- | --- |

| 720p | 1280×720 | ≈50 | 5, затем 8 если канал хороший |

| 1080p | 1920×1080 | ≈42 | 3–5 |



### 10.2. Текущий транспорт V2

Фактический sender V2 кодирует JPEG, старается держать 720p frame до ~400 KiB, 1080p до ~700 KiB и жёстко отбрасывает >1 MiB. Затем отправляет type=screen_share_frame через обычный TCP send_frame() на порт 55555. Сервер проверяет call_id/участника и пересылает payload второму клиенту.

В файле всё ещё могут быть compatibility-комментарии/обработчики старого UDP BKSS-протокола. При анализе текущего поведения ориентируйся на _screen_share_tick(): он использует TCP screen_share_frame.

### 10.3. GUI thread bridge

Сетевой worker живёт в QThread. Чтобы QLabel/QPixmap не создавались из worker thread, _ScreenShareFrameBridge(QObject) использует Signal(object, object) + Qt.QueuedConnection и возвращает обработку frame в GUI thread. Это исправляет QObject different thread/access violation crash.

## 11. bukkax_call_quality.py — стабилизация голоса

Версия V2 SAFE намеренно сохраняет старый PCM wire-format, поэтому совместима со старым клиентом. Она не использует custom magic/FEC/capability handshake. Для 1-to-1 микрофонный поток буферизуется и режется на ~10 ms PCM chunks, а receive-side кладёт данные в bytearray и проигрывает по таймеру.

Плюс: меньше риск IP fragmentation и меньше рваного звука при джиттере. Минус: это всё ещё raw PCM без Opus/PLC/WebRTC. На международной связи bandwidth и packet loss могут оставаться проблемой. Следующий серьёзный уровень — Opus + adaptive jitter + proper RTP/WebRTC.

## 12. music_player.py — музыка/видео

Отдельное окно на QtWebEngine. Может открывать VK/YouTube/URL внутри BUKKAX, хранит browser profile в web_profile/ и историю в bukkax_music.db. MusicDatabase имеет add/update_title/items/clear. MainWindow музыки строит toolbar, web view, history list и shortcuts.

Это браузерный модуль, а не downloader: он не извлекает медиапотоки и не скачивает контент.

## 13. Ресурсы и файлы состояния

| Файл/папка | Где | Для чего |

| --- | --- | --- |

| chat_users.db | сервер | Основная SQLite БД. |

| builder_config_server.json | сервер | Последний опубликованный публичный Studio config. |

| updates/version.txt | сервер | Версия, предлагаемая клиентам. |

| updates/Bukkax.exe | сервер | Новая клиентская сборка. |

| version.txt | клиент/сервер | Локальная версия процесса. |

| device_id.txt | клиент | Стабильный ID устройства. |

| nickname.txt | клиент | Последний ник. |

| bukkax_builder_config.json | клиент разработчика | Локальный UI + local dev widgets/code. |

| bukkax_chess_assets/ | клиент resource | PNG-фигуры. |

| bukkax_chess_sounds/ | клиент resource | move/check/random sounds. |

| sounds/ | клиент resource | ringtone/notification sounds. |

| web_profile/ | клиент | Cookies/storage QtWebEngine. |

| bukkax_music.db | клиент | История music browser. |



## 14. Сборка EXE

### 14.1. Клиент

```powershell
pyinstaller --clean --onefile --noconsole --name Bukkax client_qt.py --add-data "bukkax_chess_assets;bukkax_chess_assets" --add-data "sounds;sounds" --add-data "bukkax_chess_sounds;bukkax_chess_sounds" --add-data "bukkax_builder_config.json;." --hidden-import bukkax_dev_builder --hidden-import bukkax_builder_sync --hidden-import bukkax_screen_share --hidden-import bukkax_call_quality --hidden-import music_player --noupx --noconfirm
```

Результат: dist\Bukkax.exe. Для друга обычно достаточно отправить этот onefile exe. Локальные runtime-файлы вроде nickname.txt/device_id.txt создаются рядом с exe.

### 14.2. Сервер

```powershell
pyinstaller --clean --onefile --console --name server server.py --noupx --noconfirm
```

Результат: dist\server.exe. --console желательно оставить, чтобы видеть подключения и ошибки.

### 14.3. После серверной правки

Если менялся server.py — обязательно пересобрать/перезапустить server.exe. Если менялся только client module — пересобрать Bukkax.exe. Если менялась публичная Builder-конфигурация без нового action-кода — достаточно публикации config, когда у всех уже есть Studio V2.

## 15. Как правильно добавлять новую функцию

### Вариант A: только локальный UI

```text
1. Добавить метод MainWindow или отдельный модуль.
2. Создать кнопку / Developer Studio action.
3. Проверить python client_qt.py.
4. Пересобрать только Bukkax.exe.
```

### Вариант B: серверная функция

```text
1. Придумать уникальный type, например mood_set.
2. client: send_frame(...).
3. server.handle_client: elif msg_type == 'mood_set'.
4. Если нужно хранение — таблица/миграция SQLite.
5. server: send_frame ответа mood_saved/mood_data.
6. client._handle_frame: обработать ответ.
7. Сначала python server.py + python client_qt.py.
8. Потом пересобрать ОБА exe.
```

### Вариант C: новый Developer Studio public action

```text
1. Реализовать action в bukkax_dev_builder.execute_action().
2. Добавить action ID в BUILTIN_ACTIONS.
3. Добавить тот же ID в server allowed_actions sanitizer.
4. Выпустить новый Bukkax.exe всем пользователям.
5. После этого кнопки с этим action можно публиковать только конфигом.
```

Не отправляй Python-код как публичный action. Для этого в Studio специально разделены built-in public actions и local-only code/program actions.

## 16. Отладка: куда смотреть по симптомам

| Симптом | Где искать | Первый тест |

| --- | --- | --- |

| Клиент мгновенно закрывается | client_qt.py, monkey-patch modules, Qt thread | python -X faulthandler -u client_qt.py |

| Server пишет WinError 10054 | Чаще клиент упал/закрыл TCP | Сначала смотреть traceback клиента. |

| Обновление 404 | updates/Bukkax.exe, version.txt, server.exe | Открыть http://SERVER:55556/version.txt и проверить имя. |

| Нет звука | UDP 55557, audio devices, bukkax_call_quality.py | Проверить старый PCM path, выключить шумодав, gains ≈1.0. |

| Звук рваный далеко | packet loss/jitter/raw PCM | Проверить ping/packet loss; текущий jitter buffer только смягчает. |

| Камера не видна | UDP 55558, video hello, QCamera | Проверить firewall и выбранную камеру. |

| Screen Share “ожидание изображения” | screen_share_frame TCP/quality | Начать с 720p/5 FPS, проверить новый server.exe. |

| Qt different thread / access violation | GUI вызван из NetworkWorker | Проверить ScreenShareFrameBridge/QueuedConnection. |

| Шахматы всегда одним цветом | старый server.exe | Проверить random.shuffle в chess_invite и пересобрать server. |

| Новая Studio кнопка не видна другу | public config или старый client | Проверить visibility, publish, client V2. |



## 17. Безопасность и технический долг

Текущий BUKKAX — хороший учебный/частный мессенджер, но не production-secure messenger. TCP/UDP не шифруются TLS/E2EE; server trust высокий; device_id — не криптографическая аутентификация. Не использовать для секретных данных без отдельного security-layer.

Большая часть новых функций подключена monkey-patch-ами. Это удобно для быстрых патчей, но со временем усложняет порядок обёрток. Для следующего крупного рефакторинга полезно вынести ChatService/CallService/ProfileService/UpdateService в отдельные классы, а server.handle_client заменить registry обработчиков type → function.

server.py тоже стоит разделить на storage.py, handlers/, media_relay.py, updater.py. Для protocol.py добавить max header/max payload, schema/version и graceful invalid-frame errors.

## 18. Карта server.py: методы ChatServer

| Строка снимка | Метод | Группа |

| --- | --- | --- |

| 425 | __init__ | БД |

| 451 | _init_db | БД |

| 572 | get_nickname_owner | БД |

| 578 | nickname_exists | БД |

| 583 | register_nickname | БД |

| 593 | touch_nickname | БД |

| 602 | is_banned | БД |

| 611 | ban_user | БД |

| 645 | save_message | БД |

| 655 | get_history | БД |

| 669 | try_add_friend | БД |

| 695 | get_friends | БД |

| 701 | save_dm | БД |

| 713 | get_dm_history | БД |

| 728 | try_create_room | БД |

| 750 | get_rooms | БД |

| 756 | try_create_private_chat | БД |

| 786 | get_private_chats_for | БД |

| 797 | get_private_chat_members | БД |

| 805 | is_private_chat_member | БД |

| 815 | is_private_chat_owner | БД |

| 823 | get_private_chat_name | БД |

| 829 | notify_private_chat_members_changed | БД |

| 839 | private_chat_add_member | БД |

| 880 | private_chat_remove_member | БД |

| 917 | set_profile | БД |

| 930 | set_profile_bio | БД |

| 942 | get_profile | БД |

| 960 | add_gift | БД |

| 972 | get_gifts | БД |

| 982 | get_gift_image | БД |

| 988 | add_news | БД |

| 1000 | get_news | БД |

| 1014 | get_news_image | БД |

| 1020 | get_all_users_with_status | БД |

| 1031 | save_avatar | БД |

| 1040 | get_avatar | БД |

| 1046 | get_local_ip | Media/online |

| 1057 | start_voice_relay | Media/online |

| 1060 | start_video_relay | Media/online |

| 1063 | _start_media_relay | Media/online |

| 1071 | _media_relay_loop | Media/online |

| 1109 | end_calls_for | Media/online |

| 1156 | broadcast_frame | Media/online |

| 1165 | broadcast_system | Media/online |

| 1169 | get_client_by_nick | Media/online |

| 1175 | broadcast_to_private_chat | Media/online |

| 1184 | remove_client | Media/online |

| 1411 | perform_handshake | Handshake/dispatch |

| 1459 | handle_client | Handshake/dispatch |

| 2374 | receive | Accept loop |



## 19. Карта client_qt.py: методы MainWindow

| Строка снимка | Метод | Группа |

| --- | --- | --- |

| 972 | __init__ | UI / gifts / builder |

| 1050 | open_my_feature | UI / gifts / builder |

| 1055 | _build_ui | UI / gifts / builder |

| 1276 | send_user_gift | UI / gifts / builder |

| 1362 | _handle_user_gift_result | UI / gifts / builder |

| 1395 | open_developer_builder | UI / gifts / builder |

| 1436 | _reload_developer_widgets | UI / gifts / builder |

| 1452 | _friends_context_menu | Network / chats / files |

| 1465 | _style_chat_view | Network / chats / files |

| 1471 | resizeEvent | Network / chats / files |

| 1478 | open_background_menu | Network / chats / files |

| 1485 | choose_bg_color | Network / chats / files |

| 1493 | choose_bg_photo | Network / chats / files |

| 1506 | reset_background | Network / chats / files |

| 1513 | connect_to_server | Network / chats / files |

| 1560 | _nickname_handshake | Network / chats / files |

| 1578 | _attempt_nickname | Network / chats / files |

| 1589 | _handle_frame | Network / chats / files |

| 1792 | _on_room_clicked | Network / chats / files |

| 1798 | _on_private_chat_clicked | Network / chats / files |

| 1805 | _on_dm_clicked | Network / chats / files |

| 1812 | _on_friend_clicked | Network / chats / files |

| 1819 | show_room | Network / chats / files |

| 1832 | show_private_chat | Network / chats / files |

| 1847 | open_dm | Network / chats / files |

| 1861 | _add_dm_to_list | Network / chats / files |

| 1866 | _current_room_key | Network / chats / files |

| 1874 | _render_current_view | Network / chats / files |

| 1887 | _safe_avatar_nick | Network / chats / files |

| 1891 | _avatar_cache_path | Network / chats / files |

| 1896 | _set_profile_avatar_if_open | Network / chats / files |

| 1904 | _append_html | Network / chats / files |

| 1914 | _avatar_img_tag | Network / chats / files |

| 1928 | _message_html | Network / chats / files |

| 1942 | _media_html | Network / chats / files |

| 1971 | _get_circular_thumbnail | Network / chats / files |

| 2023 | _handle_anchor_click | Network / chats / files |

| 2037 | _chat_context_menu | Network / chats / files |

| 2063 | _copy_image_to_clipboard | Network / chats / files |

| 2071 | add_room_dialog | Network / chats / files |

| 2080 | request_room_list | Network / chats / files |

| 2086 | _update_rooms_list | Network / chats / files |

| 2093 | _handle_room_create_result | Network / chats / files |

| 2108 | add_private_chat_dialog | Network / chats / files |

| 2124 | request_private_chat_list | Network / chats / files |

| 2130 | _update_private_chats_list | Network / chats / files |

| 2138 | _handle_private_chat_create_result | Network / chats / files |

| 2153 | _handle_private_chat_invited | Network / chats / files |

| 2163 | _load_private_chat_history | Network / chats / files |

| 2183 | _load_history | Network / chats / files |

| 2203 | _load_room_history | Network / chats / files |

| 2224 | _load_dm_history | Network / chats / files |

| 2244 | _find_local_file | Network / chats / files |

| 2250 | _cache_sent_file | Network / chats / files |

| 2261 | _on_incoming_room_text | Network / chats / files |

| 2271 | _on_incoming_file | Network / chats / files |

| 2276 | _on_incoming_dm | Network / chats / files |

| 2288 | _on_incoming_dm_file | Network / chats / files |

| 2299 | _save_received_file | Network / chats / files |

| 2313 | send_message | Chess |

| 2362 | open_chess_start_dialog | Chess |

| 2388 | start_chess_with | Chess |

| 2409 | _open_chess_dialog | Chess |

| 2433 | _send_chess_move | Chess |

| 2442 | _send_chess_restart | Chess |

| 2448 | _send_chess_resign | Chess |

| 2454 | _send_chess_close | Chess |

| 2467 | _handle_chess_invite_result | Chess |

| 2482 | _handle_chess_invite | Chess |

| 2508 | _handle_chess_accept | Chess |

| 2519 | _handle_chess_move | Chess |

| 2532 | _handle_chess_restart | Chess |

| 2541 | _handle_chess_resign | Chess |

| 2549 | _handle_chess_close | Chess |

| 2583 | open_chess_bot_dialog | Chess |

| 2622 | _ringtone_path | Calls / audio / video |

| 2627 | _start_call_ringtone | Calls / audio / video |

| 2673 | _on_ringtone_media_status | Calls / audio / video |

| 2685 | _stop_call_ringtone | Calls / audio / video |

| 2702 | start_call | Calls / audio / video |

| 2718 | _handle_incoming_call_offer | Calls / audio / video |

| 2737 | _accept_call | Calls / audio / video |

| 2751 | _decline_call | Calls / audio / video |

| 2761 | _handle_call_declined | Calls / audio / video |

| 2766 | _handle_call_result | Calls / audio / video |

| 2774 | _handle_call_started | Calls / audio / video |

| 2796 | _handle_call_ended | Calls / audio / video |

| 2802 | end_call | Calls / audio / video |

| 2810 | _cleanup_call | Calls / audio / video |

| 2823 | _setup_audio_streams | Calls / audio / video |

| 2845 | _recreate_audio_streams | Calls / audio / video |

| 2851 | _teardown_audio_streams | Calls / audio / video |

| 2868 | _apply_gain | Calls / audio / video |

| 2890 | _apply_noise_reduction | Calls / audio / video |

| 2913 | _on_mic_data | Calls / audio / video |

| 2935 | _on_call_udp_data | Calls / audio / video |

| 2952 | _mix_and_play_group_audio | Calls / audio / video |

| 2980 | _call_packet_prefix | Calls / audio / video |

| 2985 | _group_call_packet_prefix | Calls / audio / video |

| 2989 | _send_call_hello_packet | Calls / audio / video |

| 2994 | _send_group_hello_packets | Calls / audio / video |

| 3002 | _setup_video_capture | Calls / audio / video |

| 3014 | _teardown_video_capture | Calls / audio / video |

| 3024 | _send_video_hello_packet | Calls / audio / video |

| 3029 | _on_video_frame | Calls / audio / video |

| 3059 | _on_call_video_udp_data | Calls / audio / video |

| 3076 | start_or_join_group_call | Calls / audio / video |

| 3092 | _handle_group_call_invite | Calls / audio / video |

| 3109 | _handle_group_call_joined | Calls / audio / video |

| 3130 | _handle_group_call_member_joined | Calls / audio / video |

| 3138 | _handle_group_call_member_left | Calls / audio / video |

| 3146 | leave_group_call | Calls / audio / video |

| 3154 | _cleanup_group_call | Calls / audio / video |

| 3167 | _toggle_voice_recording | Voice/video messages / files |

| 3173 | _start_voice_recording | Voice/video messages / files |

| 3197 | _stop_voice_recording | Voice/video messages / files |

| 3207 | _finish_voice_message | Voice/video messages / files |

| 3221 | open_video_message_recorder | Voice/video messages / files |

| 3234 | send_file | Voice/video messages / files |

| 3239 | _send_file_from_path | Voice/video messages / files |

| 3270 | _handle_paste | Voice/video messages / files |

| 3291 | open_emoji_picker | Friends / avatar / settings |

| 3295 | _insert_emoji | Friends / avatar / settings |

| 3299 | add_friend_dialog | Friends / avatar / settings |

| 3308 | request_friend_list | Friends / avatar / settings |

| 3314 | _update_friends_list | Friends / avatar / settings |

| 3321 | _handle_friend_add_result | Friends / avatar / settings |

| 3336 | choose_avatar | Friends / avatar / settings |

| 3371 | _request_avatar | Friends / avatar / settings |

| 3379 | _store_avatar | Friends / avatar / settings |

| 3395 | open_sound_menu | Friends / avatar / settings |

| 3403 | toggle_sound | Friends / avatar / settings |

| 3406 | choose_notification_sound | Friends / avatar / settings |

| 3411 | reset_notification_sound | Friends / avatar / settings |

| 3417 | _prompt_update | Updater |

| 3427 | _download_and_apply_update | Updater |

| 3475 | _on_update_download_progress | Updater |

| 3491 | _on_update_download_failed | Updater |

| 3506 | _on_update_download_finished | Updater |

| 3515 | _run_update_bat_and_exit | Updater |

| 3595 | _play_notification_sound | Profile / news / admin / gifts |

| 3608 | open_profile | Profile / news / admin / gifts |

| 3627 | _view_gift | Profile / news / admin / gifts |

| 3634 | _save_own_bio | Profile / news / admin / gifts |

| 3641 | open_news_feed | Profile / news / admin / gifts |

| 3648 | request_news_list | Profile / news / admin / gifts |

| 3654 | _render_news_list | Profile / news / admin / gifts |

| 3668 | _post_news | Profile / news / admin / gifts |

| 3683 | open_admin_panel | Profile / news / admin / gifts |

| 3691 | _admin_refresh_users | Profile / news / admin / gifts |

| 3697 | _admin_send_gift | Profile / news / admin / gifts |

| 3720 | _admin_kick | Profile / news / admin / gifts |

| 3732 | _handle_admin_result | Profile / news / admin / gifts |

| 3744 | _handle_gift_received | Profile / news / admin / gifts |

| 3754 | _handle_gift_image_response | Profile / news / admin / gifts |

| 3765 | _show_gift_popup | Profile / news / admin / gifts |

| 3792 | open_audio_settings | Settings / lifecycle |

| 3796 | closeEvent | Settings / lifecycle |



## 20. Карта остальных модулей

### protocol.py

Общий фрейминг TCP-сообщений: JSON-заголовок + бинарный payload.

| Строка | Тип | Имя |

| --- | --- | --- |

| 5 | function | recv_exact |

| 16 | function | send_frame |

| 28 | function | recv_frame |



### bukkax_chess_qt.py

Шахматный движок и интерфейс: правила, бот, история, дебюты, звуки, координаты.

| Строка | Тип | Имя |

| --- | --- | --- |

| 36 | function | _base_dir |

| 98 | function | apply_chess_dark_style |

| 107 | function | _chess_message_box |

| 129 | function | chess_info |

| 133 | function | chess_warning |

| 137 | function | chess_critical |

| 141 | function | chess_question |

| 145 | function | chess_get_text |

| 158 | function | chess_get_item |

| 176 | class | ChessRules |

| 198 | method | ChessRules.__init__ |

| 201 | method | ChessRules.reset |

| 211 | method | ChessRules.inside |

| 214 | method | ChessRules.is_check |

| 237 | method | ChessRules.legal_moves |

| 318 | method | ChessRules.checkmate_status |

| 328 | method | ChessRules.move |

| 395 | class | ChessDialog |

| 396 | method | ChessDialog.__init__ |

| 419 | method | ChessDialog._assets_dir |

| 422 | method | ChessDialog._load_icons |

| 431 | method | ChessDialog._build_ui |

| 490 | method | ChessDialog._resize_board_cells |

| 506 | method | ChessDialog.resizeEvent |

| 513 | method | ChessDialog._resize_board_cells |

| 529 | method | ChessDialog.resizeEvent |

| 536 | method | ChessDialog._display_to_board |

| 541 | method | ChessDialog._board_to_display |

| 546 | method | ChessDialog._turn_text |

| 549 | method | ChessDialog._my_color_text |

| 552 | method | ChessDialog._update_status |

| 563 | method | ChessDialog._redraw |

| 589 | method | ChessDialog._square_clicked |

| 627 | method | ChessDialog._promotion_if_needed |

| 640 | method | ChessDialog.apply_remote_move |

| 658 | method | ChessDialog.reset_game |

| 665 | method | ChessDialog.remote_restart |

| 669 | method | ChessDialog.remote_resign |

| 675 | method | ChessDialog._restart_clicked |

| 682 | method | ChessDialog._resign_clicked |

| 703 | function | _bot_all_legal_moves |

| 739 | function | _bot_choose_move |

| 752 | class | ChessBotDialog |

| 755 | method | ChessBotDialog.__init__ |

| 789 | method | ChessBotDialog._update_status |

| 807 | method | ChessBotDialog._square_clicked |

| 849 | method | ChessBotDialog._schedule_bot_move |

| 858 | method | ChessBotDialog._bot_move |

| 902 | method | ChessBotDialog._restart_clicked |

| 914 | method | ChessBotDialog._resign_clicked |

| 919 | function | _bukkax_chess_asset_dirs_fixed |

| 952 | function | _bukkax_piece_png_path_fixed |

| 980 | function | _bukkax_assets_dir_for_dialog_fixed |

| 989 | function | _bukkax_load_icons_fixed |

| 1016 | function | _bukkax_redraw_with_asset_icons_fixed |

| 1102 | function | _bukkax_sq_name |

| 1109 | function | _bukkax_piece_ru |

| 1122 | function | _bukkax_piece_san_letter |

| 1136 | function | _bukkax_make_san |

| 1193 | function | _bukkax_detect_opening |

| 1286 | function | _bukkax_history_build_ui |

| 1431 | function | _bukkax_render_history_panel |

| 1488 | function | _bukkax_sync_history_from_rules |

| 1559 | function | _bukkax_coord |

| 1566 | function | _bukkax_piece_letter |

| 1576 | function | _bukkax_clean_notation |

| 1583 | function | _bukkax_history_ensure |

| 1590 | function | _bukkax_make_notation |

| 1627 | function | _bukkax_detect_opening |

| 1669 | function | _bukkax_record_move |

| 1697 | function | _bukkax_moves_html |

| 1736 | function | _bukkax_update_history_panel |

| 1766 | function | _bukkax_history_build_ui |

| 1890 | function | _bukkax_history_resize_board_cells |

| 1906 | function | _bukkax_history_resize_event |

| 1917 | function | _bukkax_history_redraw |

| 1932 | function | _bukkax_history_square_clicked |

| 1974 | function | _bukkax_history_apply_remote_move |

| 1999 | function | _bukkax_history_reset_game |

| 2019 | function | _bukkax_history_remote_restart |

| 2024 | function | _bukkax_history_remote_resign |

| 2031 | function | _bukkax_bot_square_clicked_with_history |

| 2077 | function | _bukkax_bot_move_with_history |

| 2181 | function | _bukkax_chess_sound_dirs |

| 2225 | function | _bukkax_chess_sound_path |

| 2233 | function | _bukkax_chess_ensure_sound_players |

| 2259 | function | _bukkax_chess_play_move_sound |

| 2278 | function | _bukkax_chess_play_check_sound |

| 2297 | function | _bukkax_chess_is_side_to_move_in_check |

| 2308 | function | _bukkax_chess_after_successful_move |

| 2324 | function | _bukkax_chess_highlight_checked_kings |

| 2352 | function | _bukkax_chess_wrap_move_method |

| 2541 | function | _bukkax_chess_position_signature_v2 |

| 2573 | function | _bukkax_chess_ensure_sound_players_v2 |

| 2648 | function | _bukkax_chess_play_move_sound_v2 |

| 2680 | function | _bukkax_chess_play_check_sound_v2 |

| 2720 | function | _bukkax_chess_after_successful_move_v2 |

| 2775 | function | _bukkax_chess_wrap_final_move_method_v2 |

| 2861 | function | _bukkax_chess_highlight_check_v2 |

| 2951 | function | _bukkax_chess_wrap_final_redraw_v2 |

| 3009 | function | _bukkax_sound_dirs_v3 |

| 3053 | function | _bukkax_sound_file_v3 |

| 3061 | function | _bukkax_init_effect_v3 |

| 3085 | function | _bukkax_prepare_sounds_v3 |

| 3136 | function | _bukkax_play_move_v3 |

| 3186 | function | _bukkax_play_check_v3 |

| 3209 | function | _bukkax_legacy_sound_noop_v3 |

| 3345 | function | _bukkax_piece_readable |

| 3365 | function | _bukkax_square_name |

| 3372 | function | _bukkax_chess_update_coord_labels |

| 3412 | function | _bukkax_chess_build_ui_with_coords |

| 3571 | function | _bukkax_chess_resize_board_cells_with_coords |

| 3606 | function | _bukkax_chess_redraw_with_coords |

| 3656 | function | _bukkax_check_sound_dirs_v4 |

| 3704 | function | _bukkax_check_sound_files_v4 |

| 3728 | function | _bukkax_prepare_random_check_player_v4 |

| 3763 | function | _bukkax_play_random_check_v4 |



### bukkax_dev_builder.py

Developer Studio V2: визуальный конструктор, локальные Python/EXE-действия, дизайн.

| Строка | Тип | Имя |

| --- | --- | --- |

| 166 | function | _app_dir |

| 172 | function | _embedded_dir |

| 176 | function | external_config_path |

| 180 | function | _config_candidates |

| 192 | function | _upgrade_item |

| 222 | function | load_config |

| 243 | function | save_config |

| 258 | function | public_config |

| 284 | function | merge_public_into_local |

| 312 | function | _widget_text |

| 323 | function | _special_value |

| 359 | function | resolve_argument |

| 374 | function | _require_argument |

| 387 | function | _open_local_path |

| 395 | function | _python_command |

| 412 | function | execute_action |

| 584 | function | _is_admin |

| 588 | function | _valid_color |

| 596 | function | _style_qss |

| 624 | function | _pixmap_from_data |

| 636 | function | _apply_common_properties |

| 660 | function | _create_runtime_widget |

| 697 | function | clear_runtime_widgets |

| 709 | function | apply_builder_config |

| 775 | class | StudioGraphicsItem |

| 778 | method | StudioGraphicsItem.__init__ |

| 798 | method | StudioGraphicsItem._handle_hit |

| 802 | method | StudioGraphicsItem.mousePressEvent |

| 810 | method | StudioGraphicsItem.mouseMoveEvent |

| 820 | method | StudioGraphicsItem.mouseReleaseEvent |

| 845 | method | StudioGraphicsItem.mouseDoubleClickEvent |

| 858 | class | StudioCanvas |

| 859 | method | StudioCanvas.__init__ |

| 869 | method | StudioCanvas.drawBackground |

| 886 | class | DeveloperBuilderDialog |

| 887 | method | DeveloperBuilderDialog.__init__ |

| 905 | method | DeveloperBuilderDialog._build_ui |

| 1216 | method | DeveloperBuilderDialog._widgets |

| 1219 | method | DeveloperBuilderDialog._valid_id |

| 1222 | method | DeveloperBuilderDialog._combo_set_data |

| 1226 | method | DeveloperBuilderDialog._unique_id |

| 1235 | method | DeveloperBuilderDialog._add_widget |

| 1257 | method | DeveloperBuilderDialog._reload_list |

| 1280 | method | DeveloperBuilderDialog._select_row |

| 1288 | method | DeveloperBuilderDialog._load_form |

| 1320 | method | DeveloperBuilderDialog._clear_form |

| 1332 | method | DeveloperBuilderDialog._save_current |

| 1398 | method | DeveloperBuilderDialog._apply_now |

| 1405 | method | DeveloperBuilderDialog._publish_now |

| 1430 | method | DeveloperBuilderDialog._refresh_action_help |

| 1441 | method | DeveloperBuilderDialog._pick_color |

| 1447 | method | DeveloperBuilderDialog._choose_icon |

| 1473 | method | DeveloperBuilderDialog._clear_icon |

| 1478 | method | DeveloperBuilderDialog._choose_action_path |

| 1487 | method | DeveloperBuilderDialog._set_python_code_action |

| 1492 | method | DeveloperBuilderDialog._test_code |

| 1502 | method | DeveloperBuilderDialog._duplicate_current |

| 1514 | method | DeveloperBuilderDialog._delete_current |

| 1531 | method | DeveloperBuilderDialog._move_current |

| 1544 | method | DeveloperBuilderDialog._refresh_canvas |

| 1556 | method | DeveloperBuilderDialog._select_canvas_item |

| 1560 | method | DeveloperBuilderDialog._canvas_changed |



### bukkax_builder_sync.py

Синхронизация публичной части Developer Studio через сервер.

| Строка | Тип | Имя |

| --- | --- | --- |

| 19 | function | install_builder_sync |



### bukkax_screen_share.py

Демонстрация экрана/окна, 720p/1080p, просмотр, GUI-thread bridge.

| Строка | Тип | Имя |

| --- | --- | --- |

| 61 | class | _ScreenShareFrameBridge |

| 71 | method | _ScreenShareFrameBridge.__init__ |

| 81 | method | _ScreenShareFrameBridge._dispatch |

| 85 | function | _enum_windows_windows |

| 156 | class | ScreenShareSourceDialog |

| 157 | method | ScreenShareSourceDialog.__init__ |

| 268 | method | ScreenShareSourceDialog._quality_changed |

| 282 | method | ScreenShareSourceDialog._start_clicked |

| 307 | class | ScreenShareViewerDialog |

| 308 | method | ScreenShareViewerDialog.__init__ |

| 371 | method | ScreenShareViewerDialog._toggle_fullscreen |

| 377 | method | ScreenShareViewerDialog.set_quality_text |

| 382 | method | ScreenShareViewerDialog.set_frame |

| 389 | method | ScreenShareViewerDialog._render |

| 401 | method | ScreenShareViewerDialog.resizeEvent |

| 406 | function | _capture_source |

| 436 | function | install_screen_share |



### bukkax_call_quality.py

Безопасная стабилизация 1-to-1 голоса: 10-мс PCM-пакеты и jitter buffer.

| Строка | Тип | Имя |

| --- | --- | --- |

| 30 | function | install_call_quality |



### music_player.py

Встроенный браузер музыки/видео на QtWebEngine с историей SQLite.

| Строка | Тип | Имя |

| --- | --- | --- |

| 31 | function | app_dir |

| 40 | function | normalize_url |

| 49 | function | detect_service |

| 62 | function | extract_youtube_video_id |

| 84 | class | MusicDatabase |

| 85 | method | MusicDatabase.__init__ |

| 100 | method | MusicDatabase.add |

| 108 | method | MusicDatabase.update_title |

| 113 | method | MusicDatabase.items |

| 120 | method | MusicDatabase.clear |

| 124 | method | MusicDatabase.close |

| 131 | class | BrowserPage |

| 135 | class | MainWindow |

| 136 | method | MainWindow.__init__ |

| 152 | method | MainWindow._build_ui |

| 234 | method | MainWindow._setup_web |

| 278 | method | MainWindow._setup_shortcuts |

| 284 | method | MainWindow._focus_url |

| 288 | method | MainWindow.open_from_input |

| 293 | method | MainWindow.open_url |

| 310 | method | MainWindow._open_youtube |

| 320 | method | MainWindow._open_vk |

| 324 | method | MainWindow._on_title_changed |

| 334 | method | MainWindow._on_load_finished |

| 345 | method | MainWindow._load_history |

| 355 | method | MainWindow._open_history_item |

| 360 | method | MainWindow._clear_history |

| 366 | method | MainWindow.closeEvent |

| 371 | function | main |



## 21. Справочник ответных сообщений server → client

| Тип/группа | Назначение |

| --- | --- |

| history / room_history / dm_history / private_chat_history | История сообщений. |

| text / file / dm / dm_file | Новые сообщения/файлы. |

| room_list / room_list_changed / room_create_result | Состояние комнат. |

| private_chat_list / private_chat_invited / private_chat_members_changed / private_chat_removed | Состояние приватных бесед. |

| friend_list / friend_add_result | Друзья. |

| profile_data / profile_saved | Профили. |

| user_gift_result / gift_received / gift_image | Подарки. |

| news_list / news_posted | Новости. |

| admin_user_list / admin_result / kicked | Админ-события. |

| chess_invite / chess_invite_result / chess_accept / chess_move / chess_restart / chess_resign / chess_close | Сетевые шахматы. |

| builder_config_data / builder_config_updated / builder_config_missing / builder_config_publish_result | Developer Studio Sync. |

| screen_share_state / screen_share_frame | Демонстрация экрана. |

| call_offer / call_ringing / call_started / call_declined / call_result / call_ended | 1-to-1 звонки. |

| group_call_invite / group_call_joined / group_call_member_joined / group_call_member_left / group_call_result | Групповые звонки. |

| avatar_data / avatar_changed | Аватары. |



## 22. Чек-лист перед релизом

```text
□ python server.py запускается без traceback
□ python client_qt.py запускается без traceback
□ логин и список комнат
□ текст общий чат + ЛС
□ файл/картинка
□ профиль/аватар
□ подарок
□ шахматы PvP: случайный цвет, ходы, шах, закрытие
□ голос 1-to-1 в обе стороны
□ камера
□ screen share 720p/5 FPS
□ Developer Studio: local widget + publish public widget
□ updater: новая версия скачивается как Bukkax.exe
□ собрать server.exe, проверить консоль
□ собрать Bukkax.exe, проверить onefile
□ положить Bukkax.exe в updates/ и повысить updates/version.txt
□ проверить обновление старого клиента
```

## 23. Главное правило проекта

Сначала тест через python, потом EXE. Если функция требует server branch — тестировать client.py + server.py вместе. Только после работающего Python-варианта собирать PyInstaller. Перед патчами держать timestamp backup и проверять AST — это уже правильный паттерн, который используется в твоих установщиках.
