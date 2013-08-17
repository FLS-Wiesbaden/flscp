import logging
from database import MailDatabase

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
		self.created = None
		self.modified = None
		self.state = ''
		self.log = logging.getLogger('flscp')

	def create(self):
		raise NotImplemented('domains can not be created at the moment!')

	def setState(self, state):
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = ('UPDATE domain SET domain_status = %s WHERE domain_id = %s')
		cx.execute(query, (state, self.id))
		db.commit()
		cx.close()

		self.state = state

	def __eq__(self, obj):
		self.log.debug('Compare domain objects!!!')
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
		self.created = data['created']
		self.modified = data['modified']
		self.state = data['state']

		return self

	@classmethod
	def getByName(dom, name):
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
			self.log.warning('Could not find domain.')
			cx.close()
			raise KeyError('Domain "%s" could not be found!')

		cx.close()

		self = dom
		return self