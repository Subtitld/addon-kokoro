"""Speak real lines with the frozen add-on, as Subtitld does.

    python tools/smoke_synth.py dist/kokoro-addon/kokoro-addon

Downloads the model on the first line (about 330 MB with the voices used).
Fails on a line that errors, writes no audio, or takes more than the timeout:
1.0.6 hung on its first English line because spaCy's English model was
missing from the bundle and spaCy tried to download it.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import wave

LINES = [
    ('kokoro-af-heart', 'Hello there. It is 9:30, and the meeting starts in five minutes.'),
    ('kokoro-bm-george', 'Good evening, and welcome to the programme.'),
    ('kokoro-ef-dora', 'Todos los seres humanos nacen libres e iguales.'),
    ('kokoro-jf-alpha', 'すべての人間は、生まれながらにして自由である。'),
    ('kokoro-zf-xiaobei', '人人生而自由，在尊严和权利上一律平等。'),
]
TIMEOUT = 900


def main(binary: str) -> int:
    out = tempfile.mkdtemp(prefix='kokoro-smoke-')
    env = dict(os.environ, SUBTITLD_TEMP_DIR=out)
    proc = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=sys.stderr, text=True, env=env)
    timer = threading.Timer(TIMEOUT, proc.kill)
    timer.start()
    try:
        hello = json.loads(proc.stdout.readline())
        assert hello.get('type') == 'hello', hello
        for n, (voice, text) in enumerate(LINES):
            path = os.path.join(out, f'{n}.wav')
            proc.stdin.write(json.dumps({'type': 'tts.synthesize', 'id': str(n), 'params': {
                'text': text, 'voice': voice, 'output_path': path}}) + '\n')
            proc.stdin.flush()
            while True:
                line = proc.stdout.readline()
                if not line:
                    raise SystemExit(f'{voice}: the add-on exited (or timed out) without an answer')
                try:
                    frame = json.loads(line)
                except json.JSONDecodeError:   # anything but JSON on stdout breaks the host
                    raise SystemExit(f'{voice}: not a protocol frame on stdout: {line[:300]!r}')
                if frame.get('id') != str(n) or frame.get('type') == 'progress':
                    continue
                if frame.get('type') != 'result':
                    raise SystemExit(f'{voice}: {frame}')
                break
            with wave.open(path) as w:
                seconds = w.getnframes() / w.getframerate()
            assert seconds > 1.0, f'{voice}: only {seconds:.2f} s of audio'
            print(f'ok {voice}: {seconds:.2f} s', flush=True)
        proc.stdin.write(json.dumps({'type': 'shutdown'}) + '\n')
        proc.stdin.flush()
        proc.wait(timeout=30)
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
