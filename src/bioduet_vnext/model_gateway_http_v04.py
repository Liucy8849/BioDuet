"""HTTP surface for a separately isolated credential worker. No server starts on import."""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from .model_gateway_v04 import CredentialBroker
from .contracts_v01 import require

def serve_http(broker,*,host,port):
    require(type(broker) is CredentialBroker and host=="127.0.0.1" and
            type(port) is int and 0<=port<=65535,"GATEWAY_BIND")
    class Handler(BaseHTTPRequestHandler):
        protocol_version="HTTP/1.0"
        def setup(self):
            super().setup();self.connection.settimeout(15)
        def log_message(self,*args):pass # No Authorization/header values in access logs.
        def do_GET(self):
            self.send_error(404)
        def do_POST(self):
            reply=None;entered=False
            try:
                require(self.headers.get("Transfer-Encoding") is None,"GATEWAY_TRANSFER_ENCODING")
                length=self.headers.get_all("Content-Length",[])
                require(len(length)==1 and length[0].isascii() and length[0].isdigit(),"GATEWAY_CONTENT_LENGTH")
                size=int(length[0]);require(0<size<=broker.max_request,"GATEWAY_BODY_LIMIT")
                require(self.headers.get("Content-Type","").split(";",1)[0].strip()=="application/json",
                        "GATEWAY_CONTENT_TYPE")
                auth=self.headers.get_all("Authorization",[])
                require(len(auth)==1 and auth[0].startswith("Bearer "),"GATEWAY_AUTH")
                raw=self.rfile.read(size);require(len(raw)==size,"GATEWAY_SHORT_BODY")
                entered=True
                reply=broker.request(auth[0][7:],self.path,raw)
                self.send_response(reply.status);self.send_header("Content-Type",reply.media_type)
                self.send_header("Cache-Control","no-store");self.end_headers()
                for chunk in reply.chunks:self.wfile.write(chunk);self.wfile.flush()
            except Exception:
                if reply is None:
                    self.send_response(502 if entered else 403);self.send_header("Content-Type","application/json");self.end_headers()
                    self.wfile.write(b'{"error":{"code":"GATEWAY_FAILURE_UNKNOWN_OR_REJECTED"}}')
                # Disconnected/partial dispatched response is not retried here.
            finally:
                if reply is not None and callable(getattr(reply.chunks,"close",None)):
                    reply.chunks.close()
    server=ThreadingHTTPServer((host,port),Handler)
    server.daemon_threads=False
    return server # Supervisor declares READY, controls activation/stop and cgroup cleanup.
