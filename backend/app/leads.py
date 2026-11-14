"""Opt-in Orbiquant promo accounts; no broker secrets, trades, payments or API tokens."""
import hmac
import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, create_engine, select, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session

MODE = os.getenv('APP_ENV', 'development').lower()
DB_URL = os.getenv('DATABASE_URL', '').strip()
if not DB_URL:
    if MODE in {'production','prod'}:
        raise RuntimeError('DATABASE_URL required in production: use persistent PostgreSQL, not ephemeral filesystem')
    local_path = Path(__file__).resolve().parents[1] / 'data' / 'promo_leads.sqlite3'
    local_path.parent.mkdir(exist_ok=True)
    DB_URL = f'sqlite:///{local_path}'
if DB_URL.startswith('postgres://'):
    DB_URL = 'postgresql+psycopg://' + DB_URL[len('postgres://'):]
elif DB_URL.startswith('postgresql://'):
    DB_URL = 'postgresql+psycopg://' + DB_URL[len('postgresql://'):]
SECRET = os.getenv('JWT_SECRET', '').strip()
if MODE in {'production','prod'} and len(SECRET) < 32:
    raise RuntimeError('JWT_SECRET requires at least 32 unpredictable characters in production')
if not SECRET:
    SECRET = secrets.token_urlsafe(48)  # local dev sessions reset on restart
IS_PROD = MODE in {'production','prod'}
engine = create_engine(DB_URL, pool_pre_ping=True, connect_args={'check_same_thread':False} if DB_URL.startswith('sqlite:') else {})
DB = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = 'promo_users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(16), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    contact_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    broker_interests: Mapped[str] = mapped_column(String(250), default='[]', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class PasswordResetToken(Base):
    __tablename__ = 'promo_password_reset_tokens'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('promo_users.id',ondelete='CASCADE'), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

class LoginSession(Base):
    __tablename__ = 'promo_login_sessions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('promo_users.id',ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

Base.metadata.create_all(engine)
# Safe additive migration for existing SQLite/PostgreSQL installations.
with engine.begin() as conn:
    cols={c['name'] for c in inspect(engine).get_columns('promo_users')}
    if 'phone' not in cols:
        conn.execute(text('ALTER TABLE promo_users ADD COLUMN phone VARCHAR(16)'))
    if engine.dialect.name == 'sqlite':
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_promo_users_phone ON promo_users (phone)'))
    else:
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_promo_users_phone ON promo_users (phone)'))
router = APIRouter(prefix='/api/auth', tags=['promo-account'])
ph = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=2)
BROKERS = {'Zerodha','Angel One','Dhan','Motilal Oswal'}
COOKIE = 'orbiquant_promo_session'
# Best-effort in-memory abuse throttle; add edge WAF/CAPTCHA before mass public rollout.
RATE = {}
RATE_LOCK = Lock()

def throttle(request, key, limit=12, window=60):
    client = request.client.host if request.client else 'unknown'
    token = (client, key)
    now = monotonic()
    with RATE_LOCK:
        history = [t for t in RATE.get(token,[]) if now-t < window]
        if len(history)>=limit:
            raise HTTPException(429,'Too many attempts. Try again later.')
        history.append(now)
        RATE[token]=history
        if len(RATE)>10000:
            RATE.clear()

def check_origin(request: Request):
    origin = request.headers.get('origin')
    if not origin: return
    allowed = {'http://localhost:5173','http://localhost:5174','http://localhost:5175','http://127.0.0.1:5173'}
    allowed |= {x.strip().rstrip('/') for x in os.getenv('ALLOWED_ORIGINS','').split(',') if x.strip()}
    public = os.getenv('PUBLIC_BASE_URL','').rstrip('/')
    if public: allowed.add(public)
    forwarded_host = request.headers.get('x-forwarded-host') or request.headers.get('host','')
    allowed |= {'https://'+forwarded_host, 'http://'+forwarded_host}
    if origin.rstrip('/') not in allowed:
        raise HTTPException(403,'Cross-origin request blocked')

def hash_token(token):
    return hmac.new(SECRET.encode(),token.encode(),hashlib.sha256).hexdigest()

def now(): return datetime.utcnow()

def get_db():
    with DB() as db: yield db

