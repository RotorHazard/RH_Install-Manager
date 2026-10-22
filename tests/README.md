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
