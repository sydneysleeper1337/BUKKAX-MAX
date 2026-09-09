# -*- coding: utf-8 -*-
"""
BUKKAX Screen Share V2

Демонстрация:
- всего экрана;
- отдельного видимого окна приложения (Windows);
- 720p / 1080p;
- 5 / 8 / 12 / 15 FPS;
- работает во время активного 1-to-1 звонка;
- камера может продолжать работать параллельно.

Передача кадров:
JPEG -> UDP fragments -> существующий BUKKAX VIDEO_UDP relay.

V1 не передаёт системный звук.
"""

import ctypes
import os
import struct
import time
from ctypes import wintypes

from PySide6.QtCore import (
    QBuffer,
    QIODevice,
    QObject,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QGuiApplication,
    QImage,
    QPixmap,
)
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


MAGIC = b"BKSS"
FRAGMENT_HEADER_SIZE = 12  # MAGIC(4) + frame_id(4) + index(2) + count(2)
UDP_CHUNK_SIZE = 58000
MAX_FRAME_BYTES = 3 * 1024 * 1024
RX_TTL_SECONDS = 2.0

_PATCHED = False


class _ScreenShareFrameBridge(QObject):
    """
    NetworkWorker emits frames from its QThread.  The original BUKKAX
    _handle_frame updates Qt widgets, so it must execute in the GUI thread.

    Dynamic monkey-patched Python methods are not reliable Qt slot receivers,
    therefore V1.1 uses this real QObject/Signal/Slot bridge.
    """
    frame_received = Signal(object, object)

    def __init__(self, owner, handler):
        super().__init__(owner)
        self._owner = owner
        self._handler = handler
        self.frame_received.connect(
            self._dispatch,
            Qt.ConnectionType.QueuedConnection,
        )

    @Slot(object, object)
    def _dispatch(self, header, payload):
        self._handler(self._owner, header, payload)


