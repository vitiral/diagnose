from __future__ import print_function

import time
import glob
from contextlib import contextmanager
import diagnose as dg

from .utils import pjoin, ex, run_tests


@contextmanager
def mock_long(obj, result_path, name='mocked'):
    class Popen(object):
        def kill(self):
            raise RuntimeError("kill called")

        def communicate(self):
            with open(result_path, 'rb') as f:
                return f.read(), None

        def poll(self):
            return True

    def _popen_all():
        return [(name, Popen())]

    original = obj._popen_all
    original_checkers = obj.checkers
    original_sleep = time.sleep
    try:
        time.sleep = lambda t: None
        obj._popen_all = _popen_all
        obj.checkers = []
        yield
    finally:
        obj._popen_all = original
        obj.checkers = original_checkers
        time.sleep = original_sleep


class LongTest(object):
    def __init__(self, key):
        self.key = key

    def __call__(self):
        key = self.key
        obj = dg.long_system_diagnostics[key]
        for test_file in glob.glob(pjoin(ex, key) + '.pass*'):
            print('.', end='')
            with mock_long(obj, test_file, key):
                result = obj()
                assert not result

        for test_file in glob.glob(pjoin(ex, key) + '.fail*'):
            print('.', end='')
            with mock_long(obj, test_file, key):
                result = obj()
                assert result

tests = [
    LongTest('cpu_burn'),
    LongTest('mem_burn'),
    LongTest('smart_test'),
]


def test_():
    run_tests(tests)
