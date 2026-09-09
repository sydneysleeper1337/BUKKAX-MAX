# -*- coding: utf-8 -*-
"""
BUKKAX Developer Builder Sync V2

Публичная конфигурация синхронизируется через сервер.
Локальные visibility=me / Python / EXE элементы сохраняются только у разработчика
и не стираются при получении server-config.
"""

import json

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

_PATCHED = False
MAX_CONFIG_BYTES = 2 * 1024 * 1024


def install_builder_sync(MainWindow, send_frame, admin_nickname):
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    def _builder_request_config(self):
        if not getattr(self, "client", None):
            return
        try:
            send_frame(self.client, {"type": "builder_config_request"})
        except Exception as e:
            try:
                print("Builder config request error:", e)
            except Exception:
                pass

    def _builder_publish_config(self, config):
        if getattr(self, "nickname", None) != admin_nickname:
            QMessageBox.warning(
                self, "Developer Studio",
                "Публиковать интерфейс может только разработчик."
            )
            return

        try:
            from bukkax_dev_builder import public_config
            safe_config, skipped = public_config(config)
            raw = json.dumps(
                safe_config,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except Exception as e:
            QMessageBox.warning(self, "Developer Studio", f"Ошибка конфигурации:\n{e}")
            return

        if len(raw) > MAX_CONFIG_BYTES:
            QMessageBox.warning(
                self, "Developer Studio",
                "Публичная конфигурация слишком большая. Лимит V2 — 2 МБ."
            )
            return

        try:
            send_frame(
                self.client,
                {"type": "builder_config_publish", "size": len(raw)},
                raw,
            )
        except Exception as e:
            QMessageBox.warning(self, "Developer Studio", f"Не удалось отправить:\n{e}")

    def _builder_apply_server_payload(self, payload, notify=False):
        if not payload:
            return False
        try:
            public = json.loads(payload.decode("utf-8"))
        except Exception as e:
            try:
                print("Builder config decode error:", e)
            except Exception:
                pass
            return False

        if not isinstance(public, dict) or not isinstance(public.get("widgets"), list):
            return False

        try:
            from bukkax_dev_builder import load_config, merge_public_into_local, save_config
            local = load_config()
            merged = merge_public_into_local(local, public)
            save_config(merged)
            self._reload_developer_widgets()
        except Exception as e:
            try:
                print("Builder config apply error:", e)
            except Exception:
                pass
            return False

        if notify:
            try:
                self._append_html("general", "🛠 Интерфейс BUKKAX обновлён разработчиком.")
            except Exception:
                pass
        return True

    def _open_developer_builder_sync(self):
        if getattr(self, "nickname", None) != admin_nickname:
            QMessageBox.warning(
                self, "Developer Studio",
                "Developer Studio доступна только разработчику."
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
                admin_nickname,
                apply_callback=self._reload_developer_widgets,
                publish_callback=self._builder_publish_config,
            )
            self.dev_builder_dialog.finished.connect(
                lambda *_: setattr(self, "dev_builder_dialog", None)
            )
            self.dev_builder_dialog.show()
            self.dev_builder_dialog.raise_()
            self.dev_builder_dialog.activateWindow()
        except Exception as e:
            QMessageBox.warning(self, "Developer Studio", f"Не удалось открыть:\n{e}")

    MainWindow._builder_request_config = _builder_request_config
    MainWindow._builder_publish_config = _builder_publish_config
    MainWindow._builder_apply_server_payload = _builder_apply_server_payload
    MainWindow.open_developer_builder = _open_developer_builder_sync

    old_connect = MainWindow.connect_to_server

    def connect_to_server_with_builder_sync(self, *args, **kwargs):
        result = old_connect(self, *args, **kwargs)
        if getattr(self, "nickname", None):
            QTimer.singleShot(450, self._builder_request_config)
        return result

    MainWindow.connect_to_server = connect_to_server_with_builder_sync

    old_handle_frame = MainWindow._handle_frame

    def handle_frame_with_builder_sync(self, header, payload):
        msg_type = header.get("type")
        if msg_type in ("builder_config_data", "builder_config_updated"):
            self._builder_apply_server_payload(
                payload,
                notify=(msg_type == "builder_config_updated"),
            )
            return
        if msg_type == "builder_config_missing":
            return
        if msg_type == "builder_config_publish_result":
            status = header.get("status")
            if status == "ok":
                QMessageBox.information(
                    self,
                    "Developer Studio",
                    "✅ Публичная часть интерфейса опубликована.\n\n"
                    "Локальные Python/EXE элементы остались только у вас.",
                )
            elif status == "forbidden":
                QMessageBox.warning(self, "Developer Studio", "Сервер отклонил публикацию.")
            else:
                QMessageBox.warning(
                    self, "Developer Studio",
                    "Сервер отклонил конфигурацию: " + str(status or "ошибка"),
                )
            return
        return old_handle_frame(self, header, payload)

    MainWindow._handle_frame = handle_frame_with_builder_sync
