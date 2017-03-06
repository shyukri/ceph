'''
Task to deploy clusters with DeepSea
'''
import logging

from teuthology.config import config as teuth_config
from teuthology.exceptions import CommandFailedError
from teuthology.repo_utils import fetch_repo
from teuthology import misc
from teuthology.orchestra import run
from teuthology.salt import Salt
from teuthology.task import Task
from util import get_remote_for_role

log = logging.getLogger(__name__)

class DeepSea(Task):

    def __init__(self, ctx, config):
        super(DeepSea, self).__init__(ctx, config)
        try:
            self.master = self.config['master']
        except KeyError:
            raise ConfigError('deepsea requires a master role')

        # set remote name for salt to pick it up. Setting the remote itself will
        # crash the reporting tool since it doesn't know how to turn the object
        # into a string

        self.config["master_remote"] = get_remote_for_role(self.ctx,
                self.master).name
        self.salt = Salt(self.ctx, self.config)

    def setup(self):
        super(DeepSea, self).setup()

        self.cluster_name, type_, self.master_id = misc.split_role(self.master)

        if type_ != 'master':
            msg = 'master role ({0}) must be a master'.format(self.master)
            raise ConfigError(msg)

        self.log.info("master remote: {}".format(self.config["master_remote"]))

        self.salt.master_remote.run(args=[
            'git',
            'clone',
            'https://github.com/SUSE/DeepSea.git',
            run.Raw(';'),
            'cd',
            'DeepSea',
            run.Raw(';'),
            'git',
            'checkout',
            'master',
            run.Raw(';'),
            'sudo',
            'make',
            'install',
            ])

        self.salt.master_remote.run(args = ['sudo', 'salt-key', '-L'])

        for _remote, roles_for_host in self.ctx.cluster.remotes.iteritems():
            _remote.run(args = ['sudo', 'systemctl', 'status',
                'salt-minion.service'])
            _remote.run(args = ['sudo', 'cat', '/etc/salt/minion_id'])
            _remote.run(args = ['sudo', 'cat', '/etc/salt/minion.d/master.conf'])

        self.salt.ping_minions()

    def begin(self):
        super(DeepSea, self).begin()
        self.test_stage_1_to_3()

    def end(self):
        super(DeepSea, self).end()

    def test_stage_1_to_3(self):
        self.__emulate_stage_0()
        self.__stage1()
        self.salt.master_remote.run(args = [
            'sudo',
            'ls',
            '-lisa',
            '/srv/pillar/ceph/proposals/'
            ])
        self.__map_roles_to_policy_cfg()
        self.salt.master_remote.run(args = [
            'sudo',
            'cat',
            '/srv/pillar/ceph/proposals/policy.cfg'
            ])
        self.salt.master_remote.run(args = [
            'sudo',
            'cat',
            '/srv/pillar/ceph/proposals/config/stack/default/ceph/cluster.yml'
            ])
        self.__stage2()
        # self.__add_public_interfaces()
        self.__stage2()
        self.salt.master_remote.run(args = [
            'sudo',
            'salt',
            self.salt.master_remote.hostname,
            'pillar.items'
            ])
        self.salt.master_remote.run(args = [
            'sudo',
            'cat',
            '/srv/pillar/ceph/stack/default/ceph/cluster.yml'
            ])
        self.salt.master_remote.run(args = [
            'sudo',
            'cat',
            '/srv/pillar/ceph/stack/default/ceph/ceph_conf.yml'
            ])
        self.salt.master_remote.run(args = [
            'sudo',
            'cat',
            '/srv/pillar/ceph/stack/ceph/ceph_conf.yml'
            ])
        self.__stage3()
        self.salt.master_remote.run(args = [
            'sudo',
            'ceph',
            '-s'
            ])
        # misc.wait_until_healthy(self.ctx, self.salt.master_remote)

    def __emulate_stage_0(self):
        '''
        stage 0 might reboot nodes. To avoid this for now lets emulate most parts of
        it
        '''
        # TODO target only G@job_id: $job_id
        self.salt.master_remote.run(args = [
            'sudo', 'salt', '*', 'state.apply', 'ceph.sync',
            run.Raw(';'),
            'sudo', 'salt', '*', 'state.apply', 'ceph.mines',
            run.Raw(';'),
            'sudo', 'salt', '*', 'state.apply', 'ceph.packages.common',
            # don't check status...returns 11 despite seeming to succeed
            ], check_status = False)

    def __stage1(self):
        self.salt.master_remote.run(args = [
            'sudo', 'salt-run', '-l', 'debug', 'state.orch', 'ceph.stage.1'])

    def __stage2(self):
        self.salt.master_remote.run(args = [
            'sudo', 'salt-run', '-l', 'debug', 'state.orch', 'ceph.stage.2'])

    def __stage3(self):
        self.salt.master_remote.run(args = [
            'sudo', 'salt-run', 'state.orch', 'ceph.stage.3'])

    def __map_roles_to_policy_cfg(self):
        # TODO this should probably happen in a random tmp dir...look in misc
        policy_cfg = ['cluster-ceph/cluster/*.sls',
                    'config/stack/default/global.yml',
                    'config/stack/default/ceph/cluster.yml',
                    'role-master/cluster/{}.sls'.format(self.salt.master_remote.hostname)]
        for _remote, roles_for_host in self.ctx.cluster.remotes.iteritems():
            nodename = _remote.hostname
            for role in roles_for_host:
                if(role.startswith('osd')):
                    log.debug('{} will be an OSD'.format(nodename))
                    policy_cfg.append('echo "profile-*-1/cluster/{}.sls'.format(nodename))
                    policy_cfg.append('echo "profile-*-1/stack/default/ceph/minions/{}.yml'.format(nodename))
                if(role.startswith('mon')):
                    log.debug('{} will be a MON'.format(nodename))
                    policy_cfg.append('echo "role-admin/cluster/{}.sls'.format(nodename))
                    policy_cfg.append('echo "role-mon/cluster/{}.sls'.format(nodename))
                    policy_cfg.append('echo "role-mon/stack/default/ceph/minions/{}.yml'.format(nodename))
        misc.sudo_write_file(self.salt.master_remote,
                '/srv/pillar/ceph/proposals/policy.cfg', '\n'.join(policy_cfg))

    def __add_public_interfaces(self):
        self.salt.master_remote.run(args = [
            'sudo',
            'ls',
            '-lisa',
            '/srv/pillar/ceph/stack/ceph/minions'
            ])
        self.salt.master_remote.run(args = [
            'sudo',
            'sh',
            '-c',
            'echo "mon_host:" > \
                    /srv/pillar/ceph/stack/ceph/ceph_conf.yml'
            ])
        for remote, roles_for_host in self.ctx.cluster.remotes.iteritems():
            nodename = remote.hostname
            for role in roles_for_host:
                if(role.startswith('mon')):
                    self.salt.master_remote.run(args = [
                        'sudo',
                        'sh',
                        '-c',
                        'echo "public_interface: {ip}" >> \
                         /srv/pillar/ceph/stack/ceph/minions/{n}.yml;\
                         echo "- \'{ip}\'" >> /srv/pillar/ceph/stack/ceph/ceph_conf.yml'.format(ip = remote.ip_address,
                             n = nodename),
                        ])

task = DeepSea
