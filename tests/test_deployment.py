import asyncio
import json
from pathlib import Path
from typing import List

import juju.relation
import pytest
import requests
import yaml
from pytest import mark
from pytest_asyncio import fixture
from pytest_operator.plugin import OpsTest
from tenacity import retry
from tenacity.stop import stop_after_attempt
from tenacity.wait import wait_exponential as wexp

ROOT = Path(__file__).parent.parent

# app names
_DB_META = yaml.safe_load(Path("./keydb/metadata.yaml").read_text())
_WS_META = yaml.safe_load(Path("./webserver/metadata.yaml").read_text())

DB = _DB_META['name']
WS = _WS_META['name']
DB_PORT = '8042'
WS_PORT = '8000'

@mark.abort_on_fail
@pytest.fixture(autouse=True, scope='module')
async def setup(ops_test: OpsTest):
    """Deploy keydb and webserver, relate them."""
    charms = await ops_test.build_charms(ROOT / 'keydb', ROOT / 'webserver')

    await asyncio.gather(
        ops_test.model.deploy(charms[DB], application_name=DB,
                              config={'port': DB_PORT}),
        ops_test.model.deploy(charms[WS], application_name=WS)
    )

    await ops_test.model.add_relation(f'{DB}:http', f'{WS}:http')


@mark.abort_on_fail
async def test_applications_active(ops_test: OpsTest):
    """Verify that keydb and webserver are both active/idle."""
    await ops_test.model.wait_for_idle(apps=[DB, WS], timeout=1000, idle_period=1)

    # Verify that the model has exactly two applications running.
    assert set(ops_test.model.applications) == {DB, WS}


@fixture
async def db_address(ops_test: OpsTest):
    status = await ops_test.model.get_status()  # noqa: F821
    unit = list(status.applications[DB].units)[0]
    return status["applications"][DB]["units"][unit]["address"]


@fixture
async def ws_addresses(ops_test: OpsTest) -> List[str]:
    status = await ops_test.model.get_status()  # noqa: F821
    addresses = []
    for unit in list(status.applications[WS].units):
        addr = status["applications"][WS]["units"][unit]["address"]
        addresses.append(addr)
    return addresses


@mark.abort_on_fail
@retry(wait=wexp(multiplier=2, min=1, max=30), stop=stop_after_attempt(10),
       reraise=True)
async def test_db_alive(ops_test: OpsTest):
    _, stdout, _ = await ops_test.juju(*(
        f"ssh --container keydb {DB}/0 keydb-cli ping".split()
    ))
    assert stdout.strip() == 'PONG'


async def test_http_integration(ops_test: OpsTest, db_address):
    """Verify that the http relation databags look as they should."""
    rel: juju.relation.Relation = ops_test.model.relations[0]
    _, ws_unit, _ = await ops_test.juju(*(f'show-unit {WS}/0'.split()))
    application_data = yaml.safe_load(ws_unit)[f"{WS}/0"]['relation-info'][0]['application-data']
    assert application_data['host'] == db_address
    assert application_data['port'] == '6379'


@mark.abort_on_fail
async def test_webservers_ready(ws_addresses: List[str]):
    """Verify that all webserver units report ready."""
    for ws_addr in ws_addresses:
        url = f"http://{ws_addr}:{WS_PORT}"
        home = requests.get(url)
        assert json.loads(home.text)['message'] == "ready"


@pytest.mark.parametrize("key, val", (('foo', 'bar'),
                                      ('baz', 'qux')))
async def test_webservers_storage_with_db(ws_addresses: List[str],
                                          key: str, val: str):
    """Verify that all webserver units can be used to store/retrieve data
    via their db integration."""
    for ws_ip in ws_addresses:
        url = f"http://{ws_ip}:{WS_PORT}"
        set_key = requests.post(f"{url}/set/{key}/{val}")
        assert set_key.text == '"ok"'  # it's json
        assert set_key.status_code == 200

        resp = requests.get(f"{url}/get/{key}")
        assert resp.text == f'"{val}"'  # it's json
        assert resp.status_code == 200
