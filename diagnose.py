import re
import subprocess

__version__ = '0.0.1'


##################################################
# General Utility Functions

def match_pats(pats, text):
    matches = (pat.search(text) for pat in pats)
    return [m.groups() for m in matches if m is not None]


def convert_value(value):
    try:
        value = float(value)
    except ValueError:
        return value
    else:
        if int(value) == value:
            return int(value)
        return value


def get_info(infodict, line):
    out = {}
    for key, pat in infodict.items():
        match = re.search(pat, line)
        if match:
            out[key] = convert_value(match.group(1))
    return out


def get_table(header, lines, separator=None):
    return [{k: convert_value(v) for (k, v) in zip(header, l.split(separator))}
            for l in lines if l]


##################################################
# Classes

class Valid(object):
    def __init__(self, min=None, max=None, equal=None, isin=None):
        self.min, self.max, self.equal, self.isin = min, max, equal, isin

    def __call__(self, value):
        notnone = lambda v: v is not None
        if ((notnone(self.min) and value < self.min)
                or (notnone(self.max) and value > self.max)
                or (notnone(self.equal) and value != self.equal)
                or (notnone(self.isin) and self.isin not in value)):
            return False
        return True


class Failure(object):
    def __init__(self, cmd, failures):
        self.cmd = cmd
        self.failures = failures

    def __repr__(self):
        header = 'FAIL [{}]:\n'.format(self.cmd)
        lines = ['  {}'.format(l) for l in self.failures]
        return header + '\n'.join(lines)


class Skip(object):
    def __init__(self, cmd, process=None):
        '''
        :str cmd: command to call
        :func process: process function that returns True for skipping.
            If left None, item is skipped if cmd returns a string of
            the form r'^/.*/cmd$'
        '''
        self.cmd = cmd

        def default_process(text):
            return not re.search(r'^/.*{}$'.format(cmd.split()[1]), text.decode())
        self.process = process or default_process

    def __call__(self):
        output = self._call_subprocess().strip()
        return self.process(output)

    def _call_subprocess(self):
        return subprocess.check_output(self.cmd, shell=True)


class Diagnose(object):
    """Class to handle diagnostics from a command"""
    def __init__(self, cmd, fail_pats=None, success_pats=None,
                 devices=None, process=None, skip=None,
                 fail_on_output=False):
        '''
        :str cmd: the command to run to diagnose. Can have {device} in it for each device
        :str devices: command to run to get relevant devices. Will be split by newline
        :list fail_pats: list of regular expression patterns that command output FAILS on
        :func process: function to process each output INSTEAD of running through patterns.
            function should return a list of str matches that failed or an empty list
        '''
        self.cmd = cmd
        self.devices = devices
        self.process = process
        self._skip = skip
        self.fail_on_output = fail_on_output

        def format_pat(pat):
            if '(' not in pat and ')' not in pat:
                pat = '(' + pat + ')'
            pat = pat.encode()
            return pat

        if fail_pats:
            self.fail_pats = [re.compile(format_pat(f), re.S + re.M) for f in fail_pats]
        else:
            self.fail_pats = None

        if success_pats:
            self.success_pats = [re.compile(format_pat(f), re.S) for f in success_pats]
        else:
            self.success_pats = None

    def __call__(self):
        failed = []
        for cmd, output in self._call_subprocess():
            matches = []
            if self.fail_on_output and output:
                matches.append(repr(output[:80]) + '...')
            if self.success_pats:
                if not match_pats(self.success_pats, output):
                    matches.append(repr(output[:80]) + '...')
            if self.process:
                matches.extend(self.process(output))
            if self.fail_pats:
                matches.extend(match_pats(self.fail_pats, output))
            if matches:
                failed.append(Failure(cmd, matches))
        return failed

    def _call_subprocess(self):
        if self.devices:
            devices = subprocess.check_output(self.devices, shell=True).split(b'\n')
            devices = (d.strip() for d in devices)
            devices = [d.decode() for d in devices if d]
            commands = [self.cmd.format(device=d) for d in devices]
        else:
            commands = [self.cmd]
        return [(cmd, subprocess.check_output(cmd, shell=True)) for cmd in commands]

    @property
    def skip(self):
        return self._skip() if self._skip else False


##################################################
# Special parsing functions

