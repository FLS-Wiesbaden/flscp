import logging
import os, os.path
import subprocess
import shlex

def hashPostFile(postFile, postMap):
	if not os.path.exists(postFile):
		return False

	log = logging.getLogger('flscp')

	state = True
	cmd = shlex.split('%s %s' % (postMap, postFile))
	with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
		out = p.stdout.read()
		err = p.stderr.read()
		if len(out) > 0:
			log.info(out)
		if len(err) > 0:
			log.warning(err)
			state = False

	return state