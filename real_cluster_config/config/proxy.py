import socket
import select
import sys

def proxy_port(external_ip, internal_ip, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        # Bind to the docker eth0 IP to receive NATed traffic
        server.bind((external_ip, port))
        server.listen(100)
        print(f"Proxy listening on {external_ip}:{port} and forwarding to {internal_ip}:{port}")
    except Exception as e:
        print(f"Failed to bind {external_ip}:{port}: {e}")
        return

    sockets = [server]
    pairs = {}
    
    while sockets:
        try:
            r, _, _ = select.select(sockets, [], [])
            for sock in r:
                if sock is server:
                    client, addr = server.accept()
                    backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        # Forward to the loopback IP where Java is listening
                        backend.connect((internal_ip, port))
                        sockets.extend([client, backend])
                        pairs[client] = backend
                        pairs[backend] = client
                    except Exception as e:
                        print(f"Failed to connect to backend {internal_ip}:{port}: {e}")
                        client.close()
                else:
                    try:
                        data = sock.recv(32768)
                        if data:
                            pairs[sock].send(data)
                        else:
                            raise Exception('EOF')
                    except Exception:
                        sock.close()
                        sockets.remove(sock)
                        if sock in pairs:
                            peer = pairs[sock]
                            if peer in sockets:
                                peer.close()
                                sockets.remove(peer)
                            del pairs[peer]
                        if sock in pairs:
                            del pairs[sock]
        except Exception as e:
            print(f"Proxy error: {e}")

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python proxy.py <ETH0_IP> <LOOPBACK_IP> <PORT>")
        sys.exit(1)
        
    eth0_ip = sys.argv[1]
    lo_ip = sys.argv[2]
    port = int(sys.argv[3])
    
    proxy_port(eth0_ip, lo_ip, port)
