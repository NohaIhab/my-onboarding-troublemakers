"""Library for the ingress relation.

This library contains the Requires and Provides classes for handling
the db interface.
"""

import logging

from ops.charm import CharmEvents, RelationEvent, CharmBase, \
    RelationCreatedEvent
from ops.framework import EventBase, EventSource, Object, Handle
from ops.model import BlockedStatus, Relation

# The unique Charmhub library identifier, never change it
LIBID = "not a real libid"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

logger = logging.getLogger(__name__)


class DBProvider(Object):
    def __init__(self, charm: CharmBase, host: str, port: int, key: str = 'db'):
        super().__init__(charm, key)
        self.charm = charm
        self._host = host
        self._port = port

        self.framework.observe(charm.on.db_relation_created,
                               self._on_db_relation_created)

    @property
    def ready(self):
        if self._host and self._port:
            return True
        return False

    def _on_db_relation_created(self, event: RelationCreatedEvent):
        if not self.ready:
            return event.defer()
        self.offer(event.relation)

    def offer(self, relation: Relation):
        if not self.charm.unit.is_leader():
            raise RuntimeError('this relation interface only '
                               'supports scale-1 providers.')

        # publish host and port to app databag
        app_databag = relation.data[self.charm.app]

        app_databag['host'] = self._host
        app_databag['port'] = str(self._port)


class ReadyEvent(RelationEvent):
    """Redis is ready."""

    def __init__(self, handle: Handle, relation, host, port):
        super().__init__(handle, relation)
        self.host = host
        self.port = port

    def snapshot(self) -> dict:
        dct = super().snapshot()
        dct['host'] = self.host
        dct['port'] = self.port
        return dct

    def restore(self, snapshot: dict) -> None:
        super().restore(snapshot)
        self.host = snapshot['host']
        self.port = snapshot['port']


class BrokenEvent(RelationEvent):
    """Redis is broken."""


class RedisRelationCharmEvents(CharmEvents):
    ready = EventSource(ReadyEvent)
    broken = EventSource(BrokenEvent)


class DBRequirer(Object):
    on = RedisRelationCharmEvents()

    def __init__(self, charm: CharmBase, key: str = 'db'):
        super().__init__(charm, key)
        self.charm = charm
        evts = charm.on[key]
        self.framework.observe(evts.relation_changed, self._on_db_relation_changed)

    @property
    def relation(self):
        db_relations = self.charm.model.relations['db']
        if len(db_relations) != 1:
            raise RuntimeError('too many relations')
        return db_relations[0]

    def _on_db_relation_changed(self, event):
        if self.ready:
            self.on.ready.emit(event.relation, self._host, self._port)
        else:
            # data invalid
            self.on.broken.emit(event.relation)

    @property
    def _host(self):
        # read the host from the remote app databag
        return self.relation.data[self.relation.app]['host']

    @property
    def _port(self):
        # read the port from the remote app databag
        return int(self.relation.data[self.relation.app]['port'])

    @property
    def ready(self):
        try:
            self._port
            self._host
        except (TimeoutError, RuntimeError, KeyError) as e:
            logger.error(e)
            return False
        return True
