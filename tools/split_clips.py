"""
Нарезка пакетной озвучки на отдельные клипы по паузам между фразами.
Чистый Python, без внешних зависимостей (модуль wave + audioop-замена на срезах).

Использование:
    python tools/split_clips.py <файл.wav> <кол-во_фраз> <выходная_папка> ключ1 ключ2 ...
"""
from __future__ import annotations

import array
import math
import sys
import wave
from pathlib import Path


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        nch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise SystemExit(f"{path}: поддерживается только 16-бит PCM (здесь {sw * 8} бит)")
    data = array.array("h")
    data.frombytes(raw)
    if nch > 1:  # в моно
        data = array.array("h", [int(sum(data[i:i + nch]) / nch) for i in range(0, len(data), nch)])
    return data, sr, nch, sw


def rms_envelope(data, sr, win_ms=10):
    win = max(1, int(sr * win_ms / 1000))
    out = []
    for i in range(0, len(data) - win, win):
        s = 0
        chunk = data[i:i + win]
        for v in chunk:
            s += v * v
        out.append(math.sqrt(s / win))
    return out, win


def find_gaps(env, win, sr, thresh):
    """Возвращает участки тишины: (начало_кадр, конец_кадр, длительность_сек)."""
    gaps, start = [], None
    for i, v in enumerate(env):
        if v < thresh:
            if start is None:
                start = i
        else:
            if start is not None:
                gaps.append((start * win, i * win, (i - start) * win / sr))
                start = None
    if start is not None:
        gaps.append((start * win, len(env) * win, (len(env) - start) * win / sr))
    return gaps


def trim(data, sr, thresh, pad_ms=70):
    env, win = rms_envelope(data, sr)
    first, last = 0, len(env) - 1
    while first < len(env) and env[first] < thresh:
        first += 1
    while last > first and env[last] < thresh:
        last -= 1
    pad = int(sr * pad_ms / 1000)
    a = max(0, first * win - pad)
    b = min(len(data), (last + 1) * win + pad)
    return data[a:b]


def write_wav(path, data, sr, sw=2):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(sw)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def split(path, count, outdir, keys, verbose=True):
    data, sr, nch, sw = read_wav(path)
    env, win = rms_envelope(data, sr)
    peak = max(env) if env else 1.0
    thresh = max(peak * 0.035, 60.0)

    gaps = find_gaps(env, win, sr, thresh)
    # отбрасываем тишину в самом начале и в самом конце
    inner = [g for g in gaps if g[0] > win * 3 and g[1] < len(data) - win * 3]
    inner.sort(key=lambda g: -g[2])
    cuts = sorted(g for g in inner[:count - 1])

    if verbose:
        print(f"\n{Path(path).name}: {len(data)/sr:.2f} c, порог {thresh:.0f}, "
              f"пауз найдено {len(inner)}, нужно разрезов {count - 1}")
        for g in inner[:count + 2]:
            print(f"    пауза {g[2]*1000:6.0f} мс на {g[0]/sr:6.2f} c"
                  + ("   <- РЕЗ" if g in cuts else ""))

    if len(cuts) < count - 1:
        print(f"  !! найдено только {len(cuts)} пауз вместо {count - 1}")
        return []

    bounds = [0] + [int((c[0] + c[1]) / 2) for c in cuts] + [len(data)]
    made = []
    for i in range(count):
        seg = data[bounds[i]:bounds[i + 1]]
        seg = trim(seg, sr, thresh)
        key = keys[i] if i < len(keys) else f"part{i}"
        out = Path(outdir) / f"{key}.wav"
        write_wav(out, seg, sr, sw)
        made.append((key, len(seg) / sr))
        if verbose:
            print(f"    -> {out.name:<14} {len(seg)/sr:5.2f} c")
    return made


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)
    split(sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4:])
