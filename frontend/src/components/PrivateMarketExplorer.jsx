import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import Brand from './Brand';
import '../performance.css';
const BROKERS=['Angel One','Zerodha','Dhan','Kotak Neo'];
export default function PrivateMarketExplorer(){
 const [broker,setBroker]=useState('Angel One'),[out,setOut]=useState(null),[error,setError]=useState('');
 const [ticks,setTicks]=useState({}),[streamStatus,setStreamStatus]=useState('Not connected');
 useEffect(()=>{
  let cancelled=false;
  const load=async()=>{
   try{
    const res=await fetch(`/api/local/markets?broker=${encodeURIComponent(broker)}`);
    const data=await res.json();
    if(!res.ok)throw Error(typeof data.detail==='string'?data.detail:'Local API unavailable');
    if(!cancelled){setOut(data);setError('')}
   }catch(e){if(!cancelled){setOut(null);setError(e.message)}}
  };
  load();const id=setInterval(load,15000);return()=>{cancelled=true;clearInterval(id)}
 },[broker]);
 useEffect(()=>{
  if(broker!=='Angel One'){setStreamStatus('Snapshot mode');setTicks({});return;}
  let alive=true;let sock;let retry;let needsLogin=false;
  const open=()=>{if(!alive)return;setStreamStatus('Connecting…');sock=new WebSocket(`${window.location.protocol==='https:'?'wss':'ws'}://${window.location.host}/api/local/angel/stream`);
   sock.onmessage=(event)=>{try{const d=JSON.parse(event.data);if(d.error){setStreamStatus(d.error);if(d.status==='reauth_required')needsLogin=true;return;}if(d.status==='connected')setStreamStatus('Connected — waiting for exchange ticks');if(d.symbol&&typeof d.price==='number'){setTicks(t=>({...t,[d.symbol]:d}));setStreamStatus('Tick stream connected')}}catch{}};
   sock.onclose=()=>{if(!alive)return;if(needsLogin){setStreamStatus('Fresh Angel login required — run CONFIGURE_ANGEL_ONE_LOCAL.py and restart server');return;}setStreamStatus('Disconnected — retrying');retry=setTimeout(open,8000)};sock.onerror=()=>{setStreamStatus('Feed connection error')};
  };open();return()=>{alive=false;clearTimeout(retry);if(sock)sock.close()};
 },[broker]);
 return <div className="perf-shell"><aside className="perf-sidebar"><Link to="/"><Brand/></Link><div className="perf-subhead">YOUR WORKSPACE</div><Link to="/account">Account</Link><Link to="/performance">Performance Statistics</Link><Link to="/markets" className="perf-selected">Market Explorer</Link><Link to="/brokers">Brokers</Link><Link to="/">Homepage</Link></aside><main className="perf-main"><div className="perf-top"><span className="perf-kicker">PRIVATE BROKER DATA</span><Link to="/account">Account ↗</Link></div><h1>Market <em>Explorer.</em></h1><p>Only real, read-only quotes returned by your authorised local broker account. No mock data and no trading.</p><div className="perf-tabs">{BROKERS.map(b=><button key={b} type="button" className={broker===b?'active':''} onClick={()=>setBroker(b)}>{b}</button>)}</div>
 {broker==='Angel One'&&<div className="perf-note" role="status">Angel One WebSocket: {streamStatus}. JWT renews automatically while permitted; daily expiry needs fresh TOTP using CONFIGURE_ANGEL_ONE_LOCAL.py. Real ticks only.</div>}
 {error&&<div className="perf-note" role="status"><b>Feed unavailable:</b> {error}. Configure broker credentials only in local <code>backend/.env</code>; never in the website or GitHub.</div>}
 <div className="perf-market-grid">{['NIFTY','BANKNIFTY','SENSEX'].map(symbol=>{const q=out?.quotes?.find(x=>x.symbol===symbol);const tick=broker==='Angel One'?ticks[symbol]:null;return <article className="perf-panel" key={symbol}><span className="perf-kicker">{q?.exchange|| (symbol==='SENSEX'?'BSE':'NSE')}</span><h2>{symbol}</h2><div className="perf-price">{tick?.price!=null?tick.price.toLocaleString('en-IN'):q?.price!=null?q.price.toLocaleString('en-IN'):'—'}</div><small>{tick?.price!=null?'Angel One tick · '+new Date(tick.received_at).toLocaleTimeString('en-IN'):q?.price!=null?'Broker LTP snapshot · Exchange timestamp not verified':'Feed not connected'}</small></article>})}</div>
 {broker==='Kotak Neo'&&<div className="perf-note">Kotak Neo quotes need broker-issued API key, secret, current Auth Token and Access Token. Index codes auto-discovered. See MOTILAL_FREE_LIVE_FEED_SETUP_HINDI.md. Client ID alone cannot provide prices.</div>}\n <div className="perf-note">Refresh every 15 seconds while this page is open. The API response time is not an exchange trade timestamp. NSE/BSE may be closed; latest LTP need not be a fresh trade. Personal broker feeds must not be redistributed to public customers without licensing.</div>
 <p>For public visitors the separate market widget may be delayed. Real API tokens are never entered in the browser and **live order placement is disabled**.</p></main></div>
}

