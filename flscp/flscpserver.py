#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set noet fenc=utf-8 ff=unix sts=0 sw=4 ts=4 : 
# require: bsddb3
from logging.handlers import WatchedFileHandler
from ansistrm import ColorizingStreamHandler
from Printer import Printer
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.server import SimpleXMLRPCRequestHandler
from xmlrpc.server import SimpleXMLRPCDispatcher
from xmlrpc.server import resolve_dotted_attribute
from pwgen import generate_pass
from threading import Thread
from socketserver import UnixStreamServer
from email.mime.text import MIMEText
from distutils.version import StrictVersion as V
import logging, os, sys, mysql.connector, shlex, subprocess, abc, copy, smtplib
import ssl, re, socketserver, socket, io, pickle, configparser, base64, stat
import zipfile, tempfile
import flscertification
import bsddb3 as bsddb
try:
	import fcntl
except:
	fcntl = None

__author__  = 'Lukas Schreiner'
__copyright__ = 'Copyright (C) 2013 - 2013 Website-Team Friedrich-List-Schule-Wiesbaden'
__version__ = '0.2'

FORMAT = '%(asctime)-15s %(message)s'
formatter = logging.Formatter(FORMAT, datefmt='%b %d %H:%M:%S')
log = logging.getLogger()
log.setLevel(logging.INFO)
hdlr = ColorizingStreamHandler()
hdlr.setFormatter(formatter)
log.addHandler(hdlr)

workDir = os.path.dirname(os.path.realpath(__file__))

# search for config
conf = configparser.ConfigParser()
fread = conf.read(
		[
			'server.ini', os.path.expanduser('~/.flscpserver.ini'), os.path.expanduser('~/.flscp/server.ini'),
			os.path.expanduser('~/.config/flscp/server.ini'), '/etc/flscp/server.ini', '/usr/local/etc/flscp/server.ini'
		]
	)
if len(fread) <= 0:
	sys.stderr.write(
			'Missing config file in one of server.ini, ~/.flscpserver.ini, ~/.flscp/server.ini, ~/.config/flscp/server.ini, /etc/flscp/server.ini or /usr/local/etc/flscp/server.ini!\n'
		)
	sys.exit(255)
else:
	log.debug('Using config files "%s"' % (fread.pop(),))

def hashPostFile(postFile):
	if not os.path.exists(postFile):
		return False

	state = True
	cmd = shlex.split('%s %s' % (conf.get('mailserver', 'postmap'), postFile))
	with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
		out = p.stdout.read()
		err = p.stderr.read()
		if len(out) > 0:
			log.info(out)
		if len(err) > 0:
			log.warning(err)
			state = False

	return state

def reloadPostfix():
	state = True
	cmd = shlex.split('%s %s' % (conf.get('mailserver', 'postfix'), 'quiet-reload'))
	with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
		out = p.stdout.read()
		err = p.stderr.read()
		if len(out) > 0:
			log.info(out)
		if len(err) > 0:
			log.warning(err)
			state = False

	return state

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

	@staticmethod
	def getInstance():
		if SaslDatabase.__instance is None:
			SaslDatabase.__instance = SaslDatabase()

		return SaslDatabase.__instance

	def connect(self):
		# already connected?
		if self.db is not None:
			try:
				self.db.get_open_flags()
				log.info('DB already connected!')
			except bsddb.db.DBError:
				pass
			else:
				self.connected = True
				return True

		try:
			self.db = bsddb.db.DB()
			self.db.open(conf.get('mailserver', 'sasldb'))
		except Exception as e:
			log.error('Could not connect to sasldb!')
			self.connected = False
		else:
			log.info('Connected to sasldb!')
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
			log.warning('Key could not be added to sasldb: %s' % (e,))
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
			log.warning('Key could not be removed from sasldb: %s' % (e,))
			return False

	def close(self):
		if self.db is None:
			return
		
		try:
			self.db.sync()
			self.db.close()
		except:
			log.warning('DB Not closeable - already closed?')

	def __del__(self):
		super().__del__()
		SaslDatabase.__instance = None

