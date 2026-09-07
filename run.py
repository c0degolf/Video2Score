from fractions import Fraction
import calibration
import frame_check
import create_midi

# ── setting ────────────────────────────────
VIDEO = "./source/ray.mp4"
FPS = 60
BPM = 132
TIME_SIGNATURE = '4/4'     # numerator / denominator

# 아래의 설정들은 직접 다뤄보면서 수정하기를 추천
MISS_GRID = Fraction(1, 8)    # 최소 박자 단위, defualt: 1/8 박
REST_IGNORE_FRAMES = 3         # gaps of REST_IGNORE_FRAMES or fewer are treated as no gap: no rest inserted
ONSET_MERGE_TOLERANCE = 2      # n프레임 차로 눌린 동시에 끝나는 화음을 동시에 누른 것으로 병합
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