def _enum_windows_windows():
    if os.name != "nt":
        return []

    result = []

    try:
        user32 = ctypes.windll.user32

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        def callback(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True

                if user32.IsIconic(hwnd):
                    return True

                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True

                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()

                if not title:
                    return True

                # Слишком служебные окна не показываем.
                lower = title.lower()
                if lower in ("program manager", "windows input experience"):
                    return True

                result.append(
                    (int(hwnd), title)
                )

            except Exception:
                pass

            return True

        user32.EnumWindows(
            EnumWindowsProc(callback),
            0
        )

    except Exception:
        return []

    # Убираем повторы и сортируем по названию.
    seen = set()
    clean = []

    for hwnd, title in result:
        key = (hwnd, title)
        if key in seen:
            continue
        seen.add(key)
        clean.append((hwnd, title))

    clean.sort(key=lambda x: x[1].lower())
    return clean


class ScreenShareSourceDialog(QDialog):
    def __init__(self, on_start, parent=None):
        super().__init__(parent)

        self.on_start = on_start

        self.setWindowTitle("🖥 Демонстрация экрана")
        self.resize(620, 330)

        root = QVBoxLayout(self)

        title = QLabel(
            "<b>Что показать собеседнику?</b>"
        )
        title.setTextFormat(Qt.RichText)
        root.addWidget(title)

        form = QFormLayout()
        root.addLayout(form)

        self.source_combo = QComboBox()

        screens = QGuiApplication.screens()

        for index, screen in enumerate(screens):
            name = screen.name() or f"Экран {index + 1}"
            geometry = screen.geometry()

            self.source_combo.addItem(
                f"🖥 Экран {index + 1}: {name} "
                f"({geometry.width()}×{geometry.height()})",
                ("screen", index),
            )

        if os.name == "nt":
            windows = _enum_windows_windows()

            for hwnd, title_text in windows:
                short = title_text
                if len(short) > 90:
                    short = short[:87] + "..."

                self.source_combo.addItem(
                    "▣ Приложение: " + short,
                    ("window", hwnd),
                )

        form.addRow(
            "Источник:",
            self.source_combo,
        )

        self.quality_combo = QComboBox()
        self.quality_combo.addItem(
            "720p — 1280×720",
            (1280, 720, 50),
        )
        self.quality_combo.addItem(
            "1080p — 1920×1080",
            (1920, 1080, 42),
        )
        self.quality_combo.currentIndexChanged.connect(
            self._quality_changed
        )
        form.addRow(
            "Качество:",
            self.quality_combo,
        )

        self.fps_combo = QComboBox()

        for fps in (3, 5, 8, 10):
            self.fps_combo.addItem(
                f"{fps} FPS",
                fps,
            )

        self.fps_combo.setCurrentIndex(
            self.fps_combo.findData(5)
        )
        form.addRow(
            "Частота:",
            self.fps_combo,
        )

        info = QLabel(
            "Для связи через интернет начни с 720p / 5 FPS. "
            "1080p лучше начать с 3–5 FPS.\\n"
            "Для отдельного приложения окно должно быть открыто и не свёрнуто."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "color:#aab3c8;"
            "background:#171c29;"
            "border:1px solid #30394d;"
            "border-radius:7px;"
            "padding:8px;"
        )
        root.addWidget(info)

        row = QHBoxLayout()

        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(cancel_btn)

        start_btn = QPushButton("▶ Начать демонстрацию")
        start_btn.clicked.connect(self._start_clicked)
        row.addWidget(start_btn)

        root.addLayout(row)

    def _quality_changed(self, _index):
        data = self.quality_combo.currentData()

        if not data:
            return

        width, _height, _quality = data

        target_fps = 5 if width >= 1900 else 5

        idx = self.fps_combo.findData(target_fps)
        if idx >= 0:
            self.fps_combo.setCurrentIndex(idx)

    def _start_clicked(self):
        source = self.source_combo.currentData()
        quality = self.quality_combo.currentData()
        fps = self.fps_combo.currentData()

        if not source or not quality:
            return

        try:
            self.on_start(
                source,
                quality,
                int(fps or 8),
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Демонстрация экрана",
                f"Не удалось запустить демонстрацию:\\n{e}"
            )
            return

        self.accept()


class ScreenShareViewerDialog(QDialog):
    def __init__(self, peer_name="", parent=None):
        super().__init__(parent)

        self.peer_name = peer_name or "Собеседник"
        self._last_pixmap = None

        self.setWindowTitle(
            f"🖥 Демонстрация — {self.peer_name}"
        )
        self.resize(1000, 620)
        self.setMinimumSize(640, 400)

        root = QVBoxLayout(self)

        self.status_label = QLabel(
            f"🖥 {self.peer_name} демонстрирует экран"
        )
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            "font-weight:700;"
            "font-size:13px;"
            "padding:6px;"
        )
        root.addWidget(self.status_label)

        self.video_label = QLabel(
            "Ожидание изображения..."
        )
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(600, 338)
        self.video_label.setStyleSheet(
            "background:#090b10;"
            "color:#7f8798;"
            "border:1px solid #283044;"
            "border-radius:8px;"
        )
        root.addWidget(
            self.video_label,
            1,
        )

        buttons = QHBoxLayout()

        fullscreen_btn = QPushButton(
            "⛶ На весь экран"
        )
        fullscreen_btn.clicked.connect(
            self._toggle_fullscreen
        )
        buttons.addWidget(fullscreen_btn)

        buttons.addStretch()

        close_btn = QPushButton(
            "Скрыть окно"
        )
        close_btn.clicked.connect(
            self.hide
        )
        buttons.addWidget(close_btn)

        root.addLayout(buttons)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def set_quality_text(self, text):
        self.status_label.setText(
            f"🖥 {self.peer_name} демонстрирует экран — {text}"
        )

    def set_frame(self, pixmap):
        if pixmap is None or pixmap.isNull():
            return

        self._last_pixmap = pixmap
        self._render()

    def _render(self):
        if self._last_pixmap is None:
            return

        self.video_label.setPixmap(
            self._last_pixmap.scaled(
                self.video_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()


def _capture_source(source):
    if not source:
        return QPixmap()

    kind, value = source

    if kind == "screen":
        screens = QGuiApplication.screens()
        index = int(value)

        if index < 0 or index >= len(screens):
            return QPixmap()

        return screens[index].grabWindow(0)

    if kind == "window":
        screens = QGuiApplication.screens()

        if not screens:
            return QPixmap()

        # На Windows grabWindow(WId) умеет захватывать внешнее окно.
        # Некоторые GPU/protected окна могут вернуть чёрный кадр.
        return screens[0].grabWindow(
            int(value)
        )

    return QPixmap()


def install_screen_share(
    MainWindow,
    CallStatusDialog,
    send_frame,
    server_ip,
    video_udp_port,
):
    global _PATCHED

    if _PATCHED:
        return

    _PATCHED = True

    # ---------------------------------------------------------------
    # Кнопка screen-share в обычном 1-to-1 call dialog.
    # ---------------------------------------------------------------
    old_call_init = CallStatusDialog.__init__

    def call_init_with_screen_share(
        self,
        status_text,
        on_hangup,
        video=False,
        parent=None,
    ):
        old_call_init(
            self,
            status_text,
            on_hangup,
            video=video,
            parent=parent,
        )

        try:
            self.screen_share_btn = QPushButton(
                "🖥 Демонстрация экрана"
            )

            self.screen_share_btn.setToolTip(
                "Показать весь экран или отдельное приложение"
            )

            if parent is not None:
                self.screen_share_btn.clicked.connect(
                    parent.toggle_screen_share
                )

            layout = self.layout()
            index = max(
                0,
                layout.count() - 1
            )
            layout.insertWidget(
                index,
                self.screen_share_btn
            )

        except Exception as e:
            try:
                print(
                    "Screen-share button error:",
                    e
                )
            except Exception:
                pass

    CallStatusDialog.__init__ = (
        call_init_with_screen_share
    )

    # ---------------------------------------------------------------
    # MainWindow screen-share methods.
    # ---------------------------------------------------------------
    def _screen_share_update_button(self):
        dlg = getattr(
            self,
            "call_dialog",
            None
        )

        if dlg is None:
            return

        btn = getattr(
            dlg,
            "screen_share_btn",
            None
        )

        if btn is None:
            return

        active = bool(
            getattr(
                self,
                "_screen_share_active",
                False
            )
        )

        btn.setText(
            "⏹ Остановить демонстрацию"
            if active
            else "🖥 Демонстрация экрана"
        )

    def toggle_screen_share(self):
        if getattr(
            self,
            "_screen_share_active",
            False
        ):
            self._stop_screen_share(
                notify=True
            )
            return

        current = getattr(
            self,
            "current_call",
            None
        )

        if (
            not current
            or current.get("state") != "active"
            or not current.get("call_id")
        ):
            QMessageBox.information(
                self,
                "Демонстрация экрана",
                "Сначала должен начаться обычный звонок с пользователем."
            )
            return

        dlg = ScreenShareSourceDialog(
            self._start_screen_share,
            self,
        )
        dlg.exec()

    def _start_screen_share(
        self,
        source,
        quality,
        fps,
    ):
        current = getattr(
            self,
            "current_call",
            None
        )

        if (
            not current
            or current.get("state") != "active"
        ):
            raise RuntimeError(
                "Звонок уже завершён."
            )

        self._stop_screen_share(
            notify=False
        )

        width, height, jpeg_quality = quality

        self._screen_share_source = source
        self._screen_share_width = int(width)
        self._screen_share_height = int(height)
        self._screen_share_jpeg_quality = int(jpeg_quality)
        self._screen_share_fps = max(
            1,
            min(20, int(fps))
        )
        self._screen_share_frame_id = 0
        self._screen_share_active = True
        self._screen_share_capture_errors = 0

        timer = QTimer(self)
        timer.setTimerType(
            Qt.PreciseTimer
        )
        timer.timeout.connect(
            self._screen_share_tick
        )

        self._screen_share_timer = timer

        # Регистрируем video UDP endpoint даже если это голосовой звонок.
        try:
            self._send_video_hello_packet()
        except Exception:
            pass

        try:
            send_frame(
                self.client,
                {
                    "type": "screen_share_state",
                    "call_id": current.get("call_id"),
                    "active": True,
                    "quality": (
                        f"{width}x{height}"
                    ),
                    "fps": self._screen_share_fps,
                }
            )
        except Exception:
            pass

        # Дадим peer немного времени отправить свой video hello.
        try:
            QTimer.singleShot(
                180,
                self._send_video_hello_packet
            )
        except Exception:
            pass

        interval = max(
            60,
            int(
                1000
                / self._screen_share_fps
            )
        )

        timer.start(interval)

        self._screen_share_update_button()

        if getattr(
            self,
            "call_dialog",
            None
        ):
            try:
                self.call_dialog.set_status(
                    f"🖥 Демонстрация {width}×{height} "
                    f"@ {self._screen_share_fps} FPS"
                )
            except Exception:
                pass

    def _stop_screen_share(
        self,
        notify=True,
    ):
        was_active = bool(
            getattr(
                self,
                "_screen_share_active",
                False
            )
        )

        timer = getattr(
            self,
            "_screen_share_timer",
            None
        )

        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass

        self._screen_share_timer = None
        self._screen_share_active = False

        if (
            was_active
            and notify
        ):
            current = getattr(
                self,
                "current_call",
                None
            )

            if (
                current
                and current.get("call_id")
            ):
                try:
                    send_frame(
                        self.client,
                        {
                            "type": "screen_share_state",
                            "call_id": current.get("call_id"),
                            "active": False,
                        }
                    )
                except Exception:
                    pass

        self._screen_share_update_button()

        if (
            was_active
            and getattr(
                self,
                "call_dialog",
                None
            )
        ):
            try:
                peer = self.current_call.get(
                    "peer_nick",
                    "собеседником",
                ) if self.current_call else "собеседником"

                self.call_dialog.set_status(
                    f"📞 Разговор с {peer}"
                )
            except Exception:
                pass

    def _screen_share_tick(self):
        if not getattr(
            self,
            "_screen_share_active",
            False
        ):
            return

        current = getattr(
            self,
            "current_call",
            None
        )

        if (
            not current
            or current.get("state") != "active"
            or not current.get("call_id")
        ):
            self._stop_screen_share(
                notify=False
            )
            return

        # Не начинаем следующий кадр, если прошлый send_frame ещё не закончен.
        if getattr(self, "_screen_share_tcp_busy", False):
            return

        pixmap = _capture_source(
            getattr(
                self,
                "_screen_share_source",
                None
            )
        )

        if pixmap.isNull():
            self._screen_share_capture_errors = (
                getattr(
                    self,
                    "_screen_share_capture_errors",
                    0
                )
                + 1
            )

            if self._screen_share_capture_errors == 10:
                try:
                    QMessageBox.warning(
                        self,
                        "Демонстрация экрана",
                        "Не удаётся получить изображение.\n"
                        "Если выбрано приложение — убедись, что его окно не свёрнуто."
                    )
                except Exception:
                    pass

            return

        self._screen_share_capture_errors = 0

        image = pixmap.toImage()

        if image.isNull():
            return

        target_w = int(
            getattr(
                self,
                "_screen_share_width",
                1280
            )
        )
        target_h = int(
            getattr(
                self,
                "_screen_share_height",
                720
            )
        )

        scaled = image.scaled(
            target_w,
            target_h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        # JPEG для рабочего стола хорошо сжимается.
        # Если кадр слишком тяжёлый, автоматически понижаем quality.
        requested_quality = int(
            getattr(
                self,
                "_screen_share_jpeg_quality",
                48
            )
        )

        jpeg = b""

        for quality in (
            requested_quality,
            max(30, requested_quality - 10),
            28,
        ):
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)

            ok = scaled.save(
                buffer,
                "JPG",
                quality,
            )

            if ok:
                jpeg = bytes(
                    buffer.data()
                )

            buffer.close()

            if not jpeg:
                continue

            target_limit = (
                700 * 1024
                if target_w >= 1900
                else 400 * 1024
            )

            if len(jpeg) <= target_limit:
                break

        if (
            not jpeg
            or len(jpeg) > 1024 * 1024
        ):
            return

        self._screen_share_tcp_busy = True

        try:
            send_frame(
                self.client,
                {
                    "type": "screen_share_frame",
                    "call_id": current.get("call_id"),
                    "size": len(jpeg),
                    "width": scaled.width(),
                    "height": scaled.height(),
                    "fps": int(
                        getattr(
                            self,
                            "_screen_share_fps",
                            5
                        )
                    ),
                },
                jpeg,
            )

            self._screen_share_tcp_errors = 0

        except Exception as e:
            self._screen_share_tcp_errors = (
                int(
                    getattr(
                        self,
                        "_screen_share_tcp_errors",
                        0
                    )
                )
                + 1
            )

            try:
                print(
                    "Screen share TCP send error:",
                    e
                )
            except Exception:
                pass

            if self._screen_share_tcp_errors >= 3:
                self._stop_screen_share(
                    notify=True
                )

                try:
                    QMessageBox.warning(
                        self,
                        "Демонстрация экрана",
                        "Передача экрана остановлена: соединение нестабильно."
                    )
                except Exception:
                    pass

        finally:
            self._screen_share_tcp_busy = False

    def _screen_share_open_viewer(
        self,
        peer_name=None,
        quality_text="",
    ):
        viewer = getattr(
            self,
            "_screen_share_viewer",
            None
        )

        if viewer is None:
            if not peer_name:
                current = getattr(
                    self,
                    "current_call",
                    None
                )
                peer_name = (
                    current.get(
                        "peer_nick",
                        "Собеседник",
                    )
                    if current
                    else "Собеседник"
                )

            viewer = ScreenShareViewerDialog(
                peer_name=peer_name,
                parent=self,
            )

            viewer.finished.connect(
                lambda *_:
                    setattr(
                        self,
                        "_screen_share_viewer",
                        None
                    )
            )

            self._screen_share_viewer = viewer

        if quality_text:
            viewer.set_quality_text(
                quality_text
            )

        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

        return viewer

    def _screen_share_handle_state(
        self,
        header,
    ):
        current = getattr(
            self,
            "current_call",
            None
        )

        if not current:
            return

        if (
            header.get("call_id")
            != current.get("call_id")
        ):
            return

        active = bool(
            header.get("active")
        )

        if active:
            # Регистрируем наш UDP endpoint, чтобы сервер знал куда релеить экран.
            try:
                self._send_video_hello_packet()
            except Exception:
                pass

            quality = str(
                header.get("quality")
                or ""
            )
            fps = header.get("fps")

            quality_text = quality

            if fps:
                quality_text += (
                    f" @ {fps} FPS"
                )

            self._screen_share_open_viewer(
                peer_name=header.get(
                    "from"
                )
                or current.get(
                    "peer_nick",
                    "Собеседник"
                ),
                quality_text=quality_text,
            )

        else:
            viewer = getattr(
                self,
                "_screen_share_viewer",
                None
            )

            if viewer is not None:
                try:
                    viewer.close()
                except Exception:
                    pass

            self._screen_share_viewer = None
            self._screen_share_rx_frames = {}

    MainWindow.toggle_screen_share = (
        toggle_screen_share
    )
    MainWindow._start_screen_share = (
        _start_screen_share
    )
    MainWindow._stop_screen_share = (
        _stop_screen_share
    )
    MainWindow._screen_share_tick = (
        _screen_share_tick
    )
    MainWindow._screen_share_update_button = (
        _screen_share_update_button
    )
    MainWindow._screen_share_open_viewer = (
        _screen_share_open_viewer
    )
    MainWindow._screen_share_handle_state = (
        _screen_share_handle_state
    )

    # ---------------------------------------------------------------
    # TCP state signal.
    #
    # IMPORTANT:
    # NetworkWorker lives in a QThread.  The dynamically monkey-patched
    # _handle_frame method can otherwise be invoked in that worker thread.
    # Any QLabel/QTextDocument/etc. work from there can crash Qt with:
    # "QObject: Cannot create children for a parent that is in a different
    # thread" / access violation.
    #
    # We create a real QObject bridge while MainWindow is being constructed
    # in the GUI thread, and every network frame is queued through it.
    # ---------------------------------------------------------------
    old_handle_frame = MainWindow._handle_frame

    def handle_frame_on_gui_thread(
        self,
        header,
        payload,
    ):
        if header.get("type") == "screen_share_frame":
            current = getattr(
                self,
                "current_call",
                None,
            )

            if (
                not current
                or header.get("call_id")
                != current.get("call_id")
            ):
                return

            if not payload:
                return

            image = QImage()

            if not image.loadFromData(
                payload,
                "JPG",
            ):
                return

            viewer = self._screen_share_open_viewer(
                peer_name=current.get(
                    "peer_nick",
                    "Собеседник",
                ),
                quality_text=(
                    f'{header.get("width", image.width())}×'
                    f'{header.get("height", image.height())}'
                    f' @ {header.get("fps", "?")} FPS'
                ),
            )

            viewer.set_frame(
                QPixmap.fromImage(
                    image
                )
            )
            return

        if (
            header.get("type")
            == "screen_share_state"
        ):
            self._screen_share_handle_state(
                header
            )
            return

        return old_handle_frame(
            self,
            header,
            payload,
        )

    old_main_init = MainWindow.__init__

    def main_init_with_screen_share_bridge(
        self,
        *args,
        **kwargs,
    ):
        old_main_init(
            self,
            *args,
            **kwargs,
        )

        self._screen_share_frame_bridge = (
            _ScreenShareFrameBridge(
                self,
                handle_frame_on_gui_thread,
            )
        )

    MainWindow.__init__ = (
        main_init_with_screen_share_bridge
    )

    def handle_frame_with_screen_share(
        self,
        header,
        payload,
    ):
        bridge = getattr(
            self,
            "_screen_share_frame_bridge",
            None,
        )

        if bridge is not None:
            # Signal emission is thread-safe; QueuedConnection makes the
            # actual handler run on the GUI thread.
            bridge.frame_received.emit(
                header,
                payload,
            )
            return

        # Defensive fallback for unusual construction paths.
        return handle_frame_on_gui_thread(
            self,
            header,
            payload,
        )

    MainWindow._handle_frame = (
        handle_frame_with_screen_share
    )

    # ---------------------------------------------------------------
    # Video UDP receiver: поддерживаем старые camera JPEG и BKSS chunks.
    # ---------------------------------------------------------------
    def on_call_video_udp_data_with_screen_share(
        self
    ):
        now = time.time()

        rx_frames = getattr(
            self,
            "_screen_share_rx_frames",
            None
        )

        if rx_frames is None:
            rx_frames = {}
            self._screen_share_rx_frames = (
                rx_frames
            )

        # Очистка неполных кадров.
        stale = [
            key
            for key, item in rx_frames.items()
            if now - item.get(
                "time",
                now
            ) > RX_TTL_SECONDS
        ]

        for key in stale:
            rx_frames.pop(
                key,
                None
            )

        while self.video_udp_socket.hasPendingDatagrams():
            size = self.video_udp_socket.pendingDatagramSize()

            datagram, _host, _port = (
                self.video_udp_socket.readDatagram(
                    size
                )
            )

            if len(datagram) <= 17:
                continue

            call_id = datagram[:16].decode(
                "ascii",
                errors="ignore",
            )
            sender_id = datagram[16]
            payload = datagram[17:]

            # Screen-share fragment.
            if (
                len(payload) >= FRAGMENT_HEADER_SIZE
                and payload[:4] == MAGIC
            ):
                try:
                    frame_id, chunk_index, chunk_count = struct.unpack(
                        "!IHH",
                        payload[4:12],
                    )
                except Exception:
                    continue

                if (
                    chunk_count <= 0
                    or chunk_count > 256
                    or chunk_index >= chunk_count
                ):
                    continue

                key = (
                    call_id,
                    sender_id,
                    frame_id,
                )

                entry = rx_frames.get(
                    key
                )

                if (
                    entry is None
                    or entry.get("count")
                    != chunk_count
                ):
                    entry = {
                        "time": now,
                        "count": chunk_count,
                        "chunks": {},
                    }
                    rx_frames[key] = entry

                entry["time"] = now
                entry["chunks"][
                    chunk_index
                ] = payload[
                    FRAGMENT_HEADER_SIZE:
                ]

                if (
                    len(entry["chunks"])
                    < chunk_count
                ):
                    continue

                try:
                    jpeg = b"".join(
                        entry["chunks"][i]
                        for i in range(
                            chunk_count
                        )
                    )
                except Exception:
                    rx_frames.pop(
                        key,
                        None
                    )
                    continue

                rx_frames.pop(
                    key,
                    None
                )

                if (
                    not jpeg
                    or len(jpeg) > MAX_FRAME_BYTES
                ):
                    continue

                image = QImage()

                if not image.loadFromData(
                    jpeg,
                    "JPG",
                ):
                    continue

                current = getattr(
                    self,
                    "current_call",
                    None
                )

                if (
                    current
                    and call_id
                    == current.get("call_id")
                ):
                    viewer = (
                        self._screen_share_open_viewer(
                            peer_name=current.get(
                                "peer_nick",
                                "Собеседник",
                            )
                        )
                    )

                    viewer.set_frame(
                        QPixmap.fromImage(
                            image
                        )
                    )

                continue

            # Обычная камера — старый формат BUKKAX.
            image = QImage()

            if not image.loadFromData(
                payload,
                "JPG",
            ):
                continue

            if (
                getattr(
                    self,
                    "group_call",
                    None
                )
                and getattr(
                    self,
                    "group_call_dialog",
                    None
                )
            ):
                self.group_call_dialog.update_member_frame(
                    sender_id,
                    QPixmap.fromImage(
                        image
                    ),
                )

            elif getattr(
                self,
                "call_dialog",
                None
            ):
                self.call_dialog.update_remote_frame(
                    QPixmap.fromImage(
                        image
                    )
                )

    MainWindow._on_call_video_udp_data = (
        on_call_video_udp_data_with_screen_share
    )

    # ---------------------------------------------------------------
    # При завершении звонка гасим screen-share и viewer.
    # ---------------------------------------------------------------
    old_cleanup_call = MainWindow._cleanup_call

    def cleanup_call_with_screen_share(
        self,
        *args,
        **kwargs,
    ):
        try:
            self._stop_screen_share(
                notify=False
            )
        except Exception:
            pass

        viewer = getattr(
            self,
            "_screen_share_viewer",
            None
        )

        if viewer is not None:
            try:
                viewer.close()
            except Exception:
                pass

        self._screen_share_viewer = None
        self._screen_share_rx_frames = {}

        return old_cleanup_call(
            self,
            *args,
            **kwargs,
        )

    MainWindow._cleanup_call = (
        cleanup_call_with_screen_share
    )
