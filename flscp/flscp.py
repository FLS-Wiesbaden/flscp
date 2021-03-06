#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: fenc=utf-8:ts=8:sw=8:si:sta:noet
from logging.handlers import WatchedFileHandler
from ansistrm import ColorizingStreamHandler
from ui.ui_cp import Ui_MainWindow
from ui.ui_about import Ui_About
from ui.ui_mailform import Ui_MailForm
from ui.ui_maileditor import Ui_MailEditor
from ui.ui_output import Ui_OutputDialog
from ui.ui_domain import Ui_Domain
from ui.ui_hostselector import Ui_HostSelector
from ui.ui_changelog import Ui_ReSTViewer
from translator import CPTranslator
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QRunnable, QThreadPool, QObject, QSettings
from PyQt5.QtGui import QIcon, QPixmap, QColor, QPalette, QBrush, QFont, QTextDocument
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QWidget, QDialog, QListWidgetItem, QMainWindow, QApplication
from PyQt5.QtWidgets import QHeaderView, QProgressBar, QLabel, QAction, QMessageBox, QDialogButtonBox
from PyQt5.QtWidgets import QLineEdit, QInputDialog, QTreeWidget, QFileDialog, QComboBox, QWhatsThis
from PyQt5.QtWidgets import QVBoxLayout, QAbstractItemView, QTreeWidgetItem
from Printer import Printer
import logging, os, sys, copy, xmlrpc.client, http.client, ssl, socket, datetime
import tempfile, zipfile, base64
from flsconfig import FLSConfig, DEFAULT_CLIENT_CONFIGS
from flssplash import CpSplashScreen
from modules import flscertification
from modules.domain import DomainList, Domain
from modules.dns import DNSList, Dns
from modules.mail import MailAccountList, MailAccount, MailValidator
try:
	import OpenSSL
except ImportError:
	pass

__author__  = 'Lukas Schreiner'
__copyright__ = 'Copyright (C) 2013 - 2016 Website-Team Friedrich-List-Schule Wiesbaden'
__version__ = '0.9'
__min_server__ = '0.9'

FORMAT = '%(asctime)-15s %(levelname)s: %(funcName)s %(message)s'
formatter = logging.Formatter(FORMAT, datefmt='%b %d %H:%M:%S')
log = logging.getLogger()
log.setLevel(logging.INFO)
hdlr = ColorizingStreamHandler()
hdlr.setFormatter(formatter)
log.addHandler(hdlr)

workDir = os.path.dirname(os.path.realpath(__file__))

##### CONFIGURE #####
# ssl connection
KEYFILE 		= 'certs/clientKey.pem'
CERTFILE 		= 'certs/clientCert.pem'
CACERT 			= 'certs/cacert.pem'
SETTINGS_ORG 	= 'Friedrich-List-Schule Wiesbaden'
SETTINGS_APP	= 'FLS Control Panel'
### CONFIGURE END ###
cpTranslator = CPTranslator(os.path.join(workDir, 'l18n'))

# search for config
conf = FLSConfig()
fread = conf.read(
		[
			'flscp.ini', os.path.expanduser('~/.flscp.ini'), os.path.expanduser('~/.flscp/client.ini'),
			os.path.expanduser('~/.config/flscp/client.ini'), '/etc/flscp/client.ini', '/usr/local/etc/flscp/client.ini'
		]
	)
if len(fread) <= 0:
	log.info('No configuration file found. Load defaults.')
	conf.read_dict(DEFAULT_CLIENT_CONFIGS)
	# and save it...
	conf.save(os.path.expanduser('~/.config/flscp/client.ini'))
else:
	fread = fread.pop()
	log.debug('Using config files "%s"' % (fread,))

def _translate(context, text, disambig = None, param = None):
	return cpTranslator.pyTranslate(context, text, disambig, param)

###### START LOADER ######
class DataLoaderObject(QObject):
	dataLoaded = pyqtSignal(list)
	dataLoadedDict = pyqtSignal(dict)
	certError = pyqtSignal(ssl.CertificateError)
	socketError = pyqtSignal(socket.error)
	protocolError = pyqtSignal(xmlrpc.client.ProtocolError)
	unknownError = pyqtSignal(Exception)

	def __init__(self, **kwds):
		super().__init__(**kwds)

class DataLoader(QRunnable):

	def __init__(self, rpc, **kwds):
		super().__init__(**kwds)
		self.__signals = DataLoaderObject()

		self.rpc = rpc

	def run(self):
		# here we do some crazy stuff
		log = logging.getLogger()
		if log.level == logging.DEBUG:
			startTime = datetime.datetime.now()

		self.runChild()

		if log.level == logging.DEBUG:
			endTime = datetime.datetime.now()
			log.debug('Needed %s seconds for %s' % ((endTime - startTime).total_seconds(), type(self).__name__))

	def runChild(self):
		pass

	@property
	def dataLoaded(self):
		def fget(self):
			return self.__signals.dataLoaded
		return locals()

	@property
	def dataLoadedDict(self):
		def fget(self):
			return self.__signals.dataLoadedDict
		return locals()

	@property
	def certError(self):
		def fget(self):
			return self.__signals.certError
		return locals()

	@property
	def socketError(self):
		def fget(self):
			return self.__signals.socketError
		return locals()

	@property
	def protocolError(self):
		def fget(self):
			return self.__signals.protocolError
		return locals()

	@property
	def unknownError(self):
		def fget(self):
			return self.__signals.unknownError
		return locals()

class LogFileListLoader(DataLoader):

	def runChild(self):
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

class LogFileLoader(DataLoader):

	def setFile(self, fname):
		self.fname = fname

	def runChild(self):
		if not hasattr(self, 'fname') or self.fname is None:
			return

		try:
			data = self.rpc.getLogFile(self.fname)
		except ssl.CertificateError as e:
			self.certError.emit(e)
		except socket.error as e:
			self.socketError.emit(e)
		except xmlrpc.client.ProtocolError as e:
			self.protocolError.emit(e)
		except Exception as e:
			self.unknownError.emit(e)
		else:
			for i in range(0, len(data), 4000):
				self.dataLoaded.emit([data[i:i + 4000]])
				QtCore.QThread.msleep(50)

class MailListLoader(DataLoader):

	def runChild(self):
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

	def runChild(self):
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
			self.dataLoadedDict.emit(data)

class DomainListLoader(DataLoader):

	def runChild(self):
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

	def __init__(self, rpc, domainId = None, **kwds):
		super().__init__(rpc, **kwds)
		self.domainId = domainId

	def runChild(self):
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
			self.dataLoadedDict.emit({self.domainId: data})

###### END LOADER ######

###### START NOTIFIER ######
class CellChangeNotifier(QtCore.QObject):
	# Emitted when a widget changed: <table>, <id (dns, domain,..)>, <widget>
	tableWidgetChanged = pyqtSignal(QTableWidget, str, QWidget)
	# Emitted when a widget item changed: <table>, <id (dns, domain,..)>, <widgetitem>
	tableItemChanged = pyqtSignal(QTableWidget, str, QTableWidgetItem)

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
	widgetIndexChanged = pyqtSignal(QTableWidget, int, int, str, QWidget, str)

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
		icon = QIcon()
		if state == Dns.STATE_OK:
			icon.addPixmap(QPixmap(":/status/ok.png"), QIcon.Normal, QIcon.Off)
			self.__item.setText(_translate("MainWindow", "OK", None))
		elif state == Dns.STATE_CREATE:
			icon.addPixmap(QPixmap(":/status/state_add.png"), QIcon.Normal, QIcon.Off)
			self.__item.setText(_translate("MainWindow", "wird hinzugefügt", None))
		elif state == Dns.STATE_CHANGE:
			icon.addPixmap(QPixmap(":/status/waiting.png"), QIcon.Normal, QIcon.Off)
			self.__item.setText(_translate("MainWindow", "wird geändert", None))
		elif state == Dns.STATE_DELETE:
			icon.addPixmap(QPixmap(":/status/trash.png"), QIcon.Normal, QIcon.Off)
			self.__item.setText(_translate("MainWindow", "wird gelöscht", None))
		else:
			icon.addPixmap(QPixmap(":/status/warning.png"), QIcon.Normal, QIcon.Off)
			self.__item.setText(_translate("MainWindow", "Unbekannt", None))

		self.__item.setIcon(icon)
		log.info('Changed dns state in table to \'%s\'' % (state,))

###### END NOTIFIER ######

###### START WINDOWS ######
class FlsCpAbout(QDialog):
	def __init__(self, parentMain):
		super().__init__(parent=parentMain)

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

class FlsCpOutput(QDialog):
	def __init__(self, parentMain = None):
		super().__init__(parent=parentMain)

		self.ui = Ui_OutputDialog()
		self.ui.setupUi(self)

	def setText(self, text):
		self.ui.plainTextEdit.setPlainText(text)

	@pyqtSlot(str)
	def showOutput(self, text):
		self.setText(text)
		self.show()

class ReSTViewer(QDialog):
	def __init__(self, parentMain = None):
		super().__init__(parent=parentMain)

		self.ui = Ui_ReSTViewer()
		self.ui.setupUi(self)
		self.styleSheet = os.path.join(workDir, 'templates', 'styles', 'nature.css')
		#self.ui.fldRestText.setStyleSheet(self.styleSheet)

	def setText(self, text):
		self.ui.fldRestText.setHtml(text)

	@pyqtSlot(str)
	def showFile(self, fName):
		import docutils.core
		settings = {
			'input_encoding': 'unicode',
			'output_encoding': 'unicode',
			'stylesheet': self.styleSheet,
			'stylesheet_path': ''
		}
		result = docutils.core.publish_string(open(fName, 'r').read(), writer_name='html', settings_overrides=settings)
		self.setText(result)
		self.show()

class MailEditor(QDialog):
	
	def __init__(self, parent):
		super().__init__(parent=parent)

		self.accepted = False
		self.ui = Ui_MailEditor()
		self.ui.setupUi(self)

		self.ui.buttonBox.accepted.connect(self.setAcceptState)
		self.ui.buttonBox.rejected.connect(self.setRejectState)

		buttonRole = dict((x, n) for x, n in vars(QDialogButtonBox).items() if \
				isinstance(n, QDialogButtonBox.StandardButton))
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
		palette = QPalette()

		if len(self.ui.fldMail.text().strip()) == 0 \
				or not MailValidator(self.ui.fldMail.text()):
			palette.setColor(self.ui.fldMail.backgroundRole(), QColor(255, 110, 110))
			self.okButton.setDisabled(True)
		else:
			palette.setColor(self.ui.fldMail.backgroundRole(), QColor(151, 255, 139))
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

