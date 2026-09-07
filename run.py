from fractions import Fraction
import calibration
import frame_check
import create_midi

# ── setting ────────────────────────────────
VIDEO = "./source/ray.mp4"         # Path to the input video file
FPS = 60                          # Video frame rate (frames per second)
BPM = 132                         # Tempo of the performance in Beats Per Minute
TIME_SIGNATURE = '4/4'            # Musical time signature (numerator / denominator)

# Tuning parameters (recommended to adjust based on results)
MISS_GRID = Fraction(1, 8)        # Minimum note duration/grid size (e.g., 1/8 note)
REST_IGNORE_FRAMES = 3            # Gaps of this many frames or fewer are ignored (avoids tiny, unwanted rests)
ONSET_MERGE_TOLERANCE = 2         # Notes triggered within this frame count are merged into a single chord
# ────────────────────────────────────────────

KEYBOARD_JSON = "./data/keyboard_calibration.json"
COLOR_JSON = "./data/color_calibration.json"
EVENTS_JSON = "./data/note_events.json"
OUTPUT_MIDI = "./output/output.mid"

assert FPS == __import__("cv2").VideoCapture(VIDEO).get(__import__("cv2").CAP_PROP_FPS)

# calibration.run_calibration_wizard(
#     video_path=VIDEO,
#     keyboard_json_path=KEYBOARD_JSON,
#     color_json_path=COLOR_JSON,
# )

# frame_check.process_video(
#     video_path=VIDEO,
#     keyboard_json_path=KEYBOARD_JSON,
#     color_json_path=COLOR_JSON,
#     events_out=EVENTS_JSON,
# )

# create_midi.generate_midi(
#     events_json=EVENTS_JSON,
#     output_midi=OUTPUT_MIDI,
#     bpm=BPM,
#     miss_grid=MISS_GRID,
#     rest_ignore_frames=REST_IGNORE_FRAMES,
#     onset_merge_tolerance=ONSET_MERGE_TOLERANCE,
#     fps=FPS
# )

print("\nDone.")