import json
from fractions import Fraction
from music21 import chord, clef, instrument, note, pitch, stream, tempo, meter

DURATION_MAP = {
    1: 0.25, 2: 0.25,
    3: 0.5, 4: 0.5, 5: 0.5,
    6: 0.5, 7: 0.5,
    8: 1.0, 9: 1.0, 10: 1.0,
    11: 1.0, 12: 1.0,
    13: 1.5, 14: 1.5,
    17: 2.0, 18: 2.0, 19: 2.0, 20: 2.0,
    22: 2.5, 27: 2.5, 28: 2.5, 29: 2.5,
}

# frame -> debug pitch, so a quantize miss is recognizable in the debug track
DEBUG_NOTE = {
    10: 100, 11: 101, 12: 102,
    19: 103, 20: 104,
    27: 105, 28: 106, 29: 107,
}

MISS_GRID = Fraction(1, 16)
REST_IGNORE_FRAMES = 2
ONSET_MERGE_TOLERANCE = 1 

CLEF_BY_HAND = {"right": clef.TrebleClef, "left": clef.BassClef}

_SORTED_FRAMES = sorted(DURATION_MAP)


def quantize_frames(frames):
    """frame count -> beat (quarterLength). Exact hits use DURATION_MAP;
    misses interpolate between the nearest known anchors and snap to MISS_GRID."""
    if frames in DURATION_MAP:
        return Fraction(DURATION_MAP[frames]).limit_denominator(64), False

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

    beat = frames * ratio
    steps = round(beat / MISS_GRID)
    print(f"Quantize Miss frames={frames} beat={float(beat):.3f}")
    return max(Fraction(steps) * MISS_GRID, MISS_GRID), True


def preprocess_notes(notes, onset_tolerance=ONSET_MERGE_TOLERANCE):
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


def build_hand_tracks(notes, hand, melody_name, debug_name):
    notes = preprocess_notes(notes)
    groups = group_chords(notes)

    melody = _named_part(melody_name)
    melody.append(CLEF_BY_HAND[hand]())

    debug = _named_part(debug_name)

    if not groups:
        melody.append(note.Rest(quarterLength=1))
        return melody, debug, 0

    prev_end = groups[0]["start"]
    miss_count = 0

    for group in groups:
        rest_frames = group["start"] - prev_end

        if rest_frames > REST_IGNORE_FRAMES:
            beat, miss = quantize_frames(rest_frames-1)
            miss_count += miss
            melody.append(note.Rest(quarterLength=beat))
            debug.append(_debug_entry(rest_frames, beat, miss))

        chord_frames = max(n["duration_frame"] for n in group["notes"])
        beat, miss = quantize_frames(chord_frames)
        miss_count += miss

        pitches = [pitch.Pitch(midi=n["midi"]) for n in group["notes"]]
        el = note.Note(pitches[0]) if len(pitches) == 1 else chord.Chord(pitches)
        el.quarterLength = beat

        melody.append(el)
        debug.append(_debug_entry(chord_frames, beat, miss))

        prev_end = group["start"] + chord_frames

    return melody, debug, miss_count


def generate_midi(
    events_json="./data/note_events.json",
    output_midi="./output/output.mid",
    time_signature='4/4',
    bpm=120,
):
    with open(events_json, encoding="utf-8") as f:
        data = json.load(f)

    right_melody, right_debug, right_miss = build_hand_tracks(
        data["right_notes"], "right", "Right Hand", "Right Debug"
    )
    left_melody, left_debug, left_miss = build_hand_tracks(
        data["left_notes"], "left", "Left Hand", "Left Debug"
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
    print(f"Right Quantize Miss : {right_miss}")
    print(f"Left Quantize Miss  : {left_miss}")


if __name__ == "__main__":
    generate_midi()