import re
import subprocess


class Failure(object):
    def __init__(self, cmd, failures):
        self.cmd = cmd
        self.failures = failures

    def __repr__(self):
        header = 'FAIL [{}]:\n'.format(self.cmd)
        lines = ['  {}'.format(l) for l in self.failures]
        return header + '\n'.join(lines)


class Diagnose(object):
    """Class to handle diagnostics from a command"""
    def __init__(self, cmd, devices=None, fail_pats=None):
        '''
        :str cmd: the command to run to diagnose. Can have {device} in it for each device
        :str devices: command to run to get relevant devices. Will be split by newline
        :list fail_pats: list of regular expression patterns that command output FAILS on
        '''
        self.cmd = cmd
        self.devices = devices
        flags = re.DOTALL
        self.fail_pats = [re.compile(f, flags) for f in fail_pats]

    def __call__(self):
        failed = []
        for cmd, output in self._call_subprocess():
            matches = (pat.search(output) for pat in self.fail_pats)
            matches = [m.groups() for m in matches if m is not None]
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


system_calls = {
    'hdparm':
        Diagnose('hdparm -I {device}', devices="ls /dev/sd* | grep -P '^/dev/sd[a-z]+$'",
                 fail_pats=[r'Security:.*((?<!not)\slocked)',
                            r'Security:.*((?<!not)\sfrozen)',
                            r'(Checksum: (?!correct))']),
     'iplink': Diagnose('ip link', fail_pats=['(^\d+:.*state DOWN.*$)']),
}


if __name__ == '__main__':
    for name, call in system_calls.items():
        failed = call()
        if failed:
            print("FAIL {}: {}".format(name, failed))
        else:
            print("PASS {}".format(name))
