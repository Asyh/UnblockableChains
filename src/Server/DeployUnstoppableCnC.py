import yaml
import os
import sys
import getpass
from os.path import join as opj , exists as exists
import logging
import yaml, ast, json
from solc import compile_source
from web3 import Web3, HTTPProvider
from web3.contract import ConciseContract
from Util.keys import *
from Util.EtherKeysUtil import *
from Util.Process import *
from Util.LogWrapper import *
import shutil
import signal
import atexit


l = LogWrapper.getLogger()

def deployContract (web3, conf):
	#with open ('UnstoppableCnC.sol') as f:
	with open (conf['contractUri']) as f:
		cs=f.read()

	compiled_sol = compile_source(cs) # Compiled source code
	contract_interface = compiled_sol['<stdin>:'+conf['contractName']]

	# Instantiate and deploy contract
	contract = web3.eth.contract(abi=contract_interface['abi'], bytecode=contract_interface['bin'])

	tx_hash = contract.deploy(transaction={'from': conf['ownerAddress'], 'gas':conf['gaslimit'] },
		args=(conf['ownerPublic'], conf['allowedAddresses']))
	l.debug('transaction deploy contract, tx_hash:',tx_hash)

	# Get tx receipt to get contract address
	tx_receipt = None
	while not tx_receipt:
		tx_receipt = web3.eth.getTransactionReceipt(tx_hash)
		time.sleep(1)
	contract_address = tx_receipt['contractAddress']
	l.info('contract successfully deployed: ',contract_address, 'gas Used:',tx_receipt['gasUsed'])
	l.debug(' abi:', contract_interface['abi'])

	conf['abi'] = contract_interface['abi']
	conf['contractDeployedAddress'] = contract_address

	# with (open(opj(conf['interfaceDir'],conf['contractName']+'.interface.yaml'),'w')) as f:
	# 	f.write(yaml.dump({'deployedAddress': contract_address,
	# 			   'abi': contract_interface['abi']}))

	# Contract instance in concise mode
	contract_instance = web3.eth.contract(contract_interface['abi'], contract_address,
										  ContractFactoryClass=ConciseContract)
	#contract_instance.owner()
	return contract_instance



'''
# Contract instance in concise mode
contract_instance = web3.eth.contract(contract_interface['abi'], contract_address, ContractFactoryClass=ConciseContract)
contract_instance.owner()
'''



def runGethNode(conf, freshStart = False):
	gethLockFile = opj(conf['BlockChainData'], 'LOCK.pid')
	if (os.path.isfile(gethLockFile)):
		with open (gethLockFile) as f:
			pid = f.read()
			if (pid):
				try:
					os.kill(int(pid), signal.SIGTERM)
					time.sleep (1)
					l.debug('Old geth was running at PID:',pid,'. Killed.')
				except OSError:
					pass #all good because process wasn't running anymore

	# genesis = conf['genesis']#ast.literal_eval()

	if conf['opMode'] == 'test':
		if freshStart:
			l.warning('Fresh start! removing blockchain dir ',conf['BlockChainData'])

			shutil.rmtree(conf['BlockChainData'],ignore_errors=True)

			l.debug('Generating genesis file. Preallocating some coins to owner ',conf['ownerAddress'],' balance')
			conf['genesis']['alloc'][conf['ownerAddress']] = { "balance": "300000000000000000" }
			conf['genesis']['coinbase'] = conf['ownerAddress']

			with open(conf['genesisFile'],'w') as f:
				json.dump(conf['genesis'],f, indent=1)

			l.info('Initializing blockchain...')
			cmd = [conf['geth'],'--datadir',conf['BlockChainData'],'init',conf['genesisFile'] ]

			l.debug('Running geth init: ' , ' '.join(cmd))
			with open(opj('logs', 'geth.server.log'), 'a') as f:
				proc = runCommand(cmd, stdout=f)
				proc.communicate()
	elif conf['opMode'] == 'TestNet':
		pass
	elif conf['opMode'] == 'RealNet':
		pass

	cmd = conf['gethCmd']
	cmd = [x.replace('%DATADIR%', conf['BlockChainData']) for x in cmd]
	cmd = [x.replace('%OWNERADDRESS%', conf['ownerAddress']) for x in cmd]
	l.info('Running geth node: cmd: ', ' '.join(cmd))
	proc = runCommand(cmd, stderr=open(opj('logs', 'geth.server.log'), 'a'))

	if proc.returncode:
		std,sterr = proc.communicate()
		raise ValueError(format_error_message("Error trying to run geth node",cmd,proc.returncode,std,sterr))

	time.sleep(3)


	with open(gethLockFile,'w') as f:
		f.write(str(proc.pid))
	l.info('Geth node running. PID:',str(proc.pid))

	return proc






