#!/usr/bin/python
'''
    diagnose --  single python script for short and long linux diagnostics

diagnose is a single python (2 or 3) script that checks a wide range of linux
(and possibly windows in the future) utilities to determine system health.

It's intended purpose is to be able to scp or curl it onto a computer and quickly determine
the health of that computer, such as:

    curl -L https://raw.githubusercontent.com/vitiral/diagnose/master/diagnose.py > diagnose
    sudo ./diagnose

It is written using a simple and easy to understand approach that is also easy to
test and extend. If you have new features or find any bugs, please visit:
    https://github.com/vitiral/diagnose

- diagnose is licensed under the MIT license by Garrett Berg (vitiral@gmail.com)
'''

from __future__ import print_function

import sys
import time
import re
import argparse
import subprocess
import threading
import logging

try:
    from collections import OrderedDict
except ImportError:
    class OrderedDict(tuple):
        '''A really terrible implementation of OrderedDict (for python < 2.7)'''
        def __new__(cls, constructor):
            items = tuple(constructor)
            values = tuple(n[1] for n in items)
            out = tuple.__new__(cls, (n[0] for n in items))
            out.keys = lambda: out
            out.items, out.values = lambda: items, lambda: values
            return out

        def __getitem__(self, key):
            try:
                return next(v for (k, v) in self.items() if k == key)
            except:
                raise KeyError(key)


def call_cmd(cmd, raise_on_error=True):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    rc = p.returncode
    if rc and raise_on_error:
        raise RuntimeError("Command [{0}] got rc {1}: stdout={2}\nstderr={3}".format(
                           cmd, rc, stdout, stderr))
    return stdout, stderr, rc

__version__ = '0.0.1'

logging.basicConfig(level=logging.DEBUG)
_log = logging.getLogger('diagnose')


##################################################
# General Utility Functions

def get_keys(dict, *keys):
    keys = set(keys)
    return OrderedDict((k, v) for (k, v) in dict.items() if k in keys)


def decode(data):
    return data.decode('utf-8')


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
    return [dict((k, convert_value(v)) for (k, v) in zip(header, l.split(separator)))
            for l in lines if l]


##################################################
# Classes

class Thread(threading.Thread):
    '''better thread with output and exception raising on join'''
    def __init__(self, *args, **kwargs):
        super(Thread, self).__init__(*args, **kwargs)
        self.output = None
        self.exc_info = None
        if not hasattr(self, '_target'):  # python2/3 compatibility
            self._target = self._Thread__target
            self._args = self._Thread__args
            self._kwargs = self._Thread__kwargs

    def run(self, *args, **kwargs):
        try:
            self.output = self._target(*self._args, **self._kwargs)
        except Exception:
            self.exc_info = sys.exc_info()

    def join(self, *args, **kwargs):
        super(Thread, self).join(*args, **kwargs)
        if self.exc_info:
            if sys.version_info[0] == 3:
                raise self.exc_info[0]
            else:
                exec('e=self.exc_info; raise e[0], e[1], e[2]')
        return self.output

    @classmethod
    def spawn(cls, target, *args, **kwargs):
        t = cls(target=target, args=args, kwargs=kwargs)
        t.daemon = kwargs.get('daemon', True)
        t.start()
        return t


class Valid(object):
    '''Useful for testing validity in a table'''
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
    '''Used for formatting failures'''
    def __init__(self, cmd, failures):
        self.cmd = cmd
        self.failures = failures

    def __repr__(self):
        header = 'FAIL [{0}]:\n'.format(self.cmd)
        lines = [' :: {0}'.format(l) for l in self.failures]
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
            return not re.search(r'^/[/\w]+/{0}$'.format(cmd.split()[1]), decode(text))
        self.process = process or default_process

    def __call__(self):
        out, _, rc = self._call_subprocess()
        if rc:
            return True
        return self.process(out.strip())

    def _call_subprocess(self):
        return call_cmd(self.cmd, raise_on_error=False)


