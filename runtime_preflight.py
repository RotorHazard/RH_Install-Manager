"""Read-only checks for the narrow RHIM service/runtime layout. Python 3.6+."""
import argparse
import grp
import json
import os
import pwd
import re
import subprocess
import sys


# Reject execution environments that cannot be reproduced by a local probe.
EMPTY_PROPERTIES = (
    "Environment", "EnvironmentFiles", "PassEnvironment", "UnsetEnvironment",
    "RootDirectory", "RootImage", "BindPaths", "BindReadOnlyPaths",
    "TemporaryFileSystem", "InaccessiblePaths", "ReadOnlyPaths", "ReadWritePaths",
    "ExecStartPre", "ExecStartPost", "ExecCondition", "SupplementaryGroups",
    "PAMName", "NetworkNamespacePath", "JoinsNamespaceOf",
    "NoExecPaths", "ExecPaths", "SystemCallArchitectures", "AppArmorProfile", "SELinuxContext",
)
FILTER_PROPERTIES = ("SystemCallFilter", "RestrictAddressFamilies")
DEFAULT_PROPERTIES = {
    "DynamicUser": "no", "PrivateUsers": "no", "PrivateMounts": "no",
    "PrivateTmp": "no", "ProtectHome": "no", "ProtectSystem": "no",
    "MountAPIVFS": "no", "NoNewPrivileges": "no", "PrivateDevices": "no",
    "PrivateNetwork": "no", "MemoryDenyWriteExecute": "no",
}
REQUIRED_PROPERTIES = ("LoadState", "User", "WorkingDirectory", "ExecStart", "NeedDaemonReload")
PROPERTIES = REQUIRED_PROPERTIES + ("Group",) + EMPTY_PROPERTIES + FILTER_PROPERTIES + tuple(DEFAULT_PROPERTIES)
PROBE = ("import json, sys; import pip; "
         "print(json.dumps({'version': list(sys.version_info[:3]), "
         "'prefix': sys.prefix, 'base_prefix': sys.base_prefix, "
         "'executable': sys.executable}))")


def run(argv):
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, timeout=15, cwd="/",
                                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("Cannot inspect runtime: {}. Check systemd and Python access.".format(error))
    return result


def pending_fresh_install(user):
    try:
        with open("/home/{}/.rhim_markers/rhim_config.json".format(user), "r") as file:
            markers = json.load(file)
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        raise ValueError("Cannot read installation progress. Restore the RHIM marker file before retrying.")
    return isinstance(markers, dict) and markers.get("fresh_install_pending") is True


