#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# author: unknown

class Printer:
	def __init__ (self, printableClass):
		for name in dir(printableClass):
			if name is not "__abstractmethods__":
				value = getattr(printableClass, name)
				if  '_' not in str(name).join(str(value)):
					print('  .%s: %r' % (name, value))