class Diagnose(object):
    """Class to handle diagnostics from a command"""
    def __init__(self, cmd, skip_pats=None, fail_pats=None, pass_pats=None, fail_on_output=False,
                 process=None, devices=None, parallel=True, skip=None, requires=None, msg=''):
        '''
        :str cmd: the command to run to diagnose. Can have {device} in it for each device
            gotten from `devices`
        :list fail_pats: list of regular expression patterns that command output FAILS on
        :list pass_pats: list of regular expression patterns that command output FAILS if
            not true
        :bool fail_on_output: if true, fails on any non-empty output from call
        :func process: function to process each output function. Should return a
            list of str matches that failed or an empty list
        :str devices: command to run to get a list of devices (split by '\n')
        :Skip skip: skip function. Return True to skip
        :str requires: documentation for the package needed if skipped
        :str msg: message to display on PASS
        '''
        self.cmd = cmd
        self.devices = devices
        self.process = process
        self.parallel = parallel
        self._skip = skip
        self.requires = requires
        self.fail_on_output = fail_on_output
        self.msg = msg
        self.skip_pats_raw = skip_pats
        self.fail_pats_raw = fail_pats
        self.pass_pats_raw = pass_pats

        def format_pat(pat):
            if '(' not in pat and ')' not in pat:
                pat = '(' + pat + ')'
            pat = pat.encode()
            return pat

        self.skip_pats = [re.compile(format_pat(f), re.S) for f in skip_pats] if skip_pats else None
        self.fail_pats = [re.compile(format_pat(f), re.S + re.M) for f in fail_pats] if fail_pats else None
        self.pass_pats = [re.compile(format_pat(f), re.S) for f in pass_pats] if pass_pats else None

    def _find_failures(self, cmd, output):
        matches = []
        if self.fail_on_output and output:
            matches.append([repr(output[:80]) + '...'])
        if self.skip_pats:
            if match_pats(self.skip_pats, output):
                return []
        if self.pass_pats:
            if not match_pats(self.pass_pats, output):
                matches.append([repr(output[:80]) + '...'])
        if self.process:
            matches.extend(self.process(output))
        if self.fail_pats:
            matches.extend(match_pats(self.fail_pats, output))
        return [Failure(cmd, m) for m in matches]

    def __call__(self):
        failed = []
        for cmd, output in self._call_subprocesses():
            failures = self._find_failures(cmd, output)
            if failures:
                failed.extend(failures)
        return failed

    def _get_commands(self):
        if self.devices:
            if isinstance(self.devices, str):
                devices, _, _ = call_cmd(self.devices)
                devices = (d.strip() for d in devices.split(b'\n'))
                devices = [decode(d) for d in devices if d]
            else:
                devices = self.devices
            return [self.cmd.format(device=d) for d in devices]
        else:
            return [self.cmd]

    def _call_subprocesses(self):
        return [(cmd, call_cmd(cmd, raise_on_error=False)[0]) for cmd in self._get_commands()]

    @property
    def skip(self):
        return self._skip() if self._skip else False


class DiagnoseLong(Diagnose):
    ''' Diagnostic tool for long running tests, including ability to run Diagnostics side by side
        and fail if they fail. (i.e. for temperature monitoring during cpu stress test '''
    def __init__(self, cmd, checkers=None, loop_sleep=0.5, **kwargs):
        super(DiagnoseLong, self).__init__(cmd, **kwargs)
        self.checkers = checkers or []
        self.loop_sleep = loop_sleep

    def __call__(self):
        failures = []
        for cmd, process in self._popen_all():
            _log.debug("Starting long test: " + cmd)
            while process.poll() is None:
                for p in self.checkers:
                    failures.extend(p())
                if failures:
                    process.kill()
                    break
                time.sleep(self.loop_sleep)
            stdout, stderr = process.communicate()
            if stderr:
                _log.debug("stderr from {0}: {1}".format(cmd, stderr))
            failures.extend(self._find_failures(cmd, stdout))
            if failures:
                return failures

    def _popen_all(self):
        for cmd in self._get_commands():
            yield (cmd, subprocess.Popen(
                   cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))


##################################################
# Special parsing functions

def process_current_max(stdout):
    '''bash commands that return 'current\nnext' can use this'''
    fo, max = [int(re.search('(\d+)', l).group(1)) for l in decode(stdout).split('\n') if l]
    return [['file descriptor usage > 95%']] if fo * 1.0 / max > 0.95 else []


def process_free_mem(stdout):
    '''free -m processing'''
    stdout = decode(stdout)
    failures = []
    stdout = [l.strip() for l in stdout.split('\n') if l.strip()]
    header = [h.lower() for h in ['type'] + stdout[0].split()[:3]]
    mem = get_table(header, [stdout[1]])[0]
    if mem['used'] * 1.0 / mem['total'] > 0.90:
        failures.append(['mem usage > 90%'])
    if len(stdout) > 2:  # swap exists
        swap = get_table(header, [stdout[2]])[0]
        if swap['total'] and swap['used'] * 1.0 / swap['total'] > 0.25:
            failures.append(['swap usage > 25%'])
    return failures


