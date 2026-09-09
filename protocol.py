import struct
import json


def recv_exact(sock, n):
    """Читает РОВНО n байт из сокета (recv может вернуть меньше, чем просили)."""
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Соединение разорвано")
        data += chunk
    return data


def send_frame(sock, header: dict, payload: bytes = b''):
    """
    Отправляет один 'кадр' сообщения:
    [4 байта длины заголовка][JSON-заголовок][полезная нагрузка (файл), если есть]
    """
    header_bytes = json.dumps(header, ensure_ascii=False).encode('utf-8')
    sock.sendall(struct.pack('!I', len(header_bytes)))
    sock.sendall(header_bytes)
    if payload:
        sock.sendall(payload)


def recv_frame(sock):
    """
    Принимает один 'кадр' сообщения.
    Возвращает (header_dict, payload_bytes).
    Если в заголовке есть непустое поле 'size' — следом читается payload такого размера
    (используется для файлов, картинок из буфера, аватарок и т.д.).
    """
    raw_len = recv_exact(sock, 4)
    header_len = struct.unpack('!I', raw_len)[0]
    header_bytes = recv_exact(sock, header_len)
    header = json.loads(header_bytes.decode('utf-8'))

    payload = b''
    if header.get('size'):
        payload = recv_exact(sock, header['size'])

    return header, payload
