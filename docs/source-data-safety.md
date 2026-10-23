# Source and data safety

RHIM prepares a unique source directory on the installation filesystem before
stopping RotorHazard or running the stage's host/package work. ZIP downloads
use the selected ref, reject unsafe paths, links, duplicate members and multiple
roots, check CRCs, and require `src/server/server.py` and `requirements.txt`.
Git downloads resolve the selected tag or remote branch to a commit and verify
the detached checkout. ZIP receipts identify the downloaded archive by SHA256;
they do not authenticate a release or pin a moving branch to an upstream commit.
The default ZIP path uses Python's TLS-verified urllib downloader with a
60-second socket timeout and the standard-library ZIP reader. It does not need
wget or unzip before host packages are installed. Git mode still needs git
before preparation; missing host-operation tools require repair before retrying. Stale staging directories are never selected by a wildcard.

## Effective data directory

The resolver follows RH 4.4/4.5 precedence for the supported standard unit:

1. The first line of `src/server/datapath.ini`, expanded with the user's home.
   Relative paths use the final `RotorHazard/src/server` working directory.
   The target must already exist.
2. An existing `~/rh-data` directory.
3. Legacy `src/server`, when it contains `config.json`.
4. Prospective `~/rh-data`, which the read-only resolver does not create.

A legacy database without config and without another effective config/database
requires a manual path choice in `datapath.ini`, including when an empty `rh-data` would
hide that database. Invalid paths, source directory
symlinks, data ancestors of the program, and overlaps with RHIM, venv, staging or
backup storage are refused. External data-directory symlinks are supported;
in-tree data-directory symlinks require an explicit path choice. Critical config
or database file symlinks escaping the selected data directory require manual
review. Other links are preserved as links; arbitrary link target trees are not
traversed or included in the backup.

The wizard, configuration status and NuclearHazard configuration use the same
resolver. A requested configuration write can create the prospective data
directory; checking status cannot. The runtime guard still refuses extra unit
arguments such as `--data`, manager Python/loader overrides and nonstandard unit
environments. Main/custom targets still require explicit default-no consent for
each operation. The resolver does not prove unknown versions' data semantics.

## Stop, backup and copy policy

After source preparation, RHIM stops the service synchronously, confirms
inactive/failed with MainPID 0, and uses a privileged read-only `/proc` scan to
refuse manual server processes and open source/data files. Uninspectable
processes fail the check. Missing service acceptance remains the runtime guard's
fresh/proven-resume decision. Keep RH stopped and do not manually start another
writer during an operation; the RHIM lock cannot prevent an external start.

Each operation gets a mode-0700 directory under `~/rhim-backups/operation-*`.
It contains full `source` and actual `data` copies when present, including DB,
WAL/SHM, config, backups, user images, plugins, logs and unknown plugin files.
A manifest verifies types, file lengths, SHA256 and link text against the stopped
original and the copy. FIFO streams are never opened: backup copies recreate
the type, permissions and timestamps. Other special files require manual review.
A backup is announced as protected only after copy and manifest verification.
A failed unpublished copy is removed from its unique directory. If removal
fails, the error labels that exact path as incomplete and includes both errors.
Valid backups and live/external data are never removed by this cleanup.
Backup failures never count as successful stages.
Backup storage and staging must share the source filesystem. No existing backup
is overwritten or used as a directory into which a new source tree is nested.

The prepared tree receives user data before activation:

- `src/server/config.json`, `database.db`, `database.db-wal`, `database.db-shm`,
  `cfg_bkp`, `db_bkp`, `logs`, and `static/user` retain the old data.
- `static/image` keeps old custom image contents at matching paths and retains
  new bundled images without an old counterpart. Directories merge without nesting.
- Other missing files and directories, including custom plugins, shared files
  and user-added images, are copied. New bundled program files win conflicts.
  Modified old copies remain in `backup/source`; `conflicts.txt` lists conflicts.
  Copies merge directory contents without nesting image directories.
- `datapath.ini` is preserved literally. Separate in-tree data is copied intact
  only when it does not collide with new program files. External data stays at
  its current path and receives an independent backup.
