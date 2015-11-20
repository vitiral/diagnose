import re
import subprocess


def match_pats(pats, text):
    matches = (pat.search(text) for pat in pats)
    return [m.groups() for m in matches if m is not None]


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
            If left None, item is skipped if cmd returns any value
        '''
        self.cmd = cmd
        self.process = process

    def __call__(self):
        output = self._call_subprocess().strip()
        if self.process:
            return self.process(output)
        else:
            return bool(output)  # typical use case is just 'which cmd'

    def _call_subprocess(self):
        return subprocess.check_output(self.cmd)


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
            devices = subprocess.check_output(self.devices, shell=True).split('\n')
            devices = (d.strip() for d in devices)
            devices = [d for d in devices if d]
            commands = [self.cmd.format(device=d) for d in devices]
        else:
            commands = [self.cmd]
        return [(cmd, subprocess.check_output(cmd, shell=True)) for cmd in commands]

    @property
    def skip(self):
        return self._skip() if self._skip else False


def process_free_mem(stdout):
    failures = []
    stdout = [l.strip() for l in stdout.split('\n') if l.strip()]
    header, mem = stdout[:2]
    header = [h.lower() for h in header.split()[:2]]
    mem = dict(zip(header, mem.split()[1:3]))
    if mem['used'] * 1.0 / mem['total'] > 0.90:
        failures.append('mem usage > 90%')
    if len(stdout) > 2:  # swap exists
        swap = stdout[2]
        swap = dict(zip(header, swap.split()[1:3]))
        if swap['total'] and swap['used'] * 1.0 / swap['total'] > 0.25:
            failures.append('swap usage > 25%')
    return failures


system_diagnostics = {
    'hdparm':
        Diagnose('hdparm -I {device}', devices="ls /dev/sd* | grep -P '^/dev/sd[a-z]+$'",
                 fail_pats=[r'Security:.*((?<!not)\slocked)',
                            r'Security:.*((?<!not)\sfrozen)',
                            r'(Checksum: (?!correct))']),
     'iplink': Diagnose('ip link', fail_pats=['^\d+:.*state DOWN.*$']),
     'dmesg':
        Diagnose('dmesg',
                 fail_pats=[r'UncorrectableError',  # drive has uncorrectable error
                            r'Remounting filesystem read-only',
                            r'hung_task_timeout_secs',               # kernel task hung
                            r'BUG: soft lockup',                     # kernel soft lockup
                            r'nfs: server [^\n]* not responding',    # NFS timeout
                            r'invoked oom-killer']),                 # Out of Memory
    'df': Diagnose('df', fail_pats=[r'((?:9[5-9]|100)%.*$)']),              # disk usage
    'df_inode': Diagnose('df -i', fail_pats=[r'((?:9[5-9]|100)%.*$)']),     # inode usage
    'memory': Diagnose('free -m', process=process_free_mem),
    'internet': Diagnose('ping -c 1 8.8.8.8', fail_pats=[r'0 received, 100% packet loss']),
    'systemctl': Diagnose('systemctl --failed', skip=Skip('which systemctl'),
                          fail_pats=[r'\sfailed\s']),
    'journalctl': Diagnose('journalctl -p 0..2 -xn', skip=Skip('which journalctl'),
                           success_pats=[r'^-- No entries --$'])
}


if __name__ == '__main__':
    for name, diagnose in system_diagnostics.items():
        if diagnose.skip:
            print("SKIP {}".format(name))
            continue
        failed = diagnose()
        if failed:
            print("FAIL {}: {}".format(name, failed))
        else:
            print("PASS {}".format(name))
