#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: fenc=utf-8:ts=8:sw=8:si:sta:noet
import os
import os.path
import copy
from xml.dom import minidom

class Message:

	def __init__(self, line, context, source, translation = None):
		self.line = line
		self.context = context
		self.source = source
		self.translation = translation
		self.comment = []

		self.foundIn = {}

	def addSource(self, fileName, line, comment = None):
		if fileName not in self.foundIn.keys():
			self.foundIn[fileName] = []

		if comment is not None and len(comment) > 0:
			for c in comment:
				if c is not None:
					self.comment.append(c)

		self.foundIn[fileName].append(line)

	def removePySources(self):
		keysToRemove = []
		for key in self.foundIn.keys():
			if key.endswith('.py'):
				keysToRemove.append(key)

		for key in keysToRemove:
			del(self.foundIn[key])

	def hasSources(self):
		found = False

		for fpath, flines in self.foundIn.items():
			if len(flines) > 0:
				found = True
				break

		return found

	def getSource(self):
		t = minidom.Text()
		t.data = self.source
		return t.toxml()

	def getTranslation(self):
		t = minidom.Text()
		t.data = self.translation
		return t.toxml()


class PythonFile:

	def __init__(self, path):
		self.path = path
		self.absPath = os.path.abspath(path)
		self.messages = []

	def parse(self):
		content = []
		with open(self.absPath, 'rb') as f:
			content = f.read().decode('utf-8').replace('\r\n', '\n').split('\n')

		lineOfTranslate = 0
		translateLine = ''
		translationList = []
		inTranslate = False
		openBraces = 0
		strState = None
		i = 0
		for line in content:
			i += 1
			if '_translate(' in line and not 'def _translate(' in line: 
				inTranslate = True
				lineOfTranslate = i
				# a translation starts here.
				# get the start position
				strIndex = line.index('_translate(')
				# now we have to go through each character
				strState = None
				openBraces = 0
				for f in line[strIndex+11:]:
					if strState is None and f in ['\'', '"']:
						strState = f
					elif strState is not None and strState == f:
						strState = None
					elif strState is not None:
						translateLine += f
					elif strState is None and f == ',' and openBraces == 0:
						translationList.append(translateLine)
						translateLine = ''
					elif f == '(' and strState == None:
						translateLine += f
						openBraces += 1
					elif f == ')' and strState == None:
						openBraces -= 1
						if openBraces < 0:
							translationList.append(translateLine)
							self.parseMessage(lineOfTranslate, translationList)
							translateLine = ''
							lineOfTranslate = 0
							translationList = []
							inTranslate = False
							strState = None
							# we are at the end. 
							break
						else:
							translateLine += f
					elif f == '\n' or (f == '+' and strState is None):
						if f == '+' and strState is None:
							# than we had add the last line already to the list. 
							translationLine = translationList[len(translationList)-1]
							translationList.remove(translationLine)
						# we have to read in the next line ;)
					elif f != ' ' or (f == ' ' and strState is not None):
						translateLine += f
			elif inTranslate:
				# we are in translate statement. It's one of the next line. 
				# Remove the leading spaces and tabs.
				line = line.lstrip()
				for f in line:
					if strState is None and f in ['\'', '"']:
						strState = f
					elif strState is not None and strState == f:
						strState = None
					elif strState is not None:
						translateLine += f
					elif strState is None and f == ',' and openBraces == 0:
						translationList.append(translateLine)
						translateLine = ''
					elif f == '(' and strState == None:
						translateLine += f
						openBraces += 1
					elif f == ')' and strState == None:
						openBraces -= 1
						if openBraces < 0:
							translationList.append(translateLine)
							self.parseMessage(lineOfTranslate, translationList)
							lineOfTranslate = 0
							translationList = []
							translateLine = ''
							inTranslate = False
							# we are at the end. 
							break
						else:
							translateLine += f
					elif f == '\n' or (f == '+' and strState is None):
						# we have to read in the next line ;)
						pass
					elif f != ' ' or (f == ' ' and strState is not None):
						translateLine += f

	def parseMessage(self, line, translateLine):
		print('I have to create something for [%s] from line %s' % (translateLine, str(line),))
		try:
			context, msg, disambig = translateLine
		except:
			context, msg = translateLine
			disambig = None
			
		if disambig == 'None':
			disambig = None
		m = Message(line, context, msg)
		if disambig is not None:
			m.comment.append(disambig)
		self.messages.append(m)

