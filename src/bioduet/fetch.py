"""Explicit operator data acquisition; never called by a participant."""
import hashlib,json,pathlib,re,urllib.request

def fetch(manifest, output, *, maximum_bytes=100_000_000):
    document=json.loads(pathlib.Path(manifest).read_text())
    rows=document["files"]
    if not isinstance(rows,list) or not rows:raise ValueError("FILES_REQUIRED")
    names=set();total=0
    for row in rows:
        if set(row)!={"name","url","bytes","sha256"}:raise ValueError("ROW_SCHEMA")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,120}",row["name"]):raise ValueError("NAME")
        if row["name"] in {"acquisition.json","failure.txt"} or row["name"].endswith(".partial"):raise ValueError("RESERVED_NAME")
        if row["name"] in names:raise ValueError("DUPLICATE_NAME")
        names.add(row["name"])
        if type(row["bytes"]) is not int or row["bytes"]<=0:raise ValueError("SIZE")
        total+=row["bytes"]
        if not re.fullmatch(r"[0-9a-f]{64}",row["sha256"]):raise ValueError("SHA256")
        if not row["url"].startswith("https://"):raise ValueError("HTTPS_REQUIRED")
    if total>maximum_bytes:raise ValueError("OPERATOR_BYTE_LIMIT")
    out=pathlib.Path(output);out.mkdir(mode=0o700,parents=True,exist_ok=False)
    receipts=[]
    try:
        for row in rows:
            receipt={"name":row["name"],"status":"started"};receipts.append(receipt)
            digest=hashlib.sha256();size=0
            partial=out/(row["name"]+".partial")
            with urllib.request.urlopen(row["url"],timeout=30) as response,partial.open("xb") as stream:
                if not response.url.startswith("https://"):raise ValueError("HTTPS_REDIRECT_REQUIRED")
                while True:
                    block=response.read(min(65536,row["bytes"]+1-size))
                    if not block:break
                    size+=len(block);stream.write(block);digest.update(block)
                    if size>row["bytes"]:raise ValueError("SIZE_EXCEEDED")
            receipt.update(bytes=size,sha256=digest.hexdigest())
            if size!=row["bytes"] or digest.hexdigest()!=row["sha256"]:raise ValueError("SOURCE_MISMATCH")
            partial.rename(out/row["name"]);receipt["status"]="verified"
    except Exception as exc:
        if receipts:
            receipts[-1]["status"]="failed"
            receipts[-1]["failure_type"]=type(exc).__name__
        import traceback
        (out/"failure.txt").write_text(traceback.format_exc())
        raise
    finally:
        (out/"acquisition.json").write_text(json.dumps(receipts,indent=2)+"\n")
    return receipts

def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest");p.add_argument("output")
    p.add_argument("--maximum-bytes",type=int,default=100_000_000)
    a=p.parse_args();fetch(a.manifest,a.output,maximum_bytes=a.maximum_bytes)
if __name__=="__main__":main()