def current_user(request:Request, db:Session=Depends(get_db)):
    token=request.cookies.get(COOKIE,'')
    if not token or len(token)>300: raise HTTPException(401,'Please sign in')
    rec=db.scalar(select(LoginSession).where(LoginSession.token_hash==hash_token(token),LoginSession.expires_at>now()))
    user=db.get(User, rec.user_id) if rec else None
    if not user: raise HTTPException(401,'Session expired. Please sign in')
    return user

def public_user(user):
    return {'id':user.id,'name':user.name,'email':user.email,'phone':user.phone,'contact_opt_in':user.contact_opt_in,
            'broker_interests':json.loads(user.broker_interests or '[]'),'email_verified':False,
            'notice':'Promotional account only. Broker accounts are not connected. No orders or payments.'}

def sign_in(response, user, db):
    token=secrets.token_urlsafe(48)
    db.add(LoginSession(user_id=user.id,token_hash=hash_token(token),expires_at=now()+timedelta(days=7)))
    db.commit()
    response.set_cookie(COOKIE,token,max_age=7*86400,httponly=True,secure=IS_PROD,samesite='lax',path='/')

class Register(BaseModel):
    name: str = Field(min_length=2,max_length=100)
    email: str = Field(min_length=5,max_length=254)
    phone: str = Field(min_length=10,max_length=16)
    password: str = Field(min_length=10,max_length=200)
    contact_opt_in: bool = False

class Login(BaseModel):
    identifier: str = Field(min_length=3,max_length=254)
    password: str = Field(min_length=1,max_length=200)

class ForgotPassword(BaseModel):
    email: str = Field(min_length=5,max_length=254)

class ResetPassword(BaseModel):
    token: str = Field(min_length=30,max_length=250)
    password: str = Field(min_length=10,max_length=200)

class Preference(BaseModel):
    contact_opt_in: bool

class Interest(BaseModel):
    brokers: list[str] = Field(default_factory=list, max_length=4)

@router.post('/register',status_code=201)
def register(body:Register, request:Request, response:Response, db:Session=Depends(get_db)):
    check_origin(request); throttle(request,'register',30,600)
    email=body.email.strip().lower(); name=body.name.strip()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise HTTPException(422,'Enter a valid email')
    phone=re.sub(r'[\s()-]','',body.phone)
    if re.fullmatch(r'[6-9][0-9]{9}',phone): phone='+91'+phone
    if not re.fullmatch(r'\+[1-9][0-9]{7,14}',phone): raise HTTPException(422,'Enter a valid mobile number with country code')
    if len(name)<2: raise HTTPException(422,'Enter your name')
    if db.scalar(select(User).where(User.email==email)):
        raise HTTPException(409,'Account already exists. Please sign in.')
    if db.scalar(select(User).where(User.phone==phone)):
        raise HTTPException(409,'Mobile number is already registered.')
    user=User(name=name,email=email,phone=phone,password_hash=ph.hash(body.password),contact_opt_in=body.contact_opt_in)
    db.add(user)
    try: db.commit();db.refresh(user)
    except Exception:
        db.rollback();raise HTTPException(409,'Account could not be created. Please try signing in.')
    sign_in(response,user,db)
    return {'user':public_user(user)}

@router.post('/login')
def login(body:Login,request:Request,response:Response,db:Session=Depends(get_db)):
    check_origin(request); throttle(request,'login',15,120)
    identifier=body.identifier.strip().lower()
    phone=re.sub(r'[\s()-]','',identifier)
    if re.fullmatch(r'[6-9][0-9]{9}',phone): phone='+91'+phone
    user=db.scalar(select(User).where(User.email==identifier))
    if user is None and re.fullmatch(r'\+[1-9][0-9]{7,14}',phone):
        user=db.scalar(select(User).where(User.phone==phone))
    if not user: raise HTTPException(401,'Incorrect email or password')
    if user.locked_until and user.locked_until>now():
        raise HTTPException(429,'Account temporarily locked. Try again in 15 minutes.')
    try:
        valid=ph.verify(user.password_hash,body.password)
    except (VerifyMismatchError,VerificationError):
        valid=False
    if not valid:
        user.failed_login_attempts+=1
        if user.failed_login_attempts>=5:
            user.locked_until=now()+timedelta(minutes=15)
            user.failed_login_attempts=0
        db.commit()
        raise HTTPException(401,'Incorrect email or password')
    user.failed_login_attempts=0;user.locked_until=None
    db.commit();sign_in(response,user,db)
    return {'user':public_user(user)}

