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
# misaki extras unlock G2P for non-English language codes; without them,
# Kokoro will refuse to build a pipeline for ja/zh/hi etc.
pip install "kokoro[en,ja,zh,hi]"
pyinstaller kokoro-addon.spec --distpath dist/
cd dist/kokoro-addon
zip -r ../kokoro-1.0.0-linux-x86_64.zip . ../../manifest.json ../../LICENSE ../../README.md
```

`espeak-ng` is required at runtime for non-English language codes (the
G2P fallback path). Linux users typically install via `apt`, macOS via
`brew install espeak-ng`. Windows: bundled with the misaki distribution.

## Model storage

Weights are *not* bundled — `KPipeline` auto-downloads them from
`hexgrad/Kokoro-82M` on first use into the standard HuggingFace cache
(`HF_HOME`, `~/.cache/huggingface/hub` by default). ~82 MB, single
shared model across all language pipelines.

## License

Wrapper code: Apache-2.0. Kokoro 82M weights: Apache-2.0 — commercial
use is permitted, no extra license needed.
