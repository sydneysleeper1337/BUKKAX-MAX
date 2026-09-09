"""
BUKKAX — клиент на PySide6.

Расширенная версия с микшером громкости, шумоподавлением (pyrnnoise) и настройками аудио.
"""

import os
import sys
import json
import uuid
import html
import struct
import shutil
import time
import array
import subprocess
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

from PySide6.QtCore import Qt, QObject, QThread, Signal, QUrl, QTimer, QPoint, QBuffer, QIODevice, QEvent
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QKeySequence, QShortcut, QImage
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextBrowser, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QInputDialog, QDialog, QColorDialog, QMenu,
    QSlider, QCheckBox, QComboBox, QGroupBox, QDialogButtonBox, QFrame,
    QProgressDialog,
)
from PySide6.QtNetwork import QUdpSocket, QHostAddress
from PySide6.QtMultimedia import (
    QMediaPlayer, QAudioOutput, QMediaCaptureSession, QMediaRecorder,
    QCamera, QAudioInput, QMediaFormat, QMediaDevices,
    QAudioFormat, QAudioSource, QAudioSink, QVideoSink,
)
from PySide6.QtMultimediaWidgets import QVideoWidget

from protocol import send_frame, recv_frame
from bukkax_chess_qt import ChessDialog, ChessBotDialog
from bukkax_chess_qt import chess_info, chess_warning, chess_critical, chess_question, chess_get_item, chess_get_text

try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# NEW: Попытка импорта pyrnnoise для шумоподавления
try:
    from pyrnnoise import RNNoise
    import numpy as np
    RNNOISE_AVAILABLE = True
except ImportError:
    RNNOISE_AVAILABLE = False


