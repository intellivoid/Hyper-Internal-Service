import pathlib
import re
import sys
from distutils.command.build_ext import build_ext
from distutils.errors import (
    CCompilerError,
    DistutilsExecError,
    DistutilsPlatformError,
)

from setuptools import Extension, setup

if sys.version_info < (3, 5, 3):
    raise RuntimeError("hyper_internal_service 3.x requires Python 3.5.3+")

here = pathlib.Path(__file__).parent

if (
    (here / '.git').exists() and
    not (here / 'vendor/http-parser/README.md').exists()
):
    print("Install submodules when building from git clone", file=sys.stderr)
    print("Hint:", file=sys.stderr)
    print("  git submodule update --init", file=sys.stderr)
    sys.exit(2)


# NOTE: makefile cythonizes all Cython modules

extensions = [Extension('hyper_internal_service._websocket', ['hyper_internal_service/_websocket.c']),
              Extension('hyper_internal_service._http_parser',
                        ['hyper_internal_service/_http_parser.c',
                         'vendor/http-parser/http_parser.c',
                         'hyper_internal_service/_find_header.c'],
                        define_macros=[('HTTP_PARSER_STRICT', 0)],
                        ),
              Extension('hyper_internal_service._frozenlist',
                        ['hyper_internal_service/_frozenlist.c']),
              Extension('hyper_internal_service._helpers',
                        ['hyper_internal_service/_helpers.c']),
              Extension('hyper_internal_service._http_writer',
                        ['hyper_internal_service/_http_writer.c'])]


class BuildFailed(Exception):
    pass


class ve_build_ext(build_ext):
    # This class allows C extension building to fail.

    def run(self):
        try:
            build_ext.run(self)
        except (DistutilsPlatformError, FileNotFoundError):
            raise BuildFailed()

    def build_extension(self, ext):
        try:
            build_ext.build_extension(self, ext)
        except (CCompilerError, DistutilsExecError,
                DistutilsPlatformError, ValueError):
            raise BuildFailed()


txt = (here / 'hyper_internal_service' / '__init__.py').read_text('utf-8')
try:
    version = re.findall(r"^__version__ = '([^']+)'\r?$",
                         txt, re.M)[0]
except IndexError:
    raise RuntimeError('Unable to determine version.')

install_requires = [
    'attrs>=17.3.0',
    'chardet>=2.0,<4.0',
    'multidict>=4.5,<5.0',
    'async_timeout>=3.0,<4.0',
    'yarl>=1.0,<2.0',
    'idna-ssl>=1.0; python_version<"3.7"',
    'typing_extensions>=3.6.5; python_version<"3.7"',
]


def read(f):
    return (here / f).read_text('utf-8').strip()

args = dict(
    name='hyper_internal_service',
    version=version,
    description='Async http client/server framework (asyncio)',
    long_description='\n\n'.join(read('README.md')),
    classifiers=[
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Development Status :: 5 - Production/Stable',
        'Operating System :: POSIX',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Topic :: Internet :: WWW/HTTP',
    ],
    author='Intellivoid Technologies',
    author_email='netkas@intellivoid.net',
    maintainer='Zi Xing Narrakas <netkas@intellivoid.net>',
    maintainer_email='netkas@intellivoid.net',
    url='https://github.com/intellivoid/Hyper-Internal-Service',
    project_urls={
        'GitHub: issues': 'https://github.com/intellivoid/Hyper-Internal-Service/issues',
        'GitHub: repo': 'https://github.com/intellivoid/Hyper-Internal-Service',
    },
    license='Apache 2',
    packages=['hyper_internal_service'],
    python_requires='>=3.5.3',
    install_requires=install_requires,
    include_package_data=True,
    ext_modules=extensions,
    cmdclass=dict(build_ext=ve_build_ext),
)

try:
    setup(**args)
except BuildFailed:
    print("************************************************************")
    print("Cannot compile C accelerator module, use pure python version")
    print("************************************************************")
    del args['ext_modules']
    del args['cmdclass']
    setup(**args)
