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
from charm import KeyDBCharm

yaml_mock = """bind-addresses:              
- mac-address: ""            
  interface-name: ""         
  addresses:                 
  - hostname: ""             
    value: 0.0.0.42    
    cidr: ""                 
  macaddress: ""             
  interfacename: ""          
egress-subnets:              
- 0.0.0.41/32          
ingress-addresses:           
- 0.0.0.41             
"""
network_mock = yaml.safe_load(yaml_mock)


@pytest.fixture
def harness(mocker):
    harness = Harness(KeyDBCharm)
    harness.update_config({"port": "70", "appendonly": "no"})
    mocker.patch.object(harness._backend, 'network_get', return_value=network_mock)
    harness.begin()
    yield harness
    harness.cleanup()


def test_network(harness):
    assert harness.charm.model.get_binding("juju-info").network.bind_address


def test_initial_plan(harness: Harness[KeyDBCharm]):
    harness.container_pebble_ready("keydb")
    plan = harness.get_container_pebble_plan("keydb")
    expected_plan = {
        "services": {
            'keydb': {
                "override": "replace",
                "summary": "entrypoint of the keydb image",
                "command": "keydb-server /etc/keydb/keydb.conf --port 70 --appendonly no",
                "startup": "enabled",
            }
        },
    }
    assert plan.to_dict() == expected_plan
    assert isinstance(harness.charm.unit.status, ActiveStatus)


def test_db_provider_ready(harness: Harness[KeyDBCharm]):
    assert harness.charm.db.ready


def test_relation_data(harness: Harness[KeyDBCharm]):
    harness.set_leader(True)
    rel_id = harness.add_relation('db', 'remote')
    data = harness.get_relation_data(rel_id, harness.charm.app)
    host = '0.0.0.42'
    assert data['host'] == host
    assert data['port'] == '70'

