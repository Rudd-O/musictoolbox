#!/usr/bin/python3

from setuptools import setup
import os
import glob

dir = os.path.dirname(__file__)
path_to_main_file = os.path.join(dir, "lib/musictoolbox/__init__.py")
path_to_readme = os.path.join(dir, "README.md")
for line in open(path_to_main_file):
	if line.startswith('__version__'):
		version = line.split()[-1].strip("'").strip('"')
		break
else:
	raise ValueError('"__version__" not found in "lib/musictoolbox/__init__.py"')
readme = open(path_to_readme).read(-1)

classifiers = [
'Development Status :: 3 - Alpha development',
'Environment :: Console',
'Intended Audience :: End Users/Desktop',
'License :: OSI Approved :: GNU General Public License (GPL)',
'Operating System :: POSIX :: Linux',
'Programming Language :: Python :: 2 :: Only',
'Programming Language :: Python :: 2.7',
'Topic :: Utilities',
]

setup(
	name = 'musictoolbox',
	version=version,
	description = 'A set of utilities to help you groom your music collection',
	long_description = readme,
	author='Manuel Amador (Rudd-O)',
	author_email='rudd-o@rudd-o.com',
	license="GPL",
	url = 'http://github.com/Rudd-O/musictoolbox',
	package_dir=dict([
					("musictoolbox", "lib/musictoolbox"),
					]),
	classifiers = classifiers,
	packages = ["musictoolbox"],
	scripts = [ f for f in glob.glob(os.path.join("bin","*")) if not f.endswith("~") ],
	keywords = "mp3",
	requires = ["Twisted"],
	zip_safe=False,
)
