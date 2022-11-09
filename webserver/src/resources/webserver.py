import os
from typing import Union

import redis as redis
import uvicorn as uvicorn
from fastapi import FastAPI


def client():
    DB_PORT = os.environ.get('DB_PORT')
    DB_HOST = os.environ.get('DB_HOST')
    if not (DB_HOST and DB_PORT):
        raise RuntimeError('required envvars unset')
    return redis.Redis(host=DB_HOST,
                       port=int(DB_PORT))


def check_key():
    KEY = os.environ.get('KEY')

    if not KEY:
        raise RuntimeError('this webserver requires the `KEY` '
                           'environment variable to be set and to be '
                           'a nonempty string. For whatever reason.')
    return {"message": "ready",
            "*KEY*": KEY}


app = FastAPI()


@app.get("/")
async def home():
    try:
        return check_key()
    except RuntimeError:
        return 'not ready'


@app.get("/get/{var}")
async def get_var(var: str):
    check_key()
    try:
        return client().get(var)
    except Exception as e:
        return str(e)


@app.post("/set/{var}/{value}")
async def set_var(var: str, value: Union[str, int]):
    check_key()
    try:
        client().set(var, value)
        return 'ok'
    except Exception as e:
        return str(e)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
