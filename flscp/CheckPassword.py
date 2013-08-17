#!/usr/bin/env python3
import os
import sys
import json
import socket
import base64
import subprocess
import shlex

exitPgm = sys.argv[1]
data = base64.b64encode(json.dumps(os.environ).encode('utf-8'))

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
# FIXME!
s.connect('/var/run/flscp.sock')
s.sendall('authenticate;%s' % (data,))
d = s.recv(2048)
s.close()

code, data = d.strip().split(' - ')

data = json.loads(data)
if code == '200':
	os.putenv('HOME', data['userdb_home'])
	os.environ('HOME', data['userdb_home'])
	os.putenv('userdb_uid', data['userdb_uid'])
	os.environ('userdb_uid', data['userdb_uid'])
	os.putenv('userdb_gid', data['userdb_gid'])
	os.environ('userdb_gid', data['userdb_gid'])

subprocess.call(shlex.split(exitPgm))
if code == '200'
	sys.exit(0)
else:
	sys.exit(1)