"""Trusted, SHA-pinned finite BioDuet window. Never an application authority.

The pin and grant file are supplied by the operator from Root's fresh resource
receipt, never by a participant. Synthetic grants cannot authorize real work.
Append-only window reservations count failed/unknown operations without refund.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time

PROJECT = Path(__file__).resolve().parents[2]
SCHEMA = 'bioduet-finite-window/1'
PHASES = {'prehistory', 'reference', 'native-fake', 'native-live'}
FIELDS = {'schema','kind','grant_id','issued_epoch','expires_epoch','window_root',
          'allowed_phases','cpu','memory_total_bytes','model','max_model_calls',
          'max_episodes','max_analysis_operations','episode_seconds',
          'source_manifest_sha256','runtime_tree_sha256','counts_sha256'}


def need(ok, code):
    if not ok:raise ValueError(code)


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def digest_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):h.update(block)
    return h.hexdigest()


def strict(raw):
    def pairs(rows):
        result={}
        for key,value in rows:
            need(key not in result,'DUPLICATE_JSON_KEY');result[key]=value
        return result
    def constant(value):raise ValueError('NONFINITE_JSON')
    value=json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
    encoded(value)
    return value


def pinned(path, pin, *, maximum=4*1024**2, allow_empty=False):
    path=Path(path)
    need(path.is_absolute() and path.resolve(strict=True)==path,'PINNED_PATH')
    need(type(pin) is str and len(pin)==64 and all(c in '0123456789abcdef' for c in pin),'PIN')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and
             (0 if allow_empty else 1)<=before.st_size<=maximum,'PINNED_REGULAR_FILE')
        raw=b''
        while len(raw)<=maximum:
            block=os.read(fd,min(65536,maximum+1-len(raw)))
            if not block:break
            raw+=block
        after=os.fstat(fd)
        keys=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        need(keys(before)==keys(after) and len(raw)==before.st_size,'PINNED_FILE_CHANGED')
        need(hashlib.sha256(raw).hexdigest()==pin,'PIN_MISMATCH')
        return raw
    finally:os.close(fd)


def save(directory, name, value):
    need(type(name) is str and name and '/' not in name and name not in ('.','..'),'FILE_NAME')
    directory=Path(directory)
    need(directory.is_absolute() and directory.resolve(strict=True)==directory,'OUTPUT_DIRECTORY')
    st=directory.stat()
    need(st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o700,'PRIVATE_OUTPUT')
    raw=encoded(value)+b'\n'
    fd=os.open(directory/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        offset=0
        while offset<len(raw):
            n=os.write(fd,raw[offset:]);need(n>0,'SHORT_WRITE');offset+=n
        os.fsync(fd)
    finally:os.close(fd)
    dfd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(dfd)
    finally:os.close(dfd)
    return {'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


class FreshWindow:
    def __init__(self, document, grant_pin, source_manifest, *, wall=time.time, mono=time.monotonic):
        need(type(document) is dict and set(document)==FIELDS and document['schema']==SCHEMA,'WINDOW_SCHEMA')
        d=document
        need(d['kind'] in ('root_window','synthetic') and type(d['kind']) is str,'WINDOW_KIND')
        need(type(d['grant_id']) is str and 1<=len(d['grant_id'])<=128,'GRANT_ID')
        need(type(d['allowed_phases']) is list and d['allowed_phases'] and
             all(type(x) is str and x in PHASES for x in d['allowed_phases']) and
             len(set(d['allowed_phases']))==len(d['allowed_phases']),'PHASES')
        need(type(d['cpu']) is int and d['cpu']==3,'CPU')
        need(type(d['memory_total_bytes']) is int and 256*1024**2<=d['memory_total_bytes']<=4*1024**3,'MEMORY')
        need(d['model']=='deepseek-flash','MODEL')
        for key,lo,hi in [('max_model_calls',0,180),('max_episodes',1,6),
                          ('max_analysis_operations',0,48),('episode_seconds',30,1200)]:
            need(type(d[key]) is int and lo<=d[key]<=hi,key.upper())
        for key in ('issued_epoch','expires_epoch'):
            need(type(d[key]) in (int,float) and 0<d[key]<10**11,'WINDOW_CLOCK')
        now=wall()
        need(d['issued_epoch']<=now<d['expires_epoch'] and d['expires_epoch']-d['issued_epoch']<=7200,'WINDOW_EXPIRED_OR_TOO_LONG')
        need(type(source_manifest) is dict and source_manifest.get('schema')=='bioduet-executable-source-manifest/1'
             and sha(source_manifest)==d['source_manifest_sha256'],'SOURCE_MANIFEST_BINDING')
        need(type(source_manifest.get('files')) is list and 1<=len(source_manifest['files'])<=256,'SOURCE_FILES')
        for ref in source_manifest['files']:
            need(type(ref) is dict and set(ref)=={'path','sha256'},'SOURCE_REFERENCE')
            f=Path(ref['path'])
            need(f.is_absolute() and PROJECT in f.parents and f.resolve(strict=True)==f,'SOURCE_LOCATION')
            need(digest_file(f)==ref['sha256'],'SOURCE_CHANGED')
        root=Path(d['window_root'])
        need(root.is_absolute() and root.resolve(strict=True)==root and PROJECT in root.parents,'WINDOW_ROOT')
        info=root.stat()
        need(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'WINDOW_ROOT_PRIVATE')
        self.document=json.loads(encoded(d))
        self.pin=grant_pin;self.root=root;self.wall=wall;self.mono=mono
        self.deadline=mono()+(d['expires_epoch']-now)
        self._episode=None

    @classmethod
    def load(cls, grant_path, grant_pin, source_path, *, wall=time.time, mono=time.monotonic):
        doc=strict(pinned(grant_path,grant_pin,maximum=65536))
        source_raw=Path(source_path).read_bytes()
        need(len(source_raw)<=1024**2,'SOURCE_MANIFEST_SIZE')
        manifest=strict(source_raw)
        return cls(doc,grant_pin,manifest,wall=wall,mono=mono)

    def remaining(self, *, reserve=0):
        value=min(self.deadline-self.mono(),self.document['expires_epoch']-self.wall())-reserve
        need(value>0,'WINDOW_DEADLINE')
        return value

    def require(self, phase, *, real=False):
        need(type(phase) is str and phase in self.document['allowed_phases'],'PHASE_NOT_GRANTED')
        need(not real or self.document['kind']=='root_window','SYNTHETIC_CANNOT_AUTHORIZE_REAL_WORK')
        self.remaining()
        return self

    def _reserve(self, kind, identity, *, limit):
        self.remaining()
        need(kind in ('episode','model','analysis'),'RESERVATION_KIND')
        fd=os.open(self.root/'reservations.jsonl',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            st=os.fstat(fd)
            need(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1
                 and stat.S_IMODE(st.st_mode)==0o600 and st.st_size<=512*1024,'RESERVATION_FILE')
            raw=os.read(fd,512*1024+1);records=[strict(x) for x in raw.splitlines()]
            previous='0'*64
            for n,record in enumerate(records):
                need(type(record) is dict and set(record)=={'sequence','previous','grant_id','kind','identity','epoch','sha256'}
                     and type(record['kind']) is str and record['kind'] in ('episode','model','analysis')
                     and type(record['identity']) is str and 1<=len(record['identity'])<=256
                     and type(record['sequence']) is int,'RESERVATION_SCHEMA')
                body={k:v for k,v in record.items() if k!='sha256'}
                need(record['sequence']==n and record['previous']==previous and record['grant_id']==self.document['grant_id']
                     and record['sha256']==sha(body),'RESERVATION_CHAIN')
                previous=record['sha256']
            need(sum(r['kind']==kind for r in records)<limit,'WINDOW_'+kind.upper()+'_LIMIT')
            if kind=='episode':need(not any(r['kind']=='episode' and r['identity']==identity for r in records),'EPISODE_REUSE')
            self.remaining()
            body={'sequence':len(records),'previous':previous,'grant_id':self.document['grant_id'],
                  'kind':kind,'identity':identity,'epoch':self.wall()}
            data=encoded(dict(body,sha256=sha(body)))+b'\n'
            need(len(raw)+len(data)<=512*1024,'RESERVATION_FILE_LIMIT')
            os.lseek(fd,0,os.SEEK_END)
            offset=0
            while offset<len(data):
                n=os.write(fd,data[offset:]);need(n>0,'SHORT_WRITE');offset+=n
            os.fsync(fd)
            dfd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(dfd)
            finally:os.close(dfd)
            return body
        finally:os.close(fd)

    def claim(self, episode_id, phase, *, real=False):
        self.require(phase,real=real)
        need(self._episode is None and type(episode_id) is str and 1<=len(episode_id)<=128,'EPISODE_ID')
        self._reserve('episode',episode_id,limit=self.document['max_episodes'])
        self._episode=episode_id;self.phase=phase
        return self

    def model_slot(self):
        need(self._episode is not None,'EPISODE_NOT_CLAIMED')
        return self._reserve('model',self._episode,limit=self.document['max_model_calls'])

    def analysis_slot(self, label, *, real=True):
        need(self._episode is not None and type(label) is str and 1<=len(label)<=128,'ANALYSIS_ID')
        need(not real or self.document['kind']=='root_window','SYNTHETIC_CANNOT_AUTHORIZE_REAL_WORK')
        return self._reserve('analysis',self._episode+':'+label,limit=self.document['max_analysis_operations'])
