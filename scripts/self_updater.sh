#!/bin/bash

fail() { printf 'Install-Manager update failed: %s\n' "$*" >&2; exit 1; }

installed="$HOME/RH_Install-Manager"
markers="$HOME/.rhim_markers"
[ -d "$installed" ] && [ ! -L "$installed" ] || fail "Installation must be a real directory: $installed"
mkdir -p "$markers" || fail "Cannot create $markers; check ownership and permissions."
lock="$markers/.self-update-lock"
mkdir "$lock" || fail "Another self-update may be running. Check $lock before retrying."
stage=""
backup=""
cleanup() {
  status=$?
  if [ -n "$backup" ] && [ -d "$backup/RH_Install-Manager" ] && [ ! -e "$installed" ] && [ ! -L "$installed" ]; then
    mv "$backup/RH_Install-Manager" "$installed" || printf 'Restore the previous installation from %s\n' "$backup" >&2
  fi
  [ -z "$stage" ] || rm -rf -- "$stage"
  [ -z "$backup" ] || rmdir "$backup" 2>/dev/null
  rmdir "$lock" || printf 'Could not remove self-update lock %s\n' "$lock" >&2
  exit "$status"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
stage=$(mktemp -d "$markers/.self-update.XXXXXX") || fail "Cannot create preparation directory."
wget "https://codeload.github.com/RotorHazard/Install-Manager/zip/${1:-stable}" -O "$stage/source.zip" || fail "Download failed."

# Validate paths and entry points without executing downloaded code.
python3 -I -B - "$stage/source.zip" <<'PY' || fail "Invalid update archive."
import ast
import json
import stat
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError('Duplicate archive paths')
    roots = set()
    for member in archive.infolist():
        parts = member.filename.rstrip('/').split('/')
        if (not parts or any(part in ('', '.', '..') for part in parts)
                or '\\' in member.filename or stat.S_ISLNK(member.external_attr >> 16)):
            raise ValueError('Unsafe archive path: ' + member.filename)
        roots.add(parts[0])
    if len(roots) != 1:
        raise ValueError('Expected one source directory')
    root = roots.pop() + '/'
    for name in ('rhim.sh', 'start_rhim.py', 'self_update.py', 'update.py', 'modules.py',
                 'scripts/self_updater.sh', 'scripts/updater_from_rhim.sh', 'version.txt',
                 'distr-updater-config.json'):
        if not archive.read(root + name).strip():
            raise ValueError('Empty required file: ' + name)
    for name in names:
        if name.endswith('.py') and name.count('/') == 1:
            ast.parse(archive.read(name), filename=name)
    json.loads(archive.read(root + 'distr-updater-config.json').decode('utf-8'))
    if archive.testzip() is not None:
        raise ValueError('Corrupt archive')
PY
unzip -q "$stage/source.zip" -d "$stage/source" || fail "Extraction failed."
sources=("$stage/source/"*)
[ "${#sources[@]}" -eq 1 ] && [ -d "${sources[0]}" ] || fail "Missing source directory."
prepared="${sources[0]}"
for script in "$prepared/rhim.sh" "$prepared/scripts/"*.sh; do
  bash -n "$script" || fail "Invalid shell script: $script"
done
chmod u+x "$prepared/rhim.sh" "$prepared/scripts/"*.sh || fail "Cannot prepare executable scripts."
for config in updater-config.json ap-config.json; do
  if [ -e "$installed/$config" ] || [ -L "$installed/$config" ]; then
    cp -p "$installed/$config" "$prepared/$config" || fail "Cannot preserve $config."
    cmp -s "$installed/$config" "$prepared/$config" || fail "Configuration differs: $config"
  fi
done
backup=$(mktemp -d "$markers/RH_Install-Manager-backup.XXXXXX") || fail "Cannot reserve backup directory."
mv "$installed" "$backup/RH_Install-Manager" || fail "Cannot preserve the current installation."
mv "$prepared" "$installed" || fail "Cannot activate prepared installation."
printf 'Previous installation retained at %s/RH_Install-Manager\n' "$backup"