- `.git`, `__pycache__` and `.pyc` files are excluded from the old-tree merge.
  FIFOs matching only `src/server/.lgd-nfy<digits>` are backed up but excluded
  from activation as stale lgpio runtime state. Other FIFOs require manual merge.

RHIM does not open or migrate databases in production. Tests open a database
copy to check a real WAL fixture. No blanket permission change is applied to the
old installation or external data.

## Activation and recovery

One kernel file lock spans coordinator effects and direct installer/update
entry points. Children validate and reuse the inherited descriptor against the
expected lock file. An environment flag alone cannot bypass locking. Process
exit or reboot releases kernel locks; persistent recovery state survives.

Host upgrades remain enabled, after preparation and verified backup. Existing
venvs are reused. Only fresh part 1 may create a missing venv. Actual runtime
checks repeat after package work and before dependency installation, and again
before activation. Effective service/runtime validation repeats after service
setup before success is recorded. Part 1 keeps the working source in place; part 2 prepares
source again after reboot and takes a new stopped-data backup.

Before a source switch, failures in preparation, copying, host upgrades or pip
leave the live source in place and publish no pending source state. Verified
unique backups remain for review. A retry stops writers again and takes a new
backup, including races or external-data changes made since the failed attempt.
Part 1 never publishes a pending source switch and does not move live source.

`~/.rhim_markers/source-operation.json` is saved immediately before the two
renames, with phase `switching`, the exact prepared and previous paths, original
verified backup, target, data path and prepared source identity. Phase `activated`
is saved after the rename. Retry the same stage and target. An activated retry
checks the live directory identity and program files, data path, original backup
and runtime, then runs only service/setup finalization and completion checks.
It never prepares source, installs packages, restores data or swaps source again.
Current live user data, including changes made after a failed activation, stays
in place. A replaced source directory, changed program files or changed data path
requires manual review instead. Fresh retries retain `fresh_install_pending`
until checked part 2 succeeds; an existing venv is never recreated.

For a verified fresh part-2 activation, `NeedDaemonReload=yes` can request a
systemd reload after the other service/runtime checks pass. RHIM checks the
backup and live source identity before allowing this request. The engine reloads
systemd and repeats the full guard before running finalization. Unknown service
commands, arguments, overrides, manager environments or runtimes still fail.
If service creation left a missing cached unit, the existing fresh-install
marker permits the same checked service setup to run again. Other pending unit
changes require explicit review and `sudo systemctl daemon-reload` before retry.
Failed reload/enable/setup retains pending recovery and the fresh marker.
Part 2 and updates check the current rc.local layout without editing it before
service stop, backup, host package work or source preparation/switching, including
activated retries. Part 1 does not check forwarding. The final configurator reads
and validates rc.local again; the early check cannot guarantee later writes or
firewall commands will succeed. Bootstrap package work can precede this check.
Repeated port-forwarding setup checks before adding rules and preserves the
first rc.local backup. The shared installer/update configurator preserves
unrelated commands in supported simple `/etc/rc.local` scripts. It migrates
exact historical RHIM forwarding entries into a managed block and saves the
current file as `/etc/rc.local.rhim-backup-*` before each content change.
Unchanged content is not rewritten or backed up again. The stock Raspberry Pi
OS IP-address display fragment is preserved. Symlinks, special files, invalid
managed blocks and unsupported automatic edits are refused before live firewall
rules are changed. Backup, write and firewall errors remain stage failures;
retry does not discard pending recovery.

For a custom shell script that RHIM cannot edit safely, the refusal prints the
complete current forwarding block. Preserve your own commands and place that
block manually where startup will execute it, outside functions or conditions
and before any terminating exit or exec. Check your script's syntax and startup
behavior, then retry the same RHIM operation. Exactly one unchanged current
block is accepted without editing the surrounding custom script; historical
RHIM rules must not remain alongside it. RHIM does not prove that a manually
placed block is reachable. A changed block in an unsupported custom layout
requires manual review again.

