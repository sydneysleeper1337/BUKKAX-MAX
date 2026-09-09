# -*- coding: utf-8 -*-
"""
BUKKAX Call Quality V2 SAFE

Без нового аудио-протокола.
Проводной формат остаётся полностью совместим со старым BUKKAX:
    [16 bytes call_id][1 byte role][raw PCM]

Что меняется:
- микрофонный PCM дробится на маленькие UDP-пакеты по 10 мс;
- пакеты не раздуваются до больших IP-фрагментов;
- на приёме есть небольшой jitter-buffer ~60-120 мс;
- никаких capability/FEC/magic-заголовков;
- новый клиент совместим со старым клиентом.

Это специально проще и надёжнее V1.
"""

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QHostAddress

_PACKET_MS = 10
_PREBUFFER_MS = 70
_MAX_BUFFER_MS = 350
_TARGET_BUFFER_MS = 100

_PATCHED = False


def install_call_quality(
    MainWindow,
    send_frame,
    server_ip,
    voice_udp_port,
):
    global _PATCHED

    if _PATCHED:
        return

    _PATCHED = True

    old_call_started = MainWindow._handle_call_started
    old_cleanup_call = MainWindow._cleanup_call
    old_mic = MainWindow._on_mic_data
    old_rx = MainWindow._on_call_udp_data

    def _voice_v2_chunk_size(self):
        rate = int(
            getattr(
                self,
                "audio_sample_rate",
                48000,
            )
            or 48000
        )

        # mono Int16 = 2 bytes/sample
        size = int(
            rate
            * 2
            * _PACKET_MS
            / 1000
        )

        size = max(
            160,
            size,
        )

        if size % 2:
            size += 1

        return size

    def _voice_v2_reset(self):
        timer = getattr(
            self,
            "_voice_v2_timer",
            None,
        )

        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass

        self._voice_v2_timer = None
        self._voice_v2_tx_buffer = bytearray()
        self._voice_v2_rx_buffer = bytearray()
        self._voice_v2_started = False
        self._voice_v2_silence_ticks = 0

    def _voice_v2_ensure_timer(self):
        timer = getattr(
            self,
            "_voice_v2_timer",
            None,
        )

        if timer is not None:
            return

        timer = QTimer(self)
        timer.setInterval(_PACKET_MS)
        timer.timeout.connect(
            self._voice_v2_play_tick
        )

        self._voice_v2_timer = timer
        timer.start()

    def _voice_v2_play_tick(self):
        if getattr(
            self,
            "group_call",
            None,
        ):
            return

        current = getattr(
            self,
            "current_call",
            None,
        )

        if (
            not current
            or current.get("state") != "active"
        ):
            return

        speaker = getattr(
            self,
            "speaker_io",
            None,
        )

        if speaker is None:
            return

        buf = getattr(
            self,
            "_voice_v2_rx_buffer",
            None,
        )

        if buf is None:
            buf = bytearray()
            self._voice_v2_rx_buffer = buf

        chunk_size = self._voice_v2_chunk_size()

        prebuffer_bytes = max(
            chunk_size * 3,
            int(
                chunk_size
                * _PREBUFFER_MS
                / _PACKET_MS
            ),
        )

        if not getattr(
            self,
            "_voice_v2_started",
            False,
        ):
            if len(buf) < prebuffer_bytes:
                return

            self._voice_v2_started = True

        if len(buf) >= chunk_size:
            data = bytes(
                buf[:chunk_size]
            )
            del buf[:chunk_size]
            self._voice_v2_silence_ticks = 0
        else:
            # Небольшой разрыв лучше заполнить тишиной, чем ломать аудиопоток.
            data = b"\x00" * chunk_size
            self._voice_v2_silence_ticks = (
                int(
                    getattr(
                        self,
                        "_voice_v2_silence_ticks",
                        0,
                    )
                )
                + 1
            )

            # Если сеть реально остановилась, ждём новый prebuffer.
            if self._voice_v2_silence_ticks >= 8:
                self._voice_v2_started = False
                self._voice_v2_silence_ticks = 0
                return

        if getattr(
            self,
            "speaker_gain",
            1.0,
        ) != 1.0:
            data = self._apply_gain(
                data,
                self.speaker_gain,
            )

        try:
            speaker.write(
                data
            )
        except Exception:
            pass

    def call_started_with_voice_v2(
        self,
        header,
    ):
        result = old_call_started(
            self,
            header,
        )

        try:
            self._voice_v2_reset()
            self._voice_v2_ensure_timer()
        except Exception as e:
            try:
                print(
                    "Voice V2 timer init error:",
                    e,
                )
            except Exception:
                pass

        return result

    def cleanup_call_with_voice_v2(
        self,
        *args,
        **kwargs,
    ):
        try:
            self._voice_v2_reset()
        except Exception:
            pass

        return old_cleanup_call(
            self,
            *args,
            **kwargs,
        )

    def on_mic_data_voice_v2(self):
        # Групповые звонки пока оставляем полностью старому коду.
        if getattr(
            self,
            "group_call",
            None,
        ):
            return old_mic(
                self
            )

        mic = getattr(
            self,
            "mic_io",
            None,
        )

        if mic is None:
            return

        data = bytes(
            mic.readAll()
        )

        if not data:
            return

        current = getattr(
            self,
            "current_call",
            None,
        )

        if (
            not current
            or current.get("state") != "active"
        ):
            return

        data = self._apply_gain(
            data,
            self.mic_gain,
        )

        data = self._apply_noise_reduction(
            data
        )

        if not data:
            return

        tx = getattr(
            self,
            "_voice_v2_tx_buffer",
            None,
        )

        if tx is None:
            tx = bytearray()
            self._voice_v2_tx_buffer = tx

        tx.extend(
            data
        )

        chunk_size = self._voice_v2_chunk_size()

        while len(tx) >= chunk_size:
            chunk = bytes(
                tx[:chunk_size]
            )
            del tx[:chunk_size]

            try:
                packet = (
                    self._call_packet_prefix()
                    + chunk
                )

                self.call_udp_socket.writeDatagram(
                    packet,
                    QHostAddress(server_ip),
                    voice_udp_port,
                )
            except Exception:
                return

    def on_call_udp_data_voice_v2(self):
        # Групповые звонки остаются на старом обработчике.
        if getattr(
            self,
            "group_call",
            None,
        ):
            return old_rx(
                self
            )

        try:
            self._voice_v2_ensure_timer()
        except Exception:
            pass

        buf = getattr(
            self,
            "_voice_v2_rx_buffer",
            None,
        )

        if buf is None:
            buf = bytearray()
            self._voice_v2_rx_buffer = buf

        while self.call_udp_socket.hasPendingDatagrams():
            size = self.call_udp_socket.pendingDatagramSize()

            datagram, _host, _port = (
                self.call_udp_socket.readDatagram(
                    size
                )
            )

            if len(datagram) <= 17:
                continue

            # Формат тот же, что был в BUKKAX до эксперимента:
            # после 17-байтового префикса идёт только PCM.
            audio_data = datagram[17:]

            if not audio_data:
                continue

            # Int16 alignment
            if len(audio_data) % 2:
                audio_data = audio_data[:-1]

            if audio_data:
                buf.extend(
                    audio_data
                )

        chunk_size = self._voice_v2_chunk_size()

        max_bytes = int(
            chunk_size
            * _MAX_BUFFER_MS
            / _PACKET_MS
        )
        target_bytes = int(
            chunk_size
            * _TARGET_BUFFER_MS
            / _PACKET_MS
        )

        # Если сеть дала большой burst, не накапливаем секунды задержки.
        if len(buf) > max_bytes:
            drop = len(buf) - target_bytes

            if drop % 2:
                drop += 1

            del buf[:drop]

    MainWindow._voice_v2_chunk_size = _voice_v2_chunk_size
    MainWindow._voice_v2_reset = _voice_v2_reset
    MainWindow._voice_v2_ensure_timer = _voice_v2_ensure_timer
    MainWindow._voice_v2_play_tick = _voice_v2_play_tick

    MainWindow._handle_call_started = call_started_with_voice_v2
    MainWindow._cleanup_call = cleanup_call_with_voice_v2
    MainWindow._on_mic_data = on_mic_data_voice_v2
    MainWindow._on_call_udp_data = on_call_udp_data_voice_v2