class MailDatabase(Database):
	__instance = None

	def __init__(self):
		super().__init__()
		MailDatabase.__instance = self

	@staticmethod
	def getInstance():
		if MailDatabase.__instance is None:
			MailDatabase.__instance = MailDatabase()

		return MailDatabase.__instance

	def getCursor(self):
		if not self.connected or not self.db.is_connected():
			self.connect()

		try:
			return self.db.cursor()
		except mysql.connector.errors.OperationalError as e:
			log.error('Lost connection to mysql server (%s)' % (e,))
			# try to reconnect
			self.db.connected = False
			self.connect()
			if self.connected and self.db.is_connected():
				return self.db.cursor()
			else:
				log.error('Could not reconnect!')
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
					log.error('Your credentials for mysql database is wrong!')
				elif err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
					log.warning('Database does not exist!')
				else:
					log.error('Unknown error when connecting to mysql server: %s' % (err,))
			else:
				self.connected = True
				log.info('Reconnected to mysql database!')
		else:
			try:
				self.db = mysql.connector.connect(
					user=conf.get('database', 'user'), 
					password=conf.get('database', 'password'),
					host=conf.get('database', 'host'),
					port=conf.getint('database', 'port'),
					database=conf.get('database', 'name'),
				)
			except mysql.connector.Error as err:
				if err.errno == mysql.connector.errorcode.ER_ACCESS_DENIED_ERROR:
					log.error('Your credentials for mysql database is wrong!')
				elif err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
					log.warning('Database does not exist!')
				else:
					log.error('Unknown error when connecting to mysql server: %s' % (err,))
			else:
				self.connected = True
				log.info('Connected to mysql database!')

	def close(self):
		if self.connected and self.db.is_connected():
			try:
				self.db.close()
			except:
				pass

		log.info('Disconnected from mysql database!')

	def __del__(self):
		super().__del__()
		MailDatabase.__instance = None

