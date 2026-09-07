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

    voices = sorted({k[:-6] for k in profile if k.endswith(("_white", "_black"))})

    tol = profile["tolerance"]
    threshold = (tol["h"] * 2) ** 2 + tol["s"] ** 2 + tol["v"] ** 2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_w, frame_h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    prev_state = {k["midi"]: "idle" for k in keys}
    voice_events = {v: [] for v in voices}
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

                suffix = "_black" if key["is_black"] else "_white"
                best_voice = "idle"
                min_dist = float('inf')

                for v in voices:
                    p_key = f"{v}{suffix}"
                    if p_key in profile:
                        p = profile[p_key]
                        d = hsv_dist(h_, s_, v_, p["h"], p["s"], p["v"])
                        if d < min_dist:
                            min_dist = d
                            best_voice = v

                if min_dist <= threshold:
                    state = best_voice

            prev = prev_state[key["midi"]]
            if state != prev:
                ev_on = {"type": "note_on", "midi": key["midi"], "name": key["name"], "frame": frame_idx}
                ev_off = {"type": "note_off", "midi": key["midi"], "name": key["name"], "frame": frame_idx}

                if prev == "idle":
                    if state in voice_events:
                        voice_events[state].append(ev_on)
                elif state == "idle":
                    if prev in voice_events:
                        voice_events[prev].append(ev_off)
                else:  # Hand/Voice switch
                    if prev in voice_events:
                        voice_events[prev].append(ev_off)
                    if state in voice_events:
                        voice_events[state].append(ev_on)

                prev_state[key["midi"]] = state

        if frame_idx % max(1, int(fps)) == 0:
            print(f"\rProcessing... {frame_idx}/{total_frames} ({frame_idx/total_frames*100:.1f}%)", end="", flush=True)
        frame_idx += 1

    cap.release()

    output_data = {}
    for v in voices:
        output_data[f"{v}_notes"] = events_to_notes(voice_events[v])

    with open(events_out, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nProcessing complete. Notes saved to {events_out}")