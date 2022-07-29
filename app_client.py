"""
`app` in the sense that we're layering on an application level protocol here.
"""

import io
import json
import selectors
import socket
import struct
import sys
import traceback
from typing import *


class Message:
    def __init__(self, sel, sock, server_addr: Tuple[str, int], request: Dict) -> None:
        self.sel = sel
        self.sock = sock
        self.server_addr = server_addr
        self.request = request
        self._recv_buffer = b""
        self._send_buffer = b""
        self._request_queued = False
        self._jsonheader_len: Optional[int] = None
        self.jsonheader: Optional[Dict] = None
        self.response: Union[Dict, bytes, None] = None

    def process_protoheader(self) -> None:
        # expect two bytes describing size of header
        header_len = 2
        if len(self._recv_buffer) < header_len:
            return
        self._jsonheader_len = struct.unpack(">H", self._recv_buffer[:header_len])[0]
        self._recv_buffer = self._recv_buffer[header_len:]

    def _json_encode(self, obj: Dict, encoding: str) -> bytes:
        return json.dumps(obj, ensure_ascii=False).encode(encoding)

    def _json_decode(self, json_bytes: bytes, encoding: str) -> Dict:
        with io.TextIOWrapper(
            io.BytesIO(json_bytes), encoding=encoding, newline=""
        ) as tiow:
            obj = json.load(tiow)
            return obj

    def process_jsonheader(self) -> None:
        header_len = self._jsonheader_len
        if header_len and (len(self._recv_buffer) < header_len):
            return
        self.jsonheader = self._json_decode(self._recv_buffer[:header_len], "utf-8")
        self._recv_buffer = self._recv_buffer[header_len:]
        for required in [
            "byteorder",
            "content-length",
            "content-type",
            "content-encoding",
        ]:
            if required not in self.jsonheader:
                raise ValueError(f"Missing required header '{required}'")

    def _process_response_json_content(self) -> None:
        if not isinstance(self.response, dict):
            return
        content = self.response
        result = content.get("result")
        print(f"Got result: {result}")

    def process_response(self) -> None:
        if not self.jsonheader:
            return
        content_len = self.jsonheader["content-length"]
        if len(self._recv_buffer) < content_len:
            return
        data = self._recv_buffer[:content_len]
        self._recv_buffer = self._recv_buffer[content_len:]
        if self.jsonheader["content-type"] == "text/json":
            encoding = self.jsonheader["content-encoding"]
            self.response = self._json_decode(data, encoding)
            print(f"Received response {self.response!r} from {self.server_addr}")
            self._process_response_json_content()
        self.close()

    def _read(self) -> None:
        try:
            data = self.sock.recv(4096)
        except BlockingIOError:
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            pass
        else:
            if data:
                self._recv_buffer += data
            # else:
            # raise RuntimeError("Peer closed")

    def _write(self) -> None:
        if self._send_buffer:
            print(f"Sending {self._send_buffer!r} to {self.server_addr}")
            try:
                sent = self.sock.send(self._send_buffer)
            except BlockingIOError:
                pass
            else:
                self._send_buffer = self._send_buffer[sent:]

    def read(self) -> None:
        self._read()
        if self._jsonheader_len is None:
            self.process_protoheader()
        if self._jsonheader_len is not None:
            if self.jsonheader is None:
                self.process_jsonheader()
        if self.jsonheader:
            if self.response is None:
                self.process_response()

    def _create_message(
        self, *, content_bytes, content_type, content_encoding
    ) -> bytes:
        jsonheader = {
            "byteorder": sys.byteorder,
            "content-type": content_type,
            "content-encoding": content_encoding,
            "content-length": len(content_bytes),
        }
        jsonheader_bytes = self._json_encode(jsonheader, "utf-8")
        message_hdr = struct.pack(">H", len(jsonheader_bytes))
        message = message_hdr + jsonheader_bytes + content_bytes
        return message

    def queue_request(self) -> None:
        content = self.request["content"]
        content_type = self.request["type"]
        content_encoding = self.request["encoding"]
        req = {
            "content_type": content_type,
            "content_encoding": content_encoding,
        }
        if content_type == "text/json":
            content_bytes = self._json_encode(content, content_encoding)
        else:
            content_bytes = content
        req["content_bytes"] = content_bytes
        message = self._create_message(**req)
        self._send_buffer += message
        self._request_queued = True

    def write(self) -> None:
        if not self._request_queued:
            self.queue_request()
        self._write()
        if self._request_queued:
            if not self._send_buffer:
                # nothing left to send, update selector to only care about
                # reads
                self.sel.modify(self.sock, selectors.EVENT_READ, data=self)

    def process_events(self, mask: int) -> None:
        if mask & selectors.EVENT_READ:
            self.read()
        if mask & selectors.EVENT_WRITE:
            self.write()

    def close(self) -> None:
        print(f"Closing connection to {self.server_addr}")
        try:
            self.sel.unregister(self.sock)
        except Exception as e:
            print(
                f"Error: selector.unregister() exception for "
                f"{self.server_addr}: {e!r}"
            )
        try:
            self.sock.close()
        except OSError as e:
            print(f"Error: socket.close() exception for {self.server_addr}: {e!r}")
        finally:
            # kill reference to socket so it's gc'd
            self.sock = None


def create_request(action: str, value) -> Dict:
    if action == "search":
        return dict(
            type="text/json",
            encoding="utf-8",
            content=dict(action=action, value=value),
        )
    raise ValueError("unknown action")


def start_connection(sel, host: str, port: int, request: Dict) -> None:
    addr = (host, port)
    print(f"Starting connection to {addr}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    sock.connect_ex(addr)
    events = selectors.EVENT_READ | selectors.EVENT_WRITE
    message = Message(sel, sock, addr, request)
    sel.register(sock, events, data=message)


def main() -> None:
    if len(sys.argv) != 5:
        print(f"Usage: {sys.argv[0]} <host> <port> <action> <value>")
        sys.exit(1)

    host, port = sys.argv[1], int(sys.argv[2])
    action, value = sys.argv[3], sys.argv[4]
    request = create_request(action, value)

    try:
        sel = selectors.DefaultSelector()
        start_connection(sel, host, port, request)
        while True:
            events = sel.select(timeout=1)
            for key, mask in events:
                message = key.data
                try:
                    message.process_events(mask)
                except Exception:
                    print(
                        f"Main: Error: Exception for {message.server_addr}:\n"
                        f"{traceback.format_exc()}"
                    )
                    message.close()
            # bail from event loop if we're no sockets remain registered
            if not sel.get_map():
                break

    except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")
    finally:
        sel.close()


if __name__ == "__main__":
    main()
