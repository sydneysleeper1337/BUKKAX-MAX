# -*- coding: utf-8 -*-
"""
BUKKAX Developer Studio V2

Совместимый с Builder V1/V1.1 визуальный конструктор:
- top-bar и свободное размещение поверх центрального окна;
- drag & resize на холсте;
- размеры, скругление, цвета, шрифт;
- иконки, встроенные в JSON;
- видимость: всем / админ / только мне;
- встроенные действия BUKKAX;
- локальные действия разработчика: Python-код, Python-файл, EXE/программа,
  файл/папка. Такие действия никогда не должны публиковаться другим клиентам.
"""

import base64
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from copy import deepcopy

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt, QUrl, QRectF
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


CONFIG_NAME = "bukkax_builder_config.json"
CONFIG_VERSION = 2

DEFAULT_CONFIG = {
    "version": CONFIG_VERSION,
    "widgets": [],
}

WIDGET_TYPES = {
    "button": "Кнопка",
    "input": "Поле ввода",
    "label": "Текст",
    "image": "Изображение",
}

VISIBILITY_OPTIONS = {
    "all": "Все пользователи",
    "admin": "Только админ",
    "me": "Только мне / разработчику",
}

PLACEMENT_OPTIONS = {
    "topbar": "Верхняя панель",
    "floating": "Свободно на окне",
}

STYLE_PRESETS = {
    "default": {
        "label": "Обычный",
        "bg": "",
        "text": "",
        "border": "",
    },
    "accent": {
        "label": "Акцент",
        "bg": "#315bba",
        "text": "#ffffff",
        "border": "#4f79d8",
    },
    "success": {
        "label": "Зелёный",
        "bg": "#24623d",
        "text": "#ffffff",
        "border": "#3f8e5e",
    },
    "danger": {
        "label": "Красный",
        "bg": "#713437",
        "text": "#ffffff",
        "border": "#a95359",
    },
}

BUILTIN_ACTIONS = {
    "none": ("Нет действия", "Ничего не запускает.", ""),
    "open_music": ("🎵 Открыть музыку", "Открывает музыку BUKKAX.", ""),
    "open_chess": ("♟ Открыть шахматы", "Открывает выбор шахмат.", ""),
    "open_my_profile": ("👤 Мой профиль", "Открывает ваш профиль.", ""),
    "open_news": ("📰 Новости", "Открывает новости.", ""),
    "open_audio_settings": ("🔊 Настройки звука", "Открывает настройки аудио.", ""),
    "open_background": ("🎨 Настройка фона", "Открывает настройку фона.", ""),
    "open_notifications": ("🔔 Звук уведомлений", "Открывает настройки уведомлений.", ""),
    "open_admin": ("⚙️ Админ-панель", "Открывает админ-панель.", ""),
    "send_gift": ("🎁 Отправить подарок", "Открывает отправку подарка.", ""),
    "open_dm": ("✉️ Открыть ЛС", "Открывает ЛС.", "Ник или @widget_id."),
    "open_profile": ("👤 Профиль пользователя", "Открывает профиль.", "Ник или @widget_id."),
    "call_user": ("📞 Позвонить", "Голосовой звонок.", "Ник или @widget_id."),
    "video_call_user": ("📹 Видеозвонок", "Видеозвонок.", "Ник или @widget_id."),
    "set_chat_input": ("📝 Вставить в сообщение", "Заполняет поле сообщения.", "Текст / @id."),
    "send_chat_text": ("📨 Отправить текст", "Отправляет текст.", "Текст / @id."),
    "show_message": ("💬 Показать сообщение", "Локальное окно.", "Текст / @id."),
    "open_url": ("🌐 Открыть URL", "Открывает URL.", "https://..."),
    "clear_widget": ("🧹 Очистить виджет", "Очищает другой виджет.", "@widget_id"),
}

LOCAL_ACTIONS = {
    "python_code": (
        "🐍 Python-код (только мне)",
        "Выполняет локальный Python-код внутри вашего BUKKAX.",
        "Код задаётся на вкладке «Код».",
    ),
    "python_file": (
        "🐍 Запустить .py (только мне)",
        "Запускает локальный Python-файл отдельным процессом.",
        "Путь задаётся ниже.",
    ),
    "run_program": (
        "▶ Запустить программу / EXE (только мне)",
        "Запускает локальную программу.",
        "Путь и аргументы задаются ниже.",
    ),
    "open_file": (
        "📄 Открыть файл (только мне)",
        "Открывает локальный файл системным приложением.",
        "Путь задаётся ниже.",
    ),
    "open_folder": (
        "📁 Открыть папку (только мне)",
        "Открывает локальную папку.",
        "Путь задаётся ниже.",
    ),
}

ACTIONS = {}
ACTIONS.update(BUILTIN_ACTIONS)
ACTIONS.update(LOCAL_ACTIONS)

PUBLIC_ACTION_IDS = set(BUILTIN_ACTIONS)
LOCAL_ACTION_IDS = set(LOCAL_ACTIONS)


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _embedded_dir():
    return getattr(sys, "_MEIPASS", "") or ""


def external_config_path():
    return os.path.join(_app_dir(), CONFIG_NAME)


def _config_candidates():
    result = [external_config_path()]
    embedded = _embedded_dir()
    if embedded:
        result.append(os.path.join(embedded, CONFIG_NAME))
    module_dir = os.path.dirname(os.path.abspath(__file__))
    module_candidate = os.path.join(module_dir, CONFIG_NAME)
    if module_candidate not in result:
        result.append(module_candidate)
    return result


def _upgrade_item(item):
    out = dict(item or {})
    out.setdefault("type", "button")
    out.setdefault("text", "")
    out.setdefault("tooltip", "")
    out.setdefault("width", 0)
    out.setdefault("height", 0)
    out.setdefault("visibility", "all")
    out.setdefault("style", "default")
    out.setdefault("action", "none")
    out.setdefault("argument", "")
    out.setdefault("enabled", True)
    out.setdefault("placement", "topbar")
    out.setdefault("x", 30)
    out.setdefault("y", 30)
    out.setdefault("radius", 8)
    out.setdefault("font_size", 13)
    out.setdefault("font_bold", False)
    out.setdefault("bg_color", "")
    out.setdefault("text_color", "")
    out.setdefault("border_color", "")
    out.setdefault("icon_data", "")
    out.setdefault("icon_name", "")
    out.setdefault("icon_size", 20)
    out.setdefault("action_path", "")
    out.setdefault("action_args", "")
    out.setdefault("code", "")
    return out


