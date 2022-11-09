#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import asyncio
import json
import logging
from pathlib import Path
from typing import List

import pytest_asyncio
import requests
import yaml
from juju.application import Application
from pytest import mark
from pytest_operator.plugin import OpsTest
from tenacity import retry
from tenacity.stop import stop_after_attempt
from tenacity.wait import wait_exponential as wexp

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
PORT = '8000'  # port at which the webserver is listening, hardcoded in webserver.py


@mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-tests and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    resources = {"webserver-image": METADATA["resources"]["webserver-image"][
        "upstream-source"]}
    await ops_test.model.deploy(charm, resources=resources,
                                application_name=APP_NAME)

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="active",
            raise_on_blocked=True,
            timeout=1000,
            idle_period=1
        )
        assert ops_test.model.applications[APP_NAME].units[
                   0].workload_status == "active"



@pytest_asyncio.fixture(autouse=True)
async def set_default_config(ops_test: OpsTest):
    """In case a previous test has changed the config, we set it to the default of 12."""
    webserver_app: Application = ops_test.model.applications[APP_NAME]
    await webserver_app.set_config({'webserver-key': "12"})


@retry(wait=wexp(multiplier=2, min=1, max=30), stop=stop_after_attempt(10),
       reraise=True)
async def test_ws_key_reset(ops_test: OpsTest):
    """Block until the default config reset has been processed."""
    webserver_app: Application = ops_test.model.applications[APP_NAME]
    assert (await webserver_app.get_config())['webserver-key']['value'] == "12"


@pytest_asyncio.fixture
async def ws_addresses(ops_test: OpsTest) -> List[str]:
    status = await ops_test.model.get_status()  # noqa: F821
    addresses = []
    for unit in list(status.applications[APP_NAME].units):
        addr = status["applications"][APP_NAME]["units"][unit]["address"]
        addresses.append(addr)
    return addresses


@mark.abort_on_fail
async def check_webservers_ready(addresses: List[str],
                                 check_key: str = None):
    """Verify that all webserver units report ready."""
    for ws_addr in addresses:
        url = f"http://{ws_addr}:{PORT}"
        home = requests.get(url)
        assert home.status_code == 200
        resp = json.loads(home.text)
        assert resp['message'] == "ready"
        if check_key:
            assert resp['*KEY*'] == check_key


async def test_webserver_key_config(ops_test: OpsTest, ws_addresses: List[str]):
    """Test that, if we change the webserver-key config option, the webserver
    process sees it as envvar.
    """
    webserver_app: Application = ops_test.model.applications[APP_NAME]
    previous_config = await webserver_app.get_config()
    previous_key = previous_config['webserver-key']['value']
    assert previous_key == '12'
    await check_webservers_ready(ws_addresses, previous_key)

    # we change the key by configuring the app;
    # verify that the webserver knows about it.
    new_key = previous_key + 'MOO'
    await webserver_app.set_config({'webserver-key': new_key})

    # WARNING this can be racey, we want to wait for config-changed to be done before
    #  we check again if the webservers are ready. 10 secs seems to cut it
    await asyncio.sleep(10)
    await check_webservers_ready(ws_addresses, new_key)
