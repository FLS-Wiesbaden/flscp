#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from logging.handlers import WatchedFileHandler
from ansistrm import ColorizingStreamHandler
from ui.ui_cp import *
from ui.ui_mailform import *
from ui.ui_maileditor import *
from PyQt4.QtCore import pyqtSlot, pyqtSignal
from PyQt4 import QtGui
from PyQt4 import QtCore
from Printer import Printer
from pytz import UTC
import logging, os, sys, re, copy, uuid, zlib, xmlrpc.client, http.client, ssl, socket, datetime
import tempfile, zipfile, base64
from modules import flscertification
from modules.domain import DomainAccountList, Domain
from modules.mail import MailAccountList, MailAccount
try:
	import OpenSSL
except ImportError:
	pass

__author__  = 'Lukas Schreiner'
__copyright__ = 'Copyright (C) 2013 - 2013 Website-Team Friedrich-List-Schule-Wiesbaden'
__version__ = '0.3'

FORMAT = '%(asctime)-15s %(message)s'
formatter = logging.Formatter(FORMAT, datefmt='%b %d %H:%M:%S')
log = logging.getLogger()
log.setLevel(logging.INFO)
hdlr = ColorizingStreamHandler()
hdlr.setFormatter(formatter)
log.addHandler(hdlr)

workDir = os.path.dirname(os.path.realpath(__file__))

##### CONFIGURE #####
# connection
RPCHOST 		= 'cp.lschreiner.de' 
RPCPORT 		= 10027
RPCPATH			= 'RPC2'
# ssl connection
KEYFILE 		= 'certs/clientKey.pem'
CERTFILE 		= 'certs/clientCert.pem'
CACERT 			= 'certs/cacert.pem'
### CONFIGURE END ###

try:
	_encoding = QtGui.QApplication.UnicodeUTF8
	def _translate(context, text, disambig):
		return QtGui.QApplication.translate(context, text, disambig, _encoding)
except AttributeError:
	def _translate(context, text, disambig):
		return QtGui.QApplication.translate(context, text, disambig)

def MailValidator(email):
	if email is None:
		return False

	return re.match(r"^[a-zA-Z0-9._%-+]+\@[a-zA-Z0-9._%-]+\.[a-zA-Z]{2,}$", email) != None

class MailEditor(QtGui.QDialog):
	
	def __init__(self, parent):
		QtGui.QDialog.__init__(self, parent=parent)

		self.accepted = False
		self.ui = Ui_MailEditor()
		self.ui.setupUi(self)

		self.ui.buttonBox.accepted.connect(self.setAcceptState)
		self.ui.buttonBox.rejected.connect(self.setRejectState)

		buttonRole = dict((x, n) for x, n in vars(QtGui.QDialogButtonBox).items() if \
				isinstance(n, QtGui.QDialogButtonBox.StandardButton))
		self.okButton = self.ui.buttonBox.button(buttonRole['Ok'])
		if self.okButton is not None:
			# we found button!!!
			self.okButton.setDisabled(True)

		self.ui.fldMail.textChanged.connect(self.checkValidMail)

		# init
		self.checkValidMail()

	@pyqtSlot()
	def checkValidMail(self):
		log.debug('Check valid mail!!!!')
		palette = QtGui.QPalette()

		if len(self.ui.fldMail.text().strip()) == 0 \
				or not MailValidator(self.ui.fldMail.text()):
			palette.setColor(self.ui.fldMail.backgroundRole(), QtGui.QColor(255, 110, 110))
			self.okButton.setDisabled(True)
		else:
			palette.setColor(self.ui.fldMail.backgroundRole(), QtGui.QColor(151, 255, 139))
			self.okButton.setDisabled(False)

		self.ui.fldMail.setPalette(palette)

	@pyqtSlot()
	def setAcceptState(self):
		self.accepted = True

	@pyqtSlot()
	def setRejectState(self):
		self.accepted = False

	def getValue(self):
		return self.ui.fldMail.text()

