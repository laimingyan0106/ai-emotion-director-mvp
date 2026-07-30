import math
import struct
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from app.services.audio import analyze_audio_file


def write_fixture(
    path: Path,
    *,
    frequency: float,
    pulsed: bool,
    duration: float = 4.0,
    sample_rate: int = 22050,
) -> None:
    frames = bytearray()
    for index in range(round(duration * sample_rate)):
        second = index / sample_rate
        envelope = 1.0
        if pulsed:
            envelope = 1.0 if int(second * 4) % 2 == 0 else 0.05
        sample = int(
            32767
            * 0.45
            * envelope
            * math.sin(2 * math.pi * frequency * second)
        )
        frames.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(frames)


class AudioAnalysisTest(unittest.TestCase):
    def test_two_fixed_songs_are_distinct_and_repeatable(self):
        with tempfile.TemporaryDirectory(prefix="emotion-audio-fixtures-") as directory:
            low = Path(directory) / "low.wav"
            high = Path(directory) / "high-pulsed.wav"
            write_fixture(low, frequency=220, pulsed=False)
            write_fixture(high, frequency=880, pulsed=True)

            started = time.perf_counter()
            low_result = analyze_audio_file(low)
            high_result = analyze_audio_file(high)
            elapsed = time.perf_counter() - started

            self.assertFalse(low_result["degraded"])
            self.assertFalse(high_result["degraded"])
            self.assertNotEqual(
                low_result["source_sha256"],
                high_result["source_sha256"],
            )
            self.assertGreater(
                high_result["spectral_centroid"]["mean_hz"],
                low_result["spectral_centroid"]["mean_hz"] * 2,
            )
            self.assertNotEqual(
                high_result["energy_curve"],
                low_result["energy_curve"],
            )
            self.assertLess(elapsed, 30)

            repeated = analyze_audio_file(low)
            for result in (low_result, repeated):
                result.pop("processing_ms")
            self.assertEqual(repeated, low_result)

    def test_missing_ffmpeg_is_an_explicit_degraded_result(self):
        with tempfile.TemporaryDirectory(prefix="emotion-audio-no-ffmpeg-") as directory:
            source = Path(directory) / "compressed.m4a"
            source.write_bytes(b"not-a-real-compressed-file")
            with patch("app.services.audio._resolve_ffmpeg", return_value=None):
                result = analyze_audio_file(source)
            self.assertTrue(result["degraded"])
            self.assertIn(
                "ffmpeg_unavailable_for_compressed_audio",
                result["degraded_reason"],
            )


if __name__ == "__main__":
    unittest.main()
