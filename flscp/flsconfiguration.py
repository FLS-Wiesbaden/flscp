from observer import ObservableSubject
from configparser import SafeConfigParser, NoSectionError
from collections import OrderedDict
import json

class FLSConfiguration(SafeConfigParser, ObservableSubject):
	STATE_CHANGED = 'configChanged'
	STATE_LOADED  = 'configLoaded'

	def __init__(self, configFile = None):
		ObservableSubject.__init__(self)
		SafeConfigParser.__init__(self)
		self._configFile = configFile
		if self._configFile is not None:
			self.load()

	def _cleanup(self):
		self._proxies = OrderedDict()
		self._sections = OrderedDict()

	def loadJson(self, data):
		#import rpdb2; rpdb2.start_embedded_debugger('test')
		newConf = SafeConfigParser()
		try:
			config = json.loads(data)
		except ValueError as e:
			raise e

		try:
			for kSec, vSec in config.items():
				try:
					newConf.add_section(kSec)
				except NoSectionError:
					pass

				for kVal, vVal in vSec.items():
					try:
						newConf.set(kSec, kVal, str(vVal['value']))
					except NoSectionError as e:
						pass
		except Exception as e:
			#import rpdb2; rpdb2.start_embedded_debugger('test')
			print(e)

		# now replace
		self._proxies = newConf._proxies
		self._sections = newConf._sections

		self.notify(FLSConfiguration.STATE_CHANGED)

	def toJson(self):
		cfg = {}

		for sec in self.sections():
			cfg[sec] = {}
			for opt in self.options(sec):
				cfg[sec][opt] = self.get(sec, opt)

		return json.dumps(cfg)

	def load(self):
		if self._configFile is not None:
			self.read([self._configFile])
			self.notify(FLSConfiguration.STATE_LOADED)

	def save(self):
		if self._configFile is not None:
			with open(self._configFile, 'w') as f:
				self.write(f)

			# uhh we notify about changes!
			self.notify(FLSConfiguration.STATE_CHANGED)
