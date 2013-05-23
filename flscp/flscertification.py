#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime

class FLSCertificateGeneralSubject:

	def __init__(self):
		self.commonName = None
		self.emailAddress = None

	def __hash__(self):
		return hash('cn=%s,ea=%s' % (self.commonName, self.emailAddress))

class FLSCertificateIssuer(FLSCertificateGeneralSubject):

	def __init__(self):
		super().__init__()
		self.organizationName = None
		self.organizationalUnitName = None

	@classmethod
	def fromPyDict(sh, obj):
		sh = FLSCertificateIssuer()
		sh.commonName = obj['commonName']
		sh.emailAddress = obj['emailAddress']
		sh.organizationName = obj['organizationName']
		sh.organizationalUnitName = obj['organizationalUnitName']

		self = sh
		return self

	def __hash__(self):
		return hash(
			'cn=%s,ea=%s,on=%s,ou=%s' % (
				self.commonName, self.emailAddress, self.organizationName, 
				self.organizationalUnitName)
			)

class FLSCertificateSubject(FLSCertificateGeneralSubject):

	def __init__(self):
		super().__init__()

	@classmethod
	def fromPyDict(sh, obj):
		sh = FLSCertificateSubject()
		sh.commonName = obj['commonName']
		sh.emailAddress = obj['emailAddress']

		self = sh
		return self

class FLSCertificate:
	STATE_OK = 0
	STATE_DELETE = 1
	STATE_ADDED = 2

	def __init__(self):
		self.issuer = None
		self.notAfter = None
		self.notBefore = None
		self.serialNumber = None
		self.subject = None
		#self.version = None
		self.state = FLSCertificate.STATE_OK

	def setIssuer(self, issuer):
		if not isinstance(issuer, FLSCertificateIssuer):
			raise TypeError('Expected object of type FLSCertificateIssuer')

		self.issuer = issuer

	def setSubject(self, subject):
		if not isinstance(subject, FLSCertificateSubject):
			raise TypeError('Expected object of type FLSCertificateSubject')

		self.subject = subject

	def setSerialNumber(self, srn):
		try:
			self.serialNumber = int(srn)
		except ValueError:
			# convert!
			try:
				self.serialNumber = int(srn, 16)
			except:
				raise

	def __hash__(self):
		return hash(
			'sn=%s,sub=%s,iss=%s' % (
				self.serialNumber, self.subject.__hash__(), self.issuer.__hash__())
			)

	@classmethod
	def fromDict(sh, obj):
		sh = FLSCertificate()
		if 'issuer' in obj:
			issuer = FLSCertificateIssuer()
			for f in obj['issuer']:
				if len(f) == 1 and len(f[0]) == 2:
					setattr(issuer, f[0][0], f[0][1])
			sh.setIssuer(issuer)
		if 'subject' in obj:
			subject = FLSCertificateSubject()
			for f in obj['subject']:
				if len(f) == 1 and len(f[0]) == 2:
					setattr(subject, f[0][0], f[0][1])
			sh.setSubject(subject)
		if 'notAfter' in obj:
			sh.notAfter = datetime.datetime.strptime(obj['notAfter'], '%b %d %H:%M:%S %Y %Z')
		if 'notBefore' in obj:
			sh.notBefore = datetime.datetime.strptime(obj['notBefore'], '%b %d %H:%M:%S %Y %Z')
		#if 'version' in obj:
		#	sh.version = obj['version']
		if 'serialNumber' in obj:
			sh.setSerialNumber(obj['serialNumber'])

		now = datetime.datetime.now()
		if sh.serialNumber is None or sh.notAfter is None or sh.notBefore is None:
			return None
		elif not sh.notBefore <= now <= sh.notAfter:
			return None
		else:
			self = sh
			return self

	@classmethod
	def fromPyDict(sh, obj):
		#import rpdb2; rpdb2.start_embedded_debugger('test', fDebug=True, fAllowUnencrypted=False, timeout=5)
		sh = FLSCertificate()
		sh.setSerialNumber(obj['serialNumber'])
		sh.notAfter = obj['notAfter']
		sh.notBefore = obj['notBefore']
		sh.state = obj['state']
		#sh.version = obj['version']
		sh.setIssuer(FLSCertificateIssuer.fromPyDict(obj['issuer']))
		sh.setSubject(FLSCertificateSubject.fromPyDict(obj['subject']))
		self = sh

		return self

class FLSCertificateList:

	def __init__(self):
		self._certs = []

	def add(self, cert):
		if not isinstance(cert, FLSCertificate):
			raise TypeError('Expected object of type FLSCertificate')
		else:
			self._certs.append(cert)

	def remove(self, obj):
		key = self.getKeyByHash(obj.__hash__())
		if key >= 0:
			self.__delitem__(key)
		else:
			raise ValueError('FLSCertificateList.remove(obj): obj is not in list.')


	def getKeyByHash(self, hsh):
		k = 0
		for f in self._certs:
			if f.__hash__() == hsh:
				return k
			k += 1

		return None

	def getKey(self, obj):
		k = 0
		for f in self._certs:
			if f == obj:
				return k

			k += 1

		return None

	def __getitem__(self, key):
		return self._certs[key]

	def __setitem__(self, key, value):
		self._certs[key] = value

	def __delitem__(self, key):
		del(self._certs[key])

	def __iter__(self):
		for f in self._certs:
			yield f

	def __contains__(self, item):
		for f in self._certs:
			if item.__hash__() == f.__hash__():
				return True
		return False

	def __len__(self):
		return len(self._certs)

	def findByHash(self, hsh):
		print('searching for cert with hash %i' % (hsh,))
		for f in self._certs:
			if f.__hash__() == hsh:
				return f

		return None

	@classmethod
	def fromPyDict(sh, obj):
		sh = FLSCertificateList()
		for f in obj:
			cert = FLSCertificate.fromPyDict(f)
			sh.add(cert)

		self = sh
		return self