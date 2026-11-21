# Kokoro 82M add-on for Subtitld

The light end of Subtitld's TTS catalog. Apache-2.0,
[hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M):
~80 MB on disk, sub-second per line on a midrange CPU, no GPU required.

## Voices and languages

54 preset voices spread across 9 languages:

- **English (American)** — Heart (default), Alloy, Aoede, Bella, Jessica,
  Kore, Nicole, Nova, River, Sarah, Sky (female); Adam, Echo, Eric,
  Fenrir, Liam, Michael, Onyx, Puck, Santa (male).
- **English (British)** — Alice, Emma, Isabella, Lily; Daniel, Fable,
  George, Lewis.
- **Japanese** — Alpha, Gongitsune, Nezumi, Tebukuro, Kumo.
- **Mandarin** — Xiaobei, Xiaoni, Xiaoxiao, Xiaoyi; Yunjian, Yunxi,
  Yunxia, Yunyang.
- **Spanish** — Dora; Alex, Santa.
- **French** — Siwis.
- **Hindi** — Alpha, Beta; Omega, Psi.
- **Italian** — Sara; Nicola.
- **Brazilian Portuguese** — Dora; Alex, Santa.

Voice cloning is **not supported** — Kokoro doesn't have an audio
encoder path. Use Coqui XTTS, Qwen3-TTS, or F5-TTS for cloning.

## Building

```bash
pip install pyinstaller
pip install torch --extra-index-url https://download.pytorch.org/whl/cpu
# The language extras are misaki's (kokoro has none). Japanese takes
# unidic-lite rather than misaki[ja]'s unidic, a separate 500+ MB download.
pip install kokoro "misaki[en,zh]" fugashi jaconv mojimoji pyopenjtalk unidic-lite
pip install --upgrade "transformers>=4.40,<4.55"
# spaCy's English model, for misaki's English G2P (see below)
pip install "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
pyinstaller kokoro-addon.spec --distpath dist/
python tools/smoke_synth.py dist/kokoro-addon/kokoro-addon   # speaks real lines
```

The release workflow does the same on Linux, macOS and Windows for a tag
`v<version>` matching `manifest.json`, and fails if the frozen add-on can't
speak an American English, a British English, a Spanish, a Japanese and a
Chinese line.

spaCy's English model (`en_core_web_sm`, MIT) is part of the bundle. Before
26.11.1 it wasn't: misaki then asked spaCy to download it on the first English
line, spaCy ran `sys.executable -m pip`, which in a frozen add-on is the
add-on itself, and the line never finished. The add-on now refuses any such
download, and keeps stdout for protocol frames only.

Japanese and Chinese have worked since 26.11.2. Up to 26.11.1 the build
installed `kokoro[ja,zh]`, extras that don't exist, so the bundle had no
Japanese or Chinese G2P and those voices failed on their first line.

espeak-ng, which the other languages use, is part of the bundle
(`espeakng_loader`); nothing has to be installed on the computer.

## Model storage

Weights are *not* bundled — `KPipeline` auto-downloads them from
`hexgrad/Kokoro-82M` on first use into the standard HuggingFace cache
(`HF_HOME`, `~/.cache/huggingface/hub` by default). ~82 MB, single
shared model across all language pipelines.

## License

Wrapper code: Apache-2.0. Kokoro 82M weights: Apache-2.0 — commercial
use is permitted, no extra license needed.

Bundled text front ends: misaki (Apache-2.0), spaCy and en_core_web_sm (MIT),
espeak-ng (GPL-3.0, through espeakng_loader), fugashi (MIT) with MeCab
(BSD-3-Clause, chosen from its BSD/GPL/LGPL triple licence) and unidic-lite
(MIT; the UniDic 2.1.2 dictionary in it is BSD-3-Clause), pyopenjtalk (MIT),
jieba (MIT), pypinyin (MIT) and cn2an (MIT).
