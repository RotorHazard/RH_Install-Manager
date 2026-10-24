# Baseline checks

Run from the repository root on macOS or Ubuntu with Python 3.10+, Git and
Bash. No third-party Python packages are required.

```sh
python3 -m unittest discover -s tests -v
git diff --check
```

CI runs the unittest command. The whitespace check is for local, uncommitted
changes; a clean CI checkout has no working-tree diff to check.

The version tests extract and compile the named production functions with
`ast`, without importing application modules or hardware dependencies. A
missing function fails the tests. All version-file reads use mock data;
tests do not open real `/home` files or depend on current release targets.
Fixtures cover separate stable and beta targets, a hypothetical stable bump,
main/master aliases, custom refs and firmware fallback.

The shell test enumerates tracked files with `git ls-files -z`, selecting
`.sh` files and Bash/sh shebangs, including extensionless scripts. Each file
is parsed with `bash --noprofile --norc -n -- FILE` in an environment containing
only a system PATH and `LC_ALL=C`. No repository shell script is executed.
Ignored and untracked scripts are excluded. Track new scripts before expecting
this check to include them.

CI runs the full suite on Ubuntu and macOS with Python 3.10. A Linux-only
Docker step runs `python36_smoke.py` in the digest-pinned official
`python:3.6.15-slim-buster` image, with networking disabled and the checkout
mounted read-only. It compiles runtime files and executes the config-save and
banner fixtures on CPython 3.6. It does not install application dependencies
or run application startup. The archived image is only a compatibility check.
These test environments do not change RHIM's declared Python 3.6 runtime
compatibility. These checks do not
verify installation, updates, services, networking, firmware flashing or
Raspberry Pi hardware. CI does not deploy anything.

## Runtime preflight coverage

