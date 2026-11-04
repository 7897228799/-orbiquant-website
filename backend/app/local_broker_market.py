"""LOCAL-ONLY read-only market quotes from your own official broker API account.
Never deploy this endpoint for paid/public redistribution. Never places orders.
Secrets from local backend/.env only, never from browser or query string.
"""
import os
import re
import time
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from .promo_main import normalize_market
import httpx

router=APIRouter(prefix='/api/local', tags=['local-private-market-data'])
BROKERS=('Angel One','Zerodha','Dhan','Motilal Oswal')
KEYS={'NIFTY':('NSE','NIFTY 50'),'BANKNIFTY':('NSE','NIFTY BANK'),'SENSEX':('BSE','SENSEX')}

def only_local(request:Request):
    mode=os.getenv('APP_ENV','development').lower()
    enabled=os.getenv('LOCAL_PRIVATE_QUOTES_ENABLED','false').lower()=='true'
    client=request.client.host if request.client else None
    # Avoid any remote production exposure, including via reverse proxies.
    if mode in ('production','prod') or not enabled or client not in ('127.0.0.1','::1','localhost'):
        raise HTTPException(404,'Not available on public website')

def env(name):return os.getenv(name,'').strip()

def entry(prices, broker):
    stamp=datetime.now(timezone.utc).isoformat()
    quotes={name:{'price':v,'exchange':KEYS[name][0],'asof':stamp,'delayed':True} for name,v in prices.items()}
    data=normalize_market({'source':broker+' / own broker account (snapshot)','quotes':quotes})
    # HTTP response timestamp is NOT exchange trade timestamp. Do not falsely label it LIVE.
    for q in data['quotes']:
        if q['status']!='unavailable':q['status']='snapshot_time_unverified'
    return {**data,'feed_status':'quotes_received','usage':'private_local_only','note':'Read-only LTP snapshot. Exchange quote timestamps not independently verified. No real orders.'}

# Index codes are discovered from the broker's own authenticated index-master API.
# Do not guess/bake in instrument identifiers that can change.
_MOTILAL_INDEX_CACHE = {}
_MOTILAL_INDEX_CACHE_TTL_SECONDS = 21600

def _index_label(value):
    return re.sub(r'[^a-z0-9]+', ' ', str(value).lower()).strip()

def _index_matches(name, label):
    normalized = _index_label(label)
    if name == 'NIFTY':
        return normalized in ('nifty', 'nifty 50', 'nifty50', 'nifty 50 index')
    if name == 'BANKNIFTY':
        return normalized in ('nifty bank', 'bank nifty', 'banknifty')
    return normalized in ('sensex', 's p bse sensex', 'bse sensex', 's p sensex')

def _motilal_headers():
    # MOFSL's official docs require BOTH the broker auth token and access token.
    # App Key is created on the official Motilal Oswal API portal.
    names={
        'ApiKey':'LOCAL_MOTILAL_API_KEY',
        'apisecretkey':'LOCAL_MOTILAL_API_SECRET',
        'Authorization':'LOCAL_MOTILAL_AUTH_TOKEN',
        'accesstoken':'LOCAL_MOTILAL_ACCESS_TOKEN',
        'vendorinfo':'LOCAL_MOTILAL_CLIENT_ID',
        'ClientPublicIp':'LOCAL_MOTILAL_PUBLIC_IP',
        'ClientLocalIp':'LOCAL_MOTILAL_LOCAL_IP',
        'MacAddress':'LOCAL_MOTILAL_MAC',
    }
    missing=[env(k) for k in names.values() if not env(k)]
    if missing:
        raise HTTPException(412,'Motilal API setup missing: '+', '.join(missing)+'. Configure in LOCAL backend/.env only.')
    return {
        'Accept':'application/json', 'Content-Type':'application/json',
        'User-Agent':'MOSL/V.1.1.0',
        'SourceId':'WEB',
        'osname':env('LOCAL_MOTILAL_OS_NAME') or 'Windows 10',
        'osversion':env('LOCAL_MOTILAL_OS_VERSION') or '10.0',
        'devicemodel':env('LOCAL_MOTILAL_DEVICE_MODEL') or 'PC',
        'manufacturer':env('LOCAL_MOTILAL_DEVICE_MANUFACTURER') or 'Self-built',
        'productname':'Orbiquant Local Market Viewer', 'productversion':'1.0',
        'browsername':'Chrome', 'browserversion':env('LOCAL_MOTILAL_BROWSER_VERSION') or '1',
        **{header:env(var) for header,var in names.items()},
    }

