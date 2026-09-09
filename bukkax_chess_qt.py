"""
BUKKAX Chess Qt module.

Порт шахмат из pygame в PySide6: доска, фигуры, легальные ходы,
рокировка, превращение пешки, мат/пат и сетевые callbacks для BUKKAX.
"""

import os
import sys
import random
from copy import deepcopy

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QMessageBox, QInputDialog,
    QSizePolicy,
    QWidget, QComboBox,
)


PIECE_SYMBOLS = {
    'K0': '♔', 'Q0': '♕', 'R0': '♖', 'B0': '♗', 'H0': '♘', 'P0': '♙',
    'K1': '♚', 'Q1': '♛', 'R1': '♜', 'B1': '♝', 'H1': '♞', 'p1': '♟',
}

PIECE_NAMES = {
    'Q': 'Ферзь',
    'R': 'Ладья',
    'B': 'Слон',
    'H': 'Конь',
}


def _base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ---------- BUKKAX CHESS WHITE TEXT STYLE START ----------
CHESS_DARK_STYLE = r"""
QDialog, QMessageBox, QInputDialog {
    background-color: #151824;
    color: #ffffff;
}
QWidget {
    color: #ffffff;
}
QLabel, QMessageBox QLabel, QInputDialog QLabel {
    color: #ffffff;
    background: transparent;
}
QPushButton {
    border-radius: 6px;
    color: #ffffff;
    background: #273047;
    padding: 4px 8px;
    font-weight: 600;
}
QPushButton:hover {
    background: #33405f;
}
QPushButton:pressed {
    background: #1e263a;
}
QPushButton:disabled {
    color: #8d96b3;
    background: #202638;
}
QLineEdit, QComboBox, QListView, QAbstractItemView {
    color: #ffffff;
    background: #202638;
    selection-color: #ffffff;
    selection-background-color: #3d63b8;
    border: 1px solid #3b4564;
    border-radius: 6px;
    padding: 4px 8px;
}
QComboBox QAbstractItemView {
    color: #ffffff;
    background: #202638;
    selection-color: #ffffff;
    selection-background-color: #3d63b8;
}
QCheckBox, QRadioButton {
    color: #ffffff;
}
QToolTip {
    color: #ffffff;
    background-color: #202638;
    border: 1px solid #4b5a80;
}
"""


def apply_chess_dark_style(widget):
    """Применяет белый шрифт/тёмный фон к шахматному окну или попапу."""
    try:
        widget.setStyleSheet(CHESS_DARK_STYLE)
    except Exception:
        pass
    return widget


def _chess_message_box(parent, title, text, icon, buttons):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(str(text))
    box.setIcon(icon)
    box.setStandardButtons(buttons)
    apply_chess_dark_style(box)
    try:
        yes_btn = box.button(QMessageBox.Yes)
        if yes_btn:
            yes_btn.setText('Да')
        no_btn = box.button(QMessageBox.No)
        if no_btn:
            no_btn.setText('Нет')
        ok_btn = box.button(QMessageBox.Ok)
        if ok_btn:
            ok_btn.setText('OK')
    except Exception:
        pass
    return box.exec()


def chess_info(parent, title, text):
    return _chess_message_box(parent, title, text, QMessageBox.Information, QMessageBox.Ok)


def chess_warning(parent, title, text):
    return _chess_message_box(parent, title, text, QMessageBox.Warning, QMessageBox.Ok)


def chess_critical(parent, title, text):
    return _chess_message_box(parent, title, text, QMessageBox.Critical, QMessageBox.Ok)


def chess_question(parent, title, text):
    return _chess_message_box(parent, title, text, QMessageBox.Question, QMessageBox.Yes | QMessageBox.No)


def chess_get_text(parent, title, label, text=''):
    dlg = QInputDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setLabelText(label)
    try:
        dlg.setTextValue(text or '')
    except Exception:
        pass
    apply_chess_dark_style(dlg)
    ok = dlg.exec() == QDialog.Accepted
    return dlg.textValue(), ok


def chess_get_item(parent, title, label, items, current=0, editable=False):
    dlg = QInputDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setLabelText(label)
    dlg.setComboBoxItems(list(items))
    dlg.setComboBoxEditable(bool(editable))
    try:
        combo = dlg.findChild(QComboBox)
        if combo is not None:
            combo.setCurrentIndex(int(current or 0))
    except Exception:
        pass
    apply_chess_dark_style(dlg)
    ok = dlg.exec() == QDialog.Accepted
    return dlg.textValue(), ok
# ---------- BUKKAX CHESS WHITE TEXT STYLE END ----------


class ChessRules:
    START_BOARD = [
        ['R1', 'H1', 'B1', 'Q1', 'K1', 'B1', 'H1', 'R1'],
        ['p1', 'p1', 'p1', 'p1', 'p1', 'p1', 'p1', 'p1'],
        ['.', '.', '.', '.', '.', '.', '.', '.'],
        ['.', '.', '.', '.', '.', '.', '.', '.'],
        ['.', '.', '.', '.', '.', '.', '.', '.'],
        ['.', '.', '.', '.', '.', '.', '.', '.'],
        ['P0', 'P0', 'P0', 'P0', 'P0', 'P0', 'P0', 'P0'],
        ['R0', 'H0', 'B0', 'Q0', 'K0', 'B0', 'H0', 'R0'],
    ]

    ATTACKS = {
        'R': [[0, 1], [1, 0], [0, -1], [-1, 0], 1],
        'B': [[1, 1], [-1, -1], [1, -1], [-1, 1], 1],
        'Q': [[1, 1], [-1, -1], [1, -1], [-1, 1], [0, 1], [1, 0], [0, -1], [-1, 0], 1],
        'H': [[1, 2], [2, 1], [-1, -2], [-2, -1], [-1, 2], [-2, 1], [1, -2], [2, -1], 0],
        'P': [[-1, -1], [1, -1], 0],
        'p': [[-1, 1], [1, 1], 0],
        'K': [[1, 1], [-1, -1], [1, -1], [-1, 1], [0, 1], [1, 0], [0, -1], [-1, 0], 0],
    }

    def __init__(self):
        self.reset()

    def reset(self):
        self.board = deepcopy(self.START_BOARD)
        self.turn = 0  # 0 — белые, 1 — чёрные
        self.castlingL0 = True
        self.castlingR0 = True
        self.castlingL1 = True
        self.castlingR1 = True
        self.result = None

    @staticmethod
    def inside(x, y):
        return 0 <= x <= 7 and 0 <= y <= 7

    def is_check(self, color):
        color = str(color)
        for y in range(8):
            for x in range(8):
                piece = self.board[y][x]
                if piece == '.':
                    continue
                if piece[1] == color:
                    continue
                for shift in self.ATTACKS[piece[0]][0:-1]:
                    pos = [x, y]
                    for _ in range(self.ATTACKS[piece[0]][-1] * 6 + 1):
                        pos[0] += shift[0]
                        pos[1] += shift[1]
                        if not self.inside(pos[0], pos[1]):
                            break
                        target = self.board[pos[1]][pos[0]]
                        if target != '.':
                            if target != 'K' + color:
                                break
                            return True
        return False

    def legal_moves(self, x, y):
        if not self.inside(x, y):
            return []
        piece = self.board[y][x]
        if piece == '.':
            return []

        variants = []
        for shift in self.ATTACKS[piece[0]][0:-1]:
            pos = [x, y]
            for _ in range(self.ATTACKS[piece[0]][-1] * 6 + 1):
                pos[0] += shift[0]
                pos[1] += shift[1]
                if not self.inside(pos[0], pos[1]):
                    break
                target = self.board[pos[1]][pos[0]]
                if target != '.':
                    if target[1] != piece[1]:
                        variants.append((pos[0], pos[1]))
                    break
                elif piece[0] not in ('p', 'P'):
                    variants.append((pos[0], pos[1]))

        if piece[0] == 'P':
            pos = [x, y]
            for _ in range((y == 6) + 1):
                pos[1] -= 1
                if pos[1] < 0:
                    break
                if self.board[pos[1]][pos[0]] != '.':
                    break
                variants.append((pos[0], pos[1]))

        if piece[0] == 'p':
            pos = [x, y]
            for _ in range((y == 1) + 1):
                pos[1] += 1
                if pos[1] > 7:
                    break
                if self.board[pos[1]][pos[0]] != '.':
                    break
                variants.append((pos[0], pos[1]))

        # Убираем ходы, после которых свой король под шахом.
        filtered = []
        self.board[y][x] = '.'
        for vx, vy in variants:
            remembered = self.board[vy][vx]
            self.board[vy][vx] = piece
            if not self.is_check(piece[1]):
                filtered.append((vx, vy))
            self.board[vy][vx] = remembered
        self.board[y][x] = piece
        variants = filtered

        if piece == 'K0':
            if self.board[7][0:5] == ['R0', '.', '.', '.', 'K0'] and self.castlingL0:
                self.board[7][2], self.board[7][3] = 'K0', 'K0'
                if not self.is_check('0'):
                    variants.append((2, 7))
                self.board[7][2], self.board[7][3] = '.', '.'
            if self.board[7][4:8] == ['K0', '.', '.', 'R0'] and self.castlingR0:
                self.board[7][5], self.board[7][6] = 'K0', 'K0'
                if not self.is_check('0'):
                    variants.append((6, 7))
                self.board[7][5], self.board[7][6] = '.', '.'

        if piece == 'K1':
            if self.board[0][0:5] == ['R1', '.', '.', '.', 'K1'] and self.castlingL1:
                self.board[0][2], self.board[0][3] = 'K1', 'K1'
                if not self.is_check('1'):
                    variants.append((2, 0))
                self.board[0][2], self.board[0][3] = '.', '.'
            if self.board[0][4:8] == ['K1', '.', '.', 'R1'] and self.castlingR1:
                self.board[0][5], self.board[0][6] = 'K1', 'K1'
                if not self.is_check('1'):
                    variants.append((6, 0))
                self.board[0][5], self.board[0][6] = '.', '.'

        return variants

    def checkmate_status(self, color):
        color = str(color)
        for y in range(8):
            for x in range(8):
                piece = self.board[y][x]
                if piece != '.' and piece[-1] == color:
                    if self.legal_moves(x, y):
                        return 0
        return 1 if self.is_check(color) else 2

    def move(self, x1, y1, x2, y2, promotion='Q'):
        if self.result:
            return False, 'Партия уже завершена'
        if not (self.inside(x1, y1) and self.inside(x2, y2)):
            return False, 'Координаты вне доски'
        piece = self.board[y1][x1]
        if piece == '.':
            return False, 'В выбранной клетке нет фигуры'
        if int(piece[1]) != self.turn:
            return False, 'Сейчас ход другого цвета'
        if (x2, y2) not in self.legal_moves(x1, y1):
            return False, 'Так ходить нельзя'

        self.board[y2][x2] = piece
        self.board[y1][x1] = '.'

        # Рокировка.
        if [x1, y1] == [4, 7] and self.board[y2][x2] == 'K0':
            if [x2, y2] == [2, 7]:
                self.board[7][0] = '.'
                self.board[7][3] = 'R0'
            if [x2, y2] == [6, 7]:
                self.board[7][7] = '.'
                self.board[7][5] = 'R0'
        if [x1, y1] == [4, 0] and self.board[y2][x2] == 'K1':
            if [x2, y2] == [2, 0]:
                self.board[0][0] = '.'
                self.board[0][3] = 'R1'
            if [x2, y2] == [6, 0]:
                self.board[0][7] = '.'
                self.board[0][5] = 'R1'

        # Обновляем права рокировки.
        if self.board[7][0] != 'R0':
            self.castlingL0 = False
        if self.board[7][7] != 'R0':
            self.castlingR0 = False
        if self.board[7][4] != 'K0':
            self.castlingL0 = False
            self.castlingR0 = False
        if self.board[0][0] != 'R1':
            self.castlingL1 = False
        if self.board[0][7] != 'R1':
            self.castlingR1 = False
        if self.board[0][4] != 'K1':
            self.castlingL1 = False
            self.castlingR1 = False

        # Превращение пешки.
        promotion = (promotion or 'Q').upper()
        if promotion not in ('Q', 'R', 'B', 'H'):
            promotion = 'Q'
        if piece == 'P0' and y2 == 0:
            self.board[y2][x2] = promotion + '0'
        if piece == 'p1' and y2 == 7:
            self.board[y2][x2] = promotion + '1'

        self.turn = 1 - self.turn
        status = self.checkmate_status(str(self.turn))
        if status == 1:
            winner = 1 - self.turn
            self.result = f"Мат. {'Белые' if winner == 0 else 'Чёрные'} победили"
        elif status == 2:
            self.result = 'Пат. Ничья'
        return True, self.result or ''