`test_runtime_preflight.py` imports the stdlib-only guard and supplies mocked
subprocess responses for effective systemd properties and interpreter probes.
It covers standard and equivalent drop-in layouts, Python version limits,
venv/pip identity and failures, missing services, systemd errors/timeouts,
environment overrides, fresh part 1, resumed part 2, and unknown-target consent.
The original literal systemd fixture is synthetic, not captured from a Linux
host. It is independent of the guard's property constants. Empty deny-list
formatting follows the upstream [systemctl v247 property printer](https://github.com/systemd/systemd/blob/v247/src/systemctl/systemctl-show.c#L954-L994).
Tests also cover omitted optional properties and rejection of missing core ones.
`systemctl_show_systemd252_running.txt` was captured on Debian 12 amd64 with
systemd 252.39-1~deb12u2 on 2026-10-23, using the guard's exact property query
as user `pi`. Its stdout is unchanged. The service ran a dummy sleep loop with
the standard RHIM unit layout and a real Python 3.11.2 system-site-packages
venv. It was not RotorHazard. The regression test feeds this captured output
through the real guard with the interpreter probe mocked, covering live
ExecStart metadata, empty deny-lists and omitted optional properties.
Coordinator functions are loaded with the same AST helper. They run the real
guard against those fixtures with external actions mocked, checking denial
before shell commands/markers/success, final stable selection, NH quick stages,
restart and debug paths, and interpreter arguments on accepted operations.
The fresh part-1 marker, failed part-2 retry and completion state are checked
together. NH entry-point tests verify that coordinator failures return nonzero.
A parser check covers Python 3.6 syntax; it does not execute production code
on Python 3.6. Shell control flow, dependency installation and bootstrap error
propagation still require execution in a designated Linux test environment.

No systemctl, installer, apt, pip installation or hardware command is executed
by these unit tests. Shell checks only parse scripts. The remaining real Linux
and Pi checks are described in `docs/runtime-checks.md`.

## Operation status and progress coverage

`test_operation_status.py` loads production functions with the same AST helper.
Progress-file tests use temporary files and real JSON serialization, flush,
replacement and cleanup operations. Injected serialization, storage and rename
failures must leave the previous valid progress file intact; a later retry must
be able to save progress.

Other cases replace external actions to check failure propagation, completion
menus at EOF, pending configuration, failed server starts and UART setup.
Expected Ctrl+C termination of a foreground server is accepted; other failures
still propagate.
Coordinator tests also check that failed host configuration or installation
does not record completion, and that a failed fresh part 2 retains its retry
marker. These checks do not execute the shell commands they replace. Real
package, service and shell failure trials still require the designated Linux
test environment.

`test_uart_configuration.py` executes only the UART function extracted from
`sys_conf.sh`. Its shell replacements limit file operations to temporary boot
files and simulate `raspi-config` responses. It checks modern calls, the legacy
combined call when a function is unavailable, and failures without a success
message. It does not run the installer or touch actual boot settings.


## Source and data safety coverage

`test_source_safety.py` runs actual resolver, ZIP parser, copier, manifests,
merge, rename, state and lock code against explicit temporary paths. It checks
fresh/update/part-2 retry, ini precedence and relative/tilde paths, external and
in-tree data, symlinks, WAL/SHM, custom plugins, images and backup directories,
copy failures, disk-space injection, protected storage, collisions and interrupted
activation. Pre-switch failures publish no pending state; retries after newer
races or external-data changes must create a new backup. Activated retries keep
current live data and skip source preparation, host/pip work, restoration and
renames. Switching interruptions retain prepared/previous copies and report
concrete manual recovery paths, including changed external data. Unknown FIFOs
can be removed from live source and retried without editing state. Partial
backup failures remove only the unpublished copy and permit a clean retry.
Image conflicts keep custom bitmaps, retain new-only images, and keep new code.
A real SQLite WAL fixture is opened only in its backup copy.
Local Git fixtures check ref/checkout binding without network access. Mocked
urllib response bytes feed the real ZIP reader with an empty PATH; the default
ZIP bootstrap does not invoke wget/unzip, and download requests use timeout=60.
FIFO backup runs under a subprocess deadline and verifies metadata, exclusion of
stale lgpio state, refusal of unknown active FIFOs and other special files.
Kernel-lock tests cover inherited descriptor reuse, contention, invalid flags
and descriptors, exceptions and SIGKILL release.

Operation tests retain actual filesystem behavior while replacing runtime,
stop and package/service payload boundaries. Fresh pending-finalization cases
inject daemon-reload failure, retain progress/recovery state and current races,
then verify reload and a repeated guard before finalization. Runtime fixtures
separately check the proven-state reload request and rejection of unknown
service/runtime/environment overrides; this is not a real systemd reload test.
An isolated Bash helper test uses a fake iptables boundary to verify repeated
forwarding setup adds each rule once and propagates query/add failures. It does
not execute the configuration script or access /etc. Writer-scan tests use
synthetic `/proc` directories; they do not inspect host processes or run sudo/systemctl.
No installer payload, package manager, downloaded code, service or hardware
operation runs on macOS. No claim of Linux/Pi installation proof follows from
this suite. See [source/data policy](../docs/source-data-safety.md) for copy and
recovery limits. Production helpers retain Python 3.6 syntax/API choices;
the unittest/CI environment still requires Python 3.10+.

## Operation regression coverage

`test_self_update.py` runs the real Python coordinator and both Bash entry
points with downloads supplied from local ZIP fixtures. A restricted PATH
contains filesystem-command stubs that accept only paths inside the temporary
fixture; privileged, service and process commands cannot reach the host.
Downloaded Python code is parsed but never executed. Cases cover invalid
archives, preparation/config-copy failures, failed activation, retained backups,
literal branch arguments, relative config links after switching directories,
update markers and success/failure propagation.
This does not prove a real download or execution of the replacement application.
The previous installation is retained under a unique directory in
`~/.rhim_markers`; a power loss during replacement still needs manual inspection.

`test_config_writes.py` checks real atomic config saves, serialization and
storage failures, failed replacement and retry, formatting, permissions and
symlink targets. `test_banner.py` checks one host query per banner and safe
output when address lookup fails. Coordinator coverage checks that the wait
message precedes the first installation script.

`test_hotspot_configuration.py` passes credentials to a harmless argument
recorder, then executes the setup script with an allow-listed `sudo` replacement.
The replacement maps every permitted output path into a temporary directory.
Generated hotspot scripts run with fake Wi-Fi detection and `nmcli` functions.
Tests cover spaces and shell metacharacters at both boundaries, setup failures,
and saving `ap-config.json` only after setup succeeds. They do not prove actual
NetworkManager or systemd behavior, or rollback after partial system changes.

`test_nodes_flashing.py` loads production functions without hardware imports.
Mocked bus libraries, GPIO and command results cover initialization and reset
failures, bootloader retries, UART checks and single/series success reporting.
These tests do not open an I2C bus or serial port, reset a physical node or
execute `avrdude`.

## Recorded system verification

Port-forwarding regression tests use temporary rc.local files and stubbed
firewall commands. They check custom-command preservation, historical entries,
repeat runs, current-content backups, refused layouts, concurrent edits and
write failures. Pinned upstream Raspberry Pi OS rc.local fixtures exercise the
stock IP-address display, and custom scripts exercise the manual-block path.
The generic disabled-historical-rules fixture is refused without the exact
external-ownership directive. With it, tests check unchanged bytes, mode and
inode, no backups, and zero firewall calls through the actual configurator
shell entry with stub sudo/Python-path/firewall boundaries. Invalid helper
output, malformed/duplicate directives and managed-rule conflicts fail closed.
Coordinator fixtures cover fresh part 2, reinstall, update and activated retries
against the current directive; their installer payloads remain mocked.
The persistent POSIX shell block is also executed with stubs
to check error propagation and isolation of shell variables and arguments.
These tests do not prove root metadata handling or boot-time service execution.

On 2026-10-23, the following checks were run separately from this unit suite.
They describe the tested revisions and environments, not all supported systems.

- Debian 12 amd64, Python 3.11.2 and systemd 252: actual RHIM installation of
  RotorHazard 4.5.0 through ZIP, part 1, reboot and part 2; installation of
  4.4.0 followed by a Git update to 4.5.0; repeated updates and reinstallation.
  These flows used revision `ba2c245`, including the real coordinator, shell,
  sudo, package installation and service setup. Default, external datapath.ini
  and legacy source-tree data were checked. Configuration, pilot data, user
  images and plugins survived; the existing venv identity was retained.
- Controlled failures covered source download, pip, service stop, unreadable
  backup data, concurrent operations and activation retry. Newer data after a
  pre-switch failure survived retry. An interrupted switch was checked in an
  isolated filesystem fixture. The inherited-lock correction in `b5df399`
  received a separate Linux check, including all three shell entry points.
  At that revision, 156 tests and syntax checks of 32 shell scripts passed
  on Linux. The test environment was restored after each scenario.
- At revision `3484c63`, a separate Debian 12 check passed 183 tests and syntax
  checks of 34 indexed shell files, including the two stock rc.local fixtures.
  Real root-owned rc.local files preserved custom commands, current and first
  backups, permissions and no-op identity. Unsupported files were refused
  without changing NAT rules. The native rc-local service restored forwarding
  after a container reboot and retained exactly two rules after repeated
  service restarts. External HTTP requests verified both redirects, 80 to
  5000 and 8080 to 80, with matching packet-counter increases. Missing-iptables
  fixtures returned 127 and stopped before subsequent commands. The original
  test-system snapshot and file manifest were restored and verified afterward.
- Raspberry Pi 5, Debian 13 arm64 and Python 3.13.5: official RotorHazard 4.5.0
  ran twice on private copies of an existing 4.4.0 installation's data and
  venv. Wheel-only dependency updates, HTTP authentication, authenticated
  Socket.IO writes, rejection of unauthenticated writes, SQLite integrity,
  original pilot/settings preservation and persistence after restart passed.
  SIGINT reached the application handler; shutdown was logged to completion
  and its cgroup emptied in about 2.7 seconds without a forced kill.
  Its independent process exit status was not captured by the private-PID
  service. This was an application smoke test, not a full RHIM installation
  or update on the Pi. The original installation and unrelated services were
  preserved.

The Pi application used private network/device namespaces. GPIO probing logged
a caught hardware-access error; I2C and timing nodes were unavailable. The
observed configuration changes matched upstream's parameter rename and save
timestamp update. Existing system-site pip-check issues were unchanged. The Pi
lacked a cgroup memory controller, so this short trusted test used per-process
resource limits and a watchdog; it did not prove an aggregate memory limit.

These checks do not verify physical node flashing, GPIO/I2C/UART, saved races,
long-running operation, Pi reboot or normal service stop in the private-PID
test setup. They also do not prove native Python 3.6 execution or GitHub CI.
Hardware and host-network configuration need their own designated tests.

At revision `733014f`, real Linux menu checks covered refusal before the
external-ownership comment, a 4.4.0 to 4.5.0 update and repeated updates after
the operator added it. Normal updates used real apt and pip. A separate actual
RHIM menu update on Raspberry Pi preserved data, configuration, venv identity
and externally managed forwarding, with HTTP authentication and SQLite
integrity checks passing. The Pi check used real pip but explicitly skipped
four apt commands, so it does not verify Pi host-package updates. Physical
timing hardware remains unverified. The Linux suite passed 202 tests,
including syntax checks of 35 indexed shell files.
