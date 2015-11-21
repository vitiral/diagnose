try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup
from diagnose import __version__

config = {
    'name': 'diagnose',
    'author': 'Garrett Berg',
    'author_email': 'vitiral@gmail.com',
    'version': __version__,
    'py_modules': ['diagnose'],
    'scripts': ['bin/diagnose'],
    'license': 'MIT',
    'description': "single tested python script for fast linux diagnostics",
    'url': "https://github.com/vitiral/diagnose",
    'classifiers': [
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7',
        'Topic :: Utilities',
    ]
}

setup(**config)
