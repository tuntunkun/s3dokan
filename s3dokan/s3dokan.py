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
import sys, re, signal, argparse
from multiprocessing import Pool
from cStringIO import StringIO
from pkg_resources import get_distribution

# AWS Official API
from botocore.session import Session
from boto.s3.connection import S3Connection
from boto.s3.key import Key

try:
	import argcomplete
	has_autocomplete = True
except:
	has_autocomplete = False


##
# Model
class Chunk(object):
	def __init__(self, index, data):
		self.index = index
		self.data = data
		self.size = len(data)

class ChunkRange(object):
	def __init__(self, size, bs):
		self.__size = size
		self.__bs = bs

	def __iter__(self):
		self.index = 0
		return self

	def next(self):
		if self.index == 0:
			self.start = 0
		else:
			self.start += self.__bs

		self.end = min(self.__size, self.start + self.__bs) -1
		self.index += 1

		if self.start > self.__size:
			raise StopIteration

		return self

	def __str__(self):
		return "%d %d %d" % (self.index, self.start, self.end)

##
# Parallel Upload/Download Task
class S3MultipartUploader(object):
	def __init__(self, bucket, key_name):
		self.__mpu = bucket.initiate_multipart_upload(key_name)

	def __call__(self, chunk):
		memory = StringIO(chunk.data)
		key = self.__mpu.upload_part_from_file(memory, chunk.index)
		memory.close()

	def cancel(self):
		self.__mpu.cancel_upload()

	def complete(self):
		self.__mpu.complete_upload()
		
class S3MultipartDownloader(object):
	def __init__(self, key):
		self.__key = key

	def __call__(self, crange):
		memory = StringIO()

		self.__key.get_contents_to_file(memory, {'Range': "bytes=%d-%d" % (crange.start, crange.end)})
		chunk = Chunk(crange.index, memory.getvalue())

		memory.close()
		return chunk

##
# Input Scatter
class ChunkedInputIterator(object):
	def __init__(self, istream, bs):
		self.__istream = istream
		self.__bs = bs
		self.__index = 0

	def __iter__(self):
		self.__iter = iter(lambda: self.__istream.read(self.__bs), '')

		return self

	def next(self):
		self.__index += 1
		return Chunk(self.__index, self.__iter.next())

## 
# Application Framework
class App(object):
	class ArgumentParser(argparse.ArgumentParser):
		def error(self, message):
			self._print_message('[31merror: %s[0m\n\n' % message)
			self.print_help()
			sys.exit(2)

		def _print_message(self, message, file=None):
			if message:
				sys.stderr.write(message)

	class VersionAction(argparse.Action):
		def __init__(
			self, option_strings, version_callback,
			dest=argparse.SUPPRESS,
			default=argparse.SUPPRESS,
			help="show program's version number and exit"):

			super(App.VersionAction, self).__init__(
				option_strings=option_strings,
				dest=dest,
				default=default,
				nargs=0,
				help=help)

			self.__version_callback = version_callback
	
		def __call__(self, parser, namespace, values, option_string=None):
			self.__version_callback()
			sys.exit(0)

	def __init__(self, argv):
		self.__argv = argv

	def _pre_init(self):
		self._parser = App.ArgumentParser()
		self._parser.add_argument('-v', '--version', action=App.VersionAction, version_callback=self.show_version, help='show version info')

	def _post_init(self, opts):
		pass

	def _init(self):
		self._pre_init()

		if has_autocomplete:
			# eval "$(register-python-argcomplete mime)"
			# Ref) https://pypi.python.org/pypi/argcomplete
			argcomplete.autocomplete(self._parser)

		opts = self._parser.parse_args(self.__argv[1:])
		self._post_init(opts)

	def _run(self):
		pass

	def show_version(self):
		pass

	def show_usage(self):
		self._parser.print_help()

	def __call__(self):
		try:
			self._init()
			self._run()
		except Exception, e:
			print >>sys.stderr, "[31m%s[0m" % e
			sys.exit(1)

