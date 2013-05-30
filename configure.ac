#                                               -*- Autoconf -*-
# Process this file with autoconf to produce a configure script.

AC_PREREQ([2.69])
AC_INIT([flscp], [0.1], [website-team@fls-wiesbaden.de])
AC_COPYRIGHT([Copyright 2013, Lukas Schreiner])

# rsync
AC_PATH_PROG([RSYNC], [rsync])

# python
AM_PATH_PYTHON([3.2])

# pyqt4
AC_MSG_CHECKING([for PyQt4 version >= 4.8])
prog="[import sys, string
try: import PyQt4
except ImportError: sys.exit(1)
from PyQt4.QtCore import *
if list(map(int, QT_VERSION_STR.split('.'))) < [4,8,0]: sys.exit(1)
if list(map(int, PYQT_VERSION_STR.split('.'))) < [4,8,0]: sys.exit(1)
sys.exit(0)]"
${PYTHON} -c "${prog}"
retval=$?

if test $retval -ne 0; then
    AC_MSG_RESULT([0])
    AC_MSG_FAILURE([cannot find PyQt4 support (>= 4.8)])
else:
    AC_MSG_RESULT([yes])
fi

# Test for PyQt4 developer tools

# Try to find PyQt4 tools through Python interpreter
prog="[import os, sys
from PyQt4.QtCore import QCoreApplication
app = QCoreApplication([])
path = app.applicationDirPath()
sys.stdout.write(path)]"

PYPATH=`${PYTHON} -c "${prog}"`

# On Cygwin hosts, the PATH does not seem to be correctly found
if test "$host_os" = cygwin ; then
    PYPATH=/usr/lib/python$PYTHON_VERSION/site-packages/PyQt4
fi

AC_ARG_VAR([PYUIC4], [PyQt4 user interfaces compiler])
AC_ARG_VAR([PYRCC4], [PyQt4 resources compiler])

# On MinGW hosts, pyuic4 is a batch file and cannot be run from MSYS.
# To bypass this issue, we launch pyuic4 through cmd.exe
# with a "standard" PATH.
# pyrcc4 does not need this trick as it is a standard executable.
if test "$host_os" = mingw32 ; then
    CMDPYUIC4="cmd //C $PYPATH/Lib/site-packages/PyQt4/pyuic4"
fi

if test "x$PYUIC4" = "x" ; then
    AC_PATH_PROG([PYUIC4], [pyuic4], [$CMDPYUIC4], [${PYPATH}:$PATH])
fi
if test "x$PYRCC4" = "x" ; then
    AC_PATH_PROG([PYRCC4], [pyrcc4], [], [${PYPATH}:$PATH])
fi

if test "x$PYUIC4" = "x" -o "x$PYRCC4" = "x" ; then
    AC_MSG_FAILURE([cannot find PyQt4 dev tools, Graphical User Interface cannot be installed])
    cs_have_gui=no
fi

AC_CHECK_FUNCS([mkdir chmod])
# Checks for programs.

# Checks for libraries.

# Checks for header files.

# Checks for typedefs, structures, and compiler characteristics.

# Checks for library functions.

AC_CONFIG_FILES([Makefile])
AC_OUTPUT
