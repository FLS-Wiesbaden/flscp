import hashlib
import base64
import binascii
import time
import struct
import math

class SaltEncryption:

	def __init__(self, rounds=10000, sha1=True, saltLng = 16, password=''):
		self.rounds = rounds
		self.sha1 = sha1
		self.saltLng = saltLng
		self.password = password

	def hash(self, pwd, salt = None):
		if salt is None:
			salt = self.generateSalt()

		header = self.generateHeader()
		key = '%s%s%s' % (salt.decode('utf-8'), pwd, self.password)

		if self.sha1:
			key = hashlib.sha1(key.encode('utf-8')).hexdigest()
		else:
			key = hashlib.md5(key.encode('utf-8')).hexdigest()

		key = base64.b64encode(binascii.unhexlify(self.keyStretching(key).encode('utf-8')))

		return '%s;%s;%s' % (header.decode('utf-8'), salt.decode('utf-8'), key.decode('utf-8'))

	def compare(self, pwd, hash):
		t = hash.split(';')

		if len(t) == 3:
			header, salt, value = t
			header = base64.b64decode('%s==' % (header,))
			rounds = header[1] << 16 | header[2] << 8 | header[3]
			flag = ((header[0] & 0x80) >> 7) == 1

			# save the settings
			tmpRounds = self.rounds
			tmpSHA1 = self.sha1
			self.rounds = rounds
			self.sha1 = flag

			equal = self.hash(pwd, salt.encode('utf-8')) == hash

			# restore settings
			self.rounds = tmpRounds
			self.sha1 = tmpSHA1
		else:
			equal = False

		return equal

	def info(self):
		print('Improved Hash Algorithm')
		print('Version: Rolling Release ;)')
		print('Algorithm: %s' % ('SHA1' if self.sha1 else 'MD5',))
		print('Rounds: %i' % (self.rounds,))
		print('Salt-Length: %i' % (self.saltLng,))
		print('Password: %s' % ('Yes' if len(self.password) > 0 else 'No',))

		self.benchmark()

	def benchmark(self, num = 1000):
		print('Generating %i hashs!' % (num,))

		start = time.time()
		for f in range(0, num):
			self.hash('Benchmark')

		end = time.time()

		diff = end-start

		print('Generated in %f seconds; %f per hash.' % (diff, diff/num))		

	def keyStretching(self, key):
		for i in range(0, self.rounds):
			if self.sha1:
				key = hashlib.sha1(key.encode('utf-8')).hexdigest()
			else:
				key = hashlib.md5(key.encode('utf-8')).hexdigest()

		return key

	def generateSalt(self):
		salt = base64.b64encode(binascii.unhexlify(hashlib.md5(('%f %d' % math.modf(time.time())).encode('utf-8')).hexdigest()))
		return salt[0:self.saltLng]

	def generateHeader(self):
		rounds = self.rounds
		flag = (1 if self.sha1 else 0) << 7

		return base64.b64encode(struct.pack('>L', rounds | flag << 24))[0:6]
