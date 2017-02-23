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
            'sudo',
            'make',
            'install',
            run.Raw(';'),
            'sudo',
            'chown',
            '-R',
            'salt',
            '/srv/pillar/ceph/'
            ])

        self.salt.master_remote.run(args = ['sudo', 'sed', '-i',
            's/_REPLACE_ME_/{}/'.format(self.salt.master_remote.shortname),
            '/srv/pillar/ceph/master_minion.sls'])

        self.salt.ping_minions()

    def begin(self):
        super(DeepSea, self).begin()
        self.test_stage_1_to_3()

    def end(self):
        super(DeepSea, self).end()

    def test_stage_1_to_3(self):
        self.__emulate_stage_0()
        self.__stage1()
        self.__map_roles_to_policy_cfg()
        self.salt.master_remote.run(args = [
            'sudo',
            'cat',
            '/srv/pillar/ceph/proposals/policy.cfg'
            ])
        self.__stage2()
        self.__add_public_interfaces()
        self.__stage3()
        wait_until_healthy(self.ctx, self.salt.master_remote)

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
            'sudo', 'salt-run', 'state.orch', 'ceph.stage.1'])

    def __stage2(self):
        self.salt.master_remote.run(args = [
            'sudo', 'salt-run', 'state.orch', 'ceph.stage.2'])

    def __stage3(self):
        self.salt.master_remote.run(args = [
            'sudo', 'salt-run', 'state.orch', 'ceph.stage.3'])

    def __map_roles_to_policy_cfg(self):
        # TODO this should probably happen in a random tmp dir...look in misc
        policy_cfg = "/tmp/policy.cfg"
        misc.sh('echo "cluster-ceph/cluster/*.sls\n\
config/stack/default/global.yml\n\
config/stack/default/ceph/cluster.yml" > {}'.format(policy_cfg)
                )
        for _remote, roles_for_host in self.ctx.cluster.remotes.iteritems():
            nodename = _remote.shortname
            for role in roles_for_host:
                if(role.startswith('osd')):
                    log.debug('{} will be an OSD'.format(nodename))
                    misc.sh('echo "profile-*-1/cluster/{}.sls" >> {}'.format(nodename, policy_cfg))
                    misc.sh('echo "profile-*-1/stack/default/ceph/minions/{}.yml" >> {}'.format(nodename, policy_cfg))
                if(role.startswith('mon')):
                    log.debug('{} will be a MON'.format(nodename))
                    misc.sh('echo "role-admin/cluster/{}.sls" >> {}'.format(nodename, policy_cfg))
                    misc.sh('echo "role-mon/cluster/{}.sls" >> {}'.format(nodename, policy_cfg))
                    misc.sh('echo "role-mon/stack/default/ceph/minions/{}.yml" >> /tmp/policy.cfg'.format(nodename, policy_cfg))
        misc.sh('scp {} {}:'.format(policy_cfg, self.salt.master_remote.name))
        self.salt.master_remote.run(args = [
            'sudo',
            'mv',
            'policy.cfg',
            '/srv/pillar/ceph/proposals/policy.cfg'
            ])

    def __add_public_interfaces(self):
        self.salt.master_remote.run(args = [
            'sudo',
            'ls',
            '-lisa',
            '/srv/pillar/ceph/stack/ceph/minions'
            ])
        for remote, roles_for_host in self.ctx.cluster.remotes.iteritems():
            nodename = remote.shortname
            for role in roles_for_host:
                if(role.startswith('mon')):
                    self.salt.master_remote.run(args = [
                        'sudo',
                        'sh',
                        '-c',
                        'echo "roles: \n- mon\npublic_interface: {}" >> \
                         /srv/pillar/ceph/stack/ceph/minions/{}.yml'.format(remote.ip_address,
                             nodename),
                        ])

task = DeepSea
