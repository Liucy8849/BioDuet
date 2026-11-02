"""Portable, private-by-default evidence files. No provider or world imports."""
import hashlib,json,os
from pathlib import Path

def file_ref(path):
    path=Path(path)
    return {'name':path.name,'bytes':path.stat().st_size,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def save_new(path,value):
    data=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    if len(data)>16*1024**2:raise ValueError('REPORT_LIMIT')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    return file_ref(path)

def source_manifest():
    root=Path(__file__).parent
    return [file_ref(p) for p in sorted(root.glob('bw01_*')) if p.suffix in ('.py','.R','.json')]

class RoleAdmissionJournal(list):
    """Persist exact owned role unit names before any role process is launched."""
    def __init__(self,directory):
        super().__init__();self.directory=Path(directory)
    def append(self,record):
        import re
        if record.get('role') not in ('A','H') or not re.fullmatch(r'bioduet-bw01-[0-9a-f]{32}\.scope',record.get('unit','')):
            raise ValueError('ROLE_ADMISSION_IDENTITY')
        save_new(self.directory/('role-'+record['role']+'-admission.json'),
                 {'role':record['role'],'unit':record['unit'],'state':'starting'})
        super().append(record)
