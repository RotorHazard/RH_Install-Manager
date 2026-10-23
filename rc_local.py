#!/usr/bin/env python3
"""Maintain only RHIM's forwarding block in a simple rc.local script."""

import os
import re
import shlex
import stat
import sys
import tempfile


BEGIN = '# BEGIN RHIM PORT FORWARDING'
END = '# END RHIM PORT FORWARDING'
RULES = tuple('iptables -A PREROUTING -t nat -p tcp --dport {} -j REDIRECT --to-ports {}'.format(a, b)
              for a, b in ((80, 5000), (8080, 80)))
HEADERS = ('# [Port Forwarding - RH_Install-Manager]',
           '# [Port Forwarding \u2013 RH_Install-Manager]')
STOCK_IP_FRAGMENT = '''# Print the IP address
_IP=$(hostname -I) || true
if [ "$_IP" ]; then
  printf "My IP address is %s\\n" "$_IP"
fi
'''
BLOCK = '''{begin}
(
for rhim_ports in '80 5000' '8080 80'; do
    set -- $rhim_ports
    if iptables -C PREROUTING -t nat -p tcp --dport "$1" -j REDIRECT --to-ports "$2"; then
        :
    else
        rhim_status=$?
        if [ "$rhim_status" -ne 1 ]; then
            echo "RHIM: checking port $1 forwarding failed (status $rhim_status)" >&2
            exit "$rhim_status"
        fi
        iptables -A PREROUTING -t nat -p tcp --dport "$1" -j REDIRECT --to-ports "$2" || exit $?
    fi
done
) || exit $?
{end}
'''.format(begin=BEGIN, end=END)
MANUAL = ('Automatic rc.local configuration refused. Review /etc/rc.local manually, '
          'keep its existing commands, remove historical RHIM forwarding entries, and place the exact '
          'block below where startup will reach it, before the final exit and outside conditionals '
          'or functions. Verify syntax with the interpreter named in your script header. '
          'A subsequent run accepts this exact block without editing other commands; it does not '
          'verify startup reachability or application health. Until forwarding is configured, '
          'use server port 5000.\n' + BLOCK)


class ConfigError(Exception):
    pass


def refuse(reason):
    raise ConfigError('{} {}'.format(reason, MANUAL))


def render(content):
    if '\x00' in content:
        refuse('rc.local contains a NUL byte.')
    if '\r' in content:
        refuse('rc.local must use LF line endings, not CRLF.')
    if not content:
        return '#!/bin/sh\n\n' + BLOCK + '\nexit 0\n'
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].rstrip('\n') not in ('#!/bin/sh', '#!/bin/sh -e', '#!/bin/bash'):
        refuse('Unsupported shell header.')
    marked = [i for i, line in enumerate(lines)
              if 'BEGIN RHIM' in line or 'END RHIM' in line]
    insertion = None
    if marked:
        if (len(marked) != 2 or lines[marked[0]].rstrip('\n') != BEGIN or
                lines[marked[1]].rstrip('\n') != END):
            refuse('Invalid or duplicate RHIM markers.')
        insertion = marked[0]
        if ''.join(lines[marked[0]:marked[1] + 1]) == BLOCK:
            outside = lines[:marked[0]] + lines[marked[1] + 1:]
            historical = HEADERS + RULES + tuple('sudo ' + rule for rule in RULES)
            if any(line.strip() in historical for line in outside):
                refuse('Mixed historical and managed RHIM blocks.')
            # Exact manual placement is the operator's responsibility, including reachability.
            return content
        del lines[marked[0]:marked[1] + 1]

    # Only exact historical commands are ours; an unlabelled iptables-save is not.
    i = 1
    while i < len(lines):
        text = lines[i].strip()
        labelled = text in HEADERS
        start = i + 1 if labelled else i
        j = start
        while j + 1 < len(lines):
            pair = [line.strip() for line in lines[j:j + 2]]
            if all(value in (rule, 'sudo ' + rule) for value, rule in zip(pair, RULES)):
                j += 2
            else:
                break
        if j > start:
            if labelled and j < len(lines) and lines[j].strip() in ('iptables-save', 'sudo iptables-save'):
                j += 1
            if insertion is not None:
                refuse('Mixed historical and managed RHIM blocks.')
            del lines[i:j]
            continue
        if labelled or text in RULES or text in tuple('sudo ' + rule for rule in RULES):
            refuse('Incomplete historical RHIM block.')
        i += 1

    active = [i for i, line in enumerate(lines[1:], 1) if line.strip() and not line.lstrip().startswith('#')]
    if not active or lines[active[-1]].strip() != 'exit 0':
        refuse('A final standalone exit 0 is required.')
    exit_index = active[-1]
    # Recognize only the literal pi-gen IP display fragment, never general shell conditionals.
    validation = ''.join(lines)
    if validation.count(STOCK_IP_FRAGMENT) > 1:
        refuse('Duplicate stock IP display fragments.')
    validation = validation.replace(STOCK_IP_FRAGMENT, '\n' * STOCK_IP_FRAGMENT.count('\n'))
    validation_lines = validation.splitlines(keepends=True)
    # shortcut: accept only flat simple commands; compound shell scripts require manual editing.
    forbidden = {'exit', 'exec', 'eval', 'source', '.', 'return', 'break', 'continue', 'set',
                 'trap', 'alias', 'unalias', 'command', 'builtin', 'enable', 'if', 'then',
                 'else', 'elif', 'fi', 'for', 'while', 'until', 'do', 'done', 'case', 'esac',
                 'select', 'function', 'time', 'coproc', '!', 'export', 'readonly', 'unset',
                 '[[', ']]', 'in', 'logout'}
    for i in active[:-1]:
        line = validation_lines[i].strip()
        if not line:
            continue
        if any(char in line for char in ';|&<>(){}$`\\\r\x00'):
            refuse('Complex shell syntax on line {}.'.format(i + 1))
        try:
            words = shlex.split(line, comments=True, posix=True)
        except ValueError:
            refuse('Unrecognized shell quoting on line {}.'.format(i + 1))
        if not words or words[0] in forbidden or re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', words[0]):
            refuse('Unsupported shell command on line {}.'.format(i + 1))
    if insertion is not None and insertion > exit_index:
        refuse('RHIM block follows exit 0.')
    lines.insert(exit_index if insertion is None else insertion, BLOCK)
    return ''.join(lines)


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_mode, info.st_uid, info.st_gid, info.st_nlink)


