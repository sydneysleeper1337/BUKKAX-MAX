import os
import re
import sys
import sqlite3
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QSplitter, QMessageBox,
)
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

APP_NAME = "BUKKAX MUSIC"
DB_NAME = "bukkax_music.db"

YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be",
}
VK_HOSTS = {"vk.com", "www.vk.com", "m.vk.com", "vk.ru", "www.vk.ru"}

YANDEX_HOSTS = {"music.yandex.ru","music.yandex.com"}


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


DB_PATH = os.path.join(app_dir(), DB_NAME)


def normalize_url(text):
    text = (text or "").strip()
    if not text:
        return ""
    if not re.match(r"^https?://", text, re.I):
        text = "https://" + text
    return text


def detect_service(url):
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return None

    if host in YOUTUBE_HOSTS or host.endswith(".youtube.com"):
        return "youtube"
    if host in VK_HOSTS or host.endswith(".vk.com"):
        return "vk"
    if host in YANDEX_HOSTS or host.endswith(".yandex.com","yandex.ru"):
        return "yandex"
    return None


def extract_youtube_video_id(url):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = parsed.path.strip("/")

        if host == "youtu.be":
            return path.split("/")[0] if path else None

        if host.endswith("youtube.com"):
            query = parse_qs(parsed.query)
            if query.get("v"):
                return query["v"][0]

            parts = path.split("/")
            if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
                return parts[1]
    except Exception:
        pass
    return None


