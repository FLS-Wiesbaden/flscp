#!/usr/bin/env python3
# -*- coding: utf8 -*-
# vim: fenc=utf-8:ts=8:sw=8:si:sta:noet
#
# @author Lukas Schreiner
#

import sys
from cx_Freeze import setup, Executable

files = [
	#'Microsoft.VC90.CRT.manifest',
	#'msvcr90.dll',
	#'msvcp90.dll',
	#'msvcm90.dll',
	#'build/flscpserver/server.ini'
	]

base = None
exeName = 'flscp'
exeDebug = 'flscp_debug'
if sys.platform == "win32":
	base = "Win32GUI"
	exeName = exeName + '.exe'
	exeDebug = exeDebug + '.exe'

flscp = Executable(
	"build/flscp/flscp.py",
	base = base,
	icon = "flscp/res/fls_logo_60.png",
	targetName = exeName,
	copyDependentFiles = True,
	appendScriptToExe = True,
	appendScriptToLibrary = True,
	compress = True
	)

flscp_debug = Executable(
	"build/flscp/flscp.py",
	base = None,
	icon = "flscp/res/fls_logo_60.png",
	targetName = exeDebug,
	copyDependentFiles = True,
	appendScriptToExe = True,
	appendScriptToLibrary = True,
	compress = False
	)

buildOpts = {
	'include_files': files,
	'copy_dependent_files': True,
	'append_script_to_exe': True,
	'packages': [
		'cryptography',
		'PyQt5',
		'pyinotify'
	]
}

setup(
	name = "FLS Control Panel",
	version = "0.7",
	description = "FLS Control panel Client",
	author = "Friedrich-List-Schule Wiesbaden",
	author_email = "website-team@fls-wiesbaden.de",
	url = "http://fls-wiesbaden.de",
	options = {'build_exe': buildOpts},
	executables = [flscp, flscp_debug]
)

