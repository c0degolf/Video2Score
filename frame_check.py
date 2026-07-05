import csv
import json
import cv2
import numpy as np
from config import NUM_KEYS, midi_to_key_index

def hsv_dist(h1, s1, v1, h2, s2, v2):
    dh = min(abs(h1 - h2), 180 - abs(h1 - h2))
    return (dh * 2) ** 2 + (s1 - s2) ** 2 + (v1 - v2) ** 2


def process_video(video_path, keyboard_json_path, color_json_path,
                  matrix_out=None,
                  csv_out=None,
                  events_out="note_events.json"):
    with open(keyboard_json_path, encoding="utf-8") as f:
        keys = json.load(f)
    with open(color_json_path, encoding="utf-8") as f:
        profile = json.load(f)

    tol = profile["tolerance"]
    threshold = (tol["h"] * 2) ** 2 + tol["s"] ** 2 + tol["v"] ** 2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    left_hand = np.zeros((NUM_KEYS, total_frames), dtype=np.uint8)
    right_hand = np.zeros((NUM_KEYS, total_frames), dtype=np.uint8)

    prev_state = {k["midi"]: "idle" for k in keys}
    events = []
    frame_idx = 0

    if csv_out:
        csvf = open(csv_out, "w", newline="", encoding="utf-8")
        writer = csv.writer(csvf)
        writer.writerow(["frame", "time_sec", "midi", "note_name", "state"])
    else:
        csvf = None
        writer = None

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        t = frame_idx / fps
        l_col = left_hand[:, frame_idx]
        r_col = right_hand[:, frame_idx]
        l_col[:] = 0
        r_col[:] = 0

        for key in keys:
            x, y, w, h = key["x"], key["y"], key["w"], key["h"]
            y0, y1 = max(0, y), min(frame_h, y + h)
            x0, x1 = max(0, x), min(frame_w, x + w)
            if y1 <= y0 or x1 <= x0:
                state = "idle"
            else:
                roi = frame[y0:y1, x0:x1]
                hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                h_, s_, v_ = hsv.reshape(-1, 3).mean(axis=0)

                if key["is_black"] and "left_black" in profile and "right_black" in profile:
                    lp = profile["left_black"]
                    rp = profile["right_black"]
                elif (not key["is_black"]) and "left_white" in profile and "right_white" in profile:
                    lp = profile["left_white"]
                    rp = profile["right_white"]
                else:
                    lp = profile["left_hand"]
                    rp = profile["right_hand"]

                dl = hsv_dist(h_, s_, v_, lp["h"], lp["s"], lp["v"])
                dr = hsv_dist(h_, s_, v_, rp["h"], rp["s"], rp["v"])
                best = min(dl, dr)

                if best <= threshold:
                    state = "left" if dl <= dr else "right"
                else:
                    state = "idle"

            ki = midi_to_key_index(key["midi"])
            if state == "left":
                l_col[ki] = 1
            elif state == "right":
                r_col[ki] = 1

            if writer:
                writer.writerow([frame_idx, f"{t:.3f}", key["midi"], key["name"], state])

            prev = prev_state[key["midi"]]
            cur = state
            if cur != prev:
                if prev == "idle" and cur in ("left", "right"):
                    events.append({"type": "note_on", "midi": key["midi"],
                                   "name": key["name"], "hand": cur,
                                   "frame": frame_idx, "time": round(t, 3)})
                elif prev in ("left", "right") and cur == "idle":
                    events.append({"type": "note_off", "midi": key["midi"],
                                   "name": key["name"], "hand": prev,
                                   "frame": frame_idx, "time": round(t, 3)})
                elif prev in ("left", "right") and cur in ("left", "right"):
                    events.append({"type": "note_off", "midi": key["midi"],
                                   "name": key["name"], "hand": prev,
                                   "frame": frame_idx, "time": round(t, 3)})
                    events.append({"type": "note_on", "midi": key["midi"],
                                   "name": key["name"], "hand": cur,
                                   "frame": frame_idx, "time": round(t, 3)})
                prev_state[key["midi"]] = cur

        if frame_idx % max(1, int(fps)) == 0:
            pct = (frame_idx / total_frames * 100) if total_frames else 0
            print(f"\rProcessing... {frame_idx}/{total_frames} ({pct:.1f}%)", end="", flush=True)

        frame_idx += 1

    cap.release()
    if csvf:
        csvf.close()

    left_hand = left_hand[:, :frame_idx]
    right_hand = right_hand[:, :frame_idx]

    with open(events_out, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

    if matrix_out:
        np.savez(matrix_out,
                 left_hand=left_hand,
                 right_hand=right_hand,
                 fps=np.float64(fps),
                 frame_count=np.int32(left_hand.shape[1]))

    print()
    print(f"Processed {frame_idx} frames  (fps={fps:.2f})")
    if csv_out: print(f"  CSV log         : {csv_out}")
    print(f"  Note events     : {events_out}  ({len(events)} events)")
    if matrix_out: print(f"  Press matrices  : {matrix_out}  shape={left_hand.shape}")

    return {
        "left_hand": left_hand,
        "right_hand": right_hand,
        "fps": fps,
        "events": events,
    }
