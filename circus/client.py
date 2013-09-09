
# -*- coding: utf-8 -
import errno
import uuid

import zmq
from zmq.utils.jsonapi import jsonmod as json

from circus.exc import CallError
from circus.py3compat import string_types
from circus.util import DEFAULT_ENDPOINT_DEALER, get_connection


def make_message(command, **props):
    return {"command": command, "properties": props or {}}


def cast_message(command, **props):
    return {"command": command, "msg_type": "cast", "properties": props or {}}


def make_json(command, **props):
    return json.dumps(make_message(command, **props))


class CircusClient(object):
    def __init__(self, context=None, endpoint=DEFAULT_ENDPOINT_DEALER,
                 timeout=5.0, ssh_server=None, ssh_keyfile=None):
        self._init_context(context)
        self.endpoint = endpoint
        self._id = uuid.uuid4().hex
        self.socket = self.context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.IDENTITY, self._id)
        self.socket.setsockopt(zmq.LINGER, 0)
        get_connection(self.socket, endpoint, ssh_server, ssh_keyfile)
        self._init_poller()
        self._timeout = timeout
        self.timeout = timeout * 1000

    def _init_context(self, context):
        self.context = context or zmq.Context.instance()

    def _init_poller(self):
        self.poller = zmq.Poller()
        self.poller.register(self.socket, zmq.POLLIN)

    def stop(self):
        self.socket.close()

    def send_message(self, command, **props):
        return self.call(make_message(command, **props))

    def call(self, cmd):
        call_id = uuid.uuid4().hex

        if not isinstance(cmd, string_types):
            cmd['id'] = call_id
            try:
                cmd = json.dumps(cmd)
            except ValueError as e:
                raise CallError(str(e))
        else:
            raise NotImplementedError("we want to insert the id")

        try:
            self.socket.send(cmd)
        except zmq.ZMQError, e:
            raise CallError(str(e))

        while True:
            try:
                events = dict(self.poller.poll(self.timeout))
            except zmq.ZMQError as e:
                if e.errno == errno.EINTR:
                    continue
                else:
                    print str(e)
                    raise CallError(str(e))

            if len(events) == 0:
                raise CallError("Timed out.")

            for socket in events:
                msg = socket.recv()
                try:
                    res = json.loads(msg)
                    if res.get('id') != call_id:
                        # we got the wrong message
                        continue
                    return res
                except ValueError as e:
                    raise CallError(str(e))
