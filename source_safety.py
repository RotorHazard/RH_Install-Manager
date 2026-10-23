"""Source/data preparation for the standard RHIM unit. Python 3.6+, stdlib only."""
import argparse
import contextlib
import fcntl
import functools
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from urllib.parse import quote
from urllib.request import urlopen


class SafetyError(ValueError):
    pass


def inside(path, parent):
    return os.path.commonpath([os.path.realpath(path), os.path.realpath(parent)]) == os.path.realpath(parent)


def private_directory(path):
    if os.path.islink(path):
        raise SafetyError("Refusing symlink storage directory: " + path)
    os.makedirs(path, mode=0o700, exist_ok=True)
    if os.stat(path).st_uid != os.getuid() or stat.S_IMODE(os.stat(path).st_mode) & 0o077:
        raise SafetyError("Storage must be owned by the current user with mode 0700: " + path)


def state_path(home):
    return os.path.join(home, ".rhim_markers", "source-operation.json")


def read_state(home):
    path = state_path(home)
    if not os.path.lexists(path):
        return None
    if os.path.islink(path):
        raise SafetyError("Refusing symlink operation state: " + path)
    with open(path) as stream:
        value = json.load(stream)
    if (not isinstance(value, dict) or value.get("stage") not in ("part1", "part2", "update")
            or not isinstance(value.get("target"), str) or not isinstance(value.get("backup"), str)
            or not isinstance(value.get("data"), dict)
            or not all(isinstance(value["data"].get(key), str) for key in ("path", "real", "kind"))
            or type(value["data"].get("in_tree")) is not bool
            or not all(os.path.isabs(value["data"][key]) for key in ("path", "real"))):
        raise SafetyError("Invalid source recovery state. Inspect " + path)
    return value


def save_json(path, value):
    directory = os.path.dirname(path)
    fd, temporary = tempfile.mkstemp(prefix=".source-", dir=directory)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_state(home, value):
    save_json(state_path(home), value)


def fresh_pending(home, pending):
    path = os.path.join(home, ".rhim_markers", "rhim_config.json")
    if os.path.islink(path):
        raise SafetyError("Refusing symlink progress file: " + path)
    try:
        with open(path) as stream:
            markers = json.load(stream)
    except FileNotFoundError:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "rhim_config.json")) as stream:
            markers = json.load(stream)
    if not isinstance(markers, dict):
        raise SafetyError("Invalid installation progress: " + path)
    markers["fresh_install_pending"] = pending
    save_json(path, markers)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def lock_file(home):
    directory = os.path.join(home, ".rhim_markers")
    if os.path.islink(directory):
        raise SafetyError("Refusing symlink marker directory")
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = os.path.join(directory, "operation.lock")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    if os.fstat(fd).st_uid != os.getuid() or not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise SafetyError("Invalid operation lock owner/type")
    return fd


