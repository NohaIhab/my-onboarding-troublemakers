#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

# Learn more at: https://juju.is/docs/sdk

"""Charm the service."""

import logging
from pathlib import Path

from ops.charm import CharmBase, PebbleReadyEvent
from ops.framework import StoredState
from ops.model import ActiveStatus, Container, WaitingStatus
from charms.keydb.v0.db import DBRequirer, ReadyEvent, BrokenEvent
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class WebserverCharm(CharmBase):
    """Charm the service."""
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._webserver_key: str = self.config.get('webserver-key', '')
        self.db = DBRequirer(self)

        self._stored.set_default(db_host=None, db_port=None)

        self.framework.observe(self.on.webserver_pebble_ready, self._on_webserver_pebble_ready)
        self.framework.observe(self.db.on.ready, self._on_db_ready)
        self.framework.observe(self.db.on.broken, self._on_db_broken)

    @property
    def _db_host(self):
        return self._stored.db_host

    @property
    def _db_port(self):
        return self._stored.db_port

    def _on_db_ready(self, event: ReadyEvent):
        self._stored.db_host = event.host
        self._stored.db_port = event.port
        if not self._restart_webserver(event):
            event.defer()

    def _on_db_broken(self, event: BrokenEvent):
        self._stored.db_host = None
        self._stored.db_port = None
        if not self._restart_webserver(event):
            event.defer()

    def _on_webserver_pebble_ready(self, event: PebbleReadyEvent):
        """Define and start a workload using the Pebble API.

        You'll need to specify the right entrypoint and environment
        configuration for your specific workload. Tip: you can see the
        standard entrypoint of an existing container using docker inspect

        Learn more about Pebble layers at https://github.com/canonical/pebble
        """
        self._restart_webserver(event)

    def _restart_webserver(self, _=None):
        container = self.unit.get_container('webserver')
        if container.can_connect():
            # ensure the container is set up
            self._setup_container(container)

            # Get the current layer.
            current_layer = container.get_plan()
            new_layer = self._webserver_layer()
            # Check if there are any changes to layer services.
            if current_layer.services != new_layer.services:
                # Changes were made, add the new layer.
                container.add_layer('webserver', new_layer, combine=True)
                logging.info("Added updated layer 'webserver' to Pebble plan")
                # Restart it and report a new status to Juju.
                container.replan()
                logging.info("restarted webserver service")

            self.unit.status = ActiveStatus()
            return True
        else:
            self.unit.status = WaitingStatus(
                'Pending webserver restart; waiting for workload container'
            )
            return False

    def _webserver_layer(self) -> Layer:
        # Define an initial Pebble layer configuration
        pebble_layer = {
            "summary": "webserver layer",
            "description": "pebble config layer for webserver",
            "services": {
                "webserver": {
                    "override": "replace",
                    "summary": "webserver",
                    # the webserver process dumps logs to webserver.log.
                    "command": "python webserver.py > webserver.log",
                    "startup": "enabled",
                    "environment": {
                        'KEY': self._webserver_key,
                        'DB_HOST': self._db_host,
                        'DB_PORT': self._db_port
                    },
                }
            },
        }
        return Layer(pebble_layer)

    @staticmethod
    def _setup_container(container: Container):
        # copy the webserver file to the container. In a production environment,
        # the workload would typically be an OCI image. Here however we have a
        # 'bare' python container as base.

        resources = Path(__file__).parent / 'resources'
        webserver_source_path = resources / 'webserver.py'
        with open(webserver_source_path, 'r') as webserver_source:
            logger.info('pushing webserver source...')
            container.push('/webserver.py', webserver_source)

        # we install the webserver dependencies; in a production environment, these
        # would typically be baked in the workload OCI image.
        webserver_dependencies_path = resources / 'webserver-dependencies.txt'
        with open(webserver_dependencies_path, 'r') as dependencies_file:
            dependencies = dependencies_file.read().split('\n')
            logger.info(f'installing webserver dependencies {dependencies}...')
            container.exec(['pip', 'install', *dependencies]).wait()
