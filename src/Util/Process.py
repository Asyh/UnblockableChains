import subprocess
import re
import os
import signal
import time
from .timeout import TimeoutException
from .timeout import Timeout
from .LogWrapper import *

l = LogWrapper.getDefaultLogger()

def runCommand(cmd_arr,
			   stdin=subprocess.PIPE,
			   stdout=subprocess.PIPE,
			   stderr=subprocess.PIPE,
               shell=False):


	proc = subprocess.Popen(
		cmd_arr,
		stdin=stdin,
		stdout=stdout,
		stderr=stderr,
		bufsize=1,
		shell=shell
	)

	return proc

def runCommandSync(cmd_arr,
			   stdin=subprocess.PIPE,
			   stdout=subprocess.PIPE,
			   stderr=subprocess.PIPE,
               shell=False):


	proc = subprocess.run(
		cmd_arr,
		stdin=stdin,
		stdout=stdout,
		stderr=stderr,
		bufsize=1,
		shell=shell
	)

	return proc


w2lRegex = re.compile(r'^(.+):')
def Win2LinuxPathConversion(path):
	def replacement(match):
		return "/mnt/" + match.group(1).lower()
	path = path.replace ('\\','/')
	path = w2lRegex.sub(replacement,path)
	return path



def wait_for_popen(proc, timeout=30):
	try:
		with Timeout(timeout) as _timeout:
			while proc.poll() is None:
				time.sleep(0.1)
				_timeout.check()
	except Timeout:
		pass


def kill_proc(proc):
	try:
		# sig 2 doesnt work on windows
		if os.name != 'nt' \
				and proc.poll() is None:
			try:
				proc.send_signal(signal.SIGINT)
				wait_for_popen(proc, 30)
			except KeyboardInterrupt:
				print(
					"Trying to close geth process.  Press Ctrl+C 2 more times "
					"to force quit"
				)
		if proc.poll() is None:
			try:
				proc.terminate()
				wait_for_popen(proc, 10)
			except KeyboardInterrupt:
				print(
					"Trying to close geth process.  Press Ctrl+C 1 more times "
					"to force quit"
				)
		if proc.poll() is None:
			proc.kill()
			wait_for_popen(proc, 2)
	except KeyboardInterrupt:
		proc.kill()


def format_error_message(prefix, command, return_code, stdoutdata, stderrdata):
	lines = [prefix]

	lines.append("Command	: {0}".format(' '.join(command)))
	lines.append("Return Code: {0}".format(return_code))

	if stdoutdata:
		lines.append("stdout:\n`{0}`".format(stdoutdata))
	else:
		lines.append("stdout: N/A")

	if stderrdata:
		lines.append("stderr:\n`{0}`".format(stderrdata))
	else:
		lines.append("stderr: N/A")

	return "\n".join(lines)


def waitFor(operation, emptyResponse=None, pollInterval=0.5, maxRetries=10):

	res = emptyResponse
	retries = -1
	while res == emptyResponse:
		#l.debug('trying',str(operation),'attempt',retries,'of',maxRetries)
		res = operation()

		time.sleep(pollInterval)
		retries +=1
		if retries > maxRetries:
			raise TimeoutException("Unable to get a response for "+str(operation)+". Perhaps destination is not responding?")

	l.debug("waiter",str(operation), 'executed in ', retries * pollInterval)
	return res

