#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: fenc=utf-8:ts=8:sw=8:si:sta:noet
import os
import logging
import re
import smtplib
from email.mime.text import MIMEText

workDir = os.path.dirname(os.path.realpath(__file__))

class Mailer:

	def __init__(self, account):
		self.account = account
		self.log = logging.getLogger('flscp')

	def newAccount(self):
		# exist custom template?
		mailContent = Mailer.getMail('newmail')
		if mailContent is None:
			self.log.warning('Could not load mail "newmail"!')
			return False

		msg = MIMEText(
			mailContent['body'] % {
				'username': '%s@%s' % (self.account.mail,self.account.domain),
				'password': self.account.pw,
				'forwarders': ', '.join(self.account.forward) if len(self.account.forward) > 0 else mailContent['params']['noforward'],
				'notgenerated': mailContent['params']['notgenerated'] if not self.account.genPw else ''
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
			self.log.warning('Could not load mail "newforward"!')
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
			self.log.warning('Could not load mail "changemail"!')
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

	def sendPasswordLink(self):
		# exist custom template?
		mailContent = Mailer.getMail('sendpwlink')
		if mailContent is None:
			self.log.warning('Could not load mail "sendpwlink"!')
			return False

		msg = MIMEText(
			mailContent['body'] % {
				'username': '%s@%s' % (self.account.mail,self.account.domain),
				'authcode': '%s' % (self.account.authCode,),
				'authvalid': self.account.authValid.strftime('%d.%m.%Y %H:%M:%S')
			},
			_charset='utf-8'
		)

		msg['Subject'] = mailContent['subject']
		msg['From'] = mailContent['sender']
		msg['To'] = self.account.altMail

		return Mailer.sendMail(msg, mailContent['sender'], self.account.altMail)

	def sendNewPassword(self):
		# exist custom template?
		mailContent = Mailer.getMail('sendpw')
		if mailContent is None:
			self.log.warning('Could not load mail "sendpw"!')
			return False

		msg = MIMEText(
			mailContent['body'] % {
				'username': '%s@%s' % (self.account.mail,self.account.domain),
				'password': '%s' % (self.account.pw,)
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
			self.log.warning('Could not load mail "changeforward"!')
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
			log = logging.getLogger('flscp')
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
		homePath = os.path.expanduser('~/.config/flscp')
		etcPath = '/etc/flscp/templates'
		localEtcPath = '/usr/local/etc/flscp/templates'

		content = None
		# try to find custom
		if os.path.exists('%s/custom/%s.txt' % (homePath, mail)):
			with open('%s/custom/%s.txt' % (homePath, mail), 'rb') as f:
				content = f.read()
		elif os.path.exists('%s/custom/%s.txt' % (etcPath, mail)):
			with open('%s/custom/%s.txt' % (etcPath, mail), 'rb') as f:
				content = f.read()
		elif os.path.exists('%s/custom/%s.txt' % (localEtcPath, mail)):
			with open('%s/custom/%s.txt' % (localEtcPath, mail), 'rb') as f:
				content = f.read()
		elif os.path.exists('%s/custom/%s.txt' % (basePath, mail)):
			with open('%s/custom/%s.txt' % (basePath, mail), 'rb') as f:
				content = f.read()
		else:
			with open('%s/default/%s.txt' % (basePath, mail), 'rb') as f:
				content = f.read()

		if content is None:
			return None
		else:
			content = content.decode('utf-8')

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