def inherited_lock(home):
    """An environment flag is never evidence of ownership of a lock."""
    try:
        fd = int(os.environ["RHIM_LOCK_FD"])
        expected = lock_file(home)
        try:
            actual = os.fstat(fd)
            wanted = os.fstat(expected)
            if fd == expected or (actual.st_dev, actual.st_ino) != (wanted.st_dev, wanted.st_ino):
                raise SafetyError("Inherited lock does not name this operation lock")
            try:
                fcntl.flock(expected, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            raise SafetyError("Inherited descriptor does not hold the operation lock")
        finally:
            os.close(expected)
    except (KeyError, OSError, ValueError) as error:
        raise SafetyError("Invalid inherited operation lock: {}".format(error))


@contextlib.contextmanager
def operation_lock(home):
    if "RHIM_LOCK_FD" in os.environ:
        yield inherited_lock(home)
        return
    fd = lock_file(home)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SafetyError("Another RHIM operation is running. Wait for it to finish.")
        os.set_inheritable(fd, True)
        os.environ["RHIM_LOCK_FD"] = str(fd)
        yield fd
    finally:
        os.environ.pop("RHIM_LOCK_FD", None)
        os.close(fd)


def locked_operation(function):
    @functools.wraps(function)
    def locked(*args, **kwargs):
        config = args[1] if function.__name__ == "installation" else args[0]
        try:
            with operation_lock("/home/" + config.user):
                return function(*args, **kwargs)
        except (OSError, ValueError) as error:
            print("Operation refused: {}".format(error))
            try:
                input("Press Enter to return to the menu.")
            except (EOFError, OSError):
                pass
            return False
    return locked


def resolve_data(home, source=None, read_source=None):
    """Read-only RH 4.4/4.5 precedence for the guarded standard working directory."""
    source = source or os.path.join(home, "RotorHazard")
    server = os.path.join(source, "src", "server")
    read_server = os.path.join(read_source, "src", "server") if read_source else server
    ini = os.path.join(read_server, "datapath.ini")
    default = os.path.join(home, "rh-data")
    if os.path.lexists(ini):
        with open(ini) as stream:
            first = stream.readline().strip()
        if not first:
            raise SafetyError("Empty datapath.ini. Choose an existing data directory explicitly: " + ini)
        # expanduser must use the configured user's home, not root's HOME under sudo.
        path = home + first[1:] if first == "~" or first.startswith("~/") else os.path.expanduser(first)
        path = os.path.abspath(os.path.join(server, path))
        kind = "ini"
    elif os.path.lexists(default):
        path, kind = default, "default"
    elif os.path.lexists(os.path.join(read_server, "config.json")):
        path, kind = server, "legacy"
    elif os.path.lexists(os.path.join(read_server, "database.db")):
        raise SafetyError("Legacy database exists without config.json at {}. Choose its data directory manually in datapath.ini before retrying.".format(server))
    else:
        path, kind = default, "prospective"
    real = os.path.realpath(path)
    inspected = path
    if read_source and inside(real, source):
        inspected = os.path.join(read_source, os.path.relpath(real, os.path.realpath(source)))
    if kind != "prospective" and not os.path.isdir(inspected):
        raise SafetyError("Data path is not an existing directory: " + path)
    protected = [os.path.join(home, name) for name in (".venv", ".rhim_markers", "rhim-backups", ".rhim-stage", "RH_Install-Manager")]
    if inside(home, real) or any(inside(real, item) or inside(item, real) for item in protected):
        raise SafetyError("Unsafe data directory overlaps home, runtime or RHIM storage: " + path)
    if inside(real, source) and real != os.path.realpath(server) and inside(server, real):
        raise SafetyError("Data directory contains program ancestors: " + path)
    if any(os.path.islink(path) for path in (source, os.path.join(source, "src"), server)):
        raise SafetyError("Source and server directories must not be symlinks; migrate explicitly")
    if os.path.islink(path) and inside(real, source):
        raise SafetyError("Data symlink points inside the source tree; choose a real directory explicitly: " + path)
    if (kind in ("default", "prospective") and os.path.lexists(os.path.join(read_server, "database.db"))
            and not os.path.lexists(os.path.join(read_server, "config.json"))
            and not any(os.path.lexists(os.path.join(inspected, name)) for name in ("config.json", "database.db"))):
        raise SafetyError("Legacy database would be hidden by empty rh-data. Choose the intended existing data directory in datapath.ini before retrying: " + server)
    for name in ("config.json", "database.db", "database.db-wal", "database.db-shm"):
        item = os.path.join(inspected, name)
        if os.path.lexists(item) and not os.path.isfile(item):
            raise SafetyError("Critical data entry is not a regular file or valid file link: " + item)
        if os.path.islink(item) and not (inside(os.path.realpath(item), real)
                                       or read_source and inside(os.path.realpath(item), inspected)):
            raise SafetyError("Critical data symlink escapes the selected data directory: {}. Choose the actual data directory explicitly before retrying.".format(item))
    return {"path": path, "real": real, "kind": kind, "in_tree": inside(real, source)}


def config_path(home):
    if read_state(home):
        raise SafetyError("Source recovery is pending. Retry the same source operation before configuring RH.")
    return os.path.join(resolve_data(home)["path"], "config.json")


def write_config(home, value):
    path = os.path.realpath(config_path(home))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".config-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=4)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(os.path.dirname(path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def apply_config_file(home, filename):
    with operation_lock(home):
        with open(filename) as stream:
            return write_config(home, json.load(stream))


def command(argv, **kwargs):
    result = subprocess.run(argv, **kwargs)
    if result.returncode:
        raise SafetyError("Command failed ({}): {}".format(result.returncode, " ".join(argv)))
    return result


def required_source(path):
    if any(os.path.islink(part) for part in (path, os.path.join(path, "src"), os.path.join(path, "src", "server"))):
        raise SafetyError("Prepared program directories must not be symlinks")
    for name in ("server.py", "requirements.txt"):
        candidate = os.path.join(path, "src", "server", name)
        if not os.path.isfile(candidate) or os.path.islink(candidate):
            raise SafetyError("Prepared source is missing a regular src/server/" + name)


def extract_zip(archive, destination):
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        roots = set()
        names = set()
        total = 0
        for member in members:
            name = member.filename
            parts = name.rstrip("/").split("/")
            mode = member.external_attr >> 16
            if (not name or "\\" in name or any(part in ("", ".", "..") for part in parts)
                    or name.startswith("/") or ":" in parts[0] or stat.S_ISLNK(mode)
                    or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))
                    or name.rstrip("/") in names):
                raise SafetyError("Unsafe or duplicate ZIP member: " + name)
            roots.add(parts[0])
            names.add(name.rstrip("/"))
            total += member.file_size
        if len(roots) != 1 or not members:
            raise SafetyError("RotorHazard archive must have exactly one root directory")
        disk_check(destination, total)
        if bundle.testzip() is not None:
            raise SafetyError("RotorHazard archive integrity check failed")
        bundle.extractall(destination)
        for member in members:
            if not member.filename.endswith("/"):
                # zipfile does not retain executable bits as unzip does.
                os.chmod(os.path.join(destination, member.filename), 0o644 | ((member.external_attr >> 16) & 0o111))
    root = os.path.join(destination, roots.pop())
    required_source(root)
    return root


