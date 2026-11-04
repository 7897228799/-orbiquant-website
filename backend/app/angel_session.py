"""Local-only Angel refresh-token management. No PIN/TOTP storage or login bypass."""
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ENV_FILE = Path(__file__).resolve().parents[1] / '.env'
LOCK = asyncio.Lock()
URL = 'https://apiconnect.angelone.in/rest/auth/angelbroking/jwt/v1/generateTokens'

def _jwt_expired_soon(token, margin=120):
    """Decode JWT expiry for hint only; actual validity decided by broker."""
    if not token:
        return True
    try:
        import base64
        payload = token.split('.')[1]
        value = json.loads(base64.urlsafe_b64decode(payload + '='*(-len(payload)%4)))
        exp = value.get('exp')
        return exp is not None and float(exp) <= time.time()+margin
    except (IndexError, ValueError, TypeError):
        return False

def _set_values(values):
    # Replace only Angel session values; don't rewrite any other project configuration.
    old = ENV_FILE.read_text(encoding='utf-8') if ENV_FILE.exists() else ''
    kept = [line for line in old.splitlines() if not (line.partition('=')[0].strip() in values and '=' in line and not line.lstrip().startswith('#'))]
    tmp = ENV_FILE.with_name('.env.angel-tmp')
    tmp.write_text('\n'.join(kept + [f'{k}={v}' for k,v in values.items()])+'\n', encoding='utf-8')
    if os.name != 'nt': tmp.chmod(0o600)
    tmp.replace(ENV_FILE)
    os.environ.update(values)

async def ensure_session(force=False):
    """Refresh a still-authorized session; on rejection require interactive broker TOTP login."""
    async with LOCK:
        jwt = os.getenv('LOCAL_ANGEL_ACCESS_TOKEN','').strip()
        feed = os.getenv('LOCAL_ANGEL_FEED_TOKEN','').strip()
        if not force and jwt and feed and not _jwt_expired_soon(jwt):
            return jwt, feed
        refresh = os.getenv('LOCAL_ANGEL_REFRESH_TOKEN','').strip()
        key = os.getenv('LOCAL_ANGEL_API_KEY','').strip()
        if not refresh or not key:
            raise RuntimeError('Re-login needed: refresh token missing. Run py -3 CONFIGURE_ANGEL_ONE_LOCAL.py')
        headers = {'Accept':'application/json','Content-Type':'application/json', 'X-PrivateKey':key,
                   'X-UserType':'USER','X-SourceID':'WEB'}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(URL,headers=headers,json={'refreshToken':refresh})
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError,ValueError) as exc:
            raise RuntimeError('Unable to renew Angel token; check network or re-login locally.') from exc
        values = payload.get('data') or {}
        if payload.get('status') is not True or not values.get('jwtToken') or not values.get('feedToken'):
            raise RuntimeError('Angel refresh rejected/session ended. Re-login with fresh TOTP using CONFIGURE_ANGEL_ONE_LOCAL.py')
        updated = {'LOCAL_ANGEL_ACCESS_TOKEN':values['jwtToken'],
                   'LOCAL_ANGEL_FEED_TOKEN':values['feedToken'],
                   'LOCAL_ANGEL_REFRESH_TOKEN':values.get('refreshToken') or refresh}
        _set_values(updated)
        return updated['LOCAL_ANGEL_ACCESS_TOKEN'], updated['LOCAL_ANGEL_FEED_TOKEN']