class ChessDialog(QDialog):
    def __init__(self, parent, my_nick, opponent, color, game_id,
                 send_move_cb=None, send_restart_cb=None, send_resign_cb=None):
        super().__init__(parent)
        self.parent = parent
        self.my_nick = my_nick
        self.opponent = opponent
        self.my_color = int(color)
        self.game_id = game_id
        self.send_move_cb = send_move_cb
        self.send_restart_cb = send_restart_cb
        self.send_resign_cb = send_resign_cb
        self.rules = ChessRules()
        self.selected = None
        self.legal = []
        self.buttons = {}
        self.icons = {}
        self.game_over = False
        self.setWindowTitle(f"♟ Шахматы — {opponent}")
        self.resize(690, 760)
        self._load_icons()
        self._build_ui()
        self._redraw()

    def _assets_dir(self):
        return os.path.join(_base_dir(), 'bukkax_chess_assets')

    def _load_icons(self):
        assets = self._assets_dir()
        for code in PIECE_SYMBOLS:
            path = os.path.join(assets, code + '.png')
            if os.path.exists(path):
                pix = QPixmap(path)
                if not pix.isNull():
                    self.icons[code] = QIcon(pix)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)

        self.title = QLabel()
        self.title.setWordWrap(False)
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.title.setStyleSheet('font-size: 17px; font-weight: bold; color: #ffffff;')
        top.addWidget(self.title, 1)

        self.restart_btn = QPushButton('↻ Новая')
        self.restart_btn.setToolTip('Начать новую партию')
        self.restart_btn.setFixedHeight(30)
        self.restart_btn.setMinimumWidth(86)
        self.restart_btn.clicked.connect(self._restart_clicked)
        top.addWidget(self.restart_btn, 0)

        self.resign_btn = QPushButton('🏳 Сдаться')
        self.resign_btn.setToolTip('Сдаться / закрыть партию')
        self.resign_btn.setFixedHeight(30)
        self.resign_btn.setMinimumWidth(92)
        self.resign_btn.clicked.connect(self._resign_clicked)
        top.addWidget(self.resign_btn, 0)
        root.addLayout(top)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet('font-size: 13px; color: #ffffff;')
        root.addWidget(self.status)

        self.board_wrap = QWidget()
        self.board_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.board_box = QGridLayout(self.board_wrap)
        self.board_box.setContentsMargins(0, 0, 0, 0)
        self.board_box.setSpacing(0)
        for row in range(8):
            for col in range(8):
                btn = QPushButton()
                btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                btn.setFixedSize(78, 78)
                btn.setIconSize(QSize(62, 62))
                btn.clicked.connect(lambda checked=False, c=col, r=row: self._square_clicked(c, r))
                self.board_box.addWidget(btn, row, col)
                self.buttons[(col, row)] = btn
        root.addWidget(self.board_wrap, 0, Qt.AlignHCenter)

        hint = QLabel('Белые ходят первыми. Фигуру выбираешь кликом, потом кликаешь клетку хода.')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #ffffff; font-size: 12px;')
        root.addWidget(hint)
        self.setStyleSheet(CHESS_DARK_STYLE)
        self._resize_board_cells()

    def _resize_board_cells(self):
        # Держит шахматную доску ровным квадратом и не даёт клеткам разъезжаться.
        try:
            available_w = max(360, self.width() - 34)
            # сверху заголовок/статус/подсказка, поэтому высоту режем аккуратно
            available_h = max(360, self.height() - 128)
            cell = min(82, max(52, min(available_w // 8, available_h // 8)))
            icon = max(36, cell - 16)
            if hasattr(self, 'board_wrap'):
                self.board_wrap.setFixedSize(cell * 8, cell * 8)
            for btn in getattr(self, 'buttons', {}).values():
                btn.setFixedSize(cell, cell)
                btn.setIconSize(QSize(icon, icon))
        except Exception:
            pass

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        self._resize_board_cells()

    def _resize_board_cells(self):
        # Держит шахматную доску ровным квадратом и не даёт клеткам разъезжаться.
        try:
            available_w = max(360, self.width() - 34)
            # сверху заголовок/статус/подсказка, поэтому высоту режем аккуратно
            available_h = max(360, self.height() - 128)
            cell = min(82, max(52, min(available_w // 8, available_h // 8)))
            icon = max(36, cell - 16)
            if hasattr(self, 'board_wrap'):
                self.board_wrap.setFixedSize(cell * 8, cell * 8)
            for btn in getattr(self, 'buttons', {}).values():
                btn.setFixedSize(cell, cell)
                btn.setIconSize(QSize(icon, icon))
        except Exception:
            pass

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        self._resize_board_cells()

    def _display_to_board(self, dx, dy):
        if self.my_color == 1:
            return 7 - dx, 7 - dy
        return dx, dy

    def _board_to_display(self, bx, by):
        if self.my_color == 1:
            return 7 - bx, 7 - by
        return bx, by

    def _turn_text(self):
        return 'Белые' if self.rules.turn == 0 else 'Чёрные'

    def _my_color_text(self):
        return 'белыми' if self.my_color == 0 else 'чёрными'

    def _update_status(self):
        try:
            self.title.setText(f"♟ {self.opponent} — вы: {self._my_color_text()}")
        except Exception:
            pass
        if self.game_over or self.rules.result:
            self.status.setText(self.rules.result or 'Партия завершена')
            return
        extra = 'Ваш ход' if self.rules.turn == self.my_color else f'Ходит {self.opponent}'
        self.status.setText(f"Сейчас ходят: {self._turn_text()}. {extra}.")

    def _redraw(self):
        self._update_status()
        for dy in range(8):
            for dx in range(8):
                bx, by = self._display_to_board(dx, dy)
                piece = self.rules.board[by][bx]
                btn = self.buttons[(dx, dy)]
                light = (bx + by) % 2 == 0
                bg = '#F0D9B5' if light else '#B58863'
                border = '1px solid #262626'
                if self.selected == (bx, by):
                    border = '3px solid #4EA1FF'
                elif (bx, by) in self.legal:
                    border = '3px solid #6ee76e'
                    bg = '#9fd58b' if light else '#75a869'
                btn.setStyleSheet(f"background: {bg}; border: {border}; font-size: 34px; color: #111111;")
                if piece != '.' and piece in self.icons:
                    btn.setIcon(self.icons[piece])
                    btn.setText('')
                elif piece != '.':
                    btn.setIcon(QIcon())
                    btn.setText(PIECE_SYMBOLS.get(piece, piece))
                else:
                    btn.setIcon(QIcon())
                    btn.setText('')

    def _square_clicked(self, dx, dy):
        if self.game_over or self.rules.result:
            return
        bx, by = self._display_to_board(dx, dy)
        if self.rules.turn != self.my_color:
            chess_info(self, 'Шахматы', 'Сейчас ход соперника.')
            return

        if self.selected and (bx, by) in self.legal:
            x1, y1 = self.selected
            promotion = self._promotion_if_needed(x1, y1, bx, by)
            ok, result = self.rules.move(x1, y1, bx, by, promotion)
            if not ok:
                chess_warning(self, 'Шахматы', result)
                return
            self.selected = None
            self.legal = []
            self._redraw()
            if self.send_move_cb:
                self.send_move_cb(self.game_id, self.opponent, [x1, y1], [bx, by], promotion or '')
            if result:
                self.game_over = True
                chess_info(self, 'Шахматы', result)
            return

        piece = self.rules.board[by][bx]
        if piece != '.' and int(piece[1]) == self.my_color:
            moves = self.rules.legal_moves(bx, by)
            if not moves:
                chess_info(self, 'Шахматы', 'У этой фигуры нет доступных ходов.')
                return
            self.selected = (bx, by)
            self.legal = moves
        else:
            self.selected = None
            self.legal = []
        self._redraw()

    def _promotion_if_needed(self, x1, y1, x2, y2):
        piece = self.rules.board[y1][x1]
        if not ((piece == 'P0' and y2 == 0) or (piece == 'p1' and y2 == 7)):
            return ''
        choice, ok = chess_get_item(
            self, 'Превращение пешки', 'Выбери фигуру:',
            ['Ферзь', 'Ладья', 'Слон', 'Конь'], 0, False,
        )
        if not ok:
            return 'Q'
        reverse = {'Ферзь': 'Q', 'Ладья': 'R', 'Слон': 'B', 'Конь': 'H'}
        return reverse.get(choice, 'Q')

    def apply_remote_move(self, src, dst, promotion=''):
        try:
            x1, y1 = int(src[0]), int(src[1])
            x2, y2 = int(dst[0]), int(dst[1])
        except Exception:
            chess_warning(self, 'Шахматы', 'Пришёл неправильный ход от соперника.')
            return
        ok, result = self.rules.move(x1, y1, x2, y2, promotion)
        if not ok:
            chess_warning(self, 'Шахматы', f'Не удалось применить ход соперника: {result}')
            return
        self.selected = None
        self.legal = []
        self._redraw()
        if result:
            self.game_over = True
            chess_info(self, 'Шахматы', result)

    def reset_game(self):
        self.rules.reset()
        self.game_over = False
        self.selected = None
        self.legal = []
        self._redraw()

    def remote_restart(self):
        self.reset_game()
        chess_info(self, 'Шахматы', f'{self.opponent} начал новую партию.')

    def remote_resign(self):
        self.game_over = True
        self.rules.result = f'{self.opponent} сдался. Вы победили.'
        self._redraw()
        chess_info(self, 'Шахматы', self.rules.result)

    def _restart_clicked(self):
        if chess_question(self, 'Шахматы', 'Начать новую партию?') != QMessageBox.Yes:
            return
        self.reset_game()
        if self.send_restart_cb:
            self.send_restart_cb(self.game_id, self.opponent)

    def _resign_clicked(self):
        if chess_question(self, 'Шахматы', 'Сдаться в этой партии?') != QMessageBox.Yes:
            return
        self.game_over = True
        self.rules.result = 'Вы сдались.'
        self._redraw()
        if self.send_resign_cb:
            self.send_resign_cb(self.game_id, self.opponent)

# ---------- BUKKAX CHESS BOT START ----------
CHESS_BOT_NAME = 'Бот Кленовый черт'

PIECE_VALUES_BOT = {
    'P': 100, 'p': 100,
    'H': 320, 'B': 330,
    'R': 500,
    'Q': 900,
    'K': 20000,
}


def _bot_all_legal_moves(rules, color):
    """Возвращает все легальные ходы цвета color в формате (x1, y1, x2, y2, score)."""
    result = []
    color = str(color)
    for y in range(8):
        for x in range(8):
            piece = rules.board[y][x]
            if piece == '.' or piece[-1] != color:
                continue
            try:
                moves = rules.legal_moves(x, y)
            except Exception:
                moves = []
            for x2, y2 in moves:
                target = rules.board[y2][x2]
                score = 0
                if target != '.':
                    score += PIECE_VALUES_BOT.get(target[0], 0) + 30
                # Пешку выгоднее вести к превращению.
                if piece == 'p1':
                    score += y2 * 8
                    if y2 == 7:
                        score += 700
                if piece == 'P0':
                    score += (7 - y2) * 8
                    if y2 == 0:
                        score += 700
                # Маленький бонус за развитие коней/слонов из начальной позиции.
                if piece[0] in ('H', 'B') and y in (0, 7):
                    score += 20
                # Небольшой рандом, чтобы бот не играл каждый раз одинаково.
                score += random.randint(0, 25)
                result.append((x, y, x2, y2, score))
    return result


def _bot_choose_move(rules, color=1):
    moves = _bot_all_legal_moves(rules, color)
    if not moves:
        return None
    # В 25% случаев бот ходит случайно — так он остаётся простым и проходимым.
    if random.random() < 0.25:
        return random.choice(moves)
    moves.sort(key=lambda item: item[-1], reverse=True)
    # Выбираем один из нескольких лучших, чтобы не было полной предсказуемости.
    top = moves[:min(4, len(moves))]
    return random.choice(top)


class ChessBotDialog(ChessDialog):
    """Локальная партия с простым ботом. Цвет игрока выбирается случайно."""

    def __init__(self, parent, my_nick, game_id='chess_bot'):
        # ВАЖНО: эти поля ставим ДО super().__init__().
        # Базовый ChessDialog внутри __init__ сразу вызывает _redraw(),
        # а _redraw() вызывает наш переопределённый _update_status().
        self.bot_name = CHESS_BOT_NAME
        self.my_color = random.choice([0, 1])
        self.bot_color = 1 - self.my_color
        self.bot_thinking = False
        super().__init__(
            parent=parent,
            my_nick=my_nick,
            opponent=self.bot_name,
            color=self.my_color,
            game_id=game_id,
            send_move_cb=None,
            send_restart_cb=None,
            send_resign_cb=None,
        )
        self.bot_name = CHESS_BOT_NAME
        # На всякий случай сохраняем цвета после super().
        self.bot_color = 1 - self.my_color
        self.bot_thinking = False
        self.setWindowTitle(f'♟ {self.bot_name}')
        try:
            self.resign_btn.setText('Закрыть')
            self.resign_btn.setMinimumWidth(72)
            self.resign_btn.setMinimumWidth(72)
        except Exception:
            pass
        self._redraw()
        # Если бот получил белые, он ходит первым.
        if self.bot_color == 0:
            self._schedule_bot_move()

    def _update_status(self):
        try:
            bot_name = getattr(self, 'bot_name', 'Бот Кленовый черт')
            color_text = 'белые' if self.my_color == 0 else 'чёрные'
            # ВАЖНО: короткий заголовок, чтобы верхняя строка не распирала доску.
            self.title.setText(f'♟ {bot_name} — вы: {color_text}')
            if self.game_over or self.rules.result:
                self.status.setText(self.rules.result or 'Партия завершена')
                return
            if getattr(self, 'bot_thinking', False):
                self.status.setText(f'{bot_name} думает...')
                return
            extra = 'Ваш ход' if self.rules.turn == self.my_color else f'Ходит {bot_name}'
            self.status.setText(f"Сейчас ходят: {self._turn_text()}. {extra}.")
        except Exception:
            # Не даём окну молча упасть при первой отрисовке.
            pass

    def _square_clicked(self, dx, dy):
        if self.game_over or self.rules.result:
            return
        if getattr(self, 'bot_thinking', False):
            chess_info(self, 'Шахматы', f'Подожди, {self.bot_name} делает ход.')
            return
        if self.rules.turn != self.my_color:
            chess_info(self, 'Шахматы', f'Сейчас ходит {self.bot_name}.')
            return

        bx, by = self._display_to_board(dx, dy)

        if self.selected and (bx, by) in self.legal:
            x1, y1 = self.selected
            promotion = self._promotion_if_needed(x1, y1, bx, by)
            ok, result = self.rules.move(x1, y1, bx, by, promotion)
            if not ok:
                chess_warning(self, 'Шахматы', result)
                return
            self.selected = None
            self.legal = []
            self._redraw()
            if result:
                self.game_over = True
                chess_info(self, 'Шахматы', result)
                return
            self._schedule_bot_move()
            return

        piece = self.rules.board[by][bx]
        if piece != '.' and int(piece[1]) == self.my_color:
            moves = self.rules.legal_moves(bx, by)
            if not moves:
                chess_info(self, 'Шахматы', 'У этой фигуры нет доступных ходов.')
                return
            self.selected = (bx, by)
            self.legal = moves
        else:
            self.selected = None
            self.legal = []
        self._redraw()

    def _schedule_bot_move(self):
        if self.game_over or self.rules.result:
            return
        if self.rules.turn != getattr(self, 'bot_color', 1):
            return
        self.bot_thinking = True
        self._redraw()
        QTimer.singleShot(550, self._bot_move)

    def _bot_move(self):
        if self.game_over or self.rules.result:
            self.bot_thinking = False
            self._redraw()
            return
        if self.rules.turn != getattr(self, 'bot_color', 1):
            self.bot_thinking = False
            self._redraw()
            return

        move = _bot_choose_move(self.rules, getattr(self, 'bot_color', 1))
        if not move:
            self.bot_thinking = False
            status = self.rules.checkmate_status(str(getattr(self, 'bot_color', 1)))
            if status == 1:
                winner = 'Чёрные' if getattr(self, 'bot_color', 1) == 0 else 'Белые'
                self.rules.result = f'Мат. {winner} победили'
            else:
                self.rules.result = 'Пат. Ничья'
            self.game_over = True
            self._redraw()
            chess_info(self, 'Шахматы', self.rules.result)
            return

        x1, y1, x2, y2, _score = move
        piece = self.rules.board[y1][x1]
        promotion = 'Q' if ((piece == 'p1' and y2 == 7) or (piece == 'P0' and y2 == 0)) else ''
        ok, result = self.rules.move(x1, y1, x2, y2, promotion)
        self.bot_thinking = False
        if not ok:
            # На всякий случай, если выбранный ход внезапно не применился, пробуем любой другой.
            fallback = _bot_all_legal_moves(self.rules, getattr(self, 'bot_color', 1))
            if fallback:
                x1, y1, x2, y2, _score = random.choice(fallback)
                piece = self.rules.board[y1][x1]
                promotion = 'Q' if ((piece == 'p1' and y2 == 7) or (piece == 'P0' and y2 == 0)) else ''
                ok, result = self.rules.move(x1, y1, x2, y2, promotion)
        self.selected = None
        self.legal = []
        self._redraw()
        if result:
            self.game_over = True
            chess_info(self, 'Шахматы', result)

    def _restart_clicked(self):
        if chess_question(self, 'Шахматы', f'Начать новую партию с {self.bot_name}? Цвет снова выберется случайно.') != QMessageBox.Yes:
            return
        # В каждой новой партии снова рандомим цвет.
        self.my_color = random.choice([0, 1])
        self.bot_color = 1 - self.my_color
        self.reset_game()
        self.bot_thinking = False
        self._redraw()
        if self.bot_color == 0:
            self._schedule_bot_move()

    def _resign_clicked(self):
        self.close()
# ---------- BUKKAX CHESS BOT END ----------

# ---------- BUKKAX CHESS ASSET FIGURES FIX START ----------
def _bukkax_chess_asset_dirs_fixed():
    """Кандидаты, где могут лежать PNG-фигуры для шахмат."""
    dirs = []

    def add(path):
        try:
            if path and path not in dirs:
                dirs.append(path)
        except Exception:
            pass

    try:
        add(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bukkax_chess_assets'))
    except Exception:
        pass
    try:
        add(os.path.join(os.getcwd(), 'bukkax_chess_assets'))
    except Exception:
        pass
    try:
        add(os.path.join(os.path.dirname(sys.executable), 'bukkax_chess_assets'))
    except Exception:
        pass
    try:
        meipass = getattr(sys, '_MEIPASS', '')
        if meipass:
            add(os.path.join(meipass, 'bukkax_chess_assets'))
    except Exception:
        pass

    return dirs


def _bukkax_piece_png_path_fixed(code):
    """Находит PNG для фигуры. Поддерживает p1.png / P1.png и разные регистры."""
    names = []

    def add_name(name):
        if name and name not in names:
            names.append(name)

    add_name(f'{code}.png')
    add_name(f'{str(code).lower()}.png')
    add_name(f'{str(code).upper()}.png')

    # В старых ассетах чёрная пешка может называться p1.png, а не P1.png.
    if code == 'p1':
        add_name('p1.png')
        add_name('P1.png')
    if code == 'P0':
        add_name('P0.png')
        add_name('p0.png')

    for folder in _bukkax_chess_asset_dirs_fixed():
        for name in names:
            path = os.path.join(folder, name)
            if os.path.exists(path):
                return path
    return None


def _bukkax_assets_dir_for_dialog_fixed(self):
    for folder in _bukkax_chess_asset_dirs_fixed():
        if os.path.isdir(folder):
            return folder
    # Возвращаем первый ожидаемый путь, даже если папки пока нет.
    dirs = _bukkax_chess_asset_dirs_fixed()
    return dirs[0] if dirs else 'bukkax_chess_assets'


def _bukkax_load_icons_fixed(self):
    """Загружает PNG-фигуры из bukkax_chess_assets для обычной игры и игры с ботом."""
    try:
        self.icons = {}
    except Exception:
        pass

    try:
        symbols = PIECE_SYMBOLS
    except Exception:
        symbols = {
            'K0': '♔', 'Q0': '♕', 'R0': '♖', 'B0': '♗', 'H0': '♘', 'P0': '♙',
            'K1': '♚', 'Q1': '♛', 'R1': '♜', 'B1': '♝', 'H1': '♞', 'p1': '♟',
        }

    for code in symbols:
        try:
            path = _bukkax_piece_png_path_fixed(code)
            if not path:
                continue
            pix = QPixmap(path)
            if not pix.isNull():
                self.icons[code] = QIcon(pix)
        except Exception:
            pass


def _bukkax_redraw_with_asset_icons_fixed(self):
    """Отрисовка доски: сначала PNG-иконки, Unicode только если ассетов реально нет."""
    try:
        self._update_status()
    except Exception:
        pass

    try:
        if not getattr(self, 'icons', None):
            self._load_icons()
    except Exception:
        pass

    for dy in range(8):
        for dx in range(8):
            try:
                bx, by = self._display_to_board(dx, dy)
                piece = self.rules.board[by][bx]
                btn = self.buttons[(dx, dy)]
                light = (bx + by) % 2 == 0
                bg = '#F0D9B5' if light else '#B58863'
                border = '1px solid #262626'
                if getattr(self, 'selected', None) == (bx, by):
                    border = '3px solid #4EA1FF'
                elif (bx, by) in getattr(self, 'legal', []):
                    border = '3px solid #6ee76e'
                    bg = '#9fd58b' if light else '#75a869'

                btn.setStyleSheet(
                    f"background: {bg}; border: {border}; "
                    "font-size: 34px; color: #111111;"
                )

                if piece != '.' and piece in getattr(self, 'icons', {}):
                    btn.setIcon(self.icons[piece])
                    try:
                        size = min(btn.width() or 78, btn.height() or 78) - 14
                        if size < 48:
                            size = 62
                        btn.setIconSize(QSize(size, size))
                    except Exception:
                        btn.setIconSize(QSize(62, 62))
                    btn.setText('')
                elif piece != '.':
                    # Последний fallback, если папка ассетов не лежит рядом с exe/py.
                    btn.setIcon(QIcon())
                    try:
                        btn.setText(PIECE_SYMBOLS.get(piece, piece))
                    except Exception:
                        btn.setText(str(piece))
                else:
                    btn.setIcon(QIcon())
                    btn.setText('')
            except Exception:
                pass


try:
    ChessDialog._assets_dir = _bukkax_assets_dir_for_dialog_fixed
    ChessDialog._load_icons = _bukkax_load_icons_fixed
    ChessDialog._redraw = _bukkax_redraw_with_asset_icons_fixed
except Exception:
    pass

# Важно для локального бота: если у него был свой _redraw с Unicode,
# принудительно ставим ему такую же отрисовку, как у обычной шахматной доски.
try:
    ChessBotDialog._assets_dir = _bukkax_assets_dir_for_dialog_fixed
    ChessBotDialog._load_icons = _bukkax_load_icons_fixed
    ChessBotDialog._redraw = _bukkax_redraw_with_asset_icons_fixed
except Exception:
    pass
# ---------- BUKKAX CHESS ASSET FIGURES FIX END ----------

# ---------- BUKKAX CHESS HISTORY PANEL START ----------
# Правая панель истории ходов + простое определение дебюта/вариации.
# Работает и в игре с другом, и в локальной игре с ботом.
try:
    from PySide6.QtWidgets import QTextBrowser
except Exception:
    QTextBrowser = None


_BUKKAX_FILES = 'abcdefgh'


def _bukkax_sq_name(x, y):
    try:
        return _BUKKAX_FILES[int(x)] + str(8 - int(y))
    except Exception:
        return f'{x},{y}'


def _bukkax_piece_ru(piece):
    p = (piece or '')[:1]
    return {
        'K': 'Король',
        'Q': 'Ферзь',
        'R': 'Ладья',
        'B': 'Слон',
        'H': 'Конь',
        'P': 'Пешка',
        'p': 'Пешка',
    }.get(p, 'Фигура')


def _bukkax_piece_san_letter(piece):
    p = (piece or '')[:1]
    # В твоём коде конь обозначен H, но в шахматной нотации пишется N.
    return {
        'K': 'K',
        'Q': 'Q',
        'R': 'R',
        'B': 'B',
        'H': 'N',
        'P': '',
        'p': '',
    }.get(p, '')


def _bukkax_make_san(piece, x1, y1, x2, y2, captured='.', promotion='', result='', gives_check=False):
    try:
        piece = piece or ''
        # Рокировка.
        if piece in ('K0', 'K1') and abs(int(x2) - int(x1)) == 2:
            text = 'O-O' if int(x2) > int(x1) else 'O-O-O'
        else:
            capture = captured not in (None, '', '.')
            dst = _bukkax_sq_name(x2, y2)
            letter = _bukkax_piece_san_letter(piece)
            if piece[:1] in ('P', 'p'):
                text = (_BUKKAX_FILES[int(x1)] + 'x' if capture else '') + dst
            else:
                text = letter + ('x' if capture else '') + dst
            if promotion:
                text += '=' + str(promotion or 'Q').upper()[:1]
        if result and str(result).startswith('Мат'):
            text += '#'
        elif gives_check:
            text += '+'
        return text
    except Exception:
        return f'{_bukkax_sq_name(x1, y1)}-{_bukkax_sq_name(x2, y2)}'


_BUKKAX_OPENINGS = [
    (['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1b5', 'a7a6'], 'Испанская партия', 'вариант Морфи / 3...a6'),
    (['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1b5'], 'Испанская партия', 'Руй Лопес'),
    (['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1c4', 'f8c5'], 'Итальянская партия', 'Giuoco Piano'),
    (['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1c4'], 'Итальянская партия', 'классическое развитие'),
    (['e2e4', 'e7e5', 'g1f3', 'b8c6', 'd2d4'], 'Шотландская партия', 'главная линия'),
    (['e2e4', 'e7e5', 'g1f3', 'd7d6'], 'Защита Филидора', 'классическая структура'),
    (['e2e4', 'e7e5', 'f2f4'], 'Королевский гамбит', '2.f4'),
    (['e2e4', 'c7c5', 'g1f3', 'd7d6', 'd2d4', 'c5d4', 'f3d4', 'g8f6', 'b1c3', 'a7a6'], 'Сицилианская защита', 'вариант Найдорфа'),
    (['e2e4', 'c7c5', 'g1f3', 'd7d6'], 'Сицилианская защита', 'вариант с 2...d6'),
    (['e2e4', 'c7c5', 'g1f3', 'b8c6'], 'Сицилианская защита', 'вариант с 2...Nc6'),
    (['e2e4', 'c7c5'], 'Сицилианская защита', 'основная идея 1...c5'),
    (['e2e4', 'e7e6'], 'Французская защита', '1...e6'),
    (['e2e4', 'c7c6'], 'Защита Каро-Канн', '1...c6'),
    (['e2e4', 'd7d5'], 'Скандинавская защита', '1...d5'),
    (['e2e4', 'g8f6'], 'Защита Алехина', '1...Nf6'),
    (['d2d4', 'd7d5', 'c2c4', 'd5c4'], 'Ферзевый гамбит', 'принятый'),
    (['d2d4', 'd7d5', 'c2c4', 'e7e6'], 'Ферзевый гамбит', 'отказанный'),
    (['d2d4', 'd7d5', 'c2c4'], 'Ферзевый гамбит', '2.c4'),
    (['d2d4', 'g8f6', 'c2c4', 'g7g6', 'b1c3', 'f8g7', 'e2e4'], 'Староиндийская защита', 'классическая структура'),
    (['d2d4', 'g8f6', 'c2c4', 'g7g6', 'b1c3', 'd7d5'], 'Защита Грюнфельда', 'раннее ...d5'),
    (['d2d4', 'g8f6', 'c2c4', 'e7e6', 'b1c3', 'f8b4'], 'Нимцовичская защита', 'Nimzo-Indian'),
    (['d2d4', 'g8f6', 'c2c4', 'e7e6', 'g1f3', 'b7b6'], 'Новоиндийская защита', 'Queen’s Indian'),
    (['d2d4', 'g8f6', 'c2c4'], 'Индийская защита', 'общая структура'),
    (['c2c4'], 'Английское начало', '1.c4'),
    (['g1f3', 'd7d5', 'c2c4'], 'Дебют Рети', 'переход к структурам Рети'),
    (['g1f3'], 'Дебют Рети', '1.Nf3'),
    (['b2b3'], 'Дебют Ларсена', '1.b3'),
    (['g2g3'], 'Дебют Бенкё / фианкетто', '1.g3'),
]


def _bukkax_detect_opening(uci_moves):
    clean = []
    for m in uci_moves or []:
        if not m:
            continue
        clean.append(str(m)[:4])
    if not clean:
        return 'Партия ещё не началась', 'сделайте первый ход'

    best = None
    for pattern, name, variation in _BUKKAX_OPENINGS:
        if clean[:len(pattern)] == pattern:
            if best is None or len(pattern) > len(best[0]):
                best = (pattern, name, variation)
    if best:
        return best[1], best[2]

    if len(clean) == 1:
        return 'Дебют пока не определён', 'ожидаем ответный ход'
    return 'Дебют пока не определён', 'линия вне простого словаря Букакса'


# Оборачиваем ChessRules.reset/move один раз: так история появится во всех режимах без ручной правки каждого обработчика.
try:
    if not getattr(ChessRules, '_bukkax_history_wrapped', False):
        _bukkax_orig_rules_reset = ChessRules.reset
        _bukkax_orig_rules_move = ChessRules.move

        def _bukkax_rules_reset_with_history(self):
            res = _bukkax_orig_rules_reset(self)
            self._bukkax_move_id = 0
            self._bukkax_last_move = None
            return res

        def _bukkax_rules_move_with_history(self, x1, y1, x2, y2, promotion='Q'):
            try:
                x1i, y1i, x2i, y2i = int(x1), int(y1), int(x2), int(y2)
                piece_before = self.board[y1i][x1i]
                captured_before = self.board[y2i][x2i]
                color_before = int(piece_before[-1]) if piece_before not in ('.', '', None) else int(getattr(self, 'turn', 0))
                uci = _bukkax_sq_name(x1i, y1i) + _bukkax_sq_name(x2i, y2i)
                if promotion:
                    # В UCI превращение пишется маленькой буквой: e7e8q.
                    prom = str(promotion).strip().lower()[:1]
                    if prom and prom != 'q':
                        uci += prom
                    elif prom == 'q':
                        uci += 'q'
            except Exception:
                piece_before = ''
                captured_before = '.'
                color_before = int(getattr(self, 'turn', 0))
                uci = ''

            ok, result = _bukkax_orig_rules_move(self, x1, y1, x2, y2, promotion)
            if ok:
                try:
                    gives_check = False
                    try:
                        gives_check = bool(self.is_check(str(self.turn)))
                    except Exception:
                        gives_check = False
                    move_id = int(getattr(self, '_bukkax_move_id', 0)) + 1
                    self._bukkax_move_id = move_id
                    self._bukkax_last_move = {
                        'id': move_id,
                        'piece': piece_before,
                        'piece_ru': _bukkax_piece_ru(piece_before),
                        'color': color_before,
                        'color_text': 'Белые' if color_before == 0 else 'Чёрные',
                        'src': [int(x1), int(y1)],
                        'dst': [int(x2), int(y2)],
                        'src_name': _bukkax_sq_name(x1, y1),
                        'dst_name': _bukkax_sq_name(x2, y2),
                        'captured': captured_before,
                        'capture': captured_before not in (None, '', '.'),
                        'promotion': str(promotion or '').upper()[:1],
                        'uci': uci,
                        'san': _bukkax_make_san(piece_before, x1, y1, x2, y2, captured_before, promotion, result, gives_check),
                        'result': result or '',
                        'check': gives_check,
                    }
                except Exception:
                    pass
            return ok, result

        ChessRules.reset = _bukkax_rules_reset_with_history
        ChessRules.move = _bukkax_rules_move_with_history
        ChessRules._bukkax_history_wrapped = True
except Exception:
    pass


def _bukkax_history_build_ui(self):
    self.move_history = []
    self._bukkax_seen_move_id = 0
    self._bukkax_history_uci = []

    root = QVBoxLayout(self)
    root.setContentsMargins(14, 12, 14, 12)
    root.setSpacing(8)

    top = QHBoxLayout()
    top.setContentsMargins(0, 0, 0, 0)
    top.setSpacing(8)

    self.title = QLabel()
    self.title.setWordWrap(False)
    self.title.setMinimumWidth(0)
    self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    self.title.setStyleSheet('font-size: 17px; font-weight: bold; color: #ffffff;')
    top.addWidget(self.title, 1)

    self.restart_btn = QPushButton('↻ Новая')
    self.restart_btn.setToolTip('Начать новую партию')
    self.restart_btn.setFixedHeight(30)
    self.restart_btn.setMinimumWidth(86)
    self.restart_btn.clicked.connect(self._restart_clicked)
    top.addWidget(self.restart_btn, 0)

    self.resign_btn = QPushButton('🏳 Сдаться')
    self.resign_btn.setToolTip('Сдаться / закрыть партию')
    self.resign_btn.setFixedHeight(30)
    self.resign_btn.setMinimumWidth(92)
    self.resign_btn.clicked.connect(self._resign_clicked)
    top.addWidget(self.resign_btn, 0)
    root.addLayout(top)

    self.status = QLabel()
    self.status.setWordWrap(True)
    self.status.setStyleSheet('font-size: 13px; color: #ffffff;')
    root.addWidget(self.status)

    content = QHBoxLayout()
    content.setContentsMargins(0, 0, 0, 0)
    content.setSpacing(12)

    self.board_wrap = QWidget()
    self.board_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    self.board_box = QGridLayout(self.board_wrap)
    self.board_box.setContentsMargins(0, 0, 0, 0)
    self.board_box.setSpacing(0)
    for row in range(8):
        for col in range(8):
            btn = QPushButton()
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.setFixedSize(78, 78)
            btn.setIconSize(QSize(62, 62))
            btn.clicked.connect(lambda checked=False, c=col, r=row: self._square_clicked(c, r))
            self.board_box.addWidget(btn, row, col)
            self.buttons[(col, row)] = btn
    content.addWidget(self.board_wrap, 0, Qt.AlignTop | Qt.AlignHCenter)

    self.history_panel = QWidget()
    self.history_panel.setMinimumWidth(230)
    self.history_panel.setMaximumWidth(280)
    side = QVBoxLayout(self.history_panel)
    side.setContentsMargins(10, 10, 10, 10)
    side.setSpacing(8)

    self.opening_title = QLabel('Дебют')
    self.opening_title.setStyleSheet('font-size: 15px; font-weight: bold; color: #ffffff;')
    side.addWidget(self.opening_title)

    self.opening_label = QLabel('Партия ещё не началась')
    self.opening_label.setWordWrap(True)
    self.opening_label.setStyleSheet('font-size: 12px; color: #dfe6ff;')
    side.addWidget(self.opening_label)

    self.move_info_label = QLabel('Последний ход появится здесь')
    self.move_info_label.setWordWrap(True)
    self.move_info_label.setStyleSheet('font-size: 12px; color: #ffffff; background: #1f2638; border-radius: 8px; padding: 8px;')
    side.addWidget(self.move_info_label)

    self.history_title = QLabel('История ходов')
    self.history_title.setStyleSheet('font-size: 15px; font-weight: bold; color: #ffffff;')
    side.addWidget(self.history_title)

    if QTextBrowser is not None:
        self.history_browser = QTextBrowser()
        self.history_browser.setOpenExternalLinks(False)
        self.history_browser.setStyleSheet('font-size: 13px; color: #ffffff; background: #101421; border: 1px solid #2b3656; border-radius: 8px; padding: 6px;')
        side.addWidget(self.history_browser, 1)
    else:
        self.history_browser = QLabel('Ходов пока нет')
        self.history_browser.setWordWrap(True)
        self.history_browser.setStyleSheet('font-size: 13px; color: #ffffff; background: #101421; border: 1px solid #2b3656; border-radius: 8px; padding: 8px;')
        side.addWidget(self.history_browser, 1)

    content.addWidget(self.history_panel, 0, Qt.AlignTop)
    root.addLayout(content, 1)

    hint = QLabel('Белые ходят первыми. Фигуру выбираешь кликом, потом кликаешь клетку хода.')
    hint.setWordWrap(True)
    hint.setStyleSheet('color: #ffffff; font-size: 12px;')
    root.addWidget(hint)

    self.setStyleSheet('''
        QDialog {
            background: #151824;
            color: #ffffff;
        }
        QLabel {
            color: #ffffff;
        }
        QPushButton {
            border-radius: 6px;
            color: #ffffff;
            background: #273047;
            padding: 4px 8px;
        }
        QPushButton:hover {
            background: #33405f;
            color: #ffffff;
        }
        QPushButton:pressed {
            background: #1d2639;
            color: #ffffff;
        }
        QPushButton:disabled {
            color: #99a3c5;
            background: #202638;
        }
        QTextBrowser {
            color: #ffffff;
            background: #101421;
            selection-color: #ffffff;
            selection-background-color: #3f5fa8;
        }
    ''')
    try:
        self.resize(max(self.width(), 920), max(self.height(), 760))
    except Exception:
        pass
    self._resize_board_cells()
    _bukkax_render_history_panel(self)


def _bukkax_render_history_panel(self):
    try:
        hist = list(getattr(self, 'move_history', []) or [])
        uci = [m.get('uci', '') for m in hist if m.get('uci')]
        name, variation = _bukkax_detect_opening(uci)

        if hasattr(self, 'opening_label'):
            self.opening_label.setText(f'<b>{name}</b><br><span style="color:#cfd7ff;">{variation}</span>')

        if hist:
            last = hist[-1]
            capture_text = ''
            if last.get('capture'):
                capture_text = f'<br>Взятие: {_bukkax_piece_ru(last.get("captured", ""))}'
            check_text = '<br>Шах сопернику' if last.get('check') and not str(last.get('result', '')).startswith('Мат') else ''
            result_text = f'<br>{last.get("result")}' if last.get('result') else ''
            if hasattr(self, 'move_info_label'):
                self.move_info_label.setText(
                    f'<b>{last.get("color_text", "")}: {last.get("san", "")}</b><br>'
                    f'{last.get("piece_ru", "Фигура")}: {last.get("src_name", "")} → {last.get("dst_name", "")}'
                    f'{capture_text}{check_text}{result_text}'
                )
        else:
            if hasattr(self, 'move_info_label'):
                self.move_info_label.setText('Последний ход появится здесь')

        rows = []
        for i in range(0, len(hist), 2):
            no = i // 2 + 1
            white = hist[i].get('san', '') if i < len(hist) else ''
            black = hist[i + 1].get('san', '') if i + 1 < len(hist) else ''
            rows.append(
                '<tr>'
                f'<td style="color:#9aa4c7; padding:3px 8px 3px 0;">{no}.</td>'
                f'<td style="color:#ffffff; padding:3px 12px 3px 0; font-weight:600;">{white}</td>'
                f'<td style="color:#ffffff; padding:3px 0; font-weight:600;">{black}</td>'
                '</tr>'
            )
        if rows:
            html = '<table cellspacing="0" cellpadding="0" width="100%">' + ''.join(rows) + '</table>'
        else:
            html = '<span style="color:#ffffff;">Ходов пока нет</span>'

        browser = getattr(self, 'history_browser', None)
        if browser is not None:
            if hasattr(browser, 'setHtml'):
                browser.setHtml(html)
                try:
                    browser.verticalScrollBar().setValue(browser.verticalScrollBar().maximum())
                except Exception:
                    pass
            else:
                browser.setText('Ходов пока нет' if not rows else '\n'.join([m.get('san', '') for m in hist]))
    except Exception:
        pass


def _bukkax_sync_history_from_rules(self):
    try:
        move_id = int(getattr(self.rules, '_bukkax_move_id', 0))
        seen = int(getattr(self, '_bukkax_seen_move_id', 0))
        if move_id == 0 and seen != 0:
            self.move_history = []
            self._bukkax_history_uci = []
            self._bukkax_seen_move_id = 0
            _bukkax_render_history_panel(self)
            return
        if move_id > seen:
            last = getattr(self.rules, '_bukkax_last_move', None)
            if last:
                if not hasattr(self, 'move_history'):
                    self.move_history = []
                self.move_history.append(dict(last))
                self._bukkax_seen_move_id = move_id
                _bukkax_render_history_panel(self)
            return
        _bukkax_render_history_panel(self)
    except Exception:
        pass


try:
    ChessDialog._build_ui = _bukkax_history_build_ui
    ChessBotDialog._build_ui = _bukkax_history_build_ui
except Exception:
    pass

try:
    if not getattr(ChessDialog, '_bukkax_history_redraw_wrapped', False):
        _bukkax_prev_chess_redraw = ChessDialog._redraw

        def _bukkax_chess_redraw_with_history(self):
            res = _bukkax_prev_chess_redraw(self)
            _bukkax_sync_history_from_rules(self)
            return res

        ChessDialog._redraw = _bukkax_chess_redraw_with_history
        ChessDialog._bukkax_history_redraw_wrapped = True
except Exception:
    pass

try:
    if not getattr(ChessBotDialog, '_bukkax_history_redraw_wrapped', False):
        _bukkax_prev_bot_redraw = ChessBotDialog._redraw

        def _bukkax_bot_redraw_with_history(self):
            res = _bukkax_prev_bot_redraw(self)
            _bukkax_sync_history_from_rules(self)
            return res

        ChessBotDialog._redraw = _bukkax_bot_redraw_with_history
        ChessBotDialog._bukkax_history_redraw_wrapped = True
except Exception:
    pass
# ---------- BUKKAX CHESS HISTORY PANEL END ----------

# ---------- BUKKAX CHESS HISTORY PANEL V2 START ----------
# История ходов справа + простое определение дебюта.
# Патч сделан как monkey-patch, чтобы не ломать основной код шахмат.
try:
    from PySide6.QtWidgets import QTextBrowser
except Exception:
    QTextBrowser = None

_BUKKAX_FILES = 'abcdefgh'
_BUKKAX_RANKS = '87654321'


def _bukkax_coord(x, y):
    try:
        return _BUKKAX_FILES[int(x)] + _BUKKAX_RANKS[int(y)]
    except Exception:
        return f'{x},{y}'


def _bukkax_piece_letter(piece):
    try:
        k = str(piece)[0]
        if k == 'p':
            k = 'P'
        return {'K': 'K', 'Q': 'Q', 'R': 'R', 'B': 'B', 'H': 'N', 'P': ''}.get(k, '')
    except Exception:
        return ''


def _bukkax_clean_notation(n):
    n = str(n or '')
    for ch in ['+', '#', '!', '?']:
        n = n.replace(ch, '')
    return n.strip()


def _bukkax_history_ensure(self):
    if not hasattr(self, 'move_history') or self.move_history is None:
        self.move_history = []
    if not hasattr(self, 'move_san_history') or self.move_san_history is None:
        self.move_san_history = []


def _bukkax_make_notation(self, piece, target, x1, y1, x2, y2, promotion=''):
    """Очень простая SAN-похожая нотация: e4, Nf3, Bxe6, O-O, O-O-O."""
    try:
        piece = str(piece or '')
        target = str(target or '.')
        promotion = (promotion or '').upper()
        capture = target != '.'
        piece_kind = piece[0] if piece else ''
        if piece_kind == 'p':
            piece_kind = 'P'

        # Рокировка
        if piece_kind == 'K' and abs(int(x2) - int(x1)) == 2:
            text = 'O-O' if int(x2) == 6 else 'O-O-O'
        else:
            to_sq = _bukkax_coord(x2, y2)
            letter = _bukkax_piece_letter(piece)
            if piece_kind == 'P':
                text = (_BUKKAX_FILES[int(x1)] + 'x' + to_sq) if capture else to_sq
            else:
                text = letter + ('x' if capture else '') + to_sq
            if promotion:
                text += '=' + promotion

        # После rules.move() очередь уже переключена. Если новый игрок под шахом — ставим +/#.
        try:
            if getattr(self.rules, 'result', None) and str(self.rules.result).startswith('Мат'):
                text += '#'
            elif self.rules.is_check(str(self.rules.turn)):
                text += '+'
        except Exception:
            pass
        return text
    except Exception:
        return f'{_bukkax_coord(x1, y1)}-{_bukkax_coord(x2, y2)}'


def _bukkax_detect_opening(self):
    """Небольшой словарь дебютов по первым ходам. Это не полноценная база chess.com."""
    try:
        seq = [_bukkax_clean_notation(x) for x in getattr(self, 'move_san_history', [])]
        seq = [x for x in seq if x]
    except Exception:
        seq = []

    # Сначала самые длинные/точные варианты.
    openings = [
        (['e4', 'e5', 'Nf3', 'Nc6', 'Bb5'], 'Испанская партия', 'Защита Морфи / Ruy Lopez'),
        (['e4', 'e5', 'Nf3', 'Nc6', 'Bc4'], 'Итальянская партия', 'Giuoco Piano'),
        (['e4', 'e5', 'Nf3', 'Nc6'], 'Открытая игра', 'Развитие коней'),
        (['e4', 'e5', 'Nf3'], 'Открытая игра', 'Ход конём королевского фланга'),
        (['e4', 'c5', 'Nf3', 'd6'], 'Сицилианская защита', 'Вариант Найдорфа / классические схемы'),
        (['e4', 'c5', 'Nf3', 'Nc6'], 'Сицилианская защита', 'Открытая сицилианская'),
        (['e4', 'c5'], 'Сицилианская защита', 'Чёрные отвечают c5'),
        (['e4', 'e6'], 'Французская защита', 'Чёрные готовят d5'),
        (['e4', 'c6'], 'Защита Каро-Канн', 'Надёжная структура c6-d5'),
        (['e4', 'd6'], 'Защита Пирца', 'Гибкая защита короля'),
        (['e4', 'd5'], 'Скандинавская защита', 'Ранний удар по центру'),
        (['d4', 'd5', 'c4'], 'Ферзевый гамбит', 'Белые давят на центр'),
        (['d4', 'Nf6', 'c4', 'g6'], 'Староиндийское / Грюнфельд', 'Индийская структура'),
        (['d4', 'Nf6', 'c4', 'e6'], 'Индийские защиты', 'Гибкое развитие чёрных'),
        (['d4', 'd5'], 'Закрытая игра', 'Пешечный центр d4-d5'),
        (['d4'], 'Дебют ферзевой пешки', 'Белые начинают с d4'),
        (['c4'], 'Английское начало', 'Фланговое давление на центр'),
        (['Nf3'], 'Дебют Рети', 'Гибкое развитие коня'),
        (['e4', 'e5'], 'Открытая игра', 'Классический ответ e5'),
        (['e4'], 'Дебют королевской пешки', 'Белые начинают с e4'),
    ]
    for prefix, name, variation in openings:
        if len(seq) >= len(prefix) and seq[:len(prefix)] == prefix:
            return name, variation

    if not seq:
        return 'Пока нет ходов', 'Сделай первый ход'
    if len(seq) < 4:
        return 'Пока не определён', 'Нужно ещё 1–2 хода'
    return 'Редкая / своя линия', 'В базе простых дебютов не найдено'


def _bukkax_record_move(self, x1, y1, x2, y2, promotion='', piece_before=None, target_before=None):
    try:
        _bukkax_history_ensure(self)
        piece = piece_before if piece_before is not None else self.rules.board[y2][x2]
        target = target_before if target_before is not None else '.'
        color = int(str(piece)[-1]) if piece and piece != '.' and str(piece)[-1].isdigit() else 0
        san = _bukkax_make_notation(self, piece, target, x1, y1, x2, y2, promotion)
        color_name = 'Белые' if color == 0 else 'Чёрные'
        long_text = f'{color_name}: {_bukkax_coord(x1, y1)} → {_bukkax_coord(x2, y2)}'
        item = {
            'color': color,
            'piece': piece,
            'from': [int(x1), int(y1)],
            'to': [int(x2), int(y2)],
            'promotion': promotion or '',
            'notation': san,
            'long': long_text,
        }
        self.move_history.append(item)
        self.move_san_history.append(san)
    except Exception:
        pass
    try:
        _bukkax_update_history_panel(self)
    except Exception:
        pass


def _bukkax_moves_html(self):
    try:
        hist = list(getattr(self, 'move_history', []) or [])
    except Exception:
        hist = []
    if not hist:
        return '<div style="color:#9aa4c7;">Ходов пока нет.</div>'

    rows = []
    i = 0
    move_no = 1
    while i < len(hist):
        white = ''
        black = ''
        # Обычно ход белых стоит первым. Но при ошибке/нестандартном порядке не падаем.
        if i < len(hist) and hist[i].get('color') == 0:
            white = hist[i].get('notation', '')
            i += 1
        if i < len(hist) and hist[i].get('color') == 1:
            black = hist[i].get('notation', '')
            i += 1
        # Если история началась с чёрных, покажем его ход в колонке чёрных.
        if not white and not black and i < len(hist):
            if hist[i].get('color') == 0:
                white = hist[i].get('notation', '')
            else:
                black = hist[i].get('notation', '')
            i += 1
        rows.append(
            f'<tr>'
            f'<td style="color:#7f8aa8; padding:2px 6px 2px 0;">{move_no}.</td>'
            f'<td style="color:#ffffff; padding:2px 10px 2px 0; min-width:52px;">{white}</td>'
            f'<td style="color:#ffffff; padding:2px 0; min-width:52px;">{black}</td>'
            f'</tr>'
        )
        move_no += 1
    return '<table cellspacing="0" cellpadding="0">' + ''.join(rows) + '</table>'


def _bukkax_update_history_panel(self):
    try:
        _bukkax_history_ensure(self)
    except Exception:
        pass
    try:
        opening, variation = _bukkax_detect_opening(self)
        if hasattr(self, 'opening_label'):
            self.opening_label.setText(f'Дебют: {opening}')
        if hasattr(self, 'variation_label'):
            self.variation_label.setText(f'Вариация: {variation}')
    except Exception:
        pass
    try:
        hist = getattr(self, 'move_history', []) or []
        if hasattr(self, 'last_move_label'):
            if hist:
                last = hist[-1]
                self.last_move_label.setText(f"Последний ход: {last.get('long', '')} ({last.get('notation', '')})")
            else:
                self.last_move_label.setText('Последний ход: —')
    except Exception:
        pass
    try:
        if hasattr(self, 'moves_browser') and self.moves_browser is not None:
            self.moves_browser.setHtml(_bukkax_moves_html(self))
    except Exception:
        pass


def _bukkax_history_build_ui(self):
    _bukkax_history_ensure(self)
    try:
        self.resize(max(self.width(), 930), max(self.height(), 760))
    except Exception:
        pass

    root = QVBoxLayout(self)
    root.setContentsMargins(14, 12, 14, 12)
    root.setSpacing(8)

    top = QHBoxLayout()
    top.setContentsMargins(0, 0, 0, 0)
    top.setSpacing(8)

    self.title = QLabel()
    self.title.setWordWrap(False)
    self.title.setMinimumWidth(0)
    self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    self.title.setStyleSheet('font-size: 17px; font-weight: bold; color: #ffffff;')
    top.addWidget(self.title, 1)

    self.restart_btn = QPushButton('↻ Новая')
    self.restart_btn.setToolTip('Начать новую партию')
    self.restart_btn.setFixedHeight(30)
    self.restart_btn.setMinimumWidth(86)
    self.restart_btn.clicked.connect(self._restart_clicked)
    top.addWidget(self.restart_btn, 0)

    self.resign_btn = QPushButton('🏳 Сдаться')
    self.resign_btn.setToolTip('Сдаться / закрыть партию')
    self.resign_btn.setFixedHeight(30)
    self.resign_btn.setMinimumWidth(92)
    self.resign_btn.clicked.connect(self._resign_clicked)
    top.addWidget(self.resign_btn, 0)
    root.addLayout(top)

    self.status = QLabel()
    self.status.setWordWrap(True)
    self.status.setStyleSheet('font-size: 13px; color: #ffffff;')
    root.addWidget(self.status)

    body = QHBoxLayout()
    body.setContentsMargins(0, 0, 0, 0)
    body.setSpacing(12)

    left = QVBoxLayout()
    left.setContentsMargins(0, 0, 0, 0)
    left.setSpacing(8)

    self.board_wrap = QWidget()
    self.board_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    self.board_box = QGridLayout(self.board_wrap)
    self.board_box.setContentsMargins(0, 0, 0, 0)
    self.board_box.setSpacing(0)
    for row in range(8):
        for col in range(8):
            btn = QPushButton()
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.setFixedSize(72, 72)
            btn.setIconSize(QSize(56, 56))
            btn.clicked.connect(lambda checked=False, c=col, r=row: self._square_clicked(c, r))
            self.board_box.addWidget(btn, row, col)
            self.buttons[(col, row)] = btn
    left.addWidget(self.board_wrap, 0, Qt.AlignHCenter)

    hint = QLabel('Белые ходят первыми. Фигуру выбираешь кликом, потом кликаешь клетку хода.')
    hint.setWordWrap(True)
    hint.setStyleSheet('color: #ffffff; font-size: 12px;')
    left.addWidget(hint)
    body.addLayout(left, 1)

    self.history_panel = QWidget()
    self.history_panel.setObjectName('chessHistoryPanel')
    self.history_panel.setFixedWidth(250)
    side = QVBoxLayout(self.history_panel)
    side.setContentsMargins(12, 12, 12, 12)
    side.setSpacing(8)

    panel_title = QLabel('История ходов')
    panel_title.setStyleSheet('color:#ffffff; font-size:16px; font-weight:700;')
    side.addWidget(panel_title)

    self.opening_label = QLabel('Дебют: Пока нет ходов')
    self.opening_label.setWordWrap(True)
    self.opening_label.setStyleSheet('color:#ffffff; font-size:12px; font-weight:600;')
    side.addWidget(self.opening_label)

    self.variation_label = QLabel('Вариация: Сделай первый ход')
    self.variation_label.setWordWrap(True)
    self.variation_label.setStyleSheet('color:#cfd7ff; font-size:12px;')
    side.addWidget(self.variation_label)

    self.last_move_label = QLabel('Последний ход: —')
    self.last_move_label.setWordWrap(True)
    self.last_move_label.setStyleSheet('color:#ffffff; font-size:12px;')
    side.addWidget(self.last_move_label)

    if QTextBrowser is not None:
        self.moves_browser = QTextBrowser()
        self.moves_browser.setReadOnly(True)
        self.moves_browser.setMinimumHeight(360)
        self.moves_browser.setStyleSheet("QTextBrowser { background: #111522; color: #ffffff; border: 1px solid #2c344d; border-radius: 8px; padding: 8px; font-size: 14px; }")
        side.addWidget(self.moves_browser, 1)
    else:
        self.moves_browser = QLabel('История ходов недоступна')
        self.moves_browser.setWordWrap(True)
        self.moves_browser.setStyleSheet('color:#ffffff;')
        side.addWidget(self.moves_browser, 1)

    body.addWidget(self.history_panel, 0, Qt.AlignTop)
    root.addLayout(body, 1)

    self.setStyleSheet("QDialog { background: #151824; color: #ffffff; } QLabel { color: #ffffff; } QPushButton { border-radius: 6px; color: #ffffff; background: #273047; padding: 4px 8px; font-weight: 600; } QPushButton:hover { background: #33405f; } QPushButton:disabled { color: #8d96b5; background: #202638; } QWidget#chessHistoryPanel { background: #1b2030; border: 1px solid #2c344d; border-radius: 12px; } QMessageBox QLabel { color: #ffffff; } QInputDialog QLabel { color: #ffffff; }")
    try:
        self._resize_board_cells()
    except Exception:
        pass
    try:
        _bukkax_update_history_panel(self)
    except Exception:
        pass


def _bukkax_history_resize_board_cells(self):
    try:
        right = 290 if hasattr(self, 'history_panel') else 0
        available_w = max(360, self.width() - right - 46)
        available_h = max(360, self.height() - 130)
        cell = min(82, max(48, min(available_w // 8, available_h // 8)))
        icon = max(34, cell - 16)
        if hasattr(self, 'board_wrap'):
            self.board_wrap.setFixedSize(cell * 8, cell * 8)
        for btn in getattr(self, 'buttons', {}).values():
            btn.setFixedSize(cell, cell)
            btn.setIconSize(QSize(icon, icon))
    except Exception:
        pass


def _bukkax_history_resize_event(self, event):
    try:
        QDialog.resizeEvent(self, event)
    except Exception:
        pass
    try:
        self._resize_board_cells()
    except Exception:
        pass


def _bukkax_history_redraw(self):
    try:
        _BUKKAX_HISTORY_ORIGINAL_REDRAW(self)
    except Exception:
        # fallback: если старый _redraw по какой-то причине недоступен
        try:
            self._update_status()
        except Exception:
            pass
    try:
        _bukkax_update_history_panel(self)
    except Exception:
        pass


def _bukkax_history_square_clicked(self, dx, dy):
    if self.game_over or self.rules.result:
        return
    bx, by = self._display_to_board(dx, dy)
    if self.rules.turn != self.my_color:
        QMessageBox.information(self, 'Шахматы', 'Сейчас ход соперника.')
        return

    if self.selected and (bx, by) in self.legal:
        x1, y1 = self.selected
        piece_before = self.rules.board[y1][x1]
        target_before = self.rules.board[by][bx]
        promotion = self._promotion_if_needed(x1, y1, bx, by)
        ok, result = self.rules.move(x1, y1, bx, by, promotion)
        if not ok:
            QMessageBox.warning(self, 'Шахматы', result)
            return
        _bukkax_record_move(self, x1, y1, bx, by, promotion, piece_before, target_before)
        self.selected = None
        self.legal = []
        self._redraw()
        if self.send_move_cb:
            self.send_move_cb(self.game_id, self.opponent, [x1, y1], [bx, by], promotion or '')
        if result:
            self.game_over = True
            QMessageBox.information(self, 'Шахматы', result)
        return

    piece = self.rules.board[by][bx]
    if piece != '.' and int(piece[1]) == self.my_color:
        moves = self.rules.legal_moves(bx, by)
        if not moves:
            QMessageBox.information(self, 'Шахматы', 'У этой фигуры нет доступных ходов.')
            return
        self.selected = (bx, by)
        self.legal = moves
    else:
        self.selected = None
        self.legal = []
    self._redraw()


def _bukkax_history_apply_remote_move(self, src, dst, promotion=''):
    try:
        x1, y1 = int(src[0]), int(src[1])
        x2, y2 = int(dst[0]), int(dst[1])
    except Exception:
        QMessageBox.warning(self, 'Шахматы', 'Пришёл неправильный ход от соперника.')
        return
    try:
        piece_before = self.rules.board[y1][x1]
        target_before = self.rules.board[y2][x2]
    except Exception:
        piece_before, target_before = None, None
    ok, result = self.rules.move(x1, y1, x2, y2, promotion)
    if not ok:
        QMessageBox.warning(self, 'Шахматы', f'Не удалось применить ход соперника: {result}')
        return
    _bukkax_record_move(self, x1, y1, x2, y2, promotion, piece_before, target_before)
    self.selected = None
    self.legal = []
    self._redraw()
    if result:
        self.game_over = True
        QMessageBox.information(self, 'Шахматы', result)


def _bukkax_history_reset_game(self):
    try:
        self.rules.reset()
    except Exception:
        pass
    self.game_over = False
    self.selected = None
    self.legal = []
    self.move_history = []
    self.move_san_history = []
    try:
        self._redraw()
    except Exception:
        pass
    try:
        _bukkax_update_history_panel(self)
    except Exception:
        pass


def _bukkax_history_remote_restart(self):
    self.reset_game()
    QMessageBox.information(self, 'Шахматы', f'{self.opponent} начал новую партию.')


def _bukkax_history_remote_resign(self):
    self.game_over = True
    self.rules.result = f'{self.opponent} сдался. Вы победили.'
    self._redraw()
    QMessageBox.information(self, 'Шахматы', self.rules.result)


def _bukkax_bot_square_clicked_with_history(self, dx, dy):
    if self.game_over or self.rules.result:
        return
    if getattr(self, 'bot_thinking', False):
        QMessageBox.information(self, 'Шахматы', f'Подожди, {self.bot_name} делает ход.')
        return
    if self.rules.turn != self.my_color:
        QMessageBox.information(self, 'Шахматы', f'Сейчас ходит {self.bot_name}.')
        return

    bx, by = self._display_to_board(dx, dy)

    if self.selected and (bx, by) in self.legal:
        x1, y1 = self.selected
        piece_before = self.rules.board[y1][x1]
        target_before = self.rules.board[by][bx]
        promotion = self._promotion_if_needed(x1, y1, bx, by)
        ok, result = self.rules.move(x1, y1, bx, by, promotion)
        if not ok:
            QMessageBox.warning(self, 'Шахматы', result)
            return
        _bukkax_record_move(self, x1, y1, bx, by, promotion, piece_before, target_before)
        self.selected = None
        self.legal = []
        self._redraw()
        if result:
            self.game_over = True
            QMessageBox.information(self, 'Шахматы', result)
            return
        self._schedule_bot_move()
        return

    piece = self.rules.board[by][bx]
    if piece != '.' and int(piece[1]) == self.my_color:
        moves = self.rules.legal_moves(bx, by)
        if not moves:
            QMessageBox.information(self, 'Шахматы', 'У этой фигуры нет доступных ходов.')
            return
        self.selected = (bx, by)
        self.legal = moves
    else:
        self.selected = None
        self.legal = []
    self._redraw()


def _bukkax_bot_move_with_history(self):
    if self.game_over or self.rules.result:
        self.bot_thinking = False
        self._redraw()
        return
    if self.rules.turn != getattr(self, 'bot_color', 1):
        self.bot_thinking = False
        self._redraw()
        return

    move = _bot_choose_move(self.rules, getattr(self, 'bot_color', 1))
    if not move:
        self.bot_thinking = False
        status = self.rules.checkmate_status(str(getattr(self, 'bot_color', 1)))
        if status == 1:
            winner = 'Чёрные' if getattr(self, 'bot_color', 1) == 0 else 'Белые'
            self.rules.result = f'Мат. {winner} победили'
        else:
            self.rules.result = 'Пат. Ничья'
        self.game_over = True
        self._redraw()
        QMessageBox.information(self, 'Шахматы', self.rules.result)
        return

    x1, y1, x2, y2, _score = move
    piece_before = self.rules.board[y1][x1]
    target_before = self.rules.board[y2][x2]
    promotion = 'Q' if ((piece_before == 'p1' and y2 == 7) or (piece_before == 'P0' and y2 == 0)) else ''
    ok, result = self.rules.move(x1, y1, x2, y2, promotion)

    if not ok:
        fallback = _bot_all_legal_moves(self.rules, getattr(self, 'bot_color', 1))
        if fallback:
            x1, y1, x2, y2, _score = random.choice(fallback)
            piece_before = self.rules.board[y1][x1]
            target_before = self.rules.board[y2][x2]
            promotion = 'Q' if ((piece_before == 'p1' and y2 == 7) or (piece_before == 'P0' and y2 == 0)) else ''
            ok, result = self.rules.move(x1, y1, x2, y2, promotion)

    self.bot_thinking = False
    if ok:
        _bukkax_record_move(self, x1, y1, x2, y2, promotion, piece_before, target_before)
    self.selected = None
    self.legal = []
    self._redraw()
    if result:
        self.game_over = True
        QMessageBox.information(self, 'Шахматы', result)


# Сохраняем текущую отрисовку. На этом этапе уже могли быть применены патчи ассетов,
# поэтому история не ломает PNG-фигуры.
try:
    _BUKKAX_HISTORY_ORIGINAL_REDRAW = ChessDialog._redraw
except Exception:
    _BUKKAX_HISTORY_ORIGINAL_REDRAW = None

try:
    ChessDialog._build_ui = _bukkax_history_build_ui
    ChessDialog._resize_board_cells = _bukkax_history_resize_board_cells
    ChessDialog.resizeEvent = _bukkax_history_resize_event
    ChessDialog._redraw = _bukkax_history_redraw
    ChessDialog._square_clicked = _bukkax_history_square_clicked
    ChessDialog.apply_remote_move = _bukkax_history_apply_remote_move
    ChessDialog.reset_game = _bukkax_history_reset_game
    ChessDialog.remote_restart = _bukkax_history_remote_restart
    ChessDialog.remote_resign = _bukkax_history_remote_resign
except Exception:
    pass

try:
    ChessBotDialog._build_ui = _bukkax_history_build_ui
    ChessBotDialog._resize_board_cells = _bukkax_history_resize_board_cells
    ChessBotDialog.resizeEvent = _bukkax_history_resize_event
    ChessBotDialog._redraw = _bukkax_history_redraw
    ChessBotDialog._square_clicked = _bukkax_bot_square_clicked_with_history
    ChessBotDialog.apply_remote_move = _bukkax_history_apply_remote_move
    ChessBotDialog.reset_game = _bukkax_history_reset_game
    ChessBotDialog.remote_restart = _bukkax_history_remote_restart
    ChessBotDialog.remote_resign = _bukkax_history_remote_resign
    ChessBotDialog._bot_move = _bukkax_bot_move_with_history
except Exception:
    pass
# ---------- BUKKAX CHESS HISTORY PANEL V2 END ----------

# ---------- BUKKAX CHESS SOUNDS + CHECK + SYNC CLOSE PATCH START ----------
# Добавляет:
# - звук каждого успешного хода;
# - отдельный звук шаха;
# - красную подсветку короля под шахом;
# - уведомление родительского клиента при закрытии сетевой шахматной доски.

try:
    from PySide6.QtCore import QUrl as _BukkaxChessQUrl
    from PySide6.QtMultimedia import (
        QMediaPlayer as _BukkaxChessMediaPlayer,
        QAudioOutput as _BukkaxChessAudioOutput,
    )
except Exception:
    _BukkaxChessQUrl = None
    _BukkaxChessMediaPlayer = None
    _BukkaxChessAudioOutput = None


def _bukkax_chess_sound_dirs():
    dirs = []

    def add(path):
        if path and path not in dirs:
            dirs.append(path)

    try:
        add(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'bukkax_chess_sounds'
        ))
    except Exception:
        pass

    try:
        add(os.path.join(
            os.getcwd(),
            'bukkax_chess_sounds'
        ))
    except Exception:
        pass

    try:
        add(os.path.join(
            os.path.dirname(sys.executable),
            'bukkax_chess_sounds'
        ))
    except Exception:
        pass

    try:
        meipass = getattr(sys, '_MEIPASS', '')
        if meipass:
            add(os.path.join(
                meipass,
                'bukkax_chess_sounds'
            ))
    except Exception:
        pass

    return dirs


def _bukkax_chess_sound_path(filename):
    for folder in _bukkax_chess_sound_dirs():
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            return path
    return None


def _bukkax_chess_ensure_sound_players(self):
    if _BukkaxChessMediaPlayer is None:
        return False

    try:
        if getattr(self, '_bukkax_move_player', None) is None:
            self._bukkax_move_player = _BukkaxChessMediaPlayer(self)
            self._bukkax_move_audio = _BukkaxChessAudioOutput(self)
            self._bukkax_move_audio.setVolume(0.80)
            self._bukkax_move_player.setAudioOutput(
                self._bukkax_move_audio
            )

        if getattr(self, '_bukkax_check_player', None) is None:
            self._bukkax_check_player = _BukkaxChessMediaPlayer(self)
            self._bukkax_check_audio = _BukkaxChessAudioOutput(self)
            self._bukkax_check_audio.setVolume(0.88)
            self._bukkax_check_player.setAudioOutput(
                self._bukkax_check_audio
            )

        return True
    except Exception:
        return False


def _bukkax_chess_play_move_sound(self):
    try:
        if not _bukkax_chess_ensure_sound_players(self):
            return

        path = _bukkax_chess_sound_path('move.mp3')
        if not path:
            return

        self._bukkax_move_player.stop()
        self._bukkax_move_player.setSource(
            _BukkaxChessQUrl.fromLocalFile(path)
        )
        self._bukkax_move_player.setPosition(0)
        self._bukkax_move_player.play()
    except Exception:
        pass


def _bukkax_chess_play_check_sound(self):
    try:
        if not _bukkax_chess_ensure_sound_players(self):
            return

        path = _bukkax_chess_sound_path('check.wav')
        if not path:
            return

        self._bukkax_check_player.stop()
        self._bukkax_check_player.setSource(
            _BukkaxChessQUrl.fromLocalFile(path)
        )
        self._bukkax_check_player.setPosition(0)
        self._bukkax_check_player.play()
    except Exception:
        pass


def _bukkax_chess_is_side_to_move_in_check(self):
    try:
        return bool(
            self.rules.is_check(
                str(self.rules.turn)
            )
        )
    except Exception:
        return False


def _bukkax_chess_after_successful_move(self):
    # Звук хода есть всегда — и на своём ходе, и на ходе соперника/бота.
    _bukkax_chess_play_move_sound(self)

    # После move() rules.turn уже переключён на того,
    # кто теперь должен ходить. Если его король атакован — это шах.
    if _bukkax_chess_is_side_to_move_in_check(self):
        try:
            QTimer.singleShot(
                180,
                lambda obj=self: _bukkax_chess_play_check_sound(obj)
            )
        except Exception:
            _bukkax_chess_play_check_sound(self)


def _bukkax_chess_highlight_checked_kings(self):
    try:
        for color in (0, 1):
            if not self.rules.is_check(str(color)):
                continue

            king = 'K' + str(color)

            for by in range(8):
                for bx in range(8):
                    if self.rules.board[by][bx] != king:
                        continue

                    dx, dy = self._board_to_display(bx, by)
                    btn = self.buttons.get((dx, dy))

                    if btn is not None:
                        current = btn.styleSheet() or ''
                        btn.setStyleSheet(
                            current
                            + '; background:#d9534f;'
                            + ' border:4px solid #ff2020;'
                        )
                    break
    except Exception:
        pass


def _bukkax_chess_wrap_move_method(cls, method_name):
    try:
        previous = getattr(cls, method_name)
    except Exception:
        return

    marker = '_bukkax_sound_wrapped_' + method_name
    if getattr(cls, marker, False):
        return

    def wrapped(self, *args, **kwargs):
        try:
            before_turn = int(self.rules.turn)
        except Exception:
            before_turn = None

        result = previous(self, *args, **kwargs)

        try:
            after_turn = int(self.rules.turn)
        except Exception:
            after_turn = None

        # Успешный шахматный ход всегда переключает turn.
        if (
            before_turn is not None
            and after_turn is not None
            and before_turn != after_turn
        ):
            _bukkax_chess_after_successful_move(self)

        return result

    setattr(cls, method_name, wrapped)
    setattr(cls, marker, True)


# Оборачиваем ФИНАЛЬНЫЙ redraw после всех старых history/asset monkey-patch.
try:
    if not getattr(
        ChessDialog,
        '_bukkax_check_highlight_redraw_wrapped',
        False
    ):
        _bukkax_prev_redraw_check = ChessDialog._redraw

        def _bukkax_redraw_with_check(self):
            result = _bukkax_prev_redraw_check(self)
            _bukkax_chess_highlight_checked_kings(self)
            return result

        ChessDialog._redraw = _bukkax_redraw_with_check
        ChessDialog._bukkax_check_highlight_redraw_wrapped = True
except Exception:
    pass


try:
    if not getattr(
        ChessBotDialog,
        '_bukkax_check_highlight_redraw_wrapped',
        False
    ):
        _bukkax_prev_bot_redraw_check = ChessBotDialog._redraw

        def _bukkax_bot_redraw_with_check(self):
            result = _bukkax_prev_bot_redraw_check(self)
            _bukkax_chess_highlight_checked_kings(self)
            return result

        ChessBotDialog._redraw = _bukkax_bot_redraw_with_check
        ChessBotDialog._bukkax_check_highlight_redraw_wrapped = True
except Exception:
    pass


# Звук на каждый успешный ход.
_bukkax_chess_wrap_move_method(
    ChessDialog,
    '_square_clicked'
)
_bukkax_chess_wrap_move_method(
    ChessDialog,
    'apply_remote_move'
)
_bukkax_chess_wrap_move_method(
    ChessBotDialog,
    '_square_clicked'
)
_bukkax_chess_wrap_move_method(
    ChessBotDialog,
    '_bot_move'
)


# Синхронное закрытие сетевой доски.
try:
    if not getattr(
        ChessDialog,
        '_bukkax_sync_close_wrapped',
        False
    ):
        def _bukkax_chess_close_event(self, event):
            remote = bool(
                getattr(
                    self,
                    '_bukkax_remote_closing',
                    False
                )
            )

            notified = bool(
                getattr(
                    self,
                    '_bukkax_close_notified',
                    False
                )
            )

            callback = getattr(
                self,
                'send_close_cb',
                None
            )

            # У ChessBotDialog callback отсутствует,
            # поэтому локальная игра с ботом никуда ничего не отправляет.
            if (
                not remote
                and not notified
                and callable(callback)
            ):
                self._bukkax_close_notified = True

                try:
                    callback(
                        self.game_id,
                        self.opponent
                    )
                except Exception:
                    pass

            try:
                QDialog.closeEvent(
                    self,
                    event
                )
            except Exception:
                try:
                    event.accept()
                except Exception:
                    pass

            # Чтобы destroyed-сигнал клиента очистил chess_dialogs.
            try:
                QTimer.singleShot(
                    0,
                    self.deleteLater
                )
            except Exception:
                pass

        def _bukkax_chess_remote_close(self):
            self._bukkax_remote_closing = True
            self._bukkax_close_notified = True

            try:
                self.close()
            except Exception:
                pass

        ChessDialog.closeEvent = _bukkax_chess_close_event
        ChessDialog.remote_close = _bukkax_chess_remote_close
        ChessDialog._bukkax_sync_close_wrapped = True

        # Наследник тоже должен использовать тот же closeEvent.
        ChessBotDialog.closeEvent = _bukkax_chess_close_event
except Exception:
    pass

# ---------- BUKKAX CHESS SOUNDS + CHECK + SYNC CLOSE PATCH END ----------

# ---------- BUKKAX CHESS SOUND/CHECK FIX V2 START ----------
# Финальный фикс после всех старых monkey-patch:
# 1) заранее загружает звук хода;
# 2) отслеживает изменение самой позиции, а не только turn;
# 3) не даёт одному ходу проиграться дважды;
# 4) поверх самого последнего redraw красит короля под шахом.

def _bukkax_chess_position_signature_v2(self):
    try:
        move_id = int(
            getattr(
                self.rules,
                '_bukkax_move_id',
                -1
            )
        )
    except Exception:
        move_id = -1

    try:
        board_key = tuple(
            tuple(row)
            for row in self.rules.board
        )
    except Exception:
        board_key = ()

    try:
        turn = int(self.rules.turn)
    except Exception:
        turn = -1

    return (
        move_id,
        turn,
        board_key,
    )


def _bukkax_chess_ensure_sound_players_v2(self):
    if _BukkaxChessMediaPlayer is None:
        return False

    try:
        move_path = _bukkax_chess_sound_path(
            'move.mp3'
        )
        check_path = _bukkax_chess_sound_path(
            'check.wav'
        )

        if getattr(
            self,
            '_bukkax_move_player',
            None
        ) is None:
            self._bukkax_move_player = (
                _BukkaxChessMediaPlayer(self)
            )
            self._bukkax_move_audio = (
                _BukkaxChessAudioOutput(self)
            )
            self._bukkax_move_audio.setVolume(
                0.82
            )
            self._bukkax_move_player.setAudioOutput(
                self._bukkax_move_audio
            )

            if move_path:
                self._bukkax_move_player.setSource(
                    _BukkaxChessQUrl.fromLocalFile(
                        move_path
                    )
                )

        if getattr(
            self,
            '_bukkax_check_player',
            None
        ) is None:
            self._bukkax_check_player = (
                _BukkaxChessMediaPlayer(self)
            )
            self._bukkax_check_audio = (
                _BukkaxChessAudioOutput(self)
            )
            self._bukkax_check_audio.setVolume(
                0.92
            )
            self._bukkax_check_player.setAudioOutput(
                self._bukkax_check_audio
            )

            if check_path:
                self._bukkax_check_player.setSource(
                    _BukkaxChessQUrl.fromLocalFile(
                        check_path
                    )
                )

        return True

    except Exception as e:
        try:
            print(
                'Chess sound preload error:',
                e
            )
        except Exception:
            pass
        return False


def _bukkax_chess_play_move_sound_v2(self):
    try:
        if not _bukkax_chess_ensure_sound_players_v2(
            self
        ):
            return

        player = getattr(
            self,
            '_bukkax_move_player',
            None
        )

        if player is None:
            return

        # Источник уже был задан при открытии доски.
        # Поэтому первый ход не теряется на загрузке MP3.
        player.stop()
        player.setPosition(0)
        player.play()

    except Exception as e:
        try:
            print(
                'Chess move sound error:',
                e
            )
        except Exception:
            pass


def _bukkax_chess_play_check_sound_v2(self):
    try:
        if not _bukkax_chess_ensure_sound_players_v2(
            self
        ):
            return

        player = getattr(
            self,
            '_bukkax_check_player',
            None
        )

        if player is None:
            return

        player.stop()
        player.setPosition(0)
        player.play()

    except Exception:
        pass


# Старые обёртки первого патча ищут эти функции по имени
# во время выполнения, поэтому перенаправляем их на V2.
try:
    _bukkax_chess_ensure_sound_players = (
        _bukkax_chess_ensure_sound_players_v2
    )
    _bukkax_chess_play_move_sound = (
        _bukkax_chess_play_move_sound_v2
    )
    _bukkax_chess_play_check_sound = (
        _bukkax_chess_play_check_sound_v2
    )
except Exception:
    pass


def _bukkax_chess_after_successful_move_v2(self):
    signature = (
        _bukkax_chess_position_signature_v2(
            self
        )
    )

    # Один и тот же ход может увидеть старая и новая обёртка.
    # Проигрываем его только один раз.
    if getattr(
        self,
        '_bukkax_last_sound_signature_v2',
        None
    ) == signature:
        return

    self._bukkax_last_sound_signature_v2 = (
        signature
    )

    _bukkax_chess_play_move_sound_v2(
        self
    )

    try:
        checked = self.rules.is_check(
            str(self.rules.turn)
        )
    except Exception:
        checked = False

    if checked:
        try:
            QTimer.singleShot(
                140,
                lambda obj=self:
                    _bukkax_chess_play_check_sound_v2(
                        obj
                    )
            )
        except Exception:
            _bukkax_chess_play_check_sound_v2(
                self
            )


# И старый sound-wrapper теперь тоже использует V2 + dedupe.
try:
    _bukkax_chess_after_successful_move = (
        _bukkax_chess_after_successful_move_v2
    )
except Exception:
    pass


def _bukkax_chess_wrap_final_move_method_v2(
    cls,
    method_name
):
    marker = (
        '_bukkax_final_sound_v2_'
        + method_name
    )

    if getattr(
        cls,
        marker,
        False
    ):
        return

    try:
        previous = getattr(
            cls,
            method_name
        )
    except Exception:
        return

    def wrapped(
        self,
        *args,
        **kwargs
    ):
        before = (
            _bukkax_chess_position_signature_v2(
                self
            )
        )

        result = previous(
            self,
            *args,
            **kwargs
        )

        after = (
            _bukkax_chess_position_signature_v2(
                self
            )
        )

        if after != before:
            _bukkax_chess_after_successful_move_v2(
                self
            )

        return result

    setattr(
        cls,
        method_name,
        wrapped
    )
    setattr(
        cls,
        marker,
        True
    )


# Цепляемся именно к ФИНАЛЬНЫМ функциям,
# которые уже назначены HISTORY PANEL V2.
_bukkax_chess_wrap_final_move_method_v2(
    ChessDialog,
    '_square_clicked'
)
_bukkax_chess_wrap_final_move_method_v2(
    ChessDialog,
    'apply_remote_move'
)
_bukkax_chess_wrap_final_move_method_v2(
    ChessBotDialog,
    '_square_clicked'
)
_bukkax_chess_wrap_final_move_method_v2(
    ChessBotDialog,
    '_bot_move'
)


def _bukkax_chess_highlight_check_v2(self):
    any_check = False

    try:
        for color in (0, 1):
            if not self.rules.is_check(
                str(color)
            ):
                continue

            any_check = True
            king_code = (
                'K' + str(color)
            )

            king_pos = None

            for by in range(8):
                for bx in range(8):
                    if (
                        self.rules.board[by][bx]
                        == king_code
                    ):
                        king_pos = (
                            bx,
                            by
                        )
                        break

                if king_pos is not None:
                    break

            if king_pos is None:
                continue

            bx, by = king_pos
            dx, dy = (
                self._board_to_display(
                    bx,
                    by
                )
            )

            btn = self.buttons.get(
                (dx, dy)
            )

            if btn is None:
                continue

            # Полностью задаём стиль клетки короля ПОСЛЕ
            # всех предыдущих redraw, чтобы его уже ничто не затёрло.
            btn.setStyleSheet(
                'background-color:#ff6b6b;'
                'border:5px solid #ff1744;'
                'font-size:34px;'
                'color:#111111;'
            )

        if any_check:
            try:
                text = (
                    self.status.text()
                    or ''
                )

                if 'ШАХ' not in text:
                    self.status.setText(
                        text
                        + '  ⚠ ШАХ!'
                    )

                self.status.setStyleSheet(
                    'font-size:13px;'
                    'color:#ff6b6b;'
                    'font-weight:800;'
                )
            except Exception:
                pass

    except Exception as e:
        try:
            print(
                'Chess check highlight error:',
                e
            )
        except Exception:
            pass


def _bukkax_chess_wrap_final_redraw_v2(
    cls
):
    if getattr(
        cls,
        '_bukkax_final_check_redraw_v2',
        False
    ):
        return

    previous = cls._redraw

    def wrapped(self):
        # Предзагрузка звуков происходит уже при первом
        # открытии/перерисовке доски.
        try:
            _bukkax_chess_ensure_sound_players_v2(
                self
            )
        except Exception:
            pass

        result = previous(
            self
        )

        _bukkax_chess_highlight_check_v2(
            self
        )

        return result

    cls._redraw = wrapped
    cls._bukkax_final_check_redraw_v2 = True


_bukkax_chess_wrap_final_redraw_v2(
    ChessDialog
)
_bukkax_chess_wrap_final_redraw_v2(
    ChessBotDialog
)

# ---------- BUKKAX CHESS SOUND/CHECK FIX V2 END ----------

# ---------- BUKKAX CHESS OWN MOVE SOUND FIX V3 START ----------
# Низколатентный звук ходов через QSoundEffect.
# Звук привязан непосредственно к успешному ChessRules.move(),
# поэтому одинаково срабатывает на свой ход, ход друга и ход бота.

try:
    from PySide6.QtMultimedia import QSoundEffect as _BukkaxQSoundEffectV3
    from PySide6.QtCore import QUrl as _BukkaxQUrlV3
except Exception:
    _BukkaxQSoundEffectV3 = None
    _BukkaxQUrlV3 = None


def _bukkax_sound_dirs_v3():
    dirs = []

    def add(path):
        if path and path not in dirs:
            dirs.append(path)

    try:
        add(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'bukkax_chess_sounds'
        ))
    except Exception:
        pass

    try:
        add(os.path.join(
            os.getcwd(),
            'bukkax_chess_sounds'
        ))
    except Exception:
        pass

    try:
        add(os.path.join(
            os.path.dirname(sys.executable),
            'bukkax_chess_sounds'
        ))
    except Exception:
        pass

    try:
        meipass = getattr(sys, '_MEIPASS', '')
        if meipass:
            add(os.path.join(
                meipass,
                'bukkax_chess_sounds'
            ))
    except Exception:
        pass

    return dirs


def _bukkax_sound_file_v3(filename):
    for folder in _bukkax_sound_dirs_v3():
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            return path
    return None


def _bukkax_init_effect_v3(parent, path, volume):
    if (
        _BukkaxQSoundEffectV3 is None
        or _BukkaxQUrlV3 is None
        or not path
    ):
        return None

    try:
        effect = _BukkaxQSoundEffectV3(parent)
        effect.setSource(
            _BukkaxQUrlV3.fromLocalFile(path)
        )
        effect.setVolume(float(volume))
        effect.setLoopCount(1)
        return effect
    except Exception as e:
        try:
            print('Chess QSoundEffect init error:', e)
        except Exception:
            pass
        return None


def _bukkax_prepare_sounds_v3(dialog):
    if getattr(
        dialog,
        '_bukkax_sound_v3_ready',
        False
    ):
        return

    dialog._bukkax_sound_v3_ready = True

    move_path = _bukkax_sound_file_v3(
        'move.wav'
    )
    check_path = _bukkax_sound_file_v3(
        'check.wav'
    )

    # Два экземпляра звука хода.
    # Поэтому быстрый ответ бота не обрывает звук хода игрока.
    dialog._bukkax_move_effects_v3 = [
        _bukkax_init_effect_v3(
            dialog,
            move_path,
            0.86
        ),
        _bukkax_init_effect_v3(
            dialog,
            move_path,
            0.86
        ),
    ]
    dialog._bukkax_move_effect_index_v3 = 0

    dialog._bukkax_check_effect_v3 = (
        _bukkax_init_effect_v3(
            dialog,
            check_path,
            0.92
        )
    )

    try:
        print(
            'Chess sounds V3:',
            'move=' + str(bool(move_path)),
            'check=' + str(bool(check_path))
        )
    except Exception:
        pass


def _bukkax_play_move_v3(dialog):
    try:
        _bukkax_prepare_sounds_v3(
            dialog
        )

        effects = getattr(
            dialog,
            '_bukkax_move_effects_v3',
            []
        )

        effects = [
            effect
            for effect in effects
            if effect is not None
        ]

        if not effects:
            return

        index = int(
            getattr(
                dialog,
                '_bukkax_move_effect_index_v3',
                0
            )
        ) % len(effects)

        effect = effects[index]

        dialog._bukkax_move_effect_index_v3 = (
            index + 1
        ) % len(effects)

        # Этот экземпляр можно перезапустить,
        # второй экземпляр при этом продолжит предыдущий звук.
        effect.stop()
        effect.play()

    except Exception as e:
        try:
            print(
                'Chess move sound V3 error:',
                e
            )
        except Exception:
            pass


def _bukkax_play_check_v3(dialog):
    try:
        _bukkax_prepare_sounds_v3(
            dialog
        )

        effect = getattr(
            dialog,
            '_bukkax_check_effect_v3',
            None
        )

        if effect is None:
            return

        effect.stop()
        effect.play()
    except Exception:
        pass


# Выключаем старые QMediaPlayer sound-callbacks V1/V2,
# чтобы один ход не воспроизводился дважды.
def _bukkax_legacy_sound_noop_v3(*args, **kwargs):
    return None


try:
    _bukkax_chess_after_successful_move = (
        _bukkax_legacy_sound_noop_v3
    )
except Exception:
    pass

try:
    _bukkax_chess_after_successful_move_v2 = (
        _bukkax_legacy_sound_noop_v3
    )
except Exception:
    pass


# При создании ChessDialog связываем ChessRules с конкретным окном
# и заранее загружаем WAV в память Qt.
try:
    if not getattr(
        ChessDialog,
        '_bukkax_sound_init_v3_wrapped',
        False
    ):
        _bukkax_prev_chess_init_v3 = ChessDialog.__init__

        def _bukkax_chess_init_v3(
            self,
            *args,
            **kwargs
        ):
            _bukkax_prev_chess_init_v3(
                self,
                *args,
                **kwargs
            )

            try:
                self.rules._bukkax_sound_dialog_v3 = self
            except Exception:
                pass

            _bukkax_prepare_sounds_v3(
                self
            )

        ChessDialog.__init__ = (
            _bukkax_chess_init_v3
        )
        ChessDialog._bukkax_sound_init_v3_wrapped = True
except Exception:
    pass


# Самая надёжная точка: каждый реальный ход обязательно проходит
# через ChessRules.move(). Здесь звук запускается СРАЗУ после успеха,
# до redraw и до QTimer ответа бота.
try:
    if not getattr(
        ChessRules,
        '_bukkax_move_sound_v3_wrapped',
        False
    ):
        _bukkax_prev_rules_move_v3 = ChessRules.move

        def _bukkax_rules_move_sound_v3(
            self,
            *args,
            **kwargs
        ):
            ok, result = _bukkax_prev_rules_move_v3(
                self,
                *args,
                **kwargs
            )

            if ok:
                dialog = getattr(
                    self,
                    '_bukkax_sound_dialog_v3',
                    None
                )

                if dialog is not None:
                    _bukkax_play_move_v3(
                        dialog
                    )

                    try:
                        in_check = bool(
                            self.is_check(
                                str(self.turn)
                            )
                        )
                    except Exception:
                        in_check = False

                    if in_check:
                        try:
                            QTimer.singleShot(
                                90,
                                lambda d=dialog:
                                    _bukkax_play_check_v3(d)
                            )
                        except Exception:
                            _bukkax_play_check_v3(
                                dialog
                            )

            return ok, result

        ChessRules.move = (
            _bukkax_rules_move_sound_v3
        )
        ChessRules._bukkax_move_sound_v3_wrapped = True
except Exception as e:
    try:
        print(
            'ChessRules sound V3 patch error:',
            e
        )
    except Exception:
        pass

# ---------- BUKKAX CHESS OWN MOVE SOUND FIX V3 END ----------

# ---------- BUKKAX CHESS COORDS + RANDOM COLORS V1 START ----------
try:
    _BUKKAX_CHESS_COORDS_BASE_REDRAW = ChessDialog._redraw
except Exception:
    _BUKKAX_CHESS_COORDS_BASE_REDRAW = None


def _bukkax_piece_readable(piece):
    try:
        if not piece or piece == '.':
            return ''
        names = {
            'K': 'Король',
            'Q': 'Ферзь',
            'R': 'Ладья',
            'B': 'Слон',
            'H': 'Конь',
            'P': 'Пешка',
            'p': 'Пешка',
        }
        title = names.get(str(piece)[0], str(piece))
        color_name = 'белая' if str(piece)[-1] == '0' else 'чёрная'
        return f'{color_name} {title}'
    except Exception:
        return str(piece)


def _bukkax_square_name(x, y):
    try:
        return _BUKKAX_FILES[int(x)] + str(8 - int(y))
    except Exception:
        return f'{x},{y}'


def _bukkax_chess_update_coord_labels(self):
    try:
        labels = getattr(self, 'file_labels', {})
        for dx in range(8):
            bx, by = self._display_to_board(dx, 7)
            text = _bukkax_square_name(bx, by)[0]
            lbl = labels.get(dx)
            if lbl is not None:
                lbl.setText(text)
    except Exception:
        pass

    try:
        labels = getattr(self, 'rank_labels', {})
        for dy in range(8):
            bx, by = self._display_to_board(0, dy)
            text = _bukkax_square_name(bx, by)[1:]
            lbl = labels.get(dy)
            if lbl is not None:
                lbl.setText(text)
    except Exception:
        pass

    try:
        for dy in range(8):
            for dx in range(8):
                bx, by = self._display_to_board(dx, dy)
                btn = self.buttons.get((dx, dy))
                if btn is None:
                    continue

                btn.setToolTip("")
    except Exception:
        pass


def _bukkax_chess_build_ui_with_coords(self):
    _bukkax_history_ensure(self)
    try:
        self.resize(max(self.width(), 960), max(self.height(), 780))
    except Exception:
        pass

    root = QVBoxLayout(self)
    root.setContentsMargins(14, 12, 14, 12)
    root.setSpacing(8)

    top = QHBoxLayout()
    top.setContentsMargins(0, 0, 0, 0)
    top.setSpacing(8)

    self.title = QLabel()
    self.title.setWordWrap(False)
    self.title.setMinimumWidth(0)
    self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    self.title.setStyleSheet('font-size: 17px; font-weight: bold; color: #ffffff;')
    top.addWidget(self.title, 1)

    self.restart_btn = QPushButton('↻ Новая')
    self.restart_btn.setToolTip('Начать новую партию')
    self.restart_btn.setFixedHeight(30)
    self.restart_btn.setMinimumWidth(86)
    self.restart_btn.clicked.connect(self._restart_clicked)
    top.addWidget(self.restart_btn, 0)

    self.resign_btn = QPushButton('🏳 Сдаться')
    self.resign_btn.setToolTip('Сдаться / закрыть партию')
    self.resign_btn.setFixedHeight(30)
    self.resign_btn.setMinimumWidth(92)
    self.resign_btn.clicked.connect(self._resign_clicked)
    top.addWidget(self.resign_btn, 0)
    root.addLayout(top)

    self.status = QLabel()
    self.status.setWordWrap(True)
    self.status.setStyleSheet('font-size: 13px; color: #ffffff;')
    root.addWidget(self.status)

    body = QHBoxLayout()
    body.setContentsMargins(0, 0, 0, 0)
    body.setSpacing(12)

    left = QVBoxLayout()
    left.setContentsMargins(0, 0, 0, 0)
    left.setSpacing(8)

    self.board_outer = QWidget()
    self.board_outer.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    self.board_outer_box = QGridLayout(self.board_outer)
    self.board_outer_box.setContentsMargins(0, 0, 0, 0)
    self.board_outer_box.setHorizontalSpacing(4)
    self.board_outer_box.setVerticalSpacing(4)

    self.rank_labels = {}
    self.file_labels = {}
    self.buttons = {}

    for row in range(8):
        lbl = QLabel('')
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet('color:#dfe6ff; font-size:12px; font-weight:700; background:transparent;')
        self.board_outer_box.addWidget(lbl, row, 0)
        self.rank_labels[row] = lbl

    self.board_outer_box.addWidget(QLabel(''), 8, 0)

    self.board_wrap = QWidget()
    self.board_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    self.board_box = QGridLayout(self.board_wrap)
    self.board_box.setContentsMargins(0, 0, 0, 0)
    self.board_box.setSpacing(0)

    for row in range(8):
        for col in range(8):
            btn = QPushButton()
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.setFixedSize(72, 72)
            btn.setIconSize(QSize(56, 56))
            btn.clicked.connect(lambda checked=False, c=col, r=row: self._square_clicked(c, r))
            self.board_box.addWidget(btn, row, col)
            self.buttons[(col, row)] = btn

    self.board_outer_box.addWidget(self.board_wrap, 0, 1, 8, 8)

    for col in range(8):
        lbl = QLabel('')
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet('color:#dfe6ff; font-size:12px; font-weight:700; background:transparent;')
        self.board_outer_box.addWidget(lbl, 8, col + 1)
        self.file_labels[col] = lbl

    left.addWidget(self.board_outer, 0, Qt.AlignHCenter)

    hint = QLabel('Координаты клеток показаны на доске. Белые ходят первыми. Фигуру выбираешь кликом, потом кликаешь клетку хода.')
    hint.setWordWrap(True)
    hint.setStyleSheet('color: #ffffff; font-size: 12px;')
    left.addWidget(hint)
    body.addLayout(left, 1)

    self.history_panel = QWidget()
    self.history_panel.setObjectName('chessHistoryPanel')
    self.history_panel.setFixedWidth(250)
    side = QVBoxLayout(self.history_panel)
    side.setContentsMargins(12, 12, 12, 12)
    side.setSpacing(8)

    panel_title = QLabel('История ходов')
    panel_title.setStyleSheet('color:#ffffff; font-size:16px; font-weight:700;')
    side.addWidget(panel_title)

    self.opening_label = QLabel('Дебют: Пока нет ходов')
    self.opening_label.setWordWrap(True)
    self.opening_label.setStyleSheet('color:#ffffff; font-size:12px; font-weight:600;')
    side.addWidget(self.opening_label)

    self.variation_label = QLabel('Вариация: Сделай первый ход')
    self.variation_label.setWordWrap(True)
    self.variation_label.setStyleSheet('color:#cfd7ff; font-size:12px;')
    side.addWidget(self.variation_label)

    self.last_move_label = QLabel('Последний ход: —')
    self.last_move_label.setWordWrap(True)
    self.last_move_label.setStyleSheet('color:#ffffff; font-size:12px;')
    side.addWidget(self.last_move_label)

    if QTextBrowser is not None:
        self.moves_browser = QTextBrowser()
        self.moves_browser.setReadOnly(True)
        self.moves_browser.setMinimumHeight(360)
        self.moves_browser.setStyleSheet("QTextBrowser { background: #111522; color: #ffffff; border: 1px solid #2c344d; border-radius: 8px; padding: 8px; font-size: 14px; }")
        side.addWidget(self.moves_browser, 1)
    else:
        self.moves_browser = QLabel('История ходов недоступна')
        self.moves_browser.setWordWrap(True)
        self.moves_browser.setStyleSheet('color:#ffffff;')
        side.addWidget(self.moves_browser, 1)

    body.addWidget(self.history_panel, 0, Qt.AlignTop)
    root.addLayout(body, 1)

    self.setStyleSheet("QDialog { background: #151824; color: #ffffff; } QLabel { color: #ffffff; } QPushButton { border-radius: 6px; color: #ffffff; background: #273047; padding: 4px 8px; font-weight: 600; } QPushButton:hover { background: #33405f; } QPushButton:disabled { color: #8d96b5; background: #202638; } QWidget#chessHistoryPanel { background: #1b2030; border: 1px solid #2c344d; border-radius: 12px; } QMessageBox QLabel { color: #ffffff; } QInputDialog QLabel { color: #ffffff; }")
    try:
        self._resize_board_cells()
    except Exception:
        pass
    try:
        _bukkax_update_history_panel(self)
    except Exception:
        pass
    try:
        _bukkax_chess_update_coord_labels(self)
    except Exception:
        pass


def _bukkax_chess_resize_board_cells_with_coords(self):
    try:
        right = 290 if hasattr(self, 'history_panel') else 0
        available_w = max(360, self.width() - right - 64)
        available_h = max(360, self.height() - 152)
        cell = min(82, max(46, min(available_w // 8, available_h // 8)))
        icon = max(34, cell - 16)

        rank_w = max(18, min(28, cell // 2))
        file_h = max(18, min(24, cell // 2))

        if hasattr(self, 'board_wrap'):
            self.board_wrap.setFixedSize(cell * 8, cell * 8)
        if hasattr(self, 'board_outer'):
            self.board_outer.setFixedSize(rank_w + 4 + cell * 8, cell * 8 + 4 + file_h)

        for btn in getattr(self, 'buttons', {}).values():
            btn.setFixedSize(cell, cell)
            btn.setIconSize(QSize(icon, icon))

        for _row, lbl in getattr(self, 'rank_labels', {}).items():
            try:
                lbl.setFixedSize(rank_w, cell)
            except Exception:
                pass

        for _col, lbl in getattr(self, 'file_labels', {}).items():
            try:
                lbl.setFixedSize(cell, file_h)
            except Exception:
                pass
    except Exception:
        pass


def _bukkax_chess_redraw_with_coords(self):
    try:
        if _BUKKAX_CHESS_COORDS_BASE_REDRAW is not None:
            _BUKKAX_CHESS_COORDS_BASE_REDRAW(self)
    except Exception:
        pass
    try:
        _bukkax_chess_update_coord_labels(self)
    except Exception:
        pass


try:
    ChessDialog._build_ui = _bukkax_chess_build_ui_with_coords
    ChessDialog._resize_board_cells = _bukkax_chess_resize_board_cells_with_coords
    ChessDialog._redraw = _bukkax_chess_redraw_with_coords

    ChessBotDialog._build_ui = _bukkax_chess_build_ui_with_coords
    ChessBotDialog._resize_board_cells = _bukkax_chess_resize_board_cells_with_coords
    ChessBotDialog._redraw = _bukkax_chess_redraw_with_coords
except Exception:
    pass
# ---------- BUKKAX CHESS COORDS + RANDOM COLORS V1 END ----------

# ---------- BUKKAX RANDOM CHECK SOUNDS V4 START ----------
# На каждый шах выбирается случайный звук из
# bukkax_chess_sounds/check_random/.
#
# Поддерживает WAV/MP3 через QMediaPlayer.
# Новый шах останавливает предыдущий длинный звук.
# Если звуков > 1 — один и тот же файл не повторяется два шаха подряд.

try:
    import random as _bukkax_check_random_v4
    import time as _bukkax_check_time_v4
    from PySide6.QtMultimedia import (
        QMediaPlayer as _BukkaxCheckPlayerV4,
        QAudioOutput as _BukkaxCheckAudioV4,
    )
    from PySide6.QtCore import (
        QUrl as _BukkaxCheckQUrlV4,
        QTimer as _BukkaxCheckQTimerV4,
    )
except Exception:
    _BukkaxCheckPlayerV4 = None
    _BukkaxCheckAudioV4 = None
    _BukkaxCheckQUrlV4 = None
    _BukkaxCheckQTimerV4 = None


def _bukkax_check_sound_dirs_v4():
    dirs = []

    def add(path):
        if path and path not in dirs:
            dirs.append(path)

    try:
        add(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'bukkax_chess_sounds',
            'check_random',
        ))
    except Exception:
        pass

    try:
        add(os.path.join(
            os.getcwd(),
            'bukkax_chess_sounds',
            'check_random',
        ))
    except Exception:
        pass

    try:
        add(os.path.join(
            os.path.dirname(sys.executable),
            'bukkax_chess_sounds',
            'check_random',
        ))
    except Exception:
        pass

    try:
        meipass = getattr(sys, '_MEIPASS', '')
        if meipass:
            add(os.path.join(
                meipass,
                'bukkax_chess_sounds',
                'check_random',
            ))
    except Exception:
        pass

    return dirs


def _bukkax_check_sound_files_v4():
    allowed = ('.wav', '.mp3', '.ogg', '.m4a', '.aac')
    result = []

    for folder in _bukkax_check_sound_dirs_v4():
        if not os.path.isdir(folder):
            continue

        try:
            names = sorted(os.listdir(folder))
        except Exception:
            continue

        for name in names:
            if not name.lower().endswith(allowed):
                continue

            path = os.path.join(folder, name)
            if os.path.isfile(path) and path not in result:
                result.append(path)

    return result


def _bukkax_prepare_random_check_player_v4(dialog):
    if _BukkaxCheckPlayerV4 is None:
        return False

    if getattr(
        dialog,
        '_bukkax_random_check_player_v4',
        None,
    ) is None:
        try:
            dialog._bukkax_random_check_player_v4 = (
                _BukkaxCheckPlayerV4(dialog)
            )
            dialog._bukkax_random_check_audio_v4 = (
                _BukkaxCheckAudioV4(dialog)
            )
            dialog._bukkax_random_check_audio_v4.setVolume(
                0.92
            )
            dialog._bukkax_random_check_player_v4.setAudioOutput(
                dialog._bukkax_random_check_audio_v4
            )
        except Exception as e:
            try:
                print(
                    'Random check player init error:',
                    e,
                )
            except Exception:
                pass
            return False

    return True


def _bukkax_play_random_check_v4(dialog):
    try:
        # Защита от двойного вызова одного и того же шаха
        # через несколько старых monkey-patch обёрток.
        now = _bukkax_check_time_v4.monotonic()

        if (
            now
            - float(
                getattr(
                    dialog,
                    '_bukkax_last_random_check_time_v4',
                    0.0,
                )
            )
            < 0.35
        ):
            return

        dialog._bukkax_last_random_check_time_v4 = now

        files = _bukkax_check_sound_files_v4()

        if not files:
            return

        last_path = getattr(
            dialog,
            '_bukkax_last_random_check_path_v4',
            '',
        )

        choices = [
            path
            for path in files
            if path != last_path
        ]

        if not choices:
            choices = files

        path = _bukkax_check_random_v4.choice(
            choices
        )

        dialog._bukkax_last_random_check_path_v4 = path

        if not _bukkax_prepare_random_check_player_v4(
            dialog
        ):
            return

        player = dialog._bukkax_random_check_player_v4

        # Если предыдущий рандомный звук ещё играет — новый шах его заменяет.
        player.stop()
        player.setSource(
            _BukkaxCheckQUrlV4.fromLocalFile(
                path
            )
        )
        player.setPosition(0)
        player.play()

        try:
            print(
                'Chess CHECK random sound:',
                os.path.basename(path),
            )
        except Exception:
            pass

    except Exception as e:
        try:
            print(
                'Random check sound error:',
                e,
            )
        except Exception:
            pass


# V3 вызывает эту функцию по глобальному имени в момент шаха.
# Переопределение не требует переписывать старую обёртку ChessRules.move().
try:
    _bukkax_play_check_v3 = (
        _bukkax_play_random_check_v4
    )
except Exception:
    pass


# Совместимость, если у пользователя остался только V2/V1.
try:
    _bukkax_chess_play_check_sound_v2 = (
        _bukkax_play_random_check_v4
    )
except Exception:
    pass

try:
    _bukkax_chess_play_check_sound = (
        _bukkax_play_random_check_v4
    )
except Exception:
    pass


# Если никакого старого sound-patch вообще нет,
# создаём минимальный hook только для шаха.
_bukkax_has_old_check_hook_v4 = (
    getattr(
        ChessRules,
        '_bukkax_move_sound_v3_wrapped',
        False,
    )
    or '_bukkax_chess_play_check_sound_v2'
       in globals()
    or '_bukkax_chess_play_check_sound'
       in globals()
)


if not _bukkax_has_old_check_hook_v4:
    try:
        if not getattr(
            ChessDialog,
            '_bukkax_random_check_init_v4_wrapped',
            False,
        ):
            _bukkax_prev_chess_init_random_check_v4 = (
                ChessDialog.__init__
            )

            def _bukkax_chess_init_random_check_v4(
                self,
                *args,
                **kwargs
            ):
                _bukkax_prev_chess_init_random_check_v4(
                    self,
                    *args,
                    **kwargs
                )

                try:
                    self.rules._bukkax_random_check_dialog_v4 = (
                        self
                    )
                except Exception:
                    pass

                try:
                    _bukkax_prepare_random_check_player_v4(
                        self
                    )
                except Exception:
                    pass

            ChessDialog.__init__ = (
                _bukkax_chess_init_random_check_v4
            )
            ChessDialog._bukkax_random_check_init_v4_wrapped = (
                True
            )
    except Exception:
        pass

    try:
        if not getattr(
            ChessRules,
            '_bukkax_random_check_move_v4_wrapped',
            False,
        ):
            _bukkax_prev_rules_move_random_check_v4 = (
                ChessRules.move
            )

            def _bukkax_rules_move_random_check_v4(
                self,
                *args,
                **kwargs
            ):
                ok, result = (
                    _bukkax_prev_rules_move_random_check_v4(
                        self,
                        *args,
                        **kwargs
                    )
                )

                if ok:
                    try:
                        checked = bool(
                            self.is_check(
                                str(self.turn)
                            )
                        )
                    except Exception:
                        checked = False

                    if checked:
                        dialog = getattr(
                            self,
                            '_bukkax_random_check_dialog_v4',
                            None,
                        )

                        if dialog is not None:
                            try:
                                if _BukkaxCheckQTimerV4 is not None:
                                    _BukkaxCheckQTimerV4.singleShot(
                                        90,
                                        lambda d=dialog:
                                            _bukkax_play_random_check_v4(
                                                d
                                            )
                                    )
                                else:
                                    _bukkax_play_random_check_v4(
                                        dialog
                                    )
                            except Exception:
                                _bukkax_play_random_check_v4(
                                    dialog
                                )

                return ok, result

            ChessRules.move = (
                _bukkax_rules_move_random_check_v4
            )
            ChessRules._bukkax_random_check_move_v4_wrapped = (
                True
            )

    except Exception as e:
        try:
            print(
                'Random check fallback hook error:',
                e,
            )
        except Exception:
            pass

# ---------- BUKKAX RANDOM CHECK SOUNDS V4 END ----------
