"""
Module to generate approximate coordinates (x, y, w, h) for 88 keys (A0 to C8, MIDI 21 to 108).

Since key proportions vary slightly for each video, the generated coordinates here 
are intended to be visually fine-tuned in the adjustment UI of calibration.py.
"""

WHITE_KEY_COUNT = 52
MIDI_MIN = 21   # A0
NUM_KEYS = 88
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def midi_to_key_index(midi_note: int) -> int:
    """MIDI note number -> 0-based row index in 88-key press matrices."""
    return midi_note - MIDI_MIN


def is_black_key(midi_note: int) -> bool:
    """Whether the MIDI note number is a black key."""
    return midi_note % 12 in (1, 3, 6, 8, 10)


def midi_to_name(midi_note: int) -> str:
    """MIDI note number -> note name (e.g. 60 -> C4)."""
    name = NOTE_NAMES[midi_note % 12]
    octave = midi_note // 12 - 1
    return f"{name}{octave}"


def generate_88_key_layout(x_left, x_right, y_top, white_h,
                            black_h_ratio=0.62, black_w_ratio=0.6):
    """
    Generates coordinates (x, y, w, h) for small detection rectangles inside each of the 88 keys.

    Parameters
    ----------
    x_left, x_right : Left/right x pixel coordinates of the keyboard region (based on white keys)
    y_top : Top y coordinate of the keyboard (top of white keys)
    white_h : Vertical length of white keys (pixels)
    black_h_ratio : Vertical length of black keys = white_h * ratio
    black_w_ratio : Horizontal width of black keys = white key width * ratio

    Returns
    -------
    list[dict] : {midi, name, is_black, x, y, w, h}
    """
    total_width = x_right - x_left
    white_w = total_width / WHITE_KEY_COUNT
    black_h = white_h * black_h_ratio
    black_w = white_w * black_w_ratio

    keys = []
    white_index = 0  # 0 ~ 51, white key index from left

    # White key detection area ratios and vertical relative position (near bottom 85%, to avoid black keys)
    white_det_w_ratio = 0.4
    white_det_h_ratio = 0.15
    white_det_y_center_ratio = 0.85

    # Black key detection area ratios and vertical relative position (near bottom 75%)
    black_det_w_ratio = 0.5
    black_det_h_ratio = 0.15
    black_det_y_center_ratio = 0.75

    for midi in range(21, 109):  # A0 ~ C8
        black = is_black_key(midi)
        if not black:
            # White key original region and center
            x_full = x_left + white_index * white_w
            cx = x_full + white_w / 2
            cy = y_top + white_h * white_det_y_center_ratio
            
            w = max(2, round(white_w * white_det_w_ratio))
            h = max(2, round(white_h * white_det_h_ratio))
            x = round(cx - w / 2)
            y = round(cy - h / 2)

            keys.append({
                'midi': midi,
                'name': midi_to_name(midi),
                'is_black': False,
                'x': x, 'y': y,
                'w': w, 'h': h,
            })
            white_index += 1
        else:
            # Black key original center line (applying standard piano layout offsets except G#)
            note_mod = midi % 12
            offset = 0.0
            shift_ratio = 0.08  # Shift ratio relative to white key width
            if note_mod == 1:    # C# (left)
                offset = -white_w * shift_ratio
            elif note_mod == 3:  # D# (right)
                offset = white_w * shift_ratio
            elif note_mod == 6:  # F# (left)
                offset = -white_w * shift_ratio
            elif note_mod == 8:  # G# (center)
                offset = 0.0
            elif note_mod == 10: # A# (right)
                offset = white_w * shift_ratio

            cx = x_left + white_index * white_w + offset
            cy = y_top + black_h * black_det_y_center_ratio

            w = max(2, round(black_w * black_det_w_ratio))
            h = max(2, round(black_h * black_det_h_ratio))
            x = round(cx - w / 2)
            y = round(cy - h / 2)

            keys.append({
                'midi': midi,
                'name': midi_to_name(midi),
                'is_black': True,
                'x': x, 'y': y,
                'w': w, 'h': h,
            })

    return keys