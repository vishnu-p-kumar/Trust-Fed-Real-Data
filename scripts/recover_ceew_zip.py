"""Recover complete ZIP local-file members from a truncated CEEW upload archive.

The archive is scanned using ZIP local headers and ZIP64 size fields. A member is
accepted only when its compressed payload is complete, decompression succeeds,
uncompressed size matches, and CRC32 matches. Partial members are reported/skipped.
"""
from __future__ import annotations
import argparse, binascii, json, struct, zlib
from pathlib import Path

LOCAL=b"PK\x03\x04"
def recover(archive: Path, output: Path) -> dict:
    blob=archive.read_bytes()
    offsets=[]; start=0
    while True:
        pos=blob.find(LOCAL,start)
        if pos<0: break
        offsets.append(pos); start=pos+4
    output.mkdir(parents=True,exist_ok=True)
    recovered=[]; skipped=[]
    for idx,off in enumerate(offsets):
        try:
            sig,ver,flag,method,mt,md,crc,csize32,usize32,fnlen,exlen=struct.unpack_from("<IHHHHHIIIHH",blob,off)
            name=blob[off+30:off+30+fnlen].decode("utf-8",errors="replace")
            extra=blob[off+30+fnlen:off+30+fnlen+exlen]
            csize,usize=csize32,usize32
            j=0
            while j+4<=len(extra):
                tag,n=struct.unpack_from("<HH",extra,j); val=extra[j+4:j+4+n]
                if tag==1:
                    k=0
                    if usize32==0xffffffff: usize=struct.unpack_from("<Q",val,k)[0]; k+=8
                    if csize32==0xffffffff: csize=struct.unpack_from("<Q",val,k)[0]
                    break
                j+=4+n
            data_start=off+30+fnlen+exlen; data_end=data_start+csize
            next_off=offsets[idx+1] if idx+1<len(offsets) else len(blob)
            if data_end>next_off or data_end>len(blob):
                skipped.append({"member":name,"reason":"compressed payload truncated",
                                "expected_compressed_bytes":csize,"available_bytes":max(0,next_off-data_start)})
                continue
            payload=blob[data_start:data_end]
            if method==8: raw=zlib.decompress(payload,-15)
            elif method==0: raw=payload
            else:
                skipped.append({"member":name,"reason":f"unsupported ZIP compression method {method}"})
                continue
            actual_crc=binascii.crc32(raw)&0xffffffff
            if len(raw)!=usize or actual_crc!=crc:
                skipped.append({"member":name,"reason":"uncompressed size or CRC32 mismatch"})
                continue
            safe_name=Path(name).name
            if not safe_name or safe_name in {".",".."}:
                skipped.append({"member":name,"reason":"unsafe/empty filename"}); continue
            target=output/safe_name; target.write_bytes(raw)
            recovered.append({"member":name,"output":str(target),"bytes":len(raw),"crc32":"%08x"%actual_crc})
        except Exception as exc:
            skipped.append({"offset":off,"reason":str(exc)})
    report={"archive":str(archive),"archive_bytes":len(blob),"local_headers_found":len(offsets),
            "recovered":recovered,"skipped":skipped,
            "note":"No central directory is required; only complete members with verified CRC32 are extracted."}
    (output/"recovery_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",required=True,type=Path)
    p.add_argument("--output-dir",default=Path("datasets/ceew/recovered"),type=Path)
    a=p.parse_args(); result=recover(a.archive,a.output_dir)
    print(json.dumps({"recovered_members":len(result["recovered"]),
        "skipped_members":len(result["skipped"]),
        "recovered_names":[Path(x["member"]).name for x in result["recovered"]],
        "skipped":result["skipped"]},indent=2))
if __name__=="__main__": main()
