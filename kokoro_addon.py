"""Subtitld add-on entry point for Kokoro 82M.

Wraps `kokoro` (PyPI, Apache-2.0). Kokoro is the small / fast end of the
neural-TTS spectrum: ~80 MB model, sub-second per line on a midrange
CPU, no voice cloning. We expose the stock 54 preset voices spread
across 9 BCP-47 language buckets — lang_code 'a' (en-US), 'b' (en-GB),
'e' (es), 'f' (fr), 'h' (hi), 'i' (it), 'j' (ja), 'p' (pt-BR), 'z' (zh).

`KPipeline` is per-language, so we keep a small dict of pipelines
keyed by lang_code and lazy-build them on first use. The model weights
themselves are shared across pipelines so this isn't a memory tax.

API call shape:
    pipeline = KPipeline(lang_code='a')
    for _gs, _ps, audio in pipeline(text, voice='af_heart', speed=1.0):
        wav = audio.numpy()  # float32 mono, 24 000 Hz
        break
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path

log = logging.getLogger('kokoro')
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='[kokoro] %(levelname)s %(message)s')

PROTOCOL = 1
ADDON_ID = 'kokoro'
VERSION = '1.0.4'

# Voice id (with `kokoro-` prefix stripped) → kokoro lang_code, kokoro voice id.
# Mirrors the manifest. Single source of truth for the wrapper, since the
# manifest is loaded for hello-time advertising but we still need the
# lookup at request time.
_VOICE_BY_ID: dict[str, tuple[str, str]] = {
    # American English (lang_code 'a')
    'af_heart':    ('a', 'af_heart'),    'af_alloy':    ('a', 'af_alloy'),
    'af_aoede':    ('a', 'af_aoede'),    'af_bella':    ('a', 'af_bella'),
    'af_jessica':  ('a', 'af_jessica'),  'af_kore':     ('a', 'af_kore'),
    'af_nicole':   ('a', 'af_nicole'),   'af_nova':     ('a', 'af_nova'),
    'af_river':    ('a', 'af_river'),    'af_sarah':    ('a', 'af_sarah'),
    'af_sky':      ('a', 'af_sky'),      'am_adam':     ('a', 'am_adam'),
    'am_echo':     ('a', 'am_echo'),     'am_eric':     ('a', 'am_eric'),
    'am_fenrir':   ('a', 'am_fenrir'),   'am_liam':     ('a', 'am_liam'),
    'am_michael':  ('a', 'am_michael'),  'am_onyx':     ('a', 'am_onyx'),
    'am_puck':     ('a', 'am_puck'),     'am_santa':    ('a', 'am_santa'),
    # British English (lang_code 'b')
    'bf_alice':    ('b', 'bf_alice'),    'bf_emma':     ('b', 'bf_emma'),
    'bf_isabella': ('b', 'bf_isabella'), 'bf_lily':     ('b', 'bf_lily'),
    'bm_daniel':   ('b', 'bm_daniel'),   'bm_fable':    ('b', 'bm_fable'),
    'bm_george':   ('b', 'bm_george'),   'bm_lewis':    ('b', 'bm_lewis'),
    # Japanese (lang_code 'j')
    'jf_alpha':    ('j', 'jf_alpha'),    'jf_gongitsune': ('j', 'jf_gongitsune'),
    'jf_nezumi':   ('j', 'jf_nezumi'),   'jf_tebukuro': ('j', 'jf_tebukuro'),
    'jm_kumo':     ('j', 'jm_kumo'),
    # Mandarin Chinese (lang_code 'z')
    'zf_xiaobei':  ('z', 'zf_xiaobei'),  'zf_xiaoni':   ('z', 'zf_xiaoni'),
    'zf_xiaoxiao': ('z', 'zf_xiaoxiao'), 'zf_xiaoyi':   ('z', 'zf_xiaoyi'),
    'zm_yunjian':  ('z', 'zm_yunjian'),  'zm_yunxi':    ('z', 'zm_yunxi'),
    'zm_yunxia':   ('z', 'zm_yunxia'),   'zm_yunyang':  ('z', 'zm_yunyang'),
    # Spanish (lang_code 'e')
    'ef_dora':     ('e', 'ef_dora'),     'em_alex':     ('e', 'em_alex'),
    'em_santa':    ('e', 'em_santa'),
    # French (lang_code 'f')
    'ff_siwis':    ('f', 'ff_siwis'),
    # Hindi (lang_code 'h')
    'hf_alpha':    ('h', 'hf_alpha'),    'hf_beta':     ('h', 'hf_beta'),
    'hm_omega':    ('h', 'hm_omega'),    'hm_psi':      ('h', 'hm_psi'),
    # Italian (lang_code 'i')
    'if_sara':     ('i', 'if_sara'),     'im_nicola':   ('i', 'im_nicola'),
    # Brazilian Portuguese (lang_code 'p')
    'pf_dora':     ('p', 'pf_dora'),     'pm_alex':     ('p', 'pm_alex'),
    'pm_santa':    ('p', 'pm_santa'),
}


# ---------------------------------------------------------------------------
# Wire helpers
# ---------------------------------------------------------------------------
_write_lock = threading.Lock()


def write_frame(frame: dict) -> None:
    line = json.dumps(frame, ensure_ascii=False)
    with _write_lock:
        sys.stdout.write(line + '\n')
        sys.stdout.flush()


def emit_progress(rid, value, message=''):
    write_frame({'id': rid, 'type': 'progress',
                 'data': {'value': max(0.0, min(1.0, float(value))), 'message': message}})


def emit_error(rid, code, message, retryable=False):
    write_frame({'id': rid, 'type': 'error',
                 'data': {'code': code, 'message': message, 'retryable': retryable}})


def emit_result(rid, data):
    write_frame({'id': rid, 'type': 'result', 'data': data})


# ---------------------------------------------------------------------------
# Pipeline cache — one KPipeline per lang_code, lazy-built on first use
# ---------------------------------------------------------------------------
_pipeline_lock = threading.Lock()
_pipelines: dict[str, object] = {}
_pending_cancel: set[str] = set()
_pending_cancel_lock = threading.Lock()


def _get_pipeline(lang_code: str, device: str):
    with _pipeline_lock:
        cached = _pipelines.get(lang_code)
        if cached is not None:
            return cached

        try:
            from kokoro import KPipeline  # type: ignore
        except ImportError as exc:
            raise RuntimeError(f'kokoro python package not available: {exc}') from exc

        # KPipeline picks up CUDA automatically if visible; we don't get a
        # `device` kwarg in the public API. The CPU/CUDA distinction is
        # enforced via CUDA_VISIBLE_DEVICES at process spawn (host side).
        log.info('building KPipeline lang_code=%s device=%s', lang_code, device)
        pipeline = KPipeline(lang_code=lang_code)
        _pipelines[lang_code] = pipeline
        return pipeline


# ---------------------------------------------------------------------------
# Audio writing
# ---------------------------------------------------------------------------
def _write_wav(path: str, wav, sample_rate: int) -> tuple[float, int, int]:
    """Write a 1-D float waveform out as PCM-16 mono WAV. Returns
    (duration_sec, sample_rate, channels)."""
    import numpy as np
    import soundfile as sf

    arr = np.asarray(wav)
    if arr.ndim > 1:
        arr = arr.squeeze()
    if arr.ndim != 1:
        raise RuntimeError(f'unexpected waveform shape: {arr.shape}')

    arr = np.clip(arr.astype(np.float32, copy=False), -1.0, 1.0)
    sf.write(path, arr, int(sample_rate), subtype='PCM_16')

    duration = float(len(arr)) / float(sample_rate or 1)
    return duration, int(sample_rate), 1


# ---------------------------------------------------------------------------
# Request handling
# ---------------------------------------------------------------------------
def handle_tts_synthesize(rid: str, params: dict, defaults: dict) -> None:
    text = params.get('text')
    voice_id = params.get('voice')
    output_path = params.get('output_path')
    if not text or not voice_id or not output_path:
        emit_error(rid, 'bad_params', 'text, voice, and output_path are all required')
        return

    # Voice ids in the manifest are prefixed `kokoro-` and use dashes for
    # word boundaries (Subtitld convention, e.g. `kokoro-pf-dora`). Kokoro's
    # upstream voice names use underscores (e.g. `pf_dora`). Translate both
    # in one pass so the manifest can stay dash-separated.
    bare = voice_id[len('kokoro-'):] if voice_id.startswith('kokoro-') else voice_id
    bare = bare.replace('-', '_')
    voice_meta = _VOICE_BY_ID.get(bare)
    if voice_meta is None:
        emit_error(rid, 'unsupported_voice', f'unknown voice id: {voice_id!r}')
        return
    lang_code, kokoro_voice = voice_meta

    with _pending_cancel_lock:
        if rid in _pending_cancel:
            _pending_cancel.discard(rid)
            emit_error(rid, 'cancelled', 'cancelled before synthesis started')
            return

    # Speed: Subtitld passes `rate` as a -100..100 percent. Kokoro takes a
    # multiplier (1.0 = normal). Map ±100% to ±50% to keep speech intelligible.
    rate_pct = params.get('rate')
    if rate_pct is not None:
        try:
            speed = max(0.5, min(2.0, 1.0 + float(rate_pct) / 200.0))
        except (TypeError, ValueError):
            speed = float(defaults.get('speed', 1.0))
    else:
        speed = float(defaults.get('speed', 1.0))

    emit_progress(rid, 0.05, 'Loading Kokoro pipeline...')
    try:
        pipeline = _get_pipeline(lang_code, defaults['device'])
    except Exception as exc:
        log.exception('pipeline load failed')
        emit_error(rid, 'internal', f'failed to load Kokoro: {exc}')
        return

    emit_progress(rid, 0.4, 'Synthesizing...')
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        # Kokoro's pipeline yields (graphemes, phonemes, audio) chunks per
        # sentence-ish split. For Subtitld we want a single concatenated
        # waveform per request — collect them all.
        import numpy as np
        chunks = []
        for _graphemes, _phonemes, audio in pipeline(text, voice=kokoro_voice, speed=speed):
            arr = audio.detach().cpu().numpy() if hasattr(audio, 'detach') else np.asarray(audio)
            chunks.append(arr.squeeze())
        if not chunks:
            emit_error(rid, 'internal', 'kokoro pipeline returned no audio chunks')
            return
        wav = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
    except Exception as exc:
        log.exception('synth failed')
        emit_error(rid, 'internal', f'synthesize failed: {exc}')
        return

    try:
        # Kokoro emits 24 kHz audio. The pipeline doesn't expose a sample
        # rate constant, but the model's hardcoded value is 24000.
        duration, sample_rate, channels = _write_wav(output_path, wav, 24000)
    except Exception as exc:
        log.exception('wav write failed')
        emit_error(rid, 'internal', f'failed to write {output_path}: {exc}')
        return

    emit_progress(rid, 0.99, 'Finalizing...')
    emit_result(rid, {
        'path': output_path,
        'duration_sec': duration,
        'sample_rate': sample_rate,
        'channels': channels,
    })


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> int:
    manifest_path = Path(__file__).resolve().parent / 'manifest.json'
    voices: list[dict] = []
    languages: list[str] = []
    config_defaults: dict = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            voices = manifest.get('voices') or []
            languages = manifest.get('languages') or []
            config_defaults = {f.get('key'): f.get('default')
                               for f in (manifest.get('config_schema') or {}).get('fields', [])
                               if f.get('default') is not None}
        except Exception:
            log.exception('manifest parse failed')

    defaults = {
        'device': os.environ.get('KOKORO_DEVICE') or config_defaults.get('device', 'cpu'),
        'speed':  os.environ.get('KOKORO_SPEED')  or config_defaults.get('speed', 1.0),
    }

    write_frame({
        'type': 'hello',
        'protocol': PROTOCOL,
        'addon': ADDON_ID,
        'version': VERSION,
        'capabilities': [
            {'task': 'tts.synthesize', 'languages': languages, 'voices': voices,
             'voice_clone': False},
        ],
    })

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            frame = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        ftype = frame.get('type')
        rid = frame.get('id', '')

        if ftype == 'shutdown':
            log.info('shutdown received; exiting')
            return 0
        if ftype == 'cancel':
            target = (frame.get('data') or {}).get('target') or frame.get('target')
            if target:
                with _pending_cancel_lock:
                    _pending_cancel.add(target)
            continue
        if ftype == 'tts.synthesize':
            threading.Thread(
                target=handle_tts_synthesize,
                args=(rid, frame.get('params') or {}, defaults),
                daemon=True,
            ).start()
            continue
        # Host control frames (`ready` confirms our hello, future-proof for
        # other host-→-addon notifications) carry no request id and expect
        # no response. Log and ignore — only error on actual *requests* we
        # don't recognise.
        if not rid:
            log.debug('ignoring host control frame: %s', ftype)
            continue

        emit_error(rid, 'bad_params', f'unknown request type: {ftype!r}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
