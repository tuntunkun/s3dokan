#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# S3 Dokan Pipeline Generator
# Copyright (c)2014-2018 Takuya Sawada.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#      http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
# See the License for the specific language governing permissions and
# limitations under the License.
# 
from setuptools import setup

setup(
	name = 's3dokan',
	version='0.3.0',
	description='S3Dokan Pipeline Generator',
	author='Takuya Sawada',
	author_email='takuya@tuntunkun.com',
	url='https://github.com/tuntunkun/s3dokan',
	license='Apache License 2.0',
	packages = ['s3dokan'],
	install_requires = [
		'argparse==1.3.0',
		'boto==2.36.0',
		'awscli==1.7.15'
	],
	classifiers = {
		'Development Status :: 4 - Beta',
		'Environment :: Console',
		'Operating System :: POSIX',
		'Programming Language :: Python',
		'Programming Language :: Python :: 2',
		'Topic :: System :: Networking',
		'Topic :: Utilities'
	},
	entry_points = {
		'console_scripts': [
			's3dokan=s3dokan:main'
		]
	}
)