def load_config():
    for path in _config_candidates():
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue
            widgets = data.get("widgets")
            if not isinstance(widgets, list):
                continue
            data = dict(data)
            data["version"] = CONFIG_VERSION
            data["widgets"] = [_upgrade_item(x) for x in widgets if isinstance(x, dict)]
            return data
        except Exception:
            continue
    return deepcopy(DEFAULT_CONFIG)


def save_config(config):
    path = external_config_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    data = deepcopy(config)
    data["version"] = CONFIG_VERSION
    data["widgets"] = [_upgrade_item(x) for x in data.get("widgets", []) if isinstance(x, dict)]
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp, path)
    return path


def public_config(config):
    """
    Возвращает только то, что разрешено отправлять другим клиентам.
    Локальный Python/EXE/файлы и visibility=me никогда не уходят на сервер.
    """
    clean = {"version": CONFIG_VERSION, "widgets": []}
    skipped = []
    for raw in config.get("widgets", []):
        if not isinstance(raw, dict):
            continue
        item = _upgrade_item(raw)
        if item.get("visibility") == "me":
            skipped.append(str(item.get("id") or "?"))
            continue
        if str(item.get("action") or "none") in LOCAL_ACTION_IDS:
            skipped.append(str(item.get("id") or "?"))
            continue

        # Поля с локальным кодом/путями не попадают в публичный JSON даже случайно.
        item.pop("code", None)
        item.pop("action_path", None)
        item.pop("action_args", None)
        clean["widgets"].append(item)
    return clean, skipped


def merge_public_into_local(local_config, public):
    """
    Сервер обновляет публичную часть, но не стирает локальные dev-виджеты.
    """
    local_config = local_config if isinstance(local_config, dict) else {}
    public = public if isinstance(public, dict) else {}
    local_only = []
    for raw in local_config.get("widgets", []):
        if not isinstance(raw, dict):
            continue
        item = _upgrade_item(raw)
        if item.get("visibility") == "me" or item.get("action") in LOCAL_ACTION_IDS:
            item["visibility"] = "me"
            local_only.append(item)

    public_widgets = []
    for raw in public.get("widgets", []):
        if isinstance(raw, dict):
            item = _upgrade_item(raw)
            if item.get("visibility") != "me" and item.get("action") not in LOCAL_ACTION_IDS:
                public_widgets.append(item)

    return {
        "version": CONFIG_VERSION,
        "widgets": public_widgets + local_only,
    }


def _widget_text(widget):
    if widget is None:
        return ""
    if isinstance(widget, QLineEdit):
        return widget.text()
    try:
        return widget.text()
    except Exception:
        return ""


def _special_value(main_window, token):
    token = (token or "").strip()
    if token == "$nickname":
        return str(getattr(main_window, "nickname", "") or "")
    if token == "$chat_input":
        return _widget_text(getattr(main_window, "entry", None))
    if token == "$current_friend":
        try:
            item = main_window.friends_list.currentItem()
            if item is None:
                return ""
            value = item.data(Qt.UserRole)
            if value:
                return str(value)
            text = item.text()
            return text[2:].strip() if len(text) > 2 else text.strip()
        except Exception:
            return ""
    if token == "$current_dm":
        try:
            item = main_window.dm_list.currentItem()
            if item is None:
                return ""
            value = item.data(Qt.UserRole)
            return str(value or item.text()).strip()
        except Exception:
            return ""
    if token == "$current_view_target":
        try:
            _kind, target = main_window.current_view
            return str(target or "")
        except Exception:
            return ""
    return None


def resolve_argument(main_window, raw_argument):
    value = str(raw_argument or "").strip()
    if not value:
        return ""
    if value.startswith("@"):
        widget_id = value[1:].strip()
        widgets = getattr(main_window, "_builder_widgets_by_id", {})
        return _widget_text(widgets.get(widget_id)).strip()
    if value.startswith("$"):
        special = _special_value(main_window, value)
        if special is not None:
            return special
    return value


def _require_argument(main_window, action_id, raw_argument):
    value = resolve_argument(main_window, raw_argument)
    if value:
        return value
    label = ACTIONS.get(action_id, (action_id, "", ""))[0]
    QMessageBox.information(
        main_window,
        "Developer Studio",
        f"Действию «{label}» нужен непустой аргумент.",
    )
    return None


def _open_local_path(path):
    path = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
    if sys.platform.startswith("win"):
        os.startfile(path)
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def _python_command(path, args_text):
    path = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
    args = shlex.split(str(args_text or ""), posix=not sys.platform.startswith("win"))
    if not getattr(sys, "frozen", False):
        return [sys.executable, path] + args
    python_exe = shutil.which("python")
    if python_exe:
        return [python_exe, path] + args
    py_launcher = shutil.which("py")
    if py_launcher:
        return [py_launcher, path] + args
    raise RuntimeError(
        "Python не найден в PATH. Укажи действие «Программа/EXE» "
        "или установи Python/добавь его в PATH."
    )


