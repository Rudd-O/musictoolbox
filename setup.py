#!/usr/bin/python3

import glob
import os

from setuptools import setup


directory = os.path.dirname(__file__)
path_to_main_file = os.path.join(directory, "lib/musictoolbox/__init__.py")
path_to_readme = os.path.join(directory, "README.md")
for line in open(path_to_main_file):
    if line.startswith("__version__"):
        version = line.split()[-1].strip("'").strip('"')
        break
else:
    raise ValueError('"__version__" not found in "lib/musictoolbox/__init__.py"')
readme = open(path_to_readme).read(-1)

classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: End Users/Desktop",
    "License :: OSI Approved :: GNU General Public License (GPL)",
    "Operating System :: POSIX :: Linux",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3.7",
    "Topic :: Utilities",
]

setup(
    name="musictoolbox",
    version=version,
    description="A set of utilities to help you groom your music collection",
    long_description=readme,
    long_description_content_type="text/markdown",
    author="Manuel Amador (Rudd-O)",
    author_email="rudd-o@rudd-o.com",
    license="GPL",
    url="http://github.com/Rudd-O/musictoolbox",
    package_dir=dict(
        [
            ("musictoolbox", "lib/musictoolbox"),
        ]
    ),
    classifiers=classifiers,
    packages=["musictoolbox",
              "musictoolbox.sync",
              "musictoolbox.transcoding",
              "musictoolbox.transcoding.codecs",
              "musictoolbox.cmd"],
    install_requires=[
        "mutagen",
        "Twisted",
        "packaging",
        "networkx",
        "pyxdg",
        "psutil",
    ],
    entry_points={
        "musictoolbox.transcoding.codecs": [
            "copy = musictoolbox.transcoding.codecs.basic:Copy",
        ]
    },
    scripts=[f for f in glob.glob(os.path.join("bin", "*")) if not f.endswith("~")],
    keywords="mp3 ogg mkv transcoding aac mp4 video flv flac",
    zip_safe=False,
)
