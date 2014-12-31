#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: fenc=utf-8:ts=8:sw=8:si:sta:noet
import configparser
try:
	import pyinotify
	notifyInstalled = True
except:
	import dummyinotify as pyinotify
	notifyInstalled = False

class FLSConfig(configparser.ConfigParser):
	__instance = None
	mask = pyinotify.IN_CREATE | pyinotify.IN_MODIFY

	def __init__(self):
		super().__init__()
		FLSConfig.__instance = self
		self.encoding = None
		self.notifyWm = None
		self.notifyHandler = None
		self.notifyNotifier = None

	def read(self, filenames, encoding=None):
		fname = super().read(filenames, encoding)
		if notifyInstalled:
			self.installNotifier(fname, filenames, encoding)
		return fname

	def installNotifier(self, loadedConfig, filenames, encoding):
		self.encoding = encoding

		if self.notifyWm is None:
			self.notifyWm = pyinotify.WatchManager()
		if self.notifyHandler is None:
			self.notifyHandler = FLSConfigHandler(self)
		if self.notifyNotifier is None:
			self.notifyNotifier = pyinotify.ThreadedNotifier(self.notifyWm, self.notifyHandler)
			self.notifyNotifier.start()
		try:
			wdd = self.notifyWm.add_watch(loadedConfig, FLSConfig.mask, rec=True)
		except:
			pass

	def configChanged(self, fname):
		self.read([fname], self.encoding)

	@staticmethod
	def getInstance():
		return FLSConfig.__instance

class FLSConfigHandler(pyinotify.ProcessEvent):

	def __init__(self, config):
		self.config = config

	def process_IN_CREATE(self, event):
		self.config.configChanged(event.pathname)

	def process_IN_MODIFY(self, event):
		self.config.configChanged(event.pathname)
