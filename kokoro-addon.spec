# PyInstaller spec for the kokoro add-on.
# Build with: pyinstaller kokoro-addon.spec --distpath dist/

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


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
    + _safe_collect(collect_submodules, 'soundfile')
    + _safe_collect(collect_submodules, 'phonemizer')
    + _safe_collect(collect_submodules, 'segments')
    + _safe_collect(collect_submodules, 'csvw')
    + _safe_collect(collect_submodules, 'language_tags')
)
datas = (
    _safe_collect(collect_data_files, 'kokoro')
    + _safe_collect(collect_data_files, 'misaki')
    + _safe_collect(collect_data_files, 'transformers')
    + _safe_collect(collect_data_files, 'phonemizer')
    + _safe_collect(collect_data_files, 'segments')
    + _safe_collect(collect_data_files, 'csvw')
    + _safe_collect(collect_data_files, 'language_tags')
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