class MailForm(QtGui.QDialog):
	
	def __init__(self, parent, account = None):
		QtGui.QDialog.__init__(self, parent=parent)
		self.rpc = FlsServer.getInstance()

		self.ui = Ui_MailForm()
		self.ui.setupUi(self)
		self.account = account
		self.orgAccount = copy.copy(account)

		self.aborted = False

		self.actions()

		self.initFields()

	def initFields(self):
		# load domains
		try:
			for f in self.rpc.getDomains():
				print(f)
				self.ui.fldDomain.addItem(f['domain'], f['id'])
		except ssl.CertificateError as e:
			log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
		except socket.error as e:
			log.error('Connection to server lost!')
		except xmlrpc.client.ProtocolError as e:
			if e.errcode == 403:
				log.warning('Missing rights for loading mails (%s)' % (e,))
			else:
				log.warning('Unexpected error in protocol: %s' % (e,))
		
		if self.account is None:
			return

		self.ui.fldID.setText('%s' % (self.account.id,))
		self.ui.fldMail.setText(self.account.mail)
		did = self.ui.fldDomain.findText(self.account.domain)
		if did == -1:
			self.ui.fldDomain.addItem(self.account.domain)
			did = self.ui.fldDomain.findText(self.account.domain)
		self.ui.fldDomain.setCurrentIndex(did)

		self.ui.fldAltMail.setText(self.account.altMail)
		for f in self.account.forward:
			item = QtGui.QListWidgetItem()
			item.setText(f)
			self.ui.fldForward.addItem(item)

		if self.account.type == MailAccount.TYPE_ACCOUNT:
			self.ui.fldTypeAccount.setChecked(True)
			self.ui.fldTypeForward.setChecked(False)
		else:
			self.ui.fldTypeAccount.setChecked(False)
			self.ui.fldTypeForward.setChecked(True)

	def actions(self):
		self.ui.butForwardDel.clicked.connect(self.deleteMail)
		self.ui.butForwardAdd.clicked.connect(self.addMail)
		self.ui.fldForward.itemChanged.connect(self.mailChanged)

		self.ui.buttonBox.accepted.connect(self.save)
		self.ui.buttonBox.rejected.connect(self.cancel)

	@pyqtSlot()
	def save(self):
		self.aborted = False
		if self.validate():
			if self.account is None:
				self.createMail()
			else:
				self.saveMail()
			self.accept()

	@pyqtSlot()
	def cancel(self):
		self.aborted = True
		self.reject()

	def validate(self):
		log.info('Validating...')
		# reset all palettes...
		items = [
			self.ui.fldMail, self.ui.fldPw, self.ui.fldPwRepeat, self.ui.fldGenPw, self.ui.fldDomain,
			self.ui.fldForward, self.ui.fldAltMail, self.ui.fldTypeForward, self.ui.fldTypeAccount
		]

		for item in items:
			palette = QtGui.QPalette()
			item.setPalette(palette)

		state = True

		if len(self.ui.fldMail.text()) <= 0:
			palette = QtGui.QPalette()
			palette.setColor(self.ui.fldMail.backgroundRole(), QtGui.QColor(255, 110, 110))
			self.ui.fldMail.setPalette(palette)
			state = state and False

		if len(self.ui.fldDomain.currentText().strip()) <= 0:
			palette = QtGui.QPalette()
			palette.setColor(self.ui.fldDomain.backgroundRole(), QtGui.QColor(255, 110, 110))
			self.ui.fldDomain.setPalette(palette)
			state = state and False

		# check domain:
		if len(self.ui.fldMail.text()) > 0 and len(self.ui.fldDomain.currentText().strip()) > 0 \
			and not MailValidator('%s@%s' % (self.ui.fldMail.text(), self.ui.fldDomain.currentText())):
			palette = QtGui.QPalette()
			palette.setColor(self.ui.fldMail.backgroundRole(), QtGui.QColor(255, 110, 110))
			self.ui.fldMail.setPalette(palette)
			palette = QtGui.QPalette()
			palette.setColor(self.ui.fldDomain.backgroundRole(), QtGui.QColor(255, 110, 110))
			self.ui.fldDomain.setPalette(palette)
			state = state and False

		if len(self.ui.fldPw.text()) > 0 \
			or len(self.ui.fldPwRepeat.text()) > 0:
			if self.ui.fldPw.text() != self.ui.fldPwRepeat.text():
				palette = QtGui.QPalette()
				palette.setColor(self.ui.fldPw.backgroundRole(), QtGui.QColor(255, 110, 110))
				self.ui.fldPw.setPalette(palette)
				palette = QtGui.QPalette()
				palette.setColor(self.ui.fldPwRepeat.backgroundRole(), QtGui.QColor(255, 110, 110))
				self.ui.fldPwRepeat.setPalette(palette)
				state = state and False

		if self.ui.fldTypeForward.isChecked():
			if self.ui.fldForward.count() <= 0:
				palette = QtGui.QPalette()
				palette.setColor(self.ui.fldForward.backgroundRole(), QtGui.QColor(255, 110, 110))
				self.ui.fldForward.setPalette(palette)
				state = state and False
			elif not self.forwardMailsValid():
				palette = QtGui.QPalette()
				palette.setColor(self.ui.fldForward.backgroundRole(), QtGui.QColor(255, 110, 110))
				self.ui.fldForward.setPalette(palette)
				state = state and False

		# fields have to be filled (like mail, domain,...)
		self.ui.fldMail.setText(self.ui.fldMail.text().strip())
		if len(self.ui.fldMail.text()) <= 0:
			palette = QtGui.QPalette()
			palette.setColor(self.ui.fldMail.backgroundRole(), QtGui.QColor(255, 110, 110))
			self.ui.fldMail.setPalette(palette)
			state = state and False

		self.ui.fldAltMail.setText(self.ui.fldAltMail.text().strip())
		if len(self.ui.fldAltMail.text()) <= 0 \
			or not MailValidator(self.ui.fldAltMail.text()):
			palette = QtGui.QPalette()
			palette.setColor(self.ui.fldAltMail.backgroundRole(), QtGui.QColor(255, 110, 110))
			self.ui.fldAltMail.setPalette(palette)
			state = state and False

		# if mail forward: no pw and no pw gen!
		if self.ui.fldTypeForward.isChecked() \
			and (len(self.ui.fldPw.text()) > 0 or self.ui.fldGenPw.isChecked()):
			palette = QtGui.QPalette()
			palette.setColor(self.ui.fldGenPw.backgroundRole(), QtGui.QColor(255, 110, 110))
			self.ui.fldGenPw.setPalette(palette)
			palette = QtGui.QPalette()
			palette.setColor(self.ui.fldPw.backgroundRole(), QtGui.QColor(255, 110, 110))
			self.ui.fldPw.setPalette(palette)
			state = state and False		

		# if mail account: pw or pw gen (but only on creation!)
		if self.ui.fldTypeAccount.isChecked() \
			and (self.account is None or self.account.state == MailAccount.STATE_CREATE) \
			and len(self.ui.fldPw.text()) <= 0 \
			and not self.ui.fldGenPw.isChecked():
			palette = QtGui.QPalette()
			palette.setColor(self.ui.fldGenPw.backgroundRole(), QtGui.QColor(255, 110, 110))
			self.ui.fldGenPw.setPalette(palette)
			palette = QtGui.QPalette()
			palette.setColor(self.ui.fldPw.backgroundRole(), QtGui.QColor(255, 110, 110))
			self.ui.fldPw.setPalette(palette)
			state = state and False

		log.info('Validation result: %s' % ('valid' if state else 'invalid',))
		return state

	def forwardMailsValid(self):
		state = True
		i = 0
		while i < self.ui.fldForward.count():
			item = self.ui.fldForward.item(i)
			if len(item.text().strip()) == 0 or not MailValidator(item.text()):
				item.setBackground(QtGui.QBrush(QtGui.QColor(255, 110, 110)))
				state = state and False
			else:
				item.setBackground(QtGui.QBrush(QtGui.QColor(151, 255, 139)))
			i += 1

		return state

	def createMail(self):
		self.account = MailAccount()
		self.account.generateId()
		self.account.mail = self.ui.fldMail.text()
		self.account.domain = self.ui.fldDomain.currentText()
		self.account.altMail = self.ui.fldAltMail.text()
		self.account.pw = self.ui.fldPw.text()
		self.account.genPw = self.ui.fldGenPw.isChecked()
		self.account.forward = []
		i = 0
		while i < self.ui.fldForward.count():
			self.account.forward.append(self.ui.fldForward.item(i).text())
			i += 1
		if self.ui.fldTypeAccount.isChecked():
			self.account.type = MailAccount.TYPE_ACCOUNT
		elif self.ui.fldTypeForward.isChecked():
			self.account.type = MailAccount.TYPE_FORWARD
		self.account.state = MailAccount.STATE_CREATE

	def saveMail(self):
		self.account.mail = self.ui.fldMail.text()
		self.account.domain = self.ui.fldDomain.currentText()
		self.account.altMail = self.ui.fldAltMail.text()
		self.account.pw = self.ui.fldPw.text()
		self.account.genPw = self.ui.fldGenPw.isChecked()
		self.account.forward = []
		i = 0
		while i < self.ui.fldForward.count():
			self.account.forward.append(self.ui.fldForward.item(i).text())
			i += 1
		if self.ui.fldTypeAccount.isChecked():
			self.account.type = MailAccount.TYPE_ACCOUNT
		elif self.ui.fldTypeForward.isChecked():
			self.account.type = MailAccount.TYPE_FORWARD

		if self.account != self.orgAccount:
			log.info('Account was changed!')
			# if it was created and not commited, we have to let the state "create".
			if self.account.state != MailAccount.STATE_CREATE:
				self.account.state = MailAccount.STATE_CHANGE
		else:
			log.info('Account is unchanged!')

	@pyqtSlot(QtGui.QListWidgetItem)
	def mailChanged(self, item):
		log.info('Cell changed:')
		# check state
		if len(item.text().strip()) == 0 or not MailValidator(item.text()):
			item.setBackground(QtGui.QBrush(QtGui.QColor(255, 110, 110)))
		else:
			item.setBackground(QtGui.QBrush(QtGui.QColor(151, 255, 139)))

	@pyqtSlot()
	def addMail(self):
		item = QtGui.QListWidgetItem()
		item.setFlags(
			QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsEditable|QtCore.Qt.ItemIsDragEnabled|
			QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled
		)
		self.ui.fldForward.addItem(item)

	@pyqtSlot()
	def deleteMail(self):
		for selectedItem in self.ui.fldForward.selectedItems():
			self.ui.fldForward.takeItem(self.ui.fldForward.row(selectedItem))

