import cv2
import json
import numpy as np
from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)
from config import generate_88_key_layout

COLOR_LABELS = [
    ("left_white",  "Left · White Key (Pressed)"),
    ("left_black",  "Left · Black Key (Pressed)"),
    ("right_white", "Right · White Key (Pressed)"),
    ("right_black", "Right · Black Key (Pressed)"),
]
HINT = "Enter · Next    ESC · Exit    F11 · Fullscreen"


class CalibrationCanvas(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.window = parent
        self.frame_rgb = None
        self.frame_shape = None
        self.dragging = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_frame(self, frame_bgr):
        self.frame_shape = frame_bgr.shape[:2]
        self.frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        self.update()

    def _video_rect(self):
        if self.frame_shape is None:
            return QRect()
        h, w = self.frame_shape
        r = self.rect()
        s = min(r.width() / w, r.height() / h)
        dw, dh = int(w * s), int(h * s)
        return QRect(r.x() + (r.width() - dw) // 2, r.y() + (r.height() - dh) // 2, dw, dh)

    def frame_to_widget_rect(self, x, y, w, h):
        vr = self._video_rect()
        if self.frame_shape is None or vr.isNull():
            return QRect()
        fh, fw = self.frame_shape
        sx, sy = vr.width() / fw, vr.height() / fh
        return QRect(int(vr.x() + x * sx), int(vr.y() + y * sy), max(1, int(w * sx)), max(1, int(h * sy)))

    def widget_to_frame(self, pos, clamp=False):
        vr = self._video_rect()
        if self.frame_shape is None or vr.isNull():
            return None
        x, y = pos.x(), pos.y()
        if not vr.contains(pos):
            if not clamp:
                return None
            x = max(vr.left(), min(vr.right(), x))
            y = max(vr.top(), min(vr.bottom(), y))
        fh, fw = self.frame_shape
        fx = int((x - vr.x()) * fw / vr.width())
        fy = int((y - vr.y()) * fh / vr.height())
        return max(0, min(fw - 1, fx)), max(0, min(fh - 1, fy))

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        if self.frame_rgb is None:
            return
        h, w = self.frame_shape
        img = QImage(self.frame_rgb.data, w, h, self.frame_rgb.strides[0], QImage.Format_RGB888)
        p.drawPixmap(self._video_rect(), QPixmap.fromImage(img))
        self.window.paint_overlay(p)

    def mousePressEvent(self, event):
        fp = self.widget_to_frame(event.pos())
        if fp is None:
            return
        self.dragging = True
        self.window.canvas_mouse_press(fp)

    def mouseMoveEvent(self, event):
        if not self.dragging:
            return
        fp = self.widget_to_frame(event.pos(), clamp=True)
        if fp is not None:
            self.window.canvas_mouse_move(fp)

    def mouseReleaseEvent(self, event):
        was = self.dragging
        self.dragging = False
        if was:
            fp = self.widget_to_frame(event.pos(), clamp=True)
            if fp is not None:
                self.window.canvas_mouse_release(fp)
            else:
                self.window.finalize_keyboard_region()
        self.setFocus()

    def keyPressEvent(self, event):
        if self.window.handle_key_press(event):
            return
        super().keyPressEvent(event)


class PyQtCalibrationWindow(QMainWindow):
    def __init__(self, video_path, keyboard_json_path, color_json_path):
        super().__init__()
        self.keyboard_json_path = keyboard_json_path
        self.color_json_path = color_json_path
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if self.total_frames <= 0:
            raise RuntimeError("Empty video or failed to get frame count.")

        self.step = 1
        self.current_frame_idx = 0
        self.current_frame = None
        self.keyboard_region = None
        self.region_start = None
        self.region_end = None
        self.keys = []
        self.selected_key_idx = 0
        self.drag_key_origin = None
        self.drag_mouse_origin = None
        self.sample_idx = 0
        self.color_profile = {}

        self._build_ui()
        self.load_frame(0)
        self.refresh_ui()
        self.canvas.setFocus()

    def _build_ui(self):
        self.setWindowTitle("Video2Score Calibration")
        self.canvas = CalibrationCanvas(self)
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: white; font-size: 14px;")
        self.hud_title = ""
        self.hud_hint = ""

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, self.total_frames - 1)
        self.slider.valueChanged.connect(self.seek_frame)

        self.prev_btn = QPushButton("Prev")
        self.next_btn = QPushButton("Next")
        self.prev_btn.clicked.connect(self.prev_step)
        self.next_btn.clicked.connect(self.next_step)

        ctrl = QWidget()
        hl = QHBoxLayout(ctrl)
        hl.setContentsMargins(12, 6, 12, 10)
        hl.addWidget(self.prev_btn)
        hl.addWidget(self.status_label, 1)
        hl.addWidget(self.next_btn)

        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.slider)
        bl.addWidget(ctrl)

        root = QWidget()
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.canvas, 1)
        rl.addWidget(bottom)
        root.setStyleSheet("background: black;")
        self.setCentralWidget(root)

    def showEvent(self, event):
        super().showEvent(event)
        self.canvas.setFocus()

    def closeEvent(self, event):
        self.cap.release()
        super().closeEvent(event)

    def load_frame(self, idx):
        idx = max(0, min(self.total_frames - 1, int(idx)))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = self.cap.read()
        if not ok:
            return
        self.current_frame_idx = idx
        self.current_frame = frame
        self.canvas.set_frame(frame)

    def seek_frame(self, value):
        if self.step in (1, 3):
            self.load_frame(value)
            self.refresh_ui()

    def _show_hint(self, msg):
        self.hud_hint = msg
        self.status_label.setText(f"{self.hud_title}  —  {self.hud_hint}")
        self.canvas.update()

    def refresh_ui(self):
        self.prev_btn.setEnabled(self.step > 1)
        self.slider.setEnabled(self.step in (1, 3))

        if self.step == 1:
            self.hud_title = "1/3  Select Keyboard Region"
            self.hud_hint = (
                f"Frame {self.current_frame_idx}/{self.total_frames - 1}  ·  "
                "Seek to a clear view, then drag to select the entire keyboard."
            )
            self.next_btn.setText("Confirm Region")
        elif self.step == 2:
            sel = self.keys[self.selected_key_idx] if self.keys else None
            st = f"{sel['name']} (MIDI {sel['midi']})" if sel else "None"
            self.hud_title = "2/3  Adjust Key Boxes"
            self.hud_hint = (
                f"Selected: {st}  ·  "
                "Drag: Move  ·  Arrows: Fine move  ·  +/-: Width  ·  [/]: Height  ·  N/P: Select key"
            )
            self.next_btn.setText("Sample Colors")
        else:
            ck, label = COLOR_LABELS[self.sample_idx]
            phase = self.sample_idx + 1
            kt = "White Key" if ck.endswith("_white") else "Black Key"
            note = ""
            if ck in self.color_profile:
                note = f"  ·  Set: {self.color_profile[ck]['name']}"
            self.hud_title = f"3/3  Color Sampling ({phase}/4)"
            self.hud_hint = (
                f"Frame {self.current_frame_idx}/{self.total_frames - 1}  ·  "
                f"Click {label} detector ({kt}){note}  ·  Enter for next"
            )
            self.next_btn.setText("Save" if self.sample_idx == 3 else "Next Color")

        self.status_label.setText(f"{self.hud_title}  —  {self.hud_hint}")
        self.canvas.update()

    def paint_overlay(self, painter):
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_hud(painter)
        if self.step == 1:
            self._paint_region(painter)
        elif self.step == 2:
            self._paint_keys(painter)
        else:
            self._paint_keys(painter, sampling=True)

    def _paint_hud(self, painter):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 155))
        w = min(1100, self.canvas.width() - 32)
        painter.drawRoundedRect(16, 16, w, 92, 8, 8)
        f1 = QFont("Malgun Gothic", 15)
        f1.setBold(True)
        painter.setFont(f1)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(32, 46, self.hud_title)
        f2 = QFont("Malgun Gothic", 11)
        painter.setFont(f2)
        painter.setPen(QColor(220, 220, 220))
        painter.drawText(32, 72, self.hud_hint)
        painter.setPen(QColor(160, 160, 160))
        painter.drawText(32, 96, HINT)

    def _paint_region(self, painter):
        r = self._current_region_rect()
        if r is None:
            return
        wr = self.canvas.frame_to_widget_rect(*r)
        painter.setPen(QPen(QColor(0, 255, 255), 3))
        painter.setBrush(QColor(0, 255, 255, 35))
        painter.drawRect(wr)

    def _paint_keys(self, painter, sampling=False):
        sampled = {}
        if sampling:
            for k, _ in COLOR_LABELS:
                if k in self.color_profile:
                    sampled[self.color_profile[k]["midi"]] = k
        ck, _ = COLOR_LABELS[self.sample_idx] if sampling else (None, None)
        expect_black = ck.endswith("_black") if ck else None

        for idx, key in enumerate(self.keys):
            r = self.canvas.frame_to_widget_rect(key["x"], key["y"], key["w"], key["h"])
            if sampling:
                if key["midi"] in sampled:
                    sk = sampled[key["midi"]]
                    color = QColor(0, 220, 255) if sk == ck else QColor(160, 160, 160)
                    width = 3 if sk == ck else 1
                elif key["is_black"] == expect_black:
                    color = QColor(255, 80, 80) if key["is_black"] else QColor(80, 255, 80)
                    width = 2
                else:
                    color = QColor(90, 90, 90)
                    width = 1
            elif idx == self.selected_key_idx:
                color = QColor(255, 255, 0)
                width = 3
            elif key["is_black"]:
                color = QColor(255, 80, 80)
                width = 2
            else:
                color = QColor(80, 255, 80)
                width = 2
            painter.setPen(QPen(color, width))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(r)

    def _current_region_rect(self):
        if self.region_start is None or self.region_end is None:
            return self.keyboard_region
        x1, y1 = self.region_start
        x2, y2 = self.region_end
        x, y = min(x1, x2), min(y1, y2)
        w, h = abs(x2 - x1), abs(y2 - y1)
        return (x, y, w, h) if w > 0 and h > 0 else None

    def finalize_keyboard_region(self):
        if self.step != 1:
            return
        r = self._current_region_rect()
        if r is not None:
            self.keyboard_region = r
            self.refresh_ui()

    def canvas_mouse_press(self, pos):
        if self.step == 1:
            self.region_start = pos
            self.region_end = pos
        elif self.step == 2:
            self._select_key_at(pos)
            if self.keys:
                self.drag_key_origin = self.keys[self.selected_key_idx].copy()
                self.drag_mouse_origin = pos
        else:
            self.sample_key_detector(pos)

    def canvas_mouse_move(self, pos):
        if self.step == 1:
            self.region_end = pos
        elif self.step == 2 and self.drag_key_origin is not None:
            dx = pos[0] - self.drag_mouse_origin[0]
            dy = pos[1] - self.drag_mouse_origin[1]
            k = self.keys[self.selected_key_idx]
            k["x"] = int(self.drag_key_origin["x"] + dx)
            k["y"] = int(self.drag_key_origin["y"] + dy)
        self.canvas.update()

    def canvas_mouse_release(self, pos):
        if self.step == 1:
            self.region_end = pos
            self.keyboard_region = self._current_region_rect()
        self.drag_key_origin = None
        self.drag_mouse_origin = None
        self.refresh_ui()

    def _key_at(self, pos):
        x, y = pos
        for i in range(len(self.keys) - 1, -1, -1):
            k = self.keys[i]
            if k["x"] <= x <= k["x"] + k["w"] and k["y"] <= y <= k["y"] + k["h"]:
                return i, k
        return None, None

    def _select_key_at(self, pos):
        i, _ = self._key_at(pos)
        if i is not None:
            self.selected_key_idx = i

    def _sample_hsv_from_key(self, key):
        x, y, w, h = key["x"], key["y"], key["w"], key["h"]
        x0, x1 = max(0, x), min(self.frame_w, x + w)
        y0, y1 = max(0, y), min(self.frame_h, y + h)
        roi = self.current_frame[y0:y1, x0:x1]
        if roi.size == 0:
            return None
        b, g, r = roi.reshape(-1, 3).mean(axis=0)
        arr = np.uint8([[[b, g, r]]])
        hsv = cv2.cvtColor(arr, cv2.COLOR_BGR2HSV)[0][0]
        return int(hsv[0]), int(hsv[1]), int(hsv[2])

    def sample_key_detector(self, pos):
        _, key = self._key_at(pos)
        if key is None:
            self._show_hint("Please click a key detector.")
            return
        ck, label = COLOR_LABELS[self.sample_idx]
        expect_black = ck.endswith("_black")
        if key["is_black"] != expect_black:
            want = "Black key" if expect_black else "White key"
            self._show_hint(f"Please click a {want} detector here. ({label})")
            return
        hsv = self._sample_hsv_from_key(key)
        if hsv is None:
            return
        self.color_profile[ck] = {"h": hsv[0], "s": hsv[1], "v": hsv[2],
                                  "midi": key["midi"], "name": key["name"]}
        self.refresh_ui()

    def prev_step(self):
        if self.step == 3 and self.sample_idx > 0:
            self.sample_idx -= 1
        elif self.step > 1:
            self.step -= 1
            if self.step == 3:
                self.sample_idx = 0
        self.refresh_ui()

    def next_step(self):
        if self.step == 1:
            region = self.keyboard_region or self._current_region_rect()
            if region is None:
                self._show_hint("Drag to select the entire keyboard, then press Enter or [Confirm Region].")
                return
            self.keyboard_region = region
            x, y, w, h = region
            self.keys = generate_88_key_layout(x, x + w, y, white_h=h)
            self.step = 2
        elif self.step == 2:
            self.step = 3
            self.sample_idx = 0
        else:
            ck, label = COLOR_LABELS[self.sample_idx]
            if ck not in self.color_profile:
                self._show_hint(f"Please sample {label} first.")
                return
            if self.sample_idx < 3:
                self.sample_idx += 1
            else:
                self.save_outputs()
                self.close()
                return
        self.refresh_ui()
        self.canvas.setFocus()

    def save_outputs(self):
        profile = {k: {"h": v["h"], "s": v["s"], "v": v["v"]}
                   for k, v in self.color_profile.items()}
        profile["left_hand"] = profile["left_white"]
        profile["right_hand"] = profile["right_white"]
        profile["tolerance"] = {"h": 12, "s": 60, "v": 60}
        with open(self.keyboard_json_path, "w", encoding="utf-8") as f:
            json.dump(self.keys, f, ensure_ascii=False, indent=2)
        with open(self.color_json_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        print(f"Saved keyboard layout : {self.keyboard_json_path}  ({len(self.keys)} keys)")
        print(f"Saved color profile   : {self.color_json_path}")

    def handle_key_press(self, event):
        k = event.key()
        if k == Qt.Key_Escape:
            self.close()
            return True
        if k == Qt.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
            return True
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self.next_step()
            return True
        if self.step != 2 or not self.keys:
            return False
        sel = self.keys[self.selected_key_idx]
        if k == Qt.Key_N:
            self.selected_key_idx = (self.selected_key_idx + 1) % len(self.keys)
        elif k == Qt.Key_P:
            self.selected_key_idx = (self.selected_key_idx - 1) % len(self.keys)
        elif k == Qt.Key_Left:
            sel["x"] -= 1
        elif k == Qt.Key_Right:
            sel["x"] += 1
        elif k == Qt.Key_Up:
            sel["y"] -= 1
        elif k == Qt.Key_Down:
            sel["y"] += 1
        elif k in (Qt.Key_Plus, Qt.Key_Equal):
            sel["w"] += 1
        elif k == Qt.Key_Minus:
            sel["w"] = max(1, sel["w"] - 1)
        elif k == Qt.Key_BracketRight:
            sel["h"] += 1
        elif k == Qt.Key_BracketLeft:
            sel["h"] = max(1, sel["h"] - 1)
        else:
            return False
        self.refresh_ui()
        return True


def run_calibration_wizard(video_path, keyboard_json_path, color_json_path):
    app = QApplication.instance() or QApplication([])
    w = PyQtCalibrationWindow(video_path, keyboard_json_path, color_json_path)
    w.showFullScreen()
    app.exec_()