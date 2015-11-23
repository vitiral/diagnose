from __future__ import print_function

import os
from contextlib import contextmanager


pjoin = os.path.join
__path__ = os.path.split(os.path.abspath(os.path.expanduser(__file__)))[0]
ex = pjoin(__path__, 'examples')


@contextmanager
def mock_dg(obj, result_path, name='mocked'):
    def _call_subprocesses():
        with open(result_path, 'rb') as f:
            return [(name, f.read())]
    original = obj._call_subprocesses
    try:
        obj._call_subprocesses = _call_subprocesses
        yield
    finally:
        obj._call_subprocesses = original


def run_tests(tests):
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
