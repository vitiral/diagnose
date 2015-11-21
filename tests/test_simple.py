from __future__ import print_function

import os
import glob
from contextlib import contextmanager
import unittest
import mock
import diagnose as dg

pjoin = os.path.join
__path__ = os.path.split(os.path.abspath(os.path.expanduser(__file__)))[0]
ex = pjoin(__path__, 'examples')


@contextmanager
def mock_dg(obj, result_path, name='mocked'):
    def _call_subprocess():
        with open(result_path, 'rb') as f:
            return [(name, f.read())]
    original = obj._call_subprocess
    try:
        obj._call_subprocess = _call_subprocess
        yield
    finally:
        obj._call_subprocess = original


class SimpleTest(object):
    def __init__(self, key):
        self.key = key

    def __call__(self):
        key = self.key
        obj = dg.system_diagnostics[key]
        for test_file in glob.glob(pjoin(ex, key) + '.pass*'):
            print('.', end='')
            with mock_dg(obj, test_file, key):
                result = obj()
                assert not result

        for test_file in glob.glob(pjoin(ex, key) + '.fail*'):
            print('.', end='')
            with mock_dg(obj, test_file, key):
                result = obj()
                assert result


tests = [
    SimpleTest('dmesg'),
    SimpleTest('systemctl'),
    SimpleTest('journalctl'),
    SimpleTest('hdparm'),
    SimpleTest('df'),
    SimpleTest('df_inode'),
    SimpleTest('iplink'),
    SimpleTest('internet'),
]


def test_do():
    print("Running tests:")
    for test in tests:
        print("Testing {}  ".format(test.key), end='')
        try:
            test()
        except:
            print("FAIL")
            raise
        else:
            print("PASS")