def loadOrGenerateAccount(conf, regenerateOwnerAccount = False) -> bool:
	ownerChanged = False
	if not conf['ownerWallet'] or regenerateOwnerAccount:
		l.info("No account set. Generating a new account")
		conf['ownerWallet'],conf['ownerPublic'],conf['ownerPrivate'],conf['ownerAddress'] =  generateWallet(conf['keyGenScript'], conf['ownerWalletPassword'])

		l.info('Generated new owner wallet. Persisting changes to conf file')
		with open(opj('conf', 'deployment', 'DeploymentConf.GEN.Wallet.yaml'),'w') as f:
			yaml.safe_dump({'ownerWallet':conf['ownerWallet']}, f)

		ownerChanged = True
	else:
		l.info("Loading owner wallet...")
		conf['ownerPublic'], conf['ownerPrivate'], conf['ownerAddress'] = loadWallet(conf['ownerWallet'], conf['ownerWalletPassword'])

	l.info ('User Account Details:')
	l.info('\tPublic key:',conf['ownerPublic'])
	l.info('\tAddress:',conf['ownerAddress'])
	l.debug('\tPrivate key:',conf['ownerPrivate'])
	return ownerChanged



def generateClientsTemplates(web3, conf):
	confBase = yaml.safe_load(open(opj('conf', 'clientGen', 'ClientConf.BASE.yaml')))
	confBase['contract']['name'] = conf['contractName']
	confBase['contract']['abi'] = conf['abi']
	confBase['contract']['address'] = conf['contractDeployedAddress']

	if conf['opMode'] == 'test':
		with open(conf['genesisFile'], 'r') as f:
			confBase['genesis'] = json.load(f)
		# confBase['genesis'] = conf['genesis']

	confBase['enode'] = web3.admin.nodeInfo['enode']

	with open(opj('conf', 'clientGen', 'ClientConf.TEMPLATE.yaml'), 'w') as f:
		yaml.safe_dump(confBase, f)

def generateServerConf(web3, conf):
	serverConf = {}
	serverConf['contract'] = {}
	serverConf['contract']['name'] = conf['contractName']
	serverConf['contract']['abi'] = conf['abi']
	serverConf['contract']['address'] = conf['contractDeployedAddress']

	serverConf['nodeRpcUrl'] = conf['nodeRpcUrl']
	serverConf['ownerWalletPassword'] = conf['ownerWalletPassword']
	serverConf['ownerAddress'] = conf['ownerAddress']
	serverConf['keyGenScript'] = conf['keyGenScript']
	serverConf['instancesDbFile'] = conf['instancesDbFile']

	with open(opj('conf', 'server', 'ServerConf.yaml'), 'w') as f:
		yaml.safe_dump(serverConf, f)

def loadConf():
	confBase = yaml.safe_load(open(opj('conf', 'deployment', 'DeploymentConf.BASE.yaml')))
	cafile = opj('conf', 'deployment', 'DeploymentConf.GEN.Wallet.yaml')
	confAuto = yaml.safe_load(open(cafile)) if exists(cafile) else None
	conf = {**confBase, **(confAuto if confAuto else {})}
	return conf

if __name__ == "__main__":

	l.info ("base dir ",sys.argv[1])
	os.chdir(sys.argv[1])

	conf = loadConf()

	os.environ['SOLC_BINARY'] = opj(os.getcwd(), conf['solc'])

	#Loading/Generating new account for the owner of the contract
	ownerChanged = loadOrGenerateAccount(conf,regenerateOwnerAccount = False)


	gethProc = runGethNode(conf, ownerChanged)

	# atexit.register(
	# 	lambda : kill_proc(gethProc))

	#Connecting to the get Node
	web3 = Web3(HTTPProvider(conf['nodeRpcUrl']))

	l.info("Node is up at:", web3.admin.nodeInfo.enode)
	l.debug("Staring miners...")
	web3.miner.start(1)#For some reason geth doensnt auto start miners...8|
	#time.sleep(5) #let mining works for few seconds...
	#Registering the owner account to the node, unlocking the account.
	importAccountToNode(web3, conf['ownerAddress'], conf['ownerPrivate'], conf['ownerWalletPassword'])

	#deploying the contract to the blockchain
	contract = deployContract (web3, conf)

	#Generating templates with information need for generating a self contained client.
	generateClientsTemplates (web3,conf)

	generateServerConf(web3, conf)