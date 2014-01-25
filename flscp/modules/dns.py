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
		self.prio = 0
		self.value = ''
		self.weight = 0
		self.port = 0
		self.dnsAdmin = ''
		self.refreshRate = 7200
		self.retryRate = 1800
		self.expireTime = 1209600
		self.ttl = 3600
		self.state = ''

	def generateId(self):
		self.id = 'Z%s' % (str(zlib.crc32(uuid.uuid4().hex.encode('utf-8')))[0:3],)

	def save(self):
		if self.state == Dns.STATE_CREATE:
			return self.create()
		elif self.state == Dns.STATE_CHANGE:
			return self.update()
		elif self.state == Dns.STATE_DELETE:
			return self.delete()

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
		# now get the dns id
		id = cx.lastrowid
		if id is None:
			cx.close()
			return False
		else:
			self.id = id
			cx.close()

		# all fine! set the state!
		self.setState(Dns.STATE_OK)

	def update(self):
		# is it valid?
		retCode = True
		state, msg = self.validate()
		if not state:
			raise ValueError('No valid Dns Entry!!!')

		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = (
			'UPDATE dns \
			SET dns_key = %s, \
				dns_type = %s, \
				dns_prio = %s, \
				dns_value = %s, \
				dns_weight = %s, \
				dns_port = %s, \
				dns_admin = %s, \
				dns_refresh = %s, \
				dns_retry = %s, \
				dns_expire = %s, \
				dns_ttl = %s, \
				status = %s \
			WHERE dns_id = %s'
		)
		try:
			cx.execute(
				query,
				(
					self.key, self.type, self.prio, self.value, self.weight, self.port, self.dnsAdmin,
					self.refreshRate, self.retryRate, self.expireTime, self.ttl, self.state, self.id
				)
			)
		except Exception as e:
			log = logging.getLogger('flscp')
			log.warning('Could not save the dns entry %s (%s)' % (self.id, str(e)))
			retCode = False
		else:
			db.commit()
		finally:
			cx.close()

		# all fine! set the state!
		self.setState(Dns.STATE_OK)

		return retCode

	def delete(self):
		state = True
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = (
			'DELETE FROM dns WHERE dns_id = %s'
		)
		try:
			cx.execute(query, (self.id,))
		except:
			state = False
		db.commit()
		cx.close()

		return state

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
		visibleList = self.getValidCombination()
		fields = []
		# key 
		fld = ValidationField('key', ValidationField.TYPE_STR)
		fld.canEmpty = False if fld.name in visibleList else True
		fld.setErrMsg = 'You have to set the key!'
		fields.append(fld)
		# prio
		fld = ValidationField('prio', ValidationField.TYPE_INT)
		fld.canEmpty = False if fld.name in visibleList else True
		fld.setErrMsg = 'You have to set the prio (numerical value)!'
		fields.append(fld)
		# value - careful: can be an IP, NS, ...
		fld = ValidationField('value', ValidationField.TYPE_STR)
		fld.canEmpty = False if fld.name in visibleList else True
		if self.type == Dns.TYPE_SOA:
			fld.setErrMsg = 'You have to set the primary DNS-Server for the Domain.'
		else:
			fld.setErrMsg = 'You have to fill the value!'
		fields.append(fld)
		# weight
		fld = ValidationField('weight', ValidationField.TYPE_RANGE & ValidationField.TYPE_INT)
		fld.canEmpty = False if fld.name in visibleList else True
		fld.setRange(0, 65535)
		fld.setErrMsg = 'The weight has to be a numerical value between 0 and 65535.'
		fields.append(fld)
		# port
		fld = ValidationField('port', ValidationField.TYPE_RANGE & ValidationField.TYPE_INT)
		fld.canEmpty = False if fld.name in visibleList else True
		fld.setRange(0, 65535)
		fld.setErrMsg = 'The port has to be a numerical value between 0 and 65535.'
		fields.append(fld)
		# dnsAdmin
		fld = ValidationField('dnsAdmin', ValidationField.TYPE_MAIL)
		fld.canEmpty = False if fld.name in visibleList else True
		fld.setErrMsg = 'You have to set an DNS-Admin-Mail!'
		fields.append(fld)
		# refreshRate
		fld = ValidationField('refreshRate', ValidationField.TYPE_RANGE & ValidationField.TYPE_INT)
		fld.canEmpty = False if fld.name in visibleList else True
		fld.setRange(1200, 43200)
		fld.setErrMsg = 'The refresh rate has to be a numerical value between 1200 and 43200 seconds.'
		fields.append(fld)
		# retryRate
		fld = ValidationField('retryRate', ValidationField.TYPE_RANGE & ValidationField.TYPE_INT)
		fld.canEmpty = False if fld.name in visibleList else True
		fld.setRange(180, 2419200)
		fld.setErrMsg = 'The refresh rate has to be a numerical value between 180 and 2419200 seconds.'
		fields.append(fld)
		# expireTime
		fld = ValidationField('expireTime', ValidationField.TYPE_RANGE & ValidationField.TYPE_INT)
		fld.canEmpty = False if fld.name in visibleList else True
		fld.setRange(1209600, 2419200)
		fld.setErrMsg = 'The expire time has to be between 1209600 and 2419200 seconds.'
		fields.append(fld)
		# ttl
		fld = ValidationField('ttl', ValidationField.TYPE_RANGE & ValidationField.TYPE_INT)
		fld.canEmpty = False if fld.name in visibleList else True
		fld.setRange(60, 2419200)
		fld.setErrMsg = 'The TTL has to be between 60 and 2419200 seconds.'
		fields.append(fld)

		for f in fields:
			if not f.isValid(getattr(self, f.name)):
				state = False
				msg[f.name] = f.getErrMsg()

		return state, msg

	def generateDnsEntry(self, dl):
		content = []
		# get Domain!
		try:
			d = dl.findById(self.domainId)
			if d is None:
				d = Domain(self.domainId)
				d.load()
				dl.add(d)
		except KeyError:
			raise
		else:
			if d is False or d is None:
				raise KeyError('Domain for DNS does not exist. Abort!')
				return

		if self.type == Dns.TYPE_SOA:
			from datetime import datetime
			timestamp = datetime.fromtimestamp(int(d.modified)).strftime('%Y%m%d%H%M%S')
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
		query = ('UPDATE dns SET status = %s WHERE dns_id = %s')
		cx.execute(query, (state, self.id))
		db.commit()
		cx.close()

		self.state = state

	def getValidCombination(self):
		visibleList = ['key', 'type', 'value', 'ttl']
		if self.type == Dns.TYPE_A:
			visibleList += []
		elif self.type == Dns.TYPE_AAAA:
			visibleList += []
		elif self.type == Dns.TYPE_CNAME:
			visibleList += []
		elif self.type == Dns.TYPE_MX:
			visibleList += ['prio']
		elif self.type == Dns.TYPE_SOA:
			visibleList += ['dnsAdmin', 'refreshRate', 'retryRate', 'expireTime']
		elif self.type == Dns.TYPE_TXT:
			visibleList += []
		elif self.type == Dns.TYPE_SPF:
			visibleList += []
		elif self.type == Dns.TYPE_SRV:
			visibleList += ['port', 'weight', 'prio']
		elif self.type == Dns.TYPE_NS:
			visibleList += []

		return visibleList

	def getDefault(self, key):
		defaultList = {
			'key': '',
			'type': Dns.TYPE_A,
			'value': '',
			'ttl': 3600,
			'prio': 0,
			'dnsAdmin': '',
			'refreshRate': 7200,
			'retryRate': 1800,
			'expireTime': 1209600,
			'port': 0,
			'weight': 0,
			'state': Dns.STATE_CREATE
		}

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
	def getDnsForDomain(domainId):
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

