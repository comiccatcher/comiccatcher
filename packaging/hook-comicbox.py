from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# Collect everything for comicbox
datas = collect_data_files('comicbox')
hiddenimports = collect_submodules('comicbox')

# Explicitly add critical dependencies that use dynamic discovery or have data files
deps = [
    'comicfn2dict',
    'glom',
    'marshmallow',
    'marshmallow_jsonschema',
    'marshmallow_union',
    'jsonschema',
    'py7zr',
    'rarfile',
    'xmlschema',
    'elementpath',
    'pygments',
    'rich',
    'typing_extensions',
    'pydantic',
    'ruamel.yaml',
    'cryptography'
]

for dep in deps:
    try:
        datas += collect_data_files(dep)
        hiddenimports += collect_submodules(dep)
    except Exception:
        pass

# Ensure metadata for comicbox is available for version checks
datas += copy_metadata('comicbox')
