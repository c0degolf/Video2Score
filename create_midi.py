import json
from collections import Counter, defaultdict
from fractions import Fraction
from music21 import chord, clef, instrument, note, pitch, stream, tempo, meter

# Standard frame and duration mapping table
DURATION_MAP = {
    5: 0.25, 6: 0.25, 7: 0.25, 8: 0.25,
    11: 0.5, 12: 0.5, 13: 0.5, 14: 0.5, 15: 0.5, 16: 0.5,
    24: 1.0, 25: 1.0, 26: 1.0, 27: 1.0, 28: 1.0,
    40: 1.5, 41: 1.5,
    52: 2.0, 53: 2.0, 54: 2.0, 55: 2.0, 56: 2.0,
    101: 4.0, 102: 4.0, 103: 4.0,
}

_SORTED_FRAMES = sorted(DURATION_MAP)

def get_clef_for_voice(voice_name):
    if "left" in voice_name.lower():
        return clef.BassClef()
    return clef.TrebleClef()

def quantize_frames(frames, miss_grid, fps=30):
    if frames in DURATION_MAP:
        return Fraction(DURATION_MAP[frames]).limit_denominator(64), False, None

    # Find the closest standard frame to avoid linear distortion
    closest_frame = min(_SORTED_FRAMES, key=lambda f: abs(f - frames))
    base_ratio = DURATION_MAP[closest_frame] / closest_frame
    
    raw_beat = frames * base_ratio
    steps = round(raw_beat / miss_grid)
    quantized = max(Fraction(steps) * miss_grid, miss_grid)

    info = {
        "frames": frames,
        "time_sec": frames / fps,  # Calculate time in seconds
        "raw": raw_beat,
        "quantized": float(quantized),
        "error": float(quantized - Fraction(raw_beat).limit_denominator(4096)),
        "closest_standard": closest_frame,
    }

    return quantized, True, info

def preprocess_notes(notes, onset_tolerance):
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
    groups = []
    for n in sorted(notes, key=lambda x: x["start"]):
        entry = {"midi": n["midi"], "duration_frame": n["duration_frame"]}
        if groups and groups[-1]["start"] == n["start"]:
            groups[-1]["notes"].append(entry)
        else:
            groups.append({"start": n["start"], "notes": [entry]})
    return groups

def _named_part(name):
    part = stream.Part(partName=name)
    part.insert(0, instrument.Instrument(partName=name))
    return part

def build_voice_tracks(notes, voice_name, miss_grid, rest_ignore_frames, onset_merge_tolerance, fps):
    miss_counter = Counter()
    miss_details = defaultdict(list)

    notes = preprocess_notes(notes, onset_merge_tolerance)
    groups = group_chords(notes)

    melody_name = voice_name.replace("_", " ").title()

    melody = _named_part(melody_name)
    melody.append(get_clef_for_voice(voice_name))

    if not groups:
        melody.append(note.Rest(quarterLength=1))
        return melody, 0, miss_counter, miss_details

    prev_end = groups[0]["start"]
    miss_count = 0

    for group in groups:
        rest_frames = group["start"] - prev_end

        if rest_frames > rest_ignore_frames:
            beat, miss, info = quantize_frames(rest_frames, miss_grid, fps)
            if miss:
                info["at_frame"] = group["start"]
                info["at_time_sec"] = group["start"] / fps  # Calculate time in seconds for event start position
                miss_counter[rest_frames] += 1
                miss_details[rest_frames].append(info)
            miss_count += miss
            melody.append(note.Rest(quarterLength=beat))

        chord_frames = max(n["duration_frame"] for n in group["notes"])
        beat, miss, info = quantize_frames(chord_frames, miss_grid, fps)

        if miss:
            info["at_frame"] = group["start"]
            info["at_time_sec"] = group["start"] / fps  # Calculate time in seconds for event start position
            miss_counter[chord_frames] += 1
            miss_details[chord_frames].append(info)
        miss_count += miss

        pitches = [pitch.Pitch(midi=n["midi"]) for n in group["notes"]]
        el = note.Note(pitches[0]) if len(pitches) == 1 else chord.Chord(pitches)
        el.quarterLength = beat

        melody.append(el)

        prev_end = group["start"] + chord_frames

    return melody, miss_count, miss_counter, miss_details

def _print_miss_log(counter, details):
    for frame in sorted(counter.keys()):
        cnt = counter[frame]
        print(f"  {frame:>3} frames : {cnt} times")
        for d in details[frame]:
            # Display both frame and time (seconds) for 'at frame' location
            print(
                f"       [Duration: {d['frames']}]"
                f" raw={d['raw']:.3f} beat"
                f" -> quantized={d['quantized']:.3f}"
                f"  error={d['error']:+.4f}"
                f"   at frame {d['at_frame']} ({d['at_time_sec']//60:.0f}m {d['at_time_sec']%60:.2f}s)"
            )

def generate_midi(
    events_json="./data/note_events.json",
    output_midi="./output/output.mid",
    time_signature='4/4',
    bpm=120,
    miss_grid=Fraction(1, 16),
    rest_ignore_frames=1,
    onset_merge_tolerance=1,
    fps=30,  # Default frames per second (adjust to 60 if needed)
):
    with open(events_json, encoding="utf-8") as f:
        data = json.load(f)

    score = stream.Score()
    score.insert(0, meter.TimeSignature(value=time_signature))
    score.insert(0, tempo.MetronomeMark(number=bpm))

    print()
    print("========== RESULT ==========")
    print(f"MIDI : {output_midi}")
    print()

    for key, notes_list in data.items():
        if not key.endswith("_notes"):
            continue
        voice_name = key[:-6]
        
        melody, miss_count, counter, details = build_voice_tracks(
            notes_list, voice_name, miss_grid, rest_ignore_frames, onset_merge_tolerance, fps
        )
        
        score.insert(0, melody)

        print(f"{voice_name.replace('_', ' ').title()} Quantize Miss : {miss_count}")
        _print_miss_log(counter, details)
        print()

    score.write("midi", fp=output_midi)
    print(f"MIDI generation complete. Saved to {output_midi}")

if __name__ == "__main__":
    generate_midi()