# ---------- Функция получения версии из файла ----------
def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_path(relative_path):
    """Путь к ресурсу и при обычном запуске, и внутри PyInstaller --onefile."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


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

# ---------- Настройки/константы ----------
SERVER_IP = os.environ.get("BUKKAX_SERVER_IP", "127.0.0.1")
PORT = 55555
CURRENT_VERSION = get_current_version()
UPDATE_HTTP_PORT = 55556
VOICE_UDP_PORT = 55557
VIDEO_UDP_PORT = 55558
UPDATE_VERSION_URL = f'http://{SERVER_IP}:{UPDATE_HTTP_PORT}/version.txt'
UPDATE_EXE_URL = f'http://{SERVER_IP}:{UPDATE_HTTP_PORT}/Bukkax.exe'

ADMIN_NICKNAME = 'Чак Чакич'

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif', '.tiff')
VIDEO_EXTENSIONS = ('.mp4', '.avi', '.mov', '.mkv', '.webm', '.wmv')
AUDIO_EXTENSIONS = ('.m4a', '.mp3', '.wav', '.ogg', '.aac')


def parse_duration_from_filename(filename):
    import re
    match = re.search(r'_(\d+)s_', filename)
    return int(match.group(1)) if match else 0


def format_duration(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"

EMOJI_LIST = [
    "😀", "😁", "😂", "🤣", "😊", "😍", "😘", "😜", "🤔", "😎",
    "😢", "😭", "😡", "🥳", "👍", "👎", "👏", "🙏", "💪", "🔥",
    "❤️", "💔", "✨", "🎉", "👀", "🤝", "🙌", "😴", "🤯", "😅",
    "🥺", "😏", "😇", "👋", "🤗", "💯", "⚡", "☕", "🎮", "🎵",
]

DEVICE_ID_PATH = os.path.join(get_base_dir(), 'device_id.txt')
NICKNAME_PATH = os.path.join(get_base_dir(), 'nickname.txt')


def get_device_id():
    if os.path.exists(DEVICE_ID_PATH):
        try:
            with open(DEVICE_ID_PATH, 'r') as f:
                existing = f.read().strip()
                if existing:
                    return existing
        except Exception:
            pass
    new_id = uuid.uuid4().hex
    try:
        with open(DEVICE_ID_PATH, 'w') as f:
            f.write(new_id)
    except Exception:
        pass
    return new_id


def get_saved_nickname():
    if os.path.exists(NICKNAME_PATH):
        try:
            with open(NICKNAME_PATH, 'r', encoding='utf-8') as f:
                nick = f.read().strip()
                return nick or None
        except Exception:
            return None
    return None


def save_nickname(nickname):
    try:
        with open(NICKNAME_PATH, 'w', encoding='utf-8') as f:
            f.write(nickname)
    except Exception:
        pass


def open_file(path):
    try:
        if sys.platform.startswith('win'):
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception as e:
        QMessageBox.warning(None, "Ошибка", f"Не удалось открыть файл: {e}")


def short_time(timestamp):
    if not timestamp or len(timestamp) < 16:
        return ''
    return timestamp[11:16]


def short_date(timestamp):
    if not timestamp or len(timestamp) < 10:
        return timestamp or ''
    return timestamp[:10]


def parse_version(v):
    try:
        return tuple(int(x) for x in v.strip().split('.'))
    except Exception:
        return (0,)


def check_for_update():
    try:
        import urllib.request
        with urllib.request.urlopen(UPDATE_VERSION_URL, timeout=3) as resp:
            latest = resp.read().decode('utf-8').strip()
        if parse_version(latest) > parse_version(CURRENT_VERSION):
            return latest
    except Exception:
        pass
    return None


# ---------- Сетевой воркер ----------
class NetworkWorker(QObject):
    frame_received = Signal(dict, bytes)
    disconnected = Signal(str)

    def __init__(self, sock):
        super().__init__()
        self.sock = sock
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            try:
                header, payload = recv_frame(self.sock)
            except Exception:
                if self._running:
                    self.disconnected.emit("❌ Соединение с сервером потеряно")
                break
            self.frame_received.emit(header, payload)


class UpdateCheckWorker(QObject):
    update_available = Signal(str)

    def run(self):
        latest = check_for_update()
        if latest:
            self.update_available.emit(latest)



class UpdateDownloadWorker(QObject):
    progress = Signal(int, int)  # downloaded, total
    finished = Signal(str, str, str)  # new_exe, new_version_file, latest_version
    failed = Signal(str)

    def __init__(self, latest_version):
        super().__init__()
        self.latest_version = str(latest_version or '').strip()

    def run(self):
        try:
            import urllib.request

            if not self.latest_version:
                raise RuntimeError('Не указан номер новой версии.')

            current_exe = sys.executable
            base_dir = get_base_dir()
            part_exe = current_exe + '.download'
            new_exe = current_exe + '.new'
            new_version_file = os.path.join(base_dir, 'version.txt.new')

            for path in (part_exe, new_exe, new_version_file):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass

            # Чистим следы старой версии автообновления, которая могла запускать Python у пользователя.
            for old_name in ('_update.py', '_bukkax_update.py', 'update_runner.py', '_update_runner.py'):
                try:
                    old_path = os.path.join(base_dir, old_name)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception:
                    pass

            req = urllib.request.Request(
                UPDATE_EXE_URL,
                headers={'User-Agent': 'BUKKAX-Updater'}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                total = int(resp.headers.get('Content-Length') or 0)
                downloaded = 0
                with open(part_exe, 'wb') as f:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(downloaded, total)

            if not os.path.exists(part_exe):
                raise RuntimeError('Файл обновления не скачался.')

            size = os.path.getsize(part_exe)
            if size < 256 * 1024:
                raise RuntimeError(
                    f'Скачанный exe слишком маленький: {size} байт. '
                    'Проверь updates/Bukkax.exe на сервере.'
                )

            os.replace(part_exe, new_exe)
            with open(new_version_file, 'w', encoding='utf-8') as f:
                f.write(self.latest_version)

            self.finished.emit(new_exe, new_version_file, self.latest_version)
        except Exception as e:
            self.failed.emit(str(e))


# ---------- Диалог видеоплеера ----------
class VideoPlayerDialog(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(path))
        self.resize(640, 420)

        layout = QVBoxLayout(self)
        video_widget = QVideoWidget()
        layout.addWidget(video_widget)

        controls = QHBoxLayout()
        self.play_btn = QPushButton("⏸ Пауза")
        self.play_btn.clicked.connect(self._toggle)
        controls.addWidget(self.play_btn)

        # NEW: слайдер громкости для видео-плеера
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.valueChanged.connect(self._set_volume)
        controls.addWidget(QLabel("Громкость"))
        controls.addWidget(self.volume_slider)

        layout.addLayout(controls)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(video_widget)
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()
        self._set_volume(80)

    def _toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_btn.setText("⏵ Играть")
        else:
            self.player.play()
            self.play_btn.setText("⏸ Пауза")

    def _set_volume(self, val):
        self.audio_output.setVolume(val / 100.0)

    def closeEvent(self, event):
        self.player.stop()
        super().closeEvent(event)


class AudioPlayerDialog(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎤 Голосовое сообщение")
        self.resize(320, 150)

        layout = QVBoxLayout(self)
        self.play_btn = QPushButton("⏵ Играть")
        self.play_btn.clicked.connect(self._toggle)
        layout.addWidget(self.play_btn)

        # NEW: слайдер громкости
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.valueChanged.connect(self._set_volume)
        layout.addWidget(QLabel("Громкость"))
        layout.addWidget(self.volume_slider)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.play()
        self._set_volume(80)

    def _toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_btn.setText("⏵ Играть")
        else:
            self.player.play()
            self.play_btn.setText("⏸ Пауза")

    def _on_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.play_btn.setText("⏵ Играть")

    def _set_volume(self, val):
        self.audio_output.setVolume(val / 100.0)

    def closeEvent(self, event):
        self.player.stop()
        super().closeEvent(event)





class ResizableVideoLabel(QLabel):
    """QLabel для видео: размер меняется мышкой за любой угол."""

    EDGE_NONE = 0
    EDGE_LEFT = 1
    EDGE_TOP = 2
    EDGE_RIGHT = 4
    EDGE_BOTTOM = 8

    def __init__(self, text="", width=320, height=240, parent=None):
        super().__init__(text, parent)
        self._resize_margin = 18
        self._min_w = 80
        self._min_h = 60
        self._max_w = 1600
        self._max_h = 1200
        self._resizing = False
        self._resize_edges = self.EDGE_NONE
        self._drag_start_global = None
        self._start_geometry = None
        self._source_pixmap = None
        self.stretch_video = False

        self.setMinimumSize(self._min_w, self._min_h)
        self.setMaximumSize(self._max_w, self._max_h)
        self.resize(width, height)
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(self.styleSheet() + "; border: 1px solid #555;")

    def set_stretch_video(self, checked):
        self.stretch_video = bool(checked)
        self._refresh_pixmap()

    def set_video_pixmap(self, pixmap):
        self._source_pixmap = pixmap
        self._refresh_pixmap()

    def _refresh_pixmap(self):
        if self._source_pixmap is None:
            return
        mode = Qt.IgnoreAspectRatio if self.stretch_video else Qt.KeepAspectRatio
        super().setPixmap(self._source_pixmap.scaled(self.size(), mode, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_pixmap()

    def _event_pos(self, event):
        # PySide6: position(), старые варианты: pos()
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

    def _event_global_pos(self, event):
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        return event.globalPos()

    def _hit_test_edges(self, pos):
        edges = self.EDGE_NONE
        if pos.x() <= self._resize_margin:
            edges |= self.EDGE_LEFT
        elif pos.x() >= self.width() - self._resize_margin:
            edges |= self.EDGE_RIGHT

        if pos.y() <= self._resize_margin:
            edges |= self.EDGE_TOP
        elif pos.y() >= self.height() - self._resize_margin:
            edges |= self.EDGE_BOTTOM

        # Меняем размер только за углы, не за боковые стороны.
        horizontal = edges & (self.EDGE_LEFT | self.EDGE_RIGHT)
        vertical = edges & (self.EDGE_TOP | self.EDGE_BOTTOM)
        return edges if horizontal and vertical else self.EDGE_NONE

    def _apply_cursor(self, edges):
        if edges in (self.EDGE_LEFT | self.EDGE_TOP, self.EDGE_RIGHT | self.EDGE_BOTTOM):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edges in (self.EDGE_RIGHT | self.EDGE_TOP, self.EDGE_LEFT | self.EDGE_BOTTOM):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.unsetCursor()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edges = self._hit_test_edges(self._event_pos(event))
            if edges:
                self._resizing = True
                self._resize_edges = edges
                self._drag_start_global = self._event_global_pos(event)
                self._start_geometry = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = self._event_pos(event)

        if self._resizing and self._drag_start_global is not None and self._start_geometry is not None:
            delta = self._event_global_pos(event) - self._drag_start_global
            g = self._start_geometry

            left = g.left()
            top = g.top()
            right = g.right()
            bottom = g.bottom()

            if self._resize_edges & self.EDGE_LEFT:
                left = g.left() + delta.x()
            if self._resize_edges & self.EDGE_RIGHT:
                right = g.right() + delta.x()
            if self._resize_edges & self.EDGE_TOP:
                top = g.top() + delta.y()
            if self._resize_edges & self.EDGE_BOTTOM:
                bottom = g.bottom() + delta.y()

            new_w = right - left + 1
            new_h = bottom - top + 1

            if new_w < self._min_w:
                if self._resize_edges & self.EDGE_LEFT:
                    left = right - self._min_w + 1
                else:
                    right = left + self._min_w - 1
                new_w = self._min_w
            elif new_w > self._max_w:
                if self._resize_edges & self.EDGE_LEFT:
                    left = right - self._max_w + 1
                else:
                    right = left + self._max_w - 1
                new_w = self._max_w

            if new_h < self._min_h:
                if self._resize_edges & self.EDGE_TOP:
                    top = bottom - self._min_h + 1
                else:
                    bottom = top + self._min_h - 1
                new_h = self._min_h
            elif new_h > self._max_h:
                if self._resize_edges & self.EDGE_TOP:
                    top = bottom - self._max_h + 1
                else:
                    bottom = top + self._max_h - 1
                new_h = self._max_h

            self.setMinimumSize(self._min_w, self._min_h)
            self.setMaximumSize(self._max_w, self._max_h)
            self.setGeometry(left, top, new_w, new_h)
            self._refresh_pixmap()
            event.accept()
            return

        self._apply_cursor(self._hit_test_edges(pos))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self._resize_edges = self.EDGE_NONE
            self._drag_start_global = None
            self._start_geometry = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

# ---------- Диалоги звонков (с микшером) ----------
class CallStatusDialog(QDialog):
    def __init__(self, status_text, on_hangup, video=False, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.video = video
        self.setWindowTitle("Звонок")
        self.resize(400, 400) if video else self.resize(400, 400)

        layout = QVBoxLayout(self)

        self.status_label = QLabel(status_text)
        self.status_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(self.status_label)

        # NEW: ползунки громкости во время звонка
        controls = QGroupBox("Регулировка громкости")
        c_layout = QVBoxLayout()

        mic_row = QHBoxLayout()
        mic_row.addWidget(QLabel("Микрофон"))
        self.mic_slider = QSlider(Qt.Horizontal)
        self.mic_slider.setRange(0, 200)
        self.mic_slider.setValue(100)
        self.mic_slider.valueChanged.connect(self._on_mic_gain)
        mic_row.addWidget(self.mic_slider)
        self.mic_label = QLabel("100%")
        mic_row.addWidget(self.mic_label)
        c_layout.addLayout(mic_row)

        speaker_row = QHBoxLayout()
        speaker_row.addWidget(QLabel("Динамик"))
        self.speaker_slider = QSlider(Qt.Horizontal)
        self.speaker_slider.setRange(0, 200)
        self.speaker_slider.setValue(100)
        self.speaker_slider.valueChanged.connect(self._on_speaker_gain)
        speaker_row.addWidget(self.speaker_slider)
        self.speaker_label = QLabel("100%")
        speaker_row.addWidget(self.speaker_label)
        c_layout.addLayout(speaker_row)

        # NEW: чекбокс шумоподавления
        self.nr_check = QCheckBox("Шумоподавление")
        self.nr_check.setChecked(False)
        self.nr_check.toggled.connect(self._on_nr_toggle)
        c_layout.addWidget(self.nr_check)

        controls.setLayout(c_layout)
        layout.addWidget(controls)

        if video:
            video_row = QHBoxLayout()
            self.remote_label = ResizableVideoLabel("Ожидание видео...", 320, 240)
            self.remote_label.setStyleSheet("background-color: #222; color: #888;")
            self.remote_label.setAlignment(Qt.AlignCenter)
            video_row.addWidget(self.remote_label)

            self.local_label = ResizableVideoLabel("Ты", 120, 90)
            self.local_label.setStyleSheet("background-color: #333; color: #888;")
            self.local_label.setAlignment(Qt.AlignCenter)
            video_row.addWidget(self.local_label)
            layout.addLayout(video_row)

            self.stretch_video = False
            self.stretch_video_check = QCheckBox("Растягивать картинку внутри окна")
            self.stretch_video_check.toggled.connect(self._on_stretch_video)
            layout.addWidget(self.stretch_video_check)
            hint = QLabel("Подсказка: тяни правый нижний угол видео, чтобы изменить размер.")
            hint.setStyleSheet("color: #888; font-size: 11px;")
            layout.addWidget(hint)

        hangup_btn = QPushButton("📴 Завершить")
        hangup_btn.clicked.connect(on_hangup)
        layout.addWidget(hangup_btn)

        # синхронизируем с родительскими значениями
        if parent:
            self.mic_slider.setValue(int(parent.mic_gain * 100))
            self.speaker_slider.setValue(int(parent.speaker_gain * 100))
            self.nr_check.setChecked(parent.noise_reduction_enabled)

    def _on_mic_gain(self, val):
        self.mic_label.setText(f"{val}%")
        if self.parent:
            self.parent.mic_gain = val / 100.0

    def _on_speaker_gain(self, val):
        self.speaker_label.setText(f"{val}%")
        if self.parent:
            self.parent.speaker_gain = val / 100.0

    def _on_nr_toggle(self, checked):
        if self.parent:
            self.parent.noise_reduction_enabled = checked

    def set_status(self, text):
        self.status_label.setText(text)

    def _on_remote_size(self, val):
        self.remote_scale = val
        if hasattr(self, 'remote_label'):
            self.remote_label.setFixedSize(int(320 * val / 100), int(240 * val / 100))

    def _on_local_size(self, val):
        self.local_scale = val
        if hasattr(self, 'local_label'):
            self.local_label.setFixedSize(int(120 * val / 100), int(90 * val / 100))

    def _on_stretch_video(self, checked):
        self.stretch_video = checked
        if hasattr(self, 'remote_label') and hasattr(self.remote_label, 'set_stretch_video'):
            self.remote_label.set_stretch_video(checked)
        if hasattr(self, 'local_label') and hasattr(self.local_label, 'set_stretch_video'):
            self.local_label.set_stretch_video(checked)
    def update_remote_frame(self, pixmap):
        if hasattr(self, 'remote_label'):
            if hasattr(self.remote_label, 'set_video_pixmap'):
                self.remote_label.set_video_pixmap(pixmap)
            else:
                mode = Qt.IgnoreAspectRatio if getattr(self, 'stretch_video', False) else Qt.KeepAspectRatio
                self.remote_label.setPixmap(pixmap.scaled(self.remote_label.size(), mode, Qt.SmoothTransformation))

    def update_local_frame(self, pixmap):
        if hasattr(self, 'local_label'):
            if hasattr(self.local_label, 'set_video_pixmap'):
                self.local_label.set_video_pixmap(pixmap)
            else:
                mode = Qt.IgnoreAspectRatio if getattr(self, 'stretch_video', False) else Qt.KeepAspectRatio
                self.local_label.setPixmap(pixmap.scaled(self.local_label.size(), mode, Qt.SmoothTransformation))

class GroupCallDialog(QDialog):
    def __init__(self, on_leave, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("👥 Групповой звонок")
        self.resize(520, 480)
        self.member_tiles = {}
        self.member_names = {}

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Звонок идёт...")
        self.status_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(self.status_label)

        # NEW: ползунки для группового звонка
        controls = QGroupBox("Регулировка громкости")
        c_layout = QVBoxLayout()

        mic_row = QHBoxLayout()
        mic_row.addWidget(QLabel("Микрофон"))
        self.mic_slider = QSlider(Qt.Horizontal)
        self.mic_slider.setRange(0, 200)
        self.mic_slider.setValue(100)
        self.mic_slider.valueChanged.connect(self._on_mic_gain)
        mic_row.addWidget(self.mic_slider)
        self.mic_label = QLabel("100%")
        mic_row.addWidget(self.mic_label)
        c_layout.addLayout(mic_row)

        speaker_row = QHBoxLayout()
        speaker_row.addWidget(QLabel("Динамик"))
        self.speaker_slider = QSlider(Qt.Horizontal)
        self.speaker_slider.setRange(0, 200)
        self.speaker_slider.setValue(100)
        self.speaker_slider.valueChanged.connect(self._on_speaker_gain)
        speaker_row.addWidget(self.speaker_slider)
        self.speaker_label = QLabel("100%")
        speaker_row.addWidget(self.speaker_label)
        c_layout.addLayout(speaker_row)

        self.nr_check = QCheckBox("Шумоподавление")
        self.nr_check.setChecked(False)
        self.nr_check.toggled.connect(self._on_nr_toggle)
        c_layout.addWidget(self.nr_check)

        controls.setLayout(c_layout)
        layout.addWidget(controls)

        # PATCH: ресайз вебок в групповом видеозвонке
        self.tile_scale = 100
        self.stretch_video = False
        tile_size_row = QHBoxLayout()
        tile_size_row.addWidget(QLabel("Размер вебок"))
        self.tile_size_slider = QSlider(Qt.Horizontal)
        self.tile_size_slider.setRange(50, 200)
        self.tile_size_slider.setValue(100)
        self.tile_size_slider.valueChanged.connect(self._on_tile_size)
        tile_size_row.addWidget(self.tile_size_slider)
        layout.addLayout(tile_size_row)
        self.group_stretch_video_check = QCheckBox("Растягивать видео")
        self.group_stretch_video_check.toggled.connect(self._on_group_stretch_video)
        layout.addWidget(self.group_stretch_video_check)

        self.grid = QGridLayout()
        grid_widget = QWidget()
        grid_widget.setLayout(self.grid)
        layout.addWidget(grid_widget)

        leave_btn = QPushButton("📴 Покинуть звонок")
        leave_btn.clicked.connect(on_leave)
        layout.addWidget(leave_btn)

        if parent:
            self.mic_slider.setValue(int(parent.mic_gain * 100))
            self.speaker_slider.setValue(int(parent.speaker_gain * 100))
            self.nr_check.setChecked(parent.noise_reduction_enabled)

    def _on_mic_gain(self, val):
        self.mic_label.setText(f"{val}%")
        if self.parent:
            self.parent.mic_gain = val / 100.0

    def _on_speaker_gain(self, val):
        self.speaker_label.setText(f"{val}%")
        if self.parent:
            self.parent.speaker_gain = val / 100.0

    def _on_nr_toggle(self, checked):
        if self.parent:
            self.parent.noise_reduction_enabled = checked

    def _on_tile_size(self, val):
        self.tile_scale = val
        self._rebuild_grid()

    def _on_group_stretch_video(self, checked):
        self.stretch_video = checked

    def set_members(self, members):
        self.member_names = dict(members)
        self._rebuild_grid()

    def add_member(self, member_id, nick):
        self.member_names[member_id] = nick
        self._rebuild_grid()

    def remove_member(self, member_id):
        self.member_names.pop(member_id, None)
        self._rebuild_grid()

    def _rebuild_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.member_tiles = {}

        cols = 2
        for i, (mid, nick) in enumerate(sorted(self.member_names.items())):
            tile = ResizableVideoLabel(nick, int(220 * getattr(self, 'tile_scale', 100) / 100), int(165 * getattr(self, 'tile_scale', 100) / 100))
            tile.setStyleSheet("background-color: #222; color: #ccc;")
            tile.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(tile, i // cols, i % cols)
            self.member_tiles[mid] = tile

    def update_member_frame(self, member_id, pixmap):
        tile = self.member_tiles.get(member_id)
        if tile:
            if hasattr(tile, 'set_stretch_video'):
                tile.set_stretch_video(getattr(self, 'stretch_video', False))
            if hasattr(tile, 'set_video_pixmap'):
                tile.set_video_pixmap(pixmap)
            else:
                mode = Qt.IgnoreAspectRatio if getattr(self, 'stretch_video', False) else Qt.KeepAspectRatio
                tile.setPixmap(pixmap.scaled(tile.size(), mode, Qt.SmoothTransformation))
    def set_status(self, text):
        self.status_label.setText(text)


# ---------- Диалог настроек аудио ----------
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Настройки аудио")
        self.resize(400, 350)

        layout = QVBoxLayout(self)

        # Устройства ввода
        input_group = QGroupBox("Микрофон")
        in_layout = QVBoxLayout()
        self.input_combo = QComboBox()
        self.input_combo.addItem("Системное по умолчанию", None)
        for dev in QMediaDevices.audioInputs():
            self.input_combo.addItem(dev.description(), dev)
        in_layout.addWidget(self.input_combo)
        input_group.setLayout(in_layout)
        layout.addWidget(input_group)

        # Устройства вывода
        output_group = QGroupBox("Динамик")
        out_layout = QVBoxLayout()
        self.output_combo = QComboBox()
        self.output_combo.addItem("Системное по умолчанию", None)
        for dev in QMediaDevices.audioOutputs():
            self.output_combo.addItem(dev.description(), dev)
        out_layout.addWidget(self.output_combo)
        output_group.setLayout(out_layout)
        layout.addWidget(output_group)

        # Громкость
        vol_group = QGroupBox("Громкость по умолчанию")
        vol_layout = QVBoxLayout()
        mic_row = QHBoxLayout()
        mic_row.addWidget(QLabel("Микрофон"))
        self.mic_slider = QSlider(Qt.Horizontal)
        self.mic_slider.setRange(0, 200)
        self.mic_slider.setValue(100)
        mic_row.addWidget(self.mic_slider)
        self.mic_label = QLabel("100%")
        mic_row.addWidget(self.mic_label)
        vol_layout.addLayout(mic_row)

        speaker_row = QHBoxLayout()
        speaker_row.addWidget(QLabel("Динамик"))
        self.speaker_slider = QSlider(Qt.Horizontal)
        self.speaker_slider.setRange(0, 200)
        self.speaker_slider.setValue(100)
        speaker_row.addWidget(self.speaker_slider)
        self.speaker_label = QLabel("100%")
        speaker_row.addWidget(self.speaker_label)
        vol_layout.addLayout(speaker_row)
        vol_group.setLayout(vol_layout)
        layout.addWidget(vol_group)

        # Шумоподавление
        self.nr_check = QCheckBox("Включить шумоподавление (pyrnnoise)")
        self.nr_check.setChecked(False)
        layout.addWidget(self.nr_check)

        # Кнопки OK/Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Загружаем текущие значения из parent
        if parent:
            self.mic_slider.setValue(int(parent.mic_gain * 100))
            self.speaker_slider.setValue(int(parent.speaker_gain * 100))
            self.nr_check.setChecked(parent.noise_reduction_enabled)
            if parent.selected_input_device:
                idx = self.input_combo.findData(parent.selected_input_device)
                if idx >= 0:
                    self.input_combo.setCurrentIndex(idx)
            if parent.selected_output_device:
                idx = self.output_combo.findData(parent.selected_output_device)
                if idx >= 0:
                    self.output_combo.setCurrentIndex(idx)

        self.mic_slider.valueChanged.connect(lambda v: self.mic_label.setText(f"{v}%"))
        self.speaker_slider.valueChanged.connect(lambda v: self.speaker_label.setText(f"{v}%"))

    def accept(self):
        if self.parent:
            self.parent.mic_gain = self.mic_slider.value() / 100.0
            self.parent.speaker_gain = self.speaker_slider.value() / 100.0
            self.parent.noise_reduction_enabled = self.nr_check.isChecked()
            self.parent.selected_input_device = self.input_combo.currentData()
            self.parent.selected_output_device = self.output_combo.currentData()
            # Пересоздаём аудио-потоки если звонок активен
            if self.parent.current_call or self.parent.group_call:
                self.parent._recreate_audio_streams()
        super().accept()

class MyFeatureDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('СИКС СЕВЕН')
        self.resize(400, 300)

        layout = QVBoxLayout(self)

        self.label = QLabel('676767')
        self.input = QLineEdit()
        self.button = QPushButton('Нафми 67')

        layout.addWidget(self.label)
        layout.addWidget(self.input)
        layout.addWidget(self.button)

# ---------- Главное окно ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"BUKKAX v{CURRENT_VERSION}")
        self.resize(900, 600)

        icon_path = os.path.join(get_base_dir(), 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.client = None
        self.nickname = None
        self.device_id = get_device_id()
        self.rooms = ['general']
        self.current_view = ('room', 'general')
        self.friends = []
        self.private_chats = {}
        self.avatar_cache = {}
        self.pending_avatar_requests = set()
        self.room_texts = {'general': ''}
        self.dm_texts = {}
        self.dm_nicks = set()
        self.sound_enabled = True
        self.custom_sound_path = None
        self.bg_pixmap = None

        self.profile_dialog = None
        self.chess_dialogs = {}
        self.chess_pending_invites = {}
        self.news_dialog = None
        self.admin_dialog = None
        self._pending_gift_view = None

        # NEW: параметры аудио
        self.mic_gain = 0.7
        self.speaker_gain = 0.7
        self.noise_reduction_enabled = False
        self.selected_input_device = None
        self.selected_output_device = None
        self.audio_sample_rate = 48000  # можно будет менять
        self._rnnoise_denoiser = None
        if RNNOISE_AVAILABLE:
            try:
                # Создаём объект шумоподавления с нужной частотой
                self._rnnoise_denoiser = RNNoise(sample_rate=self.audio_sample_rate)
            except Exception:
                pass

        self.current_call = None
        self.call_dialog = None
        self.incoming_call_dialog = None
        self.ringtone_player = None
        self.ringtone_audio_output = None
        self.audio_source = None
        self.audio_sink = None
        self.mic_io = None
        self.speaker_io = None
        self.camera = None
        self.video_sink = None
        self.capture_session = None
        self._last_frame_sent_time = 0

        self.group_call = None
        self.group_call_dialog = None
        self.group_audio_buffers = {}
        self.group_audio_timer = None

        self.call_udp_socket = QUdpSocket(self)
        self.call_udp_socket.bind(QHostAddress.AnyIPv4, 0)
        self.call_udp_socket.readyRead.connect(self._on_call_udp_data)

        self.video_udp_socket = QUdpSocket(self)
        self.video_udp_socket.bind(QHostAddress.AnyIPv4, 0)
        self.video_udp_socket.readyRead.connect(self._on_call_video_udp_data)

        self._build_ui()
        QTimer.singleShot(300, self.connect_to_server)

    def open_my_feature(self):
        dlg = MyFeatureDialog(self)
        dlg.exec()

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self.bg_label = QLabel(central)
        self.bg_label.setScaledContents(True)
        self.bg_label.lower()

        root_layout = QHBoxLayout(central)

        left = QWidget()
        left.setAttribute(Qt.WA_StyledBackground, True)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QHBoxLayout()
        # BUKKAX DEVELOPER BUILDER V1
        self.dev_top_bar = top_bar
        self.title_label = QLabel("💬 Общий чат")
        self.title_label.setStyleSheet("color: #4EA1FF; font-weight: bold; font-size: 13px;")
        top_bar.addWidget(self.title_label)
        top_bar.addStretch()

        # NEW: кнопка настроек аудио
        settings_btn = QPushButton("🔊 "
                                   "аудио")
        settings_btn.setFixedWidth(68)
        settings_btn.setToolTip("Настройки вывода звука и микрофона")
        settings_btn.clicked.connect(self.open_audio_settings)
        top_bar.addWidget(settings_btn)

        bg_color_btn = QPushButton("🎨")
        bg_color_btn.setFixedWidth(30)
        bg_color_btn.clicked.connect(self.open_background_menu)
        top_bar.addWidget(bg_color_btn)

        avatar_btn = QPushButton("🙂")
        avatar_btn.setFixedWidth(30)
        avatar_btn.clicked.connect(self.choose_avatar)
        top_bar.addWidget(avatar_btn)

        sound_btn = QPushButton("🔔")
        sound_btn.setFixedWidth(30)
        sound_btn.clicked.connect(self.open_sound_menu)
        top_bar.addWidget(sound_btn)

        group_call_btn = QPushButton("👥")
        group_call_btn.setFixedWidth(30)
        group_call_btn.setToolTip("Групповой звонок (открой приватную беседу)")
        group_call_btn.clicked.connect(self.start_or_join_group_call)
        top_bar.addWidget(group_call_btn)

        profile_btn = QPushButton("👤")
        profile_btn.setFixedWidth(30)
        profile_btn.clicked.connect(lambda: self.open_profile(self.nickname))
        top_bar.addWidget(profile_btn)

        chess_btn = QPushButton("♟")
        chess_btn.setFixedWidth(30)
        chess_btn.setToolTip("Сыграть в шахматы")
        chess_btn.clicked.connect(self.open_chess_start_dialog)
        top_bar.addWidget(chess_btn)

#--- подарки обычных пользователей
        # Подарки между обычными пользователями
        self.my_feature_btn = QPushButton('🎁')
        self.my_feature_btn.setToolTip("Отправить подарок")
        self.my_feature_btn.setFixedWidth(48)
        self.my_feature_btn.clicked.connect(self.send_user_gift)
        top_bar.addWidget(self.my_feature_btn)

        news_btn = QPushButton("📰")
        news_btn.setFixedWidth(32)
        news_btn.clicked.connect(self.open_news_feed)
        top_bar.addWidget(news_btn)

        self.admin_btn = QPushButton("⚙️")
        self.admin_btn.setFixedWidth(32)
        self.admin_btn.clicked.connect(self.open_admin_panel)
        self.admin_btn.setVisible(False)
        top_bar.addWidget(self.admin_btn)

        self.dev_builder_btn = QPushButton("🛠")
        self.dev_builder_btn.setFixedWidth(36)
        self.dev_builder_btn.setToolTip("Developer Builder")
        self.dev_builder_btn.clicked.connect(self.open_developer_builder)
        self.dev_builder_btn.setVisible(False)
        top_bar.addWidget(self.dev_builder_btn)

        self._reload_developer_widgets()

        self.music_btn = QPushButton("🎵")
        self.music_btn.setToolTip("Включить музыку")
        self.music_btn.clicked.connect(self._start_music_app)
        self.music_btn.setFixedWidth(32)
        top_bar.addWidget(self.music_btn)

        left_layout.addLayout(top_bar)

        self.chat_view = QTextBrowser()
        self.chat_view.setOpenLinks(False)
        self.chat_view.anchorClicked.connect(self._handle_anchor_click)
        self.chat_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chat_view.customContextMenuRequested.connect(self._chat_context_menu)
        self._style_chat_view(self.chat_view)
        left_layout.addWidget(self.chat_view)

# ----------полоска для ввода сообщений --------------
        bottom_bar = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.installEventFilter(self)
        self.entry.returnPressed.connect(self.send_message)
        bottom_bar.addWidget(self.entry)

        file_btn = QPushButton("📎")
        file_btn.setFixedWidth(36)
        file_btn.clicked.connect(self.send_file)
        bottom_bar.addWidget(file_btn)

        emoji_btn = QPushButton("😊")
        emoji_btn.setFixedWidth(36)
        emoji_btn.clicked.connect(self.open_emoji_picker)
        bottom_bar.addWidget(emoji_btn)

        self.voice_btn = QPushButton("🎤")
        self.voice_btn.setFixedWidth(36)
        self.voice_btn.setToolTip("Записать голосовое сообщение")
        self.voice_btn.clicked.connect(self._toggle_voice_recording)
        bottom_bar.addWidget(self.voice_btn)

        video_msg_btn = QPushButton("📹")
        video_msg_btn.setFixedWidth(36)
        video_msg_btn.setToolTip("Записать видеосообщение (кружок)")
        video_msg_btn.clicked.connect(self.open_video_message_recorder)
        bottom_bar.addWidget(video_msg_btn)

        send_btn = QPushButton("Отправить")
        send_btn.clicked.connect(self.send_message)
        bottom_bar.addWidget(send_btn)

        left_layout.addLayout(bottom_bar)
        root_layout.addWidget(left, stretch=3)

        # Правая колонка
        right = QWidget()
        right.setFixedWidth(220)
        right_layout = QVBoxLayout(right)

        rooms_bar = QHBoxLayout()
        rooms_bar.addWidget(QLabel("Чаты"))
        rooms_bar.addStretch()
        add_room_btn = QPushButton("➕")
        add_room_btn.setFixedWidth(28)
        add_room_btn.clicked.connect(self.add_room_dialog)
        rooms_bar.addWidget(add_room_btn)
        refresh_rooms_btn = QPushButton("🔄")
        refresh_rooms_btn.setFixedWidth(28)
        refresh_rooms_btn.clicked.connect(self.request_room_list)
        rooms_bar.addWidget(refresh_rooms_btn)
        right_layout.addLayout(rooms_bar)

        self.rooms_list = QListWidget()
        self.rooms_list.addItem("general")
        self.rooms_list.setCurrentRow(0)
        self.rooms_list.itemClicked.connect(self._on_room_clicked)
        self.rooms_list.setMaximumHeight(110)
        right_layout.addWidget(self.rooms_list)

        dm_bar = QHBoxLayout()
        dm_bar.addWidget(QLabel("✉️ Личные сообщения"))
        dm_bar.addStretch()
        right_layout.addLayout(dm_bar)

        self.dm_list = QListWidget()
        self.dm_list.itemClicked.connect(self._on_dm_clicked)
        self.dm_list.setMaximumHeight(80)
        right_layout.addWidget(self.dm_list)

        private_bar = QHBoxLayout()
        private_bar.addWidget(QLabel("🔒 Приватные"))
        private_bar.addStretch()
        add_private_btn = QPushButton("➕")
        add_private_btn.setFixedWidth(28)
        add_private_btn.clicked.connect(self.add_private_chat_dialog)
        private_bar.addWidget(add_private_btn)
        refresh_private_btn = QPushButton("🔄")
        refresh_private_btn.setFixedWidth(28)
        refresh_private_btn.clicked.connect(self.request_private_chat_list)
        private_bar.addWidget(refresh_private_btn)
        right_layout.addLayout(private_bar)

        self.private_list = QListWidget()
        self.private_list.itemClicked.connect(self._on_private_chat_clicked)
        self.private_list.setMaximumHeight(110)
        right_layout.addWidget(self.private_list)

        friends_bar = QHBoxLayout()
        friends_bar.addWidget(QLabel("Друзья"))
        friends_bar.addStretch()
        add_friend_btn = QPushButton("➕")
        add_friend_btn.setFixedWidth(28)
        add_friend_btn.clicked.connect(self.add_friend_dialog)
        friends_bar.addWidget(add_friend_btn)
        refresh_friends_btn = QPushButton("🔄")
        refresh_friends_btn.setFixedWidth(28)
        refresh_friends_btn.clicked.connect(self.request_friend_list)
        friends_bar.addWidget(refresh_friends_btn)
        right_layout.addLayout(friends_bar)

        self.friends_list = QListWidget()
        self.friends_list.itemClicked.connect(self._on_friend_clicked)
        self.friends_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.friends_list.customContextMenuRequested.connect(
            self._friends_context_menu
        )
        right_layout.addWidget(self.friends_list)


        root_layout.addWidget(right, stretch=0)

    # ---------- Остальные методы (без изменений, кроме аудио) ----------
    # BUKKAX USER GIFTS PATCH: client
    def send_user_gift(self):
        nick, ok = QInputDialog.getText(
            self,
            "🎁 Отправить подарок",
            "Никнейм получателя:"
        )
        if not ok:
            return

        nick = nick.strip()
        if not nick:
            QMessageBox.information(
                self,
                "Подарок",
                "Нужно указать никнейм получателя."
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбери подарок",
            "",
            "Изображения (*.png *.jpg *.jpeg *.gif *.webp *.bmp)"
        )
        if not path:
            return

        try:
            file_size = os.path.getsize(path)
        except OSError as e:
            QMessageBox.warning(
                self,
                "Ошибка",
                f"Не удалось прочитать файл: {e}"
            )
            return

        max_size = 10 * 1024 * 1024

        if file_size <= 0:
            QMessageBox.warning(
                self,
                "Подарок",
                "Выбранный файл пустой."
            )
            return

        if file_size > max_size:
            QMessageBox.warning(
                self,
                "Подарок",
                "Картинка подарка должна быть не больше 10 МБ."
            )
            return

        note, ok = QInputDialog.getText(
            self,
            "🎁 Подарок",
            "Подпись к подарку (необязательно):"
        )
        if not ok:
            note = ""

        note = note.strip()[:300]

        try:
            with open(path, "rb") as f:
                data = f.read()

            send_frame(
                self.client,
                {
                    "type": "user_send_gift",
                    "target": nick,
                    "note": note,
                    "size": len(data),
                },
                data
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Ошибка",
                f"Не удалось отправить подарок: {e}"
            )

    def _handle_user_gift_result(self, header):
        status = header.get("status")
        target = header.get("target", "")

        if status == "ok":
            online = bool(header.get("online"))

            if online:
                text = f'🎁 Подарок для "{target}" отправлен!'
            else:
                text = f'🎁 Подарок для "{target}" сохранён. Пользователь сейчас офлайн и увидит подарок в профиле.'

            QMessageBox.information(
                self,
                "Подарок отправлен",
                text
            )
            return

        texts = {
            "invalid": "Не хватает ника или изображения.",
            "not_found": f'Пользователь "{target}" не найден.',
            "self": "Нельзя отправить подарок самому себе.",
            "too_large": "Подарок слишком большой. Максимум 10 МБ.",
            "invalid_image": "Выбранный файл не является корректным изображением.",
        }

        QMessageBox.warning(
            self,
            "Подарок",
            texts.get(status, "Сервер не смог отправить подарок.")
        )

    def open_developer_builder(self):
        if self.nickname != ADMIN_NICKNAME:
            QMessageBox.warning(
                self,
                "Developer Builder",
                "Конструктор доступен только администратору/разработчику."
            )
            return

        try:
            from bukkax_dev_builder import DeveloperBuilderDialog

            dlg = getattr(self, "dev_builder_dialog", None)
            if dlg is not None:
                try:
                    dlg.showNormal()
                    dlg.raise_()
                    dlg.activateWindow()
                    return
                except Exception:
                    pass

            self.dev_builder_dialog = DeveloperBuilderDialog(
                self,
                ADMIN_NICKNAME,
                apply_callback=self._reload_developer_widgets,
            )
            self.dev_builder_dialog.finished.connect(
                lambda *_: setattr(self, "dev_builder_dialog", None)
            )
            self.dev_builder_dialog.show()
            self.dev_builder_dialog.raise_()
            self.dev_builder_dialog.activateWindow()

        except Exception as e:
            QMessageBox.warning(
                self,
                "Developer Builder",
                f"Не удалось открыть конструктор:\n{e}"
            )

    def _reload_developer_widgets(self):
        try:
            from bukkax_dev_builder import apply_builder_config

            layout = getattr(self, "dev_top_bar", None)
            if layout is None:
                return

            apply_builder_config(
                self,
                layout,
                ADMIN_NICKNAME,
            )
        except Exception as e:
            print(f"Developer Builder reload error: {e}")

    def _friends_context_menu(self, pos):
        item = self.friends_list.itemAt(pos)
        if not item:
            return
        nick = item.text()[2:].strip() if len(item.text()) > 2 else item.text()
        menu = QMenu(self)
        menu.addAction("Написать", lambda: self.open_dm(nick))
        menu.addAction("📞 Позвонить", lambda: self.start_call(nick, video=False))
        menu.addAction("📹 Видеозвонок", lambda: self.start_call(nick, video=True))
        menu.addAction("Профиль", lambda: self.open_profile(nick))
        menu.addAction("♟ Сыграть в шахматы", lambda: self.start_chess_with(nick))
        menu.exec(self.friends_list.mapToGlobal(pos))

    def _style_chat_view(self, widget, bg="rgba(0,0,0,235)"):
        widget.setStyleSheet(
            f"QTextBrowser {{ background-color: {bg}; color: white; "
            f"border: none; font-family: Consolas; font-size: 12pt; }}"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        central = self.centralWidget()
        if central is not None:
            self.bg_label.setGeometry(0, 0, central.width(), central.height())

    # ---------- Фон ----------
    def open_background_menu(self):
        menu = QMenu(self)
        menu.addAction("🎨 Однотонный цвет", self.choose_bg_color)
        menu.addAction("🖼 Своё фото (за текстом сообщений)", self.choose_bg_photo)
        menu.addAction("↩ Сбросить", self.reset_background)
        menu.exec(self.mapToGlobal(QPoint(0, 40)))

    def choose_bg_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.bg_pixmap = None
            self.bg_label.clear()
            self.centralWidget().setStyleSheet(f"background-color: {color.name()};")
            self._style_chat_view(self.chat_view, "rgba(0,0,0,80)")

    def choose_bg_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери фото для фона", "", "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return
        self.bg_pixmap = QPixmap(path)
        self.bg_label.setPixmap(self.bg_pixmap)
        central = self.centralWidget()
        self.bg_label.setGeometry(0, 0, central.width(), central.height())
        self.bg_label.lower()
        self._style_chat_view(self.chat_view, "rgba(0,0,0,140)")

    def reset_background(self):
        self.bg_pixmap = None
        self.bg_label.clear()
        self.centralWidget().setStyleSheet("")
        self._style_chat_view(self.chat_view, "rgba(0,0,0,235)")

    # ---------- Подключение ----------
    def connect_to_server(self):
        import socket
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._append_html('general', f"🔌 Подключаемся к серверу {SERVER_IP}:{PORT}...")
        try:
            self.client.connect((SERVER_IP, PORT))
            self._append_html('general', "✅ Подключено к серверу!")
        except OSError as e:
            QMessageBox.critical(self, "Ошибка подключения", str(e))
            return

        try:
            msg = self.client.recv(1024).decode('utf-8')
        except Exception:
            msg = ''

        if msg == 'NICK':
            self._nickname_handshake()
        if not self.nickname:
            return

        self._append_html('general', f"✨ Добро пожаловать в чат, {self.nickname}!")
        if self.nickname == ADMIN_NICKNAME:
            self.admin_btn.setVisible(True)
            self.dev_builder_btn.setVisible(True)
            self._reload_developer_widgets()

        self.net_thread = QThread()
        self.worker = NetworkWorker(self.client)
        self.worker.moveToThread(self.net_thread)
        self.net_thread.started.connect(self.worker.run)
        self.worker.frame_received.connect(self._handle_frame)
        self.worker.disconnected.connect(lambda msg: self._append_html('general', msg))
        self.net_thread.start()

        self.request_friend_list()
        self.request_room_list()
        self.request_private_chat_list()
        self._request_avatar(self.nickname)

        self.update_thread = QThread()
        self.update_worker = UpdateCheckWorker()
        self.update_worker.moveToThread(self.update_thread)
        self.update_thread.started.connect(self.update_worker.run)
        self.update_worker.update_available.connect(self._prompt_update)
        self.update_thread.start()

    def _nickname_handshake(self):
        saved = get_saved_nickname()
        if saved and self._attempt_nickname(saved):
            self.nickname = saved
            return
        while True:
            nickname, ok = QInputDialog.getText(self, "Никнейм", "Введи свой никнейм:")
            if not ok:
                continue
            nickname = nickname.strip()
            if not nickname:
                continue
            if self._attempt_nickname(nickname):
                self.nickname = nickname
                save_nickname(nickname)
                return
            QMessageBox.warning(self, "Ник занят", f'Никнейм "{nickname}" уже занят. Выбери другой.')

    def _attempt_nickname(self, nickname):
        payload = json.dumps({'nickname': nickname, 'device_id': self.device_id})
        try:
            self.client.send(payload.encode('utf-8'))
            resp = self.client.recv(1024).decode('utf-8')
        except Exception:
            QMessageBox.critical(self, "Ошибка", "Потеряна связь с сервером во время регистрации ника")
            return False
        return resp == 'NICK_OK'

    # ---------- Приём кадров ----------
    def _handle_frame(self, header, payload):
        msg_type = header.get('type')

        if msg_type == 'text':
            room = header.get('room', 'general')
            nick = header.get('nick', '???')
            text = header.get('text', '')
            self._on_incoming_room_text(room, nick, text)
            if nick != self.nickname:
                self._play_notification_sound()

        elif msg_type == 'file':
            room = header.get('room', 'general')
            nick = header.get('nick', '???')
            filename = header.get('filename', 'file')
            self._on_incoming_file(room, nick, filename, payload)
            if nick != self.nickname:
                self._play_notification_sound()

        elif msg_type == 'history':
            self._load_history(header.get('messages', []))

        elif msg_type == 'room_list':
            self._update_rooms_list(header.get('rooms', []))

        elif msg_type == 'room_create_result':
            self._handle_room_create_result(header)

        elif msg_type == 'room_history':
            self._load_room_history(header.get('room'), header.get('messages', []))

        elif msg_type == 'room_list_changed':
            self.request_room_list()

        elif msg_type == 'private_chat_list':
            self._update_private_chats_list(header.get('chats', []))

        elif msg_type == 'private_chat_create_result':
            self._handle_private_chat_create_result(header)

        elif msg_type == 'private_chat_invited':
            self._handle_private_chat_invited(header)

        elif msg_type == 'private_chat_history':
            self._load_private_chat_history(header.get('chat_id'), header.get('messages', []))

        elif msg_type == 'private_chat_action_result':
            self._handle_private_chat_action_result(header)

        elif msg_type == 'private_chat_members_changed':
            self.request_private_chat_list()
            chat_id = header.get('chat_id')
            if self.current_view == ('private', chat_id):
                try:
                    send_frame(self.client, {'type': 'private_chat_history_request', 'chat_id': chat_id})
                except Exception:
                    pass

        elif msg_type == 'private_chat_removed':
            name = header.get('name', '')
            QMessageBox.warning(self, "Беседа", f'Тебя удалили из беседы "{name}".')
            self.request_private_chat_list()
            if self.current_view == ('private', header.get('chat_id')):
                self.show_room('general')

        elif msg_type == 'friend_list':
            self._update_friends_list(header.get('friends', []))

        elif msg_type == 'friend_add_result':
            self._handle_friend_add_result(header)

        elif msg_type == 'dm':
            nick = header.get('nick', '???')
            text = header.get('text', '')
            self._on_incoming_dm(nick, text)
            self._play_notification_sound()

        elif msg_type == 'dm_file':
            nick = header.get('nick', '???')
            filename = header.get('filename', 'file')
            self._on_incoming_dm_file(nick, filename, payload)
            self._play_notification_sound()

        elif msg_type == 'dm_history':
            self._load_dm_history(header.get('target'), header.get('messages', []))

        elif msg_type == 'avatar_data':
            self._store_avatar(header.get('nick'), payload)

        elif msg_type == 'avatar_changed':
            nick = header.get('nick')
            self.avatar_cache.pop(nick, None)
            try:
                old_path = self._avatar_cache_path(nick)
                if os.path.exists(old_path):
                    os.remove(old_path)
            except Exception:
                pass
            self._request_avatar(nick)

        elif msg_type == 'profile_data':
            if self.profile_dialog and self.profile_dialog.nickname == header.get('nickname'):
                self.profile_dialog.set_data(
                    header.get('bio', ''),
                    header.get('joined', ''),
                    header.get('gifts', []),
                    header.get('status', ''),
                    header.get('last_seen', ''),
                )

        elif msg_type == 'profile_saved':
            QMessageBox.information(self, "Профиль", "Профиль сохранён")

        elif msg_type == 'news_list':
            self._render_news_list(header.get('items', []))

        elif msg_type == 'news_posted':
            author = header.get('author', '???')
            text = header.get('text', '')
            self._append_html('general', f"📰 <b>{html.escape(author)}</b> опубликовал(а) новость: {html.escape(text)}")
            self._play_notification_sound()
            if self.news_dialog:
                self.request_news_list()

        elif msg_type == 'admin_user_list':
            if self.admin_dialog:
                self.admin_dialog.set_users(header.get('users', []))

        elif msg_type == 'admin_result':
            self._handle_admin_result(header)

        elif msg_type == 'user_gift_result':
            self._handle_user_gift_result(header)

        elif msg_type == 'gift_received':
            self._handle_gift_received(header, payload)

        elif msg_type == 'gift_image':
            self._handle_gift_image_response(header, payload)

        elif msg_type == 'kicked':
            QMessageBox.warning(self, "Отключено", f"Тебя забанил/кикнул администратор ({header.get('by', '')})")
            self.close()


        elif msg_type == 'chess_invite':
            self._handle_chess_invite(header)

        elif msg_type == 'chess_invite_result':
            self._handle_chess_invite_result(header)

        elif msg_type == 'chess_accept':
            self._handle_chess_accept(header)

        elif msg_type == 'chess_move':
            self._handle_chess_move(header)

        elif msg_type == 'chess_restart':
            self._handle_chess_restart(header)

        elif msg_type == 'chess_resign':
            self._handle_chess_resign(header)

        elif msg_type == 'chess_close':
            self._handle_chess_close(header)

        elif msg_type == 'call_offer':
            self._handle_incoming_call_offer(header)

        elif msg_type == 'call_ringing':
            if self.current_call:
                self.current_call['call_id'] = header.get('call_id')
            self._start_call_ringtone()

        elif msg_type == 'call_declined':
            self._handle_call_declined()

        elif msg_type == 'call_started':
            self._handle_call_started(header)

        elif msg_type == 'call_result':
            self._handle_call_result(header)

        elif msg_type == 'call_ended':
            self._handle_call_ended()

        elif msg_type == 'group_call_invite':
            self._handle_group_call_invite(header)

        elif msg_type == 'group_call_joined':
            self._handle_group_call_joined(header)

        elif msg_type == 'group_call_member_joined':
            self._handle_group_call_member_joined(header)

        elif msg_type == 'group_call_member_left':
            self._handle_group_call_member_left(header)

        elif msg_type == 'group_call_result':
            if header.get('status') == 'not_found':
                QMessageBox.information(self, "Групповой звонок", "Звонок уже завершён или не найден.")

    # ---------- Навигация ----------
    def _on_room_clicked(self, item):
        self.friends_list.clearSelection()
        self.private_list.clearSelection()
        self.dm_list.clearSelection()
        self.show_room(item.text())

    def _on_private_chat_clicked(self, item):
        self.rooms_list.clearSelection()
        self.friends_list.clearSelection()
        self.dm_list.clearSelection()
        chat_id = item.data(Qt.UserRole)
        self.show_private_chat(chat_id)

    def _on_dm_clicked(self, item):
        self.rooms_list.clearSelection()
        self.private_list.clearSelection()
        self.friends_list.clearSelection()
        nick = item.text()
        self.open_dm(nick)

    def _on_friend_clicked(self, item):
        self.rooms_list.clearSelection()
        self.private_list.clearSelection()
        self.dm_list.clearSelection()
        nick = item.text()[2:].strip() if len(item.text()) > 2 else item.text()
        self.open_dm(nick)

    def show_room(self, room_name):
        self.current_view = ('room', room_name)
        self.title_label.setText(f"💬 {room_name}" if room_name != 'general' else "💬 Общий чат")
        if room_name not in self.room_texts:
            self.room_texts[room_name] = '<i>Загрузка истории...</i><br>'
            self._render_current_view()
            try:
                send_frame(self.client, {'type': 'room_history_request', 'room': room_name})
            except Exception:
                pass
        else:
            self._render_current_view()

    def show_private_chat(self, chat_id):
        self.current_view = ('private', chat_id)
        name = self.private_chats.get(chat_id, chat_id)
        self.title_label.setText(f"🔒 {name}")
        key = f'private:{chat_id}'
        if key not in self.room_texts:
            self.room_texts[key] = '<i>Загрузка истории...</i><br>'
            self._render_current_view()
            try:
                send_frame(self.client, {'type': 'private_chat_history_request', 'chat_id': chat_id})
            except Exception:
                pass
        else:
            self._render_current_view()

    def open_dm(self, nick):
        self.current_view = ('dm', nick)
        self.title_label.setText(f"✉️ Личка: {nick}")
        if nick not in self.dm_texts:
            self.dm_texts[nick] = '<i>Загрузка истории...</i><br>'
            self._render_current_view()
            try:
                send_frame(self.client, {'type': 'dm_history_request', 'target': nick})
            except Exception:
                pass
        else:
            self._render_current_view()
        self._add_dm_to_list(nick)

    def _add_dm_to_list(self, nick):
        if nick not in self.dm_nicks:
            self.dm_nicks.add(nick)
            self.dm_list.addItem(nick)

    def _current_room_key(self):
        kind, target = self.current_view
        if kind == 'room':
            return target
        if kind == 'private':
            return f'private:{target}'
        return None

    def _render_current_view(self):
        kind, target = self.current_view
        if kind == 'dm':
            html_text = self.dm_texts.get(target, '')
        else:
            html_text = self.room_texts.get(self._current_room_key(), '')
        self.chat_view.setHtml(f'<body style="color:white;">{html_text}</body>')
        cursor = self.chat_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.chat_view.setTextCursor(cursor)

    # ---------- Вывод сообщений ----------
    def _try_send_image_url(self, url):
        if not url.lower().startswith(('http://', 'https://')):
            return False

        try:
            import urllib.request

            request = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0'
                }
            )

            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read()

            # Проверяем, что скачалось именно изображение
            image = Image.open(BytesIO(data))
            image.load()

            # Определяем расширение
            image_format = (image.format or 'PNG').upper()

            extensions = {
                'JPEG': '.jpg',
                'JPG': '.jpg',
                'PNG': '.png',
                'WEBP': '.webp',
                'GIF': '.gif',
                'BMP': '.bmp',
            }

            ext = extensions.get(image_format, '.png')

            # Временная папка
            temp_dir = os.path.join(
                get_base_dir(),
                'url_images'
            )
            os.makedirs(temp_dir, exist_ok=True)

            temp_path = os.path.join(
                temp_dir,
                f'url_{uuid.uuid4().hex}{ext}'
            )

            # Сохраняем скачанную картинку
            with open(temp_path, 'wb') as f:
                f.write(data)

            # Используем уже готовую отправку Bukkax
            self._send_file_from_path(temp_path)

            return True

        except Exception as e:
            print(f'Не удалось загрузить картинку по URL: {e}')
            return False

    def _safe_avatar_nick(self, nick):
        nick = str(nick or 'user').strip() or 'user'
        return ''.join(ch if ch.isalnum() or ch in (' ', '_', '-') else '_' for ch in nick).strip() or 'user'

    def _avatar_cache_path(self, nick):
        cache_dir = os.path.join(get_base_dir(), 'avatar_cache')
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, f'{self._safe_avatar_nick(nick)}.png')

    def _set_profile_avatar_if_open(self, nick):
        try:
            if self.profile_dialog and self.profile_dialog.nickname == nick:
                path = self.avatar_cache.get(nick) or self._avatar_cache_path(nick)
                if os.path.exists(path) and hasattr(self.profile_dialog, 'set_avatar_path'):
                    self.profile_dialog.set_avatar_path(path)
        except Exception:
            pass
    def _append_html(self, key, html_line, is_dm_key=False):
        store = self.dm_texts if is_dm_key else self.room_texts
        store[key] = store.get(key, '') + html_line + '<br>'
        if is_dm_key:
            active = (self.current_view[0] == 'dm' and self.current_view[1] == key)
        else:
            active = (self._current_room_key() == key)
        if active:
            self._render_current_view()

    def _avatar_img_tag(self, nick):
        # Важно: тег картинки возвращаем даже если файл ещё не скачан.
        # Когда avatar_data придёт с сервера, мы перерисуем чат, и этот же src уже загрузится.
        if not nick:
            return ''
        path = self.avatar_cache.get(nick) or self._avatar_cache_path(nick)
        if not os.path.exists(path):
            self._request_avatar(nick)
        try:
            url = QUrl.fromLocalFile(os.path.abspath(path)).toString()
        except Exception:
            abs_path = os.path.abspath(path).replace(os.sep, '/')
            url = f'file:///{abs_path}'
        return f"<img src=\"{url}\" width=\"28\" height=\"28\" style=\"vertical-align:middle; border-radius:14px;\"> "
    def _message_html(self, nick, text):
        safe_text = html.escape(text).replace('\n', '<br>')
        is_own = (nick == self.nickname)
        color = '#2b5278' if is_own else '#3a3a3a'
        align = 'right' if is_own else 'left'
        avatar = self._avatar_img_tag(nick)
        name_line = '' if is_own else f'<span style="color:#8ab4f8;"><b>{html.escape(nick)}</b></span><br>'
        return (
            f'<table width="100%" cellspacing="0" cellpadding="0"><tr><td align="{align}">'
            f'<table cellpadding="8" cellspacing="0" style="background-color:{color};">'
            f'<tr><td style="color:white;">{avatar}{name_line}{safe_text}</td></tr>'
            f'</table></td></tr></table>'
        )

    def _media_html(self, path, filename):
        _, ext = os.path.splitext(filename)
        abs_path = os.path.abspath(path).replace(os.sep, '/')
        if filename.startswith('voice_') and ext.lower() in AUDIO_EXTENSIONS:
            duration = parse_duration_from_filename(filename)
            label = f"🎤 Голосовое сообщение ({format_duration(duration)})"
            return f'<br><a href="playaudio:///{abs_path}">{label}</a><br>'
        if filename.startswith('videomsg_') and ext.lower() in VIDEO_EXTENSIONS:
            duration = parse_duration_from_filename(filename)
            thumb_path = self._get_circular_thumbnail(path)
            if thumb_path:
                return (
                    f'<br><a href="playvideo:///{abs_path}">'
                    f'<img src="file:///{thumb_path}" width="160" height="160"></a>'
                    f'<br><i>📹 видеосообщение ({format_duration(duration)})</i><br>'
                )
            return (
                f'<br>📹 <a href="playvideo:///{abs_path}">'
                f'Видеосообщение ({format_duration(duration)}) — нажми, чтобы посмотреть</a><br>'
            )
        if ext.lower() in IMAGE_EXTENSIONS:
            return (
                f'<br><a href="openfile:///{abs_path}">'
                f'<img src="file:///{abs_path}" width="320"></a><br>'
            )
        elif ext.lower() in VIDEO_EXTENSIONS:
            return f'<br>🎬 <a href="playvideo:///{abs_path}">{html.escape(filename)} (нажми, чтобы посмотреть)</a><br>'
        return ''

    def _get_circular_thumbnail(self, video_path):
        if not PIL_AVAILABLE:
            return None
        thumb_dir = os.path.join(get_base_dir(), 'video_thumbs')
        os.makedirs(thumb_dir, exist_ok=True)
        thumb_path = os.path.join(thumb_dir, os.path.basename(video_path) + '.round.png')
        if os.path.exists(thumb_path):
            return thumb_path

        size = 160
        frame_img = None
        if CV2_AVAILABLE:
            try:
                cap = cv2.VideoCapture(video_path)
                success, frame = cap.read()
                cap.release()
                if success:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame_img = Image.fromarray(frame_rgb)
            except Exception:
                frame_img = None

        if frame_img is None:
            frame_img = Image.new('RGB', (size, size), color=(45, 45, 45))
        else:
            w, h = frame_img.size
            side = min(w, h)
            left, top = (w - side) // 2, (h - side) // 2
            frame_img = frame_img.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)

        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
        frame_img = frame_img.convert('RGBA')
        frame_img.putalpha(mask)

        draw = ImageDraw.Draw(frame_img)
        cx, cy = size // 2, size // 2
        r = size // 6
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0, 150))
        t = r * 0.9
        draw.polygon([
            (cx - t * 0.35, cy - t * 0.55),
            (cx - t * 0.35, cy + t * 0.55),
            (cx + t * 0.65, cy),
        ], fill=(255, 255, 255, 235))

        try:
            frame_img.save(thumb_path, 'PNG')
            return thumb_path
        except Exception:
            return None

    def _handle_anchor_click(self, url: QUrl):
        scheme = url.scheme()
        path = url.path()
        if sys.platform.startswith('win') and path.startswith('/'):
            path = path[1:]
        if scheme == 'openfile':
            open_file(path)
        elif scheme == 'playvideo':
            dlg = VideoPlayerDialog(path, self)
            dlg.exec()
        elif scheme == 'playaudio':
            dlg = AudioPlayerDialog(path, self)
            dlg.exec()

    def _chat_context_menu(self, pos):
        anchor = self.chat_view.anchorAt(pos)
        menu = QMenu(self)
        if anchor:
            url = QUrl(anchor)
            scheme = url.scheme()
            path = url.path()
            if sys.platform.startswith('win') and path.startswith('/'):
                path = path[1:]
            if scheme == 'openfile':
                menu.addAction("Открыть", lambda: open_file(path))
                menu.addAction("Скопировать изображение", lambda: self._copy_image_to_clipboard(path))
                menu.addAction("Скопировать путь к файлу", lambda: QApplication.clipboard().setText(path))
            elif scheme == 'playvideo':
                menu.addAction("Посмотреть", lambda: self._handle_anchor_click(url))
                menu.addAction("Открыть во внешнем плеере", lambda: open_file(path))
                menu.addAction("Скопировать путь к файлу", lambda: QApplication.clipboard().setText(path))
            elif scheme == 'playaudio':
                menu.addAction("Прослушать", lambda: self._handle_anchor_click(url))
                menu.addAction("Открыть во внешнем плеере", lambda: open_file(path))
                menu.addAction("Скопировать путь к файлу", lambda: QApplication.clipboard().setText(path))
        else:
            menu.addAction("Копировать", self.chat_view.copy)
            menu.addAction("Выделить всё", self.chat_view.selectAll)
        menu.exec(self.chat_view.mapToGlobal(pos))

    def _copy_image_to_clipboard(self, path):
        image = QImage(path)
        if image.isNull():
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить изображение")
            return
        QApplication.clipboard().setImage(image)

    # ---------- Комнаты ----------
    def add_room_dialog(self):
        name, ok = QInputDialog.getText(self, "Новый чат", "Название чата:")
        if not ok or not name.strip():
            return
        try:
            send_frame(self.client, {'type': 'room_create', 'name': name.strip()})
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось отправить запрос на сервер")

    def request_room_list(self):
        try:
            send_frame(self.client, {'type': 'room_list_request'})
        except Exception:
            pass

    def _update_rooms_list(self, rooms):
        if 'general' not in rooms:
            rooms = ['general'] + rooms
        self.rooms = rooms
        self.rooms_list.clear()
        self.rooms_list.addItems(rooms)

    def _handle_room_create_result(self, header):
        status = header.get('status')
        name = header.get('name', '')
        texts = {
            'ok': f'✅ Чат "{name}" создан!',
            'exists': f'Чат "{name}" уже существует.',
            'reserved': 'Название "general" зарезервировано.',
            'invalid': 'Введи название чата.',
            'too_long': 'Слишком длинное название.',
        }
        QMessageBox.information(self, "Чаты", texts.get(status, 'Неизвестный ответ сервера'))
        if status == 'ok':
            self.request_room_list()

    # ---------- Приватные беседы ----------
    def add_private_chat_dialog(self):
        name, ok = QInputDialog.getText(self, "Приватная беседа", "Название беседы:")
        if not ok or not name.strip():
            return
        invitees_text, ok2 = QInputDialog.getText(
            self, "Пригласить участников",
            "Никнеймы через запятую (можно несколько).\nМожно позвать и бота — просто впиши: ИИ"
        )
        if not ok2:
            return
        invitees = [n.strip() for n in invitees_text.split(',') if n.strip()]
        try:
            send_frame(self.client, {'type': 'private_chat_create', 'name': name.strip(), 'invitees': invitees})
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось отправить запрос на сервер")

    def request_private_chat_list(self):
        try:
            send_frame(self.client, {'type': 'private_chat_list_request'})
        except Exception:
            pass

    def _update_private_chats_list(self, chats):
        self.private_chats = {c['id']: c['name'] for c in chats}
        self.private_list.clear()
        for c in chats:
            item = QListWidgetItem(c['name'])
            item.setData(Qt.UserRole, c['id'])
            self.private_list.addItem(item)

    def _handle_private_chat_create_result(self, header):
        status = header.get('status')
        name = header.get('name', '')
        skipped = header.get('skipped') or []
        texts = {
            'ok': f'✅ Приватная беседа "{name}" создана!',
            'invalid': 'Введи название беседы.',
        }
        message = texts.get(status, 'Неизвестный ответ сервера')
        if status == 'ok' and skipped:
            message += f'\n\n⚠️ Эти никнеймы не найдены и не добавлены: {", ".join(skipped)}'
        QMessageBox.information(self, "Приватные беседы", message)
        if status == 'ok':
            self.request_private_chat_list()

    def _handle_private_chat_invited(self, header):
        chat_id = header.get('chat_id')
        name = header.get('name', '')
        creator = header.get('creator', '???')
        QMessageBox.information(
            self, "Приглашение",
            f'{creator} пригласил(а) тебя в приватную беседу "{name}"!'
        )
        self.request_private_chat_list()

    def _load_private_chat_history(self, chat_id, messages):
        lines = []
        if not messages:
            lines.append('Переписки пока нет — напиши первым!')
        for m in messages:
            ts = short_time(m.get('timestamp', ''))
            sender = m.get('sender', '???')
            if m.get('msg_type') == 'text':
                lines.append(f"[{ts}] {self._message_html(sender, m.get('text', ''))}")
            elif m.get('msg_type') == 'file':
                filename = m.get('filename', '')
                lines.append(f"[{ts}] 📎 {html.escape(sender)} отправил файл: {html.escape(filename)}")
                local_path = self._find_local_file(filename)
                if local_path:
                    lines.append(self._media_html(local_path, filename))
        key = f'private:{chat_id}'
        self.room_texts[key] = '<br>'.join(lines) + '<br>'
        if self._current_room_key() == key:
            self._render_current_view()

    def _load_history(self, messages):
        if not messages:
            return
        lines = ['<i>── История чата ──</i>']
        for m in messages:
            ts = short_time(m.get('timestamp', ''))
            sender = m.get('sender', '???')
            if m.get('msg_type') == 'text':
                lines.append(f"[{ts}] {self._message_html(sender, m.get('text', ''))}")
            elif m.get('msg_type') == 'file':
                filename = m.get('filename', '')
                lines.append(f"[{ts}] 📎 {html.escape(sender)} отправил файл: {html.escape(filename)}")
                local_path = self._find_local_file(filename)
                if local_path:
                    lines.append(self._media_html(local_path, filename))
        lines.append('<i>── Конец истории ──</i>')
        self.room_texts['general'] = '<br>'.join(lines) + '<br>'
        if self.current_view == ('room', 'general'):
            self._render_current_view()

    def _load_room_history(self, room, messages):
        if room == 'general':
            return
        lines = []
        if not messages:
            lines.append(f'В чате «{html.escape(room)}» пока пусто — напиши первым!')
        for m in messages:
            ts = short_time(m.get('timestamp', ''))
            sender = m.get('sender', '???')
            if m.get('msg_type') == 'text':
                lines.append(f"[{ts}] {self._message_html(sender, m.get('text', ''))}")
            elif m.get('msg_type') == 'file':
                filename = m.get('filename', '')
                lines.append(f"[{ts}] 📎 {html.escape(sender)} отправил файл: {html.escape(filename)}")
                local_path = self._find_local_file(filename)
                if local_path:
                    lines.append(self._media_html(local_path, filename))
        self.room_texts[room] = '<br>'.join(lines) + '<br>'
        if self.current_view == ('room', room):
            self._render_current_view()

    def _load_dm_history(self, target, messages):
        lines = []
        if not messages:
            lines.append('Переписки пока нет — напиши первым!')
        for m in messages:
            ts = short_time(m.get('timestamp', ''))
            sender = m.get('sender', '???')
            if m.get('msg_type') == 'file':
                filename = m.get('filename', '')
                lines.append(f"[{ts}] 📎 {html.escape(sender)} отправил файл: {html.escape(filename)}")
                local_path = self._find_local_file(filename)
                if local_path:
                    lines.append(self._media_html(local_path, filename))
            else:
                lines.append(f"[{ts}] {self._message_html(sender, m.get('text', ''))}")
        self.dm_texts[target] = '<br>'.join(lines) + '<br>'
        if self.current_view == ('dm', target):
            self._render_current_view()
        self._add_dm_to_list(target)

    def _find_local_file(self, filename):
        if not filename:
            return None
        candidate = os.path.join(get_base_dir(), 'received_files', filename)
        return candidate if os.path.exists(candidate) else None

    def _cache_sent_file(self, path, filename):
        try:
            folder = os.path.join(get_base_dir(), 'received_files')
            os.makedirs(folder, exist_ok=True)
            target = os.path.join(folder, filename)
            if not os.path.exists(target):
                shutil.copyfile(path, target)
        except Exception:
            pass

    # ---------- Входящие сообщения ----------
    def _on_incoming_room_text(self, room, nick, text):
        self._append_html(room, self._message_html(nick, text))
        if room != 'general' and self._current_room_key() != room:
            if room.startswith('private:'):
                chat_id = room.split(':', 1)[1]
                label = f"🔒 {self.private_chats.get(chat_id, chat_id)}"
            else:
                label = room
            self._append_html('general', f'💬 Новое сообщение в «{html.escape(label)}»')

    def _on_incoming_file(self, room, nick, filename, data):
        save_path = self._save_received_file(filename, data)
        line = f"📎 {html.escape(nick)} отправил файл: {html.escape(filename)}" + self._media_html(save_path, filename)
        self._append_html(room, line)

    def _on_incoming_dm(self, nick, text):
        self._add_dm_to_list(nick)
        self._append_html(nick, self._message_html(nick, text), is_dm_key=True)
        kind, target = self.current_view
        if not (kind == 'dm' and target == nick):
            self._append_html('general', f'📩 Новое личное сообщение от {html.escape(nick)}')

    def _on_incoming_dm_file(self, nick, filename, data):
        self._add_dm_to_list(nick)
        save_path = self._save_received_file(filename, data)
        line = f"📎 {html.escape(nick)} отправил файл: {html.escape(filename)}" + self._media_html(save_path, filename)
        self._append_html(nick, line, is_dm_key=True)

    def _save_received_file(self, filename, data):
        folder = os.path.join(get_base_dir(), 'received_files')
        os.makedirs(folder, exist_ok=True)
        save_path = os.path.join(folder, filename)
        base, ext = os.path.splitext(save_path)
        counter = 1
        while os.path.exists(save_path):
            save_path = f"{base}_{counter}{ext}"
            counter += 1
        with open(save_path, 'wb') as f:
            f.write(data)
        return save_path

    # ---------- Отправка ----------
    def send_message(self):
        message = self.entry.text().strip()
        if not message:
            return
        self.entry.clear()
        if message.lower() == '/exit':
            self.close()
            return
        if self._try_send_image_url(message):
            self.entry.clear()
            return

        kind, target = self.current_view
        try:
            if kind == 'room':
                send_frame(self.client, {'type': 'text', 'nick': self.nickname, 'text': message, 'room': target})
                self._append_html(target, self._message_html(self.nickname, message))
            elif kind == 'private':
                room_key = f'private:{target}'

                # PATCH: управление участниками приватной беседы командами в поле сообщения.
                # /invite Ник  — пригласить участника
                # /remove Ник  — удалить участника
                lower = message.lower()
                if lower.startswith('/invite ') or lower.startswith('/add '):
                    nick = message.split(' ', 1)[1].strip()
                    if nick:
                        send_frame(self.client, {
                            'type': 'private_chat_invite_member',
                            'chat_id': target, 'target': nick,
                        })
                    return
                if lower.startswith('/remove ') or lower.startswith('/kick '):
                    nick = message.split(' ', 1)[1].strip()
                    if nick:
                        send_frame(self.client, {
                            'type': 'private_chat_remove_member',
                            'chat_id': target, 'target': nick,
                        })
                    return

                send_frame(self.client, {'type': 'text', 'nick': self.nickname, 'text': message, 'room': room_key})
                self._append_html(room_key, self._message_html(self.nickname, message))
            else:
                send_frame(self.client, {'type': 'dm', 'target': target, 'text': message})
                self._append_html(target, self._message_html(self.nickname, message), is_dm_key=True)
                self._add_dm_to_list(target)
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось отправить сообщение")


    # ---------- BUKKAX CHESS START ----------
    def open_chess_start_dialog(self):
        try:
            from PySide6.QtWidgets import QInputDialog, QMessageBox
            choice, ok = chess_get_item(
                self,
                "Шахматы",
                "Выбери режим:",
                ["С ботом", "С другом"],
                0,
                False,
            )
            if not ok:
                return
            if choice == "С ботом":
                self.open_chess_bot_dialog()
                return
            nick, ok = chess_get_text(self, "Шахматы", "Ник друга для игры:")
            if not ok:
                return
            self.start_chess_with(nick.strip())
        except Exception as e:
            try:
                chess_critical(self, 'Шахматы', 'Ошибка открытия шахмат:\n' + str(e))
            except Exception:
                pass

    def start_chess_with(self, nick):
        nick = (nick or '').strip()
        if not nick:
            chess_info(self, "Шахматы", "Введите ник друга.")
            return
        if nick == self.nickname:
            chess_info(self, "Шахматы", "С самим собой играть нельзя.")
            return
        game_id = f"chess_{uuid.uuid4().hex[:16]}"
        if not hasattr(self, 'chess_pending_invites'):
            self.chess_pending_invites = {}
        self.chess_pending_invites[game_id] = nick
        try:
            send_frame(self.client, {'type': 'chess_invite', 'target': nick, 'game_id': game_id})
            self._append_html('general', f"♟ Отправляю приглашение в шахматы игроку {html.escape(nick)}...")
            # Если server.py не патчен или не перезапущен, ответа chess_invite_result не будет.
            QTimer.singleShot(4500, lambda gid=game_id: self._check_chess_invite_timeout(gid))
        except Exception as e:
            self.chess_pending_invites.pop(game_id, None)
            chess_warning(self, "Шахматы", f"Не удалось отправить приглашение: {e}")

    def _open_chess_dialog(self, game_id, opponent, color):
        if not hasattr(self, 'chess_dialogs'):
            self.chess_dialogs = {}
        if game_id in self.chess_dialogs and self.chess_dialogs[game_id]:
            dlg = self.chess_dialogs[game_id]
            dlg.showNormal()
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            return dlg
        dlg = ChessDialog(
            self, self.nickname, opponent, int(color), game_id,
            send_move_cb=self._send_chess_move,
            send_restart_cb=self._send_chess_restart,
            send_resign_cb=self._send_chess_resign,
        )
        dlg.send_close_cb = self._send_chess_close
        self.chess_dialogs[game_id] = dlg
        dlg.destroyed.connect(lambda *_args, gid=game_id: self.chess_dialogs.pop(gid, None))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    def _send_chess_move(self, game_id, opponent, src, dst, promotion=''):
        try:
            send_frame(self.client, {
                'type': 'chess_move', 'target': opponent, 'game_id': game_id,
                'src': src, 'dst': dst, 'promotion': promotion or '',
            })
        except Exception:
            chess_warning(self, "Шахматы", "Не удалось отправить ход сопернику.")

    def _send_chess_restart(self, game_id, opponent):
        try:
            send_frame(self.client, {'type': 'chess_restart', 'target': opponent, 'game_id': game_id})
        except Exception:
            chess_warning(self, "Шахматы", "Не удалось отправить новую партию сопернику.")

    def _send_chess_resign(self, game_id, opponent):
        try:
            send_frame(self.client, {'type': 'chess_resign', 'target': opponent, 'game_id': game_id})
        except Exception:
            pass

    def _send_chess_close(self, game_id, opponent):
        try:
            send_frame(
                self.client,
                {
                    'type': 'chess_close',
                    'target': opponent,
                    'game_id': game_id,
                }
            )
        except Exception:
            pass

    def _handle_chess_invite_result(self, header):
        status = header.get('status')
        target = header.get('target', '')
        if status == 'offline':
            chess_info(self, "Шахматы", f"{target} сейчас не в сети.")
        elif status == 'self':
            chess_info(self, "Шахматы", "С самим собой играть нельзя.")
        elif status == 'sent':
            white = header.get('white') or ''
            black = header.get('black') or ''
            extra = ''
            if white and black:
                extra = f". Белые: {html.escape(white)}, чёрные: {html.escape(black)}"
            self._append_html('general', f"♟ Приглашение в шахматы отправлено игроку {html.escape(target)}{extra}")

    def _handle_chess_invite(self, header):
        from_nick = header.get('from', '???')
        game_id = header.get('game_id') or f"chess_{uuid.uuid4().hex[:16]}"
        white = header.get('white') or ''
        black = header.get('black') or ''
        color_text = ''
        if white and black:
            my_color_preview = 0 if getattr(self, 'nickname', '') == white else 1
            color_text = ' Вы будете играть белыми.' if my_color_preview == 0 else ' Вы будете играть чёрными.'
        answer = chess_question(
            self, "Шахматы", f"{from_nick} приглашает сыграть в шахматы.{color_text} Принять?"
        )
        accepted = answer == QMessageBox.Yes
        try:
            send_frame(self.client, {
                'type': 'chess_accept', 'target': from_nick,
                'game_id': game_id, 'accepted': accepted,
                'white': white, 'black': black,
            })
        except Exception:
            chess_warning(self, "Шахматы", "Не удалось ответить на приглашение.")
            return
        if accepted:
            my_color = 0 if white and getattr(self, 'nickname', '') == white else 1
            self._open_chess_dialog(game_id, from_nick, my_color)

    def _handle_chess_accept(self, header):
        from_nick = header.get('from', '???')
        game_id = header.get('game_id')
        if not header.get('accepted'):
            chess_info(self, "Шахматы", f"{from_nick} отказался играть.")
            return
        white = header.get('white') or ''
        black = header.get('black') or ''
        my_color = 0 if white and getattr(self, 'nickname', '') == white else 1 if black and getattr(self, 'nickname', '') == black else 0
        self._open_chess_dialog(game_id, from_nick, my_color)

    def _handle_chess_move(self, header):
        game_id = header.get('game_id')
        from_nick = header.get('from', '???')
        if not hasattr(self, 'chess_dialogs'):
            self.chess_dialogs = {}
        dlg = self.chess_dialogs.get(game_id)
        if not dlg:
            dlg = self._open_chess_dialog(game_id, from_nick, 1)
        dlg.apply_remote_move(header.get('src'), header.get('dst'), header.get('promotion', ''))
        dlg.showNormal()
        dlg.raise_()
        dlg.activateWindow()

    def _handle_chess_restart(self, header):
        game_id = header.get('game_id')
        from_nick = header.get('from', '???')
        dlg = getattr(self, 'chess_dialogs', {}).get(game_id)
        if dlg:
            dlg.remote_restart()
        else:
            self._append_html('general', f"♟ {html.escape(from_nick)} начал новую партию в шахматы")

    def _handle_chess_resign(self, header):
        game_id = header.get('game_id')
        from_nick = header.get('from', '???')
        dlg = getattr(self, 'chess_dialogs', {}).get(game_id)
        if dlg:
            dlg.remote_resign()
        else:
            self._append_html('general', f"♟ {html.escape(from_nick)} сдался в шахматах")
    def _handle_chess_close(self, header):
        game_id = header.get('game_id')
        from_nick = header.get('from', '???')

        dialogs = getattr(
            self,
            'chess_dialogs',
            {}
        )

        dlg = dialogs.pop(
            game_id,
            None
        )

        if dlg:
            try:
                dlg.remote_close()
            except Exception:
                try:
                    dlg.close()
                except Exception:
                    pass

        # Не создаём новое окно, если оно уже было закрыто.
        # Просто фиксируем событие в общем чате.
        try:
            self._append_html(
                'general',
                f"♟ {html.escape(from_nick)} вышел из шахматной партии"
            )
        except Exception:
            pass

    def open_chess_bot_dialog(self):
        try:
            import uuid as _uuid
            import traceback as _traceback
            from PySide6.QtWidgets import QMessageBox as _QMessageBox
            from bukkax_chess_qt import ChessBotDialog as _ChessBotDialog

            if not hasattr(self, 'chess_dialogs'):
                self.chess_dialogs = {}
            if not hasattr(self, 'chess_bot_dialogs'):
                self.chess_bot_dialogs = {}

            nick = getattr(self, 'nickname', '') or 'Игрок'
            game_id = f"chess_bot_{_uuid.uuid4().hex[:16]}"
            dlg = _ChessBotDialog(self, nick, game_id=game_id)
            self.chess_dialogs[game_id] = dlg
            self.chess_bot_dialogs[game_id] = dlg
            dlg.destroyed.connect(lambda *_args, gid=game_id: (self.chess_dialogs.pop(gid, None), self.chess_bot_dialogs.pop(gid, None)))
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            return dlg
        except Exception as e:
            try:
                _chess_critical(self, 'Шахматы', 'Не удалось открыть игру с ботом:\n' + str(e))
            except Exception:
                pass
            try:
                with open('chess_bot_error.log', 'a', encoding='utf-8') as f:
                    f.write('\n--- chess bot open error ---\n')
                    f.write(_traceback.format_exc())
            except Exception:
                pass
            return None

    # ---------- BUKKAX CHESS END ----------

    # ---------- BUKKAX music start----------
    def _start_music_app(self):
        from music_player import MusicWindow

        if not hasattr(self, "music_window") or self.music_window is None:
            self.music_window = MusicWindow()
            self.music_window.destroyed.connect(
                lambda: setattr(self, "music_window", None)
            )

        self.music_window.show()
        self.music_window.raise_()
        self.music_window.activateWindow()
    #---------- BUKKAX music end----------

    # ---------- Голосовые звонки ----------
    # BUKKAX CALL RINGTONE PATCH
    def _ringtone_path(self):
        return get_resource_path(
            os.path.join("sounds", "ringtone.wav")
        )

    def _start_call_ringtone(self):
        """Запускает мелодию ожидания/входящего звонка по кругу."""
        try:
            path = self._ringtone_path()
            if not os.path.exists(path):
                print(f"Рингтон не найден: {path}")
                return

            # Если уже играет — второй экземпляр не создаём.
            if (
                self.ringtone_player is not None
                and self.ringtone_player.playbackState()
                == QMediaPlayer.PlayingState
            ):
                return

            self._stop_call_ringtone()

            self.ringtone_player = QMediaPlayer(self)
            self.ringtone_audio_output = QAudioOutput(self)
            self.ringtone_audio_output.setVolume(0.65)
            self.ringtone_player.setAudioOutput(
                self.ringtone_audio_output
            )
            self.ringtone_player.setSource(
                QUrl.fromLocalFile(path)
            )

            # На разных версиях Qt setLoops может вести себя немного
            # по-разному, поэтому дополнительно оставляем обработчик
            # EndOfMedia ниже.
            try:
                self.ringtone_player.setLoops(
                    QMediaPlayer.Infinite
                )
            except Exception:
                pass

            self.ringtone_player.mediaStatusChanged.connect(
                self._on_ringtone_media_status
            )
            self.ringtone_player.play()

        except Exception as e:
            print(f"Ошибка запуска рингтона: {e}")

    def _on_ringtone_media_status(self, status):
        """Запасной способ зациклить мелодию."""
        try:
            if (
                status == QMediaPlayer.MediaStatus.EndOfMedia
                and self.ringtone_player is not None
            ):
                self.ringtone_player.setPosition(0)
                self.ringtone_player.play()
        except Exception:
            pass

    def _stop_call_ringtone(self):
        try:
            if self.ringtone_player is not None:
                self.ringtone_player.stop()
                self.ringtone_player.deleteLater()
        except Exception:
            pass

        try:
            if self.ringtone_audio_output is not None:
                self.ringtone_audio_output.deleteLater()
        except Exception:
            pass

        self.ringtone_player = None
        self.ringtone_audio_output = None

    def start_call(self, nick, video=False):
        if self.current_call:
            QMessageBox.information(self, "Звонок", "У тебя уже есть активный звонок.")
            return
        try:
            send_frame(self.client, {'type': 'call_offer', 'target': nick, 'video': video})
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось отправить запрос на звонок")
            return
        self.current_call = {
            'call_id': None, 'peer_nick': nick, 'role': None, 'state': 'ringing_out', 'video': video,
        }
        icon = "📹" if video else "📞"
        self.call_dialog = CallStatusDialog(f"{icon} Звоним {nick}...", on_hangup=self.end_call, video=video, parent=self)
        self.call_dialog.show()

    def _handle_incoming_call_offer(self, header):
        call_id = header.get('call_id')
        from_nick = header.get('from', '???')
        video = bool(header.get('video'))
        if self.current_call:
            try:
                send_frame(self.client, {'type': 'call_answer', 'call_id': call_id, 'accepted': False})
            except Exception:
                pass
            return
        self.incoming_call_dialog = IncomingCallDialog(
            from_nick, video,
            on_accept=lambda: self._accept_call(call_id, from_nick, video),
            on_decline=lambda: self._decline_call(call_id),
            parent=self,
        )
        self.incoming_call_dialog.show()
        self._start_call_ringtone()

    def _accept_call(self, call_id, from_nick, video):
        self._stop_call_ringtone()
        if self.incoming_call_dialog:
            self.incoming_call_dialog.close()
            self.incoming_call_dialog = None
        self.current_call = {
            'call_id': call_id, 'peer_nick': from_nick, 'role': None, 'state': 'connecting', 'video': video,
        }
        try:
            send_frame(self.client, {'type': 'call_answer', 'call_id': call_id, 'accepted': True})
        except Exception:
            self.current_call = None
            QMessageBox.warning(self, "Ошибка", "Не удалось принять звонок")

    def _decline_call(self, call_id):
        self._stop_call_ringtone()
        if self.incoming_call_dialog:
            self.incoming_call_dialog.close()
            self.incoming_call_dialog = None
        try:
            send_frame(self.client, {'type': 'call_answer', 'call_id': call_id, 'accepted': False})
        except Exception:
            pass

    def _handle_call_declined(self):
        peer = self.current_call.get('peer_nick', 'Собеседник') if self.current_call else 'Собеседник'
        QMessageBox.information(self, "Звонок", f"{peer} отклонил(а) звонок.")
        self._cleanup_call()

    def _handle_call_result(self, header):
        if header.get('status') == 'offline':
            QMessageBox.information(self, "Звонок", "Пользователь сейчас не в сети.")
            self._cleanup_call()
        elif header.get('status') == 'self':
            QMessageBox.information(self, "Звонок", "Нельзя позвонить самому себе :)")
            self._cleanup_call()

    def _handle_call_started(self, header):
        self._stop_call_ringtone()
        if not self.current_call:
            return
        self.current_call['call_id'] = header.get('call_id')
        self.current_call['role'] = header.get('role')
        self.current_call['state'] = 'active'
        self._setup_audio_streams()
        self._send_call_hello_packet()
        is_video = self.current_call.get('video', False)
        peer = self.current_call['peer_nick']
        if not self.call_dialog:
            self.call_dialog = CallStatusDialog(
                f"📞 Разговор с {peer}", on_hangup=self.end_call, video=is_video, parent=self
            )
            self.call_dialog.show()
        else:
            self.call_dialog.set_status(f"📞 Разговор с {peer}")
        if is_video:
            self._setup_video_capture()
            self._send_video_hello_packet()

    def _handle_call_ended(self):
        peer = self.current_call.get('peer_nick', '') if self.current_call else ''
        self._cleanup_call()
        if peer:
            self._append_html('general', f"📴 Звонок с {html.escape(peer)} завершён")

    def end_call(self):
        if self.current_call and self.current_call.get('call_id'):
            try:
                send_frame(self.client, {'type': 'call_end', 'call_id': self.current_call['call_id']})
            except Exception:
                pass
        self._cleanup_call()

    def _cleanup_call(self):
        self._stop_call_ringtone()
        self._teardown_audio_streams()
        self._teardown_video_capture()
        self.current_call = None
        if self.call_dialog:
            self.call_dialog.close()
            self.call_dialog = None
        if self.incoming_call_dialog:
            self.incoming_call_dialog.close()
            self.incoming_call_dialog = None

    # ---------- Аудио потоки с поддержкой настроек ----------
    def _setup_audio_streams(self):
        audio_format = QAudioFormat()
        audio_format.setSampleRate(self.audio_sample_rate)
        audio_format.setChannelCount(1)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        input_dev = self.selected_input_device if self.selected_input_device else QMediaDevices.defaultAudioInput()
        output_dev = self.selected_output_device if self.selected_output_device else QMediaDevices.defaultAudioOutput()

        try:
            self.audio_source = QAudioSource(input_dev, audio_format, self)
            self.mic_io = self.audio_source.start()
            self.mic_io.readyRead.connect(self._on_mic_data)
        except Exception as e:
            QMessageBox.warning(self, "Микрофон", f"Не удалось включить микрофон: {e}")

        try:
            self.audio_sink = QAudioSink(output_dev, audio_format, self)
            self.speaker_io = self.audio_sink.start()
        except Exception as e:
            QMessageBox.warning(self, "Динамики", f"Не удалось включить воспроизведение: {e}")

    def _recreate_audio_streams(self):
        """Пересоздаёт аудио-потоки при смене устройств/параметров во время звонка."""
        self._teardown_audio_streams()
        if self.current_call or self.group_call:
            self._setup_audio_streams()

    def _teardown_audio_streams(self):
        try:
            if self.audio_source:
                self.audio_source.stop()
        except Exception:
            pass
        try:
            if self.audio_sink:
                self.audio_sink.stop()
        except Exception:
            pass
        self.audio_source = None
        self.audio_sink = None
        self.mic_io = None
        self.speaker_io = None

    # ---------- Обработка микрофона с усилением и шумоподавлением ----------
    def _apply_gain(self, data, gain):
        """Умножает 16-бит PCM на gain (0..2) с использованием numpy (если доступен)."""
        if gain == 1.0 or len(data) == 0:
            return data
        try:
            # Используем numpy для скорости
            arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            arr *= gain
            np.clip(arr, -32768, 32767, out=arr)
            return arr.astype(np.int16).tobytes()
        except Exception:
            # fallback на array
            import array
            samples = array.array('h')
            samples.frombytes(data)
            for i in range(len(samples)):
                val = int(samples[i] * gain)
                if val > 32767: val = 32767
                elif val < -32768: val = -32768
                samples[i] = val
            return samples.tobytes()

    def _apply_noise_reduction(self, data):
        """Применяет шумоподавление через pyrnnoise, если доступно и включено."""
        if (not self.noise_reduction_enabled or
            not RNNOISE_AVAILABLE or
            self._rnnoise_denoiser is None or
            len(data) == 0):
            return data

        try:
            # Преобразуем байты в массив int16
            audio_array = np.frombuffer(data, dtype=np.int16)

            # Обрабатываем чанк (pyrnnoise сам разобьёт его на фреймы)
            # denoise_chunk возвращает генератор пар (frame_index, denoised_audio)
            for _, denoised_audio in self._rnnoise_denoiser.denoise_chunk(audio_array):
                # Возвращаем обработанный сигнал в байтах
                return denoised_audio.astype(np.int16).tobytes()

            # Если по какой-то причине ничего не вернулось, возвращаем исходные данные
            return data
        except Exception:
            return data

    def _on_mic_data(self):
        if not self.mic_io:
            return
        data = bytes(self.mic_io.readAll())
        if not data:
            return

        # 1) Усиление
        data = self._apply_gain(data, self.mic_gain)

        # 2) Шумоподавление
        data = self._apply_noise_reduction(data)

        # Отправка в звонок
        if self.current_call and self.current_call.get('state') == 'active':
            packet = self._call_packet_prefix() + data
            self.call_udp_socket.writeDatagram(packet, QHostAddress(SERVER_IP), VOICE_UDP_PORT)
        elif self.group_call:
            packet = self._group_call_packet_prefix() + data
            self.call_udp_socket.writeDatagram(packet, QHostAddress(SERVER_IP), VOICE_UDP_PORT)

    # ---------- Воспроизведение с усилением ----------
    def _on_call_udp_data(self):
        while self.call_udp_socket.hasPendingDatagrams():
            size = self.call_udp_socket.pendingDatagramSize()
            datagram, host, port = self.call_udp_socket.readDatagram(size)
            if len(datagram) <= 17:
                continue

            if self.group_call:
                member_id = datagram[16]
                self.group_audio_buffers.setdefault(member_id, bytearray()).extend(datagram[17:])
            elif self.speaker_io:
                audio_data = datagram[17:]
                # Применяем усиление динамика перед записью
                if self.speaker_gain != 1.0:
                    audio_data = self._apply_gain(audio_data, self.speaker_gain)
                self.speaker_io.write(audio_data)

    def _mix_and_play_group_audio(self):
        if not self.speaker_io:
            return
        chunk_size = 1920  # 20 мс при 16 кГц (если частота другая, надо пересчитать)
        ready = [mid for mid, buf in self.group_audio_buffers.items() if len(buf) >= chunk_size]
        if not ready:
            return

        mixed = array.array('h', [0] * (chunk_size // 2))
        for mid in ready:
            buf = self.group_audio_buffers[mid]
            chunk = bytes(buf[:chunk_size])
            del buf[:chunk_size]
            samples = array.array('h')
            samples.frombytes(chunk)
            for i in range(len(samples)):
                val = mixed[i] + samples[i]
                if val > 32767: val = 32767
                elif val < -32768: val = -32768
                mixed[i] = val

        # Применяем усиление динамика ко всему миксу
        mixed_bytes = mixed.tobytes()
        if self.speaker_gain != 1.0:
            mixed_bytes = self._apply_gain(mixed_bytes, self.speaker_gain)
        self.speaker_io.write(mixed_bytes)

    # ---------- Остальные методы (без изменений) ----------
    def _call_packet_prefix(self):
        call_id = self.current_call['call_id']
        role_byte = b'0' if self.current_call['role'] == 0 else b'1'
        return call_id.encode('ascii') + role_byte

    def _group_call_packet_prefix(self):
        call_id = self.group_call['call_id']
        return call_id.encode('ascii') + bytes([self.group_call['member_id']])

    def _send_call_hello_packet(self):
        if not self.current_call or not self.current_call.get('call_id'):
            return
        self.call_udp_socket.writeDatagram(self._call_packet_prefix(), QHostAddress(SERVER_IP), VOICE_UDP_PORT)

    def _send_group_hello_packets(self):
        if not self.group_call:
            return
        prefix = self._group_call_packet_prefix()
        self.call_udp_socket.writeDatagram(prefix, QHostAddress(SERVER_IP), VOICE_UDP_PORT)
        self.video_udp_socket.writeDatagram(prefix, QHostAddress(SERVER_IP), VIDEO_UDP_PORT)

    # ---------- Видео ----------
    def _setup_video_capture(self):
        try:
            self.camera = QCamera(QMediaDevices.defaultVideoInput())
            self.video_sink = QVideoSink(self)
            self.capture_session = QMediaCaptureSession()
            self.capture_session.setCamera(self.camera)
            self.capture_session.setVideoSink(self.video_sink)
            self.video_sink.videoFrameChanged.connect(self._on_video_frame)
            self.camera.start()
        except Exception as e:
            QMessageBox.warning(self, "Камера", f"Не удалось включить камеру: {e}")

    def _teardown_video_capture(self):
        try:
            if self.camera:
                self.camera.stop()
        except Exception:
            pass
        self.camera = None
        self.video_sink = None
        self.capture_session = None

    def _send_video_hello_packet(self):
        if not self.current_call or not self.current_call.get('call_id'):
            return
        self.video_udp_socket.writeDatagram(self._call_packet_prefix(), QHostAddress(SERVER_IP), VIDEO_UDP_PORT)

    def _on_video_frame(self, frame):
        is_1to1_active = bool(self.current_call and self.current_call.get('state') == 'active')
        if not is_1to1_active and not self.group_call:
            return
        now = time.time()
        if now - self._last_frame_sent_time < 0.1:
            return
        self._last_frame_sent_time = now

        image = frame.toImage()
        if image.isNull():
            return
        small = image.scaled(240, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        if is_1to1_active and self.call_dialog:
            self.call_dialog.update_local_frame(QPixmap.fromImage(small))

        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        small.save(buffer, 'JPG', 45)
        jpeg_bytes = bytes(buffer.data())
        buffer.close()

        if not jpeg_bytes or len(jpeg_bytes) > 50000:
            return

        prefix = self._call_packet_prefix() if is_1to1_active else self._group_call_packet_prefix()
        packet = prefix + jpeg_bytes
        self.video_udp_socket.writeDatagram(packet, QHostAddress(SERVER_IP), VIDEO_UDP_PORT)

    def _on_call_video_udp_data(self):
        while self.video_udp_socket.hasPendingDatagrams():
            size = self.video_udp_socket.pendingDatagramSize()
            datagram, host, port = self.video_udp_socket.readDatagram(size)
            if len(datagram) <= 17:
                continue
            jpeg_bytes = datagram[17:]
            image = QImage()
            if not image.loadFromData(jpeg_bytes, 'JPG'):
                continue
            if self.group_call and self.group_call_dialog:
                member_id = datagram[16]
                self.group_call_dialog.update_member_frame(member_id, QPixmap.fromImage(image))
            elif self.call_dialog:
                self.call_dialog.update_remote_frame(QPixmap.fromImage(image))

    # ---------- Групповые звонки ----------
    def start_or_join_group_call(self):
        kind, target = self.current_view
        if kind != 'private':
            QMessageBox.information(
                self, "Групповой звонок",
                "Групповые звонки доступны только в приватных беседах — открой одну слева и попробуй снова."
            )
            return
        if self.group_call:
            QMessageBox.information(self, "Групповой звонок", "У тебя уже есть активный групповой звонок.")
            return
        try:
            send_frame(self.client, {'type': 'group_call_start', 'chat_id': target})
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось начать групповой звонок")

    def _handle_group_call_invite(self, header):
        call_id = header.get('call_id')
        chat_id = header.get('chat_id')
        from_nick = header.get('from', '???')
        if self.group_call:
            return
        chat_name = self.private_chats.get(chat_id, chat_id)
        answer = QMessageBox.question(
            self, "Групповой звонок",
            f'{from_nick} начал(а) групповой звонок в "{chat_name}". Присоединиться?'
        )
        if answer == QMessageBox.Yes:
            try:
                send_frame(self.client, {'type': 'group_call_join', 'call_id': call_id})
            except Exception:
                QMessageBox.warning(self, "Ошибка", "Не удалось присоединиться к звонку")

    def _handle_group_call_joined(self, header):
        call_id = header.get('call_id')
        member_id = header.get('member_id')
        members = {int(k): v for k, v in (header.get('members') or {}).items()}
        members[member_id] = self.nickname

        self.group_call = {'call_id': call_id, 'member_id': member_id}
        self.group_audio_buffers = {}

        self.group_call_dialog = GroupCallDialog(on_leave=self.leave_group_call, parent=self)
        self.group_call_dialog.set_members(members)
        self.group_call_dialog.show()

        self._setup_audio_streams()
        self._setup_video_capture()
        self._send_group_hello_packets()

        self.group_audio_timer = QTimer(self)
        self.group_audio_timer.timeout.connect(self._mix_and_play_group_audio)
        self.group_audio_timer.start(20)

    def _handle_group_call_member_joined(self, header):
        if not self.group_call or header.get('call_id') != self.group_call['call_id']:
            return
        mid = header.get('member_id')
        nick = header.get('nick')
        if self.group_call_dialog:
            self.group_call_dialog.add_member(mid, nick)

    def _handle_group_call_member_left(self, header):
        if not self.group_call or header.get('call_id') != self.group_call['call_id']:
            return
        mid = header.get('member_id')
        self.group_audio_buffers.pop(mid, None)
        if self.group_call_dialog:
            self.group_call_dialog.remove_member(mid)

    def leave_group_call(self):
        if self.group_call:
            try:
                send_frame(self.client, {'type': 'group_call_leave', 'call_id': self.group_call['call_id']})
            except Exception:
                pass
        self._cleanup_group_call()

    def _cleanup_group_call(self):
        self._teardown_audio_streams()
        self._teardown_video_capture()
        if self.group_audio_timer:
            self.group_audio_timer.stop()
            self.group_audio_timer = None
        self.group_audio_buffers = {}
        self.group_call = None
        if self.group_call_dialog:
            self.group_call_dialog.close()
            self.group_call_dialog = None

    # ---------- Голосовые сообщения (без изменений) ----------
    def _toggle_voice_recording(self):
        if getattr(self, '_voice_recording', False):
            self._stop_voice_recording()
        else:
            self._start_voice_recording()

    def _start_voice_recording(self):
        self._voice_recording = True
        self.voice_btn.setText("⏹")
        self._voice_start_time = time.time()
        self._voice_audio_input = QAudioInput()
        self._voice_capture_session = QMediaCaptureSession()
        self._voice_capture_session.setAudioInput(self._voice_audio_input)
        self._voice_recorder = QMediaRecorder()
        self._voice_capture_session.setRecorder(self._voice_recorder)
        media_format = QMediaFormat()
        media_format.setFileFormat(QMediaFormat.FileFormat.Mpeg4Audio)
        media_format.setAudioCodec(QMediaFormat.AudioCodec.AAC)
        self._voice_recorder.setMediaFormat(media_format)
        voice_dir = os.path.join(get_base_dir(), 'voice_temp')
        os.makedirs(voice_dir, exist_ok=True)
        self._voice_temp_path = os.path.join(voice_dir, f'raw_{int(time.time() * 1000)}.m4a')
        self._voice_recorder.setOutputLocation(QUrl.fromLocalFile(self._voice_temp_path))
        try:
            self._voice_recorder.record()
        except Exception as e:
            self._voice_recording = False
            self.voice_btn.setText("🎤")
            QMessageBox.warning(self, "Ошибка", f"Не удалось начать запись: {e}")

    def _stop_voice_recording(self):
        self._voice_recording = False
        self.voice_btn.setText("🎤")
        duration = time.time() - getattr(self, '_voice_start_time', time.time())
        try:
            self._voice_recorder.stop()
        except Exception:
            pass
        QTimer.singleShot(400, lambda: self._finish_voice_message(self._voice_temp_path, duration))

    def _finish_voice_message(self, path, duration):
        if not os.path.exists(path) or os.path.getsize(path) < 500:
            QMessageBox.information(self, "Голосовое", "Запись слишком короткая или не удалась.")
            return
        voice_dir = os.path.join(get_base_dir(), 'voice_temp')
        filename = f"voice_{int(duration)}s_{int(time.time() * 1000)}.m4a"
        final_path = os.path.join(voice_dir, filename)
        try:
            shutil.move(path, final_path)
            self._send_file_from_path(final_path)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось отправить голосовое: {e}")

    # ---------- Видеосообщения ----------
    def open_video_message_recorder(self):
        dlg = VideoMessageRecorderDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.recorded_path:
            duration = int(dlg.duration)
            video_dir = os.path.join(get_base_dir(), 'video_temp')
            filename = f"videomsg_{duration}s_{int(time.time() * 1000)}.mp4"
            final_path = os.path.join(video_dir, filename)
            try:
                shutil.move(dlg.recorded_path, final_path)
                self._send_file_from_path(final_path)
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось отправить видеосообщение: {e}")

    def send_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбери файл для отправки")
        if path:
            self._send_file_from_path(path)

    def _send_file_from_path(self, path):
        kind, target = self.current_view
        try:
            with open(path, 'rb') as f:
                data = f.read()
            filename = os.path.basename(path)
            self._cache_sent_file(path, filename)

            if kind == 'room':
                header = {'type': 'file', 'nick': self.nickname, 'filename': filename,
                          'size': len(data), 'room': target}
                send_frame(self.client, header, data)
                key, is_dm = target, False
            elif kind == 'private':
                room_key = f'private:{target}'
                header = {'type': 'file', 'nick': self.nickname, 'filename': filename,
                          'size': len(data), 'room': room_key}
                send_frame(self.client, header, data)
                key, is_dm = room_key, False
            else:
                header = {'type': 'dm_file', 'nick': self.nickname, 'target': target,
                          'filename': filename, 'size': len(data)}
                send_frame(self.client, header, data)
                key, is_dm = target, True
                self._add_dm_to_list(target)

            line = f"📎 Ты отправил файл: {html.escape(filename)}" + self._media_html(path, filename)
            self._append_html(key, line, is_dm_key=is_dm)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось отправить файл: {e}")

    def _handle_paste(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        # Скопирован файл из Проводника
        if mime.hasUrls():
            sent = False

            for url in mime.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()

                    if os.path.isfile(path):
                        self._send_file_from_path(path)
                        sent = True

            if sent:
                return True

        # Скопирована сама картинка / скриншот
        if mime.hasImage():
            image = clipboard.image()

            if not image.isNull():
                temp_dir = os.path.join(
                    get_base_dir(),
                    'clipboard_temp'
                )

                os.makedirs(
                    temp_dir,
                    exist_ok=True
                )

                temp_path = os.path.join(
                    temp_dir,
                    f'clipboard_{uuid.uuid4().hex}.png'
                )

                if image.save(temp_path, 'PNG'):
                    self._send_file_from_path(temp_path)
                    return True

        return False

    def eventFilter(self, obj, event):
        if obj is self.entry and event.type() == QEvent.KeyPress:

            if event.matches(QKeySequence.Paste):

                # Если это файл или изображение —
                # сами обрабатываем Ctrl+V
                if self._handle_paste():
                    return True

        return super().eventFilter(obj, event)


    # ---------- Смайлики ----------
    def open_emoji_picker(self):
        dlg = EmojiPicker(self._insert_emoji, self)
        dlg.exec()

    def _insert_emoji(self, emoji):
        self.entry.insert(emoji)

    # ---------- Друзья ----------
    def add_friend_dialog(self):
        nick, ok = QInputDialog.getText(self, "Добавить друга", "Никнейм друга:")
        if not ok or not nick.strip():
            return
        try:
            send_frame(self.client, {'type': 'friend_add', 'target': nick.strip()})
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось отправить запрос на сервер")

    def request_friend_list(self):
        try:
            send_frame(self.client, {'type': 'friend_list_request'})
        except Exception:
            pass

    def _update_friends_list(self, friends):
        self.friends = friends
        self.friends_list.clear()
        for f in friends:
            dot = '●' if f.get('online') else '○'
            self.friends_list.addItem(f"{dot} {f.get('nick')}")

    def _handle_friend_add_result(self, header):
        status = header.get('status')
        target = header.get('target', '')
        texts = {
            'ok': f'✅ {target} добавлен(а) в друзья!',
            'already': f'{target} уже у тебя в друзьях.',
            'not_found': f'Пользователь "{target}" ещё не заходил в чат.',
            'self': 'Нельзя добавить самого себя :)',
            'invalid': 'Введи никнейм.',
        }
        QMessageBox.information(self, "Друзья", texts.get(status, 'Неизвестный ответ сервера'))
        if status in ('ok', 'already'):
            self.request_friend_list()

    # ---------- Аватарки ----------
    def choose_avatar(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери аватарку", "", "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return
        try:
            data = None
            # Если Pillow есть — уменьшаем и приводим к PNG. Если Pillow нет — отправляем как есть.
            if PIL_AVAILABLE:
                img = Image.open(path).convert('RGBA')
                img.thumbnail((256, 256), Image.LANCZOS)
                buf = BytesIO()
                img.save(buf, 'PNG')
                data = buf.getvalue()
            else:
                with open(path, 'rb') as f:
                    data = f.read()

            if not data:
                raise RuntimeError('пустой файл')

            send_frame(self.client, {'type': 'avatar_set', 'size': len(data)}, data)
            local_path = self._avatar_cache_path(self.nickname)
            with open(local_path, 'wb') as f:
                f.write(data)
            self.avatar_cache[self.nickname] = local_path
            self._set_profile_avatar_if_open(self.nickname)
            try:
                self._render_current_view()
            except Exception:
                pass
            QMessageBox.information(self, "Аватар", "Аватар обновлён")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось установить аватарку: {e}")
    def _request_avatar(self, nick):
        if not nick or nick in self.pending_avatar_requests:
            return
        self.pending_avatar_requests.add(nick)
        try:
            send_frame(self.client, {'type': 'avatar_request', 'target': nick})
        except Exception:
            self.pending_avatar_requests.discard(nick)
    def _store_avatar(self, nick, data):
        self.pending_avatar_requests.discard(nick)
        if not nick or not data:
            return
        try:
            local_path = self._avatar_cache_path(nick)
            with open(local_path, 'wb') as f:
                f.write(data)
            self.avatar_cache[nick] = local_path
            self._set_profile_avatar_if_open(nick)
            try:
                self._render_current_view()
            except Exception:
                pass
        except Exception as e:
            print(f'avatar store error for {nick}: {e}')
    def open_sound_menu(self):
        menu = QMenu(self)
        label = "🔕 Выключить звук" if self.sound_enabled else "🔔 Включить звук"
        menu.addAction(label, self.toggle_sound)
        menu.addAction("🎵 Свой звук (.wav)", self.choose_notification_sound)
        menu.addAction("↩ Стандартный звук", self.reset_notification_sound)
        menu.exec(self.mapToGlobal(QPoint(0, 40)))

    def toggle_sound(self):
        self.sound_enabled = not self.sound_enabled

    def choose_notification_sound(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбери звук уведомления", "", "WAV файлы (*.wav)")
        if path:
            self.custom_sound_path = path

    def reset_notification_sound(self):
        self.custom_sound_path = None

    # ---------- Автообновление ----------
    # ---------- Автообновление ----------
    # ---------- Автообновление ----------
    def _prompt_update(self, latest_version):
        answer = QMessageBox.question(
            self,
            "Доступно обновление",
            f"Вышла новая версия {latest_version} (у тебя {CURRENT_VERSION}).\n\n"
            "Обновить сейчас? Во время скачивания приложение не будет зависать."
        )
        if answer == QMessageBox.Yes:
            self._download_and_apply_update(latest_version)

    def _download_and_apply_update(self, latest_version=None):
        if not getattr(sys, 'frozen', False):
            QMessageBox.information(
                self,
                "Обновление",
                "Автообновление работает только для собранного .exe, а не при запуске через python client_qt.py."
            )
            return

        latest_version = str(latest_version or '').strip()
        if not latest_version:
            QMessageBox.warning(self, "Обновление", "Не удалось определить номер новой версии.")
            return

        try:
            self.update_progress_dialog = QProgressDialog(
                "Скачиваю обновление...",
                None,
                0,
                100,
                self
            )
            self.update_progress_dialog.setWindowTitle("Обновление BUKKAX")
            self.update_progress_dialog.setWindowModality(Qt.ApplicationModal)
            self.update_progress_dialog.setAutoClose(False)
            self.update_progress_dialog.setAutoReset(False)
            self.update_progress_dialog.setMinimumDuration(0)
            self.update_progress_dialog.setValue(0)
            self.update_progress_dialog.show()

            self.update_download_thread = QThread()
            self.update_download_worker = UpdateDownloadWorker(latest_version)
            self.update_download_worker.moveToThread(self.update_download_thread)

            self.update_download_thread.started.connect(self.update_download_worker.run)
            self.update_download_worker.progress.connect(self._on_update_download_progress)
            self.update_download_worker.finished.connect(self._on_update_download_finished)
            self.update_download_worker.failed.connect(self._on_update_download_failed)

            self.update_download_worker.finished.connect(self.update_download_thread.quit)
            self.update_download_worker.failed.connect(self.update_download_thread.quit)
            self.update_download_thread.finished.connect(self.update_download_worker.deleteLater)
            self.update_download_thread.finished.connect(self.update_download_thread.deleteLater)

            self.update_download_thread.start()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка обновления", f"Не удалось начать обновление: {e}")

    def _on_update_download_progress(self, downloaded, total):
        try:
            if not hasattr(self, 'update_progress_dialog') or self.update_progress_dialog is None:
                return
            if total and total > 0:
                percent = int(downloaded * 100 / total)
                self.update_progress_dialog.setValue(max(0, min(100, percent)))
                mb_done = downloaded / 1024 / 1024
                mb_total = total / 1024 / 1024
                self.update_progress_dialog.setLabelText(f"Скачиваю обновление... {mb_done:.1f} / {mb_total:.1f} МБ")
            else:
                mb_done = downloaded / 1024 / 1024
                self.update_progress_dialog.setLabelText(f"Скачиваю обновление... {mb_done:.1f} МБ")
        except Exception:
            pass

    def _on_update_download_failed(self, error):
        try:
            if hasattr(self, 'update_progress_dialog') and self.update_progress_dialog:
                self.update_progress_dialog.close()
                self.update_progress_dialog = None
        except Exception:
            pass
        QMessageBox.critical(
            self,
            "Ошибка обновления",
            "Не удалось скачать обновление.\n\n"
            f"Причина: {error}\n\n"
            "Проверь, что на сервере открыт порт обновлений и лежит файл updates/Bukkax.exe."
        )

    def _on_update_download_finished(self, new_exe, new_version_file, latest_version):
        try:
            if hasattr(self, 'update_progress_dialog') and self.update_progress_dialog:
                self.update_progress_dialog.setValue(100)
                self.update_progress_dialog.setLabelText("Обновление скачано. Перезапускаю приложение...")
        except Exception:
            pass
        self._run_update_bat_and_exit(new_exe, new_version_file, latest_version)

    def _run_update_bat_and_exit(self, new_exe, new_version_file, latest_version):
        try:
            current_exe = sys.executable
            base_dir = get_base_dir()
            version_file = os.path.join(base_dir, 'version.txt')
            bat_path = os.path.join(base_dir, '_bukkax_update.bat')
            log_path = os.path.join(base_dir, 'update_log.txt')
            exe_name = os.path.basename(current_exe)

            bat_lines = [
                '@echo off',
                'chcp 65001 > nul',
                'setlocal',
                f'set "APP={current_exe}"',
                f'set "NEW={new_exe}"',
                f'set "VER={version_file}"',
                f'set "VERNEW={new_version_file}"',
                f'set "LOG={log_path}"',
                'echo ===== BUKKAX UPDATE BAT ONLY ===== > "%LOG%"',
                'echo Python is not used by this updater. >> "%LOG%"',
                'echo APP=%APP% >> "%LOG%"',
                'echo NEW=%NEW% >> "%LOG%"',
                f'echo VERSION={latest_version} >> "%LOG%"',
                'del /F /Q "%~dp0_update.py" > nul 2>&1',
                'del /F /Q "%~dp0_bukkax_update.py" > nul 2>&1',
                'del /F /Q "%~dp0update_runner.py" > nul 2>&1',
                'del /F /Q "%~dp0_update_runner.py" > nul 2>&1',
                'timeout /t 2 /nobreak > nul',
                f'taskkill /IM "{exe_name}" /F > nul 2>&1',
                'timeout /t 1 /nobreak > nul',
                'if not exist "%NEW%" goto no_new',
                'set COUNT=0',
                ':copy_loop',
                'set /a COUNT=%COUNT%+1',
                'copy /Y "%NEW%" "%APP%" >> "%LOG%" 2>&1',
                'if not errorlevel 1 goto copied',
                'if %COUNT% GEQ 12 goto copy_failed',
                'timeout /t 1 /nobreak > nul',
                'goto copy_loop',
                ':copied',
                'if exist "%VERNEW%" move /Y "%VERNEW%" "%VER%" >> "%LOG%" 2>&1',
                'del /F /Q "%NEW%" > nul 2>&1',
                'echo DONE >> "%LOG%"',
                'start "" "%APP%"',
                'del /F /Q "%~f0" > nul 2>&1',
                'exit /b 0',
                ':no_new',
                'echo New exe not found >> "%LOG%"',
                'start notepad "%LOG%"',
                'exit /b 1',
                ':copy_failed',
                'echo Copy failed after retries >> "%LOG%"',
                'start notepad "%LOG%"',
                'exit /b 1',
            ]
            bat_content = '\r\n'.join(bat_lines) + '\r\n'
            with open(bat_path, 'w', encoding='utf-8') as f:
                f.write(bat_content)

            flags = 0
            if sys.platform.startswith('win'):
                flags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
            subprocess.Popen(['cmd.exe', '/c', bat_path], cwd=base_dir, creationflags=flags)

            try:
                if hasattr(self, 'worker') and self.worker:
                    self.worker.stop()
            except Exception:
                pass
            try:
                self.close()
            except Exception:
                pass
            QApplication.quit()
            sys.exit(0)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка обновления", f"Не удалось запустить BAT-установщик обновления: {e}")


# ----------Тут стоит стандартный звук-----------
    def _play_notification_sound(self):
        if not self.sound_enabled or not sys.platform.startswith('win'):
            return
        try:
            import winsound
            if self.custom_sound_path:
                winsound.PlaySound(self.custom_sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

    # ---------- Профиль ----------
    def open_profile(self, nickname):
        is_own = (nickname == self.nickname)
        self.profile_dialog = ProfileDialog(nickname, is_own, self)
        if is_own:
            self.profile_dialog.save_callback = self._save_own_bio
            self.profile_dialog.avatar_callback = self.choose_avatar
        else:
            self.profile_dialog.message_callback = lambda n=nickname: self.show_dm(n)
            self.profile_dialog.call_callback = lambda n=nickname: self.start_call(n, video=False)
            self.profile_dialog.video_callback = lambda n=nickname: self.start_call(n, video=True)
        self.profile_dialog.image_request_callback = self._view_gift
        self.profile_dialog.finished.connect(lambda: setattr(self, 'profile_dialog', None))
        self.profile_dialog.show()
        try:
            send_frame(self.client, {'type': 'profile_request', 'target': nickname})
            self._request_avatar(nickname)
        except Exception:
            pass

    def _view_gift(self, gift_data):
        self._pending_gift_view = gift_data
        try:
            send_frame(self.client, {'type': 'gift_image_request', 'gift_id': gift_data['id']})
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось запросить фото подарка")

    def _save_own_bio(self, bio, status=''):
        try:
            send_frame(self.client, {'type': 'profile_set', 'bio': bio, 'status': status})
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить профиль")

    # ---------- Новости ----------
    def open_news_feed(self):
        is_admin = (self.nickname == ADMIN_NICKNAME)
        self.news_dialog = NewsFeedDialog(is_admin, self._post_news, self)
        self.news_dialog.finished.connect(lambda: setattr(self, 'news_dialog', None))
        self.news_dialog.show()
        self.request_news_list()

    def request_news_list(self):
        try:
            send_frame(self.client, {'type': 'news_list_request'})
        except Exception:
            pass

    def _render_news_list(self, items):
        if not self.news_dialog:
            return
        if not items:
            self.news_dialog.set_html("<i>Пока новостей нет</i>")
            return
        lines = []
        for it in reversed(items):
            ts = short_date(it.get('timestamp', ''))
            author = html.escape(it.get('author', ''))
            text = html.escape(it.get('text') or '')
            lines.append(f"<b>{author}</b> <span style='color:#888;'>{ts}</span><br>{text}<br><br>")
        self.news_dialog.set_html(''.join(lines))

    def _post_news(self, text, attach_path):
        text = text.strip()
        if not text and not attach_path:
            return
        try:
            if attach_path:
                with open(attach_path, 'rb') as f:
                    data = f.read()
                send_frame(self.client, {'type': 'admin_post_news', 'text': text, 'size': len(data)}, data)
            else:
                send_frame(self.client, {'type': 'admin_post_news', 'text': text})
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось опубликовать новость")

    # ---------- Админ-панель ----------
    def open_admin_panel(self):
        self.admin_dialog = AdminPanelDialog(
            self._admin_send_gift, self._admin_kick, self._admin_refresh_users, self
        )
        self.admin_dialog.finished.connect(lambda: setattr(self, 'admin_dialog', None))
        self.admin_dialog.show()
        self._admin_refresh_users()

    def _admin_refresh_users(self):
        try:
            send_frame(self.client, {'type': 'admin_user_list_request'})
        except Exception:
            pass

    def _admin_send_gift(self, target):
        if not target:
            QMessageBox.information(self, "Подарок", "Сначала выбери пользователя из списка.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери фото подарка", "", "Изображения (*.png *.jpg *.jpeg *.gif)"
        )
        if not path:
            return
        note, ok = QInputDialog.getText(self, "Подарок", "Подпись к подарку (необязательно):")
        if not ok:
            note = ''
        try:
            with open(path, 'rb') as f:
                data = f.read()
            send_frame(
                self.client,
                {'type': 'admin_send_gift', 'target': target, 'note': note, 'size': len(data)},
                data
            )
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось отправить подарок: {e}")

    def _admin_kick(self, target):
        if not target:
            QMessageBox.information(self, "Бан", "Сначала выбери пользователя из списка.")
            return
        confirm = QMessageBox.question(self, "Подтверждение", f'Забанить "{target}"? Работает даже если пользователь офлайн.')
        if confirm != QMessageBox.Yes:
            return
        try:
            send_frame(self.client, {'type': 'admin_kick', 'target': target})
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось отправить команду")

    def _handle_admin_result(self, header):
        status = header.get('status')
        texts = {
            'forbidden': '⛔ У тебя нет прав администратора.',
            'invalid': 'Не хватает данных (фото или текста).',
            'not_online': 'Пользователь офлайн, но бан всё равно должен сохраниться на сервере.',
        }
        if status != 'ok':
            QMessageBox.information(self, "Админка", texts.get(status, 'Неизвестный статус'))
        elif self.admin_dialog:
            self._admin_refresh_users()

    def _handle_gift_received(self, header, data):
        note = header.get('note', '')
        sender = header.get('from', 'Админ')
        gift_id = header.get('gift_id', 'x')
        if not data:
            QMessageBox.information(self, "🎁 Подарок!", f"{sender} прислал(а) тебе подарок: {note}")
            return
        self._play_notification_sound()
        self._show_gift_popup("🎁 Тебе подарок!", sender, note, data, gift_id, thanks_button=True)

    def _handle_gift_image_response(self, header, data):
        gift_id = header.get('gift_id')
        pending = self._pending_gift_view
        if not pending or pending.get('id') != gift_id:
            return
        self._pending_gift_view = None
        if not data:
            QMessageBox.information(self, "Подарок", "Не удалось загрузить фото (возможно, удалено).")
            return
        self._show_gift_popup("🎁 Подарок", pending.get('sender', '???'), pending.get('note', ''), data, gift_id)

    def _show_gift_popup(self, title, sender, note, data, gift_id, thanks_button=False):
        try:
            gifts_dir = os.path.join(get_base_dir(), 'gifts_cache')
            os.makedirs(gifts_dir, exist_ok=True)
            temp_path = os.path.join(gifts_dir, f'gift_{gift_id}.png')
            with open(temp_path, 'wb') as f:
                f.write(data)

            dlg = QDialog(self)
            dlg.setWindowTitle(title)
            layout = QVBoxLayout(dlg)
            caption = f"От {sender}" + (f': "{note}"' if note else '')
            layout.addWidget(QLabel(caption))
            img_label = QLabel()
            pixmap = QPixmap(temp_path)
            if pixmap.width() > 400:
                pixmap = pixmap.scaledToWidth(400, Qt.SmoothTransformation)
            img_label.setPixmap(pixmap)
            layout.addWidget(img_label)
            close_btn = QPushButton("Спасибо! 🙏" if thanks_button else "Закрыть")
            close_btn.clicked.connect(dlg.close)
            layout.addWidget(close_btn)
            dlg.exec()
        except Exception:
            QMessageBox.information(self, title, f"{sender}: {note}")

    # ---------- Новая кнопка настроек ----------
    def open_audio_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def closeEvent(self, event):
        try:
            if hasattr(self, 'worker'):
                self.worker.stop()
            if self.client:
                self.client.close()
        except Exception:
            pass
        super().closeEvent(event)


# ---------- Дополнительные классы из оригинального кода ----------
class IncomingCallDialog(QDialog):
    def __init__(self, from_nick, video, on_accept, on_decline, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Входящий звонок")
        self.resize(280, 120)
        layout = QVBoxLayout(self)
        icon = "📹" if video else "📞"
        kind = "видео" if video else "голосовой"
        label = QLabel(f"{icon} Входящий {kind} звонок от {from_nick}")
        label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(label)

        btn_bar = QHBoxLayout()
        accept_btn = QPushButton("✅ Принять")
        accept_btn.clicked.connect(on_accept)
        btn_bar.addWidget(accept_btn)
        decline_btn = QPushButton("❌ Отклонить")
        decline_btn.clicked.connect(on_decline)
        btn_bar.addWidget(decline_btn)
        layout.addLayout(btn_bar)


class VideoMessageRecorderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📹 Видеосообщение")
        self.resize(600, 450)
        self.recorded_path = None
        self.duration = 0
        self.recording = False
        self._temp_path = None
        self._start_time = None

        layout = QVBoxLayout(self)
        self.video_widget = QVideoWidget()
        self.video_widget.setFixedSize(600, 450)
        layout.addWidget(self.video_widget, alignment=Qt.AlignHCenter)

        self.status_label = QLabel("Готов к записи")
        self.status_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(self.status_label)

        btn_bar = QHBoxLayout()
        self.record_btn = QPushButton("⏺ Записать")
        self.record_btn.clicked.connect(self._toggle_record)
        btn_bar.addWidget(self.record_btn)

        self.send_btn = QPushButton("Отправить")
        self.send_btn.setEnabled(False)
        self.send_btn.clicked.connect(self.accept)
        btn_bar.addWidget(self.send_btn)

        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_bar.addWidget(cancel_btn)
        layout.addLayout(btn_bar)

        self.camera = QCamera(QMediaDevices.defaultVideoInput())
        self.capture_session = QMediaCaptureSession()
        self.capture_session.setCamera(self.camera)
        self.capture_session.setVideoOutput(self.video_widget)

        self.audio_input = QAudioInput()
        self.capture_session.setAudioInput(self.audio_input)

        self.recorder = QMediaRecorder()
        self.capture_session.setRecorder(self.recorder)

        media_format = QMediaFormat()
        media_format.setFileFormat(QMediaFormat.FileFormat.MPEG4)
        self.recorder.setMediaFormat(media_format)

        try:
            self.camera.start()
        except Exception:
            self.status_label.setText("⚠️ Не удалось включить камеру")

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_timer)

    def _toggle_record(self):
        if not self.recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        video_dir = os.path.join(get_base_dir(), 'video_temp')
        os.makedirs(video_dir, exist_ok=True)
        self._temp_path = os.path.join(video_dir, f'raw_{int(time.time() * 1000)}.mp4')
        self.recorder.setOutputLocation(QUrl.fromLocalFile(self._temp_path))
        self.recorder.record()
        self.recording = True
        self.record_btn.setText("⏹ Стоп")
        self.send_btn.setEnabled(False)
        self._start_time = time.time()
        self._timer.start(500)

    def _stop_recording(self):
        self.recorder.stop()
        self.recording = False
        self.record_btn.setText("⏺ Записать заново")
        self._timer.stop()
        self.duration = time.time() - self._start_time
        self.recorded_path = self._temp_path
        self.send_btn.setEnabled(True)
        self.status_label.setText(f"Готово ({int(self.duration)} сек)")

    def _update_timer(self):
        elapsed = int(time.time() - self._start_time)
        self.status_label.setText(f"⏺ Запись... {elapsed} сек")

    def closeEvent(self, event):
        try:
            self.recorder.stop()
            self.camera.stop()
        except Exception:
            pass
        super().closeEvent(event)


class EmojiPicker(QDialog):
    def __init__(self, on_pick, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Смайлики")
        grid = QGridLayout(self)
        cols = 10
        for i, emoji in enumerate(EMOJI_LIST):
            btn = QPushButton(emoji)
            btn.setFixedSize(32, 32)
            btn.clicked.connect(lambda checked=False, e=emoji: on_pick(e))
            grid.addWidget(btn, i // cols, i % cols)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.close)
        grid.addWidget(close_btn, (len(EMOJI_LIST) // cols) + 1, 0, 1, cols)


class ProfileDialog(QDialog):
    def __init__(self, nickname, is_own, parent=None):
        super().__init__(parent)
        self.nickname = nickname
        self.is_own = is_own
        self.save_callback = None
        self.avatar_callback = None
        self.message_callback = None
        self.call_callback = None
        self.video_callback = None
        self.image_request_callback = None

        self.setWindowTitle(f"Профиль: {nickname}")
        self.resize(430, 560)
        self.setStyleSheet("""
            QDialog { background: #0f1117; color: #f5f5f5; }
            QLabel { color: #f5f5f5; }
            QLineEdit {
                background: #171a23; color: #ffffff;
                border: 1px solid #2b3040; border-radius: 8px;
                padding: 8px;
            }
            QPushButton {
                background: #2b6cff; color: white;
                border: none; border-radius: 8px;
                padding: 8px 12px; font-weight: 600;
            }
            QPushButton:hover { background: #3d7bff; }
            QPushButton#secondary { background: #232838; }
            QPushButton#secondary:hover { background: #30374c; }
            QListWidget {
                background: #171a23; color: #f5f5f5;
                border: 1px solid #2b3040; border-radius: 10px;
                padding: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        cover = QFrame()
        cover.setFixedHeight(96)
        cover.setStyleSheet("""
            QFrame {
                border-radius: 16px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #2b6cff, stop:0.55 #8c5bff, stop:1 #ff5bbd);
            }
        """)
        layout.addWidget(cover)

        head = QHBoxLayout()
        self.avatar_label = QLabel(self._initials(nickname))
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setFixedSize(72, 72)
        self.avatar_label.setStyleSheet("""
            QLabel {
                background: #202637;
                border: 3px solid #0f1117;
                border-radius: 36px;
                font-size: 24pt;
                font-weight: 800;
            }
        """)
        head.addWidget(self.avatar_label)

        name_box = QVBoxLayout()
        self.name_label = QLabel(f"<b style='font-size:18pt;'>{html.escape(nickname)}</b>")
        name_box.addWidget(self.name_label)
        self.meta_label = QLabel("Загрузка профиля...")
        self.meta_label.setStyleSheet("color:#aab0c0;")
        name_box.addWidget(self.meta_label)
        head.addLayout(name_box, 1)
        layout.addLayout(head)

        if is_own:
            layout.addWidget(QLabel("Статус:"))
            self.status_edit = QLineEdit()
            self.status_edit.setPlaceholderText("Например: на связи, занят, тестирую Букаксу")
            layout.addWidget(self.status_edit)

            layout.addWidget(QLabel("О себе:"))
            self.bio_edit = QLineEdit()
            self.bio_edit.setPlaceholderText("Коротко о себе...")
            layout.addWidget(self.bio_edit)

            btns = QHBoxLayout()
            avatar_btn = QPushButton("🖼 Аватар")
            avatar_btn.setObjectName("secondary")
            avatar_btn.clicked.connect(lambda: self.avatar_callback and self.avatar_callback())
            btns.addWidget(avatar_btn)

            save_btn = QPushButton("💾 Сохранить")
            save_btn.clicked.connect(self._save_clicked)
            btns.addWidget(save_btn)
            layout.addLayout(btns)
        else:
            self.status_label = QLabel("—")
            self.status_label.setWordWrap(True)
            self.status_label.setStyleSheet("font-size: 11pt; color:#d8dcff;")
            layout.addWidget(self.status_label)

            self.bio_label = QLabel("Загрузка...")
            self.bio_label.setWordWrap(True)
            self.bio_label.setStyleSheet("background:#171a23; border-radius:10px; padding:10px; color:#e7e9f2;")
            layout.addWidget(self.bio_label)

            actions = QHBoxLayout()
            msg_btn = QPushButton("💬 Написать")
            msg_btn.clicked.connect(lambda: self.message_callback and self.message_callback())
            actions.addWidget(msg_btn)

            call_btn = QPushButton("📞 Звонок")
            call_btn.setObjectName("secondary")
            call_btn.clicked.connect(lambda: self.call_callback and self.call_callback())
            actions.addWidget(call_btn)

            video_btn = QPushButton("🎥 Видео")
            video_btn.setObjectName("secondary")
            video_btn.clicked.connect(lambda: self.video_callback and self.video_callback())
            actions.addWidget(video_btn)
            layout.addLayout(actions)

        gifts_title = QLabel("🎁 Подарки")
        gifts_title.setStyleSheet("font-weight:700; margin-top:6px;")
        layout.addWidget(gifts_title)
        self.gifts_list = QListWidget()
        self.gifts_list.itemDoubleClicked.connect(self._on_gift_double_clicked)
        layout.addWidget(self.gifts_list, 1)

    def _initials(self, nickname):
        nick = (nickname or '?').strip()
        return html.escape(nick[0].upper() if nick else '?')


    def set_avatar_path(self, path):
        try:
            if not path or not os.path.exists(path):
                return
            pix = QPixmap(path)
            if pix.isNull():
                return
            pix = pix.scaled(72, 72, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = max(0, (pix.width() - 72) // 2)
            y = max(0, (pix.height() - 72) // 2)
            pix = pix.copy(x, y, 72, 72)
            self.avatar_label.setText('')
            self.avatar_label.setPixmap(pix)
        except Exception as e:
            print(f'profile avatar error: {e}')
    def _save_clicked(self):
        if self.save_callback:
            self.save_callback(self.bio_edit.text(), self.status_edit.text())

    def _on_gift_double_clicked(self, item):
        gift_data = item.data(Qt.UserRole)
        if gift_data and self.image_request_callback:
            self.image_request_callback(gift_data)

    def set_data(self, bio, joined, gifts, status='', last_seen=''):
        meta = f"В чате с: {short_date(joined) or '???'}"
        if last_seen:
            meta += f" · был(а): {short_date(last_seen)}"
        self.meta_label.setText(meta)

        if self.is_own:
            self.bio_edit.setText(bio or '')
            self.status_edit.setText(status or '')
        else:
            self.status_label.setText(f"“{html.escape(status)}”" if status else "Статус пока не указан")
            self.bio_label.setText(html.escape(bio) if bio else "Пользователь пока ничего о себе не рассказал")

        self.gifts_list.clear()
        if not gifts:
            self.gifts_list.addItem("Пока нет подарков")
            return
        for g in gifts:
            note = f': "{g["note"]}"' if g.get('note') else ''
            item = QListWidgetItem(f"🎁 от {g['sender']} ({short_date(g['timestamp'])}){note}")
            item.setData(Qt.UserRole, g)
            self.gifts_list.addItem(item)


class NewsFeedDialog(QDialog):
    def __init__(self, is_admin, on_post, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📰 Новости")
        self.resize(480, 520)
        self.attach_path = None

        layout = QVBoxLayout(self)
        self.feed_view = QTextBrowser()
        self.feed_view.setStyleSheet(
            "QTextBrowser { background-color: #111111; color: white; "
            "border: none; font-family: Consolas; font-size: 11pt; }"
        )
        layout.addWidget(self.feed_view)

        if is_admin:
            compose_bar = QHBoxLayout()
            self.compose_entry = QLineEdit()
            self.compose_entry.setPlaceholderText("Текст новости...")
            compose_bar.addWidget(self.compose_entry)

            attach_btn = QPushButton("📎")
            attach_btn.setFixedWidth(32)
            attach_btn.clicked.connect(self._choose_attachment)
            compose_bar.addWidget(attach_btn)

            post_btn = QPushButton("Опубликовать")
            post_btn.clicked.connect(lambda: self._do_post(on_post))
            compose_bar.addWidget(post_btn)

            layout.addLayout(compose_bar)

    def _choose_attachment(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Прикрепить фото", "", "Изображения (*.png *.jpg *.jpeg *.gif)"
        )
        if path:
            self.attach_path = path

    def _do_post(self, on_post):
        text = self.compose_entry.text().strip()
        on_post(text, self.attach_path)
        self.compose_entry.clear()
        self.attach_path = None

    def set_html(self, html_text):
        self.feed_view.setHtml(f'<body style="color:white;">{html_text}</body>')


class AdminPanelDialog(QDialog):
    def __init__(self, on_gift, on_kick, on_refresh, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Админ-панель")
        self.resize(420, 440)

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Все пользователи"))
        top.addStretch()
        refresh_btn = QPushButton("🔄")
        refresh_btn.clicked.connect(on_refresh)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        self.users_list = QListWidget()
        layout.addWidget(self.users_list)

        actions = QHBoxLayout()
        gift_btn = QPushButton("🎁 Подарок")
        gift_btn.clicked.connect(lambda: on_gift(self._selected_nickname()))
        actions.addWidget(gift_btn)
        kick_btn = QPushButton("👢 Кикнуть")
        kick_btn.clicked.connect(lambda: on_kick(self._selected_nickname()))
        actions.addWidget(kick_btn)
        layout.addLayout(actions)

    def set_users(self, users):
        self.users_list.clear()
        for u in users:
            dot = '●' if u.get('online') else '○'
            joined = short_date(u.get('first_seen', ''))
            item = QListWidgetItem(f"{dot} {u['nickname']}  (с {joined})")
            item.setData(Qt.UserRole, u['nickname'])
            self.users_list.addItem(item)

# ---------- BUKKAX BUILDER SYNC + SCREEN SHARE V1 START ----------
try:
    from bukkax_builder_sync import install_builder_sync as _bukkax_install_builder_sync
    _bukkax_install_builder_sync(
        MainWindow,
        send_frame,
        ADMIN_NICKNAME,
    )
except Exception as _bukkax_builder_sync_error:
    try:
        print(
            "BUKKAX Builder Sync init error:",
            _bukkax_builder_sync_error,
        )
    except Exception:
        pass

try:
    from bukkax_screen_share import install_screen_share as _bukkax_install_screen_share
    _bukkax_install_screen_share(
        MainWindow,
        CallStatusDialog,
        send_frame,
        SERVER_IP,
        VIDEO_UDP_PORT,
    )
except Exception as _bukkax_screen_share_error:
    try:
        print(
            "BUKKAX Screen Share init error:",
            _bukkax_screen_share_error,
        )
    except Exception:
        pass
# ---------- BUKKAX BUILDER SYNC + SCREEN SHARE V1 END ----------

# ---------- BUKKAX CALL QUALITY V1 START ----------
try:
    from bukkax_call_quality import install_call_quality as _bukkax_install_call_quality
    _bukkax_install_call_quality(
        MainWindow,
        send_frame,
        SERVER_IP,
        VOICE_UDP_PORT,
    )
except Exception as _bukkax_call_quality_error:
    try:
        print(
            "BUKKAX Call Quality init error:",
            _bukkax_call_quality_error,
        )
    except Exception:
        pass
# ---------- BUKKAX CALL QUALITY V1 END ----------

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())