def send_reset_email(to_email: str, link: str):
    key=os.getenv('RESEND_API_KEY','').strip(); sender=os.getenv('RESET_FROM_EMAIL','').strip()
    if not key or not sender: raise HTTPException(503,'Password recovery email is not configured. Contact support.')
    import httpx
    try:
        with httpx.Client(timeout=12) as client:
            r=client.post('https://api.resend.com/emails',headers={'Authorization':f'Bearer {key}'},json={
                'from':sender,'to':[to_email],'subject':'Reset your Orbiquant password',
                'text':f'Use this secure link within 15 minutes to reset your password:\n{link}\nIf you did not request this, ignore this email.'})
            r.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(503,'Could not send reset email. Please try again later.')

@router.post('/password/forgot')
def forgot_password(body:ForgotPassword,request:Request,db:Session=Depends(get_db)):
    check_origin(request);throttle(request,'password-forgot',4,600)
    email=body.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise HTTPException(422,'Enter a valid email')
    user=db.scalar(select(User).where(User.email==email))
    if user:
        raw=secrets.token_urlsafe(40);digest=hashlib.sha256(raw.encode()).hexdigest()
        base=os.getenv('PUBLIC_BASE_URL','https://orbiquant.in').rstrip('/')
        if base not in {'https://orbiquant.in','https://www.orbiquant.in'}: raise HTTPException(503,'Reset URL is not configured')
        from urllib.parse import quote
        send_reset_email(user.email,base+'/reset-password?token='+quote(raw,safe=''))
        for old in db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id==user.id)).all(): db.delete(old)
        db.add(PasswordResetToken(user_id=user.id,token_hash=digest,expires_at=now()+timedelta(minutes=15)));db.commit()
    return {'message':'If the email is registered, a password reset link will be sent.'}

@router.post('/password/reset')
def reset_password(body:ResetPassword,request:Request,db:Session=Depends(get_db)):
    check_origin(request);throttle(request,'password-reset',8,600)
    digest=hashlib.sha256(body.token.encode()).hexdigest()
    rec=db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash==digest))
    if not rec or rec.expires_at<=now(): raise HTTPException(400,'Reset link is invalid or expired. Request a new one.')
    user=db.get(User,rec.user_id)
    if not user: raise HTTPException(400,'Reset link is invalid or expired.')
    user.password_hash=ph.hash(body.password);user.failed_login_attempts=0;user.locked_until=None
    for session in db.scalars(select(LoginSession).where(LoginSession.user_id==user.id)).all(): db.delete(session)
    for token in db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id==user.id)).all(): db.delete(token)
    db.commit();return {'message':'Password updated. Please sign in with your new password.'}

@router.get('/me')
def me(user:User=Depends(current_user)):
    return {'user':public_user(user)}

@router.post('/logout')
def logout(request:Request,response:Response,db:Session=Depends(get_db)):
    check_origin(request)
    token=request.cookies.get(COOKIE,'')
    if token: rec=db.scalar(select(LoginSession).where(LoginSession.token_hash==hash_token(token)))
    else: rec=None
    if rec: db.delete(rec);db.commit()
    response.delete_cookie(COOKIE,path='/',secure=IS_PROD,samesite='lax')
    return {'ok':True}

@router.patch('/contact-preference')
def contact_preference(body:Preference,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    check_origin(request);user.contact_opt_in=body.contact_opt_in;db.add(user);db.commit()
    return {'user':public_user(user)}

@router.patch('/broker-interests')
def broker_interests(body:Interest,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    check_origin(request)
    if any(b not in BROKERS for b in body.brokers):raise HTTPException(422,'Unsupported broker name')
    user.broker_interests=json.dumps(sorted(set(body.brokers)))
    db.add(user);db.commit()
    return {'user':public_user(user)}

@router.delete('/account')
def delete_account(request:Request,response:Response,user:User=Depends(current_user),db:Session=Depends(get_db)):
    check_origin(request)
    for item in db.scalars(select(LoginSession).where(LoginSession.user_id==user.id)).all(): db.delete(item)
    from .performance import Trade
    db.execute(__import__('sqlalchemy').delete(Trade).where(Trade.user_id==user.id))
    db.delete(user);db.commit()
    response.delete_cookie(COOKIE,path='/',secure=IS_PROD,samesite='lax')
    return {'ok':True}