def execute_action(main_window, action_id, raw_argument="", item=None):
    action_id = str(action_id or "none")
    item = _upgrade_item(item or {})
    if action_id == "none":
        return

    try:
        if action_id == "open_music":
            for name in ("_start_music_app", "open_music_app", "open_music"):
                method = getattr(main_window, name, None)
                if callable(method):
                    method()
                    return
            QMessageBox.information(main_window, "Developer Studio", "Музыкальный модуль не найден.")
            return
        if action_id == "open_chess":
            main_window.open_chess_start_dialog()
            return
        if action_id == "open_my_profile":
            main_window.open_profile(main_window.nickname)
            return
        if action_id == "open_news":
            main_window.open_news_feed()
            return
        if action_id == "open_audio_settings":
            main_window.open_audio_settings()
            return
        if action_id == "open_background":
            main_window.open_background_menu()
            return
        if action_id == "open_notifications":
            main_window.open_sound_menu()
            return
        if action_id == "open_admin":
            method = getattr(main_window, "open_admin_panel", None)
            if callable(method):
                method()
            return
        if action_id == "send_gift":
            method = getattr(main_window, "send_user_gift", None)
            if callable(method):
                method()
            return
        if action_id == "open_dm":
            value = _require_argument(main_window, action_id, raw_argument)
            if value is not None:
                main_window.open_dm(value)
            return
        if action_id == "open_profile":
            value = _require_argument(main_window, action_id, raw_argument)
            if value is not None:
                main_window.open_profile(value)
            return
        if action_id == "call_user":
            value = _require_argument(main_window, action_id, raw_argument)
            if value is not None:
                main_window.start_call(value, video=False)
            return
        if action_id == "video_call_user":
            value = _require_argument(main_window, action_id, raw_argument)
            if value is not None:
                main_window.start_call(value, video=True)
            return
        if action_id == "set_chat_input":
            value = resolve_argument(main_window, raw_argument)
            main_window.entry.setText(value)
            main_window.entry.setFocus()
            return
        if action_id == "send_chat_text":
            value = _require_argument(main_window, action_id, raw_argument)
            if value is not None:
                main_window.entry.setText(value)
                main_window.send_message()
            return
        if action_id == "show_message":
            value = resolve_argument(main_window, raw_argument)
            QMessageBox.information(main_window, "Developer Studio", value or "(пустое значение)")
            return
        if action_id == "open_url":
            value = _require_argument(main_window, action_id, raw_argument)
            if value is not None:
                if not re.match(r"^https?://", value, re.IGNORECASE):
                    value = "https://" + value
                QDesktopServices.openUrl(QUrl(value))
            return
        if action_id == "clear_widget":
            ref = str(raw_argument or "").strip()
            if not ref.startswith("@"):
                QMessageBox.information(main_window, "Developer Studio", "Для очистки укажи @widget_id.")
                return
            widget = getattr(main_window, "_builder_widgets_by_id", {}).get(ref[1:].strip())
            if widget is None:
                return
            if isinstance(widget, QLineEdit):
                widget.clear()
            else:
                try:
                    widget.setText("")
                except Exception:
                    pass
            return

        # Локальные dev-действия.
        if action_id in LOCAL_ACTION_IDS:
            if item.get("visibility") != "me":
                raise RuntimeError(
                    "Локальные Python/EXE/файловые действия разрешены только "
                    "для элементов «Только мне / разработчику»."
                )

        if action_id == "python_code":
            code = str(item.get("code") or "")
            if not code.strip():
                raise RuntimeError("Python-код пуст.")
            arg = resolve_argument(main_window, raw_argument)
            env = {
                "__name__": "__bukkax_dev_script__",
                "main_window": main_window,
                "window": main_window,
                "argument": arg,
                "resolve_argument": lambda value: resolve_argument(main_window, value),
                "QMessageBox": QMessageBox,
                "os": os,
                "sys": sys,
                "subprocess": subprocess,
            }
            exec(compile(code, f"<BUKKAX:{item.get('id', 'script')}>", "exec"), env, env)
            return

        if action_id == "python_file":
            path = str(item.get("action_path") or "").strip()
            if not path:
                raise RuntimeError("Не указан путь к .py.")
            subprocess.Popen(_python_command(path, item.get("action_args", "")))
            return

        if action_id == "run_program":
            path = os.path.abspath(os.path.expandvars(os.path.expanduser(
                str(item.get("action_path") or "").strip()
            )))
            if not path:
                raise RuntimeError("Не указан путь к программе.")
            args = shlex.split(
                str(item.get("action_args") or ""),
                posix=not sys.platform.startswith("win"),
            )
            subprocess.Popen([path] + args)
            return

        if action_id == "open_file":
            path = str(item.get("action_path") or "").strip()
            if not path:
                raise RuntimeError("Не указан путь к файлу.")
            _open_local_path(path)
            return

        if action_id == "open_folder":
            path = str(item.get("action_path") or "").strip()
            if not path:
                raise RuntimeError("Не указан путь к папке.")
            _open_local_path(path)
            return

        QMessageBox.warning(main_window, "Developer Studio", f"Неизвестное действие: {action_id}")
    except Exception as e:
        QMessageBox.warning(
            main_window,
            "Developer Studio",
            f"Не удалось выполнить действие «{action_id}»:\n{e}",
        )


def _is_admin(main_window, admin_nickname):
    return str(getattr(main_window, "nickname", "") or "") == str(admin_nickname or "")


def _valid_color(value):
    value = str(value or "").strip()
    if not value:
        return ""
    c = QColor(value)
    return c.name() if c.isValid() else ""


def _style_qss(item, widget_type):
    item = _upgrade_item(item)
    preset = STYLE_PRESETS.get(item.get("style"), STYLE_PRESETS["default"])
    bg = _valid_color(item.get("bg_color")) or preset.get("bg", "")
    text = _valid_color(item.get("text_color")) or preset.get("text", "")
    border = _valid_color(item.get("border_color")) or preset.get("border", "")
    radius = max(0, min(60, int(item.get("radius") or 0)))
    font_size = max(8, min(48, int(item.get("font_size") or 13)))
    weight = "700" if item.get("font_bold") else "400"

    parts = [
        f"border-radius:{radius}px",
        f"font-size:{font_size}px",
        f"font-weight:{weight}",
    ]
    if bg:
        parts.append(f"background:{bg}")
    if text:
        parts.append(f"color:{text}")
    if border:
        parts.append(f"border:1px solid {border}")
    elif widget_type in ("button", "input"):
        parts.append("border:1px solid #3a4767")
    if widget_type in ("button", "input"):
        parts.append("padding:4px 8px")
    return ";".join(parts) + ";"


def _pixmap_from_data(data):
    if not data:
        return QPixmap()
    try:
        raw = base64.b64decode(str(data).encode("ascii"), validate=False)
        pix = QPixmap()
        pix.loadFromData(raw)
        return pix
    except Exception:
        return QPixmap()


def _apply_common_properties(widget, item):
    item = _upgrade_item(item)
    tooltip = str(item.get("tooltip") or "").strip()
    if tooltip:
        widget.setToolTip(tooltip)

    width = max(0, min(1000, int(item.get("width") or 0)))
    height = max(0, min(800, int(item.get("height") or 0)))
    if width > 0:
        widget.setFixedWidth(max(24, width))
    if height > 0:
        widget.setFixedHeight(max(20, height))

    widget.setStyleSheet(_style_qss(item, item.get("type")))

    pix = _pixmap_from_data(item.get("icon_data"))
    if not pix.isNull():
        icon_size = max(12, min(128, int(item.get("icon_size") or 20)))
        if isinstance(widget, QPushButton):
            widget.setIcon(QIcon(pix))
            from PySide6.QtCore import QSize
            widget.setIconSize(QSize(icon_size, icon_size))


