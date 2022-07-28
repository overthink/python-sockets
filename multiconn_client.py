import sys
import socket
import selectors
import types
from typing import *

messages = [
    "Message 1 from client \U0001f389",
    "Message 2 from client",
    "Message 3 from client",
]


def start_connections(sel, host: str, port: int, num_conns: int) -> None:
    server_addr = (host, port)
    for i in range(num_conns):
        connid = i + 1
        print(f"Starting connection {connid} to {server_addr}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        sock.connect_ex(server_addr)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        data = types.SimpleNamespace(
            connid=connid,
            msg_total=sum(len(m.encode()) for m in messages),
            recv_total=0,
            messages=messages.copy(),
            outb=b"",
        )
        sel.register(sock, events, data=data)


def service_connection(sel, key, mask):
    sock = key.fileobj
    data = key.data
    if mask & selectors.EVENT_READ:
        # Read bytes from server. If we receive all we expect, close
        # connection.
        recv_data = sock.recv(1024)
        if recv_data:
            print(f"Received `{recv_data.decode()}` from connection {data.connid}")
            data.recv_total += len(recv_data)
        if not recv_data or data.recv_total == data.msg_total:
            print(f"Closing connection {data.connid}")
            sel.unregister(sock)
            sock.close()
    if mask & selectors.EVENT_WRITE:
        # Send messages one at a time.
        if not data.outb and data.messages:
            data.outb = data.messages.pop(0).encode()
        if data.outb:
            print(f"Sending {data.outb.decode()} to connection {data.connid}")
            sent = sock.send(data.outb)
            data.outb = data.outb[sent:]


def main() -> None:
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <host> <port> <num connections>")
        sys.exit(1)
    host, port = sys.argv[1], int(sys.argv[2])
    num_conns = int(sys.argv[3])
    sel = selectors.DefaultSelector()
    start_connections(sel, host, port, num_conns)
    try:
        while sel.get_map():
            events = sel.select(timeout=1)
            if events:
                for key, mask in events:
                    service_connection(sel, key, mask)
    except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")
    finally:
        sel.close()


if __name__ == "__main__":
    main()
