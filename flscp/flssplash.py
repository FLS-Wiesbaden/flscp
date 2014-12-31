#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: fenc=utf-8:ts=8:sw=8:si:sta:noet
from PyQt5.QtWidgets import QSplashScreen, QProgressBar
from PyQt5.QtGui import QPixmap

class CpSplashScreen(QSplashScreen):

	def __init__(self, parent = None, pixmap = None, maxSteps = 1):
		super().__init__(parent, pixmap)
		self.maxSteps = maxSteps
		self.progress = QProgressBar(self)
		#self.progress.setGeometry(15, 15, 100, 10)
		self.progress.setTextVisible(False)
		self.progress.setMinimum(0)
		self.progress.setMaximum(self.maxSteps)
		self.progress.setValue(0)
		self.progress.hide()

	def show(self):
		super().show()
		geo = self.geometry()
		self.progress.setGeometry(5, geo.height() - 20, 100, 10)
		self.progress.show()

	def showMessage(self, msg, step = None, color = None):
		if step is not None:
			self.progress.setValue(step)
			self.progress.update()
		super().showMessage(msg, color=color)
