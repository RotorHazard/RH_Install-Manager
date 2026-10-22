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

CI runs on Ubuntu and macOS with Python 3.10. This test requirement does not
change RHIM's declared Python 3.6 runtime compatibility. These checks do not
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