class FLSSafeTransport(xmlrpc.client.Transport):
	"""Handles an HTTPS transaction to an XML-RPC server."""

	def make_connection(self, host):
		if not hasattr(self, 'timeout'):
			self.timeout = 5

		if self._connection and host == self._connection[0]:
			return self._connection[1]

		if not hasattr(http.client, "HTTPSConnection"):
			raise NotImplementedError(
			"your version of http.client doesn't support HTTPS")
		# create a HTTPS connection object from a host descriptor
		# host may be a string, or a (host, x509-dict) tuple
		#context = ssl.SSLContext(ssl.PROTOCOL_SSLv3)
		context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
		context.verify_mode = ssl.CERT_REQUIRED
		context.load_verify_locations(CACERT)
		log.debug('Timeout is: %s' % (self.timeout,))

		chost, self._extra_headers, x509 = self.get_host_info(host)
		self._connection = host, http.client.HTTPSConnection(
			chost,
			None, 
			key_file=KEYFILE,
			cert_file=CERTFILE,
			context=context,
			timeout=self.timeout,
			check_hostname=False
		)
		return self._connection[1]

class FlsServer(xmlrpc.client.ServerProxy):
	__instance = None

	def __init__(self):
		super().__init__('https://%s:%i/%s' % (RPCHOST, RPCPORT, RPCPATH), FLSSafeTransport(), allow_none=True)
		FlsServer.__instance = self

	@staticmethod
	def getInstance():
		return FlsServer.__instance if FlsServer.__instance is not None else FlsServer()

