#!/usr/bin/env python
#
# Copyright (c) 2011 Ivan Zakrevsky and contributors.
import os.path
from setuptools import setup, find_packages

app_name = os.path.basename(os.path.dirname(os.path.abspath(__file__)))

setup(
    name = app_name,
    version = '0.7.1',

    packages = find_packages(),

    author = "Ivan Zakrevsky",
    author_email = "ivzak@yandex.ru",
    description = "SmartSQL - lightweight sql builder.",
    long_description=open(os.path.join(os.path.dirname(__file__), 'README.rst')).read(),
    license = "BSD License",
    keywords = "SQL database",
    classifiers = [
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    url = "https://bitbucket.org/evotech/{0}".format(app_name),
)
