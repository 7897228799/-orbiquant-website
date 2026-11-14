import hashlib, hmac, json, os, secrets
from datetime import datetime, timedelta
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import ForeignKey, Integer, String, DateTime, select
from sqlalchemy.orm import Mapped, mapped_column, Session
from .leads import Base, DB, engine, User, current_user, get_db
router=APIRouter(prefix="/api/payments",tags=["payments"])
PLANS={"Basic":100000,"Pro":150000}  # INR paise, monthly, per broker
BROKERS={"Zerodha","Angel One","Dhan","Kotak Neo"}
class PaymentRecord(Base):
    __tablename__="promo_payment_records"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("promo_users.id",ondelete="CASCADE"),index=True)
    order_id:Mapped[str]=mapped_column(String(80),unique=True,index=True)
    payment_id:Mapped[Optional[str]]=mapped_column(String(80),unique=True,index=True,nullable=True)
    plan:Mapped[str]=mapped_column(String(20)); broker:Mapped[str]=mapped_column(String(30))
    amount:Mapped[int]=mapped_column(Integer); currency:Mapped[str]=mapped_column(String(3),default="INR")
    status:Mapped[str]=mapped_column(String(20),default="created")
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    activated_at:Mapped[Optional[datetime]]=mapped_column(DateTime,nullable=True)
    expires_at:Mapped[Optional[datetime]]=mapped_column(DateTime,nullable=True)
Base.metadata.create_all(bind=engine)
class OrderIn(BaseModel):
    plan:str=Field(min_length=5,max_length=20); broker:str=Field(min_length=2,max_length=30)
class VerifyIn(BaseModel):
    razorpay_order_id:str; razorpay_payment_id:str; razorpay_signature:str

def creds():
    kid=os.getenv("RAZORPAY_KEY_ID","").strip(); sec=os.getenv("RAZORPAY_KEY_SECRET","").strip()
    if not kid or not sec: raise HTTPException(503,"Razorpay Live keys are not configured on the server.")
    return kid,sec

def rp(method,path,payload=None):
    kid,sec=creds()
    try:
        with httpx.Client(timeout=15,follow_redirects=False) as c:
            r=c.request(method,"https://api.razorpay.com/v1/"+path,auth=(kid,sec),json=payload)
            r.raise_for_status(); return r.json()
    except httpx.HTTPStatusError as e:
        try: msg=e.response.json().get("error",{}).get("description","Razorpay request failed")
        except Exception: msg="Razorpay request failed"
        raise HTTPException(502,msg[:240])
    except (httpx.HTTPError,ValueError): raise HTTPException(502,"Razorpay temporarily unavailable")

def mark_paid(db,rec,payment_id):
    if rec.status=="paid":
        if rec.payment_id!=payment_id: raise HTTPException(409,"Order already used")
        return
    rec.payment_id=payment_id; rec.status="paid"; rec.activated_at=datetime.utcnow(); rec.expires_at=rec.activated_at+timedelta(days=30)
    db.add(rec); db.commit()

@router.post("/order")
def create_order(body:OrderIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    if body.plan not in PLANS: raise HTTPException(422,"Invalid paid plan")
    if body.broker not in BROKERS: raise HTTPException(422,"Invalid broker")
    amount=PLANS[body.plan]; receipt="oq"+secrets.token_hex(12)
    order=rp("POST","orders",{"amount":amount,"currency":"INR","receipt":receipt,"notes":{"user_id":str(user.id),"plan":body.plan,"broker":body.broker}})
    db.add(PaymentRecord(user_id=user.id,order_id=order["id"],plan=body.plan,broker=body.broker,amount=amount,currency="INR",status="created")); db.commit()
    kid,_=creds(); return {"key_id":kid,"order_id":order["id"],"amount":amount,"currency":"INR","name":user.name,"email":user.email}

@router.post("/verify")
def verify(body:VerifyIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    rec=db.scalar(select(PaymentRecord).where(PaymentRecord.order_id==body.razorpay_order_id,PaymentRecord.user_id==user.id))
    if not rec: raise HTTPException(404,"Order not found for this account")
    _,secret=creds(); raw=f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode()
    sig=hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig,body.razorpay_signature): raise HTTPException(400,"Invalid payment signature")
    remote=rp("GET","payments/"+body.razorpay_payment_id)
    if remote.get("order_id")!=rec.order_id or remote.get("amount")!=rec.amount or remote.get("currency")!="INR" or remote.get("status")!="captured":
        raise HTTPException(402,"Payment is not confirmed as captured")
    mark_paid(db,rec,body.razorpay_payment_id)
    return {"ok":True,"status":"paid","plan":rec.plan,"broker":rec.broker,"expires_at":rec.expires_at.isoformat()}

@router.get("/me")
def my_payments(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(PaymentRecord).where(PaymentRecord.user_id==user.id).order_by(PaymentRecord.created_at.desc()).limit(50)).all()
    return {"payments":[{"plan":x.plan,"broker":x.broker,"amount":x.amount,"status":x.status,"created_at":x.created_at.isoformat(),"expires_at":x.expires_at.isoformat() if x.expires_at else None} for x in rows]}

@router.post("/webhook")
async def webhook(request:Request,db:Session=Depends(get_db)):
    secret=os.getenv("RAZORPAY_WEBHOOK_SECRET","").strip()
    if not secret: raise HTTPException(503,"Webhook not configured")
    raw=await request.body(); signature=request.headers.get("X-Razorpay-Signature","")
    expected=hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected,signature): raise HTTPException(400,"Invalid webhook signature")
    try: event=json.loads(raw)
    except ValueError: raise HTTPException(400,"Invalid webhook body")
    if event.get("event")=="payment.captured":
        ent=event.get("payload",{}).get("payment",{}).get("entity",{}); oid=ent.get("order_id"); pid=ent.get("id")
        rec=db.scalar(select(PaymentRecord).where(PaymentRecord.order_id==oid)) if oid else None
        if rec and pid and ent.get("amount")==rec.amount and ent.get("currency")=="INR": mark_paid(db,rec,pid)
    return {"ok":True}
