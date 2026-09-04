import json
from collections import Counter, defaultdict
from fractions import Fraction
from music21 import chord, clef, instrument, note, pitch, stream, tempo, meter

DURATION_MAP = {
    3:0.25, 4:0.25, 5: 0.25, 6: 0.25, 7: 0.25,
    8: 0.5, 9: 0.5, 10: 0.5, 11: 0.5, 12: 0.5, 13: 0.5, 14: 0.5,
    19: 1.0, 20: 1.0, 21: 1.0, 22: 1.0, 23: 1.0, 24: 1.0, 25: 1.0, 26: 1.0, 27: 1.0, 28: 1.0,
    32: 1.5, 33: 1.5, 34: 1.5,
    42: 2.0, 43: 2.0, 44: 2.0, 45: 2.0, 46: 2.0, 47: 2.0,
    54: 2.5, 55: 2.5, 56: 2.5, 57: 2.5,
    66: 3.0, 67: 3.0,
    86: 4.0, 87: 4.0, 88: 4.0, 89: 4.0, 990: 4.0,
    109: 5.0,
    264: 12.0,
}

# frame -> debug pitch, so a quantize miss is recognizable in the debug track
DEBUG_NOTE = {
    10: 100, 11: 101, 12: 102,
    19: 103, 20: 104,
    27: 105, 28: 106, 29: 107,
}

CLEF_BY_HAND = {"right": clef.TrebleClef, "left": clef.BassClef}

_SORTED_FRAMES = sorted(DURATION_MAP)


def quantize_frames(frames, miss_grid):
    """frame count -> beat (quarterLength). Exact hits use DURATION_MAP;
    misses interpolate between the nearest known anchors and snap to MISS_GRID."""
    if frames in DURATION_MAP:
        return Fraction(DURATION_MAP[frames]).limit_denominator(64), False, None

    lo = max((f for f in _SORTED_FRAMES if f <= frames), default=None)
    hi = min((f for f in _SORTED_FRAMES if f >= frames), default=None)

    if lo is None:
        ratio = DURATION_MAP[hi] / hi
    elif hi is None or lo == hi:
        ratio = DURATION_MAP[lo] / lo
    else:
        ratio = DURATION_MAP[lo] / lo + (DURATION_MAP[hi] / hi - DURATION_MAP[lo] / lo) * (
            (frames - lo) / (hi - lo)
        )

    raw_beat = frames * ratio
    steps = round(raw_beat / miss_grid)
    quantized = max(Fraction(steps) * miss_grid, miss_grid)

    info = {
        "frames": frames,
        "raw": raw_beat,
        "quantized": float(quantized),
        "error": float(quantized - Fraction(raw_beat).limit_denominator(4096)),
        "lo": lo,
        "hi": hi,
    }

    return quantized, True, info


def preprocess_notes(notes, onset_tolerance):
    """Merge onsets that land within `onset_tolerance` frames of each other into
    a single chord attack (fixes color-detection jitter where notes meant to be
    struck together register 1-2 frames apart). Snaps each cluster to its
    earliest start and recomputes duration_frame from that start."""
    if not notes:
        return notes

    notes_sorted = sorted(notes, key=lambda n: n["start"])
    clusters = [[notes_sorted[0]]]

    for n in notes_sorted[1:]:
        if n["start"] - clusters[-1][-1]["start"] <= onset_tolerance:
            clusters[-1].append(n)
        else:
            clusters.append([n])

    merged = []
    for cluster in clusters:
        canonical_start = min(n["start"] for n in cluster)
        for n in cluster:
            merged.append({
                "midi": n["midi"],
                "start": canonical_start,
                "end": n["end"],
                "duration_frame": n["end"] - canonical_start,
            })

    return merged


def group_chords(notes):
    """Group notes sharing the same start frame into chords, in onset order."""
    groups = []

    for n in sorted(notes, key=lambda x: x["start"]):
        entry = {"midi": n["midi"], "duration_frame": n["duration_frame"]}

        if groups and groups[-1]["start"] == n["start"]:
            groups[-1]["notes"].append(entry)
        else:
            groups.append({"start": n["start"], "notes": [entry]})

    return groups


def _named_part(name):
    part = stream.Part()
    part.partName = name
    inst = instrument.Instrument()
    inst.partName = name
    part.insert(0, inst)
    return part


