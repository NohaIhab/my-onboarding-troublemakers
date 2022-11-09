# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import pytest
import yaml
from ops.model import ActiveStatus

import ops.testing

ops.testing.SIMULATE_CAN_CONNECT = True

from ops.testing import Harness
from charm import WebserverCharm


@pytest.fixture(autouse=True)
def _patch_pebble_exec(mocker):
    obj = mocker.Mock()
    obj.wait = lambda: None
    mocker.patch.object(ops.testing._TestingPebbleClient, 'exec', obj)


@pytest.fixture
def harness():
    harness = Harness(WebserverCharm)
    harness.update_config({'webserver-key': 'super-secret-key'})
    harness.begin()
    yield harness
    harness.cleanup()


def test_initial_plan(harness: Harness[WebserverCharm]):
    harness.container_pebble_ready("webserver")
    plan = harness.get_container_pebble_plan("webserver")
    expected_plan = {
        "services": {
            "webserver": {
                "override": "replace",
                "summary": "webserver",
                "command": "python webserver.py > webserver.log",
                "startup": "enabled",
                "environment": {
                    'KEY': 'super-secret-key',
                    'DB_HOST': None,
                    'DB_PORT': None
                },
            }
        }
    }
    assert plan.to_dict() == expected_plan
    assert isinstance(harness.charm.unit.status, ActiveStatus)


def test_plan_after_db_connect(harness: Harness[WebserverCharm]):
    harness.container_pebble_ready("webserver")

    # let's pretend a db connection was active:
    relation_id = harness.add_relation('db', 'remote-db-app')
    harness.add_relation_unit(relation_id, 'remote-db-app/0')
    host, port = '0.0.0.42', 42
    # fake remote application data set:
    harness.update_relation_data(relation_id, 'remote-db-app',
                                 {'host': host, 'port': port})

    # db.ReadyEvent should have fired;
    assert harness.charm._db_host == host
    assert harness.charm._db_port == port

    # plan should be fixed now:
    plan = harness.get_container_pebble_plan("webserver")
    expected_plan = {
        "services": {
            "webserver": {
                "override": "replace",
                "summary": "webserver",
                "command": "python webserver.py > webserver.log",
                "startup": "enabled",
                "environment": {
                    'KEY': 'super-secret-key',
                    'DB_HOST': host,
                    'DB_PORT': port
                },
            }
        }
    }
    assert plan.to_dict() == expected_plan
    assert isinstance(harness.charm.unit.status, ActiveStatus)
