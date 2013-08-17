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
from threading import Thread
from socketserver import UnixStreamServer
from distutils.version import StrictVersion as V
import logging, os, sys, shlex, subprocess, smtplib
import ssl, re, socketserver, socket, io, pickle, configparser, base64, stat
import zipfile, tempfile, datetime, json
from database import MailDatabase, SaslDatabase
from flsconfig import FLSConfig
from modules.flscertification import *
from modules.mail import *
try:
	import fcntl
except:
	fcntl = None

__author__  = 'Lukas Schreiner'
__copyright__ = 'Copyright (C) 2013 - 2013 Website-Team Friedrich-List-Schule-Wiesbaden'
__version__ = '0.3'

FORMAT = '%(asctime)-15s %(message)s'
formatter = logging.Formatter(FORMAT, datefmt='%b %d %H:%M:%S')
log = logging.getLogger('flscp')
log.setLevel(logging.INFO)
hdlr = ColorizingStreamHandler()
hdlr.setFormatter(formatter)
log.addHandler(hdlr)

workDir = os.path.dirname(os.path.realpath(__file__))

# search for config
conf = FLSConfig()
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
		data = base64.b64encode(data)
		return data.decode('utf-8')

	def __addFilesZip(self, zip, fdir):
		if fdir not in ['.', '..', 'certs']:
			for f in os.listdir(fdir):
				p = os.path.join(fdir, f)
				if os.path.isdir(p):
					self.__addFilesZip(zip, p)
				else:
					arcname = p.replace('build' + os.sep + 'flscp' + os.sep, '')
					if f.endswith('.ini'):
						arcname = arcname.replace(f, f + '.example')
					zip.write(p, arcname)

	def getCerts(self):
		data = FLSCertificateList()
		if not os.path.exists(os.path.expanduser(conf.get('connection', 'authorizekeys'))):
			return data

		with open(os.path.expanduser(conf.get('connection', 'authorizekeys')), 'rb') as f:
			data = pickle.load(f)

		return data

	def saveCerts(self, certs):
		#import rpdb2; rpdb2.start_embedded_debugger('test', fDebug=True, fAllowUnencrypted=False, timeout=5)
		certList = FLSCertificateList()
		for f in certs['_certs']:
			certList.add(FLSCertificate.fromPyDict(f))
		log.debug('Want to save %i items!' % (len(certList),))

		fullList = self.getCerts()
		for cert in certList:
			if cert.state == FLSCertificate.STATE_DELETE:
				if cert in fullList:
					fullList.remove(cert)
				else:
					log.info('Certificate is not in list,... ')
			elif cert.state == FLSCertificate.STATE_ADDED:
				cert.state = FLSCertificate.STATE_OK
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
		query = ('SELECT domain_id, domain_name, ipv6, ipv4, domain_gid, domain_uid, domain_created, domain_last_modified, domain_status FROM domain')
		cursor.execute(query)
		for (domain_id, domain_name, ipv6, ipv4, gid, uid, created, modified, state) in cursor:
			data.append(
				{
					'id': domain_id, 
					'domain': domain_name,
					'ipv6': ipv6,
					'ipv4': ipv4,
					'gid': gid,
					'uid': uid,
					'created': created,
					'modified': modified,
					'state': state
				}
			)

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
		elif cmd == 'forgotpw':
			if self.forgotpw(data):
				msg = '200 - ok'
			else:
				msg = '403 - not successful!'
		elif cmd == 'sendpw':
			# sends a new password after forgotpw was confirmed!
			if self.sendpw(data):
				msg = '200 - ok'
			else:
				msg = '403 - not successful!'
			pass
		elif cmd == 'auth':
			data = json.loads(data)
			retData = self.authenticate(data)
			msg = '200 - ' if retData is not None else '403 - '
			msg = '%s%s' % (msg, json.dumps(retData) if retData is not None else json.dumps({}))

		return msg.encode('utf-8')

	def authenticate(self, data):
		authMech = data['AUTH_MECH']
		userName = data['AUTH_USER']
		password = data['AUTH_PASSWORD']

		maccount = MailAccount.getByEMail(userName)
		if maccount is not None:
			return maccount.authenticate(authMech, password)
		else:
			return None

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

	def forgotpw(self, data):
		# <mail/username> <alternative addr>
		try:
			(mail, alt) = data.split(' ', 1)
		except:
			log.warning('Could not parse "new password request"!')
			return False
		else:
			log.info('New password request for %s (%s)' % (mail, alt))

		if len(mail.strip()) <= 0 or len(alt.strip()) <= 0:
			log.info('Given mail (%s) or alternative mail (%s) is invalid given!' % (mail, alt))
			return False

		maccount = MailAccount.getByEMail(mail)
		if maccount is None:
			log.info('Could not find a valid mail account for %s' % (mail,))
			return False

		# now check alternative addr
		if maccount.altMail != alt:
			log.info('Alternative Mail %s is wrong (expected: %s)!' % (alt, maccount.altMail))
			return False

		# now check if it is really an account!
		if maccount.type != MailAccount.TYPE_ACCOUNT:
			log.info('Can not request a new password for forwarding mails (%s)' % (mail,))
			return False

		# now create auth code and send mail!
		if maccount.createAuthCode():
			m = Mailer(maccount)
			return m.sendPasswordLink()
		else:
			log.warning('Could not create auth code for %s!' % (mail,))
			return False


	def sendpw(self, data):
		# <mail/username> <authcode>
		try:
			(mail, authcode) = data.split(' ', 1)
		except:
			return False

		if len(mail.strip()) <= 0 or len(authcode.strip()) <= 0:
			return False

		maccount = MailAccount.getByEMail(mail)
		if maccount is None:
			return False

		# now check auth code
		if maccount.authCode != authcode:
			return False

		# now check valid date!
		if maccount.authValid is None or maccount.authValid < datetime.datetime.now():
			return False

		# now send new pw!
		maccount.generatePassword()
		if maccount.changePassword(maccount.pw):
			m = Mailer(maccount)
			return m.sendNewPassword()
		else:
			return False

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
		rmtCert = FLSCertificate.fromDict(cert)
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

	def __init__(self, privkey, pubkey, cacert, addr, requestHandler=FLSRequestHandler,
					logRequests=True, allow_none=False, encoding=None, bind_and_activate=True):
		self.logRequests = logRequests

		FLSXMLRPCDispatcher.__init__(self, allow_none, encoding)
		socketserver.BaseServer.__init__(self, addr, requestHandler)
		self.socket = ssl.wrap_socket(
			socket.socket(self.address_family, self.socket_type),
			server_side=True,
			keyfile=privkey,
			certfile=pubkey,
			ca_certs=cacert,
			cert_reqs=ssl.CERT_REQUIRED,
			ssl_version=ssl.PROTOCOL_TLSv1,
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
		if os.path.exists(connection):
			# is a server running with this socket?
			os.unlink(connection)
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
	try:
		threads.append(FLSCpServer((conf.get('connection', 'host'), conf.getint('connection', 'port'))))
		threads.append(FLSCpUnixServer(conf.get('connection', 'socket')))
	except Exception as e:
		sys.stderr.write('Could not start the server(s), because of %s\n' % (e,))
		sys.exit(127)

	for t in threads:
		t.start()

	try:
		for t in threads:
			t.join()
	except KeyboardInterrupt as e:
		log.info('Try to stop the cp server (press again ctrl+c to quit)...')
		for t in threads:
			t.shutdown()

