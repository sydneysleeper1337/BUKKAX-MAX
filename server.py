import socket
import threading
import sys
import os
import sqlite3
import json
import datetime
import uuid
import http.server
import socketserver
import urllib.request
import urllib.error
import io
import base64
from PIL import Image

from protocol import send_frame, recv_frame

# ---------- BUKKAX SAFE TCP SEND V1 START ----------
_bukkax_raw_send_frame = send_frame
_bukkax_send_locks = {}
_bukkax_send_locks_guard = threading.Lock()


def send_frame(sock, header, payload=b''):
    """
    Serialize all writes to the same client TCP socket.
    Important for screen-share frames: without this, frames sent from one
    server thread can interleave with chat/control frames from another thread.
    """
    key = id(sock)

    with _bukkax_send_locks_guard:
        lock = _bukkax_send_locks.get(key)

        if lock is None:
            lock = threading.Lock()
            _bukkax_send_locks[key] = lock

    with lock:
        return _bukkax_raw_send_frame(
            sock,
            header,
            payload,
        )
# ---------- BUKKAX SAFE TCP SEND V1 END ----------

HISTORY_LIMIT = 1000
DM_HISTORY_LIMIT = 1000

UPDATE_HTTP_PORT = 55556
VOICE_UDP_PORT = 55557
VIDEO_UDP_PORT = 55558


# ---------- Функция получения версии ----------
def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_current_version():
    version_path = os.path.join(get_base_dir(), 'version.txt')
    try:
        if os.path.exists(version_path):
            with open(version_path, 'r', encoding='utf-8') as f:
                version = f.read().strip()
                if version:
                    return version
        else:
            with open(version_path, 'w', encoding='utf-8') as f:
                f.write('1.0.0')
            return '1.0.0'
    except Exception:
        pass
    return '1.0.0'


CURRENT_VERSION = get_current_version()
ADMIN_NICKNAMES = {'Чак Чакич'}

DB_PATH = os.path.join(get_base_dir(), 'chat_users.db')
UPDATES_DIR = os.path.join(get_base_dir(), 'updates')
# ---------- BUKKAX UPDATE CANONICAL NAME V1 ----------
UPDATE_EXE_NAME = 'Bukkax.exe'
LEGACY_UPDATE_EXE_NAME = 'bukkax' + '_client.exe'
ALLOWED_UPDATE_FILES = {'version.txt', UPDATE_EXE_NAME}


class UpdateRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        requested = self.path.lstrip('/')
        # ---------- BUKKAX UPDATE LEGACY ALIAS V1 ----------
        if requested == LEGACY_UPDATE_EXE_NAME:
            requested = UPDATE_EXE_NAME
        if requested not in ALLOWED_UPDATE_FILES:
            self.send_error(404, "Not Found")
            return
        file_path = os.path.join(UPDATES_DIR, requested)
        if not os.path.exists(file_path):
            self.send_error(404, "Not Found")
            return
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500, "Internal Server Error")

    def log_message(self, format, *args):
        pass


def start_update_server():
    os.makedirs(UPDATES_DIR, exist_ok=True)
    version_file = os.path.join(UPDATES_DIR, 'version.txt')
    if not os.path.exists(version_file):
        with open(version_file, 'w') as f:
            f.write(CURRENT_VERSION)

    class QuietTCPServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    httpd = QuietTCPServer(('0.0.0.0', UPDATE_HTTP_PORT), UpdateRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    print(f"🔄 Сервер обновлений запущен на порту {UPDATE_HTTP_PORT}")
    print(f"   Текущая версия: {open(version_file).read().strip()}")


# ---------- BUKKAX BUILDER SYNC SERVER V1 START ----------
# Developer Studio V2 server sanitizer.
BUILDER_SERVER_CONFIG_PATH = os.path.join(
    get_base_dir(),
    'builder_config_server.json',
)
BUILDER_CONFIG_MAX_BYTES = 2 * 1024 * 1024


def _bukkax_builder_valid_id(value):
    value = str(value or '')
    if not value or len(value) > 64:
        return False
    first = value[0]
    if not (first.isalpha() or first == '_'):
        return False
    return all(ch.isalnum() or ch == '_' for ch in value)


def _bukkax_builder_color(value):
    value = str(value or '').strip()
    if not value:
        return ''
    if len(value) > 16:
        return ''
    # Сервер не интерпретирует QSS. Разрешаем только короткие #RGB/#RRGGBB/#AARRGGBB.
    if value.startswith('#') and len(value) in (4, 7, 9):
        chars = value[1:]
        if all(ch in '0123456789abcdefABCDEF' for ch in chars):
            return value
    return ''


def _bukkax_builder_sanitize_payload(payload):
    if not payload or len(payload) > BUILDER_CONFIG_MAX_BYTES:
        return None, 'too_large'

    try:
        source = json.loads(payload.decode('utf-8'))
    except Exception:
        return None, 'invalid_json'

    if not isinstance(source, dict):
        return None, 'invalid'

    widgets = source.get('widgets')
    if not isinstance(widgets, list):
        return None, 'invalid'
    if len(widgets) > 250:
        return None, 'too_many_widgets'

    allowed_types = {'button', 'input', 'label', 'image'}
    allowed_visibility = {'all', 'admin'}
    allowed_styles = {'default', 'accent', 'success', 'danger'}
    allowed_placement = {'topbar', 'floating'}

    # Публично разрешены только известные встроенные действия.
    allowed_actions = {
        'none', 'open_music', 'open_chess', 'open_my_profile', 'open_news',
        'open_audio_settings', 'open_background', 'open_notifications',
        'open_admin', 'send_gift', 'open_dm', 'open_profile', 'call_user',
        'video_call_user', 'set_chat_input', 'send_chat_text', 'show_message',
        'open_url', 'clear_widget',
    }

    used_ids = set()
    clean_widgets = []

    for item in widgets:
        if not isinstance(item, dict):
            continue

        widget_id = str(item.get('id') or '').strip()
        if not _bukkax_builder_valid_id(widget_id) or widget_id in used_ids:
            continue

        widget_type = str(item.get('type') or 'button')
        if widget_type not in allowed_types:
            widget_type = 'button'

        visibility = str(item.get('visibility') or 'all')
        if visibility not in allowed_visibility:
            # visibility=me не публикуется.
            continue

        style = str(item.get('style') or 'default')
        if style not in allowed_styles:
            style = 'default'

        placement = str(item.get('placement') or 'topbar')
        if placement not in allowed_placement:
            placement = 'topbar'

        action = str(item.get('action') or 'none')[:64]
        if action not in allowed_actions:
            action = 'none'

        text = str(item.get('text') or '')[:300]
        tooltip = str(item.get('tooltip') or '')[:500]
        argument = str(item.get('argument') or '')[:1000]

        def _int(name, default, low, high):
            try:
                value = int(item.get(name) if item.get(name) is not None else default)
            except Exception:
                value = default
            return max(low, min(high, value))

        width = _int('width', 0, 0, 1000)
        height = _int('height', 0, 0, 800)
        x = _int('x', 0, 0, 5000)
        y = _int('y', 0, 0, 5000)
        radius = _int('radius', 8, 0, 60)
        font_size = _int('font_size', 13, 8, 48)
        icon_size = _int('icon_size', 20, 12, 128)

        icon_data = str(item.get('icon_data') or '')
        # 180 KB бинарных данных ~ 246 KB base64. Ограничиваем строку.
        if len(icon_data) > 250 * 1024:
            icon_data = ''

        icon_name = str(item.get('icon_name') or '')[:120]

        clean_widgets.append({
            'id': widget_id,
            'type': widget_type,
            'text': text,
            'tooltip': tooltip,
            'width': width,
            'height': height,
            'x': x,
            'y': y,
            'placement': placement,
            'visibility': visibility,
            'style': style,
            'action': action,
            'argument': argument,
            'enabled': bool(item.get('enabled', True)),
            'radius': radius,
            'font_size': font_size,
            'font_bold': bool(item.get('font_bold', False)),
            'bg_color': _bukkax_builder_color(item.get('bg_color')),
            'text_color': _bukkax_builder_color(item.get('text_color')),
            'border_color': _bukkax_builder_color(item.get('border_color')),
            'icon_data': icon_data,
            'icon_name': icon_name,
            'icon_size': icon_size,
        })
        used_ids.add(widget_id)

    clean = {'version': 2, 'widgets': clean_widgets}
    data = json.dumps(
        clean,
        ensure_ascii=False,
        separators=(',', ':'),
    ).encode('utf-8')

    if len(data) > BUILDER_CONFIG_MAX_BYTES:
        return None, 'too_large'
    return data, 'ok'


def _bukkax_builder_load_server_config():
    if not os.path.exists(BUILDER_SERVER_CONFIG_PATH):
        return None
    try:
        with open(BUILDER_SERVER_CONFIG_PATH, 'rb') as f:
            data = f.read(BUILDER_CONFIG_MAX_BYTES + 1)
        if len(data) > BUILDER_CONFIG_MAX_BYTES:
            return None
        clean, status = _bukkax_builder_sanitize_payload(data)
        if status != 'ok':
            return None
        return clean
    except Exception:
        return None


def _bukkax_builder_save_server_config(data):
    tmp = BUILDER_SERVER_CONFIG_PATH + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, BUILDER_SERVER_CONFIG_PATH)
