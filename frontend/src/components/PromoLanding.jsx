import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import Brand from './Brand';
import PromoHero from './PromoHero';

function WhatsAppIcon(){return <svg width="23" height="23" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12.04 2A9.94 9.94 0 0 0 3.5 17.08L2 22l5.04-1.45a10 10 0 1 0 5-18.55Zm0 18.17a8.15 8.15 0 0 1-4.16-1.14l-.3-.18-2.99.86.9-2.92-.19-.31a8.16 8.16 0 1 1 6.74 3.69Zm4.49-6.12c-.25-.13-1.48-.73-1.71-.81-.23-.08-.4-.13-.57.13-.17.25-.65.81-.79.97-.14.17-.29.19-.54.06-.25-.13-1.06-.39-2.01-1.24-.74-.66-1.25-1.48-1.39-1.73-.14-.25-.02-.39.11-.52.11-.11.25-.29.37-.44.12-.14.17-.25.25-.42.08-.17.04-.31-.02-.44-.06-.13-.57-1.37-.78-1.87-.2-.49-.41-.42-.57-.43h-.49c-.17 0-.44.06-.67.31s-.87.85-.87 2.06.89 2.38 1.01 2.54c.12.17 1.76 2.69 4.27 3.77.6.26 1.06.41 1.42.52.6.19 1.15.16 1.59.1.48-.07 1.48-.6 1.69-1.18.21-.58.21-1.08.15-1.18-.06-.1-.23-.17-.48-.29Z"/></svg>}
function TelegramIcon(){return <svg width="23" height="23" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M22 3.4 18.7 20c-.25 1.18-.94 1.46-1.91.92l-5.3-3.91-2.55 2.45c-.28.28-.52.52-1.08.52l.38-5.38 9.8-8.86c.43-.38-.09-.59-.66-.21L5.26 13.1.04 11.47c-1.14-.36-1.16-1.14.24-1.69L20.7 1.9c.94-.35 1.77.22 1.3 1.5Z"/></svg>}
const EMPTY_CONFIG={play_store_url:'',whatsapp_channel_url:'',telegram_url:''};
const MKT=[{symbol:'NIFTY',name:'NIFTY 50',exchange:'NSE'},{symbol:'BANKNIFTY',name:'BANK NIFTY',exchange:'NSE'},{symbol:'SENSEX',name:'SENSEX',exchange:'BSE'}];
// Subtle website-only UI effects. Never affect broker/trading features.
function usePromoMotion(){
  useEffect(()=>{
    const page=document.querySelector('.promo-landing');
    if(!page)return;
    const reduceMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(reduceMotion)return;
    const revealTargets=[...page.querySelectorAll('.promo-section-header, .promo-market-state, .promo-tv-panel, .promo-ticker, .promo-join-copy, .promo-social-btn, .promo-feature-card, .promo-plan, .promo-app-cta > *, .promo-footer')];
    revealTargets.forEach((el,i)=>{
      el.classList.add('promo-reveal');
      el.style.setProperty('--promo-reveal-delay',`${Math.min(i%5,4)*75}ms`);
    });
    let observer;
    if('IntersectionObserver' in window){
      observer=new IntersectionObserver(entries=>{
        entries.forEach(entry=>{
          if(entry.isIntersecting){entry.target.classList.add('promo-visible');observer.unobserve(entry.target)}
        });
      },{threshold:0.09,rootMargin:'0px 0px -35px 0px'});
      revealTargets.forEach(el=>observer.observe(el));
    }else revealTargets.forEach(el=>el.classList.add('promo-visible'));
    page.classList.add('promo-motion-ready');
    const hoverTargets=[...page.querySelectorAll('.promo-ticker, .promo-feature-card, .promo-plan')];
    const listeners=[];
    hoverTargets.forEach(el=>{
      const move=(e)=>{
        const r=el.getBoundingClientRect();
        el.style.setProperty('--promo-mouse-x',`${e.clientX-r.left}px`);
        el.style.setProperty('--promo-mouse-y',`${e.clientY-r.top}px`);
      };
      const leave=()=>{el.style.removeProperty('--promo-mouse-x');el.style.removeProperty('--promo-mouse-y')};
      el.addEventListener('pointermove',move,{passive:true});el.addEventListener('pointerleave',leave);
      listeners.push([el,move,leave]);
    });
    let raf=0;
    const updateScroll=()=>{
      if(raf)return;
      raf=window.requestAnimationFrame(()=>{
        const total=Math.max(document.documentElement.scrollHeight-window.innerHeight,1);
        page.style.setProperty('--promo-page-progress',`${(window.scrollY/total*100).toFixed(2)}%`);
        raf=0;
      });
    };
    updateScroll();window.addEventListener('scroll',updateScroll,{passive:true});window.addEventListener('resize',updateScroll,{passive:true});
    return()=>{observer?.disconnect();listeners.forEach(([el,move,leave])=>{el.removeEventListener('pointermove',move);el.removeEventListener('pointerleave',leave)});window.removeEventListener('scroll',updateScroll);window.removeEventListener('resize',updateScroll);if(raf)window.cancelAnimationFrame(raf);page.classList.remove('promo-motion-ready')};
  },[]);
}

const PLANS=[{title:'Free Trial',price:'₹0',caption:'7 days · paper-only evaluation',details:'Explore the app experience with no real orders'},{title:'Basic',price:'₹1,000',caption:'Monthly · per broker',details:'Up to 2 active strategies per broker'},{title:'Pro',price:'₹1,500',caption:'Monthly · per broker',details:'Up to 4 active strategies per broker'}];

function ExternalLink({href,onMissing,children,className}){
  return <button type="button" className={className||'promo-social-btn'} onClick={()=>href?window.open(href,'_blank','noopener,noreferrer'):onMissing()}>{children}</button>
}

function StoreModal({open,onClose,playUrl}){
  useEffect(()=>{if(!open)return;const onKey=e=>{if(e.key==='Escape')onClose()};document.addEventListener('keydown',onKey);return()=>document.removeEventListener('keydown',onKey)},[open,onClose]);
  if(!open)return null;
  return <div className="promo-modal-scrim" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}>
    <div className="promo-modal" role="dialog" aria-modal="true" aria-labelledby="promo-modal-title">
      <button type="button" className="promo-close" aria-label="Close download prompt" onClick={onClose}>×</button>
      <span className="promo-modal-orbit">â—Ž</span><span className="promo-kicker">THE ORBIQUANT APP</span>
      <h2 id="promo-modal-title">Everything happens <em>in the app.</em></h2>
      <p>Strategies, broker connections, subscriptions and trading will be available through the official Orbiquant app after launch and any required approvals. This website is for information only.</p>
      {playUrl?<a className="promo-store-link" target="_blank" rel="noopener noreferrer" href={playUrl}><span>▶</span><span><small>GET IT ON</small><strong>Google Play</strong></span></a>:<div className="promo-not-yet"><strong>App coming to Google Play</strong><span>Store listing is not published/linked yet. Check our community channels for launch updates.</span></div>}
      <button type="button" className="promo-modal-later" onClick={onClose}>Continue exploring website</button>
    </div>
  </div>
}

function TradingViewTape({quotes}){
  // Share the same broker quote objects as the three large homepage cards.
  const fmt = v => new Intl.NumberFormat('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2}).format(v);
  return <div className="promo-tv-panel">
    <div className="promo-tv-caption">ORBIQUANT · INDEX MARKET WATCH · ANGEL ONE</div>
    <div className="promo-index-strip">
      {quotes.map(q=>{
        const available=typeof q.price==='number'&&Number.isFinite(q.price);
        const stale=q.status==='stale_private';
        return <div className="promo-index-strip-item" key={q.symbol}>
          <div className="promo-index-strip-name">{q.name}<span>{q.exchange}</span></div>
          <strong className="promo-index-strip-price">{available?fmt(q.price):'— — —'}</strong>
          <small className={stale?'promo-index-stale':'promo-index-status'}>{!available?'Feed unavailable':stale?'STALE · LAST TICK':q.status==='private_live'?'ANGEL ONE · LIVE':q.status==='delayed'?'DELAYED':'LATEST QUOTE'}</small>
        </div>;
      })}
    </div>
    <small>Private authorised broker feed for personal testing. Public exchange-data redistribution requires separate permissions.</small>
  </div>
}

function MarketOverview({onInstall}){
  const [data,setData]=useState({quotes:[],feed_status:'loading',source:null});
  const [localTicks,setLocalTicks]=useState({});
  const [localFeedStatus,setLocalFeedStatus]=useState('Private stream not connected');
  const [tickClock,setTickClock]=useState(Date.now());
  useEffect(()=>{const id=setInterval(()=>setTickClock(Date.now()),5000);return()=>clearInterval(id)},[]);
  const onLocalhost=['localhost','127.0.0.1'].includes(window.location.hostname);
  useEffect(()=>{
    if(!onLocalhost)return;
    let mounted=true, socket, retryTimer, reconnect=0, requireLogin=false;
    const connect=()=>{
      if(!mounted||requireLogin)return;
      setLocalFeedStatus('Connecting to Angel One…');
      socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/local/angel/stream`);
      socket.onmessage=(event)=>{
        let tick;try{tick=JSON.parse(event.data)}catch{return}
        if(!mounted)return;
        if(tick.status==='connected'){setLocalFeedStatus('Angel One connected · waiting for ticks');reconnect=0}
        if(tick.symbol&&typeof tick.price==='number'&&Number.isFinite(tick.price)&&tick.price>0){
          setLocalTicks(prev=>({...prev,[tick.symbol]:{...tick,local_received_ms:Date.now()}}));
          setLocalFeedStatus('Angel One private live ticks');
        }
        if(tick.error){setLocalFeedStatus(tick.error);if(tick.status==='reauth_required')requireLogin=true}
      };
      socket.onerror=()=>{if(mounted)setLocalFeedStatus('Broker stream connection failed')};
      socket.onclose=()=>{if(!mounted||requireLogin)return;setLocalFeedStatus('Stream disconnected · retrying');reconnect=Math.min(reconnect+1,5);retryTimer=setTimeout(connect,Math.min(30000,3000*Math.pow(2,reconnect-1)))};
    };
    connect();return()=>{mounted=false;clearTimeout(retryTimer);if(socket)socket.close()};
  },[onLocalhost]);
  useEffect(()=>{
    let active=true;let timer;
    async function load(){
      try{const res=await fetch('/api/public/markets',{cache:'no-store'});if(!res.ok)throw new Error('feed unavailable');const d=await res.json();if(active)setData(d)}
      catch{if(active)setData({quotes:[],feed_status:'unavailable',source:null})}
    }
    load();timer=setInterval(load,15000);
    return()=>{active=false;clearInterval(timer)}
  },[]);
  const quotes=MKT.map(m=>{
    const publicQuote=(data.quotes||[]).find(q=>q.symbol===m.symbol)||{};
    const tick=onLocalhost?localTicks[m.symbol]:null;
    const fresh=tick&&tick.local_received_ms&&tickClock-tick.local_received_ms<90000;
    return {...m,...publicQuote,...(tick?{price:tick.price,status:fresh?'private_live':'stale_private',asof:tick.received_at,change_percent:null}:{} )};
  });
  const anyQuotes=quotes.some(q=>q.price!=null);
  return <section className="promo-section promo-market" id="market">
    <div className="promo-section-header"><div><span className="promo-kicker">MARKET WATCH · INFORMATION ONLY</span><h2>Stay close to the <em>market.</em></h2><p>Real values appear only through a licensed, authorised public-display data feed. NSE and BSE market hours and data delay vary by provider.</p></div><div className={'promo-market-state '+(anyQuotes?'has-feed':'')}><span className="promo-state-dot"/>{onLocalhost?(Object.keys(localTicks).length?'ANGEL ONE · LIVE FEED':'ANGEL ONE · '+localFeedStatus):(anyQuotes?'FEED AVAILABLE':'AWAITING AUTHORISED FEED')}</div></div>
    <TradingViewTape quotes={quotes}/>
    <div className="promo-tickers">
      {quotes.map(q=>{const ready=q.price!=null;const pct=q.change_percent;return <button type="button" key={q.symbol} className="promo-ticker" onClick={onInstall} aria-label={`${q.name}, ${ready?q.price:'feed unavailable'}. Open app download prompt`}>
        <div className="promo-ticker-top"><strong>{q.name}</strong><span>{q.exchange}</span></div>
        <div className={'promo-ticker-price '+(!ready?'missing':'')}>{ready?new Intl.NumberFormat('en-IN',{maximumFractionDigits:2,minimumFractionDigits:2}).format(q.price):'— — —'}</div>
        {ready?<div className={'promo-ticker-change '+(pct>=0?'up':'down')}>{pct!=null?`${pct>=0?'+':''}${pct.toFixed(2)}%`:'—'} · {q.status==='private_live'?'ANGEL ONE · LIVE':q.status==='stale_private'?'STALE · LAST RECEIVED TICK':q.status==='delayed'?'DELAYED':'LATEST QUOTE'}</div>:<div className="promo-ticker-unavailable">Live feed not connected</div>}
        {ready&&q.asof&&<small>As of {new Date(q.asof).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',hour12:true})} IST</small>}
        <div className="promo-card-action">Explore in the app ↗</div>
      </button>})}
    </div>
    <div className="promo-feed-footnote">{onLocalhost?'Authorised personal-use feed. Angel One quotes are not licensed for public redistribution; exchange hours and broker permissions apply.':anyQuotes?`Source: ${data.source||'Authorised feed'} · Quote availability and delays depend on licensed provider.`:'No prices are fabricated. Public market-display licence and feed connection are required before genuine live values can appear.'}</div>
  </section>
}

export default function PromoLanding({user,page='home'}){
  usePromoMotion();
  useEffect(()=>{window.scrollTo({top:0,left:0,behavior:'instant'});},[page]);
  const [config,setConfig]=useState(EMPTY_CONFIG);
  const [modal,setModal]=useState(false);
  const [menuOpen,setMenuOpen]=useState(false);
  const [message,setMessage]=useState('');
  useEffect(()=>{let active=true;fetch('/api/public/config').then(r=>r.ok?r.json():EMPTY_CONFIG).then(x=>{if(active)setConfig(x)}).catch(()=>{});return()=>{active=false}},[]);
  const [selectedBroker,setSelectedBroker]=useState('Zerodha');
  const [paymentBusy,setPaymentBusy]=useState(false);
  async function startRazorpayCheckout(plan){
    if(!user){window.location.href='/login';return;} if(paymentBusy)return;
    setPaymentBusy(true);setMessage('');
    try{
      const r=await fetch('/api/payments/order',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan:plan.title,broker:selectedBroker})});
      const order=await r.json(); if(!r.ok)throw new Error(order.detail||'Order creation failed');
      if(!window.Razorpay)await new Promise((resolve,reject)=>{const sc=document.createElement('script');sc.src='https://checkout.razorpay.com/v1/checkout.js';sc.onload=resolve;sc.onerror=()=>reject(new Error('Razorpay Checkout failed to load'));document.body.appendChild(sc);});
      const checkout=new window.Razorpay({key:order.key_id,amount:order.amount,currency:order.currency,order_id:order.order_id,name:'Orbiquant',description:plan.title+' / '+selectedBroker+' / 30 days',prefill:{name:order.name,email:order.email},theme:{color:'#e99b35'},
        handler:async result=>{try{const v=await fetch('/api/payments/verify',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(result)});const d=await v.json();if(!v.ok)throw new Error(d.detail||'Verification failed');setMessage(d.plan+' activated for '+d.broker+' until '+new Date(d.expires_at).toLocaleDateString('en-IN'));}catch(e){setMessage('Payment received; verification pending. Contact support with payment ID '+result.razorpay_payment_id);}},
        modal:{ondismiss:()=>setMessage('Checkout closed. Subscription not activated.')}});
      checkout.on('payment.failed',e=>setMessage(e.error?.description||'Payment failed'));checkout.open();
    }catch(e){setMessage(e.message||'Unable to start payment');}finally{setPaymentBusy(false);}
  }
  const appPrompt=()=>setModal(true);
  const noWhatsApp=()=>setMessage('WhatsApp Channel link will be added before launch.');
  const noTelegram=()=>setMessage('Telegram link will be added before launch.');
  return <div className="landing promo-landing">
    <div className="promo-top-strip"><span>ORBIQUANT</span> <span>Official App Coming Soon · Website Preview Only</span><span className="promo-no-trades">NO TRADING ON THIS WEBSITE</span></div>
    <nav className="public-nav promo-nav"><a href="/" aria-label="Go to Orbiquant home" onClick={()=>setMenuOpen(false)}><Brand/></a><button className="promo-menu-toggle" type="button" aria-label={menuOpen?'Close navigation menu':'Open navigation menu'} aria-expanded={menuOpen} aria-controls="promo-nav-links" onClick={()=>setMenuOpen(v=>!v)}>{menuOpen?'×':'☰'}</button><div id="promo-nav-links" className={'public-nav-links '+(menuOpen?'promo-links-open':'')}><a href="/market-watch" onClick={()=>setMenuOpen(false)}>Market Watch</a><a href="/features" onClick={()=>setMenuOpen(false)}>Explore App</a><a href="/brokers" onClick={()=>setMenuOpen(false)}>Brokers</a><a href="/plans" onClick={()=>setMenuOpen(false)}>Plans</a><a href="/community" onClick={()=>setMenuOpen(false)}>Community</a><a href={user?"/account":"/login"} onClick={()=>setMenuOpen(false)}>{user?"My Account":"Login / Sign Up"}</a></div><button className="btn btn-orange btn-small promo-navbar-cta" onClick={()=>{setMenuOpen(false);appPrompt()}}>Get the App ↗</button></nav>
    {page==='home'&&<div id="top"><PromoHero onInstall={appPrompt}/></div>}
{page==='home'&&<section className="promo-section" aria-label="Broker integrations preview" style={{padding:'28px 16px',textAlign:'center'}}>
<h2 style={{fontSize:'clamp(22px,3vw,32px)',marginBottom:18}}>Explore Our Brokers</h2>
<div style={{display:'flex',justifyContent:'center',flexWrap:'wrap',gap:14}}>
{[['Zerodha','zerodha'],['Angel One','angel'],['Dhan','dhan'],['Kotak Neo','kotak']].map(([name,slug])=>
<Link to={(user?'/account':'/register')+'?broker='+encodeURIComponent(name)} key={slug} aria-label={'Select '+name+' and continue to Orbiquant registration'} data-flow="oq-broker-onboard-v1" style={{display:'flex',alignItems:'center',gap:10,padding:'12px 16px',border:'1px solid #454550',borderRadius:14,background:'#191a22',color:'#fff',fontSize:15,fontWeight:600,textDecoration:'none',cursor:'pointer'}}>
<img src={'/broker-icons/'+slug+'.png'} alt={name+' icon'} width="36" height="36" style={{objectFit:'contain',borderRadius:6,background:'#fff'}} onError={e=>{const img=e.currentTarget;if(!img.dataset.fallback){img.dataset.fallback='1';img.src='/broker-icons/'+slug+'.svg';}}}/>
<span>{name}</span>
</Link>)}
</div>
<p style={{fontSize:12,opacity:0.75,marginTop:16}}>Broker integrations are planned. Live broker connections are not available on this website.</p>
</section>}
    {page!=='home'&&<header className="promo-subpage-hero"><span className="promo-kicker">ORBIQUANT · EXPLORE</span><h1>{({market:'Market Watch',features:'Explore the App',plans:'Plans & Pricing',community:'Our Community'})[page]}</h1><p>{({market:'Track the three headline indices with data available only from an authorised feed.',features:'Explore Orbiquant features planned for the official trading app.',plans:'Compare plans before the app launches; no payment is collected on this preview website.',community:'Connect with Orbiquant through our official support and community channels.'})[page]}</p><Link className="promo-back-home" to="/">← Back to Home</Link></header>}
    {page==='home'&&<div className="oq-reg-banner"><div><span className="promo-kicker">BE PART OF THE ORBIQUANT COMMUNITY</span><h2>Register now. <em>Stay informed.</em></h2><p>Keep your contact preference and broker interests in one account. Optional launch notifications—no trading on this site.</p></div><div className="oq-reg-actions"><Link to={user?"/account":"/register"} className="oq-cta">{user?"Open My Account":"Create Free Account"} ↗</Link><Link to={user?"/account":"/login"} className="oq-outline">{user?"Manage Preferences":"Already a member? Login"}</Link></div></div>}
    {page==='community'&&<><section className="promo-join-strip" id="community"><div className="promo-join-copy"><span className="promo-kicker">STAY CONNECTED</span><h2>Join the Orbiquant <em>community</em></h2><p>For customer care call 8103571528 or email support@orbiquant.in. Join our Telegram community for updates.</p></div><div className="promo-social-actions"><a className="promo-social-btn promo-whatsapp" href="https://wa.me/918103571528" target="_blank" rel="noopener noreferrer" aria-label="Chat with Orbiquant on WhatsApp"><WhatsAppIcon/> <span>WhatsApp · Chat with us ↗</span></a><ExternalLink className="promo-social-btn promo-telegram" href={config.telegram_url} onMissing={noTelegram}><TelegramIcon/> <span>Join Telegram ↗</span></ExternalLink></div></section>
    <div className="oq-care-details"><a href="tel:+918103571528">Customer Care: 8103571528</a><a href="mailto:support@orbiquant.in">Email: support@orbiquant.in</a><Link to="/terms">Terms &amp; Risk Disclosure</Link></div></>}
    {page==='market'&&<MarketOverview onInstall={appPrompt}/>} 
    {page==='features'&&<section className="promo-section promo-features" id="features"><div className="promo-section-header"><div><span className="promo-kicker">APP-FIRST TRADING EXPERIENCE</span><h2>All your tools. <em>Inside the app.</em></h2><p>Explore Orbiquant, a platform preview for Indian options traders interested in NIFTY, BANKNIFTY and SENSEX market insights. Discover planned strategy tools including ThetaShield, TrendArmor, Decaymax and SleepTight, alongside broker integration previews for Zerodha, Angel One, Dhan and Kotak Neo. Account registration is available for preview; live trading, broker connections and paid subscriptions are not available on this website.</p></div></div>
      <div className="promo-feature-grid">{[
        ['01','Strategy Library','ThetaShield, TrendArmor, Decaymax and SleepTight'],
        ['02','Your Broker Connections','Zerodha · Angel One · Dhan · Kotak Neo'],
        ['03','Market Dashboard','NIFTY · BANKNIFTY · SENSEX market watch'],
        ['04','Orders & Positions','Execution tracking inside the approved app'],
        ['05','Risk Controls','Limits, stop controls and account-specific settings'],
        ['06','Plans & Subscription','Your selected plan managed within the app'],
      ].map(([idx,title,sub])=><button type="button" className="promo-feature-card" key={idx} onClick={appPrompt}><span className="promo-feature-index">{idx}</span><h3>{title}</h3><p>{sub}</p><span className="promo-feature-cta">Open in app ↗</span></button>)}</div>
    </section>}
    {(page==='plans'||page==='home')&&<section className="promo-section promo-plans" id="plans"><div className="promo-section-header"><div><span className="promo-kicker">SIMPLE PLANS</span><h2>One platform. <em>Three plans.</em></h2><p>Choose a broker and pay securely. Subscription activates only after Razorpay confirms captured payment.</p></div></div>
      <label style={{display:'flex',gap:12,alignItems:'center',margin:'0 0 20px',flexWrap:'wrap'}}>Subscription broker:
        <select value={selectedBroker} onChange={e=>setSelectedBroker(e.target.value)} style={{padding:10,borderRadius:8}}>{['Zerodha','Angel One','Dhan','Kotak Neo'].map(b=><option key={b}>{b}</option>)}</select>
      </label>
      <div className="promo-prices">{PLANS.map((p,i)=><article className={'promo-plan '+(i===2?'promo-plan-featured':'')} key={p.title}><span className="promo-plan-label">{i===2?'POPULAR PLAN':i===0?'EXPLORE':'FOR ACTIVE USERS'}</span><h3>{p.title}</h3><div className="promo-plan-price">{p.price}</div><span>{p.caption}</span><p>{p.details}</p><button className="promo-plan-btn" type="button" disabled={paymentBusy} onClick={()=>p.title==='Free Trial'?appPrompt():startRazorpayCheckout(p)}>{paymentBusy?'Please wait…':p.title==='Free Trial'?'Explore free trial':'Pay securely with Razorpay'}</button></article>)}</div>
    </section>}
    {(page==='home'||page==='features')&&<section className="promo-app-cta"><span className="promo-kicker">THE NEXT CHAPTER OF ORBIQUANT</span><h2>Markets move fast.<br/><em>Be app-ready.</em></h2><p>Get launch information from our channels and discover the full platform when the mobile app is available.</p><button className="promo-cta-button" type="button" onClick={appPrompt}>Get Orbiquant on Google Play ↗</button></section>}
    <footer className="promo-footer"><Brand compact/><Link to="/privacy" className="oq-privacy-link">Privacy & Contact Consent</Link><Link to="/terms" className="oq-privacy-link">Terms & Risk Disclosure</Link><a className="oq-privacy-link" href="tel:+918103571528">Customer Care: 8103571528</a><a className="oq-privacy-link" href="mailto:support@orbiquant.in">support@orbiquant.in</a><Link to={user?"/account":"/login"} className="oq-privacy-link">{user?"My Account":"Member Login"}</Link><span>© {new Date().getFullYear()} Orbiquant · Preview accounts only · No orders or payments here. No guaranteed returns.</span><button type="button" onClick={appPrompt}>Download the app ↗</button></footer>
    <div className="promo-floating-app"><button type="button" onClick={appPrompt}>▶ &nbsp; Download App</button></div>
    {message&&<div role="status" className="promo-toast"><span>{message}</span><button onClick={()=>setMessage('')} aria-label="Dismiss">×</button></div>}
    <StoreModal open={modal} onClose={()=>setModal(false)} playUrl={config.play_store_url}/>
  </div>
}