def _debug_entry(frames, beat, miss):
    """A debug-track entry: a marker note on a quantize miss, a rest otherwise.
    Always the same length as the corresponding melody entry, so both tracks
    stay aligned beat-for-beat."""
    if miss:
        return note.Note(DEBUG_NOTE.get(frames, 108), quarterLength=beat)
    return note.Rest(quarterLength=beat)


def build_hand_tracks(notes, hand, melody_name, debug_name, miss_grid, rest_ignore_frames, onset_merge_tolerance, fps):
    miss_counter = Counter()
    miss_details = defaultdict(list)

    notes = preprocess_notes(notes, onset_merge_tolerance)
    groups = group_chords(notes)

    melody = _named_part(melody_name)
    melody.append(CLEF_BY_HAND[hand]())

    debug = _named_part(debug_name)

    if not groups:
        melody.append(note.Rest(quarterLength=1))
        return melody, debug, 0, miss_counter, miss_details

    prev_end = groups[0]["start"]
    miss_count = 0

    for group in groups:
        rest_frames = group["start"] - prev_end

        if rest_frames > rest_ignore_frames:
            beat, miss, info = quantize_frames(rest_frames, miss_grid)

            if miss:
                info["at_frame"] = group["start"]
                miss_counter[rest_frames] += 1
                miss_details[rest_frames].append(info)
            miss_count += miss
            melody.append(note.Rest(quarterLength=beat))
            debug.append(_debug_entry(rest_frames, beat, miss))

        chord_frames = max(n["duration_frame"] for n in group["notes"])
        beat, miss, info = quantize_frames(chord_frames, miss_grid)

        if miss:
            info["at_frame"] = group["start"]
            miss_counter[chord_frames] += 1
            miss_details[chord_frames].append(info)
        miss_count += miss

        pitches = [pitch.Pitch(midi=n["midi"]) for n in group["notes"]]
        el = note.Note(pitches[0]) if len(pitches) == 1 else chord.Chord(pitches)
        el.quarterLength = beat

        melody.append(el)
        debug.append(_debug_entry(chord_frames, beat, miss))

        prev_end = group["start"] + chord_frames

    return melody, debug, miss_count, miss_counter, miss_details

def _print_miss_log(counter, details):
    # 정렬 기준을 빈도(cnt)가 아닌 프레임 수(frame)의 오름차순으로 변경
    for frame in sorted(counter.keys()):
        cnt = counter[frame]
        print(f"  {frame:>3} frames : {cnt} times")
        for d in details[frame]:
            print(
                f"       raw={d['raw']:.3f} beat"
                f" -> {d['quantized']:.3f}"
                f"  error={d['error']:+.4f}"
                f"   ({d['lo']}~{d['hi']} frame interpolation)"
                f"   at frame {d['at_frame']}"
            )


def generate_midi(
    events_json="./data/note_events.json",
    output_midi="./output/output.mid",
    time_signature='4/4',
    bpm=120,
    miss_grid=Fraction(1, 16),
    rest_ignore_frames=1,
    onset_merge_tolerance=1,
    fps=30  # actual capture fps; used only to convert log frame numbers to seconds
):
    with open(events_json, encoding="utf-8") as f:
        data = json.load(f)

    right_melody, right_debug, right_miss, right_counter, right_details = build_hand_tracks(
        data["right_notes"], "right", "Right Hand", "Right Debug", 
        miss_grid, rest_ignore_frames, onset_merge_tolerance, fps
    )
    left_melody, left_debug, left_miss, left_counter, left_details = build_hand_tracks(
        data["left_notes"], "left", "Left Hand", "Left Debug",
        miss_grid, rest_ignore_frames, onset_merge_tolerance, fps
    )

    score = stream.Score()
    score.insert(0, meter.TimeSignature(value=time_signature))
    score.insert(0, tempo.MetronomeMark(number=bpm))
    score.insert(0, right_melody)
    score.insert(0, right_debug)
    score.insert(0, left_melody)
    score.insert(0, left_debug)

    score.write("midi", fp=output_midi)

    print()
    print("========== RESULT ==========")
    print(f"MIDI : {output_midi}")
    print()

    print(f"Right Quantize Miss : {right_miss}")
    _print_miss_log(right_counter, right_details)

    print()

    print(f"Left Quantize Miss : {left_miss}")
    _print_miss_log(left_counter, left_details)

if __name__ == "__main__":
    generate_midi()