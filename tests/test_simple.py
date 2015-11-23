from __future__ import print_function

import glob
import unittest
import mock
import diagnose as dg

from .utils import pjoin, ex, mock_dg, run_tests


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
    # system logs
    SimpleTest('dmesg'),
    SimpleTest('journalctl'),
    # services
    SimpleTest('systemctl'),
    SimpleTest('file_desc'),
    SimpleTest('threads'),
    # hdd / disk
    SimpleTest('hdparm'),
    SimpleTest('df'),
    SimpleTest('df_inode'),
    SimpleTest('smart'),
    # network
    SimpleTest('iplink'),
    SimpleTest('internet'),
    # misc hardware
    SimpleTest('memory'),
    SimpleTest('sensors'),
]


def test_():
    run_tests(tests)