def snapshot(path):
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None, None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        refuse('rc.local must be a regular file with one link.')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if identity(info) != identity(os.fstat(stream.fileno())):
            refuse('rc.local changed while opening it.')
        content = stream.read()
        if identity(info) != identity(os.fstat(stream.fileno())):
            refuse('rc.local changed while reading it.')
    return info, content


def verify(path, info, content):
    current, data = snapshot(path)
    if data != content or (None if current is None else identity(current)) != (None if info is None else identity(info)):
        refuse('rc.local changed concurrently; retry after reviewing the current file.')


def write_file(fd, content, info, mode):
    with os.fdopen(fd, 'wb') as stream:
        stream.write(content)
        stream.flush()
        if info is not None:
            os.fchown(stream.fileno(), info.st_uid, info.st_gid)
        os.fchmod(stream.fileno(), mode)
        os.fsync(stream.fileno())


def validate(path='/etc/rc.local'):
    info, content = snapshot(path)
    try:
        desired = render('' if content is None else content.decode('utf-8')).encode('utf-8')
    except UnicodeError:
        refuse('rc.local is not UTF-8 text.')
    return info, content, desired


def configure(path='/etc/rc.local'):
    info, content, desired = validate(path)
    mode = (stat.S_IMODE(info.st_mode) if info is not None else 0o755) | 0o111
    if desired == content:
        verify(path, info, content)
        if mode != stat.S_IMODE(info.st_mode):
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                if identity(os.fstat(fd)) != identity(info):
                    refuse('rc.local changed before updating permissions.')
                os.fchmod(fd, mode)
            finally:
                os.close(fd)
        return False
    directory = os.path.dirname(os.path.abspath(path))
    fd, temporary = tempfile.mkstemp(prefix='.rhim-rc-local-', dir=directory)
    try:
        write_file(fd, desired, info, mode)
        verify(path, info, content)
        if info is not None:
            first = path + '.iptables1_saved'
            try:
                backup_fd = os.open(first, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                try:
                    write_file(backup_fd, content, info, stat.S_IMODE(info.st_mode))
                except Exception:
                    os.unlink(first)
                    raise
            backup_fd, backup = tempfile.mkstemp(prefix=os.path.basename(path) + '.rhim-backup-', dir=directory)
            try:
                write_file(backup_fd, content, info, stat.S_IMODE(info.st_mode))
            except Exception:
                os.unlink(backup)
                raise
        verify(path, info, content)
        os.replace(temporary, path)
        temporary = None
        return True
    finally:
        if temporary is not None:
            os.unlink(temporary)


def main():
    try:
        configure()
    except (ConfigError, OSError) as error:
        print('Port forwarding persistence failed: {}'.format(error), file=sys.stderr)
        if not isinstance(error, ConfigError):
            print(MANUAL, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
