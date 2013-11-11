import logging
import zlib
import uuid
import time
from PyQt4 import QtCore
from PyQt4.QtCore import pyqtSignal
from modules.domain import *

class DNSList:

	def __init__(self):
		self._items = []

	def add(self, item):
		self._items.append(item)

	def remove(self, obj):
		self._items.remove(obj)

	def __getitem__(self, key):
		return self._items[key]

	def __setitem__(self, key, value):
		self._items[key] = value

	def __delitem__(self, key):
		del(self._items[key])

	def __iter__(self):
		for f in self._items:
			yield f

	def __contains__(self, item):
		return True if item in self._items else False

	def __len__(self):
		return len(self._items)

	def iterTlds(self):
		for f in self._items:
			if f.parent is None:
				yield f

	def iterByDomain(self, domainId):
		for f in self._items:
			if f.domainId == domainId:
				yield f

	def removeByDomain(self, domainId):
		log = logging.getLogger('flscp')
		items = [f for f in self._items if f.domainId == domainId]
		log.debug('Found %i items to delete from dns list.' % (len(items),))
		for item in items:
			self.remove(item)

	def findById(self, id):
		item = None
		try:
			id = int(id)
		except:
			pass

		for f in self._items:
			if f.id == id:
				item = f
				break

		return item

