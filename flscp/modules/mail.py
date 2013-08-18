import os, os.path
import subprocess
import shlex
import hashlib
import random
import datetime
import logging
import copy
import zlib
import uuid
from database import MailDatabase, SaslDatabase
from flsconfig import FLSConfig
from modules.domain import Domain
from pwgen import generate_pass
from saltencryption import SaltEncryption
from mailer import *

def hashPostFile(postFile, postMap):
	if not os.path.exists(postFile):
		return False

	log = logging.getLogger('flscp')

	state = True
	cmd = shlex.split('%s %s' % (postMap, postFile))
	with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
		out = p.stdout.read()
		err = p.stderr.read()
		if len(out) > 0:
			log.info(out)
		if len(err) > 0:
			log.warning(err)
			state = False

	return state

class MailAccountList:

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

class MailAccount:
	TYPE_ACCOUNT = 'account'
	TYPE_FORWARD = 'forward'

	STATE_OK = 'ok'
	STATE_CHANGE = 'change'
	STATE_CREATE = 'create'
	STATE_DELETE = 'delete'

	def __init__(self):
		self.id = None
		self.type = MailAccount.TYPE_ACCOUNT
		self.state = MailAccount.STATE_OK
		self.quota = 1073741824
		self.mail = ''
		self.domain = ''
		self.pw = ''
		self.hashPw = ''
		self.genPw = False
		self.altMail = ''
		self.forward = []
		self.authCode = None
		self.authValid = None

	def getMailAddress(self):
		return '%s@%s' % (self.mail, self.domain)

	def generateId(self):
		self.id = 'Z%s' % (str(zlib.crc32(uuid.uuid4().hex.encode('utf-8')))[0:3],)

	def createAuthCode(self):
		self.authCode = hashlib.md5(str(hash(random.SystemRandom().uniform(0, 1000))).encode('utf-8')).hexdigest()
		self.authValid = datetime.datetime.now() + datetime.timedelta(hours=2)

		db = MailDatabase.getInstance()
		try:
			cx = db.getCursor()
			query = (
				'UPDATE mail_users SET authcode = %s, authvalid = %s WHERE mail_id = %s'
			)
			cx.execute(query, (self.authCode, self.authValid.strftime('%Y-%m-%d %H:%M:%S'), self.id))
			db.commit()
			cx.close()
		except:
			return False
		else:
			return True

	def authenticate(self, mech, pwd):
		conf = FLSConfig.getInstance()
		data = {
			'userdb_user': '',
			'userdb_home': '',
			'userdb_uid': '',
			'userdb_gid': '',
			'userdb_mail': ''
		}
		localPartDir = os.path.join(conf.get('mailserver', 'basemailpath'), 'virtual')
		homeDir = os.path.join(localPartDir, self.domain, self.mail)
		if self.hashPw == '_no_':
			return False
		
		s = SaltEncryption()

		if mech in ['PLAIN', 'LOGIN']:
			state = s.compare(pwd, self.hashPw)
		else:
			state = False

		if state:
			username = ('%s@%s' % (self.mail, self.domain)).lower()
			data['userdb_user'] = username
			data['userdb_home'] = homeDir
			data['userdb_uid'] = conf.get('mailserver', 'uid')
			data['userdb_gid'] = conf.get('mailserver', 'gid')
			data['userdb_mail'] = 'maildir:%s' % (username,)

			return data

		else:
			return False


	# this is not allowed on client side! Only here....
	def changePassword(self, pwd):
		self.pw = pwd
		self.hashPassword()
		db = MailDatabase.getInstance()
		try:
			cx = db.getCursor()
			query = (
				'UPDATE mail_users SET mail_pass = %s, authcode = NULL, authvalid = NULL WHERE mail_id = %s'
			)
			cx.execute(query, (self.hashPw, self.id))
			db.commit()
			cx.close()
		except:
			return False
		else:
			self.updateCredentials()
			return True

	def hashPassword(self):
		s = SaltEncryption()
		# idea for later: store hash with:
		# s.hash(md5(self.pw)) and check it later with s.compare(md5(self.pw), <hash>)
		# or do it with sha512
		self.hashPw = s.hash(self.pw)

	# this is not allowed on client side! Only here....
	def generatePassword(self):
		log = logging.getLogger('flscp')
		log.info('Generating password for user %s' % (self.mail,))
		self.pw = generate_pass(12)

	def save(self):
		log = logging.getLogger('flscp')
		conf = FLSConfig.getInstance()

		if self.state == MailAccount.STATE_CREATE:
			self.create()
			return
		elif self.state == MailAccount.STATE_DELETE:
			self.delete()
			return

		# now save!
		# -> see create - but if key changed (mail address!) remove
		# all entries before and rename folder in /var/mail,... directory
		# get original data!
		if not self.exists():
			self.create()

		# get domain id! (if not exist: create!)
		try:
			d = Domain.getByName(self.domain)
		except KeyError:
			raise

		# pw entered?
		if len(self.pw.strip()) > 0:
			log.info('Hash password for user %s' % (self.mail,))
			self.hashPassword()

		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = ('SELECT mail_id, mail_addr, mail_type FROM mail_users WHERE mail_id = %s')
		cx.execute(query, (self.id,))
		(mail_id, mail_addr, mail_type) = cx.fetchone()
		(mail, domain) = mail_addr.split('@')
		cx.close()

		cx = db.getCursor()
		if (self.type == MailAccount.TYPE_ACCOUNT and self.hashPw != '') \
			or self.type == MailAccount.TYPE_FORWARD:
			query = (
				'UPDATE mail_users SET mail_acc = %s, mail_pass = %s, mail_forward = %s, ' \
				'domain_id = %s, mail_type = %s, status = %s, quota = %s, mail_addr = %s, ' \
				'alternative_addr = %s WHERE mail_id = %s'
			)
			params = (
				self.mail, self.hashPw, ','.join(self.forward), d.id, self.type, self.state, self.quota, 
				'%s@%s' % (self.mail, self.domain), self.altMail, self.id
			)
		else:
			query = (
				'UPDATE mail_users SET mail_acc = %s, mail_forward = %s, ' \
				'domain_id = %s, mail_type = %s, status = %s, quota = %s, mail_addr = %s, ' \
				'alternative_addr = %s WHERE mail_id = %s'
			)
			params = (
				self.mail, ','.join(self.forward), d.id, self.type, self.state, self.quota, 
				'%s@%s' % (self.mail, self.domain), self.altMail, self.id
			)

		cx.execute(
			query, 
			params
		)
		db.commit()
		log.debug('executed mysql statement: %s' % (cx.statement,))

		# update credentials...
		# if pw was entered or type changed
		if mail_type != self.type or self.pw.strip() != '':
			self.updateCredentials()

		# now update mailboxes files!
		if not self.updateMailboxes(oldMail=mail, oldDomain=domain):
			cx.close()
			return False

		# update aliases
		if not self.updateAliases(oldMail=mail, oldDomain=domain):
			# remove entry from updateMailboxes?
			cx.close()
			return False

		# update sender-access
		if not self.updateSenderAccess(oldMail=mail, oldDomain=domain):
			# remove entry from updateMailboxes and Aliases ?
			cx.close()
			return False

		# rename folders - but only if target directory does not exist
		# (we had to throw fatal error if target directory exists!)
		oldPath = '%s/%s/%s/' % (conf.get('mailserver', 'basemailpath'), domain, mail)
		path = '%s/%s/%s/' % (conf.get('mailserver', 'basemailpath'), self.domain, self.mail)
		if os.path.exists(oldPath):
			if os.path.exists(path):
				log.error('Could not move "%s" to "%s", because it already exists!' % (path,))
			else:
				try:
					os.rename(oldPath, path)
				except OSError as e:
					log.warning('Got OSError - Does directory exists? (%s)' % (e,))
				except Exception as e:
					log.warning('Got unexpected exception (%s)!' % (e,))

		cx.close()

		# all best? Than go forward and update set state,...
		self.setState(MailAccount.STATE_OK)

		# notify 
		if len(self.altMail) > 0:
			m = Mailer(self)
			state = False
			if self.type == MailAccount.TYPE_ACCOUNT:
				state = m.changeAccount()
			else:
				state = m.changeForward()

			if state:
				log.info('User is notified about account change!')
			else:
				log.warning('Unknown error while notifying user!')
		else:
			log.info('User is not notified because we have no address of him!')

		# reset info
		self.pw = ''
		self.hashPw = ''
		self.genPw = False

	def delete(self):
		log = logging.getLogger('flscp')
		conf = FLSConfig.getInstance()

		# delete!		
		# 1. remove credentials
		# 2. remove entry from /etc/postfix/fls/aliases
		# 3. remove entry from /etc/postfix/fls/mailboxes
		# 4. remove entry from /etc/postfix/fls/sender-access
		# 5. remove entry from mail_users
		# 7. remove complete mails in /var/mail/,... directory
		# 6. postmap all relevant entries
		self.updateCredentials()
		self.updateMailboxes()
		self.updateAliases()
		self.updateSenderAccess()

		if self.exists():
			db = MailDatabase.getInstance()
			cx = db.getCursor()
			query = ('SELECT mail_id, mail_addr FROM mail_users WHERE mail_id = %s')
			cx.execute(query, (self.id,))
			for (mail_id, mail_addr,) in cx:
				(mail, domain) = mail_addr.split('@')
				path = '%s/%s/%s/' % (conf.get('mailserver', 'basemailpath'), domain, mail) 
				if os.path.exists(path):
					try:
						os.removedirs(path)
					except Exception as e:
						log.warning('Error when removing directory: %s' % (e,))

			query = ('DELETE FROM mail_users WHERE mail_id = %s')
			cx.execute(query, (self.id,))
			cx.close()

	def exists(self):
		# check if entry exists already in mail_users!
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = ('SELECT mail_id FROM mail_users WHERE mail_addr = %s')
		cx.execute(query, ('%s@%s' % (self.mail, self.domain),))
		exists = len(cx.fetchall()) > 0
		cx.close()
		return exists

	def create(self):
		log = logging.getLogger('flscp')
		# create:
		# 1. update mail_users
		# 2. update credentials, if given
		# 3. update /etc/postfix/fls/mailboxes
		# 4. update aliases
		# 5. update sender-access (we could later be implement to restrict sending!)
		# postmap all relevant entries
		if self.exists():
			# already exists! 
			raise KeyError('Mail "%s@%s" already exists!' % (self.mail, self.domain))
		
		# get domain id! (if not exist: create!)
		try:
			d = Domain.getByName(self.domain)
		except KeyError:
			raise

		# pw entered?
		if len(self.pw.strip()) > 0:
			self.hashPassword()

		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = (
			'INSERT INTO mail_users (mail_acc, mail_pass, mail_forward, domain_id, mail_type, status, quota, mail_addr, alternative_addr) ' \
			'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)'
		)
		cx.execute(
			query, 
			(
				self.mail, self.hashPw, ','.join(self.forward), d.id, self.type, self.state, self.quota, 
				'%s@%s' % (self.mail, self.domain), self.altMail
			)
		)
		db.commit()
		log.debug('executed mysql statement: %s' % (cx.statement,))
		id = cx.lastrowid
		if id is None:
			cx.close()
			return False
		else:
			self.id = id

		# update credentials...
		self.updateCredentials()

		# now update mailboxes files!
		if not self.updateMailboxes():
			cx.close()
			return False

		# update aliases
		if not self.updateAliases():
			# remove entry from updateMailboxes?
			cx.close()
			return False

		# update sender-access
		if not self.updateSenderAccess():
			# remove entry from updateMailboxes and Aliases ?
			cx.close()
			return False

		cx.close()
		
		# all best? Than go forward and update set state,...
		self.setState(MailAccount.STATE_OK)

		# notify 
		if len(self.altMail) > 0:
			m = Mailer(self)
			state = False
			if self.type == MailAccount.TYPE_ACCOUNT:
				state = m.newAccount()
			else:
				state = m.newForward()

			if state:
				log.info('User is notified about account change!')
			else:
				log.warning('Unknown error while notifying user!')
		else:
			log.info('User is not notified because we have no address of him!')

		# reset info
		self.pw = ''
		self.hashPw = ''
		self.genPw = False

	def setState(self, state):
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = ('UPDATE mail_users SET status = %s WHERE mail_id = %s')
		cx.execute(query, (state, self.id))
		db.commit()
		cx.close()

		self.state = state

	def updateMailboxes(self, oldMail = None, oldDomain = None):
		conf = FLSConfig.getInstance()
		
		mailAddr = '%s@%s' % (self.mail, self.domain)
		if oldMail is None:
			oldMail = self.mail
		if oldDomain is None:
			oldDomain = self.domain
		mailOldAddr = '%s@%s' % (oldMail, oldDomain)

		cnt = []
		with open(conf.get('mailserver', 'mailboxes'), 'r') as f:
			cnt = f.read().split('\n')

		cnt = [f for f in cnt if (('\t' in f and f[0:f.index('\t')] != mailOldAddr) or f[0:1] == '#') and len(f.strip()) > 0]

		# now add data:
		if self.state in (MailAccount.STATE_CHANGE, MailAccount.STATE_CREATE):
			if self.type == MailAccount.TYPE_ACCOUNT:
				cnt.append('%s\t%s%s%s%s' % (mailAddr, self.domain, os.sep, self.mail, os.sep))

		# now sort file
		cnt.sort()

		# now write back
		try:
			with open(conf.get('mailserver', 'mailboxes'), 'w') as f:
				f.write('\n'.join(cnt))
		except:
			return False
		else:
			# postmap
			return hashPostFile(conf.get('mailserver', 'mailboxes'), conf.get('mailserver', 'postmap'))

	def updateAliases(self, oldMail = None, oldDomain = None):
		conf = FLSConfig.getInstance()
		
		mailAddr = '%s@%s' % (self.mail, self.domain)
		if oldMail is None:
			oldMail = self.mail
		if oldDomain is None:
			oldDomain = self.domain
		mailOldAddr = '%s@%s' % (oldMail, oldDomain)

		cnt = []
		with open(conf.get('mailserver', 'aliases'), 'r') as f:
			cnt = f.read().split('\n')

		cnt = [f for f in cnt if (('\t' in f and f[0:f.index('\t')] != mailOldAddr) or f[0:1] == '#') and len(f.strip()) > 0]

		# now add data:
		if self.state in (MailAccount.STATE_CHANGE, MailAccount.STATE_CREATE):
			forward = copy.copy(self.forward)
			if self.type == MailAccount.TYPE_ACCOUNT:
				forward.insert(0, mailAddr)
			forward = list(set(forward))
			cnt.append('%s\t%s' % (mailAddr, ','.join(forward)))

		# now sort file
		cnt.sort()

		# now write back
		try:
			with open(conf.get('mailserver', 'aliases'), 'w') as f:
				f.write('\n'.join(cnt))
		except:
			return False
		else:
			# postmap
			return hashPostFile(conf.get('mailserver', 'aliases'), conf.get('mailserver', 'postmap'))

	def updateSenderAccess(self, oldMail = None, oldDomain = None):
		conf = FLSConfig.getInstance()
		
		mailAddr = '%s@%s' % (self.mail, self.domain)
		if oldMail is None:
			oldMail = self.mail
		if oldDomain is None:
			oldDomain = self.domain
		mailOldAddr = '%s@%s' % (oldMail, oldDomain)

		cnt = []
		with open(conf.get('mailserver', 'senderaccess'), 'r') as f:
			cnt = f.read().split('\n')

		cnt = [f for f in cnt if (('\t' in f and f[0:f.index('\t')] != mailOldAddr) or f[0:1] == '#') and len(f.strip()) > 0]

		# now add data:
		if self.state in (MailAccount.STATE_CHANGE, MailAccount.STATE_CREATE):
			cnt.append('%s\t%s' % (mailAddr, 'OK'))

		# now sort file
		cnt.sort()

		# now write back
		try:
			with open(conf.get('mailserver', 'senderaccess'), 'w') as f:
				f.write('\n'.join(cnt))
		except:
			return False
		else:
			# postmap
			return hashPostFile(conf.get('mailserver', 'senderaccess'), conf.get('mailserver', 'postmap'))

	def credentialsKey(self):
		return '%s\x00%s\x00%s' % (self.mail, self.domain, 'userPassword')

	def updateCredentials(self):
		db = SaslDatabase.getInstance()

		if self.state == MailAccount.STATE_DELETE or len(self.hashPw.strip()) <= 0:
			db.delete(self.credentialsKey())
		else:
			if db.exists(self.credentialsKey()):
				db.update(self.credentialsKey(), self.pw)
			else:
				db.add(self.credentialsKey(), self.pw)

	@classmethod
	def getByEMail(self, mail):
		ma = MailAccount()
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = ('SELECT * FROM mail_users WHERE mail_addr = %s')
		cx.execute(query, ('%s' % (mail,),))
		try:
			(mail_id, mail_acc, mail_pass, mail_forward, domain_id, mail_type, sub_id, status, quota, mail_addr, alternative_addr, authcode, authvalid,) = cx.fetchone()
			ma.id = mail_id
			ma.quota = quota
			ma.mail = mail_acc
			ma.hashPw = mail_pass
			ma.domain = mail_addr.split('@')[1]
			ma.altMail = alternative_addr
			ma.forward = mail_forward.split(',')
			ma.type = MailAccount.TYPE_ACCOUNT if mail_type == 'account' else MailAccount.TYPE_FORWARD
			ma.status = status
			ma.authCode = authcode
			ma.authValid = authvalid
		except Exception as e:
			log = logging.getLogger('flscp')
			log.critical('Got error: %s' % (e,))
			cx.close()
			return None
		else:
			cx.close()
			self = ma
			return self

	def __eq__(self, obj):
		log = logging.getLogger('flscp')
		log.debug('Compare objects!!!')
		if obj is None or self is None:
			return False

		if self.id == obj.id and \
			self.type == obj.type and \
			self.mail == obj.mail and \
			self.domain == obj.domain and \
			self.pw == obj.pw and \
			self.genPw == obj.genPw and \
			self.altMail == obj.altMail and \
			self.forward == obj.forward and \
			self.state == obj.state and \
			self.quota == obj.quota:
			return True
		else:
			return False

	def __ne__(self, obj):
		return not self.__eq__(obj)

	@classmethod
	def fromDict(ma, data):
		self = ma()

		self.id = data['id']
		self.type = data['type']
		self.mail = data['mail']
		self.domain = data['domain']
		self.altMail = data['altMail']
		self.forward = data['forward']
		self.state = data['state']
		self.pw = data['pw']
		self.genPw = data['genPw']

		return self