def process_temperatures(stdout):
    '''sensors processing'''
    stdout = decode(stdout).split('\n')
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
        high = list(filter(None, (linfo.get('high'), linfo.get('crit', 10) - 10)))
        high = min(high) if high else 95
        if temp > high:
            failures.append([line])
    return failures


##################################################
# System Diagnostics definitions

drive_devices = "ls /dev/sd* | grep -P '^/dev/sd[a-z]+$'"

system_diagnostics = OrderedDict((
    # System Journals
    ('dmesg',
        Diagnose('dmesg', msg='no concerning error logs detected',
                 fail_pats=[r'UncorrectableError',  # drive has uncorrectable error
                            r'Hardware Error[^\n]*',
                            r'Remounting filesystem read-only',
                            r'hung_task_timeout_secs',               # kernel task hung
                            r'BUG: soft lockup',                     # kernel soft lockup
                            r'nfs: server [^\n]* not responding',    # NFS timeout
                            r'invoked oom-killer'])),                # Out of Memory
    ('journalctl', Diagnose('journalctl -p 0..3 -xn --since "-240"', skip=Skip('which journalctl'),
                            pass_pats=[r'^-- No entries --$'], requires='systemd',
                            msg='No emergency->error journals')),

    # Services + System
    ('systemctl', Diagnose('systemctl --failed', skip=Skip('which systemctl'),
                           fail_pats=[r'\sfailed\s'], msg='no failed services')),
    ('file_desc', Diagnose('lsof | wc -l && sysctl fs.file-max', skip=Skip('which lsof'),
                           process=process_current_max, requires='lsof',
                           msg='file descriptors < 95% usage')),
    ('threads', Diagnose("ps -eo nlwp | tail -n +2 | awk '{ num_threads += $1 }"
                         " END { print num_threads }' && bash -c 'ulimit -u'",
                         process=process_current_max, msg='threads < 95% usage')),

    # HDD / disk
    ('readonly', Diagnose('ls -ld /', pass_pats=[r'^drwx'], msg='/ is read+write+exec by root')),
    ('hdparm',
        Diagnose('hdparm -I {device}', devices=drive_devices,
                 fail_pats=[r'Security:.*((?<!not)\slocked)',
                            r'(Checksum: (?!correct))'],
                 msg='hardrives unlocked', skip=Skip('which hdparm'))),
    ('df', Diagnose('df', fail_pats=[r'((?:9[5-9]|100)%.*$)'], msg='disk usage < 95%')),

    ('df_inode', Diagnose('df -i', fail_pats=[r'((?:9[5-9]|100)%.*$)'], msg='inodes < 95%')),
    ('smart', Diagnose('smartctl -a {device}', devices=drive_devices,
                      skip_pats=[r'Device does not support Self Test logging'],
                      fail_pats=[r'(overall-health[^\n]*test result: (?!PASSED)[^\n]*)'],
                      pass_pats=[r'(Self-test execution status:\s*\(\s*0\s*\))'],
                      skip=Skip('which smartctl'), requires='smartmontools',
                      msg='drives in usable health')),

    # Network
    ('iplink', Diagnose('ip link', fail_pats=['^\d+:.*state DOWN.*$'], msg='network links up',
                        skip=Skip('which ip'))),
    ('internet', Diagnose('ping -c 1 8.8.8.8', fail_pats=[r'0 received, 100% packet loss'],
                          msg='connected to google DNS')),

    # Misc Hardware
    ('memory', Diagnose('free -m | grep "total\s*used\|Mem:\|Swap:"', process=process_free_mem, msg='mem < 90%, swap < 25%')),
    ('sensors', Diagnose('sensors', process=process_temperatures, requires='lm_sensors',
                        skip=Skip('which sensors-detect'), msg='temps look adequate')),
))


##################################################
# Main functions

cpu_checkers = [system_diagnostics['sensors'],
                Diagnose('dmesg', fail_pats=[r'Hardware Error[^\n]*'])]

