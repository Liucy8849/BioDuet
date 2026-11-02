"""Portable integrity and append-only output helpers extracted without semantic changes."""
import hashlib,json,os,stat
from pathlib import Path

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
