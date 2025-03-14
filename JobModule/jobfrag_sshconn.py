import select
import time
import PythonTools.LoggingMgr as LoggingMgr
import paramiko
from pprint import pprint

DEBUG_MODE = False
def get_private_key(logFUNC,privateKEY):
    try:
        return paramiko.RSAKey.from_private_key_file(privateKEY)
    except paramiko.SSHException:
        logFUNC(f'[PrivateKeyNotFound] Path "{privateKEY}" is not a valid private key')

def IsActivate(sshCLIENT):
    if sshCLIENT == None: return False
    if sshCLIENT.get_transport() == None: return False
    if sshCLIENT.get_transport().is_active() == False: return False
    return True


def execute_command_with_timeout(ssh_client, logOUT, logERR, command, timeout):
    """
    Execute a command on the SSH server with a timeout for output.
    
    :param ssh_client: The Paramiko SSHClient object.
    :param command: The command to execute on the server.
    :param timeout: Timeout in seconds to wait for output.
                    If no any message found, the code keeps listening the next message.
                    timeout value used to prevent the code stucked on listening.
                    You can add additional function executing when waiting for the result.
                    Also, not to put time.sleep() when you are listening the next message.
    :return: nothing
    """

    try:
        logOUT.info(f'Send command "{ command }" to remote site')
        stdin, stdout, stderr = ssh_client.exec_command(command)


        # Monitor both stdout and stderr in real-time
        while True:
            if not IsActivate(ssh_client):
                logERR.warning('[Abort] SSH Connection was closed. Abort current job')
                break

            # Use select to wait for either stream to have data
            ready_channels, _, _ = select.select([stdout.channel, stderr.channel], [], [], timeout)


            if not ready_channels:  # Timeout, no data yet
                continue

            for channel in ready_channels:
                if channel.recv_ready():  # Data in stdout
                    logOUT.info(channel.recv(1024).decode().strip())
                if channel.recv_stderr_ready():  # Data in stderr
                    logERR.info(channel.recv_stderr(1024).decode().strip())

            # Exit the loop if the command is finished and streams are empty
            if stdout.channel.exit_status_ready() and stdout.channel.recv_exit_status() == 0:
                logOUT.info(f'finished function execute_command_monitoring')
                return
    except Exception as e:
        logERR.info(f"An error occurred: {e}")
        if DEBUG_MODE: raise

def test_direct_run():
    stdout_err_mesg_filter = LoggingMgr.ErrorMessageFilter()
    stderr_err_mesg_filter = LoggingMgr.ErrorMessageFilter( [
            LoggingMgr.errortype('Type1Err', 0, '[running] 1'),
            LoggingMgr.errortype('Type3Err', 0, '[running] 3'),
        ])
    #global log_stdout, log_stderr
    log_stdout = LoggingMgr.configure_logger('out', 'log_stdout.txt', stdout_err_mesg_filter)
    log_stderr = LoggingMgr.configure_logger('err', 'log_stderr.txt', stderr_err_mesg_filter)



    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    
    pkey = get_private_key(log_stdout.info,'/Users/noises/.ssh/toNTU8')
    ssh_client.connect(hostname="ntugrid8.phys.ntu.edu.tw", username="ltsai", pkey = pkey)

    command = 'python3 -u main_job.py'
    #command = 'python3 -u main_job.py 1>&2'
    #command = 'sh main_job.sh 1>&2'
    execute_command_with_timeout(ssh_client, log_stdout, log_stderr, command, timeout=1)

    log_stdout.info('SSH client closed')
    ssh_client.close()
    log_stdout.info('end of test_direct_run()')

