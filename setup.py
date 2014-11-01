#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys

if any((x in sys.argv for x in ('develop','bdist'))):
    # use setuptools for develop, but nothing else
    from setuptools import setup
    Command = object
else:
    from distutils.core import setup, Command

with open('README.rst') as file:
    long_description = file.read()

#with open('CHANGES') as file:
#    long_description += file.read()

__version__ = ""
execfile('pyradex/version.py') # sets version

#import os
#if not os.path.exists('pyradex/radex/radex.so'):
#    import install_radex
#    install_radex.install_radex()

class InstallRadex(Command):
    """
    Compile the f2py radex modules needed for the python wrapper
    """

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import install_radex
        install_radex.install_radex()

class BuildRadexExecutable(Command):
    """
    Create the files radex_sphere, radex_lvg, radex_slab in the Radex/bin/
    directory
    """

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import install_radex
        install_radex.build_radex_executable()


class InstallFjdu(Command):
    """
    Compile Fujun Du's "myradex"
    """
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        cwd = os.getcwd()
        os.chdir('myRadex')
        os.system('make wrapper')
        os.chdir(cwd)
        for fn in ('wrapper_my_radex.pyf', 'wrapper_my_radex.so'):
            try:
                os.link('myRadex/{0}'.format(fn), 'pyradex/fjdu/{0}'.format(fn))
            except OSError as ex:
                if ex.errno == 17:
                    # file exists
                    pass
                else:
                    raise ex


import subprocess
import shutil
import os

class PyTest(Command):

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):

        if os.path.exists('build'):
            shutil.rmtree('build')
        #errno1 = subprocess.call(['py.test','--genscript=runtests.py'])
        errno2 = subprocess.call([sys.executable, 'runtests.py'])
        raise SystemExit(errno2)

setup(name='pyradex',
      version=__version__,
      description='Python-RADEX',
      long_description=long_description,
      author='Adam Ginsburg & Julia Kamenetzky',
      author_email='adam.g.ginsburg@gmail.com',
      url='http://github.com/keflavich/pyradex/',
      packages=['pyradex','pyradex.radex','pyradex.tests'],
      package_data={'pyradex.radex':['radex.so'],
                    'pyradex.fjdu':['wrapper_my_myradex.so'],
                    'pyradex.tests':['data/example.out']},
      requires=['requests', 'astroquery', ],
      install_requires=['astropy>=0.4.1', 'requests>=2.4.1',],
      cmdclass={'test': PyTest,
                'install_radex': InstallRadex,
                'build_radex_exe': BuildRadexExecutable,
                'install_myradex': InstallFjdu,
                'install_fjdu': InstallFjdu,
               },
      #include_package_data=True,
      )
