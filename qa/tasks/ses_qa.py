"""
Task (and subtasks) for SES test automation

Linter:
    flake8 --max-line-length=100
"""
import logging

from tasks.salt_manager import SaltManager
from tasks.scripts import Scripts

from teuthology.exceptions import (
    ConfigError,
    )
from teuthology.task import Task

log = logging.getLogger(__name__)
ses_qa_ctx = {}


class SESQA(Task):

    def __init__(self, ctx, config):
        global ses_qa_ctx
        super(SESQA, self).__init__(ctx, config)
        if ses_qa_ctx:
            self.log = ses_qa_ctx['logger_obj']
            self.log.debug("ses_qa_ctx already populated (we are in a subtask)")
        if not ses_qa_ctx:
            ses_qa_ctx['logger_obj'] = log
            self.log = log
            self.log.debug("populating ses_qa_ctx (we are *not* in a subtask)")
            self._populate_ses_qa_context()
        self.master_remote = ses_qa_ctx['master_remote']
        self.nodes = self.ctx['nodes']
        self.nodes_client_only = self.ctx['nodes_client_only']
        self.nodes_cluster = self.ctx['nodes_cluster']
        self.nodes_gateway = self.ctx['nodes_gateway']
        self.nodes_storage = self.ctx['nodes_storage']
        self.nodes_storage_only = self.ctx['nodes_storage_only']
        self.remote_lookup_table = self.ctx['remote_lookup_table']
        self.remotes = self.ctx['remotes']
        self.roles = self.ctx['roles']
        self.role_lookup_table = self.ctx['role_lookup_table']
        self.role_types = self.ctx['role_types']
        self.scripts = Scripts(self.ctx, self.log)
        self.sm = ses_qa_ctx['salt_manager_instance']

    def _populate_ses_qa_context(self):
        global ses_qa_ctx
        ses_qa_ctx['salt_manager_instance'] = SaltManager(self.ctx)
        ses_qa_ctx['master_remote'] = ses_qa_ctx['salt_manager_instance'].master_remote

    def os_type_and_version(self):
        os_type = self.ctx.config.get('os_type', 'unknown')
        os_version = float(self.ctx.config.get('os_version', 0))
        return (os_type, os_version)

    def setup(self):
        super(SESQA, self).setup()

    def begin(self):
        super(SESQA, self).begin()

    def end(self):
        super(SESQA, self).end()

    def teardown(self):
        super(SESQA, self).teardown()


class Validation(SESQA):

    err_prefix = "(validation subtask) "

    def __init__(self, ctx, config):
        global ses_qa_ctx
        ses_qa_ctx['logger_obj'] = log.getChild('validation')
        self.name = 'ses_qa.validation'
        super(Validation, self).__init__(ctx, config)
        self.log.debug("munged config is {}".format(self.config))

    def begin(self):
        self.log.debug("Processing tests: ->{}<-".format(self.config.keys()))
        for method_spec, kwargs in self.config.items():
            kwargs = {} if not kwargs else kwargs
            if not isinstance(kwargs, dict):
                raise ConfigError(self.err_prefix + "Method config must be a dict")
            self.log.info(
                "Running validation test {} with config ->{}<-"
                .format(method_spec, kwargs)
                )
            method = getattr(self, method_spec, None)
            if method:
                method(**kwargs)
            else:
                raise ConfigError(self.err_prefix + "No such method ->{}<-"
                                  .format(method_spec))


task = SESQA
validation = Validation
