"""Download the public TDD2022/OEDI-derived synthetic-theft benchmark from Mendeley Data."""
from __future__ import annotations
import argparse
from pathlib import Path
import requests

URL='https://data.mendeley.com/public-files/datasets/c3c7329tjj/files/df.csv/file_downloaded'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('datasets/tdd2022/raw/df.csv'))
    a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    tmp=a.output.with_suffix(a.output.suffix+'.part')
    try:
        with requests.get(URL,stream=True,timeout=(20,180),headers={'User-Agent':'Trust-Fed-Grid-X-research-prototype/1.0'}) as r:
            r.raise_for_status()
            total=0
            with tmp.open('wb') as f:
                for chunk in r.iter_content(1024*1024):
                    if chunk:
                        f.write(chunk);total+=len(chunk)
        if total<1_000_000:raise RuntimeError(f'download too small ({total} bytes); expected the ~61 MB TDD2022 CSV')
        with tmp.open('rb') as f:
            head=f.read(4096).lower()
        if b'<html' in head or b'<!doctype' in head:raise RuntimeError('server returned HTML instead of CSV data')
        tmp.replace(a.output)
        print(f'Downloaded {total:,} bytes to {a.output}')
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
if __name__=='__main__':main()
