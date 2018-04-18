# vim: ts=8 et sw=4 sts=4
"""
Highly Experimental DeepSea Orchestrator
"""

import errno
import json
import requests

from threading import Event, Thread

from mgr_module import MgrModule
from orchestrator import *

class RequestException(Exception):
    def __init__(self, message, status_code=None):
        super(RequestException, self).__init__(message)
        self.status_code = status_code


class Module(MgrModule, Orchestrator):
    config = dict()
    config_keys = {
        'salt_api_host': None,
        'salt_api_port': '8000',
        'salt_api_ssl': 'false',
        'salt_api_eauth': 'sharedsecret',
        'salt_api_username': None,
        'salt_api_password': None
    }

    COMMANDS = [
        {
            "cmd": "deepsea config-set name=key,type=CephString "
                   "name=value,type=CephString",
            "desc": "Set a configuration value",
            "perm": "rw"
        },
        {
            "cmd": "deepsea config-show",
            "desc": "Show current configuration",
            "perm": "r"
        },
        {
            "cmd": "deepsea get-inventory",
            "desc": "Get inventory",
            "perm": "r"
        },
        {
            "cmd": "deepsea add-stateless-service name=type,type=CephString",
            "desc": "Add stateless service",
            "perm": "rw"
        },
        {
            "cmd": "deepsea upgrade-start",
            "desc": "Start upgrading ALL THE THINGS!",
            "perm": "rw"
        },
        {
            "cmd": "deepsea upgrade-status",
            "desc": "Check the status of an upgrade in progress",
            "perm": "rw"
        }
    ]


    def __init__(self, *args, **kwargs):
        super(Module, self).__init__(*args, **kwargs)
        self.event = Event()
        self.token = None

        # TODO: this should really be some sort of list or dict of queued and
        #       completed jobs, not just a special case for upgrades
        self.upgrade_tag = None
        self.upgrade_result = None


    def _config_valid(self):
        for key in self.config_keys:
            self.config[key] = self.get_config(key, default=self.config_keys[key])
            if not self.config[key]:
                return False
        return True


    def handle_command(self, cmd):
        if cmd['prefix'] == 'deepsea config-show':
            return 0, json.dumps(self.config), ''

        elif cmd['prefix'] == 'deepsea config-set':
            if cmd['key'] not in self.config_keys.keys():
                return (-errno.EINVAL, '',
                        "Unknown configuration option '{0}'".format(cmd['key']))

            self.config[cmd['key']] = cmd['value']
            self.set_config(cmd['key'], cmd['value'])
            self.event.set()
            return 0, "Configuration option '{0}' updated".format(cmd['key']), ''

        elif cmd['prefix'] == 'deepsea get-inventory':
            # for dev/test purposes
            try:
                inventory = self.get_inventory()
                return 0, "\n".join([n.name for n in inventory]), ''

            except Exception as ex:
                return -errno.EINVAL, '', str(ex)

        elif cmd['prefix'] == 'deepsea add-stateless-service':
            # for dev/test purposes
            try:
                ret = self.add_stateless_service(cmd['type'])
                return 0, str(ret), ''

            except Exception as ex:
                return -errno.EINVAL, '', str(ex)

        elif cmd['prefix'] == 'deepsea upgrade-start':
            # for dev/test purposes
            try:
                if self.upgrade_start():
                    return 0, 'Upgrade started', ''
                else:
                    return 0, 'Upgrade already in progress', ''

            except Exception as ex:
                return -errno.EINVAL, '', str(ex)

        elif cmd['prefix'] == 'deepsea upgrade-status':
            # for dev/test purposes
            try:
                s = self.upgrade_status()
                if s.in_progress:
                    return 0, "Upgrade in progress", ''
                elif s.message:
                    return 0, "Last upgrade result: " + s.message, ''
                else:
                    return 0, "No upgrade in progress", ''

            except Exception as ex:
                return -errno.EINVAL, '', str(ex)

        return (-errno.EINVAL, '',
                "Command not found '{0}'".format(cmd['prefix']))


    def serve(self):
        self.log.info('DeepSea module starting up')
        self.run = True
        self._event_reader = None
        self._reading_events = False

        while self.run:
            if not self._config_valid():
                # This will spin until the config is valid, spitting a warning
                # that the config is invalid every 60 seconds.  The one oddity
                # is that while setting the various parameters, this log warning
                # will print once for each parameter set until the config is    
                # valid.
                self.log.warn("Configuration invalid; try `ceph deepsea config-set [...]`")
                self.event.wait(60)
                self.event.clear()
                continue

            if self._event_reader and not self._reading_events:
                self._event_reader = None

            if not self._event_reader:
                try:
                    # This spawns a separate thread to read the salt event bus
                    # stream.  We can't do it in the serve thead, because reading
                    # from the response blocks, which would prevent the serve
                    # thread from handling anything else.
                    self._event_response = self._do_request_with_login("GET", "events", stream=True)
                    self._event_reader = Thread(target=self._read_sse)
                    self._reading_events = True
                    self._event_reader.start()
                except Exception as ex:
                    self.log.warn("Failure setting up event reader: " + str(ex))
                    # gives an (arbitrary) 5 second retry if we can't attach to
                    # the salt-api event bus for some reason
                    # TODO: increase this and/or make it configurable
                    self.event.wait(5)
                    self.event.clear()
                    continue

            # Wait indefinitely for something interesting to happen (e.g.
            # config-set, or shutdown), or the event reader to fail, which
            # will happen if the salt-api server dies or restarts).
            # TODO: figure out how to restart the _event_reader thread if
            # config changes, e.g.: a new username or password is set.
            self.event.wait()
            self.event.clear()


    # Reader/parser of SSE events, see:
    # - https://docs.saltstack.com/en/latest/ref/netapi/all/salt.netapi.rest_cherrypy.html#events)
    # - https://www.w3.org/TR/2009/WD-eventsource-20090421/
    # Note: this is pretty braindead and doesn't implement the full eventsource
    # spec, but it *does* implement enough for us to listen to events from salt
    # and potentially do something with them.
    # TODO: How are we going to deal with salt-api dying, or mgr failing over,
    #       or other unforeseen glitches when we're waiting for particular jobs
    #       to complete?  What's to stop things falling through the cracks?
    def _read_sse(self):
        event = {}
        try:
            for line in self._event_response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    colon = line.find(':')
                    if colon > 0:
                        k = line[:colon]
                        v = line[colon+2:]
                        if k == "retry":
                            # TODO: find out if we need to obey this reconnection time
                            self.log.warn("Server requested retry {}, ignored".format(v))
                        else:
                            event[k] = v
                else:
                    # Empty line, terminates an event.  Note that event['tag']
                    # is a salt-api extension to SSE to avoid having to decode
                    # json data if you don't care about it.  To get to the
                    # interesting stuff, you want event['data'], which is json.
                    self.log.info("Got event '{}'".format(str(event)))

                    # If we actually wanted to do something with the event,
                    # say, we want to notice that some long salt run has
                    # finished, we'd call some notify method here (TBD).
                    # Right now, upgrade is the only thing that uses this
                    # functionality, so it's special-cased here.
                    if self.upgrade_tag and event['tag'] == self.upgrade_tag + "/ret":
                        self.upgrade_result = json.loads(event['data'])
                        self.upgrade_tag = None

                    # If you want to have some fun, try `salt '*' test.ping`
                    # on the master while this module is running with
                    # "debug_mgr 4/5", and tail the mgr log.
                    event = {}
            self.log.warn("SSE read terminated")
        except Exception as ex:
            self.log.warn("SSE read failed: {}".format(str(ex)))

        self._reading_events = False
        self.event.set()


    def shutdown(self):
        self.log.info('DeepSea module shutting down')
        self.run = False
        self.event.set()


    # This blocks until it gets the full list of nodes back from salt, and
    # returns a list of InventoryNode()s.
    #
    # To implement this in nonblocking form, internally it could use the
    # runner_async client which would give a salt job ID.  _read_sse() could
    # then notice when that job was complete, and...  How would it tell the
    # caller of get_inventory() that the inventory had arrived?
    #
    # TODO: populate devices[] for each node?  (I'm not aware of an obvious
    # way to extract this from DeepSea in a hurry).
    def get_inventory(self, node_filter=None):
        resp = self._do_request_with_login("POST", data = {
            "client": "runner",
            "fun": "select.minions",
            "cluster": "ceph"
            # could add "role:" here to get individual roles
            # if node_filter was requested (DeepSea role should map to
            # Orchestrator label concept)
        })

        # This is really cumbersome.  Possibly I should be subclassing
        # InventoryNode() to provide a constructor that takes a hostname,
        # then this could just be a nice little generator.
        inventory = list()
        for hostname in resp.json()["return"][0]:
            node = InventoryNode()
            node.name = hostname
            inventory.append(node)

        # Note: hosts are returned by salt in an arbitrary, unsorted order.
        return inventory


    # This one is...  Interesting.
    #
    # See, DeepSea has a policy.cfg file, where the admin defines what roles
    # each node has.  Any node with "role-rgw" assigned is where DeepSea will
    # go and install radosgw.  Usually with DeepSea, once you've run through
    # stages 0-3, you've got a Ceph cluster up with MONs, OSDs and MGRs, but
    # "optional" pieces like RGW and MDS, Ganesha and iSCSI gateways
    # are all deployed when you run stage 4.  These things could equally be
    # deployed with this add_stateless_service function (instead of running
    # stage 4), but it's a pretty blunt instrument:
    #
    # - Calling this with service_type=rgw will tell DeepSea to deploy rgw
    #   on all the nodes with role-rgw assigned, so StatelessServiceSpec()
    #   kinda doesn't really serve any purpose.
    # - Calling this with service_type=mds would (were it implemented) tell
    #   DeepSea to deploiy mds on all the nodes with role-mds, and DeepSea
    #   would *also* automatically go create the CephFS pools.
    #
    # It also takes a damnably long time to run, and if it completes
    # successfully returns a huge pile of status information for all the salt
    # stuff that happened.
    #
    # This one really wants to be async (using runner_async and having
    # _read_sse() expect events indicating the job is complete), but again,
    # the caller needs some means of knowing the job is actually complete.
    #
    def add_stateless_service(self, service_type, spec=None):
        if service_type == "rgw":
            resp = self._do_request_with_login("POST", data = {
                "client": "runner",
                "fun": "state.orch",
                "arg": ["ceph.stage.radosgw"]
            })
            return resp.json()["return"]

        raise NotImplementedError()


    # I'm fairly certain this doesn't make sense for DeepSea, given
    # StatelessServiceSpec() doesn't make sense (see above comment)
    def update_stateless_service(self, service_type, id_, spec):
        raise NotImplementedError()


    # This is impossible with DeepSea right now (DeepSea will let you remove
    # services, but to do so you have to go edit the policy.cfg file and
    # run stage 5)
    def remove_stateless_service(self, service_type, id_):
        raise NotImplementedError()


    # DeepSea's stage 0 will upgrade everything (not just ceph) for which
    # there's an upgrade available, but will do so in a sane order (MONs
    # before OSDs, etc.)  As there's currently no means of checking
    # what version of Ceph is available (or of requesting *only* Ceph be
    # upgraded), UpgradeSpec() is not used.
    #
    # This returns immediately, to check the status of an upgrade in
    # progress, try upgrade_status().
    #
    # The Orchestrator API doesn't define a return value for upgrade_start(),
    # so here I've arbitrarily got it returning True if the upgrade start
    # was triggered, False if there's an upgrade in progress already, or
    # throwing an exception if something weird happened.
    def upgrade_start(self, upgrade_spec=None):
        if self.upgrade_tag:
            # There's already (allegedly) an upgrade in progress, do nothing
            # TODO: print the tag so the user can check the salt active job
            #       queue themselves?
            # TODO: provide a means of telling the system that no, really,
            #       there's no upgrade in progress, in case mgr died or lost
            #       connection to the salt event bus at just the wrong time,
            #       and so never noticed that the job was complete?
            # TODO: See if it's possible to check if an upgrade is already in
            #       progress beacuse someone ran stage 0 by hand, not with mgr.
            return False

        resp = self._do_request_with_login("POST", data = {
            "client": "runner_async",
            "fun": "state.orch",
            "arg": ["ceph.stage.0"]
        })
        data = resp.json()["return"][0]
        if not 'tag' in data or not 'jid' in data:
            raise Exception("async job missing tag and/or jid: {}".format(str(data)))

        self.upgrade_tag = data['tag']
        self.upgrade_result = None
        return True


    # One difficulty for status reporting is that it's easy to know when a
    # given job started or finished, but for "ceph.stage.0", I don't know how
    # (or if it's possible to) track events/states that were triggered as a
    # result of the orchestration, i.e. I know *whether* an upgrade is running
    # (at least, I know if an upgrade is running if it was triggered by mgr),
    # but I have no way of knowing how far *through* the upgrade is.
    def upgrade_status(self):
        """
        If an upgrade is currently underway, report on where
        we are in the process, or if some error has occurred.

        :return: UpgradeStatusSpec instance
        """
        status = UpgradeStatusSpec()
        if self.upgrade_tag:
            status.in_progress = True

        elif self.upgrade_result:
            if self.upgrade_result['data']['success']:
                status.message = "Success"
            else:
                # If the job failed, the result will include potentially a
                # large amount of information about status and broken things.
                # TODO: parse this into something a lot nicer
                status.message = json.dumps(self.upgrade_result)

        return status


    # DeepSea doesn't expose this
    def upgrade_available(self):
        raise NotImplementedError()


    # _do_request(), _login() and _do_request_with_login() are an extremely
    # minimalist form of the following, with notably terse error handling:
    # https://bitbucket.org/openattic/openattic/src/ce4543d4cbedadc21b484a098102a16efec234f9/backend/rest_client.py?at=master&fileviewer=file-view-default
    # https://bitbucket.org/openattic/openattic/src/ce4543d4cbedadc21b484a098102a16efec234f9/backend/deepsea.py?at=master&fileviewer=file-view-default
    # rationale:
    # - I needed slightly different behaviour than in openATTIC (I want the
    #   caller to read the response, to allow streaming the salt-api event bus)
    # - I didn't want to pull in 400+ lines more code into this presently
    #   experimental module, to save everyone having to review it ;-)

    def _do_request(self, method, path="", data=None, stream=False):
        """
        returns the response, which the caller then has to read
        """
        protocol = 'https' if self.config['salt_api_ssl'].lower() != 'false' else 'http'
        url = "{0}://{1}:{2}/{3}".format(protocol,
                                         self.config['salt_api_host'],
                                         self.config['salt_api_port'], path)
        try:
            if method.lower() == 'get':
                resp = requests.get(url, headers = { "X-Auth-Token": self.token },
                                    data=data, stream=stream)
            elif method.lower() == 'post':
                resp = requests.post(url, headers = { "X-Auth-Token": self.token },
                                     data=data)

            else:
                raise RequestException("Method '{}' not supported".format(method.upper()))
            if resp.ok:
                return resp
            else:
                msg = "Request failed with status code {}".format(resp.status_code)
                self.log.error(msg)
                raise RequestException(msg, resp.status_code)
        except requests.exceptions.ConnectionError as ex:
            self.log.error(str(ex))
            raise RequestException(str(ex))
        except requests.exceptions.InvalidURL as ex:
            self.log.error(str(ex))
            raise RequestException(str(ex))


    def _login(self):
        resp = self._do_request('POST', 'login', data = {
            "eauth": self.config['salt_api_eauth'],
            "sharedsecret" if self.config['salt_api_eauth'] == 'sharedsecret' else 'password': self.config['salt_api_password'],
            "username": self.config['salt_api_username']
        })
        self.token = resp.json()['return'][0]['token']
        self.log.info("Salt API login successful")


    def _do_request_with_login(self, method, path="", data=None, stream=False):
        retries = 2
        while True:
            try:
                if not self.token:
                    self._login()
                return self._do_request(method, path, data, stream)
            except RequestException as ex:
                retries -= 1
                if ex.status_code not in [401, 403] or retries == 0:
                    raise ex
                self.token = None