def process_SMART_hdd(stdout):
    lines = stdout.decode().split('\n')
    failures = []
    name, value, raw = 'ATTRIBUTE_NAME', 'VALUE', 'RAW_VALUE'
    expected = {
        'Media_Wearout_Indicator': {value: Valid(min=10)},
        'Current_Pending_Sector': {raw: Valid(max=20)},
    }
    header_line = next(i for (i, l) in enumerate(lines) if 'ID#' in l)
    table = get_table(lines[header_line].split(), lines[header_line + 1:])
    table = [r for r in table if r[name] in expected]
    for row in table:
        for value_name, valid in expected[row[name]].items():
            if not valid(row[value_name]):
                failures.append('{} {}'.format(row[name], row[value_name]))
    return failures


def process_free_mem(stdout):
    stdout = stdout.decode()
    failures = []
    stdout = [l.strip() for l in stdout.split('\n') if l.strip()]
    header = [h.lower() for h in ['type'] + stdout[0].split()[:3]]
    mem = get_table(header, [stdout[1]])[0]
    if mem['used'] * 1.0 / mem['total'] > 0.90:
        failures.append('mem usage > 90%')
    if len(stdout) > 2:  # swap exists
        swap = get_table(header, [stdout[2]])[0]
        if swap['total'] and swap['used'] * 1.0 / swap['total'] > 0.25:
            failures.append('swap usage > 25%')
    return failures


def process_temperatures(stdout):
    stdout = stdout.decode().split('\n')
    failures = []
    infodict = {'temp': r'^[^:+\n]*:.*?([\d.]+)',
                'high': r'\(.*high\s*=\s*\+?([\d.]+)',
                'crit': r'\(.*crit\s*=\s*\+?([\d.]+)'}
    for line in stdout:
        linfo = get_info(infodict, line)
        if not linfo:
            continue
        temp = linfo.get('temp')
        if not temp:
            continue
        high = list(filter(None, (linfo.get('high'), linfo.get('crit'))))
        high = min(high) if high else 105
        if temp > high:
            failures.append(line)
    return failures


##################################################
# System Diagnostics definitions

drive_devices = "ls /dev/sd* | grep -P '^/dev/sd[a-z]+$'"

system_diagnostics = {
    # System Journals
    'dmesg':
        Diagnose('dmesg',
                 fail_pats=[r'UncorrectableError',  # drive has uncorrectable error
                            r'Remounting filesystem read-only',
                            r'hung_task_timeout_secs',               # kernel task hung
                            r'BUG: soft lockup',                     # kernel soft lockup
                            r'nfs: server [^\n]* not responding',    # NFS timeout
                            r'invoked oom-killer']),                 # Out of Memory
    'journalctl': Diagnose('journalctl -p 0 -xn', skip=Skip('which journalctl'),
                           success_pats=[r'^-- No entries --$']),

    # Services
    'systemctl': Diagnose('systemctl --failed', skip=Skip('which systemctl'),
                          fail_pats=[r'\sfailed\s']),

    # HDD / disk
    'hdparm':
        Diagnose('hdparm -I {device}', devices=drive_devices,
                 fail_pats=[r'Security:.*((?<!not)\slocked)',
                            r'Security:.*((?<!not)\sfrozen)',
                            r'(Checksum: (?!correct))']),
    'df': Diagnose('df', fail_pats=[r'((?:9[5-9]|100)%.*$)']),              # disk usage
    'df_inode': Diagnose('df -i', fail_pats=[r'((?:9[5-9]|100)%.*$)']),     # inode usage
    'smart': Diagnose('smartctl -A {device}', devices=drive_devices, process=process_SMART_hdd),

    # Network
    'iplink': Diagnose('ip link', fail_pats=['^\d+:.*state DOWN.*$']),
    'internet': Diagnose('ping -c 1 8.8.8.8', fail_pats=[r'0 received, 100% packet loss']),

    # Misc Hardware
    'memory': Diagnose('free -m', process=process_free_mem),
    'sensors': Diagnose('sensors', process=process_temperatures),
}


def main():
    for name, diagnose in system_diagnostics.items():
        if diagnose.skip:
            print("SKIP {}".format(name))
            continue
        failed = diagnose()
        if failed:
            print("FAIL {}: {}".format(name, failed))
        else:
            print("PASS {}".format(name))


if __name__ == '__main__':
    main()