def _create_runtime_widget(main_window, item):
    item = _upgrade_item(item)
    widget_type = str(item.get("type") or "button")
    text = str(item.get("text") or "")
    action_id = str(item.get("action") or "none")
    argument = str(item.get("argument") or "")

    if widget_type == "input":
        widget = QLineEdit()
        widget.setPlaceholderText(text or "Введите значение…")
        widget.setMinimumWidth(80)
        if action_id != "none":
            widget.returnPressed.connect(
                lambda a=action_id, arg=argument, data=deepcopy(item):
                    execute_action(main_window, a, arg, data)
            )
    elif widget_type == "label":
        widget = QLabel(text)
    elif widget_type == "image":
        widget = QLabel(text)
        widget.setAlignment(Qt.AlignCenter)
        pix = _pixmap_from_data(item.get("icon_data"))
        if not pix.isNull():
            width = max(24, int(item.get("width") or 96))
            height = max(24, int(item.get("height") or 96))
            widget.setPixmap(pix.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    else:
        widget = QPushButton(text or "Кнопка")
        widget.clicked.connect(
            lambda _checked=False, a=action_id, arg=argument, data=deepcopy(item):
                execute_action(main_window, a, arg, data)
        )

    _apply_common_properties(widget, item)
    return widget


def clear_runtime_widgets(main_window):
    widgets = list(getattr(main_window, "_builder_runtime_widgets", []))
    for widget in widgets:
        try:
            widget.setParent(None)
            widget.deleteLater()
        except Exception:
            pass
    main_window._builder_runtime_widgets = []
    main_window._builder_widgets_by_id = {}


def apply_builder_config(main_window, layout, admin_nickname):
    clear_runtime_widgets(main_window)
    config = load_config()
    created = []
    by_id = {}
    admin = _is_admin(main_window, admin_nickname)

    dev_btn = getattr(main_window, "dev_builder_btn", None)
    insert_index = layout.indexOf(dev_btn) if dev_btn is not None else -1
    if insert_index < 0:
        insert_index = layout.count()

    center = None
    try:
        center = main_window.centralWidget()
    except Exception:
        center = None

    for raw in config.get("widgets", []):
        if not isinstance(raw, dict):
            continue
        item = _upgrade_item(raw)
        if item.get("enabled", True) is False:
            continue

        visibility = str(item.get("visibility") or "all")
        if visibility in ("admin", "me") and not admin:
            continue

        action_id = str(item.get("action") or "none")
        if action_id in LOCAL_ACTION_IDS and not admin:
            continue

        widget_id = str(item.get("id") or "").strip()
        if not widget_id or widget_id in by_id:
            continue

        try:
            widget = _create_runtime_widget(main_window, item)
        except Exception:
            continue

        widget.setObjectName("builder_" + widget_id)

        placement = str(item.get("placement") or "topbar")
        if placement == "floating" and center is not None:
            widget.setParent(center)
            x = max(0, min(5000, int(item.get("x") or 0)))
            y = max(0, min(5000, int(item.get("y") or 0)))
            width = max(24, int(item.get("width") or 120))
            height = max(20, int(item.get("height") or 36))
            widget.setGeometry(x, y, width, height)
            widget.show()
            widget.raise_()
        else:
            layout.insertWidget(insert_index, widget)
            insert_index += 1

        created.append(widget)
        by_id[widget_id] = widget

    main_window._builder_runtime_widgets = created
    main_window._builder_widgets_by_id = by_id
    return len(created)


class StudioGraphicsItem(QGraphicsRectItem):
    HANDLE = 12

    def __init__(self, index, item, callback):
        super().__init__(0, 0, max(60, int(item.get("width") or 120)), max(28, int(item.get("height") or 40)))
        self.index = index
        self.callback = callback
        self._resizing = False
        self._press_rect = QRectF(self.rect())
        self.setPos(float(item.get("x") or 30), float(item.get("y") or 30))
        self.setFlags(
            QGraphicsRectItem.ItemIsMovable
            | QGraphicsRectItem.ItemIsSelectable
            | QGraphicsRectItem.ItemSendsGeometryChanges
        )
        self.setPen(QPen(QColor("#5f79b8"), 1))
        self.setBrush(QColor("#293249"))

        label = str(item.get("text") or item.get("id") or "widget")
        self.text_item = QGraphicsSimpleTextItem(label, self)
        self.text_item.setBrush(QColor("#ffffff"))
        self.text_item.setPos(8, 7)

    def _handle_hit(self, pos):
        r = self.rect()
        return pos.x() >= r.right() - self.HANDLE and pos.y() >= r.bottom() - self.HANDLE

    def mousePressEvent(self, event):
        if self._handle_hit(event.pos()):
            self._resizing = True
            self._press_rect = QRectF(self.rect())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            p = event.pos()
            w = max(50.0, p.x())
            h = max(26.0, p.y())
            self.setRect(0, 0, w, h)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            if callable(self.callback):
                self.callback(
                    self.index,
                    int(round(self.x())),
                    int(round(self.y())),
                    int(round(self.rect().width())),
                    int(round(self.rect().height())),
                    True,
                )
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if callable(self.callback):
            self.callback(
                self.index,
                int(round(self.x())),
                int(round(self.y())),
                int(round(self.rect().width())),
                int(round(self.rect().height())),
                True,
            )

    def mouseDoubleClickEvent(self, event):
        if callable(self.callback):
            self.callback(
                self.index,
                int(round(self.x())),
                int(round(self.y())),
                int(round(self.rect().width())),
                int(round(self.rect().height())),
                False,
            )
        super().mouseDoubleClickEvent(event)


class StudioCanvas(QGraphicsView):
    def __init__(self, parent=None):
        self.scene_obj = QGraphicsScene()
        super().__init__(self.scene_obj, parent)
        self.scene_obj.setSceneRect(0, 0, 1000, 600)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setMinimumSize(500, 380)
        self.setStyleSheet(
            "QGraphicsView { background:#0f1320; border:1px solid #303950; border-radius:8px; }"
        )

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        pen = QPen(QColor("#1c2436"), 1)
        painter.setPen(pen)
        step = 20
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)
        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += step
        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += step