import JobModule.jobfrag_base as jobfrag_base
class JobFrag(jobfrag_base.JobFragBase):
    def __init__(self, hostNAME:str, userNAME:str, privateKEYfile:str, timeOUT:float,
                 stdOUT, stdERR,
                 cmdTEMPLATEs:dict, argCONFIGs:dict, argSETUPs:dict):

        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.pkey = get_private_key(stdOUT.info, privateKEYfile)
        self.user = userNAME
        self.host = hostNAME
        self.timeout = timeOUT

        self.log = stdOUT
        self.err = stdERR

        self.set_cmd_template(cmdTEMPLATEs)
        self.set_config(argCONFIGs)
        self.set_config_const(argSETUPs)
    def __del__(self):
        cmd_del = self.get_full_command_from_cmd_template('del')
        if cmd_del:
            try:
                self.ssh_client.connect(hostname=self.host, username=self.user, pkey=self.pkey)
                execute_command_with_timeout(self.ssh_client,
                                            self.log, self.err,
                                            cmd_del, timeout = 0.4)
            except Exception as e:
                self.err.error(f'Unable to send cmd "del":"{ cmd_del }" to server')
                self.err.error(e)
                if DEBUG_MODE: raise
            finally:
                self.ssh_client.close()

    def Initialize(self):
        try:
            self.ssh_client.connect(hostname=self.host, username=self.user, pkey=self.pkey)
            execute_command_with_timeout(self.ssh_client,
                                         self.log, self.err,
                                         self.get_full_command_from_cmd_template('init'), timeout = 0.4)
            execute_command_with_timeout(self.ssh_client,
                                         self.log, self.err,
                                         'echo FINISHED', timeout = 0.4)
        except Exception as e:
            self.err.error(f'Unexpected Error')
            self.err.error(e)
            if DEBUG_MODE: raise
        finally:
            self.ssh_client.close()
    def Configure(self, updatedCONF:dict) -> bool:
        '''
        Update old argument config only if all configs in old argument config being confirmed.
        If there are some redundant key - value pair in updatedCONF, these configs are ignored.

        updatedCONF: dict. It should have the same format with original arg config
        '''
        for key, value in updatedCONF.items():
            error_mesg = self.set_config_value(key,value)
            if error_mesg:
                self.err.warning(f'[{error_mesg}] Invalid configuration from config: key "{ key }" and value "{ value }".')
                return False
        return True


        
    def Run(self):
        try:
            self.ssh_client.connect(hostname=self.host, username=self.user, pkey=self.pkey)

            if IsActivate(self.ssh_client):
                execute_command_with_timeout(self.ssh_client,
                                            self.log, self.err,
                                            self.get_full_command_from_cmd_template('run'), timeout = 0.4)
            if IsActivate(self.ssh_client):
                execute_command_with_timeout(self.ssh_client,
                                            self.log, self.err,
                                            'echo FINISHED', timeout = 0.4)
            else:
                self.err.warning('[ExternalTerminated] Run() is terminated from external signal')
            
        except Exception as e:
            self.err.error(f'Unexpected Error')
            self.err.error(e)
            if DEBUG_MODE: raise
        finally:
            self.ssh_client.close()
    def Stop(self):
        while IsActivate(self.ssh_client):
            self.ssh_client.close()
            time.sleep(0.2)


def test_jobunit():
    host = 'ntugrid8.phys.ntu.edu.tw'
    user = 'ltsai'
    pkey = '/Users/noises/.ssh/toNTU8'
    
    #### configure the status output
    stdout_filter = LoggingMgr.ErrorMessageFilter([
            LoggingMgr.errortype_exact('Type0Err', 0, '[running] 0'),
            LoggingMgr.errortype_contain('Type3Err', 0, '[running] 3'),

            LoggingMgr.errortype_exact('idle', 0, 'FINISHED'),
            ])
    stderr_filter = LoggingMgr.ErrorMessageFilter( [
            LoggingMgr.errortype_exact('Type1Err', 0, '[running] 1'),
            LoggingMgr.errortype_contain('Type3Err', 0, '[running] 3'),
            LoggingMgr.errortype_contain('RaiseErr', 0, 'Error'),

        ])
    log_stdout = LoggingMgr.configure_logger('out', 'log_stdout.txt', stdout_filter)
    log_stderr = LoggingMgr.configure_logger('err', 'log_stderr.txt', stderr_filter)

    cmd_template = {
        'init': 'echo "connection established"',
        'run': 'python3 -u main_job.py; echo "config: {prefix}"',
        'stop': '',
        'del': ''
    }
    arg_config = {
        'prefix': 'default',
    }
    arg_const_config = {
            'ip2': 'ntugrid5.phys.ntu.edu.tw'
    }
    timeout = 0.4

    job_frag = JobFrag(
            host, user, pkey, timeout,
            log_stdout, log_stderr,
            cmd_template, arg_config, arg_const_config) # asdf

    job_frag.Initialize()
    job_frag.Configure( {'prefix': 'confiugred'} )
    job_frag.Run()