long_system_diagnostics = OrderedDict((
    ('cpu_burn', DiagnoseLong("stress-ng --cpu '-1' --cpu-method {device} -t 60"
                              " --metrics-brief --maximize",
                              devices=['bitops', 'callfunc',                        # verification
                                       'decimal64', 'decimal128',                   # decimal
                                       'int128longdouble', 'in128decimal128',       # int
                                       'fft', 'hanoi', 'ackermann', 'matrixprod'],  # diverse
                             requires='stress-ng', fail_pats=['unsuccessful run completed'],
                             checkers=cpu_checkers, parallel=False)),
    ('mem_burn', DiagnoseLong("swapoff -a && stress-ng --vm '-1' --vm-method {device} -t 60 --maximize ; swapon -a",
                              devices=['zero-one', 'galpat-0', 'galpat-1', 'swap', 'modulo-x'],
                              requires='stress-ng', fail_pats=['unsuccessful run completed'],
                              checkers=cpu_checkers, parallel=False)),
    ('smart_test', DiagnoseLong('smartctl -t long {device} &&'               # start long test
                                ' while [ "$(smartctl -a {device} |'         # wait till it's done
                                ''' grep 'Self-test execution status.*in progress')" ];'''
                                ' do sleep 10; done; smartctl -a {device}', devices=drive_devices,
                                fail_pats=system_diagnostics['smart'].fail_pats_raw,
                                pass_pats=system_diagnostics['smart'].pass_pats_raw)),
))


def remove_skipped(diagnostics):
    new_diagnostics = []
    for name, diagnose in diagnostics.items():
        if diagnose.skip:
            requires = ': requires ' + diagnose.requires if diagnose.requires else ''
            print("SKIP {0}{1}".format(name, requires))
            continue
        new_diagnostics.append((name, diagnose))
    return OrderedDict(new_diagnostics)


def start_parallel_diagnostics(diagnostics):
    threads = []
    for name, diagnose in diagnostics.items():
        if diagnose.skip:
            requires = ': requires ' + diagnose.requires if diagnose.requires else ''
            print("SKIP {0}{1}".format(name, requires))
            continue
        threads.append(Thread.spawn(diagnose))
    return threads


def run_sequential_diagnostics(diagnostics):
    return [d() for d in diagnostics.values()]


def print_results(diagnostics, results):
    for name, diagnose, failed in zip(diagnostics, diagnostics.values(), results):
        if failed:
            print("FAIL {0}: {1}".format(name, failed))
        else:
            msg = ': ' + diagnose.msg if diagnose.msg else ''
            print("PASS {0}{1}".format(name, msg))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--short-names', nargs='+',
                        help='list the short diagnostics you want to run. Choices are: {0}'.
                        format(' '.join(system_diagnostics)))
    parser.add_argument('-S', '--short', action='store_true', help='run all short diagnostics')
    parser.add_argument('-l', '--long-names', nargs='+',
                        help='list the long diagnostics you want to run. Choices are: {0}'.
                        format(' '.join(long_system_diagnostics)))
    parser.add_argument('-L', '--long', action='store_true',
                        help='run all long diagnostics. These take 10s of minutes (up to an hour)'
                             ' and purposefully stress your system. Use these at your own risk!')
    parser.add_argument('--sequential', action='store_true', help='run ALL tests sequentially')
    args = parser.parse_args()

    # parse and run short tests
    short_tests = []
    if args.short:
        short_tests = list(system_diagnostics)
    elif args.short_names:
        short_tests = args.short_names
    if short_tests:
        diagnostics = get_keys(system_diagnostics, *short_tests)
        diagnostics = remove_skipped(diagnostics)
        if args.sequential:
            results = run_sequential_diagnostics(diagnostics)
        else:
            results = [t.join() for t in start_parallel_diagnostics(diagnostics)]
        print_results(diagnostics, results)

    # parse and run long tests
    long_tests = []
    if args.long:
        long_tests = list(long_system_diagnostics)
    elif args.long_names:
        long_tests = args.long_names
    if long_tests:
        print("# Running long tests, this could take a while...")
        diagnostics = get_keys(long_system_diagnostics, *long_tests)
        parallel, sequential = OrderedDict(), OrderedDict()
        for k, d in diagnostics.items():
            if d.parallel:
                parallel[k] = d
            else:
                sequential[k] = d
        if not args.sequential:
            parallel_threads = start_parallel_diagnostics(parallel)

        sequential_results = run_sequential_diagnostics(sequential)
        print_results(sequential, sequential_results)

        if args.sequential:  # cmd line override
            parallel_results = run_sequential_diagnostics(parallel)
        else:
            parallel_results = [t.join() for t in parallel_threads]
        print_results(parallel, parallel_results)


if __name__ == '__main__':
    main()
