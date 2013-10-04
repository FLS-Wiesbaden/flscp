import logging
import zlib
import uuid
import time
from database import MailDatabase
from tools import hashPostFile

class DomainAccountList:

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

	def iterTlds(self, id):
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

class Domain:
	STATE_OK = 'ok'
	STATE_CHANGE = 'change'
	STATE_CREATE = 'create'
	STATE_DELETE = 'delete'

	def __init__(self):
		self.id = None
		self.name = ''
		self.ipv6 = ''
		self.ipv4 = ''
		self.gid = ''
		self.uid = ''
		self.parent = None
		self.created = None
		self.modified = None
		self.state = ''

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
			'INSERT INTO domain (domain_parent, domain_name, ipv6, ipv4, domain_gid, domain_uid, domain_created, domain_last_modified, domain_status) ' \
			'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)'
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

	def setState(self, state):
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = ('UPDATE domain SET domain_status = %s WHERE domain_id = %s')
		cx.execute(query, (state, self.id))
		db.commit()
		cx.close()

		self.state = state

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
			log.warning('Could not find domain.')
			cx.close()
			raise KeyError('Domain "%s" could not be found!')

		cx.close()

		self = dom
		return self