class Mailer:

	def __init__(self, account):
		self.account = account

	def newAccount(self):
		# exist custom template?
		mailContent = Mailer.getMail('newmail')
		if mailContent is None:
			log.warning('Could not load mail "newmail"!')
			return False

		msg = MIMEText(
			mailContent['body'] % {
				'username': '%s@%s' % (self.account.mail,self.account.domain),
				'password': self.account.pw,
				'forwarders': ', '.join(self.account.forward) if len(self.account.forward) > 0 else mailContent['params']['noforward'],
				'notgenerated': mailContent['params']['notgenerated'] if self.account.genPw else ''
			},
			_charset='utf-8'
		)

		msg['Subject'] = mailContent['subject']
		msg['From'] = mailContent['sender']
		msg['To'] = self.account.altMail

		return Mailer.sendMail(msg, mailContent['sender'], self.account.altMail)

	def newForward(self):
		# exist custom template?
		mailContent = Mailer.getMail('newforward')
		if mailContent is None:
			log.warning('Could not load mail "newforward"!')
			return False

		msg = MIMEText(
			mailContent['body'] % {
				'username': '%s@%s' % (self.account.mail,self.account.domain),
				'forwarders': ', '.join(self.account.forward)
			},
			_charset='utf-8'
		)

		msg['Subject'] = mailContent['subject']
		msg['From'] = mailContent['sender']
		msg['To'] = self.account.altMail

		return Mailer.sendMail(msg, mailContent['sender'], self.account.altMail)

	def changeAccount(self):
		# exist custom template?
		mailContent = Mailer.getMail('changemail')
		if mailContent is None:
			log.warning('Could not load mail "changemail"!')
			return False

		msg = MIMEText(
			mailContent['body'] % {
				'username': '%s@%s' % (self.account.mail,self.account.domain),
				'password': self.account.pw if len(self.account.pw) > 0 else mailContent['params']['notchanged'],
				'forwarders': ', '.join(self.account.forward) if len(self.account.forward) > 0 else mailContent['params']['noforward']
			},
			_charset='utf-8'
		)

		msg['Subject'] = mailContent['subject']
		msg['From'] = mailContent['sender']
		msg['To'] = self.account.altMail

		return Mailer.sendMail(msg, mailContent['sender'], self.account.altMail)

	def changeForward(self):
		# exist custom template?
		mailContent = Mailer.getMail('changeforward')
		if mailContent is None:
			log.warning('Could not load mail "changeforward"!')
			return False

		msg = MIMEText(
			mailContent['body'] % {
				'username': '%s@%s' % (self.account.mail,self.account.domain),
				'forwarders': ', '.join(self.account.forward)
			},
			_charset='utf-8'
		)

		msg['Subject'] = mailContent['subject']
		msg['From'] = mailContent['sender']
		msg['To'] = self.account.altMail

		return Mailer.sendMail(msg, mailContent['sender'], self.account.altMail)

	@staticmethod
	def sendMail(msg, sender, recipient):
		try:
			s = smtplib.SMTP('localhost')
			s.sendmail(sender, [recipient], msg.as_string())
			s.quit()
		except Exception as e:
			log.warning('Error while sending mail: %s' % (e,))
			return False
		else:
			return True

	@staticmethod
	def getMail(mail):
		mailContent = {
			'subject': None, 'body': None, 'sender': None,
			'params': {}
		}

		basePath = '%s/templates' % (workDir,)

		content = None
		# try to find custom
		if os.path.exists('%s/custom/%s.txt' % (basePath, mail)):
			with open('%s/custom/%s.txt' % (basePath, mail)) as f:
				content = f.read()

		else:
			with open('%s/default/%s.txt' % (basePath, mail)) as f:
				content = f.read()

		if content is None:
			return None

		# now extract data
		## first the sender
		m = re.compile('# SENDER\\n(.*)\\n# REDNES').search(content)
		if m is None:
			return None
		else:
			mailContent['sender'] = m.group(1)

		## subject
		m = re.compile('# SUBJECT\\n(.*)\\n# TCEJBUS').search(content)
		if m is None:
			return None
		else:
			mailContent['subject'] = m.group(1)

		## body
		m = re.compile('# BODY\\n(.*)\\n# YDOB', re.S).search(content)
		if m is None:
			return None
		else:
			mailContent['body'] = m.group(1)

		## any special variables?
		### they are after YDOB
		variables = content[content.find('# YDOB')+len('# YDOB\n'):]
		if len(variables) > 0:
			variables = variables.split('\n')
			parm = []
			search = None
			for f in variables:
				if search is None and f.startswith('# '):
					search = '# ' + f[2:][::-1]
				elif search is not None and f == search:
					mailContent['params'][f[2:][::-1]] = '\n'.join(parm)
					search = None
					parm = []
				else: 
					parm.append(f)

		return mailContent

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

class Domain:

	def __init__(self):
		self.id = None
		self.name = ''

	def create(self):
		raise NotImplemented('domains can not be created at the moment!')

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
			log.warning('Could not find domain.')
			cx.close()
			raise KeyError('Domain "%s" could not be found!')

		cx.close()

		self = dom
		return self

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

	def getMailAddress(self):
		return '%s@%s' % (self.mail, self.domain)

	def generateId(self):
		self.id = 'Z%s' % (str(zlib.crc32(uuid.uuid4().hex.encode('utf-8')))[0:3],)

	# this is not allowed on client side! Only here....
	def changePassword(self, pwd):
		self.pw = pwd
		self.hashPassword()
		db = MailDatabase.getInstance()
		try:
			cx = db.getCursor()
			query = ('UPDATE mail_users SET mail_pass = %s WHERE mail_id = %s')
			cx.execute(query, (self.hashPw, self.id))
			db.commit()
			cx.close()
		except:
			return False
		else:
			self.updateCredentials()
			return True

	def hashPassword(self):
		libpath = os.path.dirname(os.path.realpath(__file__))
		cmd = shlex.split('php -f %s%slibs%sSaltEncryption%sencrypt.php' % (libpath, os.sep, os.sep, os.sep))
		p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)
		out = p.communicate(input=self.pw.encode('utf-8'))[0]
		self.hashPw = out.decode('utf-8')

	# this is not allowed on client side! Only here....
	def generatePassword(self):
		log.info('Generating password for user %s' % (self.mail,))
		self.pw = generate_pass(12)

	def save(self):
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
			return hashPostFile(conf.get('mailserver', 'mailboxes'))

	def updateAliases(self, oldMail = None, oldDomain = None):
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
			return hashPostFile(conf.get('mailserver', 'aliases'))

	def updateSenderAccess(self, oldMail = None, oldDomain = None):
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
			return hashPostFile(conf.get('mailserver', 'senderaccess'))

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
	def getByEMail(ma, mail):
		ma = MailAccount()
		db = MailDatabase.getInstance()
		cx = db.getCursor()
		query = ('SELECT * FROM mail_users WHERE mail_addr = %s')
		cx.execute(query, ('%s' % (mail,),))
		try:
			(mail_id, mail_acc, mail_pass, mail_forward, domain_id, mail_type, sub_id, status, quota, mail_addr, alternative_addr) = cx.fetchone()
			ma.id = mail_id
			ma.quota = quota
			ma.mail = mail_acc,
			ma.domain = mail_addr.split('@')[1],
			ma.altMail = alternative_addr,
			ma.forward = mail_forward.split(',')
			ma.type = MailAccount.TYPE_ACCOUNT if mail_type == 'account' else MailAccount.TYPE_FORWARD
			ma.status = status
		except:
			cx.close()
			return None
		else:
			cx.close()
			return ma

	def __eq__(self, obj):
		log.debug('Compare objects!!!')
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

