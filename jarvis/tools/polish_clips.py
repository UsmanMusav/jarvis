"""
Финальная обработка голосовых клипов: лёгкое затухание по краям + паузы,
чтобы при воспроизведении не было щелчков и обрывов.

Идемпотентно: повторный запуск не портит файлы (ориентируется на тишину по краям).

Запуск:  python tools/polish_clips.py [папка ...]
"""
from __future__ import annotations

import array
import sys
import wave
from pathlib import Path

HEAD_MS = 40       # тишина в начале
TAIL_MS = 150      # тишина в конце
FADE_IN_MS = 12
FADE_OUT_MS = 45


def process(path: Path) -> str:
    with wave.open(str(path), "rb") as w:
        nch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        return "пропуск (не 16 бит)"

    d = array.array("h")
    d.frombytes(raw)
    if nch > 1:
        d = array.array("h", [int(sum(d[i:i + nch]) / nch) for i in range(0, len(d), nch)])

    head = int(sr * HEAD_MS / 1000)
    tail = int(sr * TAIL_MS / 1000)

    # уже обработан? (тишина нужной длины по краям)
    quiet = lambda seg: all(abs(v) < 40 for v in seg)
    if len(d) > head + tail and quiet(d[:head]) and quiet(d[-tail:]):
        return "уже обработан"

    fin = int(sr * FADE_IN_MS / 1000)
    fout = int(sr * FADE_OUT_MS / 1000)
    for i in range(min(fin, len(d))):
        d[i] = int(d[i] * (i / fin))
    for i in range(min(fout, len(d))):
        j = len(d) - 1 - i
        d[j] = int(d[j] * (i / fout))

    out = array.array("h", [0] * head) + d + array.array("h", [0] * tail)

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(out.tobytes())
    return f"{len(out) / sr:.2f} c"


def main(dirs):
    total = 0
    for d in dirs:
        p = Path(d)
        if not p.exists():
            continue
        print(f"--- {p} ---")
        for f in sorted(p.glob("*.wav")):
            print(f"  {f.name:<16} {process(f)}")
            total += 1
    print(f"\nОбработано файлов: {total}")


if __name__ == "__main__":
    args = sys.argv[1:] or ["assets/voice_ru", "assets/voice_en"]
    main(args)
