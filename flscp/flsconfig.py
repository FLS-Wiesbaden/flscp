import configparser

class FLSConfig(configparser.ConfigParser):
	__instance = None

	def __init__(self):
		super().__init__()
		FLSConfig.__instance = self

	@staticmethod
	def getInstance():
		return FLSConfig.__instance