class ControlPanel:

	def upToDate(self, version):
		cliVersion = V(version)
		curVersion = V(__version__)

		return cliVersion >= curVersion

	def getCurrentVersion(self):
		# check if we have build directory or not
		base = ''
		if os.path.exists('build' + os.sep):
			base = 'build' + os.sep

		# now create temp zip file
		zfile = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
		with zipfile.ZipFile(zfile, 'w') as verzip:
			self.__addFilesZip(verzip, base)

		zfile.close()
		data = ''
		with open(zfile.name, 'rb') as f:
			data = f.read()

		os.unlink(zfile.name)
		return data

	def __addFilesZip(self, zip, fdir):
		if fdir not in ['.', '..', 'certs']:
			for f in os.listdir(fdir):
				p = os.path.join(fdir, f)
				if os.path.isdir(p):
					self.__addFilesZip(zip, p)
				else:
					arcname = p.replace('build' + os.sep, '')
					if f.endswith('.ini'):
						arcname = arcname.replace(f, f + '.example')
					zip.write(p, arcname)

	def getCerts(self):
		data = flscertification.FLSCertificateList()
		if not os.path.exists(os.path.expanduser(conf.get('connection', 'authorizekeys'))):
			return data

		with open(os.path.expanduser(conf.get('connection', 'authorizekeys')), 'rb') as f:
			data = pickle.load(f)

		return data

	def saveCerts(self, certs):
		#import rpdb2; rpdb2.start_embedded_debugger('test', fDebug=True, fAllowUnencrypted=False, timeout=5)
		certList = flscertification.FLSCertificateList()
		for f in certs['_certs']:
			certList.add(flscertification.FLSCertificate.fromPyDict(f))
		log.debug('Want to save %i items!' % (len(certList),))

		fullList = self.getCerts()
		for cert in certList:
			if cert.state == flscertification.FLSCertificate.STATE_DELETE:
				if cert in fullList:
					print(vars(cert))
					print(cert.__hash__())
					fullList.remove(cert)
				else:
					log.info('Certificate is not in list,... ')
			elif cert.state == flscertification.FLSCertificate.STATE_ADDED:
				cert.state = flscertification.FLSCertificate.STATE_OK
				fullList.add(cert)
			else:
				log.info('Unknown state: %s' % (cert.state,))

		# now save!
		if not os.path.exists(os.path.expanduser(conf.get('connection', 'authorizekeys'))):
			if not os.path.exists(os.path.dirname(os.path.expanduser(conf.get('connection', 'authorizekeys')))):
				os.makedirs(os.path.dirname(conf.get('connection', 'authorizekeys')), 0o750)

		with open(os.path.expanduser(conf.get('connection', 'authorizekeys')), 'wb') as f:
			pickle.dump(fullList, f)

		os.chmod(os.path.expanduser(conf.get('connection', 'authorizekeys')), 0o600)

		return True

	def getDomains(self):
		data = []
		db = MailDatabase.getInstance()
		cursor = db.getCursor()
		query = ('SELECT domain_id, domain_name FROM domain')
		cursor.execute(query)
		for (domain_id, domain_name) in cursor:
			data.append({'id': domain_id, 'domain': domain_name})

		cursor.close()
		
		return data

	def getMails(self):
		db = MailDatabase.getInstance()
		domainsRaw = self.getDomains()
		domains = {}
		for f in domainsRaw:
			domains[f['id']] = f['domain']

		data = []
		cursor = db.getCursor()
		query = ('SELECT mail_id, mail_acc, mail_addr, mail_type, mail_forward, `status`, domain_id, alternative_addr FROM mail_users')
		cursor.execute(query)
		for (mail_id, mail_acc, mail_addr, mail_type, mail_forward, status, domain_id, alternative_addr) in cursor:
			data.append(
				{
					'id': mail_id, 
					'mail': mail_acc,
					'altMail': alternative_addr if alternative_addr is not None else '',
					'forward': mail_forward.split(',') if mail_forward != '_no_' else [],
					'domain': domains[domain_id],
					'domainId': domain_id,
					'state': status,
					'type': mail_type,
					'pw': '',
					'genPw': False
				}
			)

		cursor.close()
		
		return data

	def saveMails(self, mails):
		#import rpdb2; rpdb2.start_embedded_debugger('test', fDebug=True, fAllowUnencrypted=False, timeout=5)
		mailList = MailAccountList()
		for f in mails['_items']:
			mailList.add(MailAccount.fromDict(f))
		log.debug('Want to save %i items!' % (len(mailList),))

		# now process mails. All mails with "generate passwords" have to be
		# pw generated. Do it now!
		for mail in mailList:
			if mail.genPw:
				mail.generatePassword()
			elif len(mail.pw) > 0:
				mail.hashPassword()
			mail.save()

		if len(mailList) > 0:
			reloadPostfix()

		return True

	def ping(self):
		return 'pong'

