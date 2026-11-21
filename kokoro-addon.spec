# PyInstaller spec for the kokoro add-on.
# Build with: pyinstaller kokoro-addon.spec --distpath dist/

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


def _safe_collect(fn, name):
    try:
        return fn(name)
    except Exception:
        return []


# kokoro pulls misaki (G2P) + transformers + torch + huggingface-hub.
# Non-English language codes additionally need misaki[ja|zh|...] extras
# at install time; those install language-specific G2P submodules that
# we collect here so the freeze sees them.
#
# Misaki's English G2P chain reaches out through phonemizer → segments →
# csvw → language_tags, and `language_tags` ships a JSON dataset
# (`data/json/index.json`) that PyInstaller does *not* pick up
# automatically (it's loaded via importlib.resources at runtime, not
# referenced statically). Without explicit collection the v1.0.2 frozen
# bundle crashed on first synthesis with:
#   FileNotFoundError: '.../_internal/language_tags/data/json/index.json'
# Collect submodules + data files for the whole transitive chain.
hiddenimports = (
    _safe_collect(collect_submodules, 'kokoro')
    + _safe_collect(collect_submodules, 'misaki')
    + _safe_collect(collect_submodules, 'transformers')
    # Note: `soundfile` was previously listed here, but the addon now
    # writes WAV via stdlib `wave` — see `_write_wav` in kokoro_addon.py
    # for the rationale (PyInstaller dropped the CFFI binding silently
    # when it wasn't installed at build time, crashing synthesis on
    # first call). No equivalent stdlib gap exists for the remaining
    # entries below.
    + _safe_collect(collect_submodules, 'phonemizer')
    + _safe_collect(collect_submodules, 'segments')
    + _safe_collect(collect_submodules, 'csvw')
    + _safe_collect(collect_submodules, 'language_tags')
    + _safe_collect(collect_submodules, 'espeakng_loader')
    # misaki's English G2P runs spaCy's en_core_web_sm. spaCy decides it is
    # installed from the package metadata, so the dist-info goes in too;
    # without it misaki downloaded the model at runtime, which a frozen
    # add-on can't do (1.0.6 hung on its first English line).
    + _safe_collect(collect_submodules, 'spacy')
    + _safe_collect(collect_submodules, 'en_core_web_sm')
)
datas = (
    _safe_collect(collect_data_files, 'kokoro')
    + _safe_collect(collect_data_files, 'misaki')
    + _safe_collect(collect_data_files, 'transformers')
    + _safe_collect(collect_data_files, 'phonemizer')
    + _safe_collect(collect_data_files, 'segments')
    + _safe_collect(collect_data_files, 'csvw')
    + _safe_collect(collect_data_files, 'language_tags')
    # espeakng_loader ships the espeak-ng binary data dictionaries under
    # `espeakng_loader/espeak-ng-data/`. misaki.espeak imports the loader
    # at module scope and calls `get_data_path()` immediately, which
    # raises RuntimeError if the directory is missing. PyInstaller picks
    # up the .py files via auto-discovery but doesn't bundle the
    # `espeak-ng-data` tree (it's not Python source). Collect explicitly.
    + _safe_collect(collect_data_files, 'espeakng_loader')
    + _safe_collect(collect_data_files, 'spacy')
    + _safe_collect(collect_data_files, 'en_core_web_sm')
    + copy_metadata('en_core_web_sm')
    + [('manifest.json', '.')]
)

block_cipher = None

a = Analysis(
    ['kokoro_addon.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tensorflow', 'jax', 'flax', 'gradio'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='kokoro-addon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name='kokoro-addon',
)
