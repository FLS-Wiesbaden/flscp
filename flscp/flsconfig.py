#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: fenc=utf-8:ts=8:sw=8:si:sta:noet
import configparser

class FLSConfig(configparser.ConfigParser):
	__instance = None

	def __init__(self):
		super().__init__()
		FLSConfig.__instance = self

	@staticmethod
	def getInstance():
		return FLSConfig.__instance
