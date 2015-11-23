from contextlib import contextmanager
from diagnose import Skip

from .utils import run_tests


@contextmanager
def mock_skip(obj, result):
    def _call_subprocess():
        return result
    original = obj._call_subprocess
    try:
        obj._call_subprocess = _call_subprocess
        yield
    finally:
        obj._call_subprocess = original


class SkipTest(object):
    def __init__(self, willskip, cmd, stdout):
        self.willskip = willskip
        self.key = cmd
        self.stdout = stdout

    def __call__(self):
        s = Skip(self.key)
        with mock_skip(s, self.stdout):
            assert s() == self.willskip


journalctl_stderr = (
    b'/usr/bin/which: no journalctl in (/usr/lib64/qt-3.3/bin:/usr/local/sbin:/usr/local/bin'
    b':/sbin:/bin:/usr/sbin:/usr/bin:/root/bin)')

tests = [
    SkipTest(False, 'which systemctl', (b'/usr/bin/systemctl', None, 0)),
    SkipTest(True, 'which systemctl', (b'systemctl not found', None, 0)),
    SkipTest(True, 'which journalctl', (b'', journalctl_stderr, 1)),
]


def test_():
    run_tests(tests)
