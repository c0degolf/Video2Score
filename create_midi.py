import json
import mido
from mido import Message, MetaMessage, MidiFile, MidiTrack

TICKS_PER_BEAT = 480

def _split_by_hand(events):
    # note_off inherits the hand of its matching note_on so a pair stays on one track
    open_hand = {}
    left, right = [], []
    for ev in sorted(events, key=lambda e: e["time"]):
        midi = ev["midi"]
        if ev["type"] == "note_on":
            hand = ev.get("hand", "left")
            open_hand[midi] = hand
        else:
            hand = open_hand.pop(midi, ev.get("hand", "left"))
        (left if hand == "left" else right).append(ev)
    return left, right


def _write_track(track, events, ticks_per_second):
    last_time = 0
    for ev in events:
        ticks = max(0, round((ev["time"] - last_time) * ticks_per_second))
        track.append(Message(ev["type"], note=ev["midi"], velocity=64, time=ticks))
        last_time = ev["time"]


def generate_midi(events_json="note_events.json", output_midi="output.mid", bpm=120, time_signature=(4, 4)):
    with open(events_json, "r", encoding="utf-8") as f:
        events = json.load(f)

    events.sort(key=lambda x: x["time"])

    left_events, right_events = _split_by_hand(events)

    mid = MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)

    meta_track = MidiTrack()
    mid.tracks.append(meta_track)
    
    numerator, denominator = time_signature
    meta_track.append(MetaMessage("time_signature", numerator=numerator,
                                  denominator=denominator, time=0))
    meta_track.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

    track_right = MidiTrack()
    track_right.append(MetaMessage("track_name", name="Right Hand", time=0))
    mid.tracks.append(track_right)

    track_left = MidiTrack()
    track_left.append(MetaMessage("track_name", name="Left Hand", time=0))
    mid.tracks.append(track_left)

    ticks_per_second = TICKS_PER_BEAT * bpm / 60
    _write_track(track_right, right_events, ticks_per_second)
    _write_track(track_left, left_events, ticks_per_second)
    
    mid.save(output_midi)
    print(f"MIDI saved to {output_midi} "
          f"(BPM: {bpm}, Time Signature: {numerator}/{denominator}, "
          f"Left notes: {len(left_events)}, Right notes: {len(right_events)})")


if __name__ == "__main__":
    generate_midi()