class DeveloperBuilderDialog(QDialog):
    def __init__(self, main_window, admin_nickname, apply_callback=None, publish_callback=None):
        super().__init__(main_window)
        self.main_window = main_window
        self.admin_nickname = admin_nickname
        self.apply_callback = apply_callback
        self.publish_callback = publish_callback
        self.config = load_config()
        self.current_index = -1
        self._loading = False
        self._icon_data_pending = ""
        self._icon_name_pending = ""

        self.setWindowTitle("🛠 BUKKAX Developer Studio V2")
        self.resize(1380, 820)
        self.setMinimumSize(1080, 680)
        self._build_ui()
        self._reload_list()

    def _build_ui(self):
        root = QVBoxLayout(self)
        intro = QLabel(
            "Developer Studio V2: перетаскивай элементы на холсте, меняй размеры и дизайн. "
            "Python/EXE/локальные файлы работают только для «Только мне» и никогда не публикуются."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "color:#c5d1ee; background:#1a2030; border:1px solid #303950; "
            "border-radius:8px; padding:9px;"
        )
        root.addWidget(intro)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        design = QWidget()
        design_root = QHBoxLayout(design)
        design_root.setContentsMargins(6, 6, 6, 6)

        splitter = QSplitter(Qt.Horizontal)
        design_root.addWidget(splitter)

        # LEFT
        left = QWidget()
        left_box = QVBoxLayout(left)
        left_box.addWidget(QLabel("Элементы"))
        self.widget_list = QListWidget()
        self.widget_list.currentRowChanged.connect(self._select_row)
        left_box.addWidget(self.widget_list, 1)

        add_row = QHBoxLayout()
        for label, kind in (
            ("+ Кнопка", "button"),
            ("+ Поле", "input"),
            ("+ Текст", "label"),
            ("+ Фото", "image"),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, k=kind: self._add_widget(k))
            add_row.addWidget(btn)
        left_box.addLayout(add_row)

        move_row = QHBoxLayout()
        up = QPushButton("↑")
        up.clicked.connect(lambda: self._move_current(-1))
        down = QPushButton("↓")
        down.clicked.connect(lambda: self._move_current(1))
        dup = QPushButton("Дубль")
        dup.clicked.connect(self._duplicate_current)
        delete = QPushButton("Удалить")
        delete.clicked.connect(self._delete_current)
        for b in (up, down, dup, delete):
            move_row.addWidget(b)
        left_box.addLayout(move_row)
        splitter.addWidget(left)

        # CENTER CANVAS
        center = QWidget()
        center_box = QVBoxLayout(center)
        center_title = QLabel("Холст свободного размещения — тащи элемент; за правый нижний угол меняется размер")
        center_title.setWordWrap(True)
        center_title.setStyleSheet("color:#9eb0d8;")
        center_box.addWidget(center_title)
        self.canvas = StudioCanvas()
        center_box.addWidget(self.canvas, 1)
        splitter.addWidget(center)

        # RIGHT PROPERTIES
        right = QWidget()
        right_box = QVBoxLayout(right)
        form = QFormLayout()
        right_box.addLayout(form)

        self.type_combo = QComboBox()
        for key, label in WIDGET_TYPES.items():
            self.type_combo.addItem(label, key)
        form.addRow("Тип:", self.type_combo)

        self.id_edit = QLineEdit()
        form.addRow("ID:", self.id_edit)

        self.text_edit = QLineEdit()
        form.addRow("Текст / placeholder:", self.text_edit)

        self.tooltip_edit = QLineEdit()
        form.addRow("Подсказка:", self.tooltip_edit)

        self.placement_combo = QComboBox()
        for key, label in PLACEMENT_OPTIONS.items():
            self.placement_combo.addItem(label, key)
        form.addRow("Расположение:", self.placement_combo)

        xy = QWidget()
        xy_box = QHBoxLayout(xy)
        xy_box.setContentsMargins(0, 0, 0, 0)
        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 5000)
        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, 5000)
        xy_box.addWidget(QLabel("X"))
        xy_box.addWidget(self.x_spin)
        xy_box.addWidget(QLabel("Y"))
        xy_box.addWidget(self.y_spin)
        form.addRow("Позиция:", xy)

        wh = QWidget()
        wh_box = QHBoxLayout(wh)
        wh_box.setContentsMargins(0, 0, 0, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(0, 1000)
        self.width_spin.setSpecialValueText("Авто")
        self.height_spin = QSpinBox()
        self.height_spin.setRange(0, 800)
        self.height_spin.setSpecialValueText("Авто")
        wh_box.addWidget(QLabel("W"))
        wh_box.addWidget(self.width_spin)
        wh_box.addWidget(QLabel("H"))
        wh_box.addWidget(self.height_spin)
        form.addRow("Размер:", wh)

        self.visibility_combo = QComboBox()
        for key, label in VISIBILITY_OPTIONS.items():
            self.visibility_combo.addItem(label, key)
        form.addRow("Кому видно:", self.visibility_combo)

        self.style_combo = QComboBox()
        for key, data in STYLE_PRESETS.items():
            self.style_combo.addItem(data["label"], key)
        form.addRow("Стиль:", self.style_combo)

        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(0, 60)
        form.addRow("Скругление:", self.radius_spin)

        font_row = QWidget()
        font_box = QHBoxLayout(font_row)
        font_box.setContentsMargins(0, 0, 0, 0)
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 48)
        self.bold_check = QCheckBox("Жирный")
        font_box.addWidget(self.font_spin)
        font_box.addWidget(self.bold_check)
        form.addRow("Шрифт:", font_row)

        self.bg_edit = QLineEdit()
        self.bg_edit.setPlaceholderText("#315bba или пусто")
        self.bg_pick = QPushButton("…")
        self.bg_pick.setFixedWidth(34)
        bg_row = QWidget()
        bg_box = QHBoxLayout(bg_row)
        bg_box.setContentsMargins(0, 0, 0, 0)
        bg_box.addWidget(self.bg_edit)
        bg_box.addWidget(self.bg_pick)
        self.bg_pick.clicked.connect(lambda: self._pick_color(self.bg_edit))
        form.addRow("Фон:", bg_row)

        self.text_color_edit = QLineEdit()
        self.text_color_edit.setPlaceholderText("#ffffff")
        self.text_color_pick = QPushButton("…")
        self.text_color_pick.setFixedWidth(34)
        tc_row = QWidget()
        tc_box = QHBoxLayout(tc_row)
        tc_box.setContentsMargins(0, 0, 0, 0)
        tc_box.addWidget(self.text_color_edit)
        tc_box.addWidget(self.text_color_pick)
        self.text_color_pick.clicked.connect(lambda: self._pick_color(self.text_color_edit))
        form.addRow("Текст:", tc_row)

        self.border_edit = QLineEdit()
        self.border_edit.setPlaceholderText("#4f79d8")
        self.border_pick = QPushButton("…")
        self.border_pick.setFixedWidth(34)
        bc_row = QWidget()
        bc_box = QHBoxLayout(bc_row)
        bc_box.setContentsMargins(0, 0, 0, 0)
        bc_box.addWidget(self.border_edit)
        bc_box.addWidget(self.border_pick)
        self.border_pick.clicked.connect(lambda: self._pick_color(self.border_edit))
        form.addRow("Рамка:", bc_row)

        icon_row = QWidget()
        icon_box = QHBoxLayout(icon_row)
        icon_box.setContentsMargins(0, 0, 0, 0)
        self.icon_label = QLabel("нет")
        self.icon_btn = QPushButton("Загрузить")
        self.icon_clear_btn = QPushButton("×")
        self.icon_btn.clicked.connect(self._choose_icon)
        self.icon_clear_btn.clicked.connect(self._clear_icon)
        icon_box.addWidget(self.icon_label, 1)
        icon_box.addWidget(self.icon_btn)
        icon_box.addWidget(self.icon_clear_btn)
        form.addRow("Иконка:", icon_row)

        self.icon_size_spin = QSpinBox()
        self.icon_size_spin.setRange(12, 128)
        form.addRow("Размер иконки:", self.icon_size_spin)

        self.action_combo = QComboBox()
        for key, (label, _desc, _help) in ACTIONS.items():
            self.action_combo.addItem(label, key)
        self.action_combo.currentIndexChanged.connect(self._refresh_action_help)
        form.addRow("Действие:", self.action_combo)

        self.argument_edit = QLineEdit()
        form.addRow("Аргумент:", self.argument_edit)

        self.path_edit = QLineEdit()
        path_row = QWidget()
        path_box = QHBoxLayout(path_row)
        path_box.setContentsMargins(0, 0, 0, 0)
        path_box.addWidget(self.path_edit)
        path_btn = QPushButton("…")
        path_btn.setFixedWidth(34)
        path_btn.clicked.connect(self._choose_action_path)
        path_box.addWidget(path_btn)
        form.addRow("Путь:", path_row)

        self.args_edit = QLineEdit()
        form.addRow("Аргументы запуска:", self.args_edit)

        self.action_help = QLabel()
        self.action_help.setWordWrap(True)
        self.action_help.setStyleSheet(
            "color:#aeb8cf; background:#151a27; border:1px solid #2d3448; "
            "border-radius:7px; padding:8px;"
        )
        right_box.addWidget(self.action_help)

        save_row = QHBoxLayout()
        save_btn = QPushButton("💾 Сохранить")
        save_btn.clicked.connect(lambda: self._save_current(True))
        apply_btn = QPushButton("⚡ Применить")
        apply_btn.clicked.connect(self._apply_now)
        publish_btn = QPushButton("🚀 Опубликовать")
        publish_btn.clicked.connect(self._publish_now)
        for b in (save_btn, apply_btn, publish_btn):
            save_row.addWidget(b)
        right_box.addLayout(save_row)
        right_box.addStretch()
        splitter.addWidget(right)
        splitter.setSizes([240, 650, 420])

        self.tabs.addTab(design, "🎨 Конструктор")

        # CODE TAB
        code_tab = QWidget()
        code_box = QVBoxLayout(code_tab)
        code_info = QLabel(
            "Локальный Python-код. Он хранится только в вашем локальном config и "
            "не публикуется другим пользователям. Доступны main_window/window, argument, "
            "QMessageBox, os, sys, subprocess."
        )
        code_info.setWordWrap(True)
        code_info.setStyleSheet(
            "color:#ffd88b; background:#2a2215; border:1px solid #66502a; "
            "border-radius:8px; padding:9px;"
        )
        code_box.addWidget(code_info)
        self.code_edit = QPlainTextEdit()
        self.code_edit.setPlaceholderText(
            'Пример:\\nQMessageBox.information(main_window, "Dev", "Работает!")\\n'
            'main_window.open_chess_start_dialog()'
        )
        self.code_edit.setStyleSheet(
            "QPlainTextEdit { background:#0d111b; color:#e7ecf7; "
            "font-family:Consolas,monospace; font-size:14px; "
            "border:1px solid #303950; border-radius:8px; padding:8px; }"
        )
        code_box.addWidget(self.code_edit, 1)
        code_buttons = QHBoxLayout()
        use_code = QPushButton("🐍 Сделать действием Python-код")
        use_code.clicked.connect(self._set_python_code_action)
        save_code = QPushButton("💾 Сохранить код")
        save_code.clicked.connect(lambda: self._save_current(True))
        test_code = QPushButton("▶ Тестировать")
        test_code.clicked.connect(self._test_code)
        for b in (use_code, save_code, test_code):
            code_buttons.addWidget(b)
        code_box.addLayout(code_buttons)
        self.tabs.addTab(code_tab, "</> Код")

        bottom = QHBoxLayout()
        path_label = QLabel("Конфиг: " + external_config_path())
        path_label.setStyleSheet("color:#7f8aa8;")
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bottom.addWidget(path_label, 1)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.close)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

        self.setStyleSheet(
            """
            QDialog, QWidget { background:#111522; color:#f1f4fb; }
            QLineEdit, QComboBox, QSpinBox, QListWidget {
                background:#1b2130; color:#ffffff; border:1px solid #313a50;
                border-radius:6px; padding:5px;
            }
            QListWidget::item { padding:7px; }
            QListWidget::item:selected { background:#315bba; }
            QPushButton {
                background:#293249; color:white; border:1px solid #3a4767;
                border-radius:6px; padding:6px 9px;
            }
            QPushButton:hover { background:#34415f; }
            QTabWidget::pane { border:1px solid #303950; }
            """
        )
        self._refresh_action_help()

    def _widgets(self):
        return self.config.setdefault("widgets", [])

    def _valid_id(self, widget_id):
        return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$", widget_id))

    def _combo_set_data(self, combo, value):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _unique_id(self, base_name):
        existing = {str(x.get("id") or "") for x in self._widgets()}
        if base_name not in existing:
            return base_name
        i = 2
        while f"{base_name}_{i}" in existing:
            i += 1
        return f"{base_name}_{i}"

    def _add_widget(self, widget_type):
        base_name = {"button": "button", "input": "input", "label": "label", "image": "image"}.get(widget_type, "widget")
        item = _upgrade_item({
            "id": self._unique_id(base_name),
            "type": widget_type,
            "text": {
                "button": "Новая кнопка",
                "input": "Введите значение…",
                "label": "Новый текст",
                "image": "",
            }.get(widget_type, ""),
            "visibility": "me",
            "placement": "floating",
            "width": 140 if widget_type != "image" else 110,
            "height": 40 if widget_type != "image" else 110,
            "x": 40 + (len(self._widgets()) % 6) * 25,
            "y": 40 + (len(self._widgets()) % 6) * 25,
        })
        self._widgets().append(item)
        save_config(self.config)
        self._reload_list(len(self._widgets()) - 1)

    def _reload_list(self, select_index=None):
        self.widget_list.blockSignals(True)
        self.widget_list.clear()
        for item in self._widgets():
            item = _upgrade_item(item)
            visibility = item.get("visibility", "all")
            badge = "👁" if visibility == "all" else "🔒" if visibility == "me" else "🛡"
            self.widget_list.addItem(
                QListWidgetItem(
                    f"{badge} {WIDGET_TYPES.get(item.get('type'), item.get('type'))}: "
                    f"{item.get('id', '?')}   {item.get('text', '')}"
                )
            )
        self.widget_list.blockSignals(False)
        if select_index is None:
            select_index = min(max(self.current_index, 0), self.widget_list.count() - 1)
        if self.widget_list.count() > 0 and select_index >= 0:
            self.widget_list.setCurrentRow(select_index)
        else:
            self.current_index = -1
            self._clear_form()
        self._refresh_canvas()

    def _select_row(self, row):
        self.current_index = row
        if row < 0 or row >= len(self._widgets()):
            self._clear_form()
            return
        self._load_form(self._widgets()[row])
        self._select_canvas_item(row)

    def _load_form(self, raw):
        self._loading = True
        item = _upgrade_item(raw)
        self._combo_set_data(self.type_combo, item.get("type"))
        self.id_edit.setText(str(item.get("id") or ""))
        self.text_edit.setText(str(item.get("text") or ""))
        self.tooltip_edit.setText(str(item.get("tooltip") or ""))
        self._combo_set_data(self.placement_combo, item.get("placement"))
        self.x_spin.setValue(int(item.get("x") or 0))
        self.y_spin.setValue(int(item.get("y") or 0))
        self.width_spin.setValue(int(item.get("width") or 0))
        self.height_spin.setValue(int(item.get("height") or 0))
        self._combo_set_data(self.visibility_combo, item.get("visibility"))
        self._combo_set_data(self.style_combo, item.get("style"))
        self.radius_spin.setValue(int(item.get("radius") or 0))
        self.font_spin.setValue(int(item.get("font_size") or 13))
        self.bold_check.setChecked(bool(item.get("font_bold")))
        self.bg_edit.setText(str(item.get("bg_color") or ""))
        self.text_color_edit.setText(str(item.get("text_color") or ""))
        self.border_edit.setText(str(item.get("border_color") or ""))
        self._icon_data_pending = str(item.get("icon_data") or "")
        self._icon_name_pending = str(item.get("icon_name") or "")
        self.icon_label.setText(self._icon_name_pending or ("есть" if self._icon_data_pending else "нет"))
        self.icon_size_spin.setValue(int(item.get("icon_size") or 20))
        self._combo_set_data(self.action_combo, item.get("action"))
        self.argument_edit.setText(str(item.get("argument") or ""))
        self.path_edit.setText(str(item.get("action_path") or ""))
        self.args_edit.setText(str(item.get("action_args") or ""))
        self.code_edit.setPlainText(str(item.get("code") or ""))
        self._loading = False
        self._refresh_action_help()

    def _clear_form(self):
        for edit in (
            self.id_edit, self.text_edit, self.tooltip_edit, self.argument_edit,
            self.path_edit, self.args_edit, self.bg_edit, self.text_color_edit,
            self.border_edit,
        ):
            edit.clear()
        self.code_edit.clear()
        self._icon_data_pending = ""
        self._icon_name_pending = ""
        self.icon_label.setText("нет")

    def _save_current(self, show_message=False):
        row = self.current_index
        if row < 0 or row >= len(self._widgets()):
            QMessageBox.information(self, "Developer Studio", "Сначала выбери или добавь элемент.")
            return False

        widget_id = self.id_edit.text().strip()
        if not self._valid_id(widget_id):
            QMessageBox.warning(
                self, "Developer Studio",
                "ID должен начинаться с буквы или _, дальше — буквы, цифры и _."
            )
            return False
        for i, item in enumerate(self._widgets()):
            if i != row and str(item.get("id") or "") == widget_id:
                QMessageBox.warning(self, "Developer Studio", f"ID «{widget_id}» уже используется.")
                return False

        action = self.action_combo.currentData() or "none"
        visibility = self.visibility_combo.currentData() or "all"
        if action in LOCAL_ACTION_IDS and visibility != "me":
            visibility = "me"
            self._combo_set_data(self.visibility_combo, "me")
            QMessageBox.information(
                self,
                "Developer Studio",
                "Python/EXE/локальные файлы автоматически переведены в «Только мне». "
                "Они не будут отправляться другим пользователям.",
            )

        item = _upgrade_item({
            "id": widget_id,
            "type": self.type_combo.currentData() or "button",
            "text": self.text_edit.text(),
            "tooltip": self.tooltip_edit.text(),
            "placement": self.placement_combo.currentData() or "topbar",
            "x": int(self.x_spin.value()),
            "y": int(self.y_spin.value()),
            "width": int(self.width_spin.value()),
            "height": int(self.height_spin.value()),
            "visibility": visibility,
            "style": self.style_combo.currentData() or "default",
            "radius": int(self.radius_spin.value()),
            "font_size": int(self.font_spin.value()),
            "font_bold": bool(self.bold_check.isChecked()),
            "bg_color": self.bg_edit.text().strip(),
            "text_color": self.text_color_edit.text().strip(),
            "border_color": self.border_edit.text().strip(),
            "icon_data": self._icon_data_pending,
            "icon_name": self._icon_name_pending,
            "icon_size": int(self.icon_size_spin.value()),
            "action": action,
            "argument": self.argument_edit.text(),
            "action_path": self.path_edit.text(),
            "action_args": self.args_edit.text(),
            "code": self.code_edit.toPlainText(),
            "enabled": True,
        })

        self._widgets()[row] = item
        path = save_config(self.config)
        self._reload_list(row)
        if show_message:
            QMessageBox.information(self, "Developer Studio", "Свойства сохранены.\n\n" + path)
        return True

    def _apply_now(self):
        if self.current_index >= 0 and not self._save_current(False):
            return
        if callable(self.apply_callback):
            self.apply_callback()
        QMessageBox.information(self, "Developer Studio", "Конфигурация применена.")

    def _publish_now(self):
        if self.current_index >= 0 and not self._save_current(False):
            return
        if not callable(self.publish_callback):
            QMessageBox.warning(self, "Developer Studio", "Синхронизация с сервером не подключена.")
            return

        public, skipped = public_config(self.config)
        msg = (
            "Опубликовать публичную часть интерфейса всем пользователям?\n\n"
            "Онлайн-клиенты применят её сразу."
        )
        if skipped:
            msg += (
                "\n\nНе будут отправлены локальные элементы:\n• "
                + "\n• ".join(skipped[:20])
            )
        answer = QMessageBox.question(self, "Developer Studio", msg)
        if answer != QMessageBox.Yes:
            return
        try:
            self.publish_callback(public)
        except Exception as e:
            QMessageBox.warning(self, "Developer Studio", f"Не удалось опубликовать:\n{e}")

    def _refresh_action_help(self):
        action_id = self.action_combo.currentData() or "none"
        label, desc, arg_help = ACTIONS.get(action_id, (action_id, "", ""))
        text = f"<b>{label}</b><br>{desc}"
        if arg_help:
            text += f"<br><br><b>Параметр:</b> {arg_help}"
        if action_id in LOCAL_ACTION_IDS:
            text += "<br><br><b>🔒 Только локально.</b> Сервер этот код/путь не получит."
        self.action_help.setText(text)
        self.action_help.setTextFormat(Qt.RichText)

    def _pick_color(self, edit):
        current = QColor(edit.text().strip()) if edit.text().strip() else QColor("#315bba")
        color = QColorDialog.getColor(current, self, "Выбери цвет")
        if color.isValid():
            edit.setText(color.name())

    def _choose_icon(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Иконка", "", "Изображения (*.png *.jpg *.jpeg *.bmp *.webp *.ico)"
        )
        if not path:
            return
        pix = QPixmap(path)
        if pix.isNull():
            QMessageBox.warning(self, "Developer Studio", "Не удалось прочитать изображение.")
            return
        pix = pix.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        if not pix.save(buffer, "PNG"):
            buffer.close()
            QMessageBox.warning(self, "Developer Studio", "Не удалось преобразовать иконку.")
            return
        raw = bytes(buffer.data())
        buffer.close()
        if len(raw) > 180 * 1024:
            QMessageBox.warning(self, "Developer Studio", "Иконка слишком большая после обработки.")
            return
        self._icon_data_pending = base64.b64encode(raw).decode("ascii")
        self._icon_name_pending = os.path.basename(path)
        self.icon_label.setText(self._icon_name_pending)

    def _clear_icon(self):
        self._icon_data_pending = ""
        self._icon_name_pending = ""
        self.icon_label.setText("нет")

    def _choose_action_path(self):
        action = self.action_combo.currentData() or "none"
        if action == "open_folder":
            path = QFileDialog.getExistingDirectory(self, "Выбери папку")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Выбери файл / программу")
        if path:
            self.path_edit.setText(path)

    def _set_python_code_action(self):
        self._combo_set_data(self.action_combo, "python_code")
        self._combo_set_data(self.visibility_combo, "me")
        self.tabs.setCurrentIndex(1)

    def _test_code(self):
        if self.current_index < 0 or self.current_index >= len(self._widgets()):
            QMessageBox.information(self, "Developer Studio", "Сначала выбери элемент.")
            return
        temp = _upgrade_item(self._widgets()[self.current_index])
        temp["code"] = self.code_edit.toPlainText()
        temp["visibility"] = "me"
        temp["action"] = "python_code"
        execute_action(self.main_window, "python_code", self.argument_edit.text(), temp)

    def _duplicate_current(self):
        row = self.current_index
        if row < 0 or row >= len(self._widgets()):
            return
        src = deepcopy(_upgrade_item(self._widgets()[row]))
        src["id"] = self._unique_id(str(src.get("id") or "widget") + "_copy")
        src["x"] = int(src.get("x") or 0) + 24
        src["y"] = int(src.get("y") or 0) + 24
        self._widgets().insert(row + 1, src)
        save_config(self.config)
        self._reload_list(row + 1)

    def _delete_current(self):
        row = self.current_index
        if row < 0 or row >= len(self._widgets()):
            return
        item = self._widgets()[row]
        if QMessageBox.question(
            self, "Developer Studio", f"Удалить «{item.get('id', '?')}»?"
        ) != QMessageBox.Yes:
            return
        self._widgets().pop(row)
        save_config(self.config)
        next_row = min(row, len(self._widgets()) - 1)
        self.current_index = next_row
        self._reload_list(next_row)
        if callable(self.apply_callback):
            self.apply_callback()

    def _move_current(self, direction):
        row = self.current_index
        target = row + int(direction)
        if row < 0 or target < 0 or target >= len(self._widgets()):
            return
        widgets = self._widgets()
        widgets[row], widgets[target] = widgets[target], widgets[row]
        save_config(self.config)
        self.current_index = target
        self._reload_list(target)
        if callable(self.apply_callback):
            self.apply_callback()

    def _refresh_canvas(self):
        self.canvas.scene_obj.clear()
        self._canvas_items = {}
        for index, raw in enumerate(self._widgets()):
            item = _upgrade_item(raw)
            if item.get("placement") != "floating":
                continue
            g = StudioGraphicsItem(index, item, self._canvas_changed)
            self.canvas.scene_obj.addItem(g)
            self._canvas_items[index] = g
        self._select_canvas_item(self.current_index)

    def _select_canvas_item(self, index):
        for i, item in getattr(self, "_canvas_items", {}).items():
            item.setSelected(i == index)

    def _canvas_changed(self, index, x, y, width, height, save_now):
        if index < 0 or index >= len(self._widgets()):
            return
        item = _upgrade_item(self._widgets()[index])
        item["x"] = max(0, x)
        item["y"] = max(0, y)
        item["width"] = max(24, width)
        item["height"] = max(20, height)
        self._widgets()[index] = item

        self.widget_list.setCurrentRow(index)
        self.current_index = index
        self.x_spin.setValue(item["x"])
        self.y_spin.setValue(item["y"])
        self.width_spin.setValue(item["width"])
        self.height_spin.setValue(item["height"])
        if save_now:
            save_config(self.config)
            if callable(self.apply_callback):
                self.apply_callback()
