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
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, create_engine, select, text, inspect
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
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(15), unique=True, index=True, nullable=True)
    contact_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    broker_interests: Mapped[str] = mapped_column(String(250), default='[]', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class PhoneOtp(Base):
    __tablename__ = 'promo_phone_otp'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(15), unique=True, nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(12), default='login', nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    resend_after: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class LoginSession(Base):
    __tablename__ = 'promo_login_sessions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('promo_users.id',ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

# Existing local SQLite databases need a backward-compatible additive column migration.
# PostgreSQL production uses the reviewed SQL migration supplied separately.
if DB_URL.startswith('sqlite:') and inspect(engine).has_table('promo_users'):
    cols={col['name'] for col in inspect(engine).get_columns('promo_users')}
    if 'phone' not in cols:
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE promo_users ADD COLUMN phone VARCHAR(15)'))
            conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_promo_users_phone ON promo_users (phone)'))
Base.metadata.create_all(engine)
if DB_URL.startswith('sqlite:') and inspect(engine).has_table('promo_phone_otp'):
    cols={col['name'] for col in inspect(engine).get_columns('promo_phone_otp')}
    with engine.begin() as conn:
        if 'purpose' not in cols:
            conn.execute(text("ALTER TABLE promo_phone_otp ADD COLUMN purpose VARCHAR(12) NOT NULL DEFAULT 'login'"))
        if 'user_id' not in cols:
            conn.execute(text('ALTER TABLE promo_phone_otp ADD COLUMN user_id INTEGER'))
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
    allowed = {f'http://{host}:{port}' for host in ('localhost','127.0.0.1') for port in range(5173,5178)}
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
    password: str = Field(min_length=10,max_length=200)
    contact_opt_in: bool = False

class Login(BaseModel):
    email: str
    password: str

class PhoneRequest(BaseModel):
    phone: str

class PhoneVerify(BaseModel):
    phone: str
    otp: str = Field(min_length=6,max_length=6)

def normalize_phone(value: str):
    digits=re.sub(r'[\s()\-]', '', value.strip())
    if re.fullmatch(r'[6-9]\d{9}', digits): return '+91'+digits
    if re.fullmatch(r'(?:\+91|91)[6-9]\d{9}', digits): return '+91'+digits[-10:]
    raise HTTPException(422,'Enter a valid Indian mobile number (10 digits).')

def seconds_left(until):
    return max(1,int((until-now()).total_seconds())+1)

def send_sms(phone: str, message: str):
    # No fake delivery or user-visible OTP. IAM role credentials, never frontend keys.
    if os.getenv('OTP_SMS_PROVIDER','').lower() != 'aws_sns':
        raise HTTPException(503,'SMS OTP is not configured. Please use email/password login for now.')
    try:
        import boto3
        boto3.client('sns',region_name=os.getenv('AWS_REGION','ap-south-1')).publish(PhoneNumber=phone,Message=message,MessageAttributes={'AWS.SNS.SMS.SMSType':{'DataType':'String','StringValue':'Transactional'}})
    except Exception:
        raise HTTPException(503,'Unable to deliver OTP right now. Please retry later.')


class Preference(BaseModel):
    contact_opt_in: bool

class Interest(BaseModel):
    brokers: list[str] = Field(default_factory=list, max_length=4)

@router.post('/register',status_code=201)
def register(body:Register, request:Request, response:Response, db:Session=Depends(get_db)):
    check_origin(request); throttle(request,'register',30,600)
    email=body.email.strip().lower(); name=body.name.strip()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise HTTPException(422,'Enter a valid email')
    if len(name)<2: raise HTTPException(422,'Enter your name')
    if db.scalar(select(User).where(User.email==email)):
        raise HTTPException(409,'Account already exists. Please sign in.')
    user=User(name=name,email=email,password_hash=ph.hash(body.password),contact_opt_in=body.contact_opt_in)
    db.add(user)
    try: db.commit();db.refresh(user)
    except Exception:
        db.rollback();raise HTTPException(409,'Account could not be created. Please try signing in.')
    sign_in(response,user,db)
    return {'user':public_user(user)}

@router.post('/login')
def login(body:Login,request:Request,response:Response,db:Session=Depends(get_db)):
    check_origin(request); throttle(request,'login',15,120)
    email=body.email.strip().lower()
    user=db.scalar(select(User).where(User.email==email))
    if not user: raise HTTPException(401,'Incorrect email or password')
    if user.locked_until and user.locked_until>now():
        raise HTTPException(429,f'Account temporarily locked. Retry in {seconds_left(user.locked_until)} seconds.',headers={'Retry-After':str(seconds_left(user.locked_until))})
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
        if user.locked_until and user.locked_until>now():
            raise HTTPException(429,f'Five failed attempts. Retry in {seconds_left(user.locked_until)} seconds.',headers={'Retry-After':str(seconds_left(user.locked_until))})
        raise HTTPException(401,'Incorrect email or password')
    user.failed_login_attempts=0;user.locked_until=None
    db.commit();sign_in(response,user,db)
    return {'user':public_user(user)}

@router.post('/phone/request-otp')
def request_phone_otp(body:PhoneRequest,request:Request,db:Session=Depends(get_db)):
    check_origin(request);throttle(request,'otp-request',6,600)
    phone=normalize_phone(body.phone)
    if os.getenv('OTP_SMS_PROVIDER','').lower()!='aws_sns':
        raise HTTPException(503,'SMS OTP is not configured. Please use email/password login for now.')
    existing=db.scalar(select(PhoneOtp).where(PhoneOtp.phone==phone))
    current=now()
    if existing and existing.locked_until and existing.locked_until>current:
        delay=seconds_left(existing.locked_until)
        raise HTTPException(429,f'Too many OTP failures. Retry in {delay} seconds.',headers={'Retry-After':str(delay)})
    if existing and existing.purpose != 'login':
        raise HTTPException(429,'Mobile verification is in progress. Retry later.')
    if existing and existing.resend_after>current:
        delay=seconds_left(existing.resend_after)
        raise HTTPException(429,f'Please wait {delay} seconds before resending.',headers={'Retry-After':str(delay)})
    # For unregistered numbers, do not send an OTP or disclose account existence.
    user=db.scalar(select(User).where(User.phone==phone))
    if not user:
        return {'message':'If this number is registered, an OTP will arrive shortly.','resend_after_seconds':60}
    if user.locked_until and user.locked_until>current:
        delay=seconds_left(user.locked_until)
        raise HTTPException(429,f'Account locked. Retry in {delay} seconds.',headers={'Retry-After':str(delay)})
    code=f'{secrets.randbelow(1000000):06d}'
    hashed=hmac.new(SECRET.encode(),f'phone-otp:{phone}:{code}'.encode(),hashlib.sha256).hexdigest()
    # Send first; never claim success or store a new challenge after delivery failure.
    send_sms(phone,f'Orbiquant login OTP: {code}. Valid for 5 minutes. Do not share this code.')
    challenge=existing or PhoneOtp(phone=phone,code_hash=hashed,expires_at=current+timedelta(minutes=5),resend_after=current+timedelta(seconds=60))
    challenge.purpose='login'
    challenge.user_id=None
    challenge.code_hash=hashed
    challenge.expires_at=current+timedelta(minutes=5)
    challenge.resend_after=current+timedelta(seconds=60)
    challenge.attempts=0
    challenge.locked_until=None
    db.add(challenge);db.commit()
    return {'message':'If this number is registered, an OTP will arrive shortly.','resend_after_seconds':60}

@router.post('/phone/verify-otp')
def verify_phone_otp(body:PhoneVerify,request:Request,response:Response,db:Session=Depends(get_db)):
    check_origin(request);throttle(request,'otp-verify',20,600)
    phone=normalize_phone(body.phone)
    entry=db.scalar(select(PhoneOtp).where(PhoneOtp.phone==phone))
    user=db.scalar(select(User).where(User.phone==phone))
    if not entry or not user or entry.purpose!='login': raise HTTPException(401,'Invalid or expired OTP.')
    current=now()
    if user.locked_until and user.locked_until>current:
        delay=seconds_left(user.locked_until)
        raise HTTPException(429,f'Account locked. Retry in {delay} seconds.',headers={'Retry-After':str(delay)})
    if entry.locked_until and entry.locked_until>current:
        delay=seconds_left(entry.locked_until)
        raise HTTPException(429,f'Too many OTP failures. Retry in {delay} seconds.',headers={'Retry-After':str(delay)})
    if entry.expires_at<current: raise HTTPException(401,'OTP expired. Request another OTP.')
    attempt=hmac.new(SECRET.encode(),f'phone-otp:{phone}:{body.otp}'.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(attempt,entry.code_hash):
        entry.attempts+=1
        if entry.attempts>=5:
            entry.locked_until=current+timedelta(minutes=15)
            user.locked_until=entry.locked_until
        db.commit()
        if entry.locked_until:
            delay=seconds_left(entry.locked_until)
            raise HTTPException(429,f'Five incorrect OTPs. Retry in {delay} seconds.',headers={'Retry-After':str(delay)})
        raise HTTPException(401,'Invalid OTP.')
    db.delete(entry)
    user.failed_login_attempts=0;user.locked_until=None
    db.commit();sign_in(response,user,db)
    return {'user':public_user(user)}

@router.post('/phone/link/request')
def phone_link_request(body:PhoneRequest,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    check_origin(request);throttle(request,'phone-link',5,600)
    phone=normalize_phone(body.phone)
    if os.getenv('OTP_SMS_PROVIDER','').lower()!='aws_sns':
        raise HTTPException(503,'SMS OTP is not configured yet. Existing email login remains available.')
    linked=db.scalar(select(User).where(User.phone==phone))
    if linked and linked.id!=user.id:
        raise HTTPException(409,'This mobile number is already linked to an account.')
    record=db.scalar(select(PhoneOtp).where(PhoneOtp.phone==phone))
    current=now()
    if record and record.locked_until and record.locked_until>current:
        delay=seconds_left(record.locked_until)
        raise HTTPException(429,f'Too many OTP failures. Retry in {delay} seconds.',headers={'Retry-After':str(delay)})
    if record and record.resend_after>current:
        delay=seconds_left(record.resend_after)
        raise HTTPException(429,f'Please wait {delay} seconds before resending.',headers={'Retry-After':str(delay)})
    code=f'{secrets.randbelow(1000000):06d}'
    hashed=hmac.new(SECRET.encode(),f'phone-otp:{phone}:{code}'.encode(),hashlib.sha256).hexdigest()
    send_sms(phone,f'Orbiquant mobile verification OTP: {code}. Valid for 5 minutes. Do not share this code.')
    record=record or PhoneOtp(phone=phone,code_hash=hashed,expires_at=current+timedelta(minutes=5),resend_after=current+timedelta(seconds=60))
    record.purpose='link';record.user_id=user.id;record.code_hash=hashed
    record.expires_at=current+timedelta(minutes=5);record.resend_after=current+timedelta(seconds=60)
    record.attempts=0;record.locked_until=None
    db.add(record);db.commit()
    return {'message':'Verification OTP sent.','resend_after_seconds':60}

@router.post('/phone/link/verify')
def phone_link_verify(body:PhoneVerify,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    check_origin(request);throttle(request,'phone-link-verify',15,600)
    phone=normalize_phone(body.phone)
    record=db.scalar(select(PhoneOtp).where(PhoneOtp.phone==phone))
    if not record or record.purpose!='link' or record.user_id!=user.id:
        raise HTTPException(401,'Invalid or expired OTP.')
    current=now()
    if record.locked_until and record.locked_until>current:
        delay=seconds_left(record.locked_until)
        raise HTTPException(429,f'Too many OTP failures. Retry in {delay} seconds.',headers={'Retry-After':str(delay)})
    if record.expires_at<current:raise HTTPException(401,'OTP expired. Request another OTP.')
    attempt=hmac.new(SECRET.encode(),f'phone-otp:{phone}:{body.otp}'.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(attempt,record.code_hash):
        record.attempts+=1
        if record.attempts>=5:record.locked_until=current+timedelta(minutes=15)
        db.commit()
        if record.locked_until:
            delay=seconds_left(record.locked_until)
            raise HTTPException(429,f'Five incorrect OTPs. Retry in {delay} seconds.',headers={'Retry-After':str(delay)})
        raise HTTPException(401,'Invalid OTP.')
    if db.scalar(select(User).where(User.phone==phone,User.id!=user.id)):
        raise HTTPException(409,'This mobile number is already linked to another account.')
    user.phone=phone
    db.delete(record);db.commit()
    return {'user':public_user(user)}

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
    if user.phone:
        challenge=db.scalar(select(PhoneOtp).where(PhoneOtp.phone==user.phone))
        if challenge: db.delete(challenge)
    db.delete(user);db.commit()
    response.delete_cookie(COOKIE,path='/',secure=IS_PROD,samesite='lax')
    return {'ok':True}