class Dns(QtCore.QObject):
	stateChanged = pyqtSignal(str)

	STATE_OK = 'ok'
	STATE_CHANGE = 'change'
	STATE_CREATE = 'create'
	STATE_DELETE = 'delete'

	TYPE_MX = 'MX'
	TYPE_NS = 'NS'
	TYPE_SOA = 'SOA'
	TYPE_A = 'A'
	TYPE_AAAA = 'AAAA'
	TYPE_CNAME = 'CNAME'
	TYPE_TXT = 'TXT'
	TYPE_SPF = 'SPF'
	TYPE_SRV = 'SRV'

	def __init__(self, did = None):
		super().__init__()
		self.id = did
		self.domainId = ''
		self.key = ''
		self.type = ''
		self.prio = ''
		self.value = ''
		self.weight = 0
		self.port = 0
		self.dnsAdmin = None
		self.refreshRate = 7200
		self.retryRate = 1800
		self.expireTime = 1209600
		self.ttl = 3600
		self.state = ''

	def generateId(self):
		self.id = 'Z%s' % (str(zlib.crc32(uuid.uuid4().hex.encode('utf-8')))[0:3],)

	def create(self):
		# SOA entries are only allowed ONCE!
		if self.type == Dns.TYPE_SOA and self.exists():
			raise ValueError('Entry has to be UNIQUE!')

		# is it a valid domain?
		state, msg = self.validate()
		if not state:
			raise ValueError('No valid data given!')

		db = MailDatabase.getInstance()
		cx = db.getCursor()
		self.state = Dns.STATE_CREATE
		query = (
			'INSERT INTO dns (domain_id, dns_key, dns_type, dns_prio, dns_value, dns_weight, dns_port, dns_admin, \
			dns_refresh, dns_retry, dns_expire, dns_ttl, status) \
			VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'
		)
		cx.execute(
			query, 
			(
				self.domainId, self.key, self.type, self.prio, self.value, self.weight, self.port, self.dnsAdmin,
				self.refreshRate, self.retryRate, self.expireTime, self.ttl, self.state
			)
		)
		db.commit()

	def load(self):
		if self.id is None:
			return False

		state = False

		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = (
			'SELECT dns_id, domain_id, dns_key, dns_type, dns_value, dns_weight, dns_port, dns_admin, dns_refresh, \
			dns_retry, dns_expire, dns_ttl, status FROM dns WHERE dns_id = %s LIMIT 1'
		)
		try:
			cx.execute(query, (self.id,))
			(
				self.id, 
				self.domainId,
				self.key,
				self.type,
				self.value,
				self.weight,
				self.port, 
				self.dnsAdmin,
				self.refreshRate,
				self.retryRate,
				self.expireTime,
				self.ttl,
				self.state
			) = cx.fetchone()

		except Exception as e:
			state = False
		else:
			state = True
		finally:
			cx.close()

		return state

	def validate(self):
		state = True
		msg = {}

		if self.type == Dns.TYPE_SOA:
			if len(self.dnsAdmin.strip()) <= 0:
				msg['dnsAdmin'] = 'You have to set an DNS-Admin-Mail for SOA-Entry.'
				state = False
			if len(self.value.strip()) <= 0:
				msg['dnsAdmin'] = 'You have to set the primary DNS-Server for the Domain.'
				state = False

			try:
				int(self.refreshRate)
			except:
				msg['refreshRate'] = 'The refresh rate has to be a numerical value between 1200 and 43200 seconds.'
				state = False
			else:
				if int(self.refreshRate) > 43200 or int(self.refreshRate) < 1200:
					msg['refreshRate'] = 'The refresh rate has to be between 1200 and 43200 seconds.'
					state = False

			try:
				int(self.retryRate)
			except:
				msg['retryRate'] = 'The refresh rate has to be a numerical value between 180 and 2419200 seconds.'
				state = False
			else:
				if int(self.retryRate) > 2419200 or int(self.retryRate) < 180:
					msg['retryRate'] = 'The refresh rate has to be between 180 and 2419200 seconds.'
					state = False

			try:
				int(self.expireTime)
			except:
				msg['expireTime'] = 'The refresh rate has to be a numerical value between 1209600 and 2419200 seconds.'
				state = False
			else:
				if int(self.expireTime) > 2419200 or int(self.expireTime) < 1209600:
					msg['expireTime'] = 'The expire time has to be between 1209600 and 2419200 seconds.'
					state = False

			try:
				int(self.ttl)
			except:
				msg['ttl'] = 'The TTL has to be a numerical value between 60 and 2419200 seconds.'
				state = False
			else:
				if int(self.ttl) > 2419200 or int(self.ttl) < 60:
					msg['ttl'] = 'The TTL has to be between 60 and 2419200 seconds.'
					state = False

		return state, msg

	def generateDnsEntry(self):
		content = []
		# get Domain!
		try:
			d = DomainList.findById(self.domainId)
			if d is None:
				d = Domain(self.domainId).load()
		except KeyError:
			raise
		else:
			if d is False or d is None:
				raise KeyError('Domain for DNS does not exist. Abort!')
				return

		if self.type == Dns.TYPE_SOA:
			timestamp = datetime.datetime.fromtimestamp(int(d.modified)).strftime('%Y%m%d%H%M%S')
			formattedDnsAdmin = self.dnsAdmin.replace('@', '.')
			content.append('%s.\tSOA\t%s\t%s. (' % (d.getFullDomain(), self.value, formattedDnsAdmin))
			content.append('%s' % (timestamp,))
			content.append('%ss' % (self.refreshRate,))
			content.append('%ss' % (self.retryRate,))
			content.append('%ss' % (self.expireTime,))
			content.append('%ss' % (self.ttl,))
			content.append(')')
		elif self.type == Dns.TYPE_MX:
			content.append('%s\tMX\t%i\t%s' % (self.key, self.prio, self.value))
		elif self.type == Dns.TYPE_SRV:
			content.append('%s\t%i\tIN\t%s\t%i\t%i\t%i\t%s' % (
				self.key, self.ttl, self.type, self.prio, self.weight, self.port, self.value
			))
		else:
			dnsValue = self.value
			if self.type == Dns.TYPE_TXT or self.type == Dns.TYPE_SPF:
				if dnsValue[0] != '"':
					dnsValue = '"%s"' % (dnsValue,)
			content.append('%s\tIN\t%s\t%s' % (self.key, self.type, dnsValue))

		return content

	# Call ONLY ON CLIENT SIDE!!!
	def changeState(self, state):
		self.state = state
		self.stateChanged.emit(state)

	# Call ONLY ON SERVER SIDE!!!
	def setState(self, state):
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = ('UPDATE dns SET status = %s WHERE dns_id = %i')
		cx.execute(query, (state, self.id))
		db.commit()
		cx.close()

		self.state = state

	def __eq__(self, obj):
		log = logging.getLogger('flscp')
		log.debug('Compare domain objects!!!')

		state = True
		for k, v in vars(obj).items():
			if hasattr(self, k):
				if getattr(self, k) != v:
					state = False
					break

		return state

	def __ne__(self, obj):
		return not self.__eq__(obj)

	def toDict(self):
		d = {}
		for k, v in vars(self).items():
			if not k.startswith('_'):
				d[k] = v

		return d

	@classmethod
	def getSoaForDomain(dom, domainId):
		log = logging.getLogger('flscp')
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = ('SELECT dns_id, domain_id FROM dns WHERE domain_id = %s AND dns_type = %s LIMIT 1')
		try:
			cx.execute(query, (domainId, Dns.TYPE_SOA,))
			(dns_id, domain_id) = cx.fetchone()
			dom = Dns(dns_id)
			dom.load()
		except Exception as e:
			dom = None
			log.warning('Could not find Dns SOA-Entry.')
			raise KeyError('Dns-Entry "SOA" could not be found!')
		finally:
			cx.close()

		self = dom
		return self

	@staticmethod
	def getDnsForDomain(dom, domainId):
		log = logging.getLogger('flscp')
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		dnsses = []
		query = ('SELECT dns_id, domain_id FROM dns WHERE domain_id = %s AND dns_type != %s')
		try:
			for (dns_id, domain_id) in cx.execute(query, (domainId, Dns.TYPE_SOA,)):
				try:
					dom = Dns(dns_id)
					if dom.load():
						dnsses.append(dom)
				except Exception as e:
					pass
		except Exception as e:
			dom = None
			log.warning('Could not find Dns entries for domain')
		finally:
			cx.close()

		return dnsses

	@classmethod
	def fromDict(ma, data):
		self = ma()

		for k, v in data.items():
			if hasattr(self, k):
				setattr(self, k, v)

		return self
