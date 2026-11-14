import React, {createContext, useCallback, useContext, useEffect, useState} from 'react';
import {BrowserRouter, Link, Navigate, Route, Routes, useNavigate} from 'react-router-dom';
import PromoLanding from './components/PromoLanding';
import Brand from './components/Brand';
import PerformanceDashboard from './components/PerformanceDashboard';
import PrivateMarketExplorer from './components/PrivateMarketExplorer';
import './styles.css';
import './promo.css';
import './account.css';

const AuthContext=createContext(null);
async function api(path,options={}){
  let response;
  const API_BASE=import.meta.env.VITE_API_BASE_URL || '';
  try { response=await fetch(`${API_BASE}${path}`,{credentials:'include',headers:{'Content-Type':'application/json'},...options}); }
  catch {throw new Error('Server unavailable. Start the Orbiquant backend and try again.');}
  let data={};try{data=await response.json();}catch{}
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Request failed. Please retry.');
  return data;
}
function AuthProvider({children}){
  const [user,setUser]=useState(null);
  const [loading,setLoading]=useState(true);
  const refresh=useCallback(async()=>{try{const d=await api('/api/auth/me');setUser(d.user);}catch{setUser(null);}finally{setLoading(false);}},[]);
  useEffect(()=>{refresh();},[refresh]);
  const logout=async()=>{try{await api('/api/auth/logout',{method:'POST'});}finally{setUser(null);}};
  return <AuthContext.Provider value={{user,setUser,loading,logout,refresh}}>{children}</AuthContext.Provider>;
}
export function useAuth(){return useContext(AuthContext)}

