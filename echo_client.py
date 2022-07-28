import socket
from types import *

HOST = "127.0.0.1"
PORT = 60000


def main() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        s.sendall(b"Hello world")
        data = s.recv(1024)

    print("Received {}".format(data.decode()))


if __name__ == "__main__":
    main()