class LinguistFileUpdater:
	
	def __init__(self, fileList, sourceLanguage, targetLanguage, targetFile, codec):
		self.originalFileList = fileList
		self.sourceLanguage = sourceLanguage
		self.targetLanguage = targetLanguage
		self.targetFile = targetFile
		self.targetFolder = os.path.abspath(os.path.dirname(self.targetFile))
		self.codec = codec
		self.fileList = []
		self.msgList = []
		self.originalMsgList = []

	def parse(self):
		self.findTranslateFiles()
		self.loadTarget()

		for f in self.fileList:
			f.parse()

		# now all files are finished. 
		# We have to look for duplicate messages and to merge them. 
		self.msgList = []
		for f in self.fileList:
			for m in f.messages:
				idx = self.findMessage(m)
				# fix the path...
				path = self.getRelativePath(f.absPath)

				if idx >= 0:
					self.msgList[idx].addSource(path, m.line, m.comment)
				else:
					m.addSource(path, m.line)
					self.msgList.append(m)

		print('Have found %s translation items in %s files!' % (len(self.msgList), len(self.fileList)))
		self.merge()
		print('After merge: %s translation items' % (len(self.msgList), ))

	def merge(self):
		pyMsgList = copy.copy(self.msgList)
		newMsgList = []

		for msg in self.originalMsgList:
			msg.removePySources()
			# now lets search for py things
			for pymsg in pyMsgList:
				if msg.context == pymsg.context and msg.source == pymsg.source:
					for fpath, flines in pymsg.foundIn.items():
						for line in flines:
							msg.addSource(fpath, line)
					pyMsgList.remove(pymsg)

			if msg.hasSources():
				newMsgList.append(msg)

		for msg in pyMsgList:
			newMsgList.append(msg)

		self.msgList = newMsgList

	def findMessage(self, msg):
		index = -1

		i = 0
		for m in self.msgList:
			if m.context == msg.context and m.source == msg.source:
				index = i
				break
			i += 1

		return index

	def getRelativePath(self, filePath):
		targetFolder = self.targetFolder.split('/')
		filePath = filePath.split('/')
		i = 0
		for elm in filePath:
			if elm == targetFolder[i]:
				i += 1
			else:
				break

		targetFolder = targetFolder[i:]
		filePath = filePath[i:]
		backLevels = len(targetFolder)

		while backLevels > 0:
			filePath.insert(0, '..')
			backLevels -= 1

		return '/'.join(filePath)

	def findTranslateFiles(self):
		for f in self.originalFileList:
			if os.path.isdir(f):
				self.findFiles(f)
			else:
				if not self.hasFileAlready(f):
					self.fileList.append(PythonFile(f))

	def findFiles(self, folder):
		for root, dirs, files in os.walk(folder):
			for name in files:
				if name.endswith('.py') and not self.hasFileAlready(os.path.join(root, name)):
					self.fileList.append(PythonFile(os.path.join(root, name)))
			for name in dirs:
				self.findFiles(os.path.join(root, name))

	def hasFileAlready(self, fileName):
		fileName = os.path.abspath(fileName)
		for f in self.fileList:
			if f.absPath == fileName:
				return True

		return False	

	def loadTarget(self):
		if os.path.exists(self.targetFile):
			dom = minidom.parse(self.targetFile)
			for context in dom.getElementsByTagName('context'):
				contextName = None
				messages = []
				for child in context.childNodes:
					if child.nodeName == '#text':
						continue
					elif child.nodeName == 'name':
						contextName = child.childNodes[0].nodeValue
					elif child.nodeName == 'message':
						msg = self.parseXmlMessage(child)
						if msg is not None:
							messages.append(msg)

				if len(messages) > 0 and contextName is not None:
					for m in messages:
						m.context = contextName
						self.originalMsgList.append(m)

	def parseXmlMessage(self, message):
		m = Message(0, '', 'xml', translation = None)

		for child in message.childNodes:
			if child.nodeName == '#text':
				continue
			elif child.nodeName == 'location':
				m.addSource(child.getAttribute('filename'), int(child.getAttribute('line')))
			elif child.nodeName == 'source':
				m.source = child.childNodes[0].nodeValue
			elif child.nodeName == 'translation':
				if child.hasAttribute('type') and child.getAttribute('type') == 'unfinished':
					m.translate = None
				else:
					if len(child.childNodes) <= 0:
						m.translate = ''
					else:
						m.translate = child.childNodes[0].nodeValue
			elif child.nodeName == 'comment':
				for txtChild in child.childNodes:
					if txtChild is not None:
						m.comment.append(txtChild.nodeValue)

		return m

	def write(self):
		groupedMsgList = {}
		for f in self.msgList:
			if f.context not in groupedMsgList.keys():
				groupedMsgList[f.context] = []

			groupedMsgList[f.context].append(f)

		content = []
		content.append('<?xml version="1.0" encoding="%s"?>' % (self.codec,))
		content.append('<!DOCTYPE TS>')
		content.append('<TS version="2.0" language="%s" sourcelanguage="%s">' % (self.targetLanguage, self.sourceLanguage))
		content.append('<defaultcodec>%s</defaultcodec>' % (self.codec,))

		for group in groupedMsgList.keys():
			content.append('<context>')
			content.append('\t<name>%s</name>' % (group,))
			for message in groupedMsgList[group]:
				content.append('\t<message>')
				for fileName, lineList in message.foundIn.items():
					for line in lineList:
						content.append('\t\t<location filename="%s" line="%s"/>' % (fileName, line))
				content.append('\t\t<source>%s</source>' % (message.getSource(),))
				if message.translation is None:
					content.append('\t\t<translation type="unfinished"></translation>')
				else:
					content.append('\t\t<translation>%s</translation>' % (message.getTranslation(),))
				# do we have some comments?
				if message.comment is not None and len(message.comment) > 0:
					print(message.comment)
					content.append('\t\t<comment>%s</comment>' % ('\n'.join(message.comment),))
				content.append('\t</message>')
			content.append('</context>')
		content.append('</TS>')

		content.append('')

		with open(self.targetFile, 'wb') as f:
			f.write(('\n'.join(content)).encode('utf-8'))


if __name__ == '__main__':
	import argparse
	parser = argparse.ArgumentParser(description='Update/Create translation file for qt from python sources.')
	parser.add_argument('files', metavar='N', type=str, nargs='+', 
		help='List of files (*.py) or directories')
	parser.add_argument('-source-language', required=True, dest='sourceLang', type=str, 
		help='Set the source language')
	parser.add_argument('-target-language', required=True, dest='targetLang', type=str, 
		help='Set the target language')
	parser.add_argument('-ts', dest='targetFile', required=True, type=str, help='Set the output file')
	parser.add_argument('-codecfortr', required=True, dest='codec', type=str, help='Set the codec')
	
	args = parser.parse_args()
	lfu = LinguistFileUpdater(args.files, args.sourceLang, args.targetLang, args.targetFile, args.codec)
	lfu.parse()
	lfu.write()