function SplashIntro(){
  // Play the cinematic intro on EVERY full page load/refresh (not only the first visit).
  // Do not persist a "seen" flag in localStorage or sessionStorage.
  const [visible,setVisible]=useState(()=>{
    if(typeof window==='undefined')return false;
    try{return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;}catch{return true;}
  });
  useEffect(()=>{
    if(!visible)return;
    const id=window.setTimeout(()=>setVisible(false),2250);
    return()=>window.clearTimeout(id);
  },[visible]);
  if(!visible)return null;
  return <div className="oq-intro" aria-label="Orbiquant loading" role="status">
    <div className="oq-intro-grid" aria-hidden="true"/>
    <div className="oq-intro-halo" aria-hidden="true"/>
    <div className="oq-intro-logo"><Brand/><span>MARKET INTELLIGENCE · DISCIPLINE FIRST</span></div>
    <div className="oq-intro-trace" aria-hidden="true"/>
  </div>;
}
function GuestLayout({children}){
  return <div className="oq-user-shell">
    <header className="oq-user-nav"><Link to="/"><Brand/></Link><nav><Link to="/">Home</Link><Link to="/brokers">Brokers</Link><Link to="/markets">Market</Link><Link to="/performance">Performance</Link><Link to="/login">Sign In</Link></nav></header>
    {children}
    <footer className="oq-auth-footer">© {new Date().getFullYear()} Orbiquant · Promotional access only · <Link to="/privacy">Privacy & Contact Consent</Link></footer>
  </div>;
}
function AuthForm({mode}){
  const [name,setName]=useState('');const [email,setEmail]=useState('');const [phone,setPhone]=useState('');const [password,setPassword]=useState('');const [optIn,setOptIn]=useState(false);
  const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  const {setUser}=useAuth();const navigate=useNavigate();const register=mode==='register';
  const submit=async e=>{
    e.preventDefault();setError('');setBusy(true);
    const cleanPhone=phone.replace(/[\s()-]/g,'');
    try{
      const d=await api(`/api/auth/${register?'register':'login'}`,{method:'POST',body:JSON.stringify(register?{name,email,phone:cleanPhone,password,contact_opt_in:optIn}:{identifier:email.trim(),password})});
      setUser(d.user);navigate('/account',{replace:true});
    }catch(e){setError(e.message)}finally{setBusy(false)}
  };
  return <GuestLayout><div className="oq-auth-grid">
    <aside className="oq-auth-art"><span className="oq-kicker">THE ORBIQUANT EXPERIENCE</span><h2>Step into a <em>smarter</em> market experience.</h2><p>Follow product updates, preview brokers and explore strategies. Live trading remains unavailable on this website.</p><div className="oq-auth-art-bull" aria-hidden="true"/></aside>
    <main className="oq-auth-panel"><span className="oq-kicker">{register?'CREATE YOUR PROFILE':'WELCOME BACK'}</span><h1>{register?'Join Orbiquant':'Sign in to Orbiquant'}</h1><p>{register?'Create an account with your email and mobile number.':'Sign in using your registered email or mobile number.'}</p>
      <form onSubmit={submit} className="oq-form">
        {register&&<label>Your name<input required minLength="2" maxLength="100" autoComplete="name" value={name} onChange={e=>setName(e.target.value)} placeholder="Full name"/></label>}
        {register&&<label>Mobile number<input required type="tel" inputMode="tel" autoComplete="tel" maxLength="16" pattern="(?:\+91)?[6-9][0-9]{9}" value={phone} onChange={e=>setPhone(e.target.value)} placeholder="10-digit mobile number"/><small>India (+91). Enter 10 digits.</small></label>}
        <label>{register?'Email address':'Email or mobile number'}<input required type="text" autoComplete="username" maxLength="254" value={email} onChange={e=>setEmail(e.target.value)} placeholder={register?'you@example.com':'Email address or +91 mobile'}/></label>
        <label>Password<input required type="password" minLength={register?10:undefined} maxLength="200" autoComplete={register?'new-password':'current-password'} value={password} onChange={e=>setPassword(e.target.value)} placeholder={register?'Minimum 10 characters':'Your password'}/></label>
        {register&&<label className="oq-check"><input type="checkbox" checked={optIn} onChange={e=>setOptIn(e.target.checked)}/><span><b>Yes, Orbiquant may contact me</b> by email about the app launch, product updates and relevant offers. Optional; I can withdraw consent any time.</span></label>}
        {error&&<div role="alert" className="oq-auth-error">{error}</div>}
        <button className="oq-cta" disabled={busy} type="submit">{busy?'Please wait…':register?'Create My Account ↗':'Sign In ↗'}</button>
      </form>
      {!register&&<div className="oq-switch"><Link to="/forgot-password">Forgot password?</Link></div>}
      <div className="oq-switch">{register?'Already have an account?':'New to Orbiquant?'} <Link to={register?'/login':'/register'}>{register?'Sign in':'Create account'}</Link></div>
      <small className="oq-disclaimer">No broker credentials, live orders or payments are collected here. Accounts do not imply any broker connection. <Link to="/privacy">Privacy notice</Link>.</small>
    </main>
  </div></GuestLayout>;
}
function ForgotPasswordPage(){
 const [email,setEmail]=useState('');const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');const [error,setError]=useState('');
 const submit=async e=>{e.preventDefault();setBusy(true);setError('');setMessage('');try{const d=await api('/api/auth/password/forgot',{method:'POST',body:JSON.stringify({email})});setMessage(d.message||'If the account exists, a reset link has been sent.');}catch(e){setError(e.message)}finally{setBusy(false)}};
 return <GuestLayout><div className="oq-auth-grid"><aside className="oq-auth-art"><span className="oq-kicker">ACCOUNT SECURITY</span><h2>Recover your <em>Orbiquant</em> account.</h2><div className="oq-auth-art-bull" aria-hidden="true"/></aside><main className="oq-auth-panel"><span className="oq-kicker">PASSWORD HELP</span><h1>Forgot password?</h1><p>Enter your registered email address. We will send a secure reset link.</p><form className="oq-form" onSubmit={submit}><label>Email address<input required type="email" maxLength="254" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com"/></label>{error&&<div className="oq-auth-error" role="alert">{error}</div>}{message&&<div className="oq-alert" role="status">{message}</div>}<button className="oq-cta" disabled={busy}>{busy?'Sending…':'Send reset link'}</button></form><div className="oq-switch"><Link to="/login">Back to Sign In</Link></div></main></div></GuestLayout>;
}
function ResetPasswordPage(){
 const token=new URLSearchParams(window.location.search).get('token')||'';const [password,setPassword]=useState('');const [confirm,setConfirm]=useState('');const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');const [error,setError]=useState('');
 const submit=async e=>{e.preventDefault();setError('');setMessage('');if(password!==confirm){setError('Passwords do not match.');return;}setBusy(true);try{const d=await api('/api/auth/password/reset',{method:'POST',body:JSON.stringify({token,password})});setMessage(d.message||'Password updated. Please sign in.');setPassword('');setConfirm('');}catch(e){setError(e.message)}finally{setBusy(false)}};
 return <GuestLayout><div className="oq-auth-grid"><aside className="oq-auth-art"><span className="oq-kicker">ACCOUNT SECURITY</span><h2>Set a new <em>password.</em></h2><div className="oq-auth-art-bull" aria-hidden="true"/></aside><main className="oq-auth-panel"><span className="oq-kicker">SECURE RESET</span><h1>Reset password</h1><p>Choose a new password with at least 10 characters.</p><form className="oq-form" onSubmit={submit}><label>New password<input required type="password" minLength="10" maxLength="200" autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}/></label><label>Confirm password<input required type="password" minLength="10" maxLength="200" autoComplete="new-password" value={confirm} onChange={e=>setConfirm(e.target.value)}/></label>{!token&&<div className="oq-auth-error">Reset token missing. Request a new link.</div>}{error&&<div className="oq-auth-error" role="alert">{error}</div>}{message&&<div className="oq-alert" role="status">{message}</div>}<button className="oq-cta" disabled={busy||!token}>{busy?'Updating…':'Update password'}</button></form><div className="oq-switch"><Link to="/login">Back to Sign In</Link></div></main></div></GuestLayout>;
}
const BROKERS=['Zerodha','Angel One','Dhan','Motilal Oswal'];
function Protected({children}){const {user,loading}=useAuth();if(loading)return <div className="oq-auth-wait">Loading account…</div>;return user?children:<Navigate to="/login" replace/>}
function AccountPage(){
  const {user,setUser,logout}=useAuth();const navigate=useNavigate();const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');const [error,setError]=useState('');
  const save=async(path,body)=>{setBusy(true);setError('');setMessage('');try{const d=await api(path,{method:'PATCH',body:JSON.stringify(body)});setUser(d.user);setMessage('Preferences saved.');}catch(e){setError(e.message)}finally{setBusy(false)}};
  const remove=async()=>{if(!window.confirm('Delete your Orbiquant promo account and contact details permanently?'))return;setBusy(true);try{await api('/api/auth/account',{method:'DELETE'});setUser(null);navigate('/',{replace:true})}catch(e){setError(e.message);setBusy(false)}};
  const brokerList=user.broker_interests||[];
  return <GuestLayout><main className="oq-dashboard">
    <div className="oq-dash-heading"><div><span className="oq-kicker">YOUR PREVIEW ACCOUNT</span><h1>Welcome, <em>{user.name}</em></h1><p>Manage your interests and communication preference. Market trades are not available here.</p></div><button type="button" onClick={async()=>{await logout();navigate('/',{replace:true})}} className="oq-quiet">Sign out ↗</button></div>
    <div className="oq-profile-grid"><section className="oq-glass"><span className="oq-kicker">ACCOUNT DETAILS</span><h2>{user.email}</h2><p>Mobile: {user.phone||'Not added'} · Demo website account</p><div className="oq-divider"/><label className="oq-check"><input type="checkbox" checked={user.contact_opt_in} disabled={busy} onChange={e=>save('/api/auth/contact-preference',{contact_opt_in:e.target.checked})}/><span><b>Allow launch and product emails</b><small>Optional; uncheck whenever you want to stop marketing contact.</small></span></label></section>
    <section className="oq-glass"><span className="oq-kicker">BROKER INTEREST</span><h2>Choose your brokers</h2><p>For future product updates only. Selecting a broker does not connect your trading account.</p><div className="oq-broker-choices">{BROKERS.map(b=><label key={b} className="oq-broker-choice"><input type="checkbox" checked={brokerList.includes(b)} disabled={busy} onChange={e=>save('/api/auth/broker-interests',{brokers:e.target.checked?[...brokerList,b]:brokerList.filter(x=>x!==b)})}/>{b}</label>)}</div></section></div>
    {(error||message)&&<div className={'oq-alert '+(error?'oq-danger':'')} role="status">{error||message}</div>}
    <div className="oq-dashboard-cta"><div><strong>Want broker connection and strategy features?</strong><span>They will open through the official app when supported and approved.</span></div><div style={{display:"flex",gap:10,flexWrap:"wrap"}}><Link className="oq-cta" to="/brokers">Explore Brokers ↗</Link><Link className="oq-cta" to="/performance">Performance Statistics ↗</Link><Link className="oq-cta" to="/markets">Market Explorer ↗</Link></div></div>
    <button type="button" disabled={busy} className="oq-delete" onClick={remove}>Delete my promo account & contact details</button>
  </main></GuestLayout>
}
function BrokersPage(){const {user}=useAuth();return <GuestLayout><main className="oq-dashboard"><div className="oq-dash-heading"><div><span className="oq-kicker">BROKER ECOSYSTEM</span><h1>Explore <em>Connections.</em></h1><p>Four broker integrations are planned for the mobile app. Web accounts cannot place trades or connect to brokers.</p></div><Link className="oq-cta" to={user?'/account':'/register'}>{user?'My Account ↗':'Register Interest ↗'}</Link></div><div className="oq-brokers-list">{BROKERS.map((name,i)=><article className="oq-glass" key={name}><span className="oq-broker-number">0{i+1}</span><h2>{name}</h2><p>Broker-specific onboarding, authorisation and app availability depend on provider approvals.</p><span className="oq-broker-status">App integration pending · No real account connected</span><Link to={user?'/account':'/register'}>Save your interest ↗</Link></article>)}</div></main></GuestLayout>}
function PrivacyPage(){return <GuestLayout><main className="oq-privacy"><span className="oq-kicker">PRIVACY & CONTACT CHOICES</span><h1>How your details are used</h1><p>Orbiquant's promotional website accepts your name, email, mobile number, and a password to create an account. It stores only a password hash, never your original password. You can optionally select brokers you are interested in.</p><p>Marketing contact is <b>opt-in</b>. We use an opted-in email only for Orbiquant app updates and related product information. You can opt out or delete your account from My Account. We don't collect broker passwords, API tokens, trade data, orders or payment details on this site.</p><p>Password recovery is available by a one-time email link when email delivery is configured. Do not use a password you use elsewhere. For privacy enquiries, use the official contact details when published.</p><Link to="/register">Back to registration ↗</Link></main></GuestLayout>}
function AppRoutes(){const {user}=useAuth();return <Routes>
  <Route path="/" element={<PromoLanding user={user}/>}/>
  <Route path="/login" element={<AuthForm mode="login"/>}/>
  <Route path="/register" element={<AuthForm mode="register"/>}/>
  <Route path="/forgot-password" element={<ForgotPasswordPage/>}/>
  <Route path="/reset-password" element={<ResetPasswordPage/>}/>
  <Route path="/account" element={<Protected><AccountPage/></Protected>}/>
  <Route path="/brokers" element={<BrokersPage/>}/>
  <Route path="/performance" element={<Protected><PerformanceDashboard/></Protected>}/>
  <Route path="/markets" element={<Protected><PrivateMarketExplorer/></Protected>}/>
  <Route path="/privacy" element={<PrivacyPage/>}/>
  <Route path="*" element={<Navigate to="/" replace/>}/>
</Routes>}
export default function App(){return <BrowserRouter><AuthProvider><SplashIntro/><AppRoutes/></AuthProvider></BrowserRouter>}
