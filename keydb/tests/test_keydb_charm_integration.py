#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path
from tenacity.wait import wait_exponential as wexp

import pytest
import yaml
from _pytest import mark
from pytest_operator.plugin import OpsTest
from tenacity import retry, stop_after_attempt

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-tests and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    resources = {
        "keydb-image": METADATA["resources"]["keydb-image"]["upstream-source"]}
    await ops_test.model.deploy(charm, resources=resources,
                                application_name=APP_NAME)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )


@retry(wait=wexp(multiplier=2, min=1, max=30), stop=stop_after_attempt(10),
       reraise=True)
async def test_db_alive(ops_test: OpsTest):
    _, stdout, _ = await ops_test.juju(*(
        f"ssh --container keydb {APP_NAME}/0 keydb-cli ping".split()
    ))
    assert stdout.strip() == 'PONG'