The file replacement and live firewall changes are separate operations. A
failure can leave the persistent configuration written before all live rules
have been applied. Inspect the reported error before retrying. Earlier RHIM
versions could replace the whole file; this change cannot recover commands
that are already absent. Review existing backups when recovering older edits.

An interruption recorded as `switching` stops automatically with the exact
recovery paths. This includes a crash between the two moves or after a rename
but before the activated state was saved. RHIM cannot safely infer whether a
user has subsequently changed live or external data. It retains the prepared
and previous source directories and original consistent backup. An ordinary
second-rename failure attempts to restore the previous live path, but still
requires manual review of the recorded switch. No external data is overwritten.

### Manual recovery after an interrupted switch

1. Read `~/.rhim_markers/source-operation.json`. Note `backup`, `prepared`,
   `previous`, `data.path`, `stage` and `target`. Stop the service with
   `sudo systemctl stop rotorhazard.service` when it exists. Stop any manually
   started RH server or plugin writer too. Keep writers stopped throughout
   recovery. A reboot alone does not establish which data copy is current.
2. Keep every recorded path. Inspect the live source if present, the previous
   source, prepared source, `backup/source`, `backup/data`, and any external
   `data.path`. `backup/manifest.json` describes the original consistent copy;
   `conflicts.txt` identifies retained program conflicts. Never select a copy
   solely because its directory name or timestamp looks newest. Compare actual
   configuration, race database and plugin/image content. Preserve the current
   external data directory separately before any manual editing.
3. Create a new recovery directory, for example
   `recovery=$(mktemp -d "$HOME/rhim-backups/manual-XXXXXXXX")`.
   Copy the source you have chosen with
   `cp -a -- /exact/chosen/source "$recovery/restored-source"`.
   If newer in-tree data is in another copy, reconcile it in this new directory
   before using it. Treat database.db, database.db-wal and database.db-shm as
   one stopped-data set. Keep the originals untouched. Do not overlay an old
   database onto newer races. Keep literal datapath.ini and its actual data
   target together; copying the ini alone is insufficient.
4. If `~/RotorHazard` exists, preserve it with
   `mv -- "$HOME/RotorHazard" "$recovery/live-before-recovery"`.
   Put the reviewed copy at the expected path with
   `mv -- "$recovery/restored-source" "$HOME/RotorHazard"`.
   Check that `src/server/server.py` and `requirements.txt` exist and that
   datapath.ini resolves to the intended current data. External data stays at
   its existing path unless you have explicitly planned a separate migration.
5. Only after checking the restored source and data, archive the pending state
   with `mv -- "$HOME/.rhim_markers/source-operation.json" "$recovery/source-operation.json"`.
   Keep the installation progress file and its legitimate fresh-install marker.
   Retry the recorded RHIM stage/target to take a new backup. If runtime/service
   checks reject the recovered layout, repair that explicit mismatch first;
   source recovery does not restore venv packages or host configuration.

Legacy states from an older attempt without the recorded activation identity
also need this manual review. Deleting state to force an automatic restore is
not a recovery procedure.

### Retention and cleanup

Success writes `source-completed.json`, recording the selected ref/archive
identity, final source/data paths and backup, then removes pending source state.
This records checked file/dependency/service-setup completion, not a successful
RH start. Part 1 records only host preparation, not source activation.

Menu `o` lists retained backup/staging paths and old wildcard source directories,
including when there is no receipt or only part 1 has run. It deletes nothing.
A pending operation refuses cleanup and names its protected backup. Keep every
pending-state path, the last verified backup, and any copy containing unique
races, images or configuration. Review older successful/failed-attempt backups
and stale staging individually after confirming RH works with the intended data
and you have another verified recovery copy. Remove only a specifically reviewed
path manually; never use a wildcard to clear RotorHazard or backup directories.
A completed receipt does not prove all older copies are disposable. The old
direct mover remains disabled.

Source/data backups do not restore shared venv packages, system Python, host
packages, service/network changes or later application database migrations.
There is no promise of automatic full rollback. Real Linux package/service,
RH startup and Raspberry Pi hardware trials remain separate acceptance steps.