class FLSUnixRequestHandler(socketserver.BaseRequestHandler):
	def handle(self):
		cmd = ''
		data = ''
		while cmd != 'exit':
			try:
				(cmd, data) = self.request.recv(2048).decode('utf-8').split(';')
			except Exception as e:
				log.debug('Got some useless data,...')
				break
			data = base64.b64decode(data.encode('utf-8')).decode('utf-8')
			cmd = cmd.strip()
			log.debug('Got: %s' % (cmd,))

			self.request.send(self.processCommand(cmd, data))

	def processCommand(self, cmd, data):
		msg = '400 - Bad Request!'

		if cmd == 'chgpwd':
			if self.chgpwd(data):
				msg = '200 - ok'
			else:
				msg = '403 - not successful!'
			pass

		return msg.encode('utf-8')

	def chgpwd(self, data):
		# <username> <pwd>
		try:
			(uname, pwd) = data.split(' ', 1)
		except:
			return False

		if len(uname.strip()) <= 0 or len(pwd.strip()) <= 0:
			return False

		maccount = MailAccount.getByEMail(uname)
		if maccount is None:
			return False

		return maccount.changePassword(pwd)

class FLSRequestHandler(SimpleXMLRPCRequestHandler):
	rpc_paths = ('/RPC2',)

	def validAuth(self):
		log.info('Want to authenticate an user,...')
		cert = self.request.getpeercert()
		log.debug('Certificate: %s' % (cert,))

		if not os.path.exists(os.path.expanduser(conf.get('connection', 'authorizekeys'))):
			(rmtIP, rmtPort) = self.request.getpeername()
			log.warning('We don\'t have keys at the moment. So we only allow local users!')
			if rmtIP.startswith('127.'):
				return True
			else:
				return False

		# create cert
		rmtCert = flscertification.FLSCertificate.fromDict(cert)
		if rmtCert is None:
			return False

		ml = pickle.load(open(os.path.expanduser(conf.get('connection', 'authorizekeys')), 'rb'))
		if len(ml) <= 0:
			(rmtIP, rmtPort) = self.request.getpeername()
			log.warning('We don\'t have keys at the moment. So we only allow local users!')
			if rmtIP.startswith('127.'):
				return True
			else:
				return False
		elif rmtCert in ml:
			return True
		else:
			return False

	def do_POST(self):

		if not self.validAuth():
			self.report_403()
			return

		super().do_POST()

	def report_403(self):
		# Report a 404 error
		self.send_response(403)
		response = b'Forbidden'
		self.send_header("Content-type", "text/plain")
		self.send_header("Content-length", str(len(response)))
		self.end_headers()
		self.wfile.write(response)

