import logging
import zlib
import uuid
import time
from database import MailDatabase
from tools import hashPostFile

class DomainList:

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

	def iterByParent(self, domainId):
		for f in self._items:
			if f.parent == domainId:
				yield f

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

	def findByParent(self, parent):
		item = None
		try:
			parent = int(parent)
		except:
			pass

		for f in self._items:
			if f.parent == parent:
				item = f
				break

		return item

class Domain:
	STATE_OK = 'ok'
	STATE_CHANGE = 'change'
	STATE_CREATE = 'create'
	STATE_DELETE = 'delete'

	def __init__(self, did = None):
		self.id = did
		self.name = ''
		self.ipv6 = ''
		self.ipv4 = ''
		self.gid = ''
		self.uid = ''
		self.parent = None
		self.created = None
		self.modified = None
		self.state = ''

		self.ttl = 3600

	def load(self):
		log = logging.getLogger('flscp')
		if self.id is None:
			log.info('Can not load data for a domain with no id!')
			return False

		state = False

		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = (
			'SELECT domain_id, domain_parent, domain_name, ipv6, ipv4, domain_gid, domain_uid, domain_created, \
			domain_last_modified, domain_status FROM domain WHERE domain_id = %s LIMIT 1'
		)
		try:
			cx.execute(query, (self.id,))
			for (did, parent, domain_name, ipv6, ipv4, gid, uid, created, modified, state) in cx:
				self.id = did
				self.parent = parent
				self.name = domain_name
				self.ipv6 = ipv6
				self.ipv4 = ipv4
				self.gid = gid
				self.uid = uid
				self.created = created
				self.modified = modified
				self.state = state
		except Exception as e:
			log.warning('Could not load the domain %s because of %s' % (self.id, str(e)))
			state = False
		else:
			state = True
		finally:
			cx.close()

		return state

	def generateId(self):
		self.id = 'Z%s' % (str(zlib.crc32(uuid.uuid4().hex.encode('utf-8')))[0:3],)

	def create(self):
		# 1. create entry in domain
		# 2. insert the things in domain file of postfix
		# 3. hash the domain file
		# 4. create default dns entries?
		# 5. generate a bind file
		# 6. reload bind
		if self.exists():
			raise KeyError('Domain "%s" already exists!' % (self.name,))

		# is it a valid domain?
		if len(self.name) <= 0:
			raise ValueError('No valid domain given!')

		self.created = time.time()
		self.modified = time.time()
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		self.state = Domain.STATE_CREATE
		query = (
			'INSERT INTO domain (domain_parent, domain_name, ipv6, ipv4, domain_gid, domain_uid, domain_created, \
			domain_last_modified, domain_status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)'
		)
		cx.execute(
			query, 
			(
				self.parent, self.name, self.ipv6, self.ipv4, self.gid, self.uid, 
				self.created, self.modified, self.state
			)
		)
		db.commit()

		self.updateDomainFile()

	def updateDomainFile(self):
		pass

	def generateBindFile(self):
		dl = DomainList()
		content = []
		content.append('$ORIGIN %s.' % (self.getFullDomain(dl),))
		content.append('$TTL %is' % (self.ttl,))
		# get soa entry.
		from modules.dns import Dns
		soa = Dns.getSoaForDomain(self.id)
		if soa is None:
			raise ValueError('Missing SOA-Entry. Cannot generatee Bind-File before!')
			return False

		for f in soa.generateDnsEntry(dl):
			content.append(f)

		# now the rest
		for dns in Dns.getDnsForDomain(self.id):
			for f in dns.generateDnsEntry(dl):
				content.append(f)

		return '\n'.join(content)

	def setState(self, state):
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = ('UPDATE domain SET domain_status = %s WHERE domain_id = %s')
		cx.execute(query, (state, self.id))
		db.commit()
		cx.close()

		self.state = state

	def getFullDomain(self, domainList = None):
		domain = self.name

		if self.parent is not None:
			if domainList is not None:
				parent = domainList.findById(self.parent)
			else:
				parent = Domain(self.parent)
				if not parent.load():
					log = logging.getLogger('flscp')
					log.warning('Could not get the parent with did = %s' % (self.parent,))
					parent = None

			if parent is None:
				return domain
			else:
				domain = '%s.%s' % (self.name, parent.getFullDomain(domainList))

		return domain

	def isDeletable(self, domainList, mailList):
		domain = self.getFullDomain(domainList)

		mail = mailList.findByDomain(domain)
		if mail:
			return False
		else:
			# is this a parent for somebody?
			item = domainList.findByParent(self.id)

			if item is None:
				return True
			else:
				return False			

	def __eq__(self, obj):
		log = logging.getLogger('flscp')
		log.debug('Compare domain objects!!!')
		if self.id == obj.id and \
			self.name == obj.name and \
			self.ipv6 == obj.ipv6 and \
			self.ipv4 == obj.ipv4 and \
			self.uid  == obj.uid and \
			self.gid  == obj.gid and \
			self.state == obj.state:
			return True
		else:
			return False

	def __ne__(self, obj):
		return not self.__eq__(obj)

	@classmethod
	def fromDict(ma, data):
		self = ma()

		self.id = data['id']
		self.name = data['domain']
		self.ipv6 = data['ipv6']
		self.ipv4 = data['ipv4']
		self.gid = data['gid']
		self.uid = data['uid']
		self.parent = data['parent']
		self.created = data['created']
		self.modified = data['modified']
		self.state = data['state']

		return self

	@classmethod
	def getByName(dom, name):
		log = logging.getLogger('flscp')
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = ('SELECT domain_id, domain_name FROM domain WHERE domain_name = %s')
		try:
			cx.execute(query, (name,))
			(domain_id, domain_name) = cx.fetchone()
			dom = Domain()
			dom.id = domain_id
			dom.name = domain_name
		except Exception as e:
			dom = None
			log.warning('Could not find domain.')
			raise KeyError('Domain "%s" could not be found!' % (name,))
		finally:
			cx.close()

		self = dom
		return self

	@classmethod
	def getById(dom, did):
		dom = Domain(did)
		if dom.load():
			self = dom
		else:
			raise KeyError('Domain with this id does not exist!')

		return self
