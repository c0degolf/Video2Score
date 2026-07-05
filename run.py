import calibration
import frame_check
import create_midi

# ── setting ────────────────────────────────
VIDEO = "./source/V.mp4"
BPM = 182
TIME_SIGNATURE = (4, 4)     # numerator / denominator
# ────────────────────────────────────────────

KEYBOARD_JSON = "./data/keyboard_calibration.json"
COLOR_JSON = "./data/color_calibration.json"
EVENTS_JSON = "./data/note_events.json"
OUTPUT_MIDI = "./output/output.mid"

# Step 1: Calibration wizard
calibration.run_calibration_wizard(
    video_path=VIDEO,
    keyboard_json_path=KEYBOARD_JSON,
    color_json_path=COLOR_JSON,
)

# Step 2: Per-frame key state detection
result = frame_check.process_video(
    video_path=VIDEO,
    keyboard_json_path=KEYBOARD_JSON,
    color_json_path=COLOR_JSON,
    events_out=EVENTS_JSON,
)

# Step 3: Generate MIDI
create_midi.generate_midi(
    events_json=EVENTS_JSON,
    output_midi=OUTPUT_MIDI,
    bpm=BPM,
    time_signature=TIME_SIGNATURE
)

print(f"\nDone. Total note events: {len(result['events'])}")