class FLScpMainWindow(QtGui.QMainWindow):

	def __init__(self):
		QtGui.QMainWindow.__init__(self)
		
		self.ui = Ui_MainWindow()
		self.ui.setupUi(self)
		self.resizeModes = dict((x, n) for x, n in vars(QtGui.QHeaderView).items() if \
				isinstance(n, QtGui.QHeaderView.ResizeMode))
		self.ui.mailTable.horizontalHeader().setResizeMode(self.resizeModes['Stretch'])
		self.ui.adminTable.horizontalHeader().setResizeMode(self.resizeModes['Stretch'])
		self.ui.adminTable.hideColumn(0)

		self.version = ''

		self.mails = MailAccountList()
		self.domains = DomainAccountList()
		self.certs = flscertification.FLSCertificateList()
		self.splash = QtGui.QSplashScreen(self, QtGui.QPixmap(":/logo/splash.png"))
		self.splash.show()
		self.splash.showMessage('Loading application...', color=QtGui.QColor(255, 255, 255))
		self.splash.repaint()
		#QtCore.QCoreApplication.processEvents()

		# check if certs exists!
		if not os.path.exists(KEYFILE) or not os.path.exists(CERTFILE):
			log.warning('Certs does not exist!')
			self.rpc = None
		else:
			# connect to xml-rpc 
			self.rpc = FlsServer.getInstance()
			self.showLoginUser()

		self.actions()

	def actions(self):
		# menu
		self.ui.actionExit.triggered.connect(self.quitApp)
		self.ui.actionWhatsThis.triggered.connect(self.triggerWhatsThis)
		self.ui.actionAbout.triggered.connect(self.about)
		self.ui.actionAboutQt.triggered.connect(self.aboutQt)

		# home
		self.ui.butHomeDomain.clicked.connect(self.switchToDomain)
		self.ui.butHomeMail.clicked.connect(self.switchToMail)
		self.ui.butHomeCert.clicked.connect(self.switchToAdmin)

		# domain tab
		#self.ui.butDomainAdd.clicked.connect(self.addDomain)
		#self.ui.butDomainDel.clicked.connect(self.deleteDomain)
		self.ui.butDomainReload.clicked.connect(self.reloadDomainTree)
		#self.ui.butDomainSave.clicked.connect(self.commitDomainData)
		#self.ui.domainTree.cellDoubleClicked.connect(self.selectedMail)

		# mail tab
		self.ui.butAdd.clicked.connect(self.addMail)
		self.ui.butEdt.clicked.connect(self.editMail)
		self.ui.butDel.clicked.connect(self.deleteMail)
		self.ui.butReload.clicked.connect(self.reloadMailTable)
		self.ui.butSave.clicked.connect(self.commitMailData)
		self.ui.mailTable.cellDoubleClicked.connect(self.selectedMail)
		self.ui.search.textChanged.connect(self.filterMail)

		# certs tab
		try:
			import OpenSSL
		except ImportError:
			self.ui.butAdminAdd.setEnabled(False)
		else:
			self.ui.butAdminAdd.clicked.connect(self.addCertificate)
		self.ui.butAdminDel.clicked.connect(self.deleteCertificates)
		self.ui.butAdminSave.clicked.connect(self.commitCertData)
		self.ui.butAdminReload.clicked.connect(self.reloadCertTable)

	def showLoginUser(self):
		self.splash.showMessage('Loading user authentication...', color=QtGui.QColor(255, 255, 255))
		self.splash.repaint()

		pubkey = None
		aborted = False
		pk = None
		content = ''
		with open(CERTFILE, 'r') as f:
			content = f.read()

		try:
			pk = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, content)
		except OpenSSL.crypto.Error as err:
			log.info('OK,... this is not a public key: %s (%s)' % (CERTFILE, err))

			# try to load private
			passphrase = ''
			loaded = False
			while not loaded and not aborted:
				try:
					pk = OpenSSL.crypto.load_privatekey(OpenSSL.crypto.FILETYPE_PEM, content, passphrase.encode('utf-8'))
				except OpenSSL.crypto.Error as e:
					log.warning('Got error: %s' % (e,))
					passphrase = QtGui.QInputDialog.getText(
						self, 
						_translate('MainWindow', 'Kennwort erforderlich', None),
						_translate('MainWindow', 'Kennwort für %s' % (CERTFILE,), None),
						QtGui.QLineEdit.Password,
						''
					)
					(passphrase, ok) = passphrase
					aborted = not ok
				else:
					loaded = True

		if aborted or pk is None:
			log.info('Login certificate not loadable (%s)!' % (CERTFILE,))

		try:
			pubkey = pk.get_certificate()
		except AttributeError:
			pubkey = pk
		else:
			if pubkey.has_expired():
				QtGui.QMessageBox.information(
					self, _translate('MainWindow', 'Information', None), 
					_translate(
						'MainWindow', 
						'Zertifikat "%s" ist abgelaufen und wird übersprungen.' % (f,), 
						None
					)
				)

		if pubkey is not None:
			pubsub = pubkey.get_subject()
			#subject.commonName = pubsub.commonName
			#subject.emailAddress = pubsub.emailAddress
			self.ui.labUser = QtGui.QLabel(self)
			self.ui.labUser.setObjectName("labUser")
			self.ui.labUser.setText(
				_translate("MainWindow", "Logged in as %s <%s>" % (pubsub.commonName, pubsub.emailAddress), None)
			)
			self.ui.statusbar.addWidget(self.ui.labUser)

	@pyqtSlot()
	def switchToDomain(self):
		self.ui.tabWidget.setCurrentIndex(1)

	@pyqtSlot()
	def switchToMail(self):
		self.ui.tabWidget.setCurrentIndex(2)

	@pyqtSlot()
	def switchToAdmin(self):
		self.ui.tabWidget.setCurrentIndex(3)

	@pyqtSlot()
	def init(self):
		# enable splash screen
		self.splash.showMessage('Try to connect to server...', color=QtGui.QColor(255, 255, 255))
		self.splash.repaint()
		
		if self.rpc is not None:
			# connection possible ?
			timeout = self.rpc.__transport.timeout
			self.rpc.__transport.timeout = 1
			try:
				p = self.rpc.ping()
			except ssl.SSLError as e:
				log.debug('Connection not possible: %s' % (e,))
				QtGui.QMessageBox.critical(
					self, _translate('MainWindow', 'Verbindung nicht möglich', None), 
					_translate('MainWindow', 
						'Möglicher Angriffsversuch: die SSL-gesicherte Verbindung ist aus Sicherheitsgründen abgebrochen worden.', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)

				self.close()
				return
			except socket.error as e:
				log.debug('Connection not possible: %s' % (e,))
				QtGui.QMessageBox.critical(
					self, _translate('MainWindow', 'Verbindung nicht möglich', None), 
					_translate('MainWindow', 
						'Keine Verbindung zum Server möglich. Prüfen Sie die VPN-Verbindung!', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)

				self.close()
				return
			self.rpc.__transport.timeout = timeout

			# connection possible - now check the version
			self.splash.showMessage('Check version...', color=QtGui.QColor(255, 255, 255))
			self.splash.repaint()
			upToDate = self.rpc.upToDate(__version__)
			if not upToDate:
				self.updateVersion()

			# load the data!
			self.splash.showMessage('Loading domains...', color=QtGui.QColor(255, 255, 255))
			self.splash.repaint()

			# domains
			try:
				self.loadDomains()
			except xmlrpc.client.Fault as e:
				log.critical('Could not load domains because of %s' % (e,))
				QtGui.QMessageBox.critical(
					self, _translate('MainWindow', 'Daten nicht ladbar', None), 
					_translate('MainWindow', 
						'Die Domains konnten nicht abgerufen werden.', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
			else:
				self.loadDomainData()

			# load the data!
			self.splash.showMessage('Loading mails...', color=QtGui.QColor(255, 255, 255))
			self.splash.repaint()

			# mails
			try:
				self.loadMails()
			except xmlrpc.client.Fault as e:
				log.critical('Could not load mails because of %s' % (e,))
				QtGui.QMessageBox.critical(
					self, _translate('MainWindow', 'Daten nicht ladbar', None), 
					_translate('MainWindow', 
						'Die E-Mail-Konten konnten nicht abgerufen werden.', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
			else:
				self.loadMailData()

			# load the data!
			self.splash.showMessage('Loading certs...', color=QtGui.QColor(255, 255, 255))
			self.splash.repaint()

			# certs
			try:
				self.loadCerts()
			except xmlrpc.client.Fault as e:
				log.critical('Could not load certificates because of %s' % (e,))
				QtGui.QMessageBox.critical(
					self, _translate('MainWindow', 'Daten nicht ladbar', None), 
					_translate('MainWindow', 
						'Die Zertifikate konnten nicht abgerufen werden.', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
			else:
				self.loadCertData()
		else:
			self.initLoginCert()

		# disable splash screen!
		self.splash.close()
		self.start()

	def updateVersion(self):
		self.splash.showMessage('New Version available. Downloading...', color=QtGui.QColor(255, 255, 255))
		self.splash.repaint()

		try:
			data = self.rpc.getCurrentVersion()
		except xmlrpc.client.Fault as e:
			log.critical('Could not update the flscp because of %s' % (e,))
			QtGui.QMessageBox.critical(
				self, _translate('MainWindow', 'Aktualisierung', None), 
				_translate('MainWindow', 
					'Eine neue Version konnte nicht heruntergeladen werden.', 
					None),
				QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
			)
		else:
			self.splash.showMessage('New Version available. Installing...', color=QtGui.QColor(255, 255, 255))
			self.splash.repaint()
			# now save it!
			data = base64.b64decode(data.encode('utf-8'))
			d = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
			d.write(data)
			d.close()
			# open zip
			zfile = zipfile.ZipFile(d.name, 'r')
			# crc ok?
			if zfile.testzip() is not None:
				log.warning('Corrupted update downloaded!')
				QtGui.QMessageBox.warning(
					self, _translate('MainWindow', 'Aktualisierung', None), 
					_translate('MainWindow', 
						'Das Update konnte nicht verifiziert werden (CRC Fehler)', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
				zfile.close()
				os.unlink(d.name)
				return

			# do we have an build folder?
			if os.path.exists('build' + os.sep):
				# yes, we have!
				extp = 'build' + os.sep + 'flscp' + os.sep
			else:
				extp = '.'
			zfile.extractall(extp)
			log.info('Update successful!')
			QtGui.QMessageBox.information(
				self, _translate('MainWindow', 'Aktualisierung', None), 
				_translate('MainWindow', 
					'Das Control Panel wurde erfolgreich aktualisiert. Bitte starten Sie die Anwendung neu!', 
					None),
				QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
			)
			zfile.close()
			os.unlink(d.name)

	def initLoginCert(self):
		answer = QtGui.QMessageBox.warning(
			self, _translate('MainWindow', 'Login erforderlich', None), 
			_translate('MainWindow', 
				'Es konnte kein Zertifikat zum Login gefunden werden.\nBitte wählen Sie im nachfolgenden Fenster ein PKCS12-Zertifikat aus.', 
				None),
			QtGui.QMessageBox.Ok|QtGui.QMessageBox.Cancel, QtGui.QMessageBox.Ok
		)
		if msg == QtGui.QMessageBox.Cancel:
			self.close()
			return

		try:
			import OpenSSL
		except:
			QtGui.QMessageBox.critical(
				self, _translate('MainWindow', 'Login nicht möglich', None), 
				_translate('MainWindow', 
					'Es ist das Python Modul "pyOpenSSL" notwendig! Programm wird beendet.', 
					None),
				QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
			)

			self.close()
			return

		fd = QtGui.QFileDialog(self, None)
		fd.setWindowModality(QtCore.Qt.ApplicationModal)
		fd.setOption(QtGui.QFileDialog.ReadOnly, True)
		filters = [_translate('MainWindow', 'Zertifikate (*.p12)', None)]
		fd.setNameFilters(filters)
		fd.setFileMode(QtGui.QFileDialog.ExistingFile | QtGui.QFileDialog.AcceptOpen)
		fd.filesSelected.connect(self.loginCertSelected)
		fd.show()

	@pyqtSlot(str)
	def loginCertSelected(self, f):
		if len(f) > 0:
			f = f[0]
		else:
			QtGui.QMessageBox.warning(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate(
					'MainWindow', 
					'Kein Zertifikat ausgewählt!', 
					None
				)
			)
			self.quit()
			return

		pubkey = None
		cnt = None
		with open(f, 'rb') as p12file:
			cnt = p12file.read()

		passphrase = ''
		loaded = False
		aborted = False
		pk = None
		while not loaded and not aborted:
			try:
				pk = OpenSSL.crypto.load_pkcs12(cnt, passphrase)
			except OpenSSL.crypto.Error as e:
				log.warning('Got error: %s' % (e,))
				passphrase = QtGui.QInputDialog.getText(
					self, 
					_translate('MainWindow', 'Kennwort erforderlich', None),
					_translate('MainWindow', 'Kennwort für %s' % (f,), None),
					QtGui.QLineEdit.Password,
					'',
				)
				(passphrase, ok) = passphrase
				aborted = not ok
			else:
				loaded = True

		if aborted or pk is None:
			QtGui.QMessageBox.warning(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate(
					'MainWindow', 
					'Zertifikat konnte nicht importiert werden.', 
					None
				)
			)
			self.quit()
			return

		pubkey = pk.get_certificate()
		privkey = pk.get_privatekey()
		if pubkey.has_expired():
			QtGui.QMessageBox.warning(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate(
					'MainWindow', 
					'Zertifikat ist abgelaufen und kann nicht verwendet werden.', 
					None
				)
			)
			self.quit()
			return

		if pubkey is None or privkey is None:
			QtGui.QMessageBox.warning(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate(
					'MainWindow', 
					'Zertifikat konnte nicht importiert werden.', 
					None
				)
			)
			self.quit()
			return

		# save the files!
		try:
			pubkey = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, pubkey)
			privkey = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, privkey)

			with open(CERTFILE, 'wb') as f:
				f.write(pubkey)

			with open(KEYFILE, 'wb') as f:
				f.write(privkey)
		except Exception as e:
			log.error('Could not write certificate (%s)!' % (e,))
			QtGui.QMessageBox.warning(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate(
					'MainWindow', 
					'Zertifikat konnte nicht gespeichert werden.', 
					None
				)
			)
			self.quit()
		else:
			# success - start the rest!
			self.rpc = FlsServer.getInstance()
			self.showLoginUser()
			self.init()

	def loadCerts(self):
		self.certs = flscertification.FLSCertificateList()
		try:
			for key, item in self.rpc.getCerts().items():
				if key == '_certs':
					self.certs = flscertification.FLSCertificateList.fromPyDict(item)
		except ssl.CertificateError as e:
			log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
			QtGui.QMessageBox.critical(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 
					'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
					None),
				QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
			)
		except socket.error as e:
			log.error('Connection to server lost!')
			QtGui.QMessageBox.critical(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 
					'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
					None),
				QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
			)
		except xmlrpc.client.ProtocolError as e:
			if e.errcode == 403:
				log.warning('Missing rights for loading mails (%s)' % (e,))
				QtGui.QMessageBox.warning(
					self, _translate('MainWindow', 'Fehlende Rechte', None), 
					_translate('MainWindow', 
						'Sie haben nicht ausreichend Rechte!', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
			else:
				log.warning('Unexpected error in protocol: %s' % (e,))
				QtGui.QMessageBox.warning(
					self, _translate('MainWindow', 'Unbekannter Fehler', None), 
					_translate('MainWindow', 
						'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)

	def loadCertData(self):
		self.ui.adminTable.setSortingEnabled(False)
		self.ui.adminTable.setRowCount(0)

		for cert in self.certs:
			rowNr = self.ui.adminTable.rowCount()
			self.ui.adminTable.insertRow(rowNr)
			# number
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (rowNr + 1,))
			self.ui.adminTable.setVerticalHeaderItem(rowNr, item)
			# hash (to identify later)
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (cert.__hash__(),))
			self.ui.adminTable.setItem(rowNr, 0, item)
			# name
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (cert.subject.commonName,))
			self.ui.adminTable.setItem(rowNr, 1, item)
			# email
			item = QtGui.QTableWidgetItem()
			item.setText(cert.subject.emailAddress)
			self.ui.adminTable.setItem(rowNr, 2, item)
			# serial number
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (cert.serialNumber,))
			self.ui.adminTable.setItem(rowNr, 3, item)
			# status
			item = QtGui.QTableWidgetItem()
			icon = QtGui.QIcon()
			if cert.state == flscertification.FLSCertificate.STATE_OK:
				icon.addPixmap(QtGui.QPixmap(":/status/ok.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "OK", None))
			elif cert.state == flscertification.FLSCertificate.STATE_ADDED:
				icon.addPixmap(QtGui.QPixmap(":/status/state_add.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "wird hinzugefügt", None))
			elif cert.state == flscertification.FLSCertificate.STATE_DELETE:
				icon.addPixmap(QtGui.QPixmap(":/status/trash.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "wird gelöscht", None))
			else:
				icon.addPixmap(QtGui.QPixmap(":/status/warning.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "Unbekannt", None))
			item.setIcon(icon)
			self.ui.adminTable.setItem(rowNr, 4, item)
		self.ui.adminTable.setSortingEnabled(True)

	def loadMails(self):
		self.mails = MailAccountList()
		try:
			for item in self.rpc.getMails():
				self.mails.add(MailAccount.fromDict(item))
		except ssl.CertificateError as e:
			log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
			QtGui.QMessageBox.critical(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 
					'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
					None),
				QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
			)
		except socket.error as e:
			log.error('Connection to server lost!')
			QtGui.QMessageBox.critical(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 
					'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
					None),
				QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
			)
		except xmlrpc.client.ProtocolError as e:
			if e.errcode == 403:
				log.warning('Missing rights for loading mails (%s)' % (e,))
				QtGui.QMessageBox.warning(
					self, _translate('MainWindow', 'Fehlende Rechte', None), 
					_translate('MainWindow', 
						'Sie haben nicht ausreichend Rechte!', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
			else:
				log.warning('Unexpected error in protocol: %s' % (e,))
				QtGui.QMessageBox.warning(
					self, _translate('MainWindow', 'Unbekannter Fehler', None), 
					_translate('MainWindow', 
						'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)

	def loadDomains(self):
		self.domains = DomainAccountList()
		try:
			for item in self.rpc.getDomains():
				print(item)
				self.domains.add(Domain.fromDict(item))
		except ssl.CertificateError as e:
			log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
			QtGui.QMessageBox.critical(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 
					'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
					None),
				QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
			)
		except socket.error as e:
			log.error('Connection to server lost!')
			QtGui.QMessageBox.critical(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 
					'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
					None),
				QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
			)
		except xmlrpc.client.ProtocolError as e:
			if e.errcode == 403:
				log.warning('Missing rights for loading mails (%s)' % (e,))
				QtGui.QMessageBox.warning(
					self, _translate('MainWindow', 'Fehlende Rechte', None), 
					_translate('MainWindow', 
						'Sie haben nicht ausreichend Rechte!', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
			else:
				log.warning('Unexpected error in protocol: %s' % (e,))
				QtGui.QMessageBox.warning(
					self, _translate('MainWindow', 'Unbekannter Fehler', None), 
					_translate('MainWindow', 
						'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)

	@pyqtSlot()
	def triggerWhatsThis(self):
		if QtGui.QWhatsThis.inWhatsThisMode():
			QtGui.QWhatsThis.leaveWhatsThisMode()
		else:
			QtGui.QWhatsThis.enterWhatsThisMode()

	def enableProgressBar(self):
		log.debug('Enable Progressbar')
		self.progress = QtGui.QProgressDialog(
			_translate('MainWindow', 'Speichern/Laden der Daten', None), 
			None, 0, 0, self
		)
		self.progress.setWindowModality(QtCore.Qt.ApplicationModal)
		self.progress.setMinimumDuration(1000)
		self.progress.show()

	@pyqtSlot()
	def disableProgressBar(self):
		log.debug('Disable Progressbar')
		if self.progress is not None:
			self.progress.close()
			self.progress = None


	@pyqtSlot()
	def reloadCertTable(self):
		self.enableProgressBar()
		# ask user - because all pending operations will be cancelled!
		pending = False
		for f in self.certs:
			if f.state != flscertification.FLSCertificate.STATE_OK:
				pending = True
				break

		if pending:
			msg = QtGui.QMessageBox.question(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 'Alle Änderungen gehen verloren. Fortfahren?', None),
				QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, QtGui.QMessageBox.No
			)
			if msg == QtGui.QMessageBox.Yes:
				self.loadCerts()
				self.loadCertData()
		else:
			self.loadCerts()
			self.loadCertData()
		self.disableProgressBar()

	@pyqtSlot()
	def addCertificate(self):
		try:
			import OpenSSL
		except:
			return

		fd = QtGui.QFileDialog(self, None)
		fd.setWindowModality(QtCore.Qt.ApplicationModal)
		fd.setOption(QtGui.QFileDialog.ReadOnly, True)
		filters = [_translate('MainWindow', 'Zertifikate (*.pem *.p12)', None)]
		fd.setNameFilters(filters)
		fd.setFileMode(QtGui.QFileDialog.ExistingFiles | QtGui.QFileDialog.AcceptOpen)
		fd.filesSelected.connect(self.certificatesSelected)
		fd.show()

	def getCert(self, pubkey):
		if not isinstance(pubkey, OpenSSL.crypto.X509):
			raise TypeError('Expected X509 object of OpenSSL!')

		cert = flscertification.FLSCertificate()
		cert.state = flscertification.FLSCertificate.STATE_ADDED
		pubsub = pubkey.get_subject()
		subject = flscertification.FLSCertificateSubject()
		subject.commonName = pubsub.commonName
		subject.emailAddress = pubsub.emailAddress
		cert.setSubject(subject)
		del(pubsub)
		del(subject)
		pubiss = pubkey.get_issuer()
		issuer = flscertification.FLSCertificateIssuer()
		issuer.commonName = pubiss.commonName
		issuer.emailAddress = pubiss.emailAddress
		issuer.organizationName = pubiss.organizationName
		issuer.organizationalUnitName = pubiss.organizationalUnitName
		cert.setIssuer(issuer)
		del(pubiss)
		del(issuer)
		#cert.version = pubkey.get_version()
		cert.notBefore = datetime.datetime.strptime(
			pubkey.get_notBefore().decode('utf-8'), '%Y%m%d%H%M%SZ'
		).replace(tzinfo=UTC)
		cert.notAfter = datetime.datetime.strptime(
			pubkey.get_notAfter().decode('utf-8'), '%Y%m%d%H%M%SZ'
		).replace(tzinfo=UTC)
		cert.serialNumber = pubkey.get_serial_number()

		return cert

	@pyqtSlot(list)
	def certificatesSelected(self, files):
		for f in files:
			pubkey = None
			cnt = None
			with open(f, 'rb') as p12file:
				cnt = p12file.read()
			if f.endswith('.p12'):
				passphrase = ''
				loaded = False
				aborted = False
				pk = None
				while not loaded and not aborted:
					try:
						pk = OpenSSL.crypto.load_pkcs12(cnt, passphrase)
					except OpenSSL.crypto.Error as e:
						log.warning('Got error: %s' % (e,))
						passphrase = QtGui.QInputDialog.getText(
							self, 
							_translate('MainWindow', 'Kennwort erforderlich', None),
							_translate('MainWindow', 'Kennwort für %s' % (f,), None),
							QtGui.QLineEdit.Password,
							'',
						)
						(passphrase, ok) = passphrase
						aborted = not ok
					else:
						loaded = True

				if aborted or pk is None:
					log.info('User aborted import of %s!' % (f,))
					continue

				pubkey = pk.get_certificate()
				if pubkey.has_expired():
					QtGui.QMessageBox.information(
						self, _translate('MainWindow', 'Information', None), 
						_translate(
							'MainWindow', 
							'Zertifikat "%s" ist abgelaufen und wird übersprungen.' % (f,), 
							None
						)
					)
					continue
			else:
				# try to load as public key
				pk = None
				aborted = False
				try:
					pk = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cnt)
				except OpenSSL.crypto.Error as err:
					log.info('OK,... this is not a public key: %s (%s)' % (f, err))

					# try to load private
					passphrase = ''
					loaded = False
					while not loaded and not aborted:
						try:
							pk = OpenSSL.crypto.load_privatekey(OpenSSL.crypto.FILETYPE_PEM, cnt, passphrase.encode('utf-8'))
						except OpenSSL.crypto.Error as e:
							log.warning('Got error: %s' % (e,))
							passphrase = QtGui.QInputDialog.getText(
								self, 
								_translate('MainWindow', 'Kennwort erforderlich', None),
								_translate('MainWindow', 'Kennwort für %s' % (f,), None),
								QtGui.QLineEdit.Password,
								''
							)
							(passphrase, ok) = passphrase
							aborted = not ok
						else:
							loaded = True

				if aborted or pk is None:
					log.info('User aborted import of %s!' % (f,))
					continue

				try:
					pubkey = pk.get_certificate()
				except AttributeError:
					pubkey = pk
				else:
					if pubkey.has_expired():
						QtGui.QMessageBox.information(
							self, _translate('MainWindow', 'Information', None), 
							_translate(
								'MainWindow', 
								'Zertifikat "%s" ist abgelaufen und wird übersprungen.' % (f,), 
								None
							)
						)
						continue

			if pubkey is not None:
				cert = self.getCert(pubkey)
				self.certs.add(cert)
				# now display in table?
				rowNr = self.ui.adminTable.rowCount()
				self.ui.adminTable.insertRow(rowNr)
				# number
				item = QtGui.QTableWidgetItem()
				item.setText('%s' % (rowNr + 1,))
				self.ui.adminTable.setVerticalHeaderItem(rowNr, item)
				# hash (to identify later)
				item = QtGui.QTableWidgetItem()
				item.setText('%s' % (cert.__hash__(),))
				self.ui.adminTable.setItem(rowNr, 0, item)
				# name
				item = QtGui.QTableWidgetItem()
				item.setText('%s' % (cert.subject.commonName,))
				self.ui.adminTable.setItem(rowNr, 1, item)
				# email
				item = QtGui.QTableWidgetItem()
				item.setText(cert.subject.emailAddress)
				self.ui.adminTable.setItem(rowNr, 2, item)
				# serial number
				item = QtGui.QTableWidgetItem()
				item.setText('%s' % (cert.serialNumber,))
				self.ui.adminTable.setItem(rowNr, 3, item)		
				# status
				item = QtGui.QTableWidgetItem()
				icon = QtGui.QIcon()
				if cert.state == flscertification.FLSCertificate.STATE_OK:
					icon.addPixmap(QtGui.QPixmap(":/status/ok.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
					item.setText(_translate("MainWindow", "OK", None))
				elif cert.state == flscertification.FLSCertificate.STATE_ADDED:
					icon.addPixmap(QtGui.QPixmap(":/status/state_add.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
					item.setText(_translate("MainWindow", "wird hinzugefügt", None))
				elif cert.state == flscertification.FLSCertificate.STATE_DELETE:
					icon.addPixmap(QtGui.QPixmap(":/status/trash.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
					item.setText(_translate("MainWindow", "wird gelöscht", None))
				else:
					icon.addPixmap(QtGui.QPixmap(":/status/warning.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
					item.setText(_translate("MainWindow", "Unbekannt", None))
				item.setIcon(icon)
				self.ui.adminTable.setItem(rowNr, 4, item)		

	@pyqtSlot()
	def deleteCertificates(self):
		nrSelected = len(self.ui.adminTable.selectionModel().selectedRows())
		log.info('Have to delete %i items!' % (nrSelected,))
		for selectedRow in self.ui.adminTable.selectionModel().selectedRows():
			nr = int(self.ui.adminTable.item(selectedRow.row(), 0).text())
			cert = self.certs.findByHash(nr)
			if cert is not None:
				if cert.state == flscertification.FLSCertificate.STATE_ADDED:
					# we cancel pending action.
					self.ui.adminTable.removeRow(selectedRow.row())		
					self.certs.remove(cert)
				else:
					# do not remove (because we want to see the pending action!)
					cert.state = flscertification.FLSCertificate.STATE_DELETE
					log.info('state set to delete')

		if nrSelected > 0:
			self.loadCertData()

	@pyqtSlot()
	def reloadMailTable(self):
		self.enableProgressBar()
		# ask user - because all pending operations will be cancelled!
		pending = False
		for f in self.mails:
			if f.state != MailAccount.STATE_OK:
				pending = True
				break

		if pending:
			msg = QtGui.QMessageBox.question(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 'Alle Änderungen gehen verloren. Fortfahren?', None),
				QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, QtGui.QMessageBox.No
			)
			if msg == QtGui.QMessageBox.Yes:
				try:
					self.loadMails()
				except xmlrpc.client.Fault as e:
					log.critical('Could not load mails because of %s' % (e,))
					QtGui.QMessageBox.critical(
						self, _translate('MainWindow', 'Daten nicht ladbar', None), 
						_translate('MainWindow', 
							'Die E-Mail-Konten konnten nicht abgerufen werden.', 
							None),
						QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
					)
				else:
					self.loadMailData()
		else:
			try:
				self.loadMails()
			except xmlrpc.client.Fault as e:
				log.critical('Could not load mails because of %s' % (e,))
				QtGui.QMessageBox.critical(
					self, _translate('MainWindow', 'Daten nicht ladbar', None), 
					_translate('MainWindow', 
						'Die E-Mail-Konten konnten nicht abgerufen werden.', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
			else:
				self.loadMailData()
		self.disableProgressBar()

	def loadMailData(self):
		self.ui.mailTable.setSortingEnabled(False)
		self.ui.mailTable.setRowCount(0)

		for row in self.mails:
			rowNr = self.ui.mailTable.rowCount()
			self.ui.mailTable.insertRow(rowNr)
			item = QtGui.QTableWidgetItem()
			try:
				item.setText('%s' % (row.id,))
			except Exception as e:
				log.warning('%s' % (e,))
				return
			item.setTextAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
			self.ui.mailTable.setItem(rowNr, 0, item)
			# mail
			item = QtGui.QTableWidgetItem()
			item.setText(row.getMailAddress())
			self.ui.mailTable.setItem(rowNr, 1, item)
			# type
			item = QtGui.QTableWidgetItem()
			icon = QtGui.QIcon()
			if row.type == MailAccount.TYPE_ACCOUNT:
				icon.addPixmap(QtGui.QPixmap(":/typ/account.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "Konto", None))
			else:
				icon.addPixmap(QtGui.QPixmap(":/typ/forward.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "Weiterleitung", None))
			item.setIcon(icon)
			self.ui.mailTable.setItem(rowNr, 2, item)
			# status
			item = QtGui.QTableWidgetItem()
			icon = QtGui.QIcon()
			if row.state == MailAccount.STATE_OK:
				icon.addPixmap(QtGui.QPixmap(":/status/ok.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "OK", None))
			elif row.state == MailAccount.STATE_CHANGE:
				icon.addPixmap(QtGui.QPixmap(":/status/waiting.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "wird geändert", None))
			elif row.state == MailAccount.STATE_CREATE:
				icon.addPixmap(QtGui.QPixmap(":/status/state_add.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "wird hinzugefügt", None))
			elif row.state == MailAccount.STATE_DELETE:
				icon.addPixmap(QtGui.QPixmap(":/status/trash.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "wird gelöscht", None))
			else:
				icon.addPixmap(QtGui.QPixmap(":/status/warning.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "Unbekannt", None))
			item.setIcon(icon)
			self.ui.mailTable.setItem(rowNr, 3, item)
		self.ui.mailTable.setSortingEnabled(True)

	@pyqtSlot()
	def addMail(self):
		log.info('Clicked "add mail"')
		mf = MailForm(self)
		mf.show()
		mf.exec_()
		if not mf.aborted and mf.account is not None:
			log.info('Mail created')
			self.mails.add(mf.account)
			self.loadMailData()
		else:
			log.info('Mail creation aborted')

	@pyqtSlot()
	def editMail(self):
		log.info('Clicked "edit mail"')
		for selectedRow in self.ui.mailTable.selectionModel().selectedRows():
			nr = self.ui.mailTable.item(selectedRow.row(), 0).text()
			account = self.mails.findById(nr)
			if account is not None:
				mf = MailForm(self, account)
				mf.show()
				mf.exec_()

		self.loadMailData()

	@pyqtSlot()
	def deleteMail(self):
		nrSelected = len(self.ui.mailTable.selectionModel().selectedRows())
		log.info('Have to delete %i items!' % (nrSelected,))

		for selectedRow in self.ui.mailTable.selectionModel().selectedRows():
			nr = self.ui.mailTable.item(selectedRow.row(), 0).text()
			account = self.mails.findById(nr)
			if account is not None:
				print(account.state)
				if account.state == MailAccount.STATE_CREATE:
					# we cancel pending action.
					self.ui.mailTable.removeRow(selectedRow.row())		
					self.mails.remove(account)
				else:
					# do not remove (because we want to see the pending action!)
					account.state = MailAccount.STATE_DELETE
					log.info('state set to delete')

		self.loadMailData()

	@pyqtSlot(int, int)
	def selectedMail(self, row, col):
		nr = self.ui.mailTable.item(row, 0).text()
		account = self.mails.findById(nr)
		if account is not None:
			mf = MailForm(self, account)
			mf.show()
			mf.exec_()

		self.loadMailData()


	def loadDomainData(self):
		self.ui.domainTree.setSortingEnabled(False)
		# delete all entries on start!
		self.ui.domainTree.clear()

		for row in self.domains.iterTlds():
			self.insertDomainData(row)

			# find the parent
		self.ui.domainTree.setSortingEnabled(True)

	def insertDomainData(self, row, parent = None):
		item = QtGui.QTreeWidgetItem()
		try:
			item.setText(0, '%s' % (row.id,))
		except Exception as e:
			log.warning('%s' % (e,))
			return
		#item.setTextAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
		# domain
		item.setText(1, row.name)
		# typ
		item.setText(2, '')
		# ip/value
		item.setText(3, row.ipv4)
		# ipv6
		item.setText(4, row.ipv6)
		# state
		icon = QtGui.QIcon()
		if row.state == Domain.STATE_OK:
			icon.addPixmap(QtGui.QPixmap(":/status/ok.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
			item.setText(5, _translate("MainWindow", "OK", None))
		elif row.state == Domain.STATE_CHANGE:
			icon.addPixmap(QtGui.QPixmap(":/status/waiting.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
			item.setText(5, _translate("MainWindow", "wird geändert", None))
		elif row.state == Domain.STATE_CREATE:
			icon.addPixmap(QtGui.QPixmap(":/status/state_add.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
			item.setText(5, _translate("MainWindow", "wird hinzugefügt", None))
		elif row.state == Domain.STATE_DELETE:
			icon.addPixmap(QtGui.QPixmap(":/status/trash.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
			item.setText(5, _translate("MainWindow", "wird gelöscht", None))
		else:
			icon.addPixmap(QtGui.QPixmap(":/status/warning.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
			item.setText(5, _translate("MainWindow", "Unbekannt", None))
		item.setIcon(5, icon)

		if parent is None:
			self.ui.domainTree.addTopLevelItem(item)
		else:
			parent.addChild(item)

		# has item chils?
		for childs in self.domains.iterByParent(row.id):
			self.insertDomainData(row, item)


	@pyqtSlot()
	def reloadDomainTree(self):
		self.enableProgressBar()
		# ask user - because all pending operations will be cancelled!
		pending = False
		for f in self.domains:
			if f.state != Domain.STATE_OK:
				pending = True
				break

		loadDomainData = True
		if pending:
			msg = QtGui.QMessageBox.question(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 'Alle Änderungen gehen verloren. Fortfahren?', None),
				QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, QtGui.QMessageBox.No
			)
			if msg != QtGui.QMessageBox.Yes:
				loadDomainData = False


		if loadDomainData:
			try:
				self.loadDomains()
			except xmlrpc.client.Fault as e:
				log.critical('Could not load domains because of %s' % (e,))
				QtGui.QMessageBox.critical(
					self, _translate('MainWindow', 'Daten nicht ladbar', None), 
					_translate('MainWindow', 
						'Die Domains konnten nicht abgerufen werden.', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
			else:
				self.loadDomainData()

		self.disableProgressBar()

	@pyqtSlot()
	def about(self):
		QtGui.QMessageBox.about(self, 'FLS Control Panel', 
			'Control Panel zum Verwalten von E-Mail Konten auf einem ' \
			'virtuellen Server der Friedrich-List-Schule-Wiesbaden.')

	@pyqtSlot()
	def aboutQt(self):
		QtGui.QMessageBox.aboutQt(self)

	@pyqtSlot()
	def quitApp(self):
		# are there some pending actions?
		pending = False
		for f in self.mails:
			if f.state != MailAccount.STATE_OK:
				pending = True
				break

		if pending:
			msg = QtGui.QMessageBox.question(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 'Alle Änderungen gehen verloren. Beenden?', None),
				QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, QtGui.QMessageBox.No
			)
			if msg == QtGui.QMessageBox.Yes:
				self.close()

		else:
			self.close()

	@pyqtSlot(str)
	def filterMail(self, filterText):
		log.debug('Filter for %s' % (filterText,))
		row = 0
		while row < self.ui.mailTable.rowCount():
			if len(filterText) <= 0:
				self.ui.mailTable.setRowHidden(row, False)
			else:
				match = False
				col = 0
				while col < self.ui.mailTable.columnCount():
					if filterText in self.ui.mailTable.item(row, col).text():
						match = True
						break
					col += 1
				self.ui.mailTable.setRowHidden(row, not match)
			row += 1

	@pyqtSlot()
	def commitMailData(self):
		self.enableProgressBar()
		data = MailAccountList()
		for f in self.mails:
			if f.state != MailAccount.STATE_OK:
				data.add(f)

		if len(data) > 0:
			try:
				self.rpc.saveMails(data)
			except TypeError as e:
				log.error('Uhhh we tried to send things the server does not understood (%s)' % (e,))
				print(data._items[0])
				Printer(data._items[0])
				log.debug('Tried to send: %s' % (str(data),))
				QtGui.QMessageBox.warning(
						self, _translate('MainWindow', 'Datenfehler', None), 
						_translate('MainWindow', 
							'Bei der Kommunikation mit dem Server ist ein Datenfehler aufgetreten!', 
							None),
						QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
					)
			except ssl.CertificateError as e:
				log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
				QtGui.QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
			except socket.error as e:
				QtGui.QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
			except xmlrpc.client.ProtocolError as e:
				if e.errcode == 403:
					log.warning('Missing rights for loading mails (%s)' % (e,))
					QtGui.QMessageBox.warning(
						self, _translate('MainWindow', 'Fehlende Rechte', None), 
						_translate('MainWindow', 
							'Sie haben nicht ausreichend Rechte!', 
							None),
						QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
					)
				else:
					log.warning('Unexpected error in protocol: %s' % (e,))
					QtGui.QMessageBox.warning(
						self, _translate('MainWindow', 'Unbekannter Fehler', None), 
						_translate('MainWindow', 
							'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
							None),
						QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
					)

			else:
				try:
					self.loadMails()
				except xmlrpc.client.Fault as e:
					log.critical('Could not load mails because of %s' % (e,))
					QtGui.QMessageBox.critical(
						self, _translate('MainWindow', 'Daten nicht ladbar', None), 
						_translate('MainWindow', 
							'Die E-Mail-Konten konnten nicht abgerufen werden.', 
							None),
						QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
					)
				else:
					self.loadMailData()
		self.disableProgressBar()

	@pyqtSlot()
	def commitCertData(self):
		self.enableProgressBar()
		data = flscertification.FLSCertificateList()
		for f in self.certs:
			if f.state != flscertification.FLSCertificate.STATE_OK:
				data.add(f)

		if len(data) > 0:
			try:
				self.rpc.saveCerts(data)
			except ssl.CertificateError as e:
				log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
				QtGui.QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
			except socket.error as e:
				QtGui.QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)
			except xmlrpc.client.ProtocolError as e:
				if e.errcode == 403:
					log.warning('Missing rights for loading mails (%s)' % (e,))
					QtGui.QMessageBox.warning(
						self, _translate('MainWindow', 'Fehlende Rechte', None), 
						_translate('MainWindow', 
							'Sie haben nicht ausreichend Rechte!', 
							None),
						QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
					)
				else:
					log.warning('Unexpected error in protocol: %s' % (e,))
					QtGui.QMessageBox.warning(
						self, _translate('MainWindow', 'Unbekannter Fehler', None), 
						_translate('MainWindow', 
							'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
							None),
						QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
					)
			except TypeError as err:
				for f in data:
					Printer(f)
				raise

			else:
				self.loadCerts()
				self.loadCertData()
		self.disableProgressBar()

	def start(self):
		self.showNormal()

if __name__ == "__main__":
	hdlr = WatchedFileHandler('flscp.log')
	hdlr.setFormatter(formatter)
	log.addHandler(hdlr)
	log.setLevel(logging.DEBUG)

	app = QtGui.QApplication(sys.argv)
	ds = FLScpMainWindow()
	QtCore.QTimer.singleShot(0, ds.init)
	sys.exit(app.exec_())
