"""
Simple asyncio server example that will (!!!) eval arbitrary python code
submitted by the client and return the result.
"""
import asyncio
import socket
import sys
from typing import *


async def handle_client(reader, writer) -> None:
    request = None
    while request != "quit":
        request = (await reader.read(255)).decode("utf-8").strip()
        print(f"got request `{request}`")
        response = str(eval(request)) + "\n"
        writer.write(response.encode("utf-8"))
        await writer.drain()
    writer.close()


async def run_server() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <host> <port>")
        sys.exit(1)
    host, port = sys.argv[1], int(sys.argv[2])
    server = await asyncio.start_server(handle_client, host, port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(run_server())
