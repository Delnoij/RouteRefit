# SPDX-License-Identifier: GPL-3.0-only
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import fitdecode
from route_formats import fit, make_gpx
from gpx_core import Track


def frame(name, **data):
    return SimpleNamespace(
        name=name,
        frame_type=fitdecode.FIT_FRAME_DATA,
        get_value=lambda key, fallback=None: data.get(key, fallback),
    )


def record(lat, time):
    return frame(
        "record",
        position_lat=round(lat / 180 * 2**31),
        position_long=round(6 / 180 * 2**31),
        altitude=100,
        timestamp=time,
    )


class FitActivity(unittest.TestCase):
    def convert(self, frames):
        with patch.object(fitdecode, "FitReader") as reader:
            reader.return_value.__enter__.return_value = frames
            result = Track(fit(b"synthetic", "test"))
            self.assertEqual(reader.call_args.kwargs["check_crc"], fitdecode.CrcCheck.RAISE)
            return result

    def test_timer_stops_at_same_position_do_not_cut_the_route(self):
        frames = [
            record(50, 1000),
            record(50.001, 1060),
            frame("event", event="timer", event_type="stop"),
            record(50.001, 1080),
            frame("event", event="timer", event_type="stop_all"),
            record(50.001, 1100),
            record(50.002, 1160),
            frame("session", sport="cycling"),
        ]
        track = self.convert(frames)
        self.assertEqual(len(track.segments), 1)
        self.assertEqual(track.stats()["points"], 5)
        self.assertEqual(track.activity_mode, "bike")
        self.assertEqual(track.stats()["seconds"], 160)

    def test_real_recording_gap_stays_separate_and_all_samples_survive(self):
        frames = [
            record(50, 1000),
            record(50.001, 1060),
            frame("event", event=0, event_type=1),
            record(50.02, 2060),
            record(50.021, 2120),
            frame("sport", sport="cycling"),
        ]
        track = self.convert(frames)
        self.assertEqual(len(track.segments), 2)
        self.assertEqual(track.stats()["points"], 4)
        self.assertEqual(track.activity_mode, "bike")

    def test_mixed_sessions_do_not_infer_one_activity(self):
        track = self.convert(
            [
                record(50, 1000),
                record(50.001, 1060),
                frame("session", sport="cycling"),
                frame("session", sport="running"),
            ]
        )
        self.assertIsNone(track.activity_mode)

    def test_single_recorded_sample_between_gaps_is_not_discarded(self):
        raw = make_gpx("test", [[(6, 50, 100, None)], [(6, 51, 100, None), (6, 51.001, 100, None)]])
        track = Track(raw)
        self.assertEqual(track.stats()["points"], 3)
        self.assertEqual(len(track.segments), 2)
        with self.assertRaises(ValueError):
            make_gpx("not a route", [[(6, 50, 100, None)]])


if __name__ == "__main__":
    unittest.main()