# ---------- BUKKAX BUILDER SYNC SERVER V1 END ----------

class ChatServer:
    def __init__(self, host='0.0.0.0', port=55555):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(5)
        self.clients = []
        self.nicknames = []

        self.pending_calls = {}
        self.active_calls = {}
        self.active_group_calls = {}
        self.calls_lock = threading.Lock()

        self.db_lock = threading.Lock()
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._init_db()

        self.start_voice_relay()
        self.start_video_relay()

        print(f"✨ Сервер запущен на {host}:{port}")
        print(f"🌐 Локальный IP: {self.get_local_ip()}")
        print(f"📌 Версия сервера: {CURRENT_VERSION}")
        print("👂 Ожидаем подключения...\n")

    # ---------- Инициализация БД (добавлена таблица banned) ----------
    def _init_db(self):
        with self.db_lock:
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    nickname   TEXT PRIMARY KEY,
                    device_id  TEXT NOT NULL,
                    last_ip    TEXT,
                    first_seen TEXT,
                    last_seen  TEXT
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    room      TEXT NOT NULL DEFAULT 'general',
                    sender    TEXT NOT NULL,
                    msg_type  TEXT NOT NULL,
                    text      TEXT,
                    filename  TEXT,
                    timestamp TEXT NOT NULL
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS friends (
                    owner_nick  TEXT NOT NULL,
                    friend_nick TEXT NOT NULL,
                    PRIMARY KEY (owner_nick, friend_nick)
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS dms (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender    TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    text      TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    msg_type  TEXT DEFAULT 'text',
                    filename  TEXT
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS avatars (
                    nickname   TEXT PRIMARY KEY,
                    image_data BLOB NOT NULL
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS rooms (
                    name       TEXT PRIMARY KEY,
                    creator    TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS private_chats (
                    id         TEXT PRIMARY KEY,
                    name       TEXT NOT NULL,
                    creator    TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS private_chat_members (
                    chat_id  TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    PRIMARY KEY (chat_id, nickname)
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS profiles (
                    nickname   TEXT PRIMARY KEY,
                    bio        TEXT,
                    status     TEXT,
                    updated_at TEXT
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS gifts (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipient  TEXT NOT NULL,
                    sender     TEXT NOT NULL,
                    note       TEXT,
                    image_data BLOB,
                    timestamp  TEXT NOT NULL
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS news (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    author     TEXT NOT NULL,
                    text       TEXT,
                    image_data BLOB,
                    timestamp  TEXT NOT NULL
                )
            ''')
            # BAN: таблица банов
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS banned (
                    nickname   TEXT PRIMARY KEY,
                    device_id  TEXT,
                    banned_at  TEXT,
                    banned_by  TEXT
                )
            ''')
            # Миграции
            try:
                self.db.execute("ALTER TABLE profiles ADD COLUMN status TEXT")
            except sqlite3.OperationalError:
                pass

            try:
                self.db.execute("ALTER TABLE dms ADD COLUMN msg_type TEXT DEFAULT 'text'")
            except sqlite3.OperationalError:
                pass
            try:
                self.db.execute("ALTER TABLE dms ADD COLUMN filename TEXT")
            except sqlite3.OperationalError:
                pass
            self.db.commit()

    # ---------- Методы работы с БД ----------
    def get_nickname_owner(self, nickname):
        with self.db_lock:
            cur = self.db.execute('SELECT device_id FROM users WHERE nickname = ?', (nickname,))
            row = cur.fetchone()
            return row[0] if row else None

    def nickname_exists(self, nickname):
        with self.db_lock:
            cur = self.db.execute('SELECT 1 FROM users WHERE nickname = ?', (nickname,))
            return cur.fetchone() is not None

    def register_nickname(self, nickname, device_id, ip):
        now = datetime.datetime.now().isoformat(timespec='seconds')
        with self.db_lock:
            self.db.execute(
                'INSERT INTO users (nickname, device_id, last_ip, first_seen, last_seen) '
                'VALUES (?, ?, ?, ?, ?)',
                (nickname, device_id, ip, now, now)
            )
            self.db.commit()

    def touch_nickname(self, nickname, ip):
        now = datetime.datetime.now().isoformat(timespec='seconds')
        with self.db_lock:
            self.db.execute(
                'UPDATE users SET last_ip = ?, last_seen = ? WHERE nickname = ?',
                (ip, now, nickname)
            )
            self.db.commit()

    def is_banned(self, nickname, device_id):
        """Проверяет, забанен ли ник или устройство."""
        with self.db_lock:
            cur = self.db.execute(
                'SELECT 1 FROM banned WHERE nickname = ? OR device_id = ?',
                (nickname, device_id)
            )
            return cur.fetchone() is not None

    def ban_user(self, nickname, device_id, banned_by):
        """Добавляет пользователя в бан-лист, удаляет из всех таблиц."""
        now = datetime.datetime.now().isoformat(timespec='seconds')
        with self.db_lock:
            # Добавляем в banned
            self.db.execute(
                'INSERT OR REPLACE INTO banned (nickname, device_id, banned_at, banned_by) '
                'VALUES (?, ?, ?, ?)',
                (nickname, device_id, now, banned_by)
            )
            # Удаляем из users
            self.db.execute('DELETE FROM users WHERE nickname = ?', (nickname,))
            # Удаляем из friends (где он owner или friend)
            self.db.execute('DELETE FROM friends WHERE owner_nick = ? OR friend_nick = ?', (nickname, nickname))
            # Удаляем из private_chat_members
            self.db.execute('DELETE FROM private_chat_members WHERE nickname = ?', (nickname,))
            # Удаляем из profiles
            self.db.execute('DELETE FROM profiles WHERE nickname = ?', (nickname,))
            # Удаляем из avatars
            self.db.execute('DELETE FROM avatars WHERE nickname = ?', (nickname,))
            # Можно удалить из gifts? Оставляем для истории.
            # Можно удалить из messages? Оставляем.
            self.db.commit()

        # PATCH: если пользователь онлайн, сразу закрываем его клиент; если офлайн — бан уже сохранён в БД.
        target_client = self.get_client_by_nick(nickname)
        if target_client:
            try:
                send_frame(target_client, {'type': 'kicked', 'by': banned_by, 'ban': True})
            except Exception:
                pass
            self.remove_client(target_client)

    # ---------- Остальные методы (без изменений) ----------
    def save_message(self, room, sender, msg_type, text=None, filename=None):
        now = datetime.datetime.now().isoformat(timespec='seconds')
        with self.db_lock:
            self.db.execute(
                'INSERT INTO messages (room, sender, msg_type, text, filename, timestamp) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (room, sender, msg_type, text, filename, now)
            )
            self.db.commit()

    def get_history(self, room='general', limit=HISTORY_LIMIT):
        with self.db_lock:
            cur = self.db.execute(
                'SELECT sender, msg_type, text, filename, timestamp FROM messages '
                'WHERE room = ? ORDER BY id DESC LIMIT ?',
                (room, limit)
            )
            rows = cur.fetchall()
        rows.reverse()
        return [
            {'sender': r[0], 'msg_type': r[1], 'text': r[2], 'filename': r[3], 'timestamp': r[4]}
            for r in rows
        ]

    def try_add_friend(self, owner, target):
        if not target:
            return 'invalid'
        if target == owner:
            return 'self'
        if not self.nickname_exists(target):
            return 'not_found'
        with self.db_lock:
            cur = self.db.execute(
                'SELECT 1 FROM friends WHERE owner_nick = ? AND friend_nick = ?',
                (owner, target)
            )
            already = cur.fetchone() is not None
            if already:
                return 'already'
            self.db.execute(
                'INSERT OR IGNORE INTO friends (owner_nick, friend_nick) VALUES (?, ?)',
                (owner, target)
            )
            self.db.execute(
                'INSERT OR IGNORE INTO friends (owner_nick, friend_nick) VALUES (?, ?)',
                (target, owner)
            )
            self.db.commit()
        return 'ok'

    def get_friends(self, owner):
        with self.db_lock:
            cur = self.db.execute('SELECT friend_nick FROM friends WHERE owner_nick = ?', (owner,))
            rows = cur.fetchall()
        return [{'nick': r[0], 'online': r[0] in self.nicknames} for r in rows]

    def save_dm(self, sender, recipient, text=None, msg_type='text', filename=None):
        now = datetime.datetime.now().isoformat(timespec='seconds')
        with self.db_lock:
            if text is None and msg_type == 'file':
                text = ''
            self.db.execute(
                'INSERT INTO dms (sender, recipient, text, timestamp, msg_type, filename) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (sender, recipient, text, now, msg_type, filename)
            )
            self.db.commit()

    def get_dm_history(self, nick_a, nick_b, limit=DM_HISTORY_LIMIT):
        with self.db_lock:
            cur = self.db.execute(
                'SELECT sender, text, timestamp, msg_type, filename FROM dms '
                'WHERE (sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?) '
                'ORDER BY id DESC LIMIT ?',
                (nick_a, nick_b, nick_b, nick_a, limit)
            )
            rows = cur.fetchall()
        rows.reverse()
        return [
            {'sender': r[0], 'text': r[1], 'timestamp': r[2], 'msg_type': r[3] or 'text', 'filename': r[4]}
            for r in rows
        ]

    def try_create_room(self, name, creator):
        name = (name or '').strip()
        if not name:
            return 'invalid'
        if name.lower() == 'general':
            return 'reserved'
        if len(name) > 40:
            return 'too_long'
        if ':' in name:
            return 'invalid'
        with self.db_lock:
            cur = self.db.execute('SELECT 1 FROM rooms WHERE name = ?', (name,))
            if cur.fetchone():
                return 'exists'
            now = datetime.datetime.now().isoformat(timespec='seconds')
            self.db.execute(
                'INSERT INTO rooms (name, creator, created_at) VALUES (?, ?, ?)',
                (name, creator, now)
            )
            self.db.commit()
        return 'ok'

    def get_rooms(self):
        with self.db_lock:
            cur = self.db.execute('SELECT name FROM rooms ORDER BY created_at ASC')
            rows = cur.fetchall()
        return ['general'] + [r[0] for r in rows]

    def try_create_private_chat(self, name, creator, invitees):
        name = (name or '').strip()
        if not name:
            return None, 'invalid', []
        valid_invitees = []
        skipped = []
        for nick in invitees:
            nick = nick.strip()
            if not nick or nick == creator:
                continue
            else:
                skipped.append(nick)
        chat_id = uuid.uuid4().hex[:12]
        now = datetime.datetime.now().isoformat(timespec='seconds')
        with self.db_lock:
            self.db.execute(
                'INSERT INTO private_chats (id, name, creator, created_at) VALUES (?, ?, ?, ?)',
                (chat_id, name, creator, now)
            )
            members = [creator] + valid_invitees
            for nick in members:
                self.db.execute(
                    'INSERT OR IGNORE INTO private_chat_members (chat_id, nickname) VALUES (?, ?)',
                    (chat_id, nick)
                )
            self.db.commit()
        return chat_id, 'ok', skipped

    def get_private_chats_for(self, nickname):
        with self.db_lock:
            cur = self.db.execute('''
                SELECT pc.id, pc.name FROM private_chats pc
                JOIN private_chat_members m ON m.chat_id = pc.id
                WHERE m.nickname = ?
                ORDER BY pc.created_at ASC
            ''', (nickname,))
            rows = cur.fetchall()
        return [{'id': r[0], 'name': r[1]} for r in rows]

    def get_private_chat_members(self, chat_id):
        with self.db_lock:
            cur = self.db.execute(
                'SELECT nickname FROM private_chat_members WHERE chat_id = ?', (chat_id,)
            )
            rows = cur.fetchall()
        return [r[0] for r in rows]

    def is_private_chat_member(self, chat_id, nickname):
        with self.db_lock:
            cur = self.db.execute(
                'SELECT 1 FROM private_chat_members WHERE chat_id = ? AND nickname = ?',
                (chat_id, nickname)
            )
            return cur.fetchone() is not None


    # ---------- PATCH: управление участниками приватных бесед ----------
    def is_private_chat_owner(self, chat_id, nickname):
        with self.db_lock:
            cur = self.db.execute(
                'SELECT 1 FROM private_chats WHERE id = ? AND creator = ?',
                (chat_id, nickname)
            )
            return cur.fetchone() is not None

    def get_private_chat_name(self, chat_id):
        with self.db_lock:
            cur = self.db.execute('SELECT name FROM private_chats WHERE id = ?', (chat_id,))
            row = cur.fetchone()
            return row[0] if row else chat_id

    def notify_private_chat_members_changed(self, chat_id):
        """Просит всех онлайн-участников обновить список приватных бесед."""
        for nick in self.get_private_chat_members(chat_id):
            member_client = self.get_client_by_nick(nick)
            if member_client:
                try:
                    send_frame(member_client, {'type': 'private_chat_members_changed', 'chat_id': chat_id})
                except Exception:
                    self.remove_client(member_client)

    def private_chat_add_member(self, chat_id, actor, target):
        target = (target or '').strip()
        if not chat_id or not target:
            return 'invalid'
        if not self.is_private_chat_member(chat_id, actor):
            return 'forbidden'
        # Только создатель беседы или глобальный админ может менять состав.
        if not self.is_private_chat_owner(chat_id, actor) and actor not in ADMIN_NICKNAMES:
            return 'forbidden'
        with self.db_lock:
            cur = self.db.execute(
                'SELECT 1 FROM private_chat_members WHERE chat_id = ? AND nickname = ?',
                (chat_id, target)
            )
            if cur.fetchone():
                return 'already'
            self.db.execute(
                'INSERT OR IGNORE INTO private_chat_members (chat_id, nickname) VALUES (?, ?)',
                (chat_id, target)
            )
            self.db.commit()
        name = self.get_private_chat_name(chat_id)
        target_client = self.get_client_by_nick(target)
        if target_client:
            try:
                send_frame(target_client, {
                    'type': 'private_chat_invited', 'chat_id': chat_id,
                    'name': name, 'creator': actor,
                })
            except Exception:
                self.remove_client(target_client)
        self.save_message(f'private:{chat_id}', 'Сервер', 'text', text=f'{actor} пригласил(а) {target}')
        self.broadcast_to_private_chat(chat_id, {
            'type': 'text', 'nick': 'Сервер', 'text': f'{actor} пригласил(а) {target}',
            'room': f'private:{chat_id}'
        })
        self.notify_private_chat_members_changed(chat_id)
        return 'ok'

    def private_chat_remove_member(self, chat_id, actor, target):
        target = (target or '').strip()
        if not chat_id or not target:
            return 'invalid'
        if not self.is_private_chat_member(chat_id, actor):
            return 'forbidden'
        if not self.is_private_chat_owner(chat_id, actor) and actor not in ADMIN_NICKNAMES:
            return 'forbidden'
        if target == actor and self.is_private_chat_owner(chat_id, actor):
            return 'owner_self'
        if self.is_private_chat_owner(chat_id, target):
            return 'owner'
        if not self.is_private_chat_member(chat_id, target):
            return 'not_member'
        with self.db_lock:
            self.db.execute(
                'DELETE FROM private_chat_members WHERE chat_id = ? AND nickname = ?',
                (chat_id, target)
            )
            self.db.commit()
        target_client = self.get_client_by_nick(target)
        if target_client:
            try:
                send_frame(target_client, {
                    'type': 'private_chat_removed', 'chat_id': chat_id,
                    'by': actor, 'name': self.get_private_chat_name(chat_id)
                })
            except Exception:
                self.remove_client(target_client)
        self.save_message(f'private:{chat_id}', 'Сервер', 'text', text=f'{actor} удалил(а) {target} из беседы')
        self.broadcast_to_private_chat(chat_id, {
            'type': 'text', 'nick': 'Сервер', 'text': f'{actor} удалил(а) {target} из беседы',
            'room': f'private:{chat_id}'
        })
        self.notify_private_chat_members_changed(chat_id)
        return 'ok'

    def set_profile(self, nickname, bio, status=''):
        now = datetime.datetime.now().isoformat(timespec='seconds')
        bio = (bio or '').strip()[:500]
        status = (status or '').strip()[:80]
        with self.db_lock:
            self.db.execute(
                'INSERT INTO profiles (nickname, bio, status, updated_at) VALUES (?, ?, ?, ?) '
                'ON CONFLICT(nickname) DO UPDATE SET '
                'bio = excluded.bio, status = excluded.status, updated_at = excluded.updated_at',
                (nickname, bio, status, now)
            )
            self.db.commit()

    def set_profile_bio(self, nickname, bio):
        # Совместимость со старыми клиентами: если пришёл только bio, статус не трогаем.
        now = datetime.datetime.now().isoformat(timespec='seconds')
        bio = (bio or '').strip()[:500]
        with self.db_lock:
            self.db.execute(
                'INSERT INTO profiles (nickname, bio, updated_at) VALUES (?, ?, ?) '
                'ON CONFLICT(nickname) DO UPDATE SET bio = excluded.bio, updated_at = excluded.updated_at',
                (nickname, bio, now)
            )
            self.db.commit()

    def get_profile(self, nickname):
        with self.db_lock:
            try:
                cur = self.db.execute('SELECT bio, status FROM profiles WHERE nickname = ?', (nickname,))
                row = cur.fetchone()
            except sqlite3.OperationalError:
                cur = self.db.execute('SELECT bio FROM profiles WHERE nickname = ?', (nickname,))
                old_row = cur.fetchone()
                row = (old_row[0], '') if old_row else None
            cur2 = self.db.execute('SELECT first_seen, last_seen FROM users WHERE nickname = ?', (nickname,))
            row2 = cur2.fetchone()
        return {
            'bio': row[0] if row else '',
            'status': row[1] if row and len(row) > 1 and row[1] else '',
            'joined': row2[0] if row2 else '',
            'last_seen': row2[1] if row2 and len(row2) > 1 else '',
        }

    def add_gift(self, recipient, sender, note, image_data):
        now = datetime.datetime.now().isoformat(timespec='seconds')
        with self.db_lock:
            self.db.execute(
                'INSERT INTO gifts (recipient, sender, note, image_data, timestamp) VALUES (?, ?, ?, ?, ?)',
                (recipient, sender, note, image_data, now)
            )
            self.db.commit()
            cur = self.db.execute('SELECT last_insert_rowid()')
            gift_id = cur.fetchone()[0]
        return gift_id

    def get_gifts(self, nickname, limit=50):
        with self.db_lock:
            cur = self.db.execute(
                'SELECT id, sender, note, timestamp FROM gifts WHERE recipient = ? '
                'ORDER BY id DESC LIMIT ?',
                (nickname, limit)
            )
            rows = cur.fetchall()
        return [{'id': r[0], 'sender': r[1], 'note': r[2], 'timestamp': r[3]} for r in rows]

    def get_gift_image(self, gift_id):
        with self.db_lock:
            cur = self.db.execute('SELECT image_data FROM gifts WHERE id = ?', (gift_id,))
            row = cur.fetchone()
        return row[0] if row else None

    def add_news(self, author, text, image_data):
        now = datetime.datetime.now().isoformat(timespec='seconds')
        with self.db_lock:
            self.db.execute(
                'INSERT INTO news (author, text, image_data, timestamp) VALUES (?, ?, ?, ?)',
                (author, text, image_data, now)
            )
            self.db.commit()
            cur = self.db.execute('SELECT last_insert_rowid()')
            news_id = cur.fetchone()[0]
        return news_id

    def get_news(self, limit=30):
        with self.db_lock:
            cur = self.db.execute(
                'SELECT id, author, text, timestamp, (image_data IS NOT NULL) FROM news '
                'ORDER BY id DESC LIMIT ?',
                (limit,)
            )
            rows = cur.fetchall()
        rows.reverse()
        return [
            {'id': r[0], 'author': r[1], 'text': r[2], 'timestamp': r[3], 'has_image': bool(r[4])}
            for r in rows
        ]

    def get_news_image(self, news_id):
        with self.db_lock:
            cur = self.db.execute('SELECT image_data FROM news WHERE id = ?', (news_id,))
            row = cur.fetchone()
        return row[0] if row else None

    def get_all_users_with_status(self):
        with self.db_lock:
            cur = self.db.execute(
                'SELECT nickname, first_seen, last_seen FROM users ORDER BY first_seen ASC'
            )
            rows = cur.fetchall()
        return [
            {'nickname': r[0], 'first_seen': r[1], 'last_seen': r[2], 'online': r[0] in self.nicknames}
            for r in rows
        ]

    def save_avatar(self, nickname, image_data):
        with self.db_lock:
            self.db.execute(
                'INSERT INTO avatars (nickname, image_data) VALUES (?, ?) '
                'ON CONFLICT(nickname) DO UPDATE SET image_data = excluded.image_data',
                (nickname, image_data)
            )
            self.db.commit()

    def get_avatar(self, nickname):
        with self.db_lock:
            cur = self.db.execute('SELECT image_data FROM avatars WHERE nickname = ?', (nickname,))
            row = cur.fetchone()
            return row[0] if row else None

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "Не удалось определить"

    # ---------- UDP-релеи (без изменений) ----------
    def start_voice_relay(self):
        self.voice_socket = self._start_media_relay(VOICE_UDP_PORT, 'audio')

    def start_video_relay(self):
        self.video_socket = self._start_media_relay(VIDEO_UDP_PORT, 'video')

    def _start_media_relay(self, port, media_label):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', port))
        thread = threading.Thread(target=self._media_relay_loop, args=(sock, media_label), daemon=True)
        thread.start()
        print(f"📡 Релей {media_label} (UDP) запущен на порту {port}")
        return sock

    def _media_relay_loop(self, sock, media_label):
        addr_key_a = f'{media_label}_addr_a'
        addr_key_b = f'{media_label}_addr_b'
        group_addr_key = f'{media_label}_addrs'
        while True:
            try:
                data, addr = sock.recvfrom(65536)
            except Exception:
                continue
            if len(data) < 17:
                continue
            call_id = data[:16].decode('ascii', errors='ignore')
            id_byte = data[16:17]
            targets = []
            with self.calls_lock:
                call = self.active_calls.get(call_id)
                if call:
                    if id_byte == b'0':
                        call[addr_key_a] = addr
                        target_addr = call.get(addr_key_b)
                    else:
                        call[addr_key_b] = addr
                        target_addr = call.get(addr_key_a)
                    if target_addr:
                        targets = [target_addr]
                else:
                    group_call = self.active_group_calls.get(call_id)
                    if group_call:
                        member_id = id_byte[0]
                        addr_map = group_call.setdefault(group_addr_key, {})
                        addr_map[member_id] = addr
                        targets = [a for mid, a in addr_map.items() if mid != member_id]
            for target_addr in targets:
                try:
                    sock.sendto(data, target_addr)
                except Exception:
                    pass

    def end_calls_for(self, nickname):
        to_notify = []
        group_notify = []
        with self.calls_lock:
            for call_id, call in list(self.active_calls.items()):
                if call['nick_a'] == nickname or call['nick_b'] == nickname:
                    other = call['nick_b'] if call['nick_a'] == nickname else call['nick_a']
                    to_notify.append((call_id, other))
                    del self.active_calls[call_id]
            for call_id, pending in list(self.pending_calls.items()):
                if pending['caller'] == nickname or pending['callee'] == nickname:
                    other = pending['callee'] if pending['caller'] == nickname else pending['caller']
                    to_notify.append((call_id, other))
                    del self.pending_calls[call_id]
            for call_id, group_call in list(self.active_group_calls.items()):
                leaving_id = None
                for mid, nick in list(group_call['members'].items()):
                    if nick == nickname:
                        leaving_id = mid
                        del group_call['members'][mid]
                        group_call.get('audio_addrs', {}).pop(mid, None)
                        group_call.get('video_addrs', {}).pop(mid, None)
                        break
                if leaving_id is not None:
                    remaining = list(group_call['members'].values())
                    if remaining:
                        group_notify.append((call_id, leaving_id, remaining))
                    else:
                        del self.active_group_calls[call_id]
        for call_id, other_nick in to_notify:
            other_client = self.get_client_by_nick(other_nick)
            if other_client:
                try:
                    send_frame(other_client, {'type': 'call_ended', 'call_id': call_id})
                except Exception:
                    pass
        for call_id, leaving_id, remaining_nicks in group_notify:
            for nick in remaining_nicks:
                member_client = self.get_client_by_nick(nick)
                if member_client:
                    try:
                        send_frame(member_client, {
                            'type': 'group_call_member_left', 'call_id': call_id, 'member_id': leaving_id,
                        })
                    except Exception:
                        pass

    def broadcast_frame(self, header, payload=b'', sender_client=None):
        for client in self.clients[:]:
            if sender_client and client == sender_client:
                continue
            try:
                send_frame(client, header, payload)
            except Exception:
                self.remove_client(client)

    def broadcast_system(self, text):
        header = {'type': 'text', 'nick': 'Сервер', 'text': text}
        self.broadcast_frame(header)

    def get_client_by_nick(self, nick):
        if nick in self.nicknames:
            idx = self.nicknames.index(nick)
            return self.clients[idx]
        return None

    def broadcast_to_private_chat(self, chat_id, header, payload=b'', sender_client=None):
        for nick in self.get_private_chat_members(chat_id):
            client = self.get_client_by_nick(nick)
            if client and client != sender_client:
                try:
                    send_frame(client, header, payload)
                except Exception:
                    self.remove_client(client)

    def remove_client(self, client):
        if client in self.clients:
            index = self.clients.index(client)
            self.clients.remove(client)
            client.close()
            nickname = self.nicknames.pop(index)
            self.end_calls_for(nickname)
            self.broadcast_system(f'❌ {nickname} покинул чат.')
            print(f"👋 {nickname} отключился")

    # ---------- Основной цикл обработки клиентов ----------
    def perform_handshake(self, client, address):
        client.send('NICK'.encode('utf-8'))
        while True:
            try:
                raw = client.recv(1024).decode('utf-8')
            except Exception:
                return None
            if not raw:
                return None

            try:
                data = json.loads(raw)
                nickname = (data.get('nickname') or '').strip()
                device_id = (data.get('device_id') or '').strip()
            except Exception:
                client.send('NICK_INVALID'.encode('utf-8'))
                continue

            if not nickname or not device_id:
                client.send('NICK_INVALID'.encode('utf-8'))
                continue

            # BAN: проверяем, не забанен ли ник или устройство
            if self.is_banned(nickname, device_id):
                client.send('NICK_BANNED'.encode('utf-8'))
                return None

            if nickname in self.nicknames:
                client.send('NICK_TAKEN'.encode('utf-8'))
                continue

            owner = self.get_nickname_owner(nickname)
            if owner is None:
                self.register_nickname(nickname, device_id, address[0])
                client.send('NICK_OK'.encode('utf-8'))
                return nickname
            elif owner == device_id:
                self.touch_nickname(nickname, address[0])
                client.send('NICK_OK'.encode('utf-8'))
                return nickname
            else:
                client.send('NICK_TAKEN'.encode('utf-8'))
                continue

    def handle_client(self, client):
        while True:
            try:
                header, payload = recv_frame(client)
                index = self.clients.index(client)
                sender_nick = self.nicknames[index]
                msg_type = header.get('type')

                if msg_type == 'text':
                    room = (header.get('room') or 'general').strip()
                    header['nick'] = sender_nick
                    header['room'] = room
                    text = header.get('text', '')
                    if room.startswith('private:'):
                        chat_id = room.split(':', 1)[1]
                        if not self.is_private_chat_member(chat_id, sender_nick):
                            continue
                        self.save_message(room, sender_nick, 'text', text=text)
                        print(f"🔒 [{room}] {sender_nick}: {text}")
                        self.broadcast_to_private_chat(chat_id, header, b'', client)
                    else:
                        self.save_message(room, sender_nick, 'text', text=text)
                        print(f"📨 [{room}] {sender_nick}: {text}")
                        self.broadcast_frame(header, payload, client)

                elif msg_type == 'file':
                    room = (header.get('room') or 'general').strip()
                    header['nick'] = sender_nick
                    header['room'] = room
                    filename = header.get('filename')
                    if room.startswith('private:'):
                        chat_id = room.split(':', 1)[1]
                        if not self.is_private_chat_member(chat_id, sender_nick):
                            continue
                        self.save_message(room, sender_nick, 'file', filename=filename)
                        print(f"🔒 [{room}] {sender_nick} отправил файл: {filename}")
                        self.broadcast_to_private_chat(chat_id, header, payload, client)
                    else:
                        self.save_message(room, sender_nick, 'file', filename=filename)
                        print(f"📎 [{room}] {sender_nick} отправил файл: {filename} ({header.get('size')} байт)")
                        self.broadcast_frame(header, payload, client)

                elif msg_type == 'friend_add':
                    target = (header.get('target') or '').strip()
                    status = self.try_add_friend(sender_nick, target)
                    send_frame(client, {'type': 'friend_add_result', 'target': target, 'status': status})

                elif msg_type == 'friend_list_request':
                    friends = self.get_friends(sender_nick)
                    send_frame(client, {'type': 'friend_list', 'friends': friends})

                elif msg_type == 'dm':
                    target = (header.get('target') or '').strip()
                    text = header.get('text', '')
                    self.save_dm(sender_nick, target, text=text, msg_type='text')
                    target_client = self.get_client_by_nick(target)
                    if target_client:
                        try:
                            send_frame(target_client, {'type': 'dm', 'nick': sender_nick, 'text': text})
                        except Exception:
                            self.remove_client(target_client)
                    print(f"✉️  ЛС {sender_nick} → {target}: {text}")

                elif msg_type == 'dm_file':
                    target = (header.get('target') or '').strip()
                    filename = header.get('filename')
                    self.save_dm(sender_nick, target, text='', msg_type='file', filename=filename)
                    target_client = self.get_client_by_nick(target)
                    if target_client:
                        try:
                            send_frame(
                                target_client,
                                {'type': 'dm_file', 'nick': sender_nick, 'filename': filename, 'size': len(payload)},
                                payload
                            )
                        except Exception:
                            self.remove_client(target_client)
                    print(f"📎 ЛС {sender_nick} → {target}: файл {filename}")

                elif msg_type == 'dm_history_request':
                    target = (header.get('target') or '').strip()
                    messages = self.get_dm_history(sender_nick, target)
                    send_frame(client, {'type': 'dm_history', 'target': target, 'messages': messages})

                elif msg_type == 'room_create':
                    name = (header.get('name') or '').strip()
                    status = self.try_create_room(name, sender_nick)
                    send_frame(client, {'type': 'room_create_result', 'name': name, 'status': status})
                    if status == 'ok':
                        self.broadcast_frame({'type': 'room_list_changed'})

                elif msg_type == 'room_list_request':
                    send_frame(client, {'type': 'room_list', 'rooms': self.get_rooms()})

                elif msg_type == 'room_history_request':
                    room = (header.get('room') or 'general').strip()
                    messages = self.get_history(room, HISTORY_LIMIT)
                    send_frame(client, {'type': 'room_history', 'room': room, 'messages': messages})

                elif msg_type == 'private_chat_create':
                    name = (header.get('name') or '').strip()
                    invitees = header.get('invitees') or []
                    chat_id, status, skipped = self.try_create_private_chat(name, sender_nick, invitees)
                    send_frame(client, {
                        'type': 'private_chat_create_result', 'status': status,
                        'name': name, 'chat_id': chat_id, 'skipped': skipped,
                    })
                    if status == 'ok':
                        for nick in self.get_private_chat_members(chat_id):
                            if nick == sender_nick:
                                continue
                            member_client = self.get_client_by_nick(nick)
                            if member_client:
                                try:
                                    send_frame(member_client, {
                                        'type': 'private_chat_invited', 'chat_id': chat_id,
                                        'name': name, 'creator': sender_nick,
                                    })
                                except Exception:
                                    self.remove_client(member_client)

                elif msg_type == 'private_chat_list_request':
                    chats = self.get_private_chats_for(sender_nick)
                    send_frame(client, {'type': 'private_chat_list', 'chats': chats})

                elif msg_type == 'private_chat_history_request':
                    chat_id = (header.get('chat_id') or '').strip()
                    if not self.is_private_chat_member(chat_id, sender_nick):
                        continue
                    room = f'private:{chat_id}'
                    messages = self.get_history(room, HISTORY_LIMIT)
                    send_frame(client, {'type': 'private_chat_history', 'chat_id': chat_id, 'messages': messages})



                elif msg_type == 'private_chat_invite_member':
                    chat_id = (header.get('chat_id') or '').strip()
                    target = (header.get('target') or '').strip()
                    status = self.private_chat_add_member(chat_id, sender_nick, target)
                    send_frame(client, {
                        'type': 'private_chat_action_result',
                        'action': 'invite', 'chat_id': chat_id, 'target': target,
                        'status': status,
                    })

                elif msg_type == 'private_chat_remove_member':
                    chat_id = (header.get('chat_id') or '').strip()
                    target = (header.get('target') or '').strip()
                    status = self.private_chat_remove_member(chat_id, sender_nick, target)
                    send_frame(client, {
                        'type': 'private_chat_action_result',
                        'action': 'remove', 'chat_id': chat_id, 'target': target,
                        'status': status,
                    })

                elif msg_type == 'profile_set':
                    bio = (header.get('bio') or '').strip()[:500]
                    status = (header.get('status') or '').strip()[:80]
                    self.set_profile(sender_nick, bio, status)
                    send_frame(client, {'type': 'profile_saved', 'status': 'ok'})

                elif msg_type == 'profile_request':
                    target = (header.get('target') or sender_nick).strip()
                    profile = self.get_profile(target)
                    gifts = self.get_gifts(target)
                    send_frame(client, {
                        'type': 'profile_data', 'nickname': target,
                        'bio': profile.get('bio', ''),
                        'status': profile.get('status', ''),
                        'joined': profile.get('joined', ''),
                        'last_seen': profile.get('last_seen', ''),
                        'gifts': gifts,
                    })

                elif msg_type == 'gift_image_request':
                    gift_id = header.get('gift_id')
                    data = self.get_gift_image(gift_id) if gift_id is not None else None
                    if data:
                        send_frame(client, {'type': 'gift_image', 'gift_id': gift_id, 'size': len(data)}, data)
                    else:
                        send_frame(client, {'type': 'gift_image', 'gift_id': gift_id, 'size': 0})

                elif msg_type == 'news_list_request':
                    send_frame(client, {'type': 'news_list', 'items': self.get_news()})

                elif msg_type == 'news_image_request':
                    news_id = header.get('news_id')
                    data = self.get_news_image(news_id) if news_id is not None else None
                    if data:
                        send_frame(client, {'type': 'news_image', 'news_id': news_id, 'size': len(data)}, data)
                    else:
                        send_frame(client, {'type': 'news_image', 'news_id': news_id, 'size': 0})

                elif msg_type == 'admin_user_list_request':
                    if sender_nick not in ADMIN_NICKNAMES:
                        send_frame(client, {'type': 'admin_result', 'status': 'forbidden'})
                        continue
                    send_frame(client, {'type': 'admin_user_list', 'users': self.get_all_users_with_status()})

                # BUKKAX USER GIFTS PATCH: server
                elif msg_type == 'user_send_gift':
                    target = (header.get('target') or '').strip()
                    note = (header.get('note') or '').strip()[:300]

                    if not target or not payload:
                        send_frame(client, {
                            'type': 'user_gift_result',
                            'status': 'invalid',
                            'target': target,
                        })
                        continue

                    if target == sender_nick:
                        send_frame(client, {
                            'type': 'user_gift_result',
                            'status': 'self',
                            'target': target,
                        })
                        continue

                    if not self.nickname_exists(target):
                        send_frame(client, {
                            'type': 'user_gift_result',
                            'status': 'not_found',
                            'target': target,
                        })
                        continue

                    max_gift_size = 10 * 1024 * 1024
                    if len(payload) > max_gift_size:
                        send_frame(client, {
                            'type': 'user_gift_result',
                            'status': 'too_large',
                            'target': target,
                        })
                        continue

                    try:
                        img = Image.open(io.BytesIO(payload))
                        img.verify()
                    except Exception:
                        send_frame(client, {
                            'type': 'user_gift_result',
                            'status': 'invalid_image',
                            'target': target,
                        })
                        continue

                    gift_id = self.add_gift(
                        target,
                        sender_nick,
                        note,
                        payload
                    )

                    target_client = self.get_client_by_nick(target)
                    is_online = target_client is not None

                    if target_client:
                        try:
                            send_frame(
                                target_client,
                                {
                                    'type': 'gift_received',
                                    'gift_id': gift_id,
                                    'from': sender_nick,
                                    'note': note,
                                    'size': len(payload),
                                },
                                payload
                            )
                        except Exception:
                            self.remove_client(target_client)
                            is_online = False

                    send_frame(client, {
                        'type': 'user_gift_result',
                        'status': 'ok',
                        'target': target,
                        'gift_id': gift_id,
                        'online': is_online,
                    })

                    print(f"🎁 {sender_nick} отправил подарок игроку {target}")

                elif msg_type == 'admin_send_gift':
                    if sender_nick not in ADMIN_NICKNAMES:
                        send_frame(client, {'type': 'admin_result', 'status': 'forbidden'})
                        continue
                    target = (header.get('target') or '').strip()
                    note = (header.get('note') or '').strip()
                    if not target or not payload:
                        send_frame(client, {'type': 'admin_result', 'status': 'invalid'})
                        continue
                    gift_id = self.add_gift(target, sender_nick, note, payload)
                    target_client = self.get_client_by_nick(target)
                    if target_client:
                        try:
                            send_frame(
                                target_client,
                                {'type': 'gift_received', 'gift_id': gift_id, 'from': sender_nick,
                                 'note': note, 'size': len(payload)},
                                payload
                            )
                        except Exception:
                            self.remove_client(target_client)
                    print(f"🎁 {sender_nick} отправил подарок игроку {target}")
                    send_frame(client, {'type': 'admin_result', 'status': 'ok'})

                # ---------- ИЗМЕНЁННАЯ КОМАНДА ADMIN_KICK (БАН) ----------
                elif msg_type == 'admin_kick':
                    if sender_nick not in ADMIN_NICKNAMES:
                        send_frame(client, {'type': 'admin_result', 'status': 'forbidden'})
                        continue

                    target = (header.get('target') or '').strip()
                    if not target:
                        send_frame(client, {'type': 'admin_result', 'status': 'invalid'})
                        continue

                    # BAN: получаем device_id пользователя (если есть в БД)
                    device_id = None
                    with self.db_lock:
                        cur = self.db.execute('SELECT device_id FROM users WHERE nickname = ?', (target,))
                        row = cur.fetchone()
                        if row:
                            device_id = row[0]

                    # Баним пользователя (добавляем в banned, удаляем из всех таблиц)
                    self.ban_user(target, device_id or '', sender_nick)

                    # Если пользователь онлайн – принудительно отключаем
                    target_client = self.get_client_by_nick(target)
                    if target_client:
                        try:
                            send_frame(target_client, {'type': 'kicked', 'by': sender_nick})
                        except Exception:
                            pass
                        self.remove_client(target_client)

                    print(f"👢 {sender_nick} забанил(а) {target}")
                    send_frame(client, {'type': 'admin_result', 'status': 'ok'})

                elif msg_type == 'admin_post_news':
                    if sender_nick not in ADMIN_NICKNAMES:
                        send_frame(client, {'type': 'admin_result', 'status': 'forbidden'})
                        continue
                    text = (header.get('text') or '').strip()
                    if not text and not payload:
                        send_frame(client, {'type': 'admin_result', 'status': 'invalid'})
                        continue
                    news_id = self.add_news(sender_nick, text, payload if payload else None)
                    now = datetime.datetime.now().isoformat(timespec='seconds')
                    self.broadcast_frame({
                        'type': 'news_posted', 'id': news_id, 'author': sender_nick,
                        'text': text, 'timestamp': now, 'has_image': bool(payload),
                    })
                    print(f"📰 {sender_nick} опубликовал(а) новость")
                    send_frame(client, {'type': 'admin_result', 'status': 'ok'})


                elif msg_type == 'chess_invite':
                    target = (header.get('target') or '').strip()
                    game_id = (header.get('game_id') or uuid.uuid4().hex[:16]).strip()
                    if not target:
                        send_frame(client, {'type': 'chess_invite_result', 'status': 'invalid', 'target': target})
                        continue
                    if target == sender_nick:
                        send_frame(client, {'type': 'chess_invite_result', 'status': 'self', 'target': target})
                        continue
                    target_client = self.get_client_by_nick(target)
                    if not target_client:
                        send_frame(client, {'type': 'chess_invite_result', 'status': 'offline', 'target': target})
                        continue
                    try:
                        import random as _bukkax_chess_random
                        players = [sender_nick, target]
                        _bukkax_chess_random.shuffle(players)
                        white_nick = players[0]
                        black_nick = players[1]
                        send_frame(target_client, {
                            'type': 'chess_invite', 'from': sender_nick, 'game_id': game_id,
                            'white': white_nick, 'black': black_nick,
                        })
                        send_frame(client, {
                            'type': 'chess_invite_result', 'status': 'sent',
                            'target': target, 'game_id': game_id,
                            'white': white_nick, 'black': black_nick,
                        })
                        print(f"♟ {sender_nick} приглашает {target} в шахматы. Белые: {white_nick}, чёрные: {black_nick}")
                    except Exception:
                        self.remove_client(target_client)
                        send_frame(client, {'type': 'chess_invite_result', 'status': 'offline', 'target': target})

                elif msg_type == 'chess_accept':
                    target = (header.get('target') or '').strip()
                    game_id = (header.get('game_id') or '').strip()
                    accepted = bool(header.get('accepted'))
                    white_nick = (header.get('white') or '').strip()
                    black_nick = (header.get('black') or '').strip()
                    target_client = self.get_client_by_nick(target)
                    if not target_client:
                        continue
                    try:
                        send_frame(target_client, {
                            'type': 'chess_accept', 'from': sender_nick,
                            'game_id': game_id, 'accepted': accepted,
                            'white': white_nick, 'black': black_nick,
                        })
                        print(f"♟ {sender_nick} {'принял' if accepted else 'отклонил'} шахматы от {target}")
                    except Exception:
                        self.remove_client(target_client)

                elif msg_type in ('chess_move', 'chess_restart', 'chess_resign', 'chess_close'):
                    target = (header.get('target') or '').strip()
                    target_client = self.get_client_by_nick(target)
                    if not target_client:
                        continue
                    relay = dict(header)
                    relay['from'] = sender_nick
                    relay.pop('target', None)
                    try:
                        send_frame(target_client, relay)
                    except Exception:
                        self.remove_client(target_client)

                # ---------- BUKKAX BUILDER SYNC ----------
                elif msg_type == 'builder_config_request':
                    data = _bukkax_builder_load_server_config()

                    if data is None:
                        send_frame(
                            client,
                            {
                                'type': 'builder_config_missing',
                            }
                        )
                    else:
                        send_frame(
                            client,
                            {
                                'type': 'builder_config_data',
                                'size': len(data),
                            },
                            data,
                        )

                elif msg_type == 'builder_config_publish':
                    if sender_nick not in ADMIN_NICKNAMES:
                        send_frame(
                            client,
                            {
                                'type': 'builder_config_publish_result',
                                'status': 'forbidden',
                            }
                        )
                        continue

                    clean, status = (
                        _bukkax_builder_sanitize_payload(
                            payload
                        )
                    )

                    if (
                        status != 'ok'
                        or clean is None
                    ):
                        send_frame(
                            client,
                            {
                                'type': 'builder_config_publish_result',
                                'status': status,
                            }
                        )
                        continue

                    try:
                        _bukkax_builder_save_server_config(
                            clean
                        )
                    except Exception as e:
                        print(
                            'Builder config save error:',
                            e
                        )
                        send_frame(
                            client,
                            {
                                'type': 'builder_config_publish_result',
                                'status': 'save_error',
                            }
                        )
                        continue

                    self.broadcast_frame(
                        {
                            'type': 'builder_config_updated',
                            'from': sender_nick,
                            'size': len(clean),
                        },
                        clean,
                    )

                    send_frame(
                        client,
                        {
                            'type': 'builder_config_publish_result',
                            'status': 'ok',
                        }
                    )

                    print(
                        f'🛠 {sender_nick} опубликовал '
                        f'Developer Builder config '
                        f'({len(clean)} байт)'
                    )

                # ---------- BUKKAX SCREEN SHARE STATE ----------
                elif msg_type == 'screen_share_state':
                    call_id = (
                        header.get('call_id')
                        or ''
                    ).strip()

                    with self.calls_lock:
                        call = self.active_calls.get(
                            call_id
                        )

                        if not call:
                            continue

                        if sender_nick not in (
                            call.get('nick_a'),
                            call.get('nick_b'),
                        ):
                            continue

                        other_nick = (
                            call.get('nick_b')
                            if call.get('nick_a')
                            == sender_nick
                            else call.get('nick_a')
                        )

                    other_client = (
                        self.get_client_by_nick(
                            other_nick
                        )
                    )

                    if other_client:
                        try:
                            send_frame(
                                other_client,
                                {
                                    'type': 'screen_share_state',
                                    'call_id': call_id,
                                    'from': sender_nick,
                                    'active': bool(
                                        header.get(
                                            'active'
                                        )
                                    ),
                                    'quality': str(
                                        header.get(
                                            'quality'
                                        )
                                        or ''
                                    )[:32],
                                    'fps': int(
                                        header.get(
                                            'fps'
                                        )
                                        or 0
                                    ),
                                }
                            )
                        except Exception:
                            self.remove_client(
                                other_client
                            )

                # ---------- BUKKAX SCREEN SHARE TCP V2 ----------
                elif msg_type == 'screen_share_frame':
                    call_id = (
                        header.get('call_id')
                        or ''
                    ).strip()

                    if (
                        not payload
                        or len(payload) > 1024 * 1024
                    ):
                        continue

                    with self.calls_lock:
                        call = self.active_calls.get(
                            call_id
                        )

                        if not call:
                            continue

                        if sender_nick not in (
                            call.get('nick_a'),
                            call.get('nick_b'),
                        ):
                            continue

                        other_nick = (
                            call.get('nick_b')
                            if call.get('nick_a')
                            == sender_nick
                            else call.get('nick_a')
                        )

                    other_client = (
                        self.get_client_by_nick(
                            other_nick
                        )
                    )

                    if other_client:
                        try:
                            send_frame(
                                other_client,
                                {
                                    'type': 'screen_share_frame',
                                    'call_id': call_id,
                                    'from': sender_nick,
                                    'size': len(payload),
                                    'width': int(
                                        header.get('width')
                                        or 0
                                    ),
                                    'height': int(
                                        header.get('height')
                                        or 0
                                    ),
                                    'fps': int(
                                        header.get('fps')
                                        or 0
                                    ),
                                },
                                payload,
                            )
                        except Exception:
                            self.remove_client(
                                other_client
                            )

                # ---------- BUKKAX CALL QUALITY CAPABILITY V1 ----------
                elif msg_type == 'call_quality_capability':
                    call_id = (
                        header.get('call_id')
                        or ''
                    ).strip()

                    with self.calls_lock:
                        call = self.active_calls.get(
                            call_id
                        )

                        if not call:
                            continue

                        if sender_nick not in (
                            call.get('nick_a'),
                            call.get('nick_b'),
                        ):
                            continue

                        other_nick = (
                            call.get('nick_b')
                            if call.get('nick_a')
                            == sender_nick
                            else call.get('nick_a')
                        )

                    other_client = (
                        self.get_client_by_nick(
                            other_nick
                        )
                    )

                    if other_client:
                        try:
                            send_frame(
                                other_client,
                                {
                                    'type': 'call_quality_capability',
                                    'call_id': call_id,
                                    'from': sender_nick,
                                    'version': 1,
                                }
                            )
                        except Exception:
                            self.remove_client(
                                other_client
                            )

                elif msg_type == 'call_offer':
                    target = (header.get('target') or '').strip()
                    with_video = bool(header.get('video'))
                    target_client = self.get_client_by_nick(target)
                    if not target_client:
                        send_frame(client, {'type': 'call_result', 'status': 'offline', 'target': target})
                        continue
                    if target == sender_nick:
                        send_frame(client, {'type': 'call_result', 'status': 'self'})
                        continue
                    call_id = uuid.uuid4().hex[:16]
                    with self.calls_lock:
                        self.pending_calls[call_id] = {
                            'caller': sender_nick, 'callee': target, 'video': with_video,
                        }
                    try:
                        send_frame(target_client, {
                            'type': 'call_offer', 'call_id': call_id,
                            'from': sender_nick, 'video': with_video,
                        })
                    except Exception:
                        self.remove_client(target_client)
                        send_frame(client, {'type': 'call_result', 'status': 'offline', 'target': target})
                        continue
                    send_frame(client, {'type': 'call_ringing', 'call_id': call_id, 'target': target})
                    print(f"📞 {sender_nick} звонит {target} ({'видео' if with_video else 'голос'})")

                elif msg_type == 'call_answer':
                    call_id = (header.get('call_id') or '').strip()
                    accepted = bool(header.get('accepted'))
                    with self.calls_lock:
                        pending = self.pending_calls.pop(call_id, None)
                    if not pending or pending['callee'] != sender_nick:
                        continue
                    caller_client = self.get_client_by_nick(pending['caller'])
                    if accepted:
                        if not caller_client:
                            continue
                        with self.calls_lock:
                            self.active_calls[call_id] = {
                                'nick_a': pending['caller'], 'nick_b': pending['callee'],
                                'video': pending.get('video', False),
                                'audio_addr_a': None, 'audio_addr_b': None,
                                'video_addr_a': None, 'video_addr_b': None,
                            }
                        try:
                            send_frame(caller_client, {
                                'type': 'call_started', 'call_id': call_id, 'role': 0,
                                'video': pending.get('video', False),
                            })
                        except Exception:
                            pass
                        send_frame(client, {
                            'type': 'call_started', 'call_id': call_id, 'role': 1,
                            'video': pending.get('video', False),
                        })
                        print(f"📞 Звонок {pending['caller']} <-> {pending['callee']} начался")
                    else:
                        if caller_client:
                            try:
                                send_frame(caller_client, {'type': 'call_declined', 'call_id': call_id})
                            except Exception:
                                pass
                        print(f"📴 {sender_nick} отклонил(а) звонок от {pending['caller']}")

                elif msg_type == 'call_end':
                    call_id = (header.get('call_id') or '').strip()
                    with self.calls_lock:
                        call = self.active_calls.pop(call_id, None)
                        pending = self.pending_calls.pop(call_id, None)
                    other_nick = None
                    if call:
                        other_nick = call['nick_b'] if call['nick_a'] == sender_nick else call['nick_a']
                    elif pending:
                        other_nick = pending['callee'] if pending['caller'] == sender_nick else pending['caller']
                    if other_nick:
                        other_client = self.get_client_by_nick(other_nick)
                        if other_client:
                            try:
                                send_frame(other_client, {'type': 'call_ended', 'call_id': call_id})
                            except Exception:
                                pass
                    print(f"📴 {sender_nick} завершил(а) звонок {call_id}")

                elif msg_type == 'group_call_start':
                    chat_id = (header.get('chat_id') or '').strip()
                    if not self.is_private_chat_member(chat_id, sender_nick):
                        continue
                    call_id = uuid.uuid4().hex[:16]
                    with self.calls_lock:
                        self.active_group_calls[call_id] = {
                            'chat_id': chat_id,
                            'members': {0: sender_nick},
                            'next_member_id': 1,
                            'audio_addrs': {}, 'video_addrs': {},
                        }
                    send_frame(client, {
                        'type': 'group_call_joined', 'call_id': call_id, 'member_id': 0,
                        'members': {0: sender_nick},
                    })
                    for nick in self.get_private_chat_members(chat_id):
                        if nick == sender_nick:
                            continue
                        member_client = self.get_client_by_nick(nick)
                        if member_client:
                            try:
                                send_frame(member_client, {
                                    'type': 'group_call_invite', 'call_id': call_id,
                                    'chat_id': chat_id, 'from': sender_nick,
                                })
                            except Exception:
                                pass
                    print(f"👥 {sender_nick} начал(а) групповой звонок в приватной беседе")

                elif msg_type == 'group_call_join':
                    call_id = (header.get('call_id') or '').strip()
                    with self.calls_lock:
                        group_call = self.active_group_calls.get(call_id)
                        if not group_call:
                            send_frame(client, {'type': 'group_call_result', 'status': 'not_found', 'call_id': call_id})
                            continue
                        if not self.is_private_chat_member(group_call['chat_id'], sender_nick):
                            continue
                        if sender_nick in group_call['members'].values():
                            continue
                        member_id = group_call['next_member_id']
                        group_call['next_member_id'] += 1
                        group_call['members'][member_id] = sender_nick
                        existing_members = dict(group_call['members'])
                    send_frame(client, {
                        'type': 'group_call_joined', 'call_id': call_id, 'member_id': member_id,
                        'members': existing_members,
                    })
                    for mid, nick in existing_members.items():
                        if nick == sender_nick:
                            continue
                        member_client = self.get_client_by_nick(nick)
                        if member_client:
                            try:
                                send_frame(member_client, {
                                    'type': 'group_call_member_joined', 'call_id': call_id,
                                    'member_id': member_id, 'nick': sender_nick,
                                })
                            except Exception:
                                pass
                    print(f"👥 {sender_nick} присоединился(-лась) к групповому звонку")

                elif msg_type == 'group_call_leave':
                    call_id = (header.get('call_id') or '').strip()
                    leaving_id = None
                    remaining = []
                    with self.calls_lock:
                        group_call = self.active_group_calls.get(call_id)
                        if group_call:
                            for mid, nick in list(group_call['members'].items()):
                                if nick == sender_nick:
                                    leaving_id = mid
                                    del group_call['members'][mid]
                                    group_call.get('audio_addrs', {}).pop(mid, None)
                                    group_call.get('video_addrs', {}).pop(mid, None)
                                    break
                            remaining = list(group_call['members'].values())
                            if not remaining:
                                del self.active_group_calls[call_id]
                    if leaving_id is not None:
                        for nick in remaining:
                            member_client = self.get_client_by_nick(nick)
                            if member_client:
                                try:
                                    send_frame(member_client, {
                                        'type': 'group_call_member_left',
                                        'call_id': call_id, 'member_id': leaving_id,
                                    })
                                except Exception:
                                    pass
                    print(f"👋 {sender_nick} покинул(а) групповой звонок")

                elif msg_type == 'avatar_set':
                    self.save_avatar(sender_nick, payload)
                    self.broadcast_frame({'type': 'avatar_changed', 'nick': sender_nick}, sender_client=client)

                elif msg_type == 'avatar_request':
                    target = (header.get('target') or '').strip()
                    data = self.get_avatar(target)
                    if data:
                        send_frame(client, {'type': 'avatar_data', 'nick': target, 'size': len(data)}, data)
                    else:
                        send_frame(client, {'type': 'avatar_data', 'nick': target, 'size': 0})

            except Exception as e:
                print(f"Ошибка при обработке клиента: {e}")
                self.remove_client(client)
                break

    def receive(self):
        while True:
            try:
                client, address = self.server.accept()
                print(f"🔌 Новое подключение: {str(address)}")

                nickname = self.perform_handshake(client, address)
                if nickname is None:
                    client.close()
                    continue

                self.nicknames.append(nickname)
                self.clients.append(client)

                print(f"👤 Никнейм: {nickname} ({address[0]})")
                print(f"👥 Всего пользователей: {len(self.clients)}")

                try:
                    history = self.get_history('general', HISTORY_LIMIT)
                    send_frame(client, {'type': 'history', 'messages': history})
                except Exception:
                    pass

                self.broadcast_system(f'✅ {nickname} присоединился к чату!')

                thread = threading.Thread(target=self.handle_client, args=(client,))
                thread.daemon = True
                thread.start()

            except Exception as e:
                print(f"Ошибка при принятии подключения: {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("🚀 ЗАПУСК СЕРВЕРА ЧАТА")
    print("=" * 50)
    print(f"📌 Версия сервера: {CURRENT_VERSION}")

    server = ChatServer()
    start_update_server()

    try:
        server.receive()
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен пользователем")
        for client in server.clients:
            client.close()
        server.server.close()
        sys.exit(0)