def disk_check(path, needed, statvfs=os.statvfs):
    available = statvfs(path)
    if available.f_bavail * available.f_frsize < needed + 16 * 1024 * 1024:
        raise SafetyError("Insufficient free space for source and verified backups at " + path)


def tree_manifest(path):
    """Hash regular files and link text; record FIFO metadata without opening streams."""
    result = {}
    if not os.path.lexists(path):
        return result
    def visit(current, relative):
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode):
            result[relative] = ["link", os.readlink(current)]
        elif stat.S_ISDIR(info.st_mode):
            result[relative] = ["dir"]
            for name in sorted(os.listdir(current)):
                visit(os.path.join(current, name), os.path.join(relative, name))
        elif stat.S_ISFIFO(info.st_mode):
            result[relative] = ["fifo", stat.S_IMODE(info.st_mode), info.st_atime_ns, info.st_mtime_ns]
        elif stat.S_ISREG(info.st_mode):
            digest = hashlib.sha256()
            with open(current, "rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            result[relative] = ["file", info.st_size, digest.hexdigest()]
        else:
            raise SafetyError("Cannot preserve special file: " + current)
    visit(path, "")
    return result


def copy_file(source, destination):
    if stat.S_ISFIFO(os.lstat(source).st_mode):
        os.mkfifo(destination, stat.S_IMODE(os.lstat(source).st_mode))
        shutil.copystat(source, destination, follow_symlinks=False)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)
    return destination


def copy_verified(source, destination):
    if os.path.lexists(destination):
        raise SafetyError("Backup/copy destination already exists: " + destination)
    before = tree_manifest(source)
    if os.path.islink(source):
        os.symlink(os.readlink(source), destination)
    elif os.path.isdir(source):
        shutil.copytree(source, destination, symlinks=True, copy_function=copy_file)
    else:
        copy_file(source, destination)
    for relative, item in before.items():
        if item[0] == "file":
            copied_path = os.path.join(destination, relative) if relative else destination
            with open(copied_path, "rb") as stream:
                os.fsync(stream.fileno())
    for relative, item in sorted(before.items(), reverse=True):
        if item[0] == "dir":
            sync_directory(os.path.join(destination, relative))
    if tree_manifest(source) != before or tree_manifest(destination) != before:
        raise SafetyError("Copy verification failed: " + destination)
    return before


