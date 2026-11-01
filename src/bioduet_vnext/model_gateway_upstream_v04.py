"""HTTPS transport inside the isolated credential worker only.
No credential lookup or network until after broker admission. Fixed upstream
routing, public CA pin, no redirects/retries, credentials filtered in the same
private worker before any model response can reach the actor.
"""
import hashlib,http.client,json,math,ssl,time
from pathlib import Path
from .contracts_v01 import require,sha
from .model_gateway_v04 import ProviderStream,ProviderNotDispatched
class HTTPSUpstream:
    def __init__(self,*,host,path,ca_path,ca_sha256,authorization_headers,clock=time.monotonic):
        require(type(host) is str and host and "/" not in host and ":" not in host and
                type(path) is str and path.startswith("/") and "\r" not in path and "\n" not in path,
                "FIXED_UPSTREAM")
        require(sha(ca_sha256) and callable(authorization_headers),"PROVIDER_AUTH_SOURCE")
        raw=Path(ca_path).read_bytes();require(hashlib.sha256(raw).hexdigest()==ca_sha256,"PROVIDER_CA_PIN")
        self.context=ssl.create_default_context(cafile=str(ca_path))
        self.host=host;self.path=path;self.headers=authorization_headers;self.clock=clock
    def __call__(self,raw,deadline):
        # Everything before conn.request is known not to dispatch upstream.
        try:
            remaining=deadline-self.clock()
            require(math.isfinite(remaining) and remaining>0,"PROVIDER_DEADLINE")
            headers=self.headers()
            require(type(headers) is dict and headers and all(
                type(k) is str and type(v) is str and "\r" not in k+v and "\n" not in k+v
                and "\x00" not in k+v for k,v in headers.items()),"PROVIDER_AUTH_HEADERS")
            require(all(k.lower() in {"authorization","api-key","x-api-key","openai-organization","openai-project"}
                        for k in headers),"PROVIDER_AUTH_HEADER_SCOPE")
            credential_values=[]
            for key,value in headers.items():
                if key.lower() in ("authorization","api-key","x-api-key"):
                    if key.lower()=="authorization":
                        require(value.lower().startswith("bearer "),"PROVIDER_BEARER_ONLY")
                    token=value[7:] if value.lower().startswith("bearer ") else value
                    require(len(token)>=16,"PROVIDER_CREDENTIAL_LENGTH")
                    credential_values.extend([token.encode(),json.dumps(token)[1:-1].encode()])
            require(bool(credential_values),"PROVIDER_AUTH_REQUIRED")
            conn=http.client.HTTPSConnection(self.host,443,context=self.context,timeout=remaining)
        except Exception as exc:raise ProviderNotDispatched(type(exc).__name__) from None
        try:
            conn.request("POST",self.path,body=raw,headers={
                "Content-Type":"application/json","Accept":"application/json, text/event-stream",**headers})
            response=conn.getresponse()
            def chunks():
                while True:
                    left=deadline-self.clock();require(math.isfinite(left) and left>0,"PROVIDER_DEADLINE")
                    if conn.sock is not None:conn.sock.settimeout(left)
                    chunk=response.read1(65536)
                    if not chunk:break
                    yield chunk
            return ProviderStream(response.status,response.getheader("Content-Type",""),chunks(),
                                  conn.close,tuple(credential_values))
        except BaseException:
            conn.close();raise