class MusicDatabase:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                played_at TEXT NOT NULL
            )
            """
        )
        self.db.commit()

    def add(self, service, url):
        self.db.execute("DELETE FROM history WHERE url = ?", (url,))
        self.db.execute(
            "INSERT INTO history(service,url,title,played_at) VALUES(?,?,?,?)",
            (service, url, "", datetime.now().isoformat(timespec="seconds")),
        )
        self.db.commit()

    def update_title(self, url, title):
        if title:
            self.db.execute("UPDATE history SET title=? WHERE url=?", (title, url))
            self.db.commit()

    def items(self, limit=100):
        cur = self.db.execute(
            "SELECT service,url,title,played_at FROM history ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    def clear(self):
        self.db.execute("DELETE FROM history")
        self.db.commit()

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass


class BrowserPage(QWebEnginePage):
    pass


class MusicWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(640, 280)
        self.setMinimumSize(640, 280)

        self.db = MusicDatabase(DB_PATH)
        self.current_source_url = ""
        self.current_service = ""

        self._build_ui()
        self._setup_web()
        self._setup_shortcuts()
        self._load_history()
        self.status_label.setText("Вставь ссылку YouTube или VK и нажми «Открыть»")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("🎵 BUKKAX MUSIC")
        title.setObjectName("appTitle")
        root.addWidget(title)

        bar = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Вставь ссылку YouTube / YouTube Music / VK / Yandex Music...")
        self.url_edit.returnPressed.connect(self.open_from_input)
        bar.addWidget(self.url_edit, 1)

        self.open_btn = QPushButton("▶ Открыть")
        self.open_btn.clicked.connect(self.open_from_input)
        bar.addWidget(self.open_btn)

        self.back_btn = QPushButton("←")
        self.back_btn.setFixedWidth(44)
        bar.addWidget(self.back_btn)

        self.reload_btn = QPushButton("↻")
        self.reload_btn.setFixedWidth(44)
        bar.addWidget(self.reload_btn)
        root.addLayout(bar)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        root.addWidget(self.status_label)

        splitter = QSplitter(Qt.Horizontal)

        self.web = QWebEngineView()
        splitter.addWidget(self.web)

        history_wrap = QWidget()
        history_wrap.setMinimumWidth(260)
        history_wrap.setMaximumWidth(380)
        history_layout = QVBoxLayout(history_wrap)
        history_layout.setContentsMargins(0, 0, 0, 0)

        hist_title = QLabel("🕘 История")
        hist_title.setObjectName("historyTitle")
        history_layout.addWidget(hist_title)

        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(self._open_history_item)
        history_layout.addWidget(self.history_list, 1)

        clear_btn = QPushButton("Очистить историю")
        clear_btn.setObjectName("secondary")
        clear_btn.clicked.connect(self._clear_history)
        history_layout.addWidget(clear_btn)

        splitter.addWidget(history_wrap)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([900, 280])
        root.addWidget(splitter, 1)

        self.setStyleSheet("""
            QMainWindow, QWidget { background:#0f1117; color:#e8eaf0; font-family:Segoe UI; font-size:10.5pt; }
            QLabel#appTitle { font-size:19pt; font-weight:800; color:white; padding:2px 0 5px 0; }
            QLabel#statusLabel { color:#aab1c5; padding:2px 4px; }
            QLabel#historyTitle { font-size:12pt; font-weight:700; padding:4px; }
            QLineEdit { background:#171a23; border:1px solid #2a3040; border-radius:10px; padding:10px 12px; color:white; }
            QLineEdit:focus { border:1px solid #4b8cff; }
            QPushButton { background:#3b82f6; color:white; border:none; border-radius:9px; padding:9px 14px; font-weight:700; }
            QPushButton:hover { background:#4b8cff; }
            QPushButton:pressed { background:#2d6ed4; }
            QPushButton#secondary { background:#252a36; }
            QPushButton#secondary:hover { background:#303747; }
            QListWidget { background:#151820; border:1px solid #252a36; border-radius:10px; padding:4px; outline:none; }
            QListWidget::item { padding:9px 7px; border-radius:7px; }
            QListWidget::item:selected { background:#273a5e; color:white; }
            QSplitter::handle { background:#20242f; width:4px; }
        """)

    def _setup_web(self):
        profile_dir = os.path.join(app_dir(), "web_profile")
        cache_dir = os.path.join(profile_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)

        self.profile = QWebEngineProfile("BukkaxMusicProfile", self)
        self.profile.setHttpAcceptLanguage(
            "ru-RU,ru;q=0.9,en;q=0.8")
        self.profile.setPersistentStoragePath(profile_dir)
        self.profile.setCachePath(cache_dir)

        try:
            self.profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
            )
        except Exception:
            pass

        self.page = BrowserPage(self.profile, self.web)
        self.web.setPage(self.page)

        settings = self.web.settings()
        try:
            settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        except Exception:
            pass
        try:
            settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        except Exception:
            pass

        self.web.titleChanged.connect(self._on_title_changed)
        self.web.loadStarted.connect(lambda: self.status_label.setText("Загрузка..."))
        self.web.loadFinished.connect(self._on_load_finished)
        self.back_btn.clicked.connect(self.web.back)
        self.reload_btn.clicked.connect(self.web.reload)

        self.web.setHtml("""
        <!doctype html><html><head><meta charset='utf-8'>
        <style>html,body{margin:0;height:100%;background:#11141b;color:#d8deed;font-family:Segoe UI,Arial}
        .c{height:100%;display:flex;align-items:center;justify-content:center;text-align:center}.b{max-width:540px;padding:34px}
        h1{color:white}p{color:#9da7bd;line-height:1.6}</style></head>
        <body><div class='c'><div class='b'><h1>🎵 BUKKAX MUSIC</h1>
        <p>Вставь сверху ссылку на YouTube, YouTube Music или VK.</p></div></div></body></html>
        """)

    def _setup_shortcuts(self):
        action = QAction(self)
        action.setShortcut(QKeySequence("Ctrl+L"))
        action.triggered.connect(self._focus_url)
        self.addAction(action)

    def _focus_url(self):
        self.url_edit.setFocus()
        self.url_edit.selectAll()

    def open_from_input(self):
        url = normalize_url(self.url_edit.text())
        if url:
            self.open_url(url)

    def open_url(self, url):
        service = detect_service(url)
        if service is None:
            QMessageBox.information(self, "Неизвестная ссылка", "Пока поддерживаются только ссылки YouTube,VK, Yandex.")
            return

        self.current_source_url = url
        self.current_service = service
        self.url_edit.setText(url)
        self.db.add(service, url)
        self._load_history()

        if service == "youtube":
            self._open_youtube(url)
        if service == "vk":
            self._open_vk(url)
        else:
            self._open_yandex(url)

    def _open_youtube(self, url):
        video_id = extract_youtube_video_id(url)
        if video_id:
            embed = f"https://www.youtube.com/embed/{video_id}?autoplay=1&rel=0&playsinline=1"
            self.status_label.setText("YouTube — открываю встроенный плеер")
            self.web.setUrl(QUrl(embed))
        else:
            self.status_label.setText("YouTube — открываю страницу")
            self.web.setUrl(QUrl(url))

    def _open_vk(self, url):
        self.status_label.setText("VK — открываю страницу. Если потребуется, войди в аккаунт один раз. Не бойся твои данные видны только тебе")
        self.web.setUrl(QUrl(url))

    def _open_yandex(self, url):
        self.status_label.setText("Открываю Yandex music, в первый раз может потребоваться авторизация")
        self.web.setUrl(QUrl(url))

    def _on_title_changed(self, title):
        title = (title or "").strip()
        if not title:
            return
        if self.current_source_url:
            self.db.update_title(self.current_source_url, title)
            self._load_history()
        if title.lower() not in {"youtube", "vk"}:
            self.setWindowTitle(f"{title} — {APP_NAME}")

    def _on_load_finished(self, ok):
        if not ok:
            self.status_label.setText("Не удалось загрузить страницу")
            return
        if self.current_service == "youtube":
            self.status_label.setText("▶ YouTube готов")
        elif self.current_service == "vk":
            self.status_label.setText("▶ VK готов")
        else:
            self.status_label.setText("Готово")

    def _load_history(self):
        self.history_list.clear()
        for service, url, title, played_at in self.db.items():
            prefix = "▶" if service == "youtube" else "VK"
            text = f"{prefix} {title or url}"
            item = QListWidgetItem(text)
            item.setToolTip(url)
            item.setData(Qt.UserRole, url)
            self.history_list.addItem(item)

    def _open_history_item(self, item):
        url = item.data(Qt.UserRole)
        if url:
            self.open_url(url)

    def _clear_history(self):
        if QMessageBox.question(self, "История", "Очистить всю историю?") != QMessageBox.Yes:
            return
        self.db.clear()
        self._load_history()

    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MusicWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()