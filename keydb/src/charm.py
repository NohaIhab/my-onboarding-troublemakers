#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from charms.keydb.v0.db import DBProvider
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, WaitingStatus
from ops.pebble import Layer


logger = logging.getLogger(__name__)


class KeyDBCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.keydb_pebble_ready, self._on_keydb_pebble_ready)

        host = self.model.get_binding("juju-info").network.bind_address

        if host is None:
            # compatibility with earlier juju versions; see https://github.com/canonical/operator/issues/753
            try:
                binding = self.model.get_binding('juju-info')
                network_info = binding._backend.network_get(binding.name, binding._relation_id)
                host = network_info['bind-addresses'][0]['addresses'][0]['address']
            except Exception as e:
                logger.error(e)

        if host is None:
            logger.debug('unable to determine hostname.')
            host = 'none'
        else:
            host = str(host)

        port = int(self.config['port'])  # always defined

        assert isinstance(host, str), host
        assert isinstance(port, int), port

        self.db = DBProvider(self, host, port)

    def _on_keydb_pebble_ready(self, event):
        container = event.workload
        # Create a new config layer.

        if container.can_connect():
            # Get the current layer.
            current_layer = container.get_plan()
            # Check if there are any changes to layer services.
            new_layer = self._keydb_layer()
            if current_layer.services != new_layer.services:
                # Changes were made, add the new layer.
                container.add_layer('keydb', new_layer, combine=True)
                logging.info("Added updated layer 'keydb' to Pebble plan")
                # Restart it and report a new status to Juju.
                container.restart('keydb')
                logging.info("Restarted keydb service")

            # All is well, set an ActiveStatus.
            self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus(
                "waiting for Pebble in workload container")

    def _keydb_layer(self) -> Layer:
        """Returns a Pebble configuration layer for KeyDB."""
        config = self.config
        args = f"--port {config['port']} --appendonly {config['appendonly']}"
        require_pass = config.get('requirepass')
        if require_pass:
            args += f"--requirepass {require_pass}"
        cmd = f"keydb-server /etc/keydb/keydb.conf {args}"
        logger.debug(cmd)

        layer_config = {
            "summary": "keydb layer",
            "description": "pebble config layer for keydb",
            "services": {
                'keydb': {
                    "override": "replace",
                    "summary": "entrypoint of the keydb image",
                    "command": cmd,
                    "startup": "enabled",
                }
            },
        }
        return Layer(layer_config)


if __name__ == "__main__":  # pragma: no cover
    main(KeyDBCharm)
