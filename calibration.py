import cv2, json, numpy as np
from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QInputDialog, QLabel,
                             QMainWindow, QPushButton, QSlider, QVBoxLayout, QWidget)
from config import generate_88_key_layout

class CalibrationCanvas(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.win = parent
        self.frame_rgb = self.frame_shape = None
        self.dragging = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_frame(self, frame_bgr):
        self.frame_shape = frame_bgr.shape[:2]
        self.frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        self.update()

    def _video_rect(self):
        if not self.frame_shape:
            return QRect()
        h, w = self.frame_shape
        r = self.rect()
        s = min(r.width() / w, r.height() / h)
        return QRect(r.x() + int(r.width() - w * s) // 2, r.y() + int(r.height() - h * s) // 2, int(w * s), int(h * s))

    def frame_to_widget_rect(self, x, y, w, h):
        if not self.frame_shape or (vr := self._video_rect()).isNull():
            return QRect()
        fh, fw = self.frame_shape
        return QRect(
            int(vr.x() + x * vr.width() / fw),
            int(vr.y() + y * vr.height() / fh),
            max(1, int(w * vr.width() / fw)),
            max(1, int(h * vr.height() / fh)),
        )

    def widget_to_frame(self, pos, clamp=False):
        if not self.frame_shape or (vr := self._video_rect()).isNull():
            return None
        x = max(vr.left(), min(vr.right(), pos.x())) if clamp or not vr.contains(pos) else pos.x()
        y = max(vr.top(), min(vr.bottom(), pos.y())) if clamp or not vr.contains(pos) else pos.y()
        if not clamp and not vr.contains(pos):
            return None
        fh, fw = self.frame_shape
        return (
            max(0, min(fw - 1, int((x - vr.x()) * fw / vr.width()))),
            max(0, min(fh - 1, int((y - vr.y()) * fh / vr.height()))),
        )

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        if self.frame_rgb is not None:
            h, w = self.frame_shape
            p.drawPixmap(self._video_rect(), QPixmap.fromImage(QImage(self.frame_rgb.data, w, h, self.frame_rgb.strides[0], QImage.Format_RGB888)))
            self.win.paint_overlay(p)

    def mousePressEvent(self, e):
        if fp := self.widget_to_frame(e.pos()):
            self.dragging = True
            self.win.canvas_mouse_press(fp)

    def mouseMoveEvent(self, e):
        if self.dragging and (fp := self.widget_to_frame(e.pos(), clamp=True)):
            self.win.canvas_mouse_move(fp)

    def mouseReleaseEvent(self, e):
        if self.dragging:
            self.dragging = False
            if fp := self.widget_to_frame(e.pos(), clamp=True):
                self.win.canvas_mouse_release(fp)
            else:
                self.win.finalize_keyboard_region()
        self.setFocus()

    def keyPressEvent(self, e):
        if not self.win.handle_key_press(e):
            super().keyPressEvent(e)


class PyQtCalibrationWindow(QMainWindow):
    def __init__(self, video_path, keyboard_json_path, color_json_path):
        super().__init__()
        self.keyboard_json_path, self.color_json_path = keyboard_json_path, color_json_path
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        self.voices = ["left", "right"]
        self.color_profile = {}
        self._update_color_labels() 

        self.step = 1
        self.current_frame_idx = self.selected_key_idx = self.sample_idx = 0
        self.current_frame = self.keyboard_region = self.region_start = self.region_end = None
        self.drag_key_origin = self.drag_mouse_origin = None
        self.keys = []

        self._build_ui()
        self.load_frame(0)
        self.refresh_ui()

    def _update_color_labels(self):
        self.color_labels = [(f"{v}_{k}", f"{v.replace('_', ' ').title()} {k.title()} (Pressed)") for v in self.voices for k in ("white", "black")]

    def _build_ui(self):
        self.setWindowTitle("Video2Score Calibration")
        self.canvas, self.status_label = CalibrationCanvas(self), QLabel()
        self.status_label.setStyleSheet("color: white; font-size: 14px;")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, max(0, self.total_frames - 1))
        self.slider.valueChanged.connect(self.seek_frame)

        self.prev_btn, self.next_btn, self.add_voice_btn = QPushButton("Prev"), QPushButton("Next"), QPushButton("+ Add Voice")
        btn_style = """
            QPushButton {
                background-color: #007ACC; color: white; font-weight: bold; 
                border-radius: 4px; padding: 0 16px; font-size: 14px; 
                min-height: 36px; max-height: 36px;
            }
            QPushButton:hover { background-color: #0098FF; }
            QPushButton:disabled { background-color: #444444; color: #888888; }
        """
        self.prev_btn.setStyleSheet(btn_style)
        self.add_voice_btn.setStyleSheet(btn_style)
        self.next_btn.setStyleSheet(btn_style)

        self.prev_btn.clicked.connect(self.prev_step)
        self.next_btn.clicked.connect(self.next_step)
        self.add_voice_btn.clicked.connect(self.add_custom_voice)

        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(12, 8, 12, 12)
        ctrl_layout.setSpacing(10)
        for w, stretch in [(self.prev_btn, 0), (self.add_voice_btn, 0), (self.status_label, 1), (self.next_btn, 0)]:
            ctrl_layout.addWidget(w, stretch, Qt.AlignVCenter)

        bottom_box = QVBoxLayout()
        bottom_box.setContentsMargins(0, 0, 0, 0)
        bottom_box.setSpacing(0)
        bottom_box.addWidget(self.slider)
        bottom_box.addLayout(ctrl_layout)

        root = QWidget()
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.canvas, 1)
        rl.addLayout(bottom_box)
        root.setStyleSheet("background: black;")
        self.setCentralWidget(root)

    def keyPressEvent(self, e):
        if not self.handle_key_press(e):
            super().keyPressEvent(e)

    def add_custom_voice(self):
            text, ok = QInputDialog.getText(
                self, 
                "Add Voice", 
                "Enter voice name (e.g., a_left, a_right, pedal):"
            )
            if ok and (v := text.strip().lower().replace(" ", "_")):
                if v not in self.voices:
                    self.voices.append(v)
                    self._update_color_labels()
                    self.refresh_ui()

    def load_frame(self, idx):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(self.total_frames - 1, int(idx))))
        ok, frame = self.cap.read()
        if ok and frame is not None:
            self.current_frame_idx, self.current_frame = idx, frame
            self.canvas.set_frame(frame)

    def seek_frame(self, val):
        if self.step in (1, 3):
            self.load_frame(val)
            self.refresh_ui()

    def refresh_ui(self):
        self.prev_btn.setEnabled(self.step > 1)
        self.slider.setEnabled(self.step in (1, 3))
        self.add_voice_btn.setVisible(self.step == 3)
        if self.step == 1:
            self.hud_title = "1/3 Select Keyboard Region"
            self.hud_hint = f"Frame {self.current_frame_idx}/{self.total_frames - 1} · Drag keyboard."
            self.next_btn.setText("Confirm Region")
        elif self.step == 2:
            st = f"{self.keys[self.selected_key_idx]['name']} (MIDI {self.keys[self.selected_key_idx]['midi']})" if self.keys else "None"
            self.hud_title = "2/3 Adjust Key Boxes"
            self.hud_hint = f"Selected: {st} · Drag/Arrows: Move · +/-: Width · [/]: Height"
            self.next_btn.setText("Sample Colors")
        else:
            ck, label = self.color_labels[self.sample_idx]
            self.hud_title = f"3/3 Color Sampling ({self.sample_idx + 1}/{len(self.color_labels)})"
            self.hud_hint = f"Click {label}" + (f" · Set: {self.color_profile[ck]['name']}" if ck in self.color_profile else "")
            self.next_btn.setText("Save" if self.sample_idx == len(self.color_labels) - 1 else "Next Color")

        self.status_label.setText(f"{self.hud_title}  —  {self.hud_hint}")
        self.canvas.update()

    def paint_overlay(self, p):
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 155))
        p.drawRoundedRect(16, 16, min(1100, self.canvas.width() - 32), 92, 8, 8)

        p.setFont(QFont("Malgun Gothic", 15, QFont.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(32, 46, self.hud_title)

        p.setFont(QFont("Malgun Gothic", 11))
        p.setPen(QColor(220, 220, 220))
        p.drawText(32, 72, self.hud_hint)

        p.setPen(QColor(160, 160, 160))
        p.drawText(32, 96, "Enter · Next    ESC · Exit    F11 · Fullscreen")

        if self.step == 1 and (r := self._current_region_rect()):
            p.setPen(QPen(QColor(0, 255, 255), 3))
            p.setBrush(QColor(0, 255, 255, 35))
            p.drawRect(self.canvas.frame_to_widget_rect(*r))
        elif self.step in (2, 3):
            ck = self.color_labels[self.sample_idx][0] if self.step == 3 else None
            for idx, key in enumerate(self.keys):
                r = self.canvas.frame_to_widget_rect(key["x"], key["y"], key["w"], key["h"])
                if self.step == 3:
                    sampled = {self.color_profile[k]["midi"]: k for k, _ in self.color_labels if k in self.color_profile}
                    if sampled.get(key["midi"]) == ck:
                        color, width = QColor(0, 220, 255), 3
                    elif key["is_black"] == ck.endswith("_black"):
                        color, width = (QColor(255, 80, 80) if key["is_black"] else QColor(80, 255, 80)), 2
                    else:
                        color, width = QColor(90, 90, 90), 1
                else:
                    color, width = (QColor(255, 255, 0), 3) if idx == self.selected_key_idx else (QColor(255, 80, 80) if key["is_black"] else QColor(80, 255, 80), 2)
                p.setPen(QPen(color, width))
                p.setBrush(Qt.NoBrush)
                p.drawRect(r)

    def _current_region_rect(self):
        if not self.region_start or not self.region_end:
            return self.keyboard_region
        x1, y1, x2, y2 = *self.region_start, *self.region_end
        return (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)) if abs(x2 - x1) > 0 and abs(y2 - y1) > 0 else None

    def finalize_keyboard_region(self):
        if self.step == 1 and (r := self._current_region_rect()):
            self.keyboard_region = r
            self.refresh_ui()

    def canvas_mouse_press(self, pos):
        if self.step == 1:
            self.region_start = self.region_end = pos
        elif self.step == 2 and (i := self._key_at(pos)[0]) is not None:
            self.selected_key_idx = i
            self.drag_key_origin, self.drag_mouse_origin = self.keys[i].copy(), pos
        elif self.step == 3:
            self.sample_key_detector(pos)

    def canvas_mouse_move(self, pos):
        if self.step == 1:
            self.region_end = pos
        elif self.step == 2 and self.drag_key_origin:
            self.keys[self.selected_key_idx].update({
                "x": int(self.drag_key_origin["x"] + pos[0] - self.drag_mouse_origin[0]),
                "y": int(self.drag_key_origin["y"] + pos[1] - self.drag_mouse_origin[1]),
            })
        self.canvas.update()

    def canvas_mouse_release(self, pos):
        if self.step == 1:
            self.region_end = pos
            self.keyboard_region = self._current_region_rect()
        self.drag_key_origin = self.drag_mouse_origin = None
        self.refresh_ui()

    def _key_at(self, pos):
        for i in range(len(self.keys) - 1, -1, -1):
            key = self.keys[i]
            if key["x"] <= pos[0] <= key["x"] + key["w"] and key["y"] <= pos[1] <= key["y"] + key["h"]:
                return i, key
        return None, None

    def sample_key_detector(self, pos):
        _, key = self._key_at(pos)
        if not key or key["is_black"] != self.color_labels[self.sample_idx][0].endswith("_black"):
            return
        fh, fw = self.canvas.frame_shape
        roi = self.current_frame[max(0, key["y"]):min(fh, key["y"] + key["h"]), max(0, key["x"]):min(fw, key["x"] + key["w"])]
        if roi.size == 0:
            return
        hsv = cv2.cvtColor(np.uint8([[[*roi.reshape(-1, 3).mean(axis=0)]]]), cv2.COLOR_BGR2HSV)[0][0]
        self.color_profile[self.color_labels[self.sample_idx][0]] = {
            "h": int(hsv[0]), "s": int(hsv[1]), "v": int(hsv[2]), "midi": key["midi"], "name": key["name"],
        }
        self.refresh_ui()

    def prev_step(self):
        if self.step == 3 and self.sample_idx > 0:
            self.sample_idx -= 1
        elif self.step > 1:
            self.step -= 1
            self.sample_idx = 0
        self.refresh_ui()

    def next_step(self):
        if self.step == 1:
            if not (r := self.keyboard_region or self._current_region_rect()):
                return
            self.keyboard_region = r
            self.keys = generate_88_key_layout(r[0], r[0] + r[2], r[1], white_h=r[3])
            self.step = 2
        elif self.step == 2:
            self.step = 3
            self.sample_idx = 0
        else:
            if self.color_labels[self.sample_idx][0] not in self.color_profile:
                return
            if self.sample_idx < len(self.color_labels) - 1:
                self.sample_idx += 1
            else:
                self.save_outputs()
                self.close()
                return
        self.refresh_ui()
        self.canvas.setFocus()

    def save_outputs(self):
        profile = {k: {"h": v["h"], "s": v["s"], "v": v["v"]} for k, v in self.color_profile.items()}
        profile["tolerance"] = {"h": 12, "s": 60, "v": 60}
        with open(self.keyboard_json_path, "w", encoding="utf-8") as f:
            json.dump(self.keys, f, ensure_ascii=False, indent=2)
        with open(self.color_json_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

    def handle_key_press(self, e):
        k = e.key()
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
        if k in (Qt.Key_N, Qt.Key_P):
            self.selected_key_idx = (self.selected_key_idx + (1 if k == Qt.Key_N else -1)) % len(self.keys)
        elif (tf := {
            Qt.Key_Left: ("x", -1), Qt.Key_Right: ("x", 1),
            Qt.Key_Up: ("y", -1), Qt.Key_Down: ("y", 1),
            Qt.Key_Plus: ("w", 1), Qt.Key_Equal: ("w", 1), Qt.Key_Minus: ("w", -1),
            Qt.Key_BracketRight: ("h", 1), Qt.Key_BracketLeft: ("h", -1),
        }.get(k)):
            sel[tf[0]] = max(1, sel[tf[0]] + tf[1]) if tf[0] in ("w", "h") else sel[tf[0]] + tf[1]
        else:
            return False
        self.refresh_ui()
        return True


def run_calibration_wizard(video_path, keyboard_json_path, color_json_path):
    app = QApplication.instance() or QApplication([])
    w = PyQtCalibrationWindow(video_path, keyboard_json_path, color_json_path)
    w.showFullScreen()
    app.exec_()