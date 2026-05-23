"""
Entry point for the backend server.

On Windows, psycopg v3 async requires a SelectorEventLoop.
We create the loop explicitly here BEFORE importing uvicorn,
then run uvicorn.Server inside that specific loop instance.
This is the only reliable way since uvicorn creates its loop
before importing your app when called via CLI.
"""
import sys
import asyncio
import selectors

if sys.platform == "win32":
    # Create a SelectorEventLoop instance and set it as the running loop
    # before anything else (uvicorn, sqlalchemy, psycopg) is imported.
    _selector = selectors.SelectSelector()
    _loop = asyncio.SelectorEventLoop(_selector)
    asyncio.set_event_loop(_loop)
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn
from uvicorn.config import Config
from uvicorn.main import Server


async def serve():
    config = Config(app="main:app", host="0.0.0.0", port=8000, loop="none")
    server = Server(config=config)
    await server.serve()


if __name__ == "__main__":
    if sys.platform == "win32":
        _loop.run_until_complete(serve())
        _loop.close()
    else:
        asyncio.run(serve())