def check_runtime(user, target, stage, confirm=None):
    """Return validated executable paths, or raise ValueError before any mutation."""
    if stage not in ("part1", "part2", "update"):
        raise ValueError("Invalid installation stage. Restart RHIM and select the operation again.")
    try:
        account = pwd.getpwuid(os.getuid())
        primary_group = grp.getgrgid(account.pw_gid).gr_name
    except KeyError:
        raise ValueError("Cannot identify the current account or group. Restore the account configuration before retrying.")
    if (not isinstance(user, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*[$]?", user)
            or account.pw_name != user):
        raise ValueError("Configured user differs from the current account. Run RHIM as the configured user.")
    if (not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", target)
            or ".." in target or "//" in target or target.endswith("/")):
        raise ValueError("Invalid RotorHazard source. Select a valid version tag or branch in RHIM.")
    home = "/home/" + user
    venv = home + "/.venv"
    python = venv + "/bin/python3"
    directory = home + "/RotorHazard/src/server"
    existing = os.path.lexists(home + "/RotorHazard")
    result = run(["systemctl", "show", "--all", "--property=" + ",".join(PROPERTIES),
                  "rotorhazard.service"])
    properties = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    missing = properties.get("LoadState") == "not-found"
    fresh_install = missing and not existing
    pending_daemon_reload = False
    if missing:
        if existing and stage != "update":
            fresh_install = pending_fresh_install(user)
        if stage == "update" or (existing and not fresh_install):
            raise ValueError("RotorHazard service is missing on an existing installation. Restore or migrate the service explicitly.")
        if result.returncode not in (0, 4):
            raise ValueError("Cannot inspect RotorHazard service. Restore systemd access and retry.")
    else:
        if result.returncode or properties.get("LoadState") != "loaded":
            raise ValueError("Cannot inspect loaded RotorHazard service. Restore systemd access and retry.")
        if any(key not in properties for key in REQUIRED_PROPERTIES):
            raise ValueError("Incomplete systemd runtime properties. Review the service on a supported systemd host.")
        if properties["NeedDaemonReload"] != "no":
            # Only our verified fresh activation can request a reload before repeating this guard.
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from source_safety import read_state, check_activation
            state = read_state(home) if stage == "part2" else None
            if (properties["NeedDaemonReload"] != "yes" or not state
                    or state.get("stage") != stage or state.get("target") != target
                    or state.get("phase") != "activated" or state.get("fresh_install") is not True):
                raise ValueError("RotorHazard unit has pending changes. Review the unit and drop-ins, run sudo systemctl daemon-reload, then retry the same RHIM operation.")
            check_activation(home, state)
            pending_daemon_reload = True
        if properties["User"] != user or properties.get("Group", "") not in ("", primary_group):
            raise ValueError("Unsupported service user/group. Migrate explicitly to the standard RHIM account layout.")
        if properties["WorkingDirectory"] != directory:
            raise ValueError("Unsupported service working directory. Migrate explicitly to the standard RHIM layout.")
        # Only systemctl's single direct-command representation is accepted, not unit-file syntax.
        command = properties["ExecStart"]
        pattern = (r"\{ path=" + re.escape(python) + r" ; argv\[\]=" + re.escape(python)
                   + r" (?:server\.py|" + re.escape(directory + "/server.py")
                   + r") ; ignore_errors=no ; start_time=[^;]*; stop_time=[^;]*; pid=\d+ ; code=[^;]*; status=[^;{}]* \}")
        if not re.fullmatch(pattern, command):
            raise ValueError("Unsupported RotorHazard ExecStart. Explicitly migrate legacy/system Python, wrappers or arguments to ~/.venv/bin/python3 server.py.")
        # Older systemd versions omit unsupported optional properties. '~' is an empty deny-list.
        if (any(properties.get(key, "") for key in EMPTY_PROPERTIES)
                or any(properties.get(key, value) != value for key, value in DEFAULT_PROPERTIES.items())
                or any(properties.get(key, "~") != "~" for key in FILTER_PROPERTIES)):
            raise ValueError("Unsupported service environment or sandbox overrides. Review and migrate them explicitly before retrying.")
    environment = run(["systemctl", "show-environment"])
    if environment.returncode or any(re.match(r"(?:PYTHON|LD_|VIRTUAL_ENV=)", line)
                                     for line in environment.stdout.splitlines()):
        raise ValueError("Unsupported systemd manager environment. Review Python/loader overrides before retrying.")
    create_venv = not os.path.lexists(venv)
    if create_venv and (stage != "part1" or existing or not missing):
        raise ValueError("RotorHazard venv is missing. Restore it or plan an explicit runtime migration; it will not be recreated.")
    executable = "/usr/bin/python3" if create_venv else python
    # A new base needs venv support, not pip; an existing runtime must have pip.
    code = PROBE if not create_venv else PROBE.replace("import pip", "import venv")
    probe = run([executable, "-I", "-B", "-c", code])
    if probe.returncode:
        raise ValueError("Cannot run {} with {}. Repair Python/venv and pip explicitly. {}".format(
            executable, "venv support" if create_venv else "pip", probe.stderr.strip()[:300]))
    try:
        runtime = json.loads(probe.stdout)
        version = runtime["version"]
        valid_version = (isinstance(version, list) and len(version) == 3
                         and all(type(part) is int for part in version))
        valid_identity = (os.path.abspath(runtime["executable"]) == executable
                          and (runtime["prefix"] == runtime["base_prefix"] if create_venv else
                               os.path.realpath(runtime["prefix"]) == os.path.realpath(venv)
                               and runtime["prefix"] != runtime["base_prefix"]))
        if not valid_version or not valid_identity:
            raise ValueError("identity")
    except (ValueError, KeyError, TypeError):
        raise ValueError("Python probe returned an invalid runtime/venv identity. Repair the intended runtime explicitly.")
    source_directory = os.path.realpath(home + "/RotorHazard")
    if os.path.commonpath([os.path.realpath(venv), source_directory]) == source_directory:
        raise ValueError("The venv points inside the RotorHazard source directory. Plan an explicit migration before replacing that directory.")
    known = re.fullmatch(r"v?4\.[45]\.\d+(?:-(?:beta|rc)\.\d+)?", target) is not None
    if known and tuple(version[:2]) < (3, 10):
        raise ValueError("RotorHazard {} requires Python 3.10+, but {} runs {}.{}. Plan an explicit runtime/OS migration.".format(
            target, executable, version[0], version[1]))
    if not known:
        prompt = ("Runtime requirements for {} are unverified. Check upstream requirements first. "
                  "Proceed for this operation only? [y/N] ").format(target)
        try:
            approved = confirm is not None and confirm(prompt).strip().lower() in ("y", "yes")
        except (EOFError, OSError):
            approved = False
        if not approved:
            raise ValueError("Unknown target requirements were not accepted. Select a known release or confirm this operation explicitly.")
    return {"python": python, "base_python": executable, "create_venv": create_venv,
            "service_present": not missing, "unknown_target": not known, "version": version,
            "fresh_install": fresh_install, "pending_daemon_reload": pending_daemon_reload}


def main(argv=None):
    # A successful --help exit must not let a caller continue into system changes.
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("stage", choices=("part1", "part2", "update"))
    parser.add_argument("user")
    parser.add_argument("target")
    parser.add_argument("python", help="Expected executable from the coordinator")
    parser.add_argument("--accept-unknown", action="store_true",
                        help="Explicit acceptance for this invocation only; runtime layout checks still apply")
    args = parser.parse_args(argv)
    try:
        result = check_runtime(args.user, args.target, args.stage,
                               (lambda prompt: "yes") if args.accept_unknown else None)
        if result.get("pending_daemon_reload"):
            raise ValueError("Pending activation needs a daemon reload. Retry the same RHIM operation so the source engine can reload and repeat all runtime checks.")
        expected = result["base_python"] if args.stage == "part1" else result["python"]
        if args.python != expected:
            raise ValueError("Interpreter argument differs from the validated runtime. Restart the operation in RHIM.")
    except ValueError as error:
        print("Operation not started: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