class MailForm(QDialog):
	
	def __init__(self, parent, account = None):
		super().__init__(parent=parent)
		self.rpc = FlsServer.getInstance()

		self.ui = Ui_MailForm()
		self.ui.setupUi(self)
		self._features = []
		self.dl = None
		self.getFeatures()
		self.account = account
		self.orgAccount = copy.copy(account)
		self.aborted = False
		self.actions()
		self.initFields()

	def getFeatures(self):
		log.debug('Get list of features....')
		try:
			self._features = self.rpc.getFeatures()
			log.debug('List result: %s' % (str(self._features),))
		except ssl.CertificateError as e:
			log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
		except socket.error as e:
			log.error('Connection to server lost!')
		except xmlrpc.client.ProtocolError as e:
			if e.errcode == 403:
				log.warning('Missing rights for loading features (%s)' % (e,))
			else:
				log.warning('Unexpected error in protocol: %s' % (e,))

	def initFields(self):
		self.dl = DomainList()
		# load domains
		try:
			for f in self.rpc.getDomains():
				d = Domain.fromDict(f)
				self.dl.add(d)
		except ssl.CertificateError as e:
			log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
		except socket.error as e:
			log.error('Connection to server lost!')
		except xmlrpc.client.ProtocolError as e:
			if e.errcode == 403:
				log.warning('Missing rights for loading mails (%s)' % (e,))
			else:
				log.warning('Unexpected error in protocol: %s' % (e,))

		for domain in self.dl:
			self.ui.fldDomain.addItem(domain.getFullDomain(self.dl), domain.id)
		
		# depending on features, we need to change some visibilities.
		# quota
		if 'quota' in self._features:
			self.ui.fldQuota.setValue(self.account.getQuotaMb())
			self.ui.fldQuota.setVisible(True)
			self.ui.labQuota.setVisible(True)
		else:
			self.ui.fldQuota.setValue(0)
			self.ui.fldQuota.setVisible(False)
			self.ui.labQuota.setVisible(False)

		# encryption available and set?
		if 'encryption' in self._features:
			if self.account is not None and self.account.encryption:
				self.ui.fldEncryption.setChecked(True)
			else:
				self.ui.fldEncryption.setChecked(False)
			self.ui.fldEncryption.setVisible(True)
			self.ui.labEnc.setVisible(True)
		else:
			self.ui.fldEncryption.setChecked(False)
			self.ui.fldEncryption.setVisible(False)
			self.ui.labEnc.setVisible(False)

		filterAvailable = False
		# filter postgrey available and set?
		if 'postgrey' in self._features:
			filterAvailable = True
			if self.account is not None and self.account.filterPostgrey:
				self.ui.fldPostgrey.setChecked(True)
			else:
				self.ui.fldPostgrey.setChecked(False)
			self.ui.fldPostgrey.setVisible(True)
		else:
			self.ui.fldPostgrey.setChecked(False)
			self.ui.fldPostgrey.setVisible(False)

		# filter virus available and set?
		if 'antivirus' in self._features:
			filterAvailable = True
			if self.account is not None and self.account.filterVirus:
				self.ui.fldVirus.setChecked(True)
			else:
				self.ui.fldVirus.setChecked(False)
			self.ui.fldVirus.setVisible(True)
		else:
			self.ui.fldVirus.setChecked(False)
			self.ui.fldVirus.setVisible(False)

		# filter spam available and set?
		if 'antispam' in self._features:
			filterAvailable = True
			if self.account is not None and self.account.filterSpam:
				self.ui.fldSpam.setChecked(True)
			else:
				self.ui.fldSpam.setChecked(False)
			self.ui.fldSpam.setVisible(True)
		else:
			self.ui.fldSpam.setChecked(False)
			self.ui.fldSpam.setVisible(False)

		# Now filter available? Than hide!
		if not filterAvailable:
			self.ui.labFilter.setVisible(False)
		else:
			self.ui.labFilter.setVisible(True)

		# below are only field preparations if we change an account.
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
			item = QListWidgetItem()
			item.setText(f)
			self.ui.fldForward.addItem(item)

		if self.account.type == MailAccount.TYPE_ACCOUNT:
			self.ui.fldTypeAccount.setChecked(True)
			self.ui.fldTypeFwdSmtp.setChecked(False)
			self.ui.fldTypeForward.setChecked(False)
		elif self.account.type == MailAccount.TYPE_FWDSMTP:
			self.ui.fldTypeAccount.setChecked(False)
			self.ui.fldTypeFwdSmtp.setChecked(True)
			self.ui.fldTypeForward.setChecked(False)
		else:
			self.ui.fldTypeAccount.setChecked(False)
			self.ui.fldTypeFwdSmtp.setChecked(False)
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
			palette = QPalette()
			item.setPalette(palette)

		state = True

		if len(self.ui.fldMail.text()) <= 0:
			palette = QPalette()
			palette.setColor(self.ui.fldMail.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldMail.setPalette(palette)
			state = state and False

		if len(self.ui.fldDomain.currentText().strip()) <= 0:
			palette = QPalette()
			palette.setColor(self.ui.fldDomain.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldDomain.setPalette(palette)
			state = state and False

		# check domain:
		if len(self.ui.fldMail.text()) > 0 and len(self.ui.fldDomain.currentText().strip()) > 0 \
			and not MailValidator('%s@%s' % (self.ui.fldMail.text(), self.ui.fldDomain.currentText())):
			palette = QPalette()
			palette.setColor(self.ui.fldMail.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldMail.setPalette(palette)
			palette = QPalette()
			palette.setColor(self.ui.fldDomain.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldDomain.setPalette(palette)
			state = state and False

		if len(self.ui.fldPw.text()) > 0 \
			or len(self.ui.fldPwRepeat.text()) > 0:
			if self.ui.fldPw.text() != self.ui.fldPwRepeat.text():
				palette = QPalette()
				palette.setColor(self.ui.fldPw.backgroundRole(), QColor(255, 110, 110))
				self.ui.fldPw.setPalette(palette)
				palette = QPalette()
				palette.setColor(self.ui.fldPwRepeat.backgroundRole(), QColor(255, 110, 110))
				self.ui.fldPwRepeat.setPalette(palette)
				state = state and False

		if self.ui.fldTypeForward.isChecked() \
				or self.ui.fldTypeFwdSmtp.isChecked():
			if self.ui.fldForward.count() <= 0:
				palette = QPalette()
				palette.setColor(self.ui.fldForward.backgroundRole(), QColor(255, 110, 110))
				self.ui.fldForward.setPalette(palette)
				state = state and False
			elif not self.forwardMailsValid():
				palette = QPalette()
				palette.setColor(self.ui.fldForward.backgroundRole(), QColor(255, 110, 110))
				self.ui.fldForward.setPalette(palette)
				state = state and False

		# fields have to be filled (like mail, domain,...)
		self.ui.fldMail.setText(self.ui.fldMail.text().strip())
		if len(self.ui.fldMail.text()) <= 0:
			palette = QPalette()
			palette.setColor(self.ui.fldMail.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldMail.setPalette(palette)
			state = state and False

		self.ui.fldAltMail.setText(self.ui.fldAltMail.text().strip())
		if len(self.ui.fldAltMail.text()) <= 0 \
			or not MailValidator(self.ui.fldAltMail.text()):
			palette = QPalette()
			palette.setColor(self.ui.fldAltMail.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldAltMail.setPalette(palette)
			state = state and False

		# if mail forward: no pw and no pw gen!
		if self.ui.fldTypeForward.isChecked() \
			and (len(self.ui.fldPw.text()) > 0 or self.ui.fldGenPw.isChecked()):
			palette = QPalette()
			palette.setColor(self.ui.fldGenPw.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldGenPw.setPalette(palette)
			palette = QPalette()
			palette.setColor(self.ui.fldPw.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldPw.setPalette(palette)
			state = state and False		

		# if mail account: pw or pw gen (but only on creation!)
		if (self.ui.fldTypeAccount.isChecked() or self.ui.fldTypeFwdSmtp.isChecked()) \
			and (self.account is None or self.account.state == MailAccount.STATE_CREATE) \
			and len(self.ui.fldPw.text()) <= 0 \
			and not self.ui.fldGenPw.isChecked():
			palette = QPalette()
			palette.setColor(self.ui.fldGenPw.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldGenPw.setPalette(palette)
			palette = QPalette()
			palette.setColor(self.ui.fldPw.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldPw.setPalette(palette)
			state = state and False

		# Enabling encryption can only be done, if the new password is set!
		if self.ui.fldEncryption.isChecked() and len(self.ui.fldPw.text()) <= 0 \
			and not self.ui.fldGenPw.isChecked():
			palette = QPalette()
			palette.setColor(self.ui.fldGenPw.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldGenPw.setPalette(palette)
			palette = QPalette()
			palette.setColor(self.ui.fldPw.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldPw.setPalette(palette)
			palette = QPalette()
			palette.setColor(self.ui.fldEncryption.backgroundRole(), QColor(255, 110, 110))
			self.ui.fldEncryption.setPalette(palette)
			state = state and False

		log.info('Validation result: %s' % ('valid' if state else 'invalid',))
		return state

	def forwardMailsValid(self):
		state = True
		i = 0
		while i < self.ui.fldForward.count():
			item = self.ui.fldForward.item(i)
			if len(item.text().strip()) == 0 or not MailValidator(item.text()):
				item.setBackground(QBrush(QColor(255, 110, 110)))
				state = state and False
			else:
				item.setBackground(QBrush(QColor(151, 255, 139)))
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
		self.account.quota = self.ui.fldQuota.value()*1024*1024
		self.account.encryption = self.ui.fldEncryption.isChecked()
		self.account.filterPostgrey = self.ui.fldPostgrey.isChecked()
		self.account.filterVirus = self.ui.fldVirus.isChecked()
		self.account.filterSpam = self.ui.fldSpam.isChecked()
		self.account.forward = []
		i = 0
		while i < self.ui.fldForward.count():
			self.account.forward.append(self.ui.fldForward.item(i).text())
			i += 1
		if self.ui.fldTypeAccount.isChecked():
			self.account.type = MailAccount.TYPE_ACCOUNT
		elif self.ui.fldTypeFwdSmtp.isChecked():
			self.account.type = MailAccount.TYPE_FWDSMTP
		elif self.ui.fldTypeForward.isChecked():
			self.account.type = MailAccount.TYPE_FORWARD
		self.account.state = MailAccount.STATE_CREATE

		# If it is a forwarding account and its our domain: alias!
		self.account.alias = False
		if self.account.type == MailAccount.TYPE_FORWARD and self.checkAlias():
			self.account.alias = True

	def saveMail(self):
		self.account.mail = self.ui.fldMail.text()
		self.account.domain = self.ui.fldDomain.currentText()
		self.account.altMail = self.ui.fldAltMail.text()
		self.account.pw = self.ui.fldPw.text()
		self.account.genPw = self.ui.fldGenPw.isChecked()
		self.account.quota = self.ui.fldQuota.value()*1024*1024
		self.account.encryption = self.ui.fldEncryption.isChecked()
		self.account.filterPostgrey = self.ui.fldPostgrey.isChecked()
		self.account.filterVirus = self.ui.fldVirus.isChecked()
		self.account.filterSpam = self.ui.fldSpam.isChecked()
		self.account.forward = []
		i = 0
		while i < self.ui.fldForward.count():
			self.account.forward.append(self.ui.fldForward.item(i).text())
			i += 1
		if self.ui.fldTypeAccount.isChecked():
			self.account.type = MailAccount.TYPE_ACCOUNT
		elif self.ui.fldTypeFwdSmtp.isChecked():
			self.account.type = MailAccount.TYPE_FWDSMTP
		elif self.ui.fldTypeForward.isChecked():
			self.account.type = MailAccount.TYPE_FORWARD

		# If it is a forwarding account and its our domain: alias!
		if self.account.type == MailAccount.TYPE_FORWARD and self.checkAlias():
			self.account.alias = True
		else:
			self.account.alias = False

		if self.account != self.orgAccount:
			log.info('Account was changed!')
			# if it was created and not commited, we have to let the state "create".
			if self.account.state != MailAccount.STATE_CREATE:
				self.account.state = MailAccount.STATE_CHANGE
		else:
			log.info('Account is unchanged!')

	def checkAlias(self):
		# alternative address required!
		if len(self.account.altMail) <= 0:
			return False

		# get domain part of mail.
		domainPart = None
		try:
			domainPart = self.account.altMail[self.account.altMail.index('@') + 1:]
		except ValueError:
			return False

		# is it part of our domain?
		for domain in self.dl:
			if domainPart == domain.getFullDomain(self.dl):
				return True

		return False

	@pyqtSlot(QListWidgetItem)
	def mailChanged(self, item):
		log.info('Cell changed:')
		# check state
		if len(item.text().strip()) == 0 or not MailValidator(item.text()):
			item.setBackground(QBrush(QColor(255, 110, 110)))
		else:
			item.setBackground(QBrush(QColor(151, 255, 139)))

	@pyqtSlot()
	def addMail(self):
		item = QListWidgetItem()
		item.setFlags(
			QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsEditable|QtCore.Qt.ItemIsDragEnabled|
			QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled
		)
		self.ui.fldForward.addItem(item)

	@pyqtSlot()
	def deleteMail(self):
		for selectedItem in self.ui.fldForward.selectedItems():
			self.ui.fldForward.takeItem(self.ui.fldForward.row(selectedItem))

class DomainEditor(QDialog):
	
	def __init__(self, domainList, domain = None, parentDomain = None, parent = None):
		super().__init__(parent=parent)

		self.rpc = FlsServer.getInstance()
		self.domain = domain
		self.domainList = domainList
		self.parentDomain = parentDomain
		self.accepted = False
		self.ui = Ui_Domain()
		self.ui.setupUi(self)

		self.ui.buttonBox.accepted.connect(self.setAcceptState)
		self.ui.buttonBox.rejected.connect(self.setRejectState)

		if self.parentDomain is not None:
			self.ui.txtParent.setText(self.parentDomain.getFullDomain(domainList))
		elif self.domain is not None:
			if self.domain.parent is not None:
				self.parentDomain = self.domainList.findById(self.domain.parent)
				self.ui.txtParent.setText(self.parentDomain.getFullDomain(domainList))

		if self.domain is not None:
			self.ui.txtDomain.setText(self.domain.name)
			self.ui.txtIPv4.setText(self.domain.ipv4)
			self.ui.txtIPv6.setText(self.domain.ipv6)
			self.ui.txtPath.setText(self.domain.srvpath)
			self.ui.txtDomain.setReadOnly(True)

		self.ui.txtIPv4.textChanged.connect(self.validIPv4)

		self.initFields()

	def initFields(self):
		# get the list of users and the list of groups.
		userList = []
		try:
			userList = self.rpc.getSystemUsers()
		except ssl.CertificateError as e:
			log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
		except socket.error as e:
			log.error('Connection to server lost!')
		except xmlrpc.client.ProtocolError as e:
			if e.errcode == 403:
				log.warning('Missing rights for loading mails (%s)' % (e,))
			else:
				log.warning('Unexpected error in protocol: %s' % (e,))

		groupList = []
		try:
			groupList = self.rpc.getSystemGroups()
		except ssl.CertificateError as e:
			log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
		except socket.error as e:
			log.error('Connection to server lost!')
		except xmlrpc.client.ProtocolError as e:
			if e.errcode == 403:
				log.warning('Missing rights for loading mails (%s)' % (e,))
			else:
				log.warning('Unexpected error in protocol: %s' % (e,))

		# now add them all to the fields
		for user in userList:
			self.ui.fldUser.addItem(user['name'], user['uid'])

		for group in groupList:
			self.ui.fldGroup.addItem(group['name'], group['gid'])

		# if we edit a domain, we have to pre-select the correct selected item.
		# but how? :)
		if self.domain is not None:
			# first set the user
			if len(str(self.domain.uid)) > 0:
				uid = self.ui.fldUser.findData(self.domain.uid)
				if uid > -1:
					self.ui.fldUser.setCurrentIndex(uid)
			if len(str(self.domain.gid)) > 0:
				gid = self.ui.fldGroup.findData(self.domain.gid)
				if gid > -1:
					self.ui.fldGroup.setCurrentIndex(gid)

	@pyqtSlot()
	def validIPv4(self):
		log.debug('Check if given IPv4-address is valid')
		palette = QPalette()
		error = False

		if len(self.ui.txtIPv4.text().strip()) <= 0:
			self.ui.txtIPv4.setPalette(None)
		else:
			try:
				part1, part2, part3, part4 = self.ui.txtIPv4.text().strip().split('.')
			except:
				error = True
			else:
				try:
					part1 = int(part1)
					part2 = int(part2)
					part3 = int(part3)
					part4 = int(part4)
				except:
					error = True
				else:
					# all are valid integers. 
					if part1 <= 0 or part4 <= 0:
						error = True
					elif part1 > 255 or part2 > 255 or part3 > 255 or part4 >= 255:
						error = True

		if error:
			palette.setColor(self.ui.txtIPv4.backgroundRole(), QColor(255, 110, 110))
		else:
			palette.setColor(self.ui.txtIPv4.backgroundRole(), QColor(151, 255, 139))

		self.ui.txtIPv4.setPalette(palette)

	@pyqtSlot()
	def setAcceptState(self):
		self.accepted = True
		# full name:
		name = self.ui.txtDomain.text().strip()
		if self.parentDomain is not None:
			name = '%s.%s' % (name, self.parentDomain.getFullDomain(self.domainList))


		# all valid?
		if self.ui.fldUser.currentIndex() < 0:
			QMessageBox.warning(
				self, _translate('MainWindow', 'Domain speichern/erstellen', None), 
				_translate('MainWindow', 
					'Bitte legen Sie noch einen Benutzer fest.', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
			return False

		if self.ui.fldGroup.currentIndex() < 0:
			QMessageBox.warning(
				self, _translate('MainWindow', 'Domain speichern/erstellen', None), 
				_translate('MainWindow', 
					'Bitte legen Sie noch eine Gruppe fest.', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
			return False

		if self.domain is None and self.domainList.existDomain(name):
			QMessageBox.warning(
				self, _translate('MainWindow', 'Domain anlegen', None), 
				_translate('MainWindow', 
					'Die anzulegende Domain existiert bereits!', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
		elif self.domain is not None:
			if (self.domain.ipv4 != self.getIPv4() \
				or self.domain.ipv6 != self.getIPv6() \
				or self.domain.uid != self.getUserId() \
				or self.domain.gid != self.getGroupId() \
				or self.domain.srvpath != self.getServicePath()) \
				and self.domain.state == Domain.STATE_OK:
				self.domain.state = Domain.STATE_CHANGE

			self.domain.ipv4 = self.getIPv4().strip()
			self.domain.ipv6 = self.getIPv6().strip()
			self.domain.uid = self.getUserId()
			self.domain.gid = self.getGroupId()
			self.domain.srvpath = self.getServicePath()
		else:
			nD = Domain()
			nD.generateId()
			if self.parentDomain is not None:
				nD.parent = self.parentDomain.id
			nD.name = self.getDomain()
			nD.ipv4 = self.getIPv4().strip()
			nD.ipv6 = self.getIPv6().strip()
			nD.uid = self.getUserId()
			nD.gid = self.getGroupId()
			nD.srvpath = self.getServicePath()
			nD.state = Domain.STATE_CREATE
			self.domain = nD
			self.accept()

	@pyqtSlot()
	def setRejectState(self):
		self.accepted = False
		self.reject()

	def getDomain(self):
		return self.ui.txtDomain.text()

	def getIPv4(self):
		return self.ui.txtIPv4.text()

	def getIPv6(self):
		return self.ui.txtIPv6.text()

	def getServicePath(self):
		return self.ui.txtPath.text()

	def getUserId(self):
		if self.ui.fldUser.currentIndex() < 0:
			return None

		uid = self.ui.fldUser.itemData(self.ui.fldUser.currentIndex())
		if uid == QtCore.QVariant.Invalid:
			return None
		else:
			log.debug('Selected the user id ' + str(uid))
			return uid

	def getGroupId(self):
		if self.ui.fldGroup.currentIndex() < 0:
			return None

		gid = self.ui.fldGroup.itemData(self.ui.fldGroup.currentIndex())
		if gid == QtCore.QVariant.Invalid:
			return None
		else:
			log.debug('Selected the group id ' + str(gid))
			return gid

class MailEditor(QDialog):
	
	def __init__(self, parent):
		super().__init__(parent=parent)

		self.accepted = False
		self.ui = Ui_MailEditor()
		self.ui.setupUi(self)

		self.ui.buttonBox.accepted.connect(self.setAcceptState)
		self.ui.buttonBox.rejected.connect(self.setRejectState)

		buttonRole = dict((x, n) for x, n in vars(QDialogButtonBox).items() if \
				isinstance(n, QDialogButtonBox.StandardButton))
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
		palette = QPalette()

		if len(self.ui.fldMail.text().strip()) == 0 \
				or not MailValidator(self.ui.fldMail.text()):
			palette.setColor(self.ui.fldMail.backgroundRole(), QColor(255, 110, 110))
			self.okButton.setDisabled(True)
		else:
			palette.setColor(self.ui.fldMail.backgroundRole(), QColor(151, 255, 139))
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

class HostSelectionForm(QDialog):
	
	def __init__(self, parent):
		super().__init__(parent=parent)

		self.ui = Ui_HostSelector()
		self.ui.setupUi(self)
		self.selectedHost = ''
		self.aborted = False
		self.actions()
		self.initFields()

	def initFields(self):
		# load host list.
		self.ui.hostList.clear()
		for f in conf.items('hosts'):
			# create QListWidgetItem
			f = f[1]
			item = QListWidgetItem(conf.get(f, 'name'))
			item.setData(QtCore.Qt.UserRole, f)
			self.ui.hostList.addItem(item)

	def actions(self):
		self.ui.hostList.itemDoubleClicked.connect(self.accept)

	def validate(self):
		items = self.ui.hostList.selectedItems()
		if len(items) <= 0 or len(items) > 1:
			QMessageBox.warning(
				self, _translate('MainWindow', 'Server auswählen', None), 
				_translate('MainWindow', 
					'Sie müssen einen Server auswählen!', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
			return False

		# get user role
		self.selectedHost = items[0].data(QtCore.Qt.UserRole)
		return True

	@pyqtSlot()
	def accept(self):
		self.aborted = False
		if self.validate():
			super().accept()
		else:
			return False

	@pyqtSlot()
	def reject(self):
		self.aborted = True
		super().reject()

###### END WINDOWS ######
class FLSSafeTransport(xmlrpc.client.Transport):
	"""Handles an HTTPS transaction to an XML-RPC server."""

	def __init__(self, use_datetime=False, use_builtin_types=False):
		super().__init__(use_datetime, use_builtin_types)

		self._extra_headers.append(('Connection', 'keep-alive'))		

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
		super().__init__(
			'https://%s:%i/%s' % (
				conf.get(conf.get('options', 'currenthost'), 'host'), 
				conf.getint(conf.get('options', 'currenthost'), 'port'), 
				conf.get(conf.get('options', 'currenthost'), 'rpcpath')
			), 
			FLSSafeTransport(), allow_none=True
		)
		FlsServer.__instance = self

	@staticmethod
	def getInstance():
		return FlsServer.__instance if FlsServer.__instance is not None else FlsServer()

class FLScpMainWindow(QMainWindow):
	execInit = pyqtSignal()
	sigCancelStart = pyqtSignal()
	killApp = pyqtSignal()
	versionChanged = pyqtSignal()

	def __init__(self, app):
		QMainWindow.__init__(self)

		self.app = app
		self.ui = Ui_MainWindow()
		self.ui.setupUi(self)
		self.ui.mailTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
		self.ui.adminTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
		self.ui.adminTable.hideColumn(0)
		self.ui.progress = QProgressBar(self)
		self.ui.progress.setTextVisible(False)
		self.ui.progress.setMinimum(0)
		self.ui.progress.setMaximum(0)
		self.ui.statusbar.addPermanentWidget(self.ui.progress)
		self.ui.progress.hide()
		self.stateProgressBar = False
		self.loginNeeded = True
		self.fd = None

		self.version = ''

		self.mails = MailAccountList()
		self.domains = DomainList()
		self.dns = DNSList()
		self.certs = flscertification.FLSCertificateList()
		self.splash = CpSplashScreen(self, QPixmap(":/logo/splash.png"), 10)

		# connect to xml-rpc
		self.rpc = None
		self.actions()

		# start
		QtCore.QTimer.singleShot(0, self.init)

	def actions(self):
		# global
		self.sigCancelStart.connect(self.abortStartup)
		self.killApp.connect(self.app.quit)
		self.app.aboutToQuit.connect(self.preQuitSlot)
		self.versionChanged.connect(self.changelog)

		# menu
		self.ui.actionExit.triggered.connect(self.quitApp)
		self.ui.actionWhatsThis.triggered.connect(self.triggerWhatsThis)
		self.ui.actionChangelog.triggered.connect(self.changelog)
		self.ui.actionAbout.triggered.connect(self.about)
		self.ui.actionAboutQt.triggered.connect(self.aboutQt)

		# home
		self.ui.butHomeDomain.clicked.connect(self.switchToDomain)
		self.ui.butHomeMail.clicked.connect(self.switchToMail)
		self.ui.butHomeLogs.clicked.connect(self.switchToLogs)
		self.ui.butHomeCert.clicked.connect(self.switchToAdmin)

		# domain tab
		self.ui.butDomainAdd.clicked.connect(self.addDomain)
		self.ui.butDomainEdit.clicked.connect(self.editDomain)
		self.ui.butDomainDel.clicked.connect(self.deleteDomain)
		self.ui.butDomainFile.clicked.connect(self.generateBindFile)
		self.ui.butDomainDNS.clicked.connect(self.openDNSDomain)
		self.ui.butDomainReload.clicked.connect(self.reloadDomainTree)
		self.ui.butDomainSave.clicked.connect(self.commitDomainData)
		#self.ui.domainTree.cellDoubleClicked.connect(self.selectedMail)

		self.ui.tabDNS.tabCloseRequested.connect(self.dnsCloseTab)

		# mail tab
		self.ui.butAdd.clicked.connect(self.addMail)
		self.ui.butEdt.clicked.connect(self.editMail)
		self.ui.butDel.clicked.connect(self.deleteMail)
		self.ui.butState.clicked.connect(self.toggleStatusMail)
		self.ui.butQuotaCalc.clicked.connect(self.calculateMailQuota)
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
		pubkey = None
		aborted = False
		pk = None
		content = ''
		try:
			with open(CERTFILE, 'r') as f:
				content = f.read()
		except:
			return False

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
					passphrase = QInputDialog.getText(
						self, 
						_translate('MainWindow', 'Kennwort erforderlich', None),
						_translate('MainWindow', 'Kennwort für %s' % (CERTFILE,), None),
						QLineEdit.Password,
						''
					)
					(passphrase, ok) = passphrase
					aborted = not ok
				else:
					loaded = True

		if aborted or pk is None:
			log.info('Login certificate not loadable (%s)!' % (CERTFILE,))
			return False

		try:
			pubkey = pk.get_certificate()
		except AttributeError:
			pubkey = pk
		else:
			if pubkey.has_expired():
				QMessageBox.information(
					self, _translate('MainWindow', 'Information', None), 
					_translate(
						'MainWindow', 
						'Zertifikat "%s" ist abgelaufen und wird übersprungen.' % (f,), 
						None
					)
				)

		if pubkey is not None:
			pubsub = pubkey.get_subject()
			self.ui.labUser = QLabel(self)
			self.ui.labUser.setObjectName("labUser")
			self.ui.labUser.setText(
				_translate("MainWindow", "Logged in as %s <%s>" % (pubsub.commonName, pubsub.emailAddress), None)
			)
			self.ui.statusbar.addWidget(self.ui.labUser)

	def readSettings(self):
		log.info('Reading all settings.')
		settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
		self.restoreGeometry(settings.value('geometry'))
		self.restoreState(settings.value('windowState'))

	def closeEvent(self, event):
		if self.isVisible():
			settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
			settings.setValue('geometry', self.saveGeometry())
			settings.setValue('windowState', self.saveState())
		super().closeEvent(event)

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
		dataLoader = LogFileListLoader(self.rpc)
		dataLoader.dataLoaded.connect(self.logFileListLoaded)
		dataLoader.certError.connect(self.dataLoadCertError)
		dataLoader.socketError.connect(self.dataLoadSocketError)
		dataLoader.protocolError.connect(self.dataLoadProtocolError)
		dataLoader.unknownError.connect(self.dataLoadError)
		QThreadPool.globalInstance().start(dataLoader)

	@pyqtSlot(list)
	def logFileListLoaded(self, data):
		for f in data:
			self.ui.fldLogFile.addItem(f)

		self.disableProgressBar()

	@pyqtSlot(Exception)
	def dataLoadError(self, e):
		self.disableProgressBar()
		log.warning('Error while loading data: %s!' % (str(e),))
		QMessageBox.warning(
			self, _translate('MainWindow', 'Unbekannter Fehler', None), 
			_translate('MainWindow', 
				'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
				None),
			QMessageBox.Ok, QMessageBox.Ok
		)

	@pyqtSlot(ssl.CertificateError)
	def dataLoadCertError(self, e):
		self.disableProgressBar()
		log.error('Possible attack! Server Certificate is wrong! (%s)' % (str(e),))
		QMessageBox.critical(
			self, _translate('MainWindow', 'Warnung', None), 
			_translate('MainWindow', 
				'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
				None),
			QMessageBox.Ok, QMessageBox.Ok
		)
		
	@pyqtSlot(socket.error)
	def dataLoadSocketError(self, e):
		self.disableProgressBar()
		log.error('Connection to server lost!')
		QMessageBox.critical(
			self, _translate('MainWindow', 'Warnung', None), 
			_translate('MainWindow', 
				'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
				None),
			QMessageBox.Ok, QMessageBox.Ok
		)
		
	@pyqtSlot(xmlrpc.client.ProtocolError)
	def dataLoadProtocolError(self, e):
		self.disableProgressBar()
		if e.errcode == 403:
			log.warning('Missing rights for loading mails (%s)' % (str(e),))
			QMessageBox.warning(
				self, _translate('MainWindow', 'Fehlende Rechte', None), 
				_translate('MainWindow', 
					'Sie haben nicht ausreichend Rechte!', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
		else:
			log.warning('Unexpected error in protocol: %s' % (str(e),))
			QMessageBox.warning(
				self, _translate('MainWindow', 'Unbekannter Fehler', None), 
				_translate('MainWindow', 
					'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
		
	@pyqtSlot()
	def loadLog(self):
		logFile = self.ui.fldLogFile.currentText().strip()
		if logFile == '':
			return

		self.ui.logText.setPlainText('')

		self.enableProgressBar(self.ui.tabLog, _translate('MainWindow', 'Loading log file...', None))
		dataLoader = LogFileLoader(self.rpc)
		dataLoader.setFile(logFile)
		dataLoader.dataLoaded.connect(self.logFileLoaded)
		dataLoader.certError.connect(self.dataLoadCertError)
		dataLoader.socketError.connect(self.dataLoadSocketError)
		dataLoader.protocolError.connect(self.dataLoadProtocolError)
		dataLoader.unknownError.connect(self.dataLoadError)
		QThreadPool.globalInstance().start(dataLoader)

	@pyqtSlot(list)
	def logFileLoaded(self, data):
		self.disableProgressBar()
		self.ui.logText.insertPlainText(data[0])
		#self.ui.logText.setPlainText(self.ui.logText.getPlainText() + data[0])
		self.ui.logText.setReadOnly(True)
		self.ui.logText.setAcceptRichText(False)

	@pyqtSlot()
	def clearLogFile(self):
		self.ui.logText.setPlainText('')

	@pyqtSlot(str)
	def searchLog(self, filterText):
		options = None
		log.debug('Search for %s' % (filterText,))
		if self.ui.butLogChkSensitive.isChecked():
			options = QTextDocument.FindCaseSensitively

		if options is None:
			self.ui.logText.find(filterText)
		else:
			self.ui.logText.find(filterText, options)

	@pyqtSlot()
	def searchLogBack(self):
		options = QTextDocument.FindBackward
		if self.ui.butLogChkSensitive.isChecked():
			options = options | QTextDocument.FindCaseSensitively
		
		self.ui.logText.find(self.ui.logSearch.text(), options)

	@pyqtSlot()
	def searchLogForward(self):
		options = None
		if self.ui.butLogChkSensitive.isChecked():
			options = QTextDocument.FindCaseSensitively

		if options is None:
			self.ui.logText.find(self.ui.logSearch.text())
		else:
			self.ui.logText.find(self.ui.logSearch.text(), options)

	@pyqtSlot()
	def switchToAdmin(self):
		self.ui.tabWidget.setCurrentIndex(4)

	@pyqtSlot()
	def init(self):
		self.splash.show()
		self.splash.showMessage(_translate('SplashScreen', 'Lade Anwendung...'), 1, color=QColor(255, 255, 255))
		self.app.processEvents()

		self.update()
		self.splash.showMessage(_translate('SplashScreen', 'Lade Anwendung...'), 1, color=QColor(255, 255, 255))
		self.app.processEvents()

		# do we need to select the host?
		if conf.getboolean('options', 'hostselection'):
			self.splash.showMessage(_translate('SplashScreen', 'Auswahl Server...'), 1, color=QColor(255, 255, 255))
			self.app.processEvents()
			if not self.selectHost():
				log.warning('Host selection aborted. Close application.')
				self.sigCancelStart.emit()
				return
		else:
			# select the default host.
			conf.set('options', 'currenthost', conf.get('options', 'defaulthost'))

		# now initiate the RPC server
		self.rpc = FlsServer.getInstance()
		if self.showLoginUser() is False:
			if not self.initLoginCert():
				self.sigCancelStart.emit()
				return
			else:
				if self.showLoginUser() is False:
					self.sigCancelStart.emit()
					return	

		self.splash.showMessage(_translate('SplashScreen', 'Versuche mit dem Server zu verbinden...'), 2, color=QColor(255, 255, 255))
		self.app.processEvents()
		self.loginNeeded = True
		
		if self.rpc is not None:
			# connection possible ?
			timeout = self.rpc.__transport.timeout
			self.rpc.__transport.timeout = 1
			try:
				p = self.rpc.ping()
			except ssl.SSLError as e:
				log.warning('Connection not possible: %s' % (e,))
				QMessageBox.critical(
					self, _translate('MainWindow', 'Verbindung nicht möglich', None), 
					_translate('MainWindow', 
						'Möglicher Angriffsversuch: die SSL-gesicherte Verbindung ist aus Sicherheitsgründen abgebrochen worden.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
				self.sigCancelStart.emit()
				return
			except socket.error as e:
				log.warning('Connection not possible: %s' % (e,))
				QMessageBox.critical(
					self, _translate('MainWindow', 'Verbindung nicht möglich', None), 
					_translate('MainWindow', 
						'Keine Verbindung zum Server möglich. Prüfen Sie die VPN-Verbindung!', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
				self.sigCancelStart.emit()
				return
			except xmlrpc.client.ProtocolError as e:
				# uhhh error?
				log.warning('Connection not possible: %s - %s' % (e.errcode, e.errmsg))
				if e.errcode == 403:
					QMessageBox.critical(
						self, _translate('MainWindow', 'Login nicht möglich', None), 
						_translate('MainWindow', 
							'Sie haben keine Berechtigung zum Nutzen der Anwendung.', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
				else:
					QMessageBox.critical(
						self, _translate('MainWindow', 'Unbekannter Fehler beim Verbinden', None), 
						_translate('MainWindow', 
							'Der Server hat die weitere Verbindung abgelehnt.', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
				self.sigCancelStart.emit()
				return
			except Exception as e:
				QMessageBox.critical(
					self, _translate('MainWindow', 'Unbekannter Fehler beim Verbinden', None), 
					_translate('MainWindow', 
						'Der Server konnte den Verbindungsversuch nicht erfolgreich abarbeiten',
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
				self.sigCancelStart.emit()
				return
			self.rpc.__transport.timeout = timeout
			self.loginNeeded = False

			# Check if we're allowed to connect with this version.
			self.splash.showMessage(_translate('SplashScreen', 'Prüfe Kompatibilität...'), 4, color=QColor(255, 255, 255))
			self.app.processEvents()
			try:
				upToDate = self.rpc.compatible(__version__, __min_server__)
			except xmlrpc.client.Fault as e:
				upToDate = False
			if not upToDate:
				log.critical('Could not connect due to incompatibility.')
				QMessageBox.critical(
					self, _translate('MainWindow', 'Versionsfehler!', None), 
					_translate('MainWindow', 
						'Eine Verbindung kann nicht aufgebaut werden wegen Versionsinkompatibilität. ' \
						'Bitte aktualisieren Sie die Server- oder Clientapplikation!', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
				self.sigCancelStart.emit()
				return

			# connection possible - now check the version
			self.splash.showMessage(_translate('SplashScreen', 'Prüfe Version...'), 4, color=QColor(255, 255, 255))
			self.app.processEvents()
			upToDate = self.rpc.upToDate(__version__)
			if not upToDate:
				self.updateVersion()

			# load the data!
			self.splash.showMessage(_translate('SplashScreen', 'Lade Domains...'), 7, color=QColor(255, 255, 255))
			self.app.processEvents()

			# domains
			try:
				self.loadDomains()
			except xmlrpc.client.Fault as e:
				log.critical('Could not load domains because of %s' % (e,))
				QMessageBox.critical(
					self, _translate('MainWindow', 'Daten nicht ladbar', None), 
					_translate('MainWindow', 
						'Die Domains konnten nicht abgerufen werden.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			else:
				self.loadDomainData()

			# load the data!
			self.splash.showMessage(_translate('SplashScreen', 'Lade E-Mail-Adresse...'), 8, color=QColor(255, 255, 255))
			self.app.processEvents()

			# mails
			try:
				self.loadMails(True)
			except xmlrpc.client.Fault as e:
				log.critical('Could not load mails because of %s' % (e,))
				QMessageBox.critical(
					self, _translate('MainWindow', 'Daten nicht ladbar', None), 
					_translate('MainWindow', 
						'Die E-Mail-Konten konnten nicht abgerufen werden.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)

			# load the data!
			self.splash.showMessage(_translate('SplashScreen', 'Lade Zertifikate...'), 9, color=QColor(255, 255, 255))
			self.app.processEvents()

			# certs
			try:
				self.loadCerts(True)
			except xmlrpc.client.Fault as e:
				log.critical('Could not load certificates because of %s' % (e,))
				QMessageBox.critical(
					self, _translate('MainWindow', 'Daten nicht ladbar', None), 
					_translate('MainWindow', 
						'Die Zertifikate konnten nicht abgerufen werden.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
		else:
			if not self.initLoginCert():
				self.sigCancelStart.emit()
				return

		# disable splash screen!
		# (it is always a login needed. But sometimes we cannot simply start the application ;))
		if not self.loginNeeded:
			self.stateProgressBar = True
			self.start()

	def updateVersion(self):
		self.splash.showMessage(_translate('SplashScreen', 'Neue Version verfügbar. Lade herunter...'), 5, color=QColor(255, 255, 255))
		self.app.processEvents()

		try:
			data = self.rpc.getCurrentVersion()
		except xmlrpc.client.Fault as e:
			log.critical('Could not update the flscp because of %s' % (e,))
			QMessageBox.critical(
				self, _translate('MainWindow', 'Aktualisierung', None), 
				_translate('MainWindow', 
					'Eine neue Version konnte nicht heruntergeladen werden.', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
		else:
			self.splash.showMessage(_translate('SplashScreen', 'Neue Version verfügbar. Installiere...'), 6, color=QColor(255, 255, 255))
			self.app.processEvents()
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
				QMessageBox.warning(
					self, _translate('MainWindow', 'Aktualisierung', None), 
					_translate('MainWindow', 
						'Das Update konnte nicht verifiziert werden (CRC Fehler)', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
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
			QMessageBox.information(
				self, _translate('MainWindow', 'Aktualisierung', None), 
				_translate('MainWindow', 
					'Das Control Panel wurde erfolgreich aktualisiert. Bitte starten Sie die Anwendung neu!', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
			zfile.close()
			os.unlink(d.name)
			self.splash.close()
			self.stateProgressBar = False
			self.close()
			return

	def initLoginCert(self):
		self.splash.showMessage(_translate('SplashScreen', 'Warte auf Anmeldung...'), 3, color=QColor(255, 255, 255))
		self.app.processEvents()

		answer = QMessageBox.warning(
			self, _translate('MainWindow', 'Login erforderlich', None), 
			_translate('MainWindow', 
				'Es konnte kein Zertifikat zum Login gefunden werden.\n' \
				'Bitte wählen Sie im nachfolgenden Fenster ein PKCS12-Zertifikat aus.', 
				None),
			QMessageBox.Ok|QMessageBox.Cancel, QMessageBox.Ok
		)
		if answer == QMessageBox.Cancel:
			log.info('Certificate selection cancelled.')
			self.close()
			return False

		try:
			import OpenSSL
		except:
			QMessageBox.critical(
				self, _translate('MainWindow', 'Login nicht möglich', None), 
				_translate('MainWindow', 
					'Es ist das Python Modul "pyOpenSSL" notwendig! Programm wird beendet.', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
			log.error('OpenSSL could not be imported.')
			self.close()
			return False

		self.fd = QFileDialog(self, None)
		self.fd.setWindowModality(QtCore.Qt.ApplicationModal)
		self.fd.setOption(QFileDialog.ReadOnly, True)
		filters = [_translate('MainWindow', 'Zertifikate', None) + ' (*.p12)']
		self.fd.setNameFilters(filters)
		self.fd.setFileMode(QFileDialog.ExistingFile | QFileDialog.AcceptOpen)
		self.fd.filesSelected.connect(self.loginCertSelected)
		# connect slots
		self.execInit.connect(self.init)
		# now show the select!
		self.fd.show()
		QtCore.QCoreApplication.processEvents()
		self.fd.exec_()

		return True

	@pyqtSlot(str)
	def loginCertSelected(self, f):

		if len(f) > 0:
			f = f[0]
		else:
			QMessageBox.warning(
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
				pk = OpenSSL.crypto.load_pkcs12(cnt, passphrase.encode('utf-8'))
			except OpenSSL.crypto.Error as e:
				log.warning('Got error: %s' % (e,))
				passphrase = QInputDialog.getText(
					self,
					_translate('MainWindow', 'Kennwort erforderlich', None),
					_translate('MainWindow', 'Kennwort für %s' % (f,), None),
					QLineEdit.Password,
					'',
				)
				(passphrase, ok) = passphrase
				aborted = not ok
				if ok:
					passphrase = passphrase
			except Exception as e:
				log.warning('Other exception while loading cert! %s' % (str(e),))
			else:
				loaded = True

		if aborted or pk is None:
			QMessageBox.warning(
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
			QMessageBox.warning(
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
			QMessageBox.warning(
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
			QMessageBox.warning(
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

			if self.loginNeeded:
				self.loginNeeded = False
				
			# we have to be careful to block not the thread!
			self.execInit.emit()
			self.update()

	def loadCerts(self, interactive = False):
		if interactive:
			try:
				data = self.rpc.getCerts()
				self.certListLoaded(data)
			except ssl.CertificateError as e:
				log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
				QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			except socket.error as e:
				log.error('Connection to server lost!')
				QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			except xmlrpc.client.ProtocolError as e:
				if e.errcode == 403:
					log.warning('Missing rights for loading mails (%s)' % (e,))
					QMessageBox.warning(
						self, _translate('MainWindow', 'Fehlende Rechte', None), 
						_translate('MainWindow', 
							'Sie haben nicht ausreichend Rechte!', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
				else:
					log.warning('Unexpected error in protocol: %s' % (e,))
					QMessageBox.warning(
						self, _translate('MainWindow', 'Unbekannter Fehler', None), 
						_translate('MainWindow', 
							'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
			finally:
				self.disableProgressBar()
		else:
			self.enableProgressBar(self.ui.tabAdmins, _translate('MainWindow', 'Loading admin list...', None))
			dataLoader = CertListLoader(self.rpc)
			dataLoader.dataLoadedDict.connect(self.certListLoaded)
			dataLoader.certError.connect(self.dataLoadCertError)
			dataLoader.socketError.connect(self.dataLoadSocketError)
			dataLoader.protocolError.connect(self.dataLoadProtocolError)
			dataLoader.unknownError.connect(self.dataLoadError)
			QThreadPool.globalInstance().start(dataLoader)

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
			item = QTableWidgetItem()
			item.setText('%s' % (rowNr + 1,))
			self.ui.adminTable.setVerticalHeaderItem(rowNr, item)
			# hash (to identify later)
			item = QTableWidgetItem()
			item.setText('%s' % (cert.__hash__(),))
			self.ui.adminTable.setItem(rowNr, 0, item)
			# name
			item = QTableWidgetItem()
			item.setText('%s' % (cert.subject.commonName,))
			self.ui.adminTable.setItem(rowNr, 1, item)
			# email
			item = QTableWidgetItem()
			item.setText(cert.subject.emailAddress)
			self.ui.adminTable.setItem(rowNr, 2, item)
			# serial number
			item = QTableWidgetItem()
			item.setText('%s' % (cert.serialNumber,))
			self.ui.adminTable.setItem(rowNr, 3, item)
			# valid until?
			item = QTableWidgetItem()
			if cert.notAfter is not None:
				item.setText(cert.notAfter.strftime('%d.%m.%Y %H:%M:%S'))
			else:
				item.setText('')
			self.ui.adminTable.setItem(rowNr, 4, item)
			# status
			item = QTableWidgetItem()
			icon = QIcon()
			if cert.state == flscertification.FLSCertificate.STATE_OK:
				icon.addPixmap(QPixmap(":/status/ok.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "OK", None))
			elif cert.state == flscertification.FLSCertificate.STATE_ADDED:
				icon.addPixmap(QPixmap(":/status/state_add.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "wird hinzugefügt", None))
			elif cert.state == flscertification.FLSCertificate.STATE_DELETE:
				icon.addPixmap(QPixmap(":/status/trash.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "wird gelöscht", None))
			elif cert.state == flscertification.FLSCertificate.STATE_EXPIRED:
				icon.addPixmap(QPixmap(":/status/expired.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "ist abgelaufen", None))
			else:
				icon.addPixmap(QPixmap(":/status/warning.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "Unbekannt", None))
			item.setIcon(icon)
			self.ui.adminTable.setItem(rowNr, 5, item)
		self.ui.adminTable.setSortingEnabled(True)

	def loadMails(self, interactive = False):
		if interactive:
			try:
				data = self.rpc.getMails()
				self.mailListLoaded(data)
			except ssl.CertificateError as e:
				log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
				QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			except socket.error as e:
				log.error('Connection to server lost!')
				QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			except xmlrpc.client.ProtocolError as e:
				if e.errcode == 403:
					log.warning('Missing rights for loading mails (%s)' % (e,))
					QMessageBox.warning(
						self, _translate('MainWindow', 'Fehlende Rechte', None), 
						_translate('MainWindow', 
							'Sie haben nicht ausreichend Rechte!', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
				else:
					log.warning('Unexpected error in protocol: %s' % (e,))
					QMessageBox.warning(
						self, _translate('MainWindow', 'Unbekannter Fehler', None), 
						_translate('MainWindow', 
							'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
			finally:
				self.disableProgressBar()
		else:
			self.enableProgressBar(self.ui.tabMail, _translate('MainWindow', 'Loading mail list...', None))
			dataLoader = MailListLoader(self.rpc)
			dataLoader.dataLoaded.connect(self.mailListLoaded)
			dataLoader.certError.connect(self.dataLoadCertError)
			dataLoader.socketError.connect(self.dataLoadSocketError)
			dataLoader.protocolError.connect(self.dataLoadProtocolError)
			dataLoader.unknownError.connect(self.dataLoadError)
			QThreadPool.globalInstance().start(dataLoader)

	@pyqtSlot(list)
	def mailListLoaded(self, data):
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
			QMessageBox.critical(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 
					'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
		except socket.error as e:
			log.error('Connection to server lost!')
			QMessageBox.critical(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 
					'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
		except xmlrpc.client.ProtocolError as e:
			if e.errcode == 403:
				log.warning('Missing rights for loading mails (%s)' % (e,))
				QMessageBox.warning(
					self, _translate('MainWindow', 'Fehlende Rechte', None), 
					_translate('MainWindow', 
						'Sie haben nicht ausreichend Rechte!', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			else:
				log.warning('Unexpected error in protocol: %s' % (e,))
				QMessageBox.warning(
					self, _translate('MainWindow', 'Unbekannter Fehler', None), 
					_translate('MainWindow', 
						'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)

	@pyqtSlot()
	def triggerWhatsThis(self):
		if QWhatsThis.inWhatsThisMode():
			QWhatsThis.leaveWhatsThisMode()
		else:
			QWhatsThis.enterWhatsThisMode()

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
			msg = QMessageBox.question(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 'Alle Änderungen gehen verloren. Fortfahren?', None),
				QMessageBox.Yes | QMessageBox.No, QMessageBox.No
			)
			if msg == QMessageBox.Yes:
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

		fd = QFileDialog(self, None)
		fd.setWindowModality(QtCore.Qt.ApplicationModal)
		fd.setOption(QFileDialog.ReadOnly, True)
		filters = [_translate('MainWindow', 'Zertifikate (*.pem *.p12)', None)]
		fd.setNameFilters(filters)
		fd.setFileMode(QFileDialog.ExistingFiles | QFileDialog.AcceptOpen)
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
		).replace(tzinfo=datetime.timezone.utc)
		cert.notAfter = datetime.datetime.strptime(
			pubkey.get_notAfter().decode('utf-8'), '%Y%m%d%H%M%SZ'
		).replace(tzinfo=datetime.timezone.utc)
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
				passphrase = ''.encode('utf-8')
				loaded = False
				aborted = False
				pk = None
				while not loaded and not aborted:
					try:
						pk = OpenSSL.crypto.load_pkcs12(cnt, passphrase.encode('utf-8'))
					except OpenSSL.crypto.Error as e:
						log.warning('Got error: %s' % (e,))
						passphrase = QInputDialog.getText(
							self, 
							_translate('MainWindow', 'Kennwort erforderlich', None),
							_translate('MainWindow', 'Kennwort für %s' % (f,), None),
							QLineEdit.Password,
							'',
						)
						(passphrase, ok) = passphrase
						aborted = not ok
						if ok:
							passphrase = passphrase.encode('utf-8')
					else:
						loaded = True

				if aborted or pk is None:
					log.info('User aborted import of %s!' % (f,))
					continue

				pubkey = pk.get_certificate()
				if pubkey.has_expired():
					QMessageBox.information(
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
							passphrase = QInputDialog.getText(
								self, 
								_translate('MainWindow', 'Kennwort erforderlich', None),
								_translate('MainWindow', 'Kennwort für %s' % (f,), None),
								QLineEdit.Password,
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
						QMessageBox.information(
							self, _translate('MainWindow', 'Information', None), 
							_translate(
								'MainWindow', 
								'Zertifikat "%s" ist abgelaufen und wird übersprungen.' % (f,), 
								None
							)
						)
						continue

			if pubkey is not None:
				try:
					cert = self.getCert(pubkey)
				except:
					QMessageBox.information(
						self, _translate('MainWindow', 'Fehler', None), 
						_translate(
							'MainWindow', 
							'Zertifikat "%s" ist weder ein gültiges .p12, noch ein gültiges öffentliches Zertifikat!' % (f,), 
							None
						)
					)
					continue

				self.certs.add(cert)
				# now display in table?
				rowNr = self.ui.adminTable.rowCount()
				self.ui.adminTable.insertRow(rowNr)
				# number
				item = QTableWidgetItem()
				item.setText('%s' % (rowNr + 1,))
				self.ui.adminTable.setVerticalHeaderItem(rowNr, item)
				# hash (to identify later)
				item = QTableWidgetItem()
				item.setText('%s' % (cert.__hash__(),))
				self.ui.adminTable.setItem(rowNr, 0, item)
				# name
				item = QTableWidgetItem()
				item.setText('%s' % (cert.subject.commonName,))
				self.ui.adminTable.setItem(rowNr, 1, item)
				# email
				item = QTableWidgetItem()
				item.setText(cert.subject.emailAddress)
				self.ui.adminTable.setItem(rowNr, 2, item)
				# serial number
				item = QTableWidgetItem()
				item.setText('%s' % (cert.serialNumber,))
				self.ui.adminTable.setItem(rowNr, 3, item)
				# expires on...
				item = QTableWidgetItem()
				if cert.notAfter is not None:
					item.setText(cert.notAfter.strftime('%d.%m.%Y %H:%M:%S'))
				else:
					item.setText('')
				self.ui.adminTable.setItem(rowNr, 4, item)
				# status
				item = QTableWidgetItem()
				icon = QIcon()
				if cert.state == flscertification.FLSCertificate.STATE_OK:
					icon.addPixmap(QPixmap(":/status/ok.png"), QIcon.Normal, QIcon.Off)
					item.setText(_translate("MainWindow", "OK", None))
				elif cert.state == flscertification.FLSCertificate.STATE_ADDED:
					icon.addPixmap(QPixmap(":/status/state_add.png"), QIcon.Normal, QIcon.Off)
					item.setText(_translate("MainWindow", "wird hinzugefügt", None))
				elif cert.state == flscertification.FLSCertificate.STATE_DELETE:
					icon.addPixmap(QPixmap(":/status/trash.png"), QIcon.Normal, QIcon.Off)
					item.setText(_translate("MainWindow", "wird gelöscht", None))
				else:
					icon.addPixmap(QPixmap(":/status/warning.png"), QIcon.Normal, QIcon.Off)
					item.setText(_translate("MainWindow", "Unbekannt", None))
				item.setIcon(icon)
				self.ui.adminTable.setItem(rowNr, 5, item)

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
			msg = QMessageBox.question(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 'Alle Änderungen gehen verloren. Fortfahren?', None),
				QMessageBox.Yes | QMessageBox.No, QMessageBox.No
			)
			if msg == QMessageBox.Yes:
				try:
					self.loadMails()
				except xmlrpc.client.Fault as e:
					log.critical('Could not load mails because of %s' % (e,))
					QMessageBox.critical(
						self, _translate('MainWindow', 'Daten nicht ladbar', None), 
						_translate('MainWindow', 
							'Die E-Mail-Konten konnten nicht abgerufen werden.', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
		else:
			try:
				self.loadMails()
			except xmlrpc.client.Fault as e:
				log.critical('Could not load mails because of %s' % (e,))
				QMessageBox.critical(
					self, _translate('MainWindow', 'Daten nicht ladbar', None), 
					_translate('MainWindow', 
						'Die E-Mail-Konten konnten nicht abgerufen werden.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
		self.disableProgressBar()

	def loadMailData(self):
		self.ui.mailTable.setSortingEnabled(False)
		self.ui.mailTable.setRowCount(0)

		for row in self.mails:
			rowNr = self.ui.mailTable.rowCount()
			self.ui.mailTable.insertRow(rowNr)
			item = QTableWidgetItem()
			try:
				item.setText('%s' % (row.id,))
			except Exception as e:
				log.warning('%s' % (e,))
				return
			item.setTextAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
			self.ui.mailTable.setItem(rowNr, 0, item)
			# mail
			item = QTableWidgetItem()
			item.setText(row.getMailAddress())
			self.ui.mailTable.setItem(rowNr, 1, item)
			# type
			item = QTableWidgetItem()
			icon = QIcon()
			if row.type == MailAccount.TYPE_ACCOUNT:
				icon.addPixmap(QPixmap(":/typ/account.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "Konto", None))
			elif row.type == MailAccount.TYPE_FWDSMTP:
				icon.addPixmap(QPixmap(":/typ/fwdsmtp.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "Weiterleitung mit SMTP", None))
			else:
				icon.addPixmap(QPixmap(":/typ/forward.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "Weiterleitung", None))
			item.setIcon(icon)
			self.ui.mailTable.setItem(rowNr, 2, item)
			# quota (human readable)
			item = QTableWidgetItem()
			item.setText(row.getQuotaReadable())
			item.setTextAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
			self.ui.mailTable.setItem(rowNr, 3, item)
			# quotaSts (in percent)
			item = QTableWidgetItem()
			item.setText(row.getQuotaStatus())
			item.setTextAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
			self.ui.mailTable.setItem(rowNr, 4, item)
			# Enabled / Disabled
			item = QTableWidgetItem()
			if row.enabled:
				item.setText(_translate('MainWindow', 'Ja'))
			else:
				item.setText(_translate('MainWindow', 'Nein'))
			item.setTextAlignment(QtCore.Qt.AlignCenter|QtCore.Qt.AlignVCenter)
			self.ui.mailTable.setItem(rowNr, 5, item)
			# status
			item = QTableWidgetItem()
			icon = QIcon()
			if row.state == MailAccount.STATE_OK:
				icon.addPixmap(QPixmap(":/status/ok.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "OK", None))
			elif row.state == MailAccount.STATE_CHANGE:
				icon.addPixmap(QPixmap(":/status/waiting.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "wird geändert", None))
			elif row.state == MailAccount.STATE_CREATE:
				icon.addPixmap(QPixmap(":/status/state_add.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "wird hinzugefügt", None))
			elif row.state == MailAccount.STATE_DELETE:
				icon.addPixmap(QPixmap(":/status/trash.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "wird gelöscht", None))
			elif row.state == MailAccount.STATE_QUOTA:
				icon.addPixmap(QPixmap(":/status/general_process.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "Quota wird neuberechnet", None))
			else:
				icon.addPixmap(QPixmap(":/status/warning.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "Unbekannt", None))
			item.setIcon(icon)
			self.ui.mailTable.setItem(rowNr, 6, item)

		self.ui.mailTable.setSortingEnabled(True)
		if len(self.ui.search.text()) > 0:
			self.filterMail(self.ui.search.text())

	def selectHost(self):
		mf = HostSelectionForm(self.splash)
		mf.show()
		mf.exec_()
		if not mf.aborted:
			log.info('Host was selected: %s' % (mf.selectedHost,))
			conf.set('options', 'currenthost', mf.selectedHost)
			return True
		else:
			log.info('No host was selected! Aborting...')
			conf.set('options', 'currenthost', '')
			return False

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
	def calculateMailQuota(self):
		log.info('Clicked "calculate mail quota"')
		for selectedRow in self.ui.mailTable.selectionModel().selectedRows():
			nr = self.ui.mailTable.item(selectedRow.row(), 0).text()
			account = self.mails.findById(nr)
			account.markQuotaCalc()
			log.debug('Marked mail to recalculation.')

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

	@pyqtSlot()
	def toggleStatusMail(self):
		nrSelected = len(self.ui.mailTable.selectionModel().selectedRows())
		log.info('Have to toggle %i items!' % (nrSelected,))

		for selectedRow in self.ui.mailTable.selectionModel().selectedRows():
			nr = self.ui.mailTable.item(selectedRow.row(), 0).text()
			account = self.mails.findById(nr)
			if account is not None:
				account.toggleStatus()

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
		item = QTreeWidgetItem()
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
		icon = QIcon()
		if row.state == Domain.STATE_OK:
			icon.addPixmap(QPixmap(":/status/ok.png"), QIcon.Normal, QIcon.Off)
			item.setText(5, _translate("MainWindow", "OK", None))
		elif row.state == Domain.STATE_CHANGE:
			icon.addPixmap(QPixmap(":/status/waiting.png"), QIcon.Normal, QIcon.Off)
			item.setText(5, _translate("MainWindow", "wird geändert", None))
		elif row.state == Domain.STATE_CREATE:
			icon.addPixmap(QPixmap(":/status/state_add.png"), QIcon.Normal, QIcon.Off)
			item.setText(5, _translate("MainWindow", "wird hinzugefügt", None))
		elif row.state == Domain.STATE_DELETE:
			icon.addPixmap(QPixmap(":/status/trash.png"), QIcon.Normal, QIcon.Off)
			item.setText(5, _translate("MainWindow", "wird gelöscht", None))
		else:
			icon.addPixmap(QPixmap(":/status/warning.png"), QIcon.Normal, QIcon.Off)
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
	def addDomain(self):
		addDNS = False

		elms = self.ui.tabDNS.currentWidget()
		# first we think, that the selected element contains tree widget:
		activeTable = elms.findChild(QTreeWidget)
		if activeTable is None:
			addDNS = True
			activeTable = elms.findChild(QTableWidget)
			if activeTable is None:
				return

		if addDNS:
			self.addDNSEntry(dnsTable=activeTable)
		else:
			# if we have something selected, than lets use that as parent!
			selectedIds = []
			for selectedRow in self.ui.domainTree.selectedItems():
				selectedIds.append(selectedRow.text(0))

			parentDomain = None
			if len(selectedIds) == 1:
				parentDomain = self.domains.findById(selectedIds[0])

			de = DomainEditor(self.domains, parentDomain=parentDomain, parent=self)
			de.show()
			de.exec_()
			if de.accepted:
				log.debug('Yes... domain can be added. Can we?')
				nD = de.domain
				if nD is not None:
					self.domains.add(nD)
					self.loadDomainData()
			else:
				log.debug('No... domain creation was cancelled!')

	@pyqtSlot()
	def editDomain(self):
		editDNS = False

		elms = self.ui.tabDNS.currentWidget()
		# first we think, that the selected element contains tree widget:
		activeTable = elms.findChild(QTreeWidget)
		if activeTable is None:
			editDNS = True
			activeTable = elms.findChild(QTableWidget)
			if activeTable is None:
				return

		if editDNS:
			# eehm... we do not support it ;)
			return
		else:
			# if we have something selected, than lets use that as parent!
			for selectedRow in self.ui.domainTree.selectedItems():
				did = selectedRow.text(0)
				domain = self.domains.findById(did)
				if domain is not None:
					de = DomainEditor(self.domains, domain=domain, parent=self)
					de.show()
					de.exec_()
					if de.accepted:
						log.debug('Yes... domain can be saved. Can we?')
						self.loadDomainData()
					else:
						log.debug('No... domain editing was cancelled!')
						# so do nothing! ;)

	def addDNSEntry(self, triggered = False, dnsTable = False):
		if dnsTable is None:
			dnsTable = self.ui.tabDNS.currentWidget().findChild(QTableWidget)
			if dnsTable is None:
				return

		domainId = dnsTable.property('domainId')
		# first: create a new DNS Entry
		dnse = Dns()
		dnse.generateId()
		dnse.domainId = domainId
		dnse.state = Dns.STATE_CREATE
		# add to the global list!
		self.dns.add(dnse)

		# now add to the dnsTable!
		dnsTable.setRowCount(dnsTable.rowCount())
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

		rowNr = dnsTable.rowCount()
		dnsTable.insertRow(rowNr)
		# id
		item = QTableWidgetItem()
		item.setText('%s' % (dnse.id,))
		item.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled)
		item.setData(QtCore.Qt.UserRole, 'id')
		item.setData(QtCore.Qt.UserRole + 5, True) # changes not relevant
		dnsTable.setItem(rowNr, 0, item)
		# key
		item = QTableWidgetItem()
		item.setText('%s' % (dnse.key,))
		item.setData(QtCore.Qt.UserRole, 'key')
		dnsTable.setItem(rowNr, 1, item)
		# type
		item = QComboBox()
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
		item = QTableWidgetItem()
		item.setText('%s' % (dnse.prio,))
		item.setData(QtCore.Qt.UserRole, 'prio')
		dnsTable.setItem(rowNr, 3, item)
		# value
		item = QTableWidgetItem()
		item.setText('%s' % (dnse.value,))
		item.setData(QtCore.Qt.UserRole, 'value')
		dnsTable.setItem(rowNr, 4, item)
		# weight
		item = QTableWidgetItem()
		item.setText('%s' % (dnse.weight,))
		item.setData(QtCore.Qt.UserRole, 'weight')
		dnsTable.setItem(rowNr, 5, item)
		# port
		item = QTableWidgetItem()
		item.setText('%s' % (dnse.port,))
		item.setData(QtCore.Qt.UserRole, 'port')
		dnsTable.setItem(rowNr, 6, item)
		# admin
		item = QTableWidgetItem()
		item.setText('%s' % (dnse.dnsAdmin,))
		item.setData(QtCore.Qt.UserRole, 'dnsAdmin')
		dnsTable.setItem(rowNr, 7, item)
		# refresh
		item = QTableWidgetItem()
		item.setText('%s' % (dnse.refreshRate,))
		item.setData(QtCore.Qt.UserRole, 'refreshRate')
		dnsTable.setItem(rowNr, 8, item)
		# retry
		item = QTableWidgetItem()
		item.setText('%s' % (dnse.retryRate,))
		item.setData(QtCore.Qt.UserRole, 'retryRate')
		dnsTable.setItem(rowNr, 9, item)
		# expire
		item = QTableWidgetItem()
		item.setText('%s' % (dnse.expireTime,))
		item.setData(QtCore.Qt.UserRole, 'expireTime')
		dnsTable.setItem(rowNr, 10, item)
		# ttl
		item = QTableWidgetItem()
		item.setText('%s' % (dnse.ttl,))
		item.setData(QtCore.Qt.UserRole, 'ttl')
		dnsTable.setItem(rowNr, 11, item)
		# status
		item = QTableWidgetItem()
		icon = QIcon()
		if dnse.state == Dns.STATE_OK:
			icon.addPixmap(QPixmap(":/status/ok.png"), QIcon.Normal, QIcon.Off)
			item.setText(_translate("MainWindow", "OK", None))
		elif dnse.state == Dns.STATE_CREATE:
			icon.addPixmap(QPixmap(":/status/state_add.png"), QIcon.Normal, QIcon.Off)
			item.setText(_translate("MainWindow", "wird hinzugefügt", None))
		elif dnse.state == Dns.STATE_CHANGE:
			icon.addPixmap(QPixmap(":/status/waiting.png"), QIcon.Normal, QIcon.Off)
			item.setText(_translate("MainWindow", "wird geändert", None))
		elif dnse.state == Dns.STATE_DELETE:
			icon.addPixmap(QPixmap(":/status/trash.png"), QIcon.Normal, QIcon.Off)
			item.setText(_translate("MainWindow", "wird gelöscht", None))
		else:
			icon.addPixmap(QPixmap(":/status/warning.png"), QIcon.Normal, QIcon.Off)
			item.setText(_translate("MainWindow", "Unbekannt", None))
		item.setIcon(icon)
		item.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled)
		item.setData(QtCore.Qt.UserRole, 'state')
		item.setData(QtCore.Qt.UserRole + 5, True) # changes not relevant
		dnsTable.setItem(rowNr, 12, item)
		dsco = DnsStateChangeObserver(dnsTable, item, dnse)
		dnse.stateChanged.connect(dsco.stateChanged)
		self.ui.dnsNotifier[domainId].append(dsco)

	@pyqtSlot()
	def deleteDomain(self):
		editDNS = False

		elms = self.ui.tabDNS.currentWidget()
		# first we think, that the selected element contains tree widget:
		activeTable = elms.findChild(QTreeWidget)
		if activeTable is None:
			editDNS = True
			activeTable = elms.findChild(QTableWidget)
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
			activeTable = self.ui.tabDNS.currentWidget().findChild(QTableWidget)
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

	@pyqtSlot()
	def generateBindFile(self):
		elms = self.ui.tabDNS.currentWidget()
		# first we think, that the selected element contains tree widget:
		activeTable = elms.findChild(QTreeWidget)
		if activeTable is None:
			activeTable = elms.findChild(QTableWidget)
			if activeTable is not None:
				self.generateBindFileByDns(activeTable)
			return

		nrSelected = len(self.ui.domainTree.selectionModel().selectedRows())
		log.info('Have to generate bind file for %i items!' % (nrSelected,))

		zoneFiles = []
		for selectedRow in self.ui.domainTree.selectedItems():
			nr = int(selectedRow.text(0))
			# now get the zone file
			try:
				zoneFiles.append(self.rpc.getDomainZoneFile(nr))
			except Exception as e:
				log.error('Could not generate zone file: %s' % (str(e),))
				QMessageBox.warning(
					self, _translate('MainWindow', 'Zonen-Erstellung', None), 
					_translate(
						'MainWindow', 
						'BIND-Datei konnte nicht erzeugt werden, weil nicht alle erforderlichen DNS-Einträge erstellt worden sind! ' +
						'Haben Sie bereits alle Änderungen gespeichert?', 
						None
					)
				)

		for f in zoneFiles:
			self.zoneFileLoaded(f)

	def generateBindFileByDns(self, table):
		domainId = table.property('domainId')
		log.info('Have to generate bind file for domain %s!' % (domainId,))
		try:
			self.zoneFileLoaded(self.rpc.getDomainZoneFile(domainId))
		except Exception as e:
			pass

	@pyqtSlot(str)
	def zoneFileLoaded(self, text):
		log.debug(text)
		fco = FlsCpOutput(self)
		fco.setText(text)
		fco.show()
	
	def createDNSWidget(self, domain):
		tabDomainDNS = QWidget()
		verticalLayout = QVBoxLayout(tabDomainDNS)
		tableDNS = QTableWidget(tabDomainDNS)
		tableDNS.setEditTriggers(QAbstractItemView.DoubleClicked|QAbstractItemView.EditKeyPressed)
		tableDNS.setAlternatingRowColors(True)
		tableDNS.setSelectionBehavior(QAbstractItemView.SelectRows)
		tableDNS.setColumnCount(13)
		tableDNS.setRowCount(0)
		tableDNS.setSortingEnabled(False)
		item = QTableWidgetItem()
		tableDNS.setVerticalHeaderItem(0, item)
		item = QTableWidgetItem()
		tableDNS.setVerticalHeaderItem(1, item)
		item = QTableWidgetItem()
		item.setTextAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
		font = QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(0, item)
		item = QTableWidgetItem()
		item.setTextAlignment(QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
		font = QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(1, item)
		item = QTableWidgetItem()
		item.setTextAlignment(QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
		font = QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(2, item)
		item = QTableWidgetItem()
		item.setTextAlignment(QtCore.Qt.AlignHCenter|QtCore.Qt.AlignVCenter|QtCore.Qt.AlignCenter)
		font = QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(3, item)
		item = QTableWidgetItem()
		item.setTextAlignment(QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
		font = QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(4, item)
		item = QTableWidgetItem()
		font = QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(5, item)
		item = QTableWidgetItem()
		font = QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(6, item)
		item = QTableWidgetItem()
		font = QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(7, item)
		item = QTableWidgetItem()
		font = QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(8, item)
		item = QTableWidgetItem()
		font = QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(9, item)
		item = QTableWidgetItem()
		font = QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(10, item)
		item = QTableWidgetItem()
		font = QFont()
		font.setBold(True)
		font.setWeight(75)
		item.setFont(font)
		tableDNS.setHorizontalHeaderItem(11, item)
		item = QTableWidgetItem()
		font = QFont()
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
		action = QAction(
			QIcon(QPixmap(':actions/delete.png')), 
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
			activeTable = self.ui.tabDNS.currentWidget().findChild(QTableWidget)
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
			msg = QMessageBox.question(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 'Alle Änderungen gehen verloren. Fortfahren?', None),
				QMessageBox.Yes | QMessageBox.No, QMessageBox.No
			)

			if msg == QMessageBox.Yes:
				pending = False
	
		if not pending or not interactive:
			# remove all entries for domain id
			self.dns.removeByDomain(domainId)

			dataLoader = DnsListLoader(self.rpc, domainId)
			dataLoader.dataLoadedDict.connect(self.dnsDataLoaded)
			dataLoader.certError.connect(self.dataLoadCertError)
			dataLoader.socketError.connect(self.dataLoadSocketError)
			dataLoader.protocolError.connect(self.dataLoadProtocolError)
			dataLoader.unknownError.connect(self.dataLoadError)
			QThreadPool.globalInstance().start(dataLoader)

	@pyqtSlot(int, list)
	def dnsDataLoaded(self, data):

		for domainId, entries in data.items():
			for f in entries:
				d = Dns.fromDict(f)
				# check if d already in dns
				if d not in self.dns:
					self.dns.add(d)

			if domainId is not None:
				self.loadDnsData(domainId)

		self.disableProgressBar()

	def loadDnsData(self, domainId):
		if domainId not in self.ui.dnsTabs or \
			domainId not in self.ui.dnsTable:
			log.debug('Got new data for domain #%s, but no table is open for that.' % (domainId,))

		dnsTab = self.ui.dnsTabs[domainId]
		dnsTable = self.ui.dnsTable[domainId]

		if dnsTable is None or dnsTab is None:
			log.warning('Should update table for domain #%s, but objects are not present.' % (domainId,))
			return

		log.debug('Reload DNS-table for domain #%s' % (domainId,))

		dnsTable.setSortingEnabled(False)
		dnsTable.setRowCount(0)

		# remove all notifier
		if domainId in self.ui.dnsNotifier:
			log.debug(
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
			log.debug('Found no notifier for domain.')
		log.debug('Found %i notifier. Expected: 0' % (len(self.ui.dnsNotifier[domainId]),))

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
			item = QTableWidgetItem()
			item.setText('%s' % (dnse.id,))
			item.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled)
			item.setData(QtCore.Qt.UserRole, 'id')
			item.setData(QtCore.Qt.UserRole + 5, True) # changes not relevant
			dnsTable.setItem(rowNr, 0, item)
			# key
			item = QTableWidgetItem()
			item.setText('%s' % (dnse.key,))
			item.setData(QtCore.Qt.UserRole, 'key')
			dnsTable.setItem(rowNr, 1, item)
			# type
			item = QComboBox()
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
			item = QTableWidgetItem()
			item.setText('%s' % (dnse.prio,))
			item.setData(QtCore.Qt.UserRole, 'prio')
			dnsTable.setItem(rowNr, 3, item)
			# value
			item = QTableWidgetItem()
			item.setText('%s' % (dnse.value,))
			item.setData(QtCore.Qt.UserRole, 'value')
			dnsTable.setItem(rowNr, 4, item)
			# weight
			item = QTableWidgetItem()
			item.setText('%s' % (dnse.weight,))
			item.setData(QtCore.Qt.UserRole, 'weight')
			dnsTable.setItem(rowNr, 5, item)
			# port
			item = QTableWidgetItem()
			item.setText('%s' % (dnse.port,))
			item.setData(QtCore.Qt.UserRole, 'port')
			dnsTable.setItem(rowNr, 6, item)
			# admin
			item = QTableWidgetItem()
			item.setText('%s' % (dnse.dnsAdmin,))
			item.setData(QtCore.Qt.UserRole, 'dnsAdmin')
			dnsTable.setItem(rowNr, 7, item)
			# refresh
			item = QTableWidgetItem()
			item.setText('%s' % (dnse.refreshRate,))
			item.setData(QtCore.Qt.UserRole, 'refreshRate')
			dnsTable.setItem(rowNr, 8, item)
			# retry
			item = QTableWidgetItem()
			item.setText('%s' % (dnse.retryRate,))
			item.setData(QtCore.Qt.UserRole, 'retryRate')
			dnsTable.setItem(rowNr, 9, item)
			# expire
			item = QTableWidgetItem()
			item.setText('%s' % (dnse.expireTime,))
			item.setData(QtCore.Qt.UserRole, 'expireTime')
			dnsTable.setItem(rowNr, 10, item)
			# ttl
			item = QTableWidgetItem()
			item.setText('%s' % (dnse.ttl,))
			item.setData(QtCore.Qt.UserRole, 'ttl')
			dnsTable.setItem(rowNr, 11, item)
			# status
			item = QTableWidgetItem()
			icon = QIcon()
			if dnse.state == Dns.STATE_OK:
				icon.addPixmap(QPixmap(":/status/ok.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "OK", None))
			elif dnse.state == Dns.STATE_CREATE:
				icon.addPixmap(QPixmap(":/status/state_add.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "wird hinzugefügt", None))
			elif dnse.state == Dns.STATE_CHANGE:
				icon.addPixmap(QPixmap(":/status/waiting.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "wird geändert", None))
			elif dnse.state == Dns.STATE_DELETE:
				icon.addPixmap(QPixmap(":/status/trash.png"), QIcon.Normal, QIcon.Off)
				item.setText(_translate("MainWindow", "wird gelöscht", None))
			else:
				icon.addPixmap(QPixmap(":/status/warning.png"), QIcon.Normal, QIcon.Off)
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

	@pyqtSlot(QTableWidget, str, QTableWidgetItem)
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

		if hasattr(dns, dnsProperty) and str(getattr(dns, dnsProperty)) != str(value):
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

	@pyqtSlot(QTableWidget, int, int, str, QWidget, str)
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

		if hasattr(dns, dnsProperty) and str(getattr(dns, dnsProperty)) != str(value):
			setattr(dns, dnsProperty, value)
			if dns.state == Dns.STATE_OK:
				dns.changeState(Dns.STATE_CHANGE)
			# find row for item
			log.info('I know the row for update the validating style: %i!' % (row,))
			# now change the editable-flag of the other columns!
			if dnsProperty == 'type':
				visibleList = dns.getValidCombination()
			else:
				visibleList = []

			# validate the new items
			state, msg = dns.validate()
			self.updateDnsValidation(table, row, state, msg, True if dnsProperty == 'type' else False, visibleList)

		log.debug('Widget changed: DNS: %s, Name: %s, Value: %s' % ( id, dnsProperty, value))

	def updateDnsValidation(self, table, row, state, msg, typeChange = False, visibleList = None):
		curCol = 0
		maxCol = table.columnCount()
		if visibleList is None:
			visibleList = []

		brush = QBrush(QColor(255, 207, 207))
		if state:
			log.info('DNS change is valid!')
		else:
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

			if typeChange and name not in ['id', 'key', 'type']:
				if name in visibleList:
					log.debug('Enable %s!' % (name,))
					item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
				else:
					log.debug('Disable %s!' % (name,))
					item.setFlags(item.flags() &~ QtCore.Qt.ItemIsEditable)

			try:
				if not state and name in msg:
					brush.setStyle(QtCore.Qt.SolidPattern)
				else:
					brush.setStyle(QtCore.Qt.NoBrush)
				item.setBackground(brush)
			except Exception as e:
				log.error('Cannot set the background for widgets!!!!: %s' % (str(e),))
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

		if self.ui.tabDNS.currentWidget().findChild(QTreeWidget) is None:
			return

		nrSelected = len(self.ui.domainTree.selectionModel().selectedRows())
		log.info('Have to open %i domains!' % (nrSelected,))

		firstSave = False
		alreadyDelete = False
		for selectedRow in self.ui.domainTree.selectedItems():
			nr = selectedRow.text(0)
			domain = self.domains.findById(nr)
			if domain is not None:
				if domain.state != Domain.STATE_CREATE and \
					domain.state != Domain.STATE_DELETE:
					# is a tab with this already open?
					self.createDNSWidget(domain)
				elif domain.state == Domain.STATE_CREATE:
					firstSave = True
				elif domain.state == Domain.STATE_DELETE:
					alreadyDelete = True

		if alreadyDelete:
			QMessageBox.information(
				self, _translate('MainWindow', 'DNS-Einstellungen ändern', None), 
				_translate('MainWindow', 
					'Die Domain wird bereits entfernt. DNS-Einstellungen können nicht vorgenommen werden.',
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
		elif firstSave:
			QMessageBox.information(
				self, _translate('MainWindow', 'DNS-Einstellungen ändern', None), 
				_translate('MainWindow', 
					'Bitte speichern Sie zunächst die neu angelegten Domains!',
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)

	@pyqtSlot()
	def reloadDomainTree(self):
		# which tab?
		activeWidget = self.ui.tabDNS.currentWidget().findChild(QTableWidget)
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
			msg = QMessageBox.question(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 'Alle Änderungen gehen verloren. Fortfahren?', None),
				QMessageBox.Yes | QMessageBox.No, QMessageBox.No
			)
			if msg != QMessageBox.Yes:
				loadDomainData = False


		if loadDomainData:
			try:
				self.loadDomains()
			except xmlrpc.client.Fault as e:
				log.critical('Could not load domains because of %s' % (e,))
				QMessageBox.critical(
					self, _translate('MainWindow', 'Daten nicht ladbar', None), 
					_translate('MainWindow', 
						'Die Domains konnten nicht abgerufen werden.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			else:
				self.loadDomainData()

		self.disableProgressBar()

	@pyqtSlot(int)
	def dnsCloseTab(self, idx):
		if idx == 0:
			log.info('Cannot close the domain overview!')
			QMessageBox.information(
				self, _translate('MainWindow', 'Domain-Tab', None), 
				_translate('MainWindow', 
					'Die Überssichtsseite kann nicht geschlossen werden.', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
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
	def commitDomainData(self):
		editDNS = False

		elms = self.ui.tabDNS.currentWidget()
		# first we think, that the selected element contains tree widget:
		activeTable = elms.findChild(QTreeWidget)
		if activeTable is None:
			editDNS = True
			activeTable = elms.findChild(QTableWidget)
			if activeTable is None:
				return

		if editDNS:
			self.saveDNSEntries(activeTable=activeTable)
		else:
			domainList = DomainList()
			for domain in self.domains:
				if domain is not None:
					if domain.state == Domain.STATE_CREATE:
						# we cancel pending creation action.
						#self.ui.domainTree.removeItemWidget(selectedRow)
						self.domains.remove(domain)
					else:
						# do not remove (because we want to see the pending action!)
						# check possibility!
						# this means: are there mails with this domain?
						if domain.state == Domain.STATE_DELETE and not domain.isDeletable(self.domains, self.mails):
							log.error('cannot delete domain %s!' % (domain.name,))
							continue
						else:
							domainList.add(domain)

			if len(domainList) > 0:
				try:
					self.rpc.saveDomains(domainList)
				except TypeError as e:
					log.error('Uhhh we tried to send things the server does not understood (%s)' % (e,))
					QMessageBox.warning(
							self, _translate('MainWindow', 'Datenfehler', None), 
							_translate('MainWindow', 
								'Bei der Kommunikation mit dem Server ist ein Datenfehler aufgetreten!', 
								None),
							QMessageBox.Ok, QMessageBox.Ok
						)
				except ssl.CertificateError as e:
					log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
					QMessageBox.critical(
						self, _translate('MainWindow', 'Warnung', None), 
						_translate('MainWindow', 
							'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
				except socket.error as e:
					QMessageBox.critical(
						self, _translate('MainWindow', 'Warnung', None), 
						_translate('MainWindow', 
							'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
				except xmlrpc.client.ProtocolError as e:
					if e.errcode == 403:
						log.warning('Missing rights for loading mails (%s)' % (e,))
						QMessageBox.warning(
							self, _translate('MainWindow', 'Fehlende Rechte', None), 
							_translate('MainWindow', 
								'Sie haben nicht ausreichend Rechte!', 
								None),
							QMessageBox.Ok, QMessageBox.Ok
						)
					else:
						log.warning('Unexpected error in protocol: %s' % (e,))
						QMessageBox.warning(
							self, _translate('MainWindow', 'Unbekannter Fehler', None), 
							_translate('MainWindow', 
								'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
								None),
							QMessageBox.Ok, QMessageBox.Ok
						)
				else:
					log.debug('Saved with success. Now reload domain data.')
					try:
						self.loadDomains()
					except xmlrpc.client.Fault as e:
						log.critical('Could not load domains because of %s' % (e,))
						QMessageBox.critical(
							self, _translate('MainWindow', 'Daten nicht ladbar', None), 
							_translate('MainWindow', 
								'Die Domains konnten nicht abgerufen werden.', 
								None),
							QMessageBox.Ok, QMessageBox.Ok
						)
					else:
						self.loadDomainData()
						
		self.disableProgressBar()

	@pyqtSlot(bool)
	def saveDNSEntries(self, triggered = False, activeTable = None):
		if activeTable is None:
			activeTable = self.ui.tabDNS.currentWidget().findChild(QTableWidget)
			if activeTable is None:
				return

		# first: check whether all dns entries are valid!
		domainId = activeTable.property('domainId')
		if domainId is None:
			return

		dList = DNSList()
		errors = False
		for dns in self.dns.iterByDomain(domainId):
			if not dns.validate():
				errors = True
				break
			else:
				dList.add(dns)

		if errors:
			QMessageBox.warning(
				self, _translate('MainWindow', 'DNs-Fehler', None), 
				_translate('MainWindow', 
					'Die DNS-Tabelle enthält Fehler und kann nicht gespeichert werden.', 
					None),
				QMessageBox.Ok, QMessageBox.Ok
			)
			return

		# All is ok. Now save (but only for given domain!)
		self.enableProgressBar()
		if len(dList) > 0:
			try:
				self.rpc.saveDns(domainId, dList)
			except TypeError as e:
				log.error('Uhhh we tried to send things the server does not understood (%s)' % (e,))
				QMessageBox.warning(
						self, _translate('MainWindow', 'Datenfehler', None), 
						_translate('MainWindow', 
							'Bei der Kommunikation mit dem Server ist ein Datenfehler aufgetreten!', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
			except ssl.CertificateError as e:
				log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
				QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			except socket.error as e:
				QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			except xmlrpc.client.ProtocolError as e:
				if e.errcode == 403:
					log.warning('Missing rights for loading mails (%s)' % (e,))
					QMessageBox.warning(
						self, _translate('MainWindow', 'Fehlende Rechte', None), 
						_translate('MainWindow', 
							'Sie haben nicht ausreichend Rechte!', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
				else:
					log.warning('Unexpected error in protocol: %s' % (e,))
					QMessageBox.warning(
						self, _translate('MainWindow', 'Unbekannter Fehler', None), 
						_translate('MainWindow', 
							'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)

			else:
				self.reloadDnsDataByDomain(domainId, interactive=False)

		self.disableProgressBar()

	@pyqtSlot()
	def changelog(self):
		win = ReSTViewer(self)
		win.showFile('CHANGELOG')

	@pyqtSlot()
	def about(self):
		aboutWin = FlsCpAbout(self)

	@pyqtSlot()
	def aboutQt(self):
		QMessageBox.aboutQt(self)

	@pyqtSlot()
	def preQuitSlot(self):
		if self.rpc is not None:
			del(self.rpc)

	@pyqtSlot()
	def abortStartup(self): 
		self.splash.close()
		self.stateProgressBar = False
		self.close()
		self.killApp.emit()

	@pyqtSlot()
	def quitApp(self):
		# are there some pending actions?
		pending = False
		for f in self.mails:
			if f.state != MailAccount.STATE_OK:
				pending = True
				break

		if pending:
			msg = QMessageBox.question(
				self, _translate('MainWindow', 'Warnung', None), 
				_translate('MainWindow', 'Alle Änderungen gehen verloren. Beenden?', None),
				QMessageBox.Yes | QMessageBox.No, QMessageBox.No
			)
			if msg == QMessageBox.Yes:
				self.close()

		else:
			self.close()

		self.app.quit()

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
				QMessageBox.warning(
						self, _translate('MainWindow', 'Datenfehler', None), 
						_translate('MainWindow', 
							'Bei der Kommunikation mit dem Server ist ein Datenfehler aufgetreten!', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
			except ssl.CertificateError as e:
				log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
				QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			except socket.error as e:
				QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			except xmlrpc.client.ProtocolError as e:
				if e.errcode == 403:
					log.warning('Missing rights for loading mails (%s)' % (e,))
					QMessageBox.warning(
						self, _translate('MainWindow', 'Fehlende Rechte', None), 
						_translate('MainWindow', 
							'Sie haben nicht ausreichend Rechte!', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
				else:
					log.warning('Unexpected error in protocol: %s' % (e,))
					QMessageBox.warning(
						self, _translate('MainWindow', 'Unbekannter Fehler', None), 
						_translate('MainWindow', 
							'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)

			else:
				try:
					self.loadMails()
				except xmlrpc.client.Fault as e:
					log.critical('Could not load mails because of %s' % (e,))
					QMessageBox.critical(
						self, _translate('MainWindow', 'Daten nicht ladbar', None), 
						_translate('MainWindow', 
							'Die E-Mail-Konten konnten nicht abgerufen werden.', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
				else:
					self.loadMailData()
		self.disableProgressBar()

	def setupMailTable(self):
		# create context menu
		actions = []
		act = QAction(
			QIcon(QPixmap(':actions/edit.png')), 
			_translate("MainWindow", "Bearbeiten", None), self.ui.mailTable
		)
		act.triggered.connect(self.editMail)
		actions.append(act)
		act = QAction(
			QIcon(QPixmap(':actions/delete.png')), 
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
				self.rpc.saveCerts(data.__serialize__())
			except ssl.CertificateError as e:
				log.error('Possible attack! Server Certificate is wrong! (%s)' % (e,))
				QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Potentieller Angriff! Server-Zertifikat ist fehlerhaft! Bitte informieren Sie Ihren Administrator!', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			except socket.error as e:
				QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Verbindung zum Server nicht möglich. Bitte versuchen Sie es später noch einmal.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			except xmlrpc.client.Fault as e:
				QMessageBox.critical(
					self, _translate('MainWindow', 'Warnung', None), 
					_translate('MainWindow', 
						'Austausch von Daten mit dem Server ist fehlerhaft.', 
						None),
					QMessageBox.Ok, QMessageBox.Ok
				)
			except xmlrpc.client.ProtocolError as e:
				if e.errcode == 403:
					log.warning('Missing rights for loading mails (%s)' % (e,))
					QMessageBox.warning(
						self, _translate('MainWindow', 'Fehlende Rechte', None), 
						_translate('MainWindow', 
							'Sie haben nicht ausreichend Rechte!', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
					)
				else:
					log.warning('Unexpected error in protocol: %s' % (e,))
					QMessageBox.warning(
						self, _translate('MainWindow', 'Unbekannter Fehler', None), 
						_translate('MainWindow', 
							'Unbekannter Fehler in der Kommunikation mit dem Server aufgetreten.', 
							None),
						QMessageBox.Ok, QMessageBox.Ok
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
		act = QAction(
			QIcon(QPixmap(':actions/delete.png')), 
			_translate("MainWindow", "Löschen", None), self.ui.mailTable
		)
		act.triggered.connect(self.deleteCertificates)
		actions.append(act)
		self.ui.adminTable.setContextMenuPolicy(2)
		self.ui.adminTable.addActions(actions)

	def start(self):
		# load the data!
		self.splash.showMessage(_translate('SplashScreen', 'Starte Benutzeroberfläche...'), 10, color=QColor(255, 255, 255))
		self.app.processEvents()
		self.splash.finish(self)
		self.readSettings()
		self.show()

		# version changed?
		lastInstalledVersion = None
		try:
			lastInstalledVersion = conf.get('general', 'installedversion')
		except:
			pass

		if lastInstalledVersion is None or lastInstalledVersion != __version__:
			self.versionChanged.emit()
			if not conf.has_section('general'):
				conf.add_section('general')
			conf.set('general', 'installedversion', __version__)
			conf.save(fread)

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

	app = QApplication(sys.argv)
	app.installTranslator(cpTranslator.getTranslator())
	app.setQuitOnLastWindowClosed(False)
	ds = FLScpMainWindow(app)
	app.exec()
	os.kill(os.getpid(), 15)
	sys.exit(0)
