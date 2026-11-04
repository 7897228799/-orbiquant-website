"""Public Orbiquant promotional API: deliberately READ ONLY, no trading/auth/payment endpoints.

For market display, operator must provide a commercially licensed public-display quote endpoint.
The configured endpoint must return JSON matching docs/PROMO_FEED_CONTRACT.md.
No broker customer credentials are accepted or loaded by this app.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
app = FastAPI(title='Orbiquant Public Website', version='promo-1.0.0', docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[s.strip() for s in os.getenv('PROMO_ALLOWED_ORIGINS', 'http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:5176,http://localhost:5177,http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5175,http://127.0.0.1:5176,http://127.0.0.1:5177').split(',') if s.strip()], allow_credentials=True, allow_methods=['GET','POST','PATCH','DELETE','OPTIONS'], allow_headers=['Content-Type'])

MARKETS = [('NIFTY', 'NIFTY 50', 'NSE'), ('BANKNIFTY', 'BANK NIFTY', 'NSE'), ('SENSEX', 'SENSEX', 'BSE')]

def allowed_public_link(link, hosts):
    if not link: return ''
    try:
        u = urlparse(link)
        return link if u.scheme == 'https' and u.hostname in hosts and not u.username and not u.password else ''
    except (ValueError, TypeError):
        return ''

@app.get('/api/health')
def health():
    return {'ok':True,'service':'orbiquant-public-promo','trading_enabled':False,'payments_enabled':False,'broker_connections_enabled':False,'promo_accounts_enabled':True}

@app.get('/api/public/config')
def promo_config():
    return {
        'play_store_url':allowed_public_link(os.getenv('ORBIQUANT_PLAY_STORE_URL',''),{'play.google.com'}),
        'whatsapp_channel_url':allowed_public_link((os.getenv('ORBIQUANT_WHATSAPP_CHANNEL_URL') or 'https://wa.me/918103571528'),{'wa.me','whatsapp.com','www.whatsapp.com'}),
        'telegram_url':allowed_public_link((os.getenv('ORBIQUANT_TELEGRAM_URL') or 'https://t.me/Orbiquant'),{'t.me','telegram.me','www.t.me'}),
        'customer_care_phone': '8103571528',
        'support_email': 'support@orbiquant.in',
        'trading_enabled':False,
        'payment_enabled':False,
    }

def parse_iso(date_str):
    if not isinstance(date_str, str): return None
    try:
        dt=datetime.fromisoformat(date_str.replace('Z','+00:00'))
        if dt.tzinfo is None: return None
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None

def normalize_market(payload):
    """Never publish a quote as live if it is stale/unverified or lacking required data."""
    now=datetime.now(timezone.utc)
    out=[]
    by_symbol = payload.get('quotes',{}) if isinstance(payload,dict) else {}
    if isinstance(by_symbol,list):
        by_symbol={x.get('symbol'):x for x in by_symbol if isinstance(x,dict)}
    if not isinstance(by_symbol,dict): by_symbol={}
    source=payload.get('source','') if isinstance(payload,dict) else ''
    for symbol,name,exchange in MARKETS:
        raw=by_symbol.get(symbol,{})
        raw=raw if isinstance(raw,dict) else {}
        stamp=parse_iso(raw.get('asof'))
        age=(now-stamp).total_seconds() if stamp else None
        price=raw.get('price')
        displayable=(isinstance(price,(int,float)) and not isinstance(price,bool)
                     and 0 < price < 1e8 and age is not None and -30 <= age <= 180
                     and isinstance(source,str) and len(source.strip())>=2
                     and raw.get('exchange',exchange)==exchange)
        def valid_metric(x):
            return round(float(x),2) if isinstance(x,(int,float)) and not isinstance(x,bool) and abs(x)<1e8 else None
        out.append({'symbol':symbol,'name':name,'exchange':exchange,
                    'status':'delayed' if displayable and raw.get('delayed') else ('live' if displayable else 'unavailable'),
                    'price':valid_metric(price) if displayable else None,
                    'change':valid_metric(raw.get('change')) if displayable else None,
                    'change_percent':valid_metric(raw.get('change_percent')) if displayable else None,
                    'asof':stamp.isoformat() if displayable else None})
    return {'source':source.strip()[:80] if any(x['status']!='unavailable' for x in out) else None,
            'quotes':out, 'trading_enabled':False, 'notice':'Display-only market data. No orders or account access.'}

@app.get('/api/public/markets')
async def public_markets():
    empty=normalize_market({})
    if os.getenv('PUBLIC_MARKET_DISPLAY_AUTHORIZED','false').lower()!='true':
        return {**empty,'feed_status':'not_authorized'}
    target=os.getenv('PROMO_MARKET_FEED_URL','').strip()
    try:
        url=urlparse(target)
        if url.scheme!='https' or not url.hostname or url.username or url.password:
            return {**empty,'feed_status':'not_configured'}
    except ValueError:
        return {**empty,'feed_status':'not_configured'}
    # Single server-side connector, never fetched from a browser-supplied URL.
    headers={'Accept':'application/json'}
    token=os.getenv('PROMO_MARKET_FEED_TOKEN','').strip()
    if token: headers['Authorization']=f'Bearer {token}'
    try:
        async with httpx.AsyncClient(timeout=5.0,follow_redirects=False) as client:
            response=await client.get(target,headers=headers)
            response.raise_for_status()
            if len(response.content)>100000: raise ValueError('Feed too large')
            payload=response.json()
        out=normalize_market(payload)
        return {**out,'feed_status':'ok' if any(q['status']!='unavailable' for q in out['quotes']) else 'no_fresh_quotes'}
    except (httpx.HTTPError,ValueError,TypeError,json.JSONDecodeError):
        return {**empty,'feed_status':'unavailable'}

# Promotional account endpoints ONLY; no portfolio, payments, broker tokens, strategies or orders.
from .leads import router as leads_router
app.include_router(leads_router)
from .performance import router as performance_router
app.include_router(performance_router)
from .local_broker_market import router as local_market_router
app.include_router(local_market_router)
from .angel_live_ws import router as angel_stream_router
app.include_router(angel_stream_router)
# Always respond 404 for other API paths, even when a SPA frontend is mounted at /.
@app.api_route('/api/{rest_of_path:path}',methods=['GET','POST','PUT','PATCH','DELETE'])
def reject_other_api(rest_of_path:str):
    return JSONResponse(status_code=404,content={'detail':'Not available on the promotional website'})