def _broker_rows(response):
    if not isinstance(response,dict) or str(response.get('status','')).upper()!='SUCCESS':
        raise HTTPException(502,'Motilal API rejected the market-data request; verify auth token/permissions')
    data=response.get('data') or []
    if isinstance(data,dict): data=[data]
    return [d for d in data if isinstance(d,dict)]

async def _motilal_codes(client, headers):
    manual={name:env('LOCAL_MOTILAL_'+name+'_INDEX_CODE') for name in KEYS}
    if all(manual.values()): return manual
    # Cache ONLY index identifiers, never passwords or tokens.
    cache_key=(env('LOCAL_MOTILAL_CLIENT_ID'),env('LOCAL_MOTILAL_API_KEY'))
    cached=_MOTILAL_INDEX_CACHE.get(cache_key)
    if cached and time.monotonic()-cached[0]<_MOTILAL_INDEX_CACHE_TTL_SECONDS:
        return {**cached[1],**{name:code for name,code in manual.items() if code}}
    endpoint='https://openapi.motilaloswal.com/rest/report/v3/getindexdatabyexchangename'
    found={}
    for exchange in ('NSE','BSE'):
        body={'exchangename':exchange}
        if env('LOCAL_MOTILAL_DEALER_CLIENT_CODE'): body['clientcode']=env('LOCAL_MOTILAL_DEALER_CLIENT_CODE')
        resp=await client.post(endpoint,json=body,headers=headers)
        if resp.status_code in (401,403):
            raise HTTPException(409,'Motilal broker session expired; login via official portal again')
        if resp.status_code!=200: raise HTTPException(502,'Motilal index-master API not available')
        try: rows=_broker_rows(resp.json())
        except ValueError: raise HTTPException(502,'Motilal index-master response invalid')
        for row in rows:
            for name,(market,_) in KEYS.items():
                if market!=exchange or name in found: continue
                if _index_matches(name,row.get('indexname',row.get('name',''))):
                    code=str(row.get('indexcode') or row.get('scripcode') or '').strip()
                    if code.isdigit():found[name]=code
    _MOTILAL_INDEX_CACHE[cache_key]=(time.monotonic(),found)
    return {**found,**{name:code for name,code in manual.items() if code}}

async def _motilal_fetch():
    headers=_motilal_headers()
    endpoint='https://openapi.motilaloswal.com/rest/report/v3/getindexltpdata'
    prices={}
    try:
        async with httpx.AsyncClient(timeout=12.0,follow_redirects=False) as client:
            codes=await _motilal_codes(client,headers)
            if not codes:
                raise HTTPException(424,'No Motilal index codes found; see official index master/API access')
            for name,(exchange,_) in KEYS.items():
                code=codes.get(name)
                if not code: continue
                body={'exchangename':exchange,'scripcode':str(code)}
                if env('LOCAL_MOTILAL_DEALER_CLIENT_CODE'):
                    body['clientcode']=env('LOCAL_MOTILAL_DEALER_CLIENT_CODE')
                response=await client.post(endpoint,headers=headers,json=body)
                if response.status_code in (401,403):
                    raise HTTPException(409,'Motilal session expired/permission denied, reconnect officially')
                if response.status_code!=200:
                    raise HTTPException(502,'Motilal index-LTP API unavailable')
                try: rows=_broker_rows(response.json())
                except ValueError: raise HTTPException(502,'Invalid Motilal index LTP response')
                # Motilal index LTP response is in index points, unlike equity LTP in paisa.
                for row in rows:
                    if str(row.get('scripcode'))==str(code):
                        quote=parse_positive(row.get('ltp'))
                        if quote is not None: prices[name]=quote
    except httpx.RequestError:
        raise HTTPException(503,'Motilal market-data server unreachable')
    if not prices:
        raise HTTPException(424,'No Motilal index quote returned. Check session, current index codes and permissions.')
    return entry(prices,'Motilal Oswal')

def parse_positive(value):
    try:
        v=float(value);return v if 0<v<1e8 else None
    except (TypeError,ValueError):return None

