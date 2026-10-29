"""The Alarm chime: a short two-tone WAV the assistant makes itself and serves from
`/staff/alarm/chime.wav`. Generated, so nothing is fetched and no recording's licence
applies (ADR-0006, ADR-0007)."""

from __future__ import annotations

import functools
import io
import math
import struct
import wave

RATE = 8000
# Two falling notes (A5, E5), each fading out.
NOTES = ((880.0, 0.3), (659.25, 0.45))


@functools.cache
def chime_wav() -> bytes:
    frames = bytearray()
    for frequency, seconds in NOTES:
        count = int(RATE * seconds)
        for i in range(count):
            envelope = (1 - i / count) ** 2
            sample = 0.6 * envelope * math.sin(2 * math.pi * frequency * i / RATE)
            frames += struct.pack("<h", int(sample * 32767))
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(bytes(frames))
    return out.getvalue()
