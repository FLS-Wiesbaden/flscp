#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from logging.handlers import WatchedFileHandler
from ansistrm import ColorizingStreamHandler
from ui.ui_cp import *
from ui.ui_about import *
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
from modules.domain import DomainList, Domain
from modules.dns import DNSList, Dns
from modules.mail import MailAccountList, MailAccount
try:
	import OpenSSL
except ImportError:
	pass

__author__  = 'Lukas Schreiner'
__copyright__ = 'Copyright (C) 2013 - 2013 Website-Team Friedrich-List-Schule-Wiesbaden'
__version__ = '0.4'

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
#RPCHOST 		= 'cp.lschreiner.de' 
RPCHOST 		= 'cp.fls-wiesbaden.de' 
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

###### START LOADER ######
class DataLoader(QtCore.QThread):
	dataLoaded = pyqtSignal(list)
	certError = pyqtSignal(ssl.CertificateError)
	socketError = pyqtSignal(socket.error)
	protocolError = pyqtSignal(xmlrpc.client.ProtocolError)
	unknownError = pyqtSignal(Exception)

	def __init__(self, rpc, parent = None):
		super().__init__(parent)

		self.rpc = rpc

	def run(self):
		pass

class LogFileListLoader(DataLoader):

	def run(self):
		try:
			data = self.rpc.getListOfLogs()
		except ssl.CertificateError as e:
			self.certError.emit(e)
		except socket.error as e:
			self.socketError.emit(e)
		except xmlrpc.client.ProtocolError as e:
			self.protocolError.emit(e)
		except Exception as e:
			self.unknownError.emit(e)
		else:
			self.dataLoaded.emit(data)

class MailListLoader(DataLoader):

	def run(self):
		try:
			data = self.rpc.getMails()
		except ssl.CertificateError as e:
			self.certError.emit(e)
		except socket.error as e:
			self.socketError.emit(e)
		except xmlrpc.client.ProtocolError as e:
			self.protocolError.emit(e)
		except Exception as e:
			self.unknownError.emit(e)
		else:
			self.dataLoaded.emit(data)

class CertListLoader(DataLoader):
	dataLoaded = pyqtSignal(dict)

	def run(self):
		try:
			data = self.rpc.getCerts()
		except ssl.CertificateError as e:
			self.certError.emit(e)
		except socket.error as e:
			self.socketError.emit(e)
		except xmlrpc.client.ProtocolError as e:
			self.protocolError.emit(e)
		except Exception as e:
			self.unknownError.emit(e)
		else:
			self.dataLoaded.emit(data)

class DomainListLoader(DataLoader):

	def run(self):
		try:
			data = self.rpc.getDomains()
		except ssl.CertificateError as e:
			self.certError.emit(e)
		except socket.error as e:
			self.socketError.emit(e)
		except xmlrpc.client.ProtocolError as e:
			self.protocolError.emit(e)
		except Exception as e:
			self.unknownError.emit(e)
		else:
			self.dataLoaded.emit(data)

class DnsListLoader(DataLoader):
	dataLoaded = pyqtSignal(int, list)

	def __init__(self, rpc, domainId = None, parent = None):
		super().__init__(rpc, parent)
		self.domainId = domainId

	def run(self):
		try:
			data = self.rpc.getDns(self.domainId)
		except ssl.CertificateError as e:
			self.certError.emit(e)
		except socket.error as e:
			self.socketError.emit(e)
		except xmlrpc.client.ProtocolError as e:
			self.protocolError.emit(e)
		except Exception as e:
			self.unknownError.emit(e)
		else:
			self.dataLoaded.emit(self.domainId, data)


###### END LOADER ######

###### START NOTIFIER ######
class CellChangeNotifier(QtCore.QObject):
	# Emitted when a widget changed: <table>, <id (dns, domain,..)>, <widget>
	tableWidgetChanged = pyqtSignal(QtGui.QTableWidget, str, QtGui.QWidget)
	# Emitted when a widget item changed: <table>, <id (dns, domain,..)>, <widgetitem>
	tableItemChanged = pyqtSignal(QtGui.QTableWidget, str, QtGui.QTableWidgetItem)

	def __init__(self, table):
		super().__init__()
		self.__table = table

	def disconnectAll(self):
		self.__table.cellChanged.disconnect(self.cellChanged)
		self.__table.currentCellChanged.disconnect(self.currentCellChanged)

		try:
			self.tableWidgetChanged.disconnect()
		except TypeError as e:
			log.warning('Failed to disconnect signal: %s' % (str(e),))
		try:
			self.tableItemChanged.disconnect()
		except TypeError as e:
			log.warning('Failed to disconnect signal: %s' % (str(e),))

	@pyqtSlot(int, int, int, int)
	def currentCellChanged(self, row, col, prevRow, prevCol):
		if row >= 0 and col >= 0:
			self.cellChanged(row, col)

	@pyqtSlot(int, int)
	def cellChanged(self, row, column):
		if row < 0 or column < 0:
			return

		log.debug('Cell change commited for row, col: %s, %s' % (row, column))
		# get id
		id = self.__table.item(row, 0).text()

		widget = self.__table.item(row, column)
		if widget is None:
			widget = self.__table.cellWidget(row, column)
			self.tableWidgetChanged.emit(self.__table, id, widget)
		else:
			self.tableItemChanged.emit(self.__table, id, widget)

