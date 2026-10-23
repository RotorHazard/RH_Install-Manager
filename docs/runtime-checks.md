# RotorHazard runtime checks

RHIM still supports Python 3.6 for its own bootstrap and menus. RotorHazard
4.4 and 4.5 tags, including beta and rc tags, require Python 3.10 or newer.
This also applies when a known tag is selected as a custom source. See the
upstream [4.4 setup instructions](https://github.com/RotorHazard/RotorHazard/blob/v4.4.0/doc/Software%20Setup.md#updating-an-existing-installation)
and [4.5 setup instructions](https://github.com/RotorHazard/RotorHazard/blob/v4.5.0/doc/Software%20Setup.md#updating-an-existing-installation).

Before either installation stage or an update, RHIM checks the actual runtime.
Updates check the final source after the offer to switch to stable. NuclearHazard
uses the same coordinator, including explicit part 1 and part 2 requests.
An unfinished installation stage or update resumes its recorded target without
changing the configured source channel, even if stable metadata changes. This
also preserves a one-time update switch to stable. Interrupted source switches
still require manual recovery before the operation can continue.
Markers and debug mode cannot skip these checks. A refused check reports
"Installation not started" or "RH update not started" before stopping the
service, changing stage markers, configuring the host or running the operation's
shell script. A failed service stop also aborts the operation.

## Supported layout

For the current configured account `USER`, RHIM accepts an effective service with:

- `User=USER`, with the default group or the account's primary group.
- `WorkingDirectory=/home/USER/RotorHazard/src/server`.
- One direct `ExecStart=/home/USER/.venv/bin/python3 server.py`. The equivalent
  absolute server.py path is accepted. Extra arguments and wrappers are refused.
- No environment overrides, pre/post execution hooks or execution sandbox
  settings checked by the guard. Pending daemon reloads are normally refused.

A verified fresh part-2 activation can request a reload when service setup
previously failed. RHIM checks its recorded backup, activated source identity
and all other runtime conditions, reloads systemd, then repeats the full guard.
Other pending unit changes require explicit review and a manual reload. See
[source activation and recovery](source-data-safety.md#activation-and-recovery).

The read-only query uses `systemctl show --all --property=...` and checks loaded
properties. Drop-ins producing these same effective values are accepted. RHIM
does not parse unit files or change the service to make it pass. Identity and
command properties are required; optional properties absent on older systemd
versions use their unrestricted defaults. Empty system-call and address-family
deny-lists are represented as `~`, not as configured restrictions. Systemd access
failures or missing required properties cause refusal. See
[systemctl show](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html#show%20%5BPATTERN%E2%80%A6%7CJOB%E2%80%A6%5D).

Legacy/system-Python services, different interpreters, directories, users and
custom execution environments need a separately planned migration. RHIM never
silently substitutes the standard venv for a different service runtime. The
validated update path skips the old Python 3 service/sensor transition script.
The standalone transition tool remains available for separately planned work.
Neither update nor reinstall automatically migrates these unsupported layouts;
they require manual migration planned for that installation.

## Fresh and resumed installation

A missing service is normal when there is no `/home/USER/RotorHazard` tree
and this is an installation stage. After successful fresh part 1, RHIM records
`fresh_install_pending` in its existing marker file. That explicit state permits
retrying a fresh installation if part 2 leaves downloaded source but no service
after an activation failure. Source preparation and pip failures before
activation keep the live source path unchanged. The working venv is still
required. Old markers without this field do not authorize treating an existing
tree as fresh, and an update
always requires the service. The pending state is cleared after successful
part 2, before the completion menu can request a reboot.

Part 1 may validate `/usr/bin/python3` and the venv module and create the intended
`/home/USER/.venv` if neither the tree nor service nor venv exists. Existing venv
paths, including broken paths or symlinks, are never recreated. An existing
venv must pass the interpreter identity and pip checks, even for part 1.
If both source and venv are absent but `rotorhazard.service` remains loaded,
RHIM identifies the leftover unit and refuses to recreate the venv. Review the
service and runtime manually and verify whether the unit is still in use before
making changes.
Part 2 always requires the working venv and pip, including after reboot.
An environment resolving inside the RotorHazard source tree is refused because
replacing that tree would also remove access to the interpreter.

This preserves the installation sequence: part 1 creates the venv once,
part 2 uses it, and later updates validate and reuse it. A failed check remains
on screen until Enter is pressed; a normal successful check adds no question.

The module check does not prove venv creation will succeed; for example,
ensurepip may still be missing. Creation errors stop the stage.

Probes use argument lists without a shell, a 15-second timeout, `-I -B`, a
sanitized environment and `/` as their working directory. They import pip or
venv, not RotorHazard startup or hardware modules. The executable path is kept
as the venv path rather than resolved to its base-Python symlink. Dependency
installation uses that venv's `python3 -I -B -m pip`.

The three installation/update shell scripts enter the shared source engine,
which repeats the runtime guard before source preparation or host changes.
Direct invocation requires arguments `USER TARGET MODE
PYTHON`, where MODE is `git` or an empty quoted string, and PYTHON matches the
validated executable. Part 1 uses `/usr/bin/python3` only for a new venv;
otherwise all stages use `/home/USER/.venv/bin/python3`. A missing or mismatched
executable argument refuses the operation. These are system-changing scripts;
run them only on the intended installation host.

## Unknown targets and protection limits

`main` and unknown custom refs remain selectable. Their minimum Python version
is not guessed. RHIM asks for explicit confirmation with default No for each
operation after the layout and runtime checks pass. It reports that target
requirements remain unverified. The coordinator passes `--accept-unknown` to
its shell recheck for that invocation only. A direct script invocation also
requires this explicit flag for an unknown target; it does not bypass runtime
layout, identity or pip checks. Nothing is saved as a permanent exception.

`rhim.sh` may already have run host dependency setup through apt before these
per-operation checks. It uses distro wheel, requests and RPi.GPIO packages
rather than ambient pip writes. It no longer creates a venv from
`.python_venv_flag`; this legacy flag does not trigger automatic migration.
Fresh creation belongs to validated part 1. RHIM does not retry the whole
application after a failure. NH propagates bootstrap and coordinator failures
as nonzero exit codes; a noninteractive refusal does not require Enter.
Bootstrap installation failures for Python, Git, pip, requests or venv support
stop startup. Other helper-package failures retain their previous nonfatal
behavior.
Host apt upgrade/autoremove steps inside accepted operations remain.

If an older installer left source without a service and without the new pending
marker, RHIM cannot establish its origin. Inspect and preserve that source tree
before explicitly planning recovery. Likewise, inspect an incomplete new venv
after failed creation; do not remove or recreate an environment used by an
existing installation. RHIM does not infer that either directory is disposable.

This guard checks interpreter selection, version, venv identity and pip
availability. It does not test server startup, dependency/plugin compatibility,
hardware, every possible systemd restriction or changes made concurrently after
the probe. It supplies no rollback. Source preparation, verified backups and
retry behavior are described in the [source/data policy](source-data-safety.md).
Host package updates can require a reboot and can affect the runtime after
preflight.
An operation failing after it starts can leave changed files/dependencies and
a stopped service. Review its error and recovery state before retrying.

Local mocked tests and shell syntax checks do not prove behavior on a real
systemd host, Linux venv or Raspberry Pi. Those need fresh-install, resumed
part-2 and existing-install update trials on designated Linux/Pi test systems.

On 2026-10-23, the read-only preflight was exercised as `pi` on Debian 12
amd64 with Python 3.11.2 and systemd 252.39. Fresh part 1 selected the system
base without creating files. A manually created system-site-packages venv and
a running dummy service passed targets `v4.4.0` and `v4.5.0` across all stages.
System Python ExecStart, environment overrides, missing venv and broken venv
were refused without changing the measured service state or fixture files.
The captured systemctl output is retained in the test fixtures. This verifies
the guard with a real venv and service, not installation scripts, real
RotorHazard startup, dependency installation or Raspberry Pi hardware.

Later installation/update and isolated ARM application checks are summarized
in [recorded system verification](../tests/README.md#recorded-system-verification).
Their scope and limitations are separate from the read-only guard trial above.