async def fetch(broker):
    if broker not in BROKERS:raise HTTPException(422,'Unsupported broker')
    headers={'Accept':'application/json'}
    params=None;json=None;method='POST';out={}
    if broker=='Zerodha':
        key=env('LOCAL_ZERODHA_API_KEY'); token=env('LOCAL_ZERODHA_ACCESS_TOKEN')
        if not (key and token):raise HTTPException(412,'Zerodha API key/token not configured in local .env')
        url='https://api.kite.trade/quote/ltp';method='GET'
        params=[('i',f'{exchange}:{symbol}') for exchange,symbol in KEYS.values()]
        headers.update({'X-Kite-Version':'3','Authorization':f'token {key}:{token}'})
    elif broker=='Dhan':
        client=env('LOCAL_DHAN_CLIENT_ID'); token=env('LOCAL_DHAN_ACCESS_TOKEN')
        if not (client and token):raise HTTPException(412,'DhanHQ client ID/token not configured in local .env')
        url='https://api.dhan.co/v2/marketfeed/ltp';json={'IDX_I':[13,25,51]}
        headers.update({'access-token':token,'client-id':client,'Content-Type':'application/json'})
    elif broker=='Angel One':
        key=env('LOCAL_ANGEL_API_KEY');token=env('LOCAL_ANGEL_ACCESS_TOKEN')
        if not (key and token):raise HTTPException(412,'Angel One API key/session token not configured in local .env')
        tokens={name:(KEYS[name][0],env('LOCAL_ANGEL_'+name+'_TOKEN')) for name in KEYS}
        if not any(val[1] for val in tokens.values()):raise HTTPException(412,'Angel instrument tokens missing; look them up in current instrument master')
        url='https://apiconnect.angelone.in/rest/secure/angelbroking/market/v1/quote/'
        exchanges={}
        for exchange,symbol_token in tokens.values():
            if symbol_token: exchanges.setdefault(exchange,[]).append(symbol_token)
        json={'mode':'LTP','exchangeTokens':exchanges}
        headers.update({'Authorization':'Bearer '+token,'X-PrivateKey':key,'X-UserType':'USER','X-SourceID':'WEB','Content-Type':'application/json'})
    else:
        return await _motilal_fetch()
    try:
        async with httpx.AsyncClient(timeout=10.0,follow_redirects=False) as client:
            response=await (client.get(url,params=params,headers=headers) if method=='GET' else client.post(url,json=json,headers=headers))
    except httpx.RequestError:raise HTTPException(503,'Broker quote network unavailable')
    if response.status_code in (401,403):raise HTTPException(409,'Broker session expired/permission denied. Reconnect officially.')
    if response.status_code!=200:raise HTTPException(502,'Broker data feed unavailable; check API entitlement')
    try: payload=response.json()
    except ValueError:raise HTTPException(502,'Invalid broker response')
    if broker=='Zerodha':
        if payload.get('status')!='success':raise HTTPException(502,'Zerodha API rejected quote request')
        rows=payload.get('data') or {}
        for name,(exchange,symbol) in KEYS.items():
            row=rows.get(f'{exchange}:{symbol}',{})
            p=parse_positive(row.get('last_price') if isinstance(row,dict) else None)
            if p:out[name]=p
    elif broker=='Dhan':
        if payload.get('status')!='success':raise HTTPException(502,'DhanHQ feed entitlement or status error')
        rows=(payload.get('data') or {}).get('IDX_I') or {}
        for name,sid in [('NIFTY','13'),('BANKNIFTY','25'),('SENSEX','51')]:
            row=rows.get(sid,{})
            p=parse_positive(row.get('last_price') if isinstance(row,dict) else None)
            if p:out[name]=p
    else:
        if payload.get('status') is not True:raise HTTPException(502,'Angel One feed status error')
        reverse={ (exchange,token):name for name,(exchange,token) in tokens.items() if token }
        for row in (payload.get('data') or {}).get('fetched') or []:
            if not isinstance(row,dict):continue
            name=reverse.get((str(row.get('exchange')),str(row.get('symbolToken',row.get('symboltoken','')))))
            p=parse_positive(row.get('ltp'))
            if name and p:out[name]=p
    if not out:raise HTTPException(424,'No matching index quotes; check broker symbol IDs/data plan')
    return entry(out,broker)

@router.get('/markets')
async def local_markets(request:Request, broker:str='Angel One'):
    only_local(request)
    return await fetch(broker)
