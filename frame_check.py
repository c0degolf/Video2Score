import json
import cv2

def events_to_notes(events):
    active = {}
    notes = []

    for ev in events:
        midi = ev["midi"]

        if ev["type"] == "note_on":
            active[midi] = {
                "start": ev["frame"],
                "name": ev["name"],
            }

        elif ev["type"] == "note_off" and midi in active:
            start = active[midi]["start"]

            notes.append({
                "midi": midi,
                "name": active[midi]["name"],
                "start": start,
                "end": ev["frame"],
                "duration_frame": ev["frame"] - start,
            })

            del active[midi]

    return notes

def hsv_dist(h1, s1, v1, h2, s2, v2):
    dh = min(abs(h1 - h2), 180 - abs(h1 - h2))
    return (dh * 2) ** 2 + (s1 - s2) ** 2 + (v1 - v2) ** 2

def process_video(video_path, keyboard_json_path, color_json_path, events_out):
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
    frame_w, frame_h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    prev_state = {k["midi"]: "idle" for k in keys}
    left_events = []
    right_events = []
    frame_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok: break

        for key in keys:
            x, y, w, h = key["x"], key["y"], key["w"], key["h"]
            y0, y1 = max(0, y), min(frame_h, y + h)
            x0, x1 = max(0, x), min(frame_w, x + w)
            state = "idle"
            if y1 > y0 and x1 > x0:
                roi = frame[y0:y1, x0:x1]
                hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                h_, s_, v_ = hsv.reshape(-1, 3).mean(axis=0)

                # Simplified profile selection
                if key["is_black"]:
                    lp, rp = profile.get("left_black", profile["left_hand"]), profile.get("right_black", profile["right_hand"])
                else:
                    lp, rp = profile.get("left_white", profile["left_hand"]), profile.get("right_white", profile["right_hand"])

                dl = hsv_dist(h_, s_, v_, lp["h"], lp["s"], lp["v"])
                dr = hsv_dist(h_, s_, v_, rp["h"], rp["s"], rp["v"])
                if min(dl, dr) <= threshold:
                    state = "left" if dl <= dr else "right"

            prev = prev_state[key["midi"]]
            if state != prev:
                ev_on = {"type": "note_on", "midi": key["midi"], "name": key["name"], "frame": frame_idx}
                ev_off = {"type": "note_off", "midi": key["midi"], "name": key["name"], "frame": frame_idx}

                if prev == "idle":
                    if state == "left":
                        left_events.append(ev_on)
                    elif state == "right":
                        right_events.append(ev_on)

                elif state == "idle":
                    if prev == "left":
                        left_events.append(ev_off)
                    elif prev == "right":
                        right_events.append(ev_off)

                else:  # hand switch
                    if prev == "left":
                        left_events.append(ev_off)
                    elif prev == "right":
                        right_events.append(ev_off)

                    if state == "left":
                        left_events.append(ev_on)
                    elif state == "right":
                        right_events.append(ev_on)

                prev_state[key["midi"]] = state
        if frame_idx % max(1, int(fps)) == 0:
            print(f"\rProcessing... {frame_idx}/{total_frames} ({frame_idx/total_frames*100:.1f}%)", end="", flush=True)
        frame_idx += 1

    cap.release()

    left_notes = events_to_notes(left_events)
    right_notes = events_to_notes(right_events)

    with open(events_out, "w", encoding="utf-8") as f:
        json.dump(
            {
                "left_notes": left_notes,
                "right_notes": right_notes,
            },
            f,
            indent=2,
        )

    print(f"\nProcessing complete. Notes saved to {events_out}")