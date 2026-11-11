"""RFC 6238 TOTP primitives for MFA integration (secret provisioning is external)."""
from __future__ import annotations
import base64, hashlib, hmac, struct, time

def generate_secret(nbytes=20):
    import secrets
    return base64.b32encode(secrets.token_bytes(nbytes)).decode().rstrip("=")

def code(secret: str, timestamp: int | None=None, period: int=30, digits: int=6) -> str:
    if period<1 or digits not in (6,8): raise ValueError("invalid TOTP parameters")
    normalized=secret.strip().upper()
    key=base64.b32decode(normalized+"="*((8-len(normalized)%8)%8))
    counter=int((time.time() if timestamp is None else timestamp)//period)
    digest=hmac.new(key,struct.pack(">Q",counter),hashlib.sha1).digest()
    offset=digest[-1]&0x0f
    binary=struct.unpack(">I",digest[offset:offset+4])[0]&0x7fffffff
    return str(binary%(10**digits)).zfill(digits)

def verify(secret: str, token: str, *, timestamp: int | None=None, window: int=1) -> bool:
    if not token.isdigit() or len(token) not in (6,8): return False
    now=int(time.time() if timestamp is None else timestamp)
    return any(hmac.compare_digest(code(secret,now+offset*30,digits=len(token)),token)
               for offset in range(-window,window+1))
