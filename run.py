from fractions import Fraction
import calibration
import frame_check
import create_midi

# ── setting ────────────────────────────────
VIDEO = "./source/V.mp4"
BPM = 182
TIME_SIGNATURE = '4/4'     # numerator / denominator

# 아래의 설정들은 직접 다뤄보면서 수정하기를 추천
create_midi.MISS_GRID = Fraction(1, 16)    # 1박을 n등분한 단위로 박자 자동 정렬
create_midi.REST_IGNORE_FRAMES = 2         # gaps of REST_IGNORE_FRAMES or fewer are treated as no gap: no rest inserted
create_midi.ONSET_MERGE_TOLERANCE = 1      # n프레임 차로 눌린 동시에 끝나는 화음을 동시에 누른 것으로 병합
# ────────────────────────────────────────────

KEYBOARD_JSON = "./data/keyboard_calibration.json"
COLOR_JSON = "./data/color_calibration.json"
EVENTS_JSON = "./data/note_events.json"
OUTPUT_MIDI = "./output/output.mid"

calibration.run_calibration_wizard(
    video_path=VIDEO,
    keyboard_json_path=KEYBOARD_JSON,
    color_json_path=COLOR_JSON,
)

frame_check.process_video(
    video_path=VIDEO,
    keyboard_json_path=KEYBOARD_JSON,
    color_json_path=COLOR_JSON,
    events_out=EVENTS_JSON,
)

create_midi.generate_midi(
    events_json=EVENTS_JSON,
    output_midi=OUTPUT_MIDI,
    bpm=BPM,
)

print("\nDone.")