def YamlConfiguredJobFrag(yamlLOADEDdict:dict):
    config = yamlLOADEDdict
    try:
        #### configure the status output
        log_config = config['logging']['stdout']
        stdout_filter_rules = [ LoggingMgr.errortype_factory(c['filter_method'], c['indicator'],c['threshold'],c['pattern']) for c in log_config['filters'] ]
        stdout_filter = LoggingMgr.ErrorMessageFilter(stdout_filter_rules)
        log_stdout = LoggingMgr.configure_logger(log_config['name'],log_config['file'], stdout_filter)

        log_config = config['logging']['stderr']
        stderr_filter_rules = [ LoggingMgr.errortype_factory(c['filter_method'], c['indicator'],c['threshold'],c['pattern']) for c in log_config['filters'] ]
        stderr_filter = LoggingMgr.ErrorMessageFilter(stderr_filter_rules)
        log_stderr = LoggingMgr.configure_logger(log_config['name'],log_config['file'], stderr_filter)

        basic_pars = config['basic_parameters']
        cmd_templates = config['cmd_templates']
        cmd_arguments = config['cmd_arguments']
        cmd_const_arguments = config['cmd_const_arguments']
        job_frag = JobFrag(
                basic_pars['host'], basic_pars['user'], basic_pars['pkey'], basic_pars['timeout'],
                log_stdout, log_stderr,
                cmd_templates, cmd_arguments, cmd_const_arguments
        )
    except KeyError as e:
        raise KeyError(f'Invalid key in yaml config "{ config }"') from e

    return job_frag
def test_YamlConfiguredJobFrag():
    yaml_content = '''
basic_parameters:
  timeout: 0.4
  host: 'ntugrid8.phys.ntu.edu.tw'
  user: 'ltsai'
  pkey: '/Users/noises/.ssh/toNTU8'
cmd_templates:
  'init': 'echo "connection established"'
  'run': 'python3 -u main_job.py; echo "config: {prefix}", echo "additional config: {ip2}"'
  'stop': 'exit'
  'del': ''
cmd_arguments:
  prefix: default
cmd_const_arguments:
  ip2: ntugrid5.phys.ntu.edu.tw
logging:
  stdout:
    name: out
    file: log_stdout.txt
    filters:
      - indicator: running
        threshold: 0
        pattern: 'RUNNING'
        filter_method: exact
      - indicator: Type0ERROR
        threshold: 0
        pattern: '[running] 0'
        filter_method: exact
      - indicator: Type3ERROR
        threshold: 0
        pattern: '[running] 3'
        filter_method: contain
      - indicator: idle
        threshold: 0
        pattern: 'FINISHED'
        filter_method: exact
  stderr:
    name: err
    file: log_stderr.txt
    filters:
      - indicator: running
        threshold: 0
        pattern: 'RUNNING'
        filter_method: exact
      - indicator: Type0ERROR
        threshold: 0
        pattern: '[running] 0'
        filter_method: exact
      - indicator: RaiseError
        threshold: 0
        pattern: 'Error'
        filter_method: contain
        '''

    with open('the_conf.yaml','w') as f:
        f.write(yaml_content)
    import yaml
    with open('the_conf.yaml','r') as f:
        loaded_conf = yaml.safe_load(f)

    job_frag = YamlConfiguredJobFrag(loaded_conf)
    job_frag.Initialize()
    job_frag.Configure( {'prefix': 'confiugred'} )
    job_frag.Run()
if __name__ == "__main__":
    test_direct_run()
    exit()
    test_jobunit()
    exit()
    test_YamlConfiguredJobFrag()