class ValidationField: 
	TYPE_INT = 1
	TYPE_STR = 2
	TYPE_RANGE = 4
	TYPE_BOOL = 8
	TYPE_ENUM = 16
	TYPE_MAIL = 32

	def __init__(self, name, fldType = 2, canEmpty = True):
		self.name = name
		self.fldType = fldType
		self.canEmpty = canEmpty
		self.rangeStart = 0
		self.rangeEnd = 0
		self.enumList = []

		self.errMsg = 'The element %s is invalid!' % (self.name,)

	def setErrMsg(self, errMsg):
		self.errMsg = errMsg

	def getErrMsg(self):
		return self.errMsg

	def setEnumList(self, eList):
		self.enumList = eList

	def setRange(self, start, end):
		self.rangeStart = start
		self.rangeEnd = end

	def isValid(self, value):
		state = True
		if not self.canEmpty and value == '':
			state = False
		elif self.fldType == ValidationField.TYPE_INT:
			try:
				int(value)
			except:
				state = False
		elif self.fldType == ValidationField.TYPE_RANGE:
			if value > self.rangeEnd or value < self.rangeStart:
				state = False
		elif self.fldType == (ValidationField.TYPE_RANGE & ValidationField.TYPE_INT):
			try:
				value = int(value)
			except:
				state = False
			else:
				if value > self.rangeEnd or value < self.rangeStart:
					state = False
		elif self.fldType == ValidationField.TYPE_BOOL:
			if value not in ['True', 'False', True, False]:
				state = False
		elif self.fldType == ValidationField.TYPE_ENUM:
			if value not in self.enumList:
				state = False
		elif self.fldType == ValidationField.TYPE_STR:
			# nothing???
			pass
		elif self.fldType == ValidationField.TYPE_MAIL and value is not None and len(value.strip()) > 0:
			from modules.mail import MailValidator
			state = MailValidator(value)

		return state