#                                               -*- Autoconf -*-
# Process this file with autoconf to produce a configure script.

AC_PREREQ([2.69])
AC_INIT([flscp], [0.7], [website-team@fls-wiesbaden.de])
AC_COPYRIGHT([Copyright 2014, Lukas Schreiner])

# rsync
AC_PATH_PROG([RSYNC], [rsync])

# python
AM_PATH_PYTHON([3.4])

# pyqt5
AC_MSG_CHECKING([for PyQt5 version >= 5.2])
prog="[import sys, string
try: import PyQt5
except ImportError: sys.exit(1)
from PyQt5.QtCore import *
if list(map(int, QT_VERSION_STR.split('.'))) < [5,2,0]: sys.exit(1)
if list(map(int, PYQT_VERSION_STR.split('.'))) < [5,2,0]: sys.exit(1)
sys.exit(0)]"
${PYTHON} -c "${prog}"
retval=$?

if test $retval -ne 0; then
    AC_MSG_RESULT([0])
    AC_MSG_FAILURE([cannot find PyQt5 support (>= 5.2)])
else:
    AC_MSG_RESULT([yes])
fi

# Test for PyQt5 developer tools

# Try to find PyQt5 tools through Python interpreter
prog="[import os, sys
from PyQt5.QtCore import QCoreApplication
app = QCoreApplication([])
path = app.applicationDirPath()
sys.stdout.write(path)]"

PYPATH=`${PYTHON} -c "${prog}"`

# On Cygwin hosts, the PATH does not seem to be correctly found
if test "$host_os" = cygwin ; then
    PYPATH=/usr/lib/python$PYTHON_VERSION/site-packages/PyQt5
fi

AC_ARG_VAR([PYUIC5], [PyQt5 user interfaces compiler])
AC_ARG_VAR([PYRCC5], [PyQt5 resources compiler])

# On MinGW hosts, pyuic4 is a batch file and cannot be run from MSYS.
# To bypass this issue, we launch pyuic4 through cmd.exe
# with a "standard" PATH.
# pyrcc5 does not need this trick as it is a standard executable.
if test "$host_os" = mingw32 ; then
    CMDPYUIC5="cmd //C $PYPATH/Lib/site-packages/PyQt5/pyuic5"
fi

if test "x$PYUIC5" = "x" ; then
    AC_PATH_PROG([PYUIC5], [pyuic5], [$CMDPYUIC5], [${PYPATH}:$PATH])
fi
if test "x$PYRCC5" = "x" ; then
    AC_PATH_PROG([PYRCC5], [pyrcc5], [], [${PYPATH}:$PATH])
fi

if test "x$PYUIC5" = "x" -o "x$PYRCC5" = "x" ; then
    AC_MSG_FAILURE([cannot find PyQt5 dev tools, Graphical User Interface cannot be installed])
    cs_have_gui=no
fi

# pyinotify
AC_MSG_CHECKING([for pyinotify])
prog="[import sys, string
try: import pyinotify
except ImportError: sys.exit(1)
sys.exit(0)]"
${PYTHON} -c "${prog}"
retval=$?

if test $retval -ne 0; then
    AC_MSG_RESULT([0])
    AC_MSG_FAILURE([cannot find pyinotify support])
else:
    AC_MSG_RESULT([yes])
fi

AC_CHECK_FUNCS([mkdir chmod])
# Checks for programs.

# Checks for libraries.

# Checks for header files.

# Checks for typedefs, structures, and compiler characteristics.

# Checks for library functions.

AC_CONFIG_FILES([Makefile])
AC_OUTPUT