class FLSXMLRPCDispatcher(SimpleXMLRPCDispatcher):

	def _dispatch(self, method, params):
		func = None
		try:
			# check to see if a matching function has been registered
			func = self.funcs[method]
		except KeyError:
			if self.instance is not None:
				# check for a _dispatch method
				if hasattr(self.instance, '_dispatch'):
					return self.instance._dispatch(method, params)
				else:
					# call instance method directly
					try:
						func = resolve_dotted_attribute(
							self.instance,
							method,
							self.allow_dotted_names
							)
					except AttributeError:
						pass

		if func is not None:
			try:
				return func(*params)
			except Exception as e:
				import traceback
				log.critical('Error while executing method "%s": %s' % (method, e))
				log.critical(traceback.format_exc())
				raise
		else:
			log.warning('Client tried to call method "%s" which does not exist!' % (method,))
			raise Exception('method "%s" is not supported' % method)

class FLSXMLRPCServer(SimpleXMLRPCServer, FLSXMLRPCDispatcher):

	_send_traceback_header = False

	def __init__(self, privkey, pubkey, cacert, addr, requestHandler=FLSRequestHandler, logRequests=True, 
			allow_none=False, encoding=None, bind_and_activate=True, use_builtin_types=True):
		self.logRequests = logRequests

		FLSXMLRPCDispatcher.__init__(self, allow_none, encoding, use_builtin_types)
		socketserver.BaseServer.__init__(self, addr, requestHandler)
		self.socket = ssl.wrap_socket(
			socket.socket(self.address_family, self.socket_type),
			server_side=True,
			keyfile=privkey,
			certfile=pubkey,
			ca_certs=cacert,
			cert_reqs=ssl.CERT_REQUIRED,
			ssl_version=ssl.PROTOCOL_SSLv3,
		)
		self.socket.context.set_ciphers('HIGH:!aNULL:!eNULL')
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

		if bind_and_activate:
			self.server_bind()
			self.server_activate()

		if fcntl is not None and hasattr(fcntl, 'FD_CLOEXEC'):
			flags = fcntl.fcntl(self.fileno(), fcntl.F_GETFD)
			flags |= fcntl.FD_CLOEXEC
			fcntl.fcntl(self.fileno(), fcntl.F_SETFD, flags)

class FLSCpServer(Thread, FLSXMLRPCServer):

	def __init__(self, connection):
		Thread.__init__(self, name='flscp-rpc')
		FLSXMLRPCServer.__init__(self, conf.get('connection', 'keyfile'), conf.get('connection', 'certfile'), conf.get('connection', 'cacert'), connection)
		self.register_instance(ControlPanel())

	def run(self):
		self.serve_forever()

class FLSCpUnixServer(Thread, UnixStreamServer):
	allow_reuse_address = True

	def __init__(self, connection):
		Thread.__init__(self, name='flscp-unix')
		UnixStreamServer.__init__(self, connection, FLSUnixRequestHandler)

	def run(self):
		# set permission
		os.chmod(
				self.socket.getsockname(), 
				stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH|stat.S_IWUSR|stat.S_IWGRP|stat.S_IWOTH,
		)
		self.serve_forever()

if __name__ == '__main__':
	hdlr = WatchedFileHandler('flscpserver.log')
	hdlr.setFormatter(formatter)
	log.addHandler(hdlr)
	log.setLevel(logging.DEBUG)

	threads = []
	threads.append(FLSCpServer((conf.get('connection', 'host'), conf.getint('connection', 'port'))))
	threads.append(FLSCpUnixServer(conf.get('connection', 'socket')))

	for t in threads:
		t.start()

	try:
		for t in threads:
			t.join()
	except KeyboardInterrupt as e:
		log.info('Try to stop the cp server (press again ctrl+c to quit)...')
		for t in threads:
			t.shutdown()

