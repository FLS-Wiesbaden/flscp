import abc
from PyQt4.QtCore import pyqtSignal, QObject, pyqtSlot

class ObserverNotifier(QObject):
	sigNotification = pyqtSignal(str)

	def __init__(self):
		super(ObserverNotifier, self).__init__()

class ObservableSubject:

	def __init__(self):
		self._observer = []
		self._notifier = ObserverNotifier()

	def addObserver(self, observer):
		if hasattr(observer, 'notification'):
			if observer not in self._observer:
				self._observer.append(observer)
				self._notifier.sigNotification.connect(observer._notifyReceiver.notification)
			else:
				raise ValueError('Observer is already observing the subject!')
		else:
			raise ValueError('Observer have to have special methods!')

	def removeObserver(self, observer):
		if observer in self._observer:
			self._observer.remove(observer)
		else:
			raise ValueError('Observer is not observing subject !?')

	def notify(self, state):
		self._notifier.sigNotification.emit(state)
		#for f in self._observer:
		#	f.notification(state)

class NotifyReceiver(QObject):

	def __init__(self, obj):
		super(NotifyReceiver, self).__init__()
		self._obj = obj

	@pyqtSlot(str)
	def notification(self, state):
		self._obj.notification(state)

class Observer(metaclass=abc.ABCMeta):
	def __init__(self):
		self._notifyReceiver = NotifyReceiver(self)

	@abc.abstractmethod
	def notification(self, state):
		pass
