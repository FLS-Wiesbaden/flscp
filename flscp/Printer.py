#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: fenc=utf-8:ts=8:sw=8:si:sta:noet
# author: unknown

class Printer:
	def __init__ (self, printableClass):
		for name in dir(printableClass):
			if name is not "__abstractmethods__":
				value = getattr(printableClass, name)
				if  '_' not in str(name).join(str(value)):
					print('  .%s: %r' % (name, value))

