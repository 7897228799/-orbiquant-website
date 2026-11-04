"""One-owner localhost-only relay for Angel's official push-based index ticks."""
import asyncio
import json
import os
import struct
from datetime import datetime,timezone
from fastapi import APIRouter,WebSocket,WebSocketDisconnect
from .angel_session import ensure_session

router=APIRouter()

@router.websocket('/api/local/angel/stream')
async def angel_stream(ws:WebSocket):
    client=ws.client.host if ws.client else ''
    origin=ws.headers.get('origin','')
    allowed=(client in ('127.0.0.1','::1','localhost') and
             origin.startswith(('http://127.0.0.1:', 'http://localhost:')) and
             os.getenv('APP_ENV','development').lower() not in ('production','prod') and
             os.getenv('LOCAL_PRIVATE_QUOTES_ENABLED','false').lower()=='true')
    if not allowed:
        await ws.close(code=1008);return
    await ws.accept()
    key=os.getenv('LOCAL_ANGEL_API_KEY','').strip(); jwt=os.getenv('LOCAL_ANGEL_ACCESS_TOKEN','').strip()
    feed=os.getenv('LOCAL_ANGEL_FEED_TOKEN','').strip();code=os.getenv('LOCAL_ANGEL_CLIENT_CODE','').strip()
    indexes={name:(1 if name!='SENSEX' else 3,os.getenv('LOCAL_ANGEL_'+name+'_TOKEN','').strip()) for name in ('NIFTY','BANKNIFTY','SENSEX')}
    indexes={name:val for name,val in indexes.items() if val[1].isdigit()}
    if not all((key,code)) or not indexes:
        await ws.send_json({'error':'Angel session/token missing. Run py -3 CONFIGURE_ANGEL_ONE_LOCAL.py in project root.'});await ws.close();return
    try:
        jwt,feed=await ensure_session()
        from websockets.asyncio.client import connect
        groups={}
        for exch,token in indexes.values():groups.setdefault(exch,[]).append(token)
        subscription={'correlationID':'orbiquant1','action':1,'params':{'mode':1,'tokenList':[{'exchangeType':e,'tokens':t} for e,t in groups.items()]}}
        headers={'Authorization':jwt,'x-api-key':key,'x-client-code':code,'x-feed-token':feed}
        async with connect('wss://smartapisocket.angelone.in/smart-stream',additional_headers=headers,ping_interval=None,open_timeout=15,max_size=1048576) as remote:
            await remote.send(json.dumps(subscription))
            await ws.send_json({'status':'connected','source':'Angel One SmartAPI WebSocket V2'})
            async def heartbeat():
                while True:
                    await asyncio.sleep(10)
                    await remote.send('ping')
            async def monitor_expiry():
                from .angel_session import _jwt_expired_soon
                while True:
                    await asyncio.sleep(30)
                    if _jwt_expired_soon(os.getenv('LOCAL_ANGEL_ACCESS_TOKEN','')):
                        try:
                            await ensure_session(force=True)
                        except RuntimeError:
                            await ws.send_json({'status':'reauth_required','error':'Angel session refresh rejected. Run CONFIGURE_ANGEL_ONE_LOCAL.py with a fresh TOTP and restart website.'})
                        await remote.close(code=1000,reason='Session renewed or requires login')
                        return
            hb=asyncio.create_task(heartbeat())
            monitor=asyncio.create_task(monitor_expiry())
            try:
                async for packet in remote:
                    if isinstance(packet,bytes) and len(packet)>=51:
                        mode=packet[0];exch=packet[1];token=packet[2:27].split(b'\x00',1)[0].decode('ascii','ignore')
                        if mode!=1:continue
                        price=struct.unpack_from('<q',packet,43)[0]/100.0
                        if not 0<price<100000000:continue
                        name=next((n for n,(e,t) in indexes.items() if e==exch and t==token),None)
                        if name:
                            exchange_ms=struct.unpack_from('<q',packet,35)[0]
                            await ws.send_json({'symbol':name,'price':price,'exchange_timestamp_ms':exchange_ms,'received_at':datetime.now(timezone.utc).isoformat(),'source':'Angel One'})
                    elif isinstance(packet,str) and packet not in ('pong','ping'):
                        try:
                            message=json.loads(packet)
                            if isinstance(message,dict) and message.get('errorCode'):
                                await ws.send_json({'error':'Broker subscription rejected. Verify index tokens and entitlement.'})
                        except ValueError:pass
            finally:
                hb.cancel()
                monitor.cancel()
    except WebSocketDisconnect:pass
    except RuntimeError as exc:
        try: await ws.send_json({'error':str(exc),'status':'reauth_required' if 'Re-login' in str(exc) or 're-login' in str(exc) else 'unavailable'})
        except Exception:pass
        try: await ws.close()
        except Exception:pass
    except Exception:
        try: await ws.send_json({'error':'Angel streaming disconnected. Check current session, index tokens, connectivity and account permissions.'})
        except Exception:pass
        try:await ws.close()
        except Exception:pass
