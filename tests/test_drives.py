from __future__ import print_function

import os
from contextlib import contextmanager
import unittest
import mock
import diagnose as dg

pjoin = os.path.join
__path__ = os.path.split(os.path.abspath(os.path.expanduser(__file__)))[0]
ex = pjoin(__path__, 'examples')


@contextmanager
def mock_dg(obj, result_path):
    def _call_subprocess():
        with open(result_path) as f:
            return [('mocked', f.read())]
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
        obj = dg.system_calls[key]
        with mock_dg(obj, pjoin(ex, '{}.pass'.format(key))):
            result = obj()
            assert not result

        with mock_dg(obj, pjoin(ex, '{}.fail'.format(key))):
            result = obj()
            assert result


tests = [
    SimpleTest('hdparm'),
    SimpleTest('iplink'),
]


def test_do():
    print("Running tests:")
    for test in tests:
        print("Testing {:30}".format(test.key + '...'), end=' ')
        try:
            test()
        except:
            print("FAIL")
            raise
        else:
            print("PASS")
