#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: fenc=utf-8:ts=8:sw=8:si:sta:noet
import configparser, os
try:
	import pyinotify
	notifyInstalled = True
except:
	import dummyinotify as pyinotify
	notifyInstalled = False

DEFAULT_CLIENT_CONFIGS = {
	'options': {
		'hostselection': False,
		'defaulthost': 'flswiesbaden',
		'currenthost': ''
	},
	'hosts': {
		'flswiesbaden': 'flswiesbaden',
		'lschreiner': 'lschreiner'
	},
	'flswiesbaden': {
		'name': 'Friedrich-List-Schule Wiesbaden',
		'host': 'cp.fls-wiesbaden.de',
		'port': 10027,
		'rpcpath': 'RPC2',
		'keyfile': 'certs/clientKey.pem',
		'certfile': 'certs/clientCert.pem',
		'cacert': 'certs/cacert.pem'
	},
	'lschreiner': {
		'name': 'Lukas Schreiner',
		'host': 'cp.lschreiner.de',
		'port': 10027,
		'rpcpath': 'RPC2',
		'keyfile': 'certs/clientKey.pem',
		'certfile': 'certs/clientCert.pem',
		'cacert': 'certs/cacert.pem'
	}
}

class FLSConfig(configparser.ConfigParser):
	__instance = None
	mask = pyinotify.IN_CREATE | pyinotify.IN_MODIFY

	def __init__(self, defaults = None):
		super().__init__(defaults=defaults)
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

	def save(self, fileName):
		os.makedirs(os.path.dirname(fileName), exist_ok = True)
		with open(fileName, 'w') as f:
			self.write(f)

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
