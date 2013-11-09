import abc
try:
	import mysql.connector
except:
	print('There is no database connection possible (server)')

import logging
from flsconfig import FLSConfig
try:
	import bsddb3 as bsddb
except:
	print('No SaslDatabase available!')

class Database(metaclass=abc.ABCMeta):
	__instance = None

	def __init__(self):
		self.db = None
		self.connected = False

	@staticmethod
	@abc.abstractmethod
	def getInstance():
		raise NotImplemented

	@abc.abstractmethod
	def connect(self):
		pass

	@abc.abstractmethod
	def close(self):
		pass

	def __del__(self):
		self.close()

class SaslDatabase(Database):
	__instance = None

	def __init__(self):
		super().__init__()
		SaslDatabase.__instance = self
		self.conf = FLSConfig.getInstance()
		self.log = logging.getLogger('flscp')

	@staticmethod
	def getInstance():
		if SaslDatabase.__instance is None:
			SaslDatabase()
		return SaslDatabase.__instance

	def connect(self):
		# already connected?
		if self.db is not None:
			try:
				self.db.get_open_flags()
				self.log.info('DB already connected!')
			except bsddb.db.DBError:
				pass
			else:
				self.connected = True
				return True

		try:
			self.db = bsddb.db.DB()
			self.db.open(self.conf.get('mailserver', 'sasldb'))
		except Exception as e:
			self.log.error('Could not connect to sasldb (%s)!' % (e,))
			self.connected = False
		else:
			self.log.info('Connected to sasldb!')
			self.connected = True

	def exists(self, key):
		if not self.connected:
			self.connect()

		return self.db.exists(key.encode('utf-8'))

	def get(self, key):
		if not self.connected:
			self.connect()

		return self.db.get(key.encode('utf-8'))

	def add(self, key, data):
		if not self.connected:
			self.connect()

		try:
			cx = self.db.cursor()
			cx.put(key.encode('utf-8'), data.encode('utf-8'), bsddb.db.DB_KEYFIRST)
			cx.close()
			self.db.sync()
			return True
		except:
			self.log.warning('Key could not be added to sasldb: %s' % (e,))
			return False

	def update(self, key, data):
		return self.add(key, data)

	def delete(self, key):
		if not self.connected:
			self.connect()

		try:
			self.db.delete(key.encode('utf-8'))
			return True
		except Exception as e:
			self.log.warning('Key could not be removed from sasldb: %s' % (e,))
			return False

	def close(self):
		if self.db is None:
			return
		
		try:
			self.db.sync()
			self.db.close()
		except:
			self.log.warning('DB Not closeable - already closed?')

	def __del__(self):
		super().__del__()
		SaslDatabase.__instance = None

class MailDatabase(Database):
	__instance = None

	def __init__(self):
		super().__init__()
		MailDatabase.__instance = self
		self.conf = FLSConfig.getInstance()
		self.log = logging.getLogger('flscp')

	@staticmethod
	def getInstance():
		if MailDatabase.__instance is None:
			MailDatabase()

		return MailDatabase.__instance

	def getCursor(self):
		if not self.connected or not self.db.is_connected():
			self.connect()

		try:
			return self.db.cursor()
		except mysql.connector.errors.OperationalError as e:
			self.log.error('Lost connection to mysql server (%s)' % (e,))
			# try to reconnect
			self.db.connected = False
			self.connect()
			if self.connected and self.db.is_connected():
				return self.db.cursor()
			else:
				self.log.error('Could not reconnect!')
				raise

	def commit(self):
		self.db.commit()

	def connect(self):
		if self.db is not None and self.db.is_connected() and self.connected:
			return True
		elif self.db is not None:
			# try to reconnect!
			try:
				self.db.reconnect()
			except mysql.connector.Error as err:
				if err.errno == mysql.connector.errorcode.ER_ACCESS_DENIED_ERROR:
					self.log.error('Your credentials for mysql database is wrong!')
				elif err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
					self.log.warning('Database does not exist!')
				else:
					self.log.error('Unknown error when connecting to mysql server: %s' % (err,))
			else:
				self.connected = True
				self.log.info('Reconnected to mysql database!')
		else:
			try:
				self.db = mysql.connector.connect(
					user=self.conf.get('database', 'user'), 
					password=self.conf.get('database', 'password'),
					host=self.conf.get('database', 'host'),
					port=self.conf.getint('database', 'port'),
					database=self.conf.get('database', 'name'),
				)
			except mysql.connector.Error as err:
				if err.errno == mysql.connector.errorcode.ER_ACCESS_DENIED_ERROR:
					self.log.error('Your credentials for mysql database is wrong!')
				elif err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
					self.log.warning('Database does not exist!')
				else:
					self.log.error('Unknown error when connecting to mysql server: %s' % (err,))
			else:
				self.connected = True
				self.log.info('Connected to mysql database!')

	def close(self):
		if self.connected and self.db.is_connected():
			try:
				self.db.close()
			except:
				pass

		self.log.info('Disconnected from mysql database!')

	def __del__(self):
		super().__del__()
		MailDatabase.__instance = None