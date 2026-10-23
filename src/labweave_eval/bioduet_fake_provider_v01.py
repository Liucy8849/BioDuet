"""Explicit fake-only native startup fixture; never scientific/model evaluation."""
import hashlib
from http.server import BaseHTTPRequestHandler,HTTPServer
import hmac
import json
from pathlib import Path
import secrets
import threading
import time

from .bioduet_integrity_v01 import need,save,strict


def fake_reply(request,number):
    need(type(request) is dict and request.get('model')=='deepseek-flash','FAKE_MODEL')
    messages=request['messages'];system='\n'.join(str(m.get('content','')) for m in messages if m.get('role')=='system')
    prior=[m for m in messages if m.get('role')=='assistant']
    human='You are an independent simulated human scientist.' in system
    content=None;calls=None
    if human:content='{"kind":"finish"}'
    elif request.get('tools'):
        names=[t['function']['name'] for t in request['tools']]
        name=next((n for n in names if n.endswith('research_wait')),None)
        if name and not any(m.get('tool_calls') for m in prior):
            calls=[{'id':'synthetic-wait','type':'function','function':{
                'name':name,'arguments':'{"until":1}'}}]
        else:content='Synthetic native startup/tool-path probe finished; no scientific result claimed.'
    elif not any('<execute>' in str(m.get('content','')) for m in prior):
        content='<execute>from mcp_servers.research import research_wait\nprint(research_wait(until=1))</execute>'
    else:content='<solution>Synthetic native startup/tool-path probe finished; no scientific result claimed.</solution>'
    message={'role':'assistant','content':content}
    if calls:message['tool_calls']=calls
    return {'id':'synthetic-native-probe-'+str(number),'object':'chat.completion',
        'created':1,'model':'deepseek-flash','choices':[{'index':0,'message':message,
            'finish_reason':'tool_calls' if calls else 'stop'}],
        'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}}


class FakeProvider:
    def __init__(self,window,directory):
        window.require('native-fake',real=True)
        self.window=window;self.root=Path(directory);self.root.mkdir(mode=0o700)
        self.secret=secrets.token_hex(24);self.count=0;self.errors=[];self.closed=False
        secret_root=self.root/'fake-secret';secret_root.mkdir(mode=0o700)
        save(secret_root,'deepseek.json',{'DEEPSEEK_API_KEY':self.secret})
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                status=200;value=None
                try:
                    owner.window.require('native-fake',real=True)
                    self.connection.settimeout(2)
                    need(self.path=='/chat/completions','FAKE_PATH')
                    need(hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+owner.secret),'FAKE_AUTH')
                    size=int(self.headers.get('Content-Length','0'));need(1<=size<=131072,'FAKE_BYTES')
                    body=self.rfile.read(size);need(len(body)==size,'FAKE_INCOMPLETE_BODY')
                    need(owner.count<30,'FAKE_ATTEMPT_LIMIT');owner.count+=1
                    value=fake_reply(strict(body),owner.count)
                except Exception as exc:
                    owner.errors.append(type(exc).__name__);status=400
                    value={'error':{'code':'SYNTHETIC_FIXTURE_REJECTED'}}
                raw=json.dumps(value).encode()
                self.send_response(status);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw)));self.end_headers()
                try:self.wfile.write(raw)
                except OSError:pass
        self.server=HTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.05},daemon=True)
        try:self.thread.start()
        except BaseException:
            self.server.server_close();raise
        self.configuration={'port':self.server.server_port,'fake_secret_dir':str(secret_root)}
    def close(self):
        if self.closed:return self.receipt
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)
        self.closed=True
        self.receipt={'source':'explicit_synthetic_native_probe','requests':self.count,
            'thread_stopped':not self.thread.is_alive(),'listener_closed':self.server.fileno()==-1,
            'errors':self.errors,'actual_model_calls':0,
            'confirmed':not self.thread.is_alive() and self.server.fileno()==-1}
        save(self.root,'fake-provider-cleanup.json',self.receipt)
        return self.receipt