def prepare_source(home, target, method):
    root = os.path.join(home, ".rhim-stage")
    private_directory(root)
    if os.stat(root).st_dev != os.stat(home).st_dev:
        raise SafetyError("Source staging must be on the same filesystem as the installation")
    stage = tempfile.mkdtemp(prefix="source-", dir=root)
    try:
        if method == "git":
            if not shutil.which("git"):
                raise SafetyError("git is required. Install it before retrying.")
            source = os.path.join(stage, "source")
            command(["git", "clone", "--no-checkout", "--", "https://github.com/RotorHazard/RotorHazard.git", source])
            # Resolve only the selected tag or remote branch, never a local filename/expression.
            refs = []
            for ref in ("refs/tags/" + target, "refs/remotes/origin/" + target):
                result = subprocess.run(["git", "-C", source, "rev-parse", "--verify", ref + "^{commit}"],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                if result.returncode == 0:
                    refs.append(result.stdout.strip())
            if len(set(refs)) != 1:
                raise SafetyError("Selected Git ref is missing or ambiguous: " + target)
            revision = refs[0]
            command(["git", "-C", source, "checkout", "--detach", revision])
            actual = command(["git", "-C", source, "rev-parse", "HEAD"], stdout=subprocess.PIPE,
                             universal_newlines=True).stdout.strip()
            if actual != revision:
                raise SafetyError("Git checkout does not match selected ref")
        else:
            archive = os.path.join(stage, "source.zip")
            with urlopen("https://codeload.github.com/RotorHazard/RotorHazard/zip/" + quote(target, safe="/"), timeout=60) as response:
                with open(archive, "wb") as stream:
                    shutil.copyfileobj(response, stream)
            source = extract_zip(archive, stage)
            revision = "zip-sha256:" + tree_manifest(archive)[""][2]
            os.unlink(archive)
        required_source(source)
        return stage, source, revision
    except BaseException:
        shutil.rmtree(stage)
        raise


def stop_and_confirm(service_present, source, data):
    if service_present:
        command(["sudo", "systemctl", "stop", "rotorhazard.service"])
        result = command(["systemctl", "show", "rotorhazard.service", "--property=ActiveState,SubState,MainPID"],
                         stdout=subprocess.PIPE, universal_newlines=True)
        fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if fields.get("ActiveState") not in ("inactive", "failed") or fields.get("MainPID") != "0":
            raise SafetyError("RotorHazard did not stop completely. No data was copied.")
    # Inspect privileged/manual writers too; ordinary users cannot inspect root process fds.
    command(["sudo", "/usr/bin/python3", "-I", "-B", os.path.abspath(__file__),
             "check-writers", source, data["real"]])


def assert_no_writers(source, data, proc="/proc"):
    if not os.path.isdir(proc):
        raise SafetyError("Cannot inspect server writers without Linux /proc. No data was copied.")
    protected = (os.path.realpath(source), data["real"])
    for pid in os.listdir(proc):
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        directory = os.path.join(proc, pid)
        try:
            with open(os.path.join(directory, "cmdline"), "rb") as stream:
                args = stream.read().replace(b"\0", b" ").decode("utf-8", "replace")
            words = args.split()
            server_arguments = [word for word in words if os.path.basename(word) == "server.py"]
            if server_arguments or ("-m" in words and "server" in words):
                cwd = os.readlink(os.path.join(directory, "cwd"))
                if inside(cwd, source) or any(word.startswith("/") and inside(word, source) for word in server_arguments):
                    raise SafetyError("Possible manual RotorHazard writer PID {}. Stop it explicitly before retrying.".format(pid))
            # Database/file writers started by plugins also prevent a consistent backup.
            fd_dir = os.path.join(directory, "fd")
            for fd in os.listdir(fd_dir):
                try:
                    path = os.readlink(os.path.join(fd_dir, fd))
                except FileNotFoundError:
                    continue
                if path.startswith("/") and any(inside(path, root) for root in protected):
                    raise SafetyError("Process {} has an open RH source/data file. Close it before retrying.".format(pid))
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            raise SafetyError("Cannot inspect possible RH writer PID " + pid + ". Restore privileged /proc access before retrying.")


def make_backup(home, source, data):
    root = os.path.join(home, "rhim-backups")
    private_directory(root)
    if os.stat(root).st_dev != os.stat(home).st_dev:
        raise SafetyError("Backup storage must be on the source filesystem for checked source moves")
    manifests = {}
    for label, path in (("source", source), ("data", data["real"])):
        if os.path.lexists(path):
            manifests[label] = tree_manifest(path)
    needed = sum(item[1] for manifest in manifests.values() for item in manifest.values() if item[0] == "file")
    disk_check(home, needed * 2)
    backup = tempfile.mkdtemp(prefix="operation-", dir=root)
    try:
        for label, path in (("source", source), ("data", data["real"])):
            if label in manifests:
                copied = copy_verified(path, os.path.join(backup, label))
                if copied != manifests[label]:
                    raise SafetyError("Data changed while backing up: " + path)
        save_json(os.path.join(backup, "manifest.json"), manifests)
        sync_directory(backup)
    except BaseException as error:
        try:
            shutil.rmtree(backup)
        except OSError as cleanup_error:
            raise SafetyError("Incomplete backup retained at {}. Copy error: {}. Cleanup error: {}".format(backup, error, cleanup_error)) from error
        raise SafetyError("Backup failed at {}; incomplete copy removed: {}".format(backup, error)) from error
    print("Protected RH backup: " + backup, flush=True)
    return backup


USER_PATHS = ("config.json", "database.db", "database.db-wal", "database.db-shm", "cfg_bkp", "db_bkp", "logs", "static/user", "static/image")


def overlay(source, destination, conflicts, relative="", data_only=False):
    """Data wins; bundled program conflicts stay new and are reported in the backup."""
    for name in sorted(os.listdir(source)):
        rel = os.path.join(relative, name)
        if name in (".git", "__pycache__") or name.endswith(".pyc"):
            continue
        old, new = os.path.join(source, name), os.path.join(destination, name)
        if re.fullmatch(r"src/server/\.lgd-nfy[0-9]+", rel) and stat.S_ISFIFO(os.lstat(old).st_mode):
            continue
        user_relative = rel[len("src/server/"):] if rel.startswith("src/server/") else ""
        wins = data_only or any(user_relative == path or user_relative.startswith(path + os.sep) for path in USER_PATHS)
        if not os.path.lexists(new):
            copy_verified(old, new)
        elif (user_relative == "static/image" or user_relative.startswith("static/image/")) and (
                os.path.isdir(old) and not os.path.islink(old) and os.path.isdir(new) and not os.path.islink(new)):
            overlay(old, new, conflicts, rel, data_only)
        elif wins:
            if os.path.islink(new) or not os.path.isdir(new):
                os.unlink(new)
            else:
                shutil.rmtree(new)
            copy_verified(old, new)
        elif os.path.isdir(old) and not os.path.islink(old) and os.path.isdir(new) and not os.path.islink(new):
            overlay(old, new, conflicts, rel, data_only)
        elif tree_manifest(old) != tree_manifest(new):
            conflicts.append(rel)


def no_link_parents(path, root):
    current = os.path.dirname(path)
    while current != root:
        if not inside(current, root) or os.path.islink(current):
            raise SafetyError("Data destination has a symlink/escaping ancestor: " + path)
        current = os.path.dirname(current)


def restore_to_stage(home, new_source, backup, data):
    old_source = os.path.join(backup, "source")
    conflicts = []
    if os.path.isdir(old_source):
        for relative, entry in tree_manifest(old_source).items():
            if entry[0] == "fifo" and not re.fullmatch(r"src/server/\.lgd-nfy[0-9]+", relative):
                raise SafetyError("Unknown FIFO preserved in backup, manual merge required: " + relative)
        overlay(old_source, new_source, conflicts)
    if data["in_tree"]:
        relative = os.path.relpath(data["real"], os.path.realpath(os.path.join(home, "RotorHazard")))
        destination = os.path.join(new_source, relative)
        no_link_parents(destination, new_source)
        if data["real"] != os.path.realpath(os.path.join(home, "RotorHazard", "src", "server")):
            if os.path.lexists(destination):
                if os.path.islink(destination) or not os.path.isdir(destination) or os.listdir(destination):
                    # The source overlay may already have copied this data directory verbatim.
                    if tree_manifest(destination) != tree_manifest(os.path.join(backup, "data")):
                        raise SafetyError("In-tree data conflicts with new program path: " + relative)
            else:
                os.makedirs(destination)
            overlay(os.path.join(backup, "data"), destination, conflicts, data_only=True)
    if data["real"] == os.path.realpath(os.path.join(home, "RotorHazard", "src", "server")) and os.path.isdir(old_source):
        for relative in USER_PATHS:
            original = os.path.join(old_source, "src", "server", relative)
            restored = os.path.join(new_source, "src", "server", relative)
            if os.path.lexists(original):
                no_link_parents(restored, new_source)
            if os.path.lexists(original):
                before, after = tree_manifest(original), tree_manifest(restored)
                preserved = (all(after.get(name) == entry for name, entry in before.items())
                             if relative == "static/image" else before == after)
                if not preserved:
                    raise SafetyError("Could not preserve user data in prepared source: " + relative)
    if data["in_tree"]:
        relative_data = os.path.relpath(data["real"], os.path.realpath(os.path.join(home, "RotorHazard")))
        for name in ("config.json", "database.db", "database.db-wal", "database.db-shm"):
            original = os.path.join(data["real"], name)
            if os.path.islink(original):
                relative_target = os.path.relpath(os.path.realpath(original), data["real"])
                saved = os.path.join(backup, "data", relative_target)
                restored = os.path.join(new_source, relative_data, relative_target)
                no_link_parents(restored, new_source)
                if tree_manifest(saved) != tree_manifest(restored):
                    raise SafetyError("Critical data link target conflicts with prepared program files: " + original)
    # Preserve the ini literally. Relative paths retain their meaning at the final source path.
    ini = os.path.join(old_source, "src", "server", "datapath.ini")
    if os.path.lexists(ini):
        destination = os.path.join(new_source, "src", "server", "datapath.ini")
        if os.path.lexists(destination):
            os.unlink(destination)
        copy_verified(ini, destination)
    with open(os.path.join(backup, "conflicts.txt"), "w") as stream:
        stream.write("\n".join(conflicts) + ("\n" if conflicts else ""))
    if conflicts:
        print("Old program conflicts retained in backup/source, new bundled files kept. See " + os.path.join(backup, "conflicts.txt"))


def switch_source(home, staged, backup, state=None):
    live = os.path.join(home, "RotorHazard")
    previous = None
    if os.path.lexists(live):
        previous = tempfile.mkdtemp(prefix="previous-", dir=backup)
        os.rmdir(previous)
    if state is not None:
        state["previous"] = previous
        state["phase"] = "switching"
        save_state(home, state)
    if previous is not None:
        os.rename(live, previous)
        sync_directory(backup)
        sync_directory(home)
    try:
        os.rename(staged, live)
        sync_directory(home)
    except BaseException:
        if previous is not None and not os.path.lexists(live):
            os.rename(previous, live)
        raise
    return previous


def validate_backup(home, state):
    backup = state["backup"]
    root = os.path.join(home, "rhim-backups")
    if not inside(backup, root) or os.path.islink(backup) or os.path.dirname(backup) != root:
        raise SafetyError("Unsafe recovery backup path. Inspect " + state_path(home))
    with open(os.path.join(backup, "manifest.json")) as stream:
        manifests = json.load(stream)
    for label, manifest in manifests.items():
        if label not in ("source", "data") or tree_manifest(os.path.join(backup, label)) != manifest:
            raise SafetyError("Recovery backup verification failed: " + backup)
    return backup


def cleanup_old(home):
    pending = read_state(home)
    if pending:
        print("Protected pending recovery: {}. Backup: {}".format(state_path(home), pending["backup"]))
        raise SafetyError("Recovery is pending; cleanup is refused")
    # Review is useful even after part 1 or before a completion receipt exists.
    paths = [os.path.join(home, "rhim-backups"), os.path.join(home, ".rhim-stage")]
    paths += [os.path.join(home, name) for name in sorted(os.listdir(home)) if name.startswith("RotorHazard_")]
    print("Retained paths for manual review:")
    for path in paths:
        if os.path.lexists(path):
            print("  " + path)
        if path in paths[:2] and os.path.isdir(path) and not os.path.islink(path):
            for name in sorted(os.listdir(path)):
                print("    " + os.path.join(path, name))
    print("Nothing was deleted. Keep pending recovery copies and the last verified backup. See docs/source-data-safety.md before manual cleanup.")
    return True


def activation_identity(source):
    required_source(source)
    info = os.stat(source)
    return {"device": info.st_dev, "inode": info.st_ino,
            "program": {name: tree_manifest(os.path.join(source, "src", "server", name))
                        for name in ("server.py", "requirements.txt")}}


def check_activation(home, state):
    validate_backup(home, state)
    live = os.path.join(home, "RotorHazard")
    if state.get("phase") not in ("activated", "completed"):
        raise SafetyError(
            "Interrupted source switch; automatic retry cannot choose current data safely. "
            "Stop all RH writers. Keep live {}, prepared {}, previous {}, and verified backup {}. "
            "Compare these copies, preserve current external data at {}, then follow the manual recovery steps "
            "in docs/source-data-safety.md. Do not delete {} to force a retry.".format(
                live, state.get("prepared"), state.get("previous"), state["backup"],
                state["data"]["path"], state_path(home)))
    if activation_identity(live) != state.get("source_identity"):
        raise SafetyError("Activated source identity changed. Keep {} and {} and follow manual recovery in docs/source-data-safety.md.".format(live, state["backup"]))
    actual = resolve_data(home)
    if any(actual[key] != state["data"][key] for key in ("path", "real", "in_tree")):
        raise SafetyError("Activated data path changed. Restore the recorded path only after reviewing current data: " + state_path(home))


def run_operation(home, stage, user, target, method, executable, accept_unknown=False):
    # Isolated CLI mode omits the script directory from sys.path.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from runtime_preflight import check_runtime
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts",
                          {"part1": "install_rh_part_1.sh", "part2": "install_rh_part_2.sh", "update": "update_rh.sh"}[stage])
    with operation_lock(home) as fd:
        state = read_state(home)
        if state and (state["stage"] != stage or state["target"] != target):
            raise SafetyError("Unfinished {} for {}. Retry that exact operation first. Recovery: {}".format(state["stage"], state["target"], state_path(home)))
        if state:
            check_activation(home, state)
        runtime = check_runtime(user, target, stage, (lambda prompt: "yes") if accept_unknown else None)
        expected = runtime["base_python"] if stage == "part1" else runtime["python"]
        if executable != expected:
            raise SafetyError("Interpreter argument differs from validated runtime")
        if runtime.get("pending_daemon_reload"):
            command(["sudo", "systemctl", "daemon-reload"])
            runtime = check_runtime(user, target, stage, (lambda prompt: "yes") if accept_unknown else None)
            if runtime.get("pending_daemon_reload"):
                raise SafetyError("systemd still reports pending unit changes after daemon-reload. Review the service explicitly.")
        data = state["data"] if state else resolve_data(home)
        backup = state["backup"] if state else None
        live = os.path.join(home, "RotorHazard")
        if os.path.ismount(live):
            raise SafetyError("Source is a mount point. Plan an explicit source migration.")
        stage_root = None
        try:
            if state is None:
                stage_root, prepared, revision = prepare_source(home, target, method)
                stop_and_confirm(runtime["service_present"], live, data)
                if resolve_data(home) != data:
                    raise SafetyError("Effective data path changed during preparation. Review it before retrying.")
                backup = make_backup(home, live, data)
                state = {"stage": stage, "target": target, "backup": backup, "data": data,
                         "revision": revision, "prepared": prepared,
                         "fresh_install": runtime.get("fresh_install", False)}
                restore_to_stage(home, prepared, backup, data)
                if resolve_data(home, read_source=prepared)["real"] != data["real"]:
                    raise SafetyError("Prepared source resolves a different data path. Review selected source and backup: " + backup)
                env = dict(os.environ, RHIM_SOURCE_PAYLOAD="host", RHIM_PREPARED_SOURCE=prepared)
                command(["bash", script, user, target, method, executable] + (["--accept-unknown"] if accept_unknown else []),
                        env=env, pass_fds=(fd,))
                current_runtime = check_runtime(user, target, stage, (lambda prompt: "yes") if accept_unknown else None)
                if current_runtime["create_venv"]:
                    raise SafetyError("The expected venv is still missing after host preparation. Repair it explicitly before retrying.")
                print("Post-package RotorHazard runtime verified: Python {}.{}.{} at {}".format(
                    *current_runtime["version"], current_runtime["python"]))
                if stage != "part1":
                    stop_and_confirm(runtime["service_present"], live, data)
                    with open(os.path.join(backup, "manifest.json")) as stream:
                        manifests = json.load(stream)
                    for label, path in (("source", live), ("data", data["real"])):
                        if tree_manifest(path) != manifests.get(label, {}):
                            raise SafetyError("{} changed after backup. Live data was not replaced. Retry for a new backup; retained copy: {}".format(path, backup))
                    if runtime.get("fresh_install"):
                        fresh_pending(home, True)
                    state["source_identity"] = activation_identity(prepared)
                    switch_source(home, prepared, backup, state)
                    state["phase"] = "activated"
                    save_state(home, state)
            if stage != "part1":
                check_activation(home, state)
                stop_and_confirm(runtime["service_present"], live, data)
                env = dict(os.environ, RHIM_SOURCE_PAYLOAD="activate", RHIM_PREPARED_SOURCE=live)
                command(["bash", script, user, target, method, executable] + (["--accept-unknown"] if accept_unknown else []),
                        env=env, pass_fds=(fd,))
                configured = check_runtime(user, target, stage, (lambda prompt: "yes") if accept_unknown else None)
                if not configured["service_present"] or configured.get("pending_daemon_reload"):
                    raise SafetyError("Source activation finished without a checked, loaded service. Recovery remains pending.")
                fresh_pending(home, False)
            state["phase"] = "completed"
            save_json(os.path.join(home, ".rhim_markers", "source-completed.json"), state)
            if os.path.exists(state_path(home)):
                os.unlink(state_path(home))
            sync_directory(os.path.join(home, ".rhim_markers"))
            print(("Host preparation completed; source activation is pending. " if stage == "part1" else "Checked source activation completed. ") + "Source: {}. Data: {}. Ref: {}. Backup: {}".format(
                live, data["path"], state["revision"], backup))
        except BaseException:
            print("Operation incomplete. RotorHazard may be stopped. Verified backup: {}. Pending state: {}".format(
                backup or "none; see backup error above", state_path(home) if os.path.exists(state_path(home)) else "none; retry takes a new backup"), file=sys.stderr)
            raise
        finally:
            pending = read_state(home)
            if stage_root and not (pending and pending.get("phase") == "switching"):
                shutil.rmtree(stage_root)


