"""Exact launched process-group cancellation receipt for trusted fixed R scripts."""
import os
from pathlib import Path
import signal
import subprocess
import time


def members(group):
    found=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            if path.stat().st_uid!=os.getuid():continue
            fields=(path/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2])==group:found.append({'pid':int(path.name),'start_ticks':fields[19]})
        except (FileNotFoundError,ProcessLookupError):continue
    return sorted(found,key=lambda r:r['pid'])


def close_group(process):
    if process is None:
        return {'launcher_reaped':True,'group_members':[],'confirmed':True,'launch_attempted':False}
    errors=[];reaped=False
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    except Exception as exc:errors.append('kill:'+type(exc).__name__)
    try:process.wait(timeout=5);reaped=True
    except Exception as exc:errors.append('reap:'+type(exc).__name__)
    remaining=None
    try:
        deadline=time.monotonic()+2
        while True:
            remaining=members(process.pid)
            if not remaining or time.monotonic()>=deadline:break
            time.sleep(.02)
    except Exception as exc:errors.append('census:'+type(exc).__name__)
    return {'process_group':process.pid,'launcher_reaped':reaped,'group_members':remaining,
            'confirmed':bool(reaped and remaining==[] and not errors),'errors':errors,
            'launch_attempted':True,'scope':'launched group; fixed trusted R script only'}