##
# Application Implementation
class S3DokanApp(App):
	##
	# Context
	class Context(object):
		def __init__(self, profile=''):
			self.session = Session()
			self.session.profile = profile
	
		def getS3Connection(self):
			return S3Connection(
				self.session.get_config_variable('access_key'),
				self.session.get_config_variable('secret_key'))

	##
	# Argument Completer
	class ProfileCompleter(object):
		def __init__(self, parent):
			self.__parent = parent
		
		def __call__(self, prefix, **kwargs):
			profiles = self.__parent.ctx.session.available_profiles
			return (x for x in profiles if x.startswith(prefix))

	##
	# Argument Action
	class BlockSizeAction(argparse.Action):
		def __call__(self, parser, namespace, value, option_string=None):
			if not value in range(5, 4096):
				parser.error('invalid block size: must in range of 5-4096 MiB')
			else:
				setattr(namespace, self.dest, value)

	##
	# Abstract Command
	class SubCommand(object):
		def __init__(self, parent, name, help):
			parent._cmdmap[name] =self
			parser = parent._subparsers.add_parser(name, help=help)
			self._declare_args(parser)
			self.__parent = parent

		def getContext(self):
			return self.__parent.ctx

		def _declare_args(self, parser):
			parser.add_argument('s3url', metavar='<s3url>', help='接続先S3のURL 例) s3://bucket-name/key-name')

		def _prepare(self, opts):
			self.nproc = opts.nproc
			self.bs = opts.bs * 1024 * 1024

			match = re.search('^(s3)://([^/]+?)/(.*?)/?$', opts.s3url)
			if not match:
				raise Exception("invalid url format: '%s'" % opts.s3url)
			else:
				self.scheme = match.group(1)
				self.bucket_name = match.group(2)
				self.key_name = match.group(3)

		def _run(self):
			raise NotImplementedError()

		def __call__(self, opts):
			self._prepare(opts)
			self._run()

	class MultiprocessSubCommand(SubCommand):
		def __init_worker(self):
			signal.signal(signal.SIGINT, signal.SIG_IGN)

		def _prepare(self, opts):
			super(S3DokanApp.MultiprocessSubCommand, self)._prepare(opts)
			self.pool = Pool(self.nproc, self.__init_worker)

	##
	# Command Implementation
	class SinkCommand(MultiprocessSubCommand):
		def _run(self):
			conn = self.getContext().getS3Connection()
			bucket = conn.lookup(self.bucket_name)
	
			if not bucket:
				raise Exception("bucket not found: '%s'" % self.bucket_name)

			chunk_iter = ChunkedInputIterator(sys.stdin, self.bs)
			uploader = S3MultipartUploader(bucket, self.key_name)
	
			try:
				self.pool.imap_unordered(uploader, chunk_iter)
				self.pool.close()
				self.pool.join()

				uploader.complete()

			except KeyboardInterrupt:
				signal.signal(signal.SIGINT, signal.SIG_IGN)
				print >>sys.stderr, "[33mterminating...[0m"
				uploader.cancel()
				self.pool.terminate()
				sys.exit(1)

			except Exception, e:
				signal.signal(signal.SIGINT, signal.SIG_IGN)
				uploader.cancel()
				self.pool.terminate()
				raise

	class SourceCommand(MultiprocessSubCommand):
		def _run(self):
			conn = self.getContext().getS3Connection()
			bucket = conn.lookup(self.bucket_name)
	
			if not bucket:
				raise Exception("bucket not found: '%s'" % self.bucket_name)

			key = bucket.get_key(self.key_name)
			if not key:
				raise Exception("key not found: '%s'" % self.key_name)
	
			downloader = S3MultipartDownloader(key)
			
			try:
				for chunk in self.pool.imap(downloader, ChunkRange(key.size, self.bs)):
					sys.stdout.write(chunk.data)

				self.pool.close()
				self.pool.join()

			except KeyboardInterrupt:
				signal.signal(signal.SIGINT, signal.SIG_IGN)
				print >>sys.stderr, "[33mterminating...[0m"
				self.pool.terminate()
				sys.exit(1)

			except Exception, e:
				print >>sys.stderr, e
				signal.signal(signal.SIGINT, signal.SIG_IGN)
				self.pool.terminate()
				raise

	class ListCommand(SubCommand):
		def _run(self):
			conn = self.getContext().getS3Connection()
			bucket = conn.lookup(self.bucket_name)
	
			if not bucket:
				raise Exception("bucket not found: '%s'" % self.bucket_name)
	
			for key in filter(lambda x: not x.key.endswith('/') and x.key.startswith(self.key_name), bucket.list()):
				print key.key

	class SizeCommand(SubCommand):
		def _run(self):
			conn = self.getContext().getS3Connection()
			bucket = conn.lookup(self.bucket_name)
	
			if not bucket:
				raise Exception("bucket not found: '%s'" % self.bucket_name)
			
			key = bucket.get_key(self.key_name)
			if not key:
				raise Exception("key not found: '%s'" % self.key_name)
	
			print key.size

	def _pre_init(self):
		super(S3DokanApp, self)._pre_init()
		self.ctx = S3DokanApp.Context()

		self._cmdmap = {}

		# optional argument
		self._parser.add_argument('--profile', type=str, metavar='PROFILE', default='', help='profile name') \
			.completer = S3DokanApp.ProfileCompleter(self)
		self._parser.add_argument('--nproc', type=int, metavar='NPROC', default=8, help='number of process (default: 8)')
		self._parser.add_argument('--bs', type=int, action=S3DokanApp.BlockSizeAction, metavar='SIZE', default=5, help='block size (default: 5) [MiB]')

		self._subparsers = self._parser.add_subparsers(title='command', dest='command', metavar='<command>')

		# command
		S3DokanApp.SinkCommand(self,'sink', 'create pipe to s3 object from stdin')
		S3DokanApp.SourceCommand(self, 'source', 'create pipe from s3 object to stdout')
		S3DokanApp.ListCommand(self, 'list', 'enumerate s3 objects')
		S3DokanApp.SizeCommand(self, 'size', 'show size of existing s3 object')

	def _post_init(self, opts):
		super(S3DokanApp, self)._post_init(opts)
		self.ctx.session.profile = opts.profile
		self._opts = opts

	def _run(self):
		self._cmdmap[self._opts.command](self._opts)

	def show_version(self):
		print >>sys.stderr, "Copyrights (c)2014-2018 Takuya Sawada All rights reserved."
		print >>sys.stderr, "S3Dokan Wormhole Generator v%s" % get_distribution("s3dokan").version

##
# Entry Point
def main():
	try:
		app = S3DokanApp(sys.argv)()
	except Exception, e:
		print >>sys.stderr, "[31m%s[0m" % e
		sys.exit(1)
		
if __name__ == '__main__':
	main()