def check_tools(stage, method):
    tools = ["bash", "sudo", "systemctl", "apt", "apt-get", "dpkg", "sed", "grep"]
    tools += ["git"] if method == "git" else []
    missing = [name for name in tools if not shutil.which(name)]
    if missing:
        raise SafetyError("Install required tools before retrying: " + ", ".join(missing))


def execute(stage, user, target, method, executable, accept_unknown=False):
    check_tools(stage, method)
    return run_operation("/home/" + user, stage, user, target, method, executable, accept_unknown)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check-writers":
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("command")
        parser.add_argument("source")
        parser.add_argument("data")
        args = parser.parse_args()
        try:
            assert_no_writers(args.source, {"real": args.data})
            return 0
        except (OSError, ValueError) as error:
            print("Cannot confirm quiescent RH data: {}".format(error), file=sys.stderr)
            return 1
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("stage", choices=("part1", "part2", "update", "verify-lock"))
    parser.add_argument("user")
    parser.add_argument("target", nargs="?")
    parser.add_argument("method", nargs="?", default="")
    parser.add_argument("python", nargs="?")
    parser.add_argument("--accept-unknown", action="store_true")
    args = parser.parse_args()
    try:
        if args.stage == "verify-lock":
            inherited_lock("/home/" + args.user)
        else:
            execute(args.stage, args.user, args.target, args.method, args.python, args.accept_unknown)
        return 0
    except (OSError, ValueError, shutil.Error, zipfile.BadZipFile) as error:
        print("Source/data operation failed: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
