#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# author: Lukas Schreiner
from PyQt4.QtCore import QTranslator
from PyQt4.QtGui import QApplication
import os.path

class CPTranslator:

	def __init__(self, qmPath, language = 'de_DE'):
		self.l18Path = os.path.abspath(qmPath)
		self.language = language
		self.translator = QTranslator()

		self.loadDictionary()

	def getTranslator(self):
		return self.translator

	def loadDictionary(self):
		self.translator.load('%s.po' % (self.language,), self.l18Path)

	def changeLanguage(self, language):
		self.language = language
		self.loadDictionary()

	def pyTranslate(self, context, sourceText, disambiguation = None, params = None):
		txt = QApplication.translate(context, sourceText, disambiguation, QApplication.UnicodeUTF8)
		if params is not None:
			return txt.format(params)
		else:
			return txt