class WidgetTableChangeNotifier(QtCore.QObject):
	# Triggered, when index changed: <table>, <row>, <col>, <id>, <widget>, <value>
	widgetIndexChanged = pyqtSignal(QtGui.QTableWidget, int, int, str, QtGui.QWidget, str)

	def __init__(self, table, row, col, widget):
		super().__init__()
		self.__table = table
		self.__row = row
		self.__col = col
		self.__widget = widget

		self.__widget.currentIndexChanged.connect(self.currentIndexChanged)

	def disconnectAll(self):
		self.__widget.currentIndexChanged.disconnect(self.currentIndexChanged)

		try:
			self.widgetIndexChanged.disconnect()
		except TypeError as e:
			log.warning('Failed to disconnect signal: %s' % (str(e),))

	@pyqtSlot(int)
	def currentIndexChanged(self, index):
		log.debug('Current index changed commited for widget, index: %s, %s' % (str(self.__widget), index))
		# get id
		id = self.__table.item(self.__row, 0).text()
		self.widgetIndexChanged.emit(self.__table, self.__row, self.__col, id, self.__widget, self.__widget.itemText(index))

class DnsStateChangeObserver(QtCore.QObject):

	def __init__(self, table, item, dns):
		super().__init__()
		self.__table = table
		self.__item = item
		self.__dns = dns

	def disconnectAll(self):
		self.__dns.stateChanged.disconnect(self.stateChanged)

	@pyqtSlot(str)
	def stateChanged(self, state):
		icon = QtGui.QIcon()
		if state == Dns.STATE_OK:
			icon.addPixmap(QtGui.QPixmap(":/status/ok.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
			self.__item.setText(_translate("MainWindow", "OK", None))
		elif state == Dns.STATE_CREATE:
			icon.addPixmap(QtGui.QPixmap(":/status/state_add.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
			self.__item.setText(_translate("MainWindow", "wird hinzugefügt", None))
		elif state == Dns.STATE_CHANGE:
			icon.addPixmap(QtGui.QPixmap(":/status/waiting.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
			self.__item.setText(_translate("MainWindow", "wird geändert", None))
		elif state == Dns.STATE_DELETE:
			icon.addPixmap(QtGui.QPixmap(":/status/trash.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
			self.__item.setText(_translate("MainWindow", "wird gelöscht", None))
		else:
			icon.addPixmap(QtGui.QPixmap(":/status/warning.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
			self.__item.setText(_translate("MainWindow", "Unbekannt", None))

		self.__item.setIcon(icon)
		log.info('Changed dns state in table to \'%s\'' % (state,))

###### END NOTIFIER ######

###### START WINDOWS ######
class FlsCpAbout(QtGui.QDialog):
	def __init__(self, parentMain):
		QtGui.QDialog.__init__(self, parent=parentMain)

		self.ui = Ui_About()
		self.ui.setupUi(self)

		self.autostart()

	def autostart(self):
		# wait - what should i do?
		# set version!
		# check version
		version = 'Development'
		if os.path.exists('VERSION'):
			with open('VERSION', 'rb') as f:
				version = f.readline().decode('utf-8').strip()

		self.ui.textVersion.setText(version)
		self.ui.textVersionQt.setText(
				'PyQt-Version: %s / Qt-Version: %s' % (QtCore.PYQT_VERSION_STR, QtCore.QT_VERSION_STR)
		)
		self.ui.textVersionPy.setText(sys.version)

		self.show()

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
		self.ui.progress = QtGui.QProgressBar(self)
		self.ui.progress.setTextVisible(False)
		self.ui.progress.setMinimum(0)
		self.ui.progress.setMaximum(0)
		self.ui.statusbar.addPermanentWidget(self.ui.progress)
		self.ui.progress.hide()
		self.stateProgressBar = False

		self.version = ''

		self.mails = MailAccountList()
		self.domains = DomainList()
		self.dns = DNSList()
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
		self.ui.butHomeLogs.clicked.connect(self.switchToLogs)
		self.ui.butHomeCert.clicked.connect(self.switchToAdmin)

		# domain tab
		#self.ui.butDomainAdd.clicked.connect(self.addDomain)
		#self.ui.butDomainEdit.clicked.connect(self.editDomain)
		self.ui.butDomainDel.clicked.connect(self.deleteDomain)
		self.ui.butDomainDNS.clicked.connect(self.openDNSDomain)
		self.ui.butDomainReload.clicked.connect(self.reloadDomainTree)
		#self.ui.butDomainSave.clicked.connect(self.commitDomainData)
		#self.ui.domainTree.cellDoubleClicked.connect(self.selectedMail)

		self.ui.tabDNS.tabCloseRequested.connect(self.dnsCloseTab)

		# mail tab
		self.ui.butAdd.clicked.connect(self.addMail)
		self.ui.butEdt.clicked.connect(self.editMail)
		self.ui.butDel.clicked.connect(self.deleteMail)
		self.ui.butReload.clicked.connect(self.reloadMailTable)
		self.ui.butSave.clicked.connect(self.commitMailData)
		self.ui.mailTable.cellDoubleClicked.connect(self.selectedMail)
		self.ui.search.textChanged.connect(self.filterMail)
		self.setupMailTable()

		# logs tab
		self.ui.butLogLoad.clicked.connect(self.loadLog)
		self.ui.butLogReload.clicked.connect(self.reloadLogFileList)
		self.ui.butLogTrash.clicked.connect(self.clearLogFile)
		self.ui.logSearch.textChanged.connect(self.searchLog)
		self.ui.butLogSearchBack.clicked.connect(self.searchLogBack)
		self.ui.butLogSearchForw.clicked.connect(self.searchLogForward)

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
		self.setupCertTable()

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
	def switchToLogs(self):
		self.ui.tabWidget.setCurrentIndex(3)
		self.reloadLogFileList()

	@pyqtSlot()
	def reloadLogFileList(self):
		self.enableProgressBar(self.ui.tabLog, _translate('MainWindow', 'Loading log file list...', None))
		self.dataLoader = LogFileListLoader(self.rpc, self)
		self.dataLoader.dataLoaded.connect(self.logFileListLoaded)
		self.dataLoader.certError.connect(self.dataLoadCertError)
		self.dataLoader.socketError.connect(self.dataLoadSocketError)
		self.dataLoader.protocolError.connect(self.dataLoadProtocolError)
		self.dataLoader.unknownError.connect(self.dataLoadError)
		self.dataLoader.start()

	@pyqtSlot(list)
	def logFileListLoaded(self, data):
		self.dataLoader = None
		for f in data:
			self.ui.fldLogFile.addItem(f)

		self.disableProgressBar()

	@pyqtSlot(Exception)
	def dataLoadError(self, e):
		self.disableProgressBar()
		log.warning('Error while loading data: %s!' % (str(e),))
		QtGui.QMessageBox.warning(
			self, _translate('MainWindow', 'Unbekannter Fehler', None), 
			_translate('MainWindow', 
				'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
				None),
			QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
		)

	@pyqtSlot(ssl.CertificateError)
	def dataLoadCertError(self, e):
		self.disableProgressBar()
		log.error('Possible attack! Server Certificate is wrong! (%s)' % (str(e),))
		QtGui.QMessageBox.critical(
			self, _translate('MainWindow', 'Warnung', None), 
			_translate('MainWindow', 
				'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
				None),
			QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
		)
		
	@pyqtSlot(socket.error)
	def dataLoadSocketError(self, e):
		self.disableProgressBar()
		log.error('Connection to server lost!')
		QtGui.QMessageBox.critical(
			self, _translate('MainWindow', 'Warnung', None), 
			_translate('MainWindow', 
				'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
				None),
			QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
		)
		
	@pyqtSlot(xmlrpc.client.ProtocolError)
	def dataLoadProtocolError(self, e):
		self.disableProgressBar()
		if e.errcode == 403:
			log.warning('Missing rights for loading mails (%s)' % (str(e),))
			QtGui.QMessageBox.warning(
				self, _translate('MainWindow', 'Fehlende Rechte', None), 
				_translate('MainWindow', 
					'Sie haben nicht ausreichend Rechte!', 
					None),
				QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
			)
		else:
			log.warning('Unexpected error in protocol: %s' % (str(e),))
			QtGui.QMessageBox.warning(
				self, _translate('MainWindow', 'Unbekannter Fehler', None), 
				_translate('MainWindow', 
					'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
					None),
				QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
			)
		
	@pyqtSlot()
	def loadLog(self):
		logFile = self.ui.fldLogFile.currentText().strip()
		if logFile == '':
			return

		try:
			logTxt = self.rpc.getLogFile(logFile)
			self.ui.logText.setPlainText(logTxt)
			self.ui.logText.setReadOnly(True)
			self.ui.logText.setAcceptRichText(False)
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
	def clearLogFile(self):
		self.ui.logText.setPlainText('')

	@pyqtSlot(str)
	def searchLog(self, filterText):
		options = None
		log.debug('Search for %s' % (filterText,))
		if self.ui.butLogChkSensitive.isChecked():
			options = QtGui.QTextDocument.FindCaseSensitively

		if options is None:
			self.ui.logText.find(filterText)
		else:
			self.ui.logText.find(filterText, options)

	@pyqtSlot()
	def searchLogBack(self):
		options = QtGui.QTextDocument.FindBackward
		if self.ui.butLogChkSensitive.isChecked():
			options = options | QtGui.QTextDocument.FindCaseSensitively
		
		self.ui.logText.find(self.ui.logSearch.text(), options)

	@pyqtSlot()
	def searchLogForward(self):
		options = None
		if self.ui.butLogChkSensitive.isChecked():
			options = QtGui.QTextDocument.FindCaseSensitively

		if options is None:
			self.ui.logText.find(self.ui.logSearch.text())
		else:
			self.ui.logText.find(self.ui.logSearch.text(), options)

	@pyqtSlot()
	def switchToAdmin(self):
		self.ui.tabWidget.setCurrentIndex(4)

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
				self.loadMails(True)
			except xmlrpc.client.Fault as e:
				log.critical('Could not load mails because of %s' % (e,))
				QtGui.QMessageBox.critical(
					self, _translate('MainWindow', 'Daten nicht ladbar', None), 
					_translate('MainWindow', 
						'Die E-Mail-Konten konnten nicht abgerufen werden.', 
						None),
					QtGui.QMessageBox.Ok, QtGui.QMessageBox.Ok
				)

			# load the data!
			self.splash.showMessage('Loading certs...', color=QtGui.QColor(255, 255, 255))
			self.splash.repaint()

			# certs
			try:
				self.loadCerts(True)
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
			self.initLoginCert()

		# disable splash screen!
		self.splash.close()
		self.stateProgressBar = True
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
				'Es konnte kein Zertifikat zum Login gefunden werden.\n \
				Bitte wählen Sie im nachfolgenden Fenster ein PKCS12-Zertifikat aus.', 
				None),
			QtGui.QMessageBox.Ok|QtGui.QMessageBox.Cancel, QtGui.QMessageBox.Ok
		)
		if answer == QtGui.QMessageBox.Cancel:
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
			self.close()
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
			except Exception as e:
				log.warning('Other exception while loading cert! %s' % (str(e),))
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
			self.close()
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
			self.close()
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
			self.close()
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
			self.close()
		else:
			# success - start the rest!
			self.rpc = FlsServer.getInstance()
			self.showLoginUser()
			self.init()

	def loadCerts(self, interactive = False):
		if interactive:
			try:
				data = self.rpc.getCerts()
				self.certListLoaded(data)
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
			finally:
				self.disableProgressBar()
		else:
			self.enableProgressBar(self.ui.tabAdmins, _translate('MainWindow', 'Loading admin list...', None))
			self.dataLoader = CertListLoader(self.rpc, self)
			self.dataLoader.dataLoaded.connect(self.certListLoaded)
			self.dataLoader.certError.connect(self.dataLoadCertError)
			self.dataLoader.socketError.connect(self.dataLoadSocketError)
			self.dataLoader.protocolError.connect(self.dataLoadProtocolError)
			self.dataLoader.unknownError.connect(self.dataLoadError)
			self.dataLoader.start()

	@pyqtSlot(dict)
	def certListLoaded(self, data):
		self.certs = flscertification.FLSCertificateList()

		for key, item in data.items():
			if key == '_certs':
				self.certs = flscertification.FLSCertificateList.fromPyDict(item)

		self.loadCertData()

		self.disableProgressBar()

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

	def loadMails(self, interactive = False):
		if interactive:
			try:
				data = self.rpc.getMails()
				self.mailListLoaded(data)
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
			finally:
				self.disableProgressBar()
		else:
			self.enableProgressBar(self.ui.tabMail, _translate('MainWindow', 'Loading mail list...', None))
			self.dataLoader = MailListLoader(self.rpc, self)
			self.dataLoader.dataLoaded.connect(self.mailListLoaded)
			self.dataLoader.certError.connect(self.dataLoadCertError)
			self.dataLoader.socketError.connect(self.dataLoadSocketError)
			self.dataLoader.protocolError.connect(self.dataLoadProtocolError)
			self.dataLoader.unknownError.connect(self.dataLoadError)
			self.dataLoader.start()

	@pyqtSlot(list)
	def mailListLoaded(self, data):
		self.dataLoader = None
		self.mails = MailAccountList()
		for item in data:
			self.mails.add(MailAccount.fromDict(item))

		self.loadMailData()
		self.disableProgressBar()

	def loadDomains(self, interactive = False):
		self.domains = DomainList()
		try:
			for item in self.rpc.getDomains():
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

	def enableProgressBar(self, tab = None, msg = None):
		if self.stateProgressBar:
			log.debug('Enable Progressbar')
			if msg is not None:
				self.ui.statusbar.showMessage(msg)
			if tab is not None:
				self.lockTab = tab
				self.lockTab.setEnabled(False)
			self.ui.progress.show()

	@pyqtSlot()
	def disableProgressBar(self):
		log.debug('Disable Progressbar')
		if self.ui.progress.isVisible():
			self.ui.statusbar.clearMessage()
			if hasattr(self, 'lockTab') and self.lockTab is not None:
				self.lockTab.setEnabled(True)
				self.lockTab = None
			self.ui.progress.hide()

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
			self.insertDomainData(childs, item)

	@pyqtSlot()
	def deleteDomain(self):
		editDNS = False

		elms = self.ui.tabDNS.currentWidget()
		# first we think, that the selected element contains tree widget:
		activeTable = elms.findChild(QtGui.QTreeWidget)
		if activeTable is None:
			editDNS = True
			activeTable = elms.findChild(QtGui.QTableWidget)
			if activeTable is None:
				return

		if editDNS:
			self.deleteDNSEntries(activeTable=activeTable)
		else:
			nrSelected = len(self.ui.domainTree.selectionModel().selectedRows())
			log.info('Have to delete %i items!' % (nrSelected,))

			for selectedRow in self.ui.domainTree.selectedItems():
				nr = int(selectedRow.text(0))
				domain = self.domains.findById(nr)
				if domain is not None:
					if domain.state == Domain.STATE_CREATE:
						# we cancel pending action.
						self.ui.domainTree.removeItemWidget(selectedRow)
						self.domains.remove(domain)
					else:
						# do not remove (because we want to see the pending action!)
						# check possibility!
						# this means: are there mails with this domain?
						if domain.isDeletable(self.domains, self.mails):
							domain.state = Domain.STATE_DELETE
							log.info('state set to delete')
						else:
							log.error('cannot delete domain %s!' % (domain.name,))
							continue

			self.loadDomainData()

	@pyqtSlot(bool)
	def deleteDNSEntries(self, triggered = False, activeTable = None):
		if activeTable is None:
			activeTable = self.ui.tabDNS.currentWidget().findChild(QtGui.QTableWidget)
			if activeTable is None:
				return

		nrSelected = len(activeTable.selectionModel().selectedRows())
		log.info('Have to delete %i items!' % (nrSelected,))

		for selectedRow in activeTable.selectionModel().selectedRows():
			nr = activeTable.item(selectedRow.row(), 0).text()
			log.info('Have to delete DNS #%s' % (nr,))
			dns = self.dns.findById(nr)
			# do nothing if its already marked to be deleted (at the moment we have no undo stack)
			if dns.state == Dns.STATE_DELETE:
				continue
			elif dns.state != Dns.STATE_CREATE:
				dns.changeState(Dns.STATE_DELETE)
			else:
				activeTable.removeRow(selectedRow.row())
				self.dns.remove(dns)

		#self.loadDNSData(<id>????)
	
	def createDNSWidget(self, domain):
		tabDomainDNS = QtGui.QWidget()
		verticalLayout = QtGui.QVBoxLayout(tabDomainDNS)
		tableDNS = QtGui.QTableWidget(tabDomainDNS)
		tableDNS.setEditTriggers(QtGui.QAbstractItemView.DoubleClicked|QtGui.QAbstractItemView.EditKeyPressed)
		tableDNS.setAlternatingRowColors(True)
		tableDNS.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
		tableDNS.setColumnCount(13)
		tableDNS.setRowCount(0)
		tableDNS.setSortingEnabled(False)
		item = QtGui.QTableWidgetItem()
		tableDNS.setVerticalHeaderItem(0, item)
		item = QtGui.QTableWidgetItem()
		tableDNS.setVerticalHeaderItem(1, item)
		item = QtGui.QTableWidgetItem()
		item.setTextAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(0, item)
		item = QtGui.QTableWidgetItem()
		item.setTextAlignment(QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(1, item)
		item = QtGui.QTableWidgetItem()
		item.setTextAlignment(QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(2, item)
		item = QtGui.QTableWidgetItem()
		item.setTextAlignment(QtCore.Qt.AlignHCenter|QtCore.Qt.AlignVCenter|QtCore.Qt.AlignCenter)
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(3, item)
		item = QtGui.QTableWidgetItem()
		item.setTextAlignment(QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(4, item)
		item = QtGui.QTableWidgetItem()
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(5, item)
		item = QtGui.QTableWidgetItem()
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(6, item)
		item = QtGui.QTableWidgetItem()
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(7, item)
		item = QtGui.QTableWidgetItem()
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(8, item)
		item = QtGui.QTableWidgetItem()
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(9, item)
		item = QtGui.QTableWidgetItem()
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(10, item)
		item = QtGui.QTableWidgetItem()
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(11, item)
		item = QtGui.QTableWidgetItem()
		font = QtGui.QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(12, item)
		tableDNS.horizontalHeaderItem(0).setText(_translate("MainWindow", "#", None))
		tableDNS.horizontalHeaderItem(1).setText(_translate("MainWindow", "Key", None))
		tableDNS.horizontalHeaderItem(2).setText(_translate("MainWindow", "Typ", None))
		tableDNS.horizontalHeaderItem(3).setText(_translate("MainWindow", "Prio", None))
		tableDNS.horizontalHeaderItem(4).setText(_translate("MainWindow", "Wert", None))
		tableDNS.horizontalHeaderItem(5).setText(_translate("MainWindow", "Gewicht", None))
		tableDNS.horizontalHeaderItem(6).setText(_translate("MainWindow", "Port", None))
		tableDNS.horizontalHeaderItem(7).setText(_translate("MainWindow", "Admin", None))
		tableDNS.horizontalHeaderItem(8).setText(_translate("MainWindow", "Refresh", None))
		tableDNS.horizontalHeaderItem(9).setText(_translate("MainWindow", "Retry", None))
		tableDNS.horizontalHeaderItem(10).setText(_translate("MainWindow", "Expire", None))
		tableDNS.horizontalHeaderItem(11).setText(_translate("MainWindow", "TTL", None))
		tableDNS.horizontalHeaderItem(12).setText(_translate("MainWindow", "Status", None))
		tableDNS.verticalHeader().setVisible(False)
		tableDNS.horizontalHeader().setCascadingSectionResizes(False)
		tableDNS.horizontalHeader().setStretchLastSection(False)
		verticalLayout.addWidget(tableDNS)

		# save meta information
		tableDNS.setProperty('domainId', domain.id)

		# add context menu
		# create context menu
		action = QtGui.QAction(
			QtGui.QIcon(QtGui.QPixmap(':actions/delete.png')), 
			_translate("MainWindow", "Löschen", None), tableDNS
		)
		action.triggered.connect(self.deleteDNSEntries)
		tableDNS.setContextMenuPolicy(2)
		tableDNS.addAction(action)
		
		# save it all.
		self.ui.dnsTabs[domain.id] = tabDomainDNS
		self.ui.dnsTable[domain.id] = tableDNS
		self.ui.dnsNotifier[domain.id] = []
		self.ui.tabDNS.addTab(tabDomainDNS, domain.name)
		self.reloadDnsDataByDomain(domain.id, tab=tabDomainDNS)

	@pyqtSlot()
	def reloadDnsData(self, activeTable=None, interactive = False):
		if activeTable is None:
			activeTable = self.ui.tabDNS.currentWidget().findChild(QtGui.QTableWidget)
			if activeTable is None:
				return

		domainId = activeTable.property('domainId')
		self.reloadDnsDataByDomain(domainId, interactive=interactive)

		self.disableProgressBar()

	def reloadDnsDataByDomain(self, domainId, interactive = False, tab = None):
		if tab is None:
			tab = self.ui.tabDNS.currentWidget()

		if domainId == 0 or domainId is None:
			domainId = None
			self.enableProgressBar(
				tab, 
				_translate('MainWindow', 'Loading dns data for all domains...', None)
			)
		else:
			self.enableProgressBar(
				tab, 
				_translate('MainWindow', 'Loading dns data for domain #%s...' % (domainId,), None)
			)
		# are there any changes for the given domain?
		# ask user - because all pending operations will be cancelled!
		pending = False
		if interactive:
			if domainId is not None:
				for f in self.dns.iterByDomain(domainId):
					if f.state != Dns.STATE_OK:
						pending = True
						break
			else:
				for f in self.dns:
					if f.state != Dns.STATE_OK:
						pending = True

		if pending:
			msg = QtGui.QMessageBox.question(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 'Alle Änderungen gehen verloren. Fortfahren?', None),
				QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, QtGui.QMessageBox.No
			)

			if msg == QtGui.QMessageBox.Yes:
				pending = False
	
		if not pending or not interactive:
			# remove all entries for domain id
			self.dns.removeByDomain(domainId)

			self.dataLoader = DnsListLoader(self.rpc, domainId, self)
			self.dataLoader.dataLoaded.connect(self.dnsDataLoaded)
			self.dataLoader.certError.connect(self.dataLoadCertError)
			self.dataLoader.socketError.connect(self.dataLoadSocketError)
			self.dataLoader.protocolError.connect(self.dataLoadProtocolError)
			self.dataLoader.unknownError.connect(self.dataLoadError)
			self.dataLoader.start()

	@pyqtSlot(int, list)
	def dnsDataLoaded(self, domain, data):

		for f in data:
			d = Dns.fromDict(f)
			# check if d already in dns
			if d not in self.dns:
				self.dns.add(d)

		if domain is not None:
			self.loadDnsData(domain)

		self.disableProgressBar()

	def loadDnsData(self, domainId):
		if domainId not in self.ui.dnsTabs or \
			domainId not in self.ui.dnsTable:
			log.info('Got new data for domain #%s, but no table is open for that.' % (domainId,))

		dnsTab = self.ui.dnsTabs[domainId]
		dnsTable = self.ui.dnsTable[domainId]

		if dnsTable is None or dnsTab is None:
			log.warning('Should update table for domain #%s, but objects are not present.' % (domainId,))
			return

		log.info('Reload DNS-table for domain #%s' % (domainId,))

		dnsTable.setSortingEnabled(False)
		dnsTable.setRowCount(0)

		# remove all notifier
		if domainId in self.ui.dnsNotifier:
			log.info(
				'Found %i notifier. Have to remove them (but only if i\'ve found more than zero!\').' % (
					len(self.ui.dnsNotifier[domainId]),
				)
			)
			notifier = []
			for f in self.ui.dnsNotifier[domainId]:
				f.disconnectAll()
				notifier.append(f)
			for f in notifier:
				self.ui.dnsNotifier[domainId].remove(f)
			del(notifier)
		else:
			log.info('Found no notifier for domain.')
		log.info('Found %i notifier. Expected: 0' % (len(self.ui.dnsNotifier[domainId]),))

		typeList = [
			Dns.TYPE_SOA,
			Dns.TYPE_NS,
			Dns.TYPE_MX,
			Dns.TYPE_A,
			Dns.TYPE_AAAA,
			Dns.TYPE_CNAME,
			Dns.TYPE_TXT,
			Dns.TYPE_SPF,
			Dns.TYPE_SRV
		]

		for dnse in self.dns.iterByDomain(domainId):
			rowNr = dnsTable.rowCount()
			dnsTable.insertRow(rowNr)
			# id
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (dnse.id,))
			item.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled)
			item.setData(QtCore.Qt.UserRole, 'id')
			item.setData(QtCore.Qt.UserRole + 5, True) # changes not relevant
			dnsTable.setItem(rowNr, 0, item)
			# key
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (dnse.key,))
			item.setData(QtCore.Qt.UserRole, 'key')
			dnsTable.setItem(rowNr, 1, item)
			# type
			item = QtGui.QComboBox()
			item.setProperty('dnsKeyName', 'type')
			item.addItems(typeList)
			currentType = item.findText(dnse.type)
			item.setCurrentIndex(currentType)
			dnsTable.setCellWidget(rowNr, 2, item)
			wtcn = WidgetTableChangeNotifier(dnsTable, rowNr, 2, item)
			item.currentIndexChanged.connect(wtcn.currentIndexChanged)
			wtcn.widgetIndexChanged.connect(self.dnsWidgetChanged)
			self.ui.dnsNotifier[domainId].append(wtcn)
			# prio
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (dnse.prio,))
			item.setData(QtCore.Qt.UserRole, 'prio')
			dnsTable.setItem(rowNr, 3, item)
			# value
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (dnse.value,))
			item.setData(QtCore.Qt.UserRole, 'value')
			dnsTable.setItem(rowNr, 4, item)
			# weight
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (dnse.weight,))
			item.setData(QtCore.Qt.UserRole, 'weight')
			dnsTable.setItem(rowNr, 5, item)
			# port
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (dnse.port,))
			item.setData(QtCore.Qt.UserRole, 'port')
			dnsTable.setItem(rowNr, 6, item)
			# admin
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (dnse.dnsAdmin,))
			item.setData(QtCore.Qt.UserRole, 'dnsAdmin')
			dnsTable.setItem(rowNr, 7, item)
			# refresh
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (dnse.refreshRate,))
			item.setData(QtCore.Qt.UserRole, 'refreshRate')
			dnsTable.setItem(rowNr, 8, item)
			# retry
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (dnse.retryRate,))
			item.setData(QtCore.Qt.UserRole, 'retryRate')
			dnsTable.setItem(rowNr, 9, item)
			# expire
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (dnse.expireTime,))
			item.setData(QtCore.Qt.UserRole, 'expireTime')
			dnsTable.setItem(rowNr, 10, item)
			# ttl
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % (dnse.ttl,))
			item.setData(QtCore.Qt.UserRole, 'ttl')
			dnsTable.setItem(rowNr, 11, item)
			# status
			item = QtGui.QTableWidgetItem()
			icon = QtGui.QIcon()
			if dnse.state == Dns.STATE_OK:
				icon.addPixmap(QtGui.QPixmap(":/status/ok.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "OK", None))
			elif dnse.state == Dns.STATE_CREATE:
				icon.addPixmap(QtGui.QPixmap(":/status/state_add.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "wird hinzugefügt", None))
			elif dnse.state == Dns.STATE_CHANGE:
				icon.addPixmap(QtGui.QPixmap(":/status/waiting.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "wird geändert", None))
			elif dnse.state == Dns.STATE_DELETE:
				icon.addPixmap(QtGui.QPixmap(":/status/trash.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "wird gelöscht", None))
			else:
				icon.addPixmap(QtGui.QPixmap(":/status/warning.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
				item.setText(_translate("MainWindow", "Unbekannt", None))
			item.setIcon(icon)
			item.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled)
			item.setData(QtCore.Qt.UserRole, 'state')
			item.setData(QtCore.Qt.UserRole + 5, True) # changes not relevant
			dnsTable.setItem(rowNr, 12, item)
			dsco = DnsStateChangeObserver(dnsTable, item, dnse)
			dnse.stateChanged.connect(dsco.stateChanged)
			self.ui.dnsNotifier[domainId].append(dsco)

		dnsTable.setSortingEnabled(True)
		ccn = CellChangeNotifier(dnsTable)
		dnsTable.cellChanged.connect(ccn.cellChanged)
		dnsTable.currentCellChanged.connect(ccn.currentCellChanged)
		ccn.tableItemChanged.connect(self.dnsItemChanged)
		self.ui.dnsNotifier[domainId].append(ccn)

	@pyqtSlot(QtGui.QTableWidget, str, QtGui.QTableWidgetItem)
	def dnsItemChanged(self, table, id, item):
		# find dns by id
		dns = self.dns.findById(id)

		# type?
		dnsProperty = item.data(QtCore.Qt.UserRole)
		if dnsProperty is None:
			log.debug('Got a dns item change for dns ID %s with no key name in dns row' % (id, ))
			return

		# there is a type... but maybe the thing is disabled!
		notifierDisabled = item.data(QtCore.Qt.UserRole + 5)
		if notifierDisabled is True:
			log.debug('Item change not interesting: DNS: %s, Name: %s' % (id, dnsProperty))
			return

		# value
		value = item.text()

		if hasattr(dns, dnsProperty) and getattr(dns, dnsProperty) != value:
			setattr(dns, dnsProperty, value)
			if dns.state == Dns.STATE_OK:
				dns.changeState(Dns.STATE_CHANGE)
			# find row for item
			row = table.row(item)
			log.info('I know the row for update the validating style: %i!' % (row,))
			# validate the new items
			state, msg = dns.validate()
			self.updateDnsValidation(table, row, state, msg)

		log.debug('Item changed: DNS: %s, Name: %s, Text: %s' % (id, dnsProperty, item.text()))

	@pyqtSlot(QtGui.QTableWidget, int, int, str, QtGui.QWidget, str)
	def dnsWidgetChanged(self, table, row, col, id, widget, value):
		# find dns by id.
		dns = self.dns.findById(id)
		
		# now we have the value. But what's the type?
		dnsProperty = widget.property('dnsKeyName')
		if dnsProperty is None:
			log.debug('Got a dns item change for dns ID %s with no key name in widget %s' % (id, str(widget)))
			return

		# there is a type.. but maybe the thing is disabled?
		notifierDisabled = widget.property('notifierDisabled')
		if notifierDisabled is True:
			log.debug('Widget change not interesting: DNS: %s, Name: %s' % (id, dnsProperty))
			return

		if hasattr(dns, dnsProperty) and getattr(dns, dnsProperty) != value:
			setattr(dns, dnsProperty, value)
			if dns.state == Dns.STATE_OK:
				dns.changeState(Dns.STATE_CHANGE)
			# find row for item
			log.info('I know the row for update the validating style: %i!' % (row,))
			# validate the new items
			state, msg = dns.validate()
			self.updateDnsValidation(table, row, state, msg)

		log.debug('Widget changed: DNS: %s, Name: %s, Value: %s' % ( id, dnsProperty, value))

	def updateDnsValidation(self, table, row, state, msg):
		curCol = 0
		maxCol = table.columnCount()

		brush = QtGui.QBrush(QtGui.QColor(255, 207, 207))
		if state:
			brush.setStyle(QtCore.Qt.NoBrush)
			log.info('DNS change is valid!')
		else:
			brush.setStyle(QtCore.Qt.SolidPattern)
			log.info('DNS change is not valid!')

		while curCol < maxCol:
			# get item
			item = table.item(row, curCol)
			if item is None:
				# its a widget
				item = table.cellWidget(row, curCol)
				name = item.property('dnsKeyName')
			else:
				# get user data (name)
				name = item.data(QtCore.Qt.UserRole)
			
			if name in msg:
				item.setToolTip(msg[name])
			else:
				item.setToolTip('')

			try:
				item.setBackground(brush)
			except:
				log.error('Cannot set the background for widgets!!!!')
				pass

			curCol += 1

	@pyqtSlot()
	def openDNSDomain(self):
		if not hasattr(self.ui, 'dnsTabs'):
			self.ui.dnsTabs = {}
		if not hasattr(self.ui, 'dnsTable'):
			self.ui.dnsTable = {}
		if not hasattr(self.ui, 'dnsNotifier'):
			self.ui.dnsNotifier = {}

		if self.ui.tabDNS.currentWidget().findChild(QtGui.QTreeWidget) is None:
			return

		nrSelected = len(self.ui.domainTree.selectionModel().selectedRows())
		log.info('Have to open %i domains!' % (nrSelected,))

		for selectedRow in self.ui.domainTree.selectedItems():
			nr = int(selectedRow.text(0))
			domain = self.domains.findById(nr)
			if domain is not None:
				if domain.state != Domain.STATE_CREATE and \
					domain.state != Domain.STATE_DELETE:
					# is a tab with this already open?
					self.createDNSWidget(domain)

	@pyqtSlot()
	def reloadDomainTree(self):
		# which tab?
		activeWidget = self.ui.tabDNS.currentWidget().findChild(QtGui.QTableWidget)
		if activeWidget is not None and activeWidget.property('domainId') is not None:
			self.reloadDnsData(interactive=True)
			return

		self.enableProgressBar(
			self.ui.tabDNS.currentWidget(), 
			_translate('MainWindow', 'Loading domain data...', None)
		)
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

	@pyqtSlot(int)
	def dnsCloseTab(self, idx):
		if idx == 0:
			log.info('Cannot close the domain overview!')
		else:
			log.info('Close domain tab %i' % (idx,))
			# find the item
			if hasattr(self.ui, 'dnsTabs'):
				tab = self.ui.tabDNS.widget(idx)
				domainId = None
				if tab is not None:
					for k, v in self.ui.dnsTabs.items():
						if v == tab:
							domainId = k
							break

				if domainId is not None:
					log.debug('Removing tab + table for %s' % (domainId,))
					# remove associations.
					del(self.ui.dnsTabs[domainId])
					del(self.ui.dnsTable[domainId])
					if hasattr(self.ui, 'dnsNotifier') and domainId in self.ui.dnsNotifier:
						for item in self.ui.dnsNotifier[domainId]:
							self.ui.dnsNotifier[domainId].remove(item)

						del(self.ui.dnsNotifier[domainId])

			self.ui.tabDNS.removeTab(idx)

	@pyqtSlot()
	def about(self):
		aboutWin = FlsCpAbout(self)

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

	def setupMailTable(self):
		# create context menu
		actions = []
		act = QtGui.QAction(
			QtGui.QIcon(QtGui.QPixmap(':actions/edit.png')), 
			_translate("MainWindow", "Bearbeiten", None), self.ui.mailTable
		)
		act.triggered.connect(self.editMail)
		actions.append(act)
		act = QtGui.QAction(
			QtGui.QIcon(QtGui.QPixmap(':actions/delete.png')), 
			_translate("MainWindow", "Löschen", None), self.ui.mailTable
		)
		act.triggered.connect(self.deleteMail)
		actions.append(act)
		self.ui.mailTable.setContextMenuPolicy(2)
		self.ui.mailTable.addActions(actions)

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

	def setupCertTable(self):
		# create context menu
		actions = []
		act = QtGui.QAction(
			QtGui.QIcon(QtGui.QPixmap(':actions/delete.png')), 
			_translate("MainWindow", "Löschen", None), self.ui.mailTable
		)
		act.triggered.connect(self.deleteCertificates)
		actions.append(act)
		self.ui.adminTable.setContextMenuPolicy(2)
		self.ui.adminTable.addActions(actions)

	def start(self):
		self.showNormal()

if __name__ == "__main__":
	if os.path.exists('flscp.log'):
		try:
			# clear logfile
			f = open('flscp.log', 'wb')
			os.ftruncate(f, 0)
			f.close()
		except:
			pass
	hdlr = WatchedFileHandler('flscp.log')
	hdlr.setFormatter(formatter)
	log.addHandler(hdlr)
	log.setLevel(logging.DEBUG)

	app = QtGui.QApplication(sys.argv)
	ds = FLScpMainWindow()
	QtCore.QTimer.singleShot(0, ds.init)
	sys.exit(app.exec_())
