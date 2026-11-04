"""Authenticated performance from a user's imported, NON-verified trade CSV.
No synthetic performance and no broker order execution. Brokerage receipts are not audited.
"""
from datetime import date
import math
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import ForeignKey, Integer, Date, Float, String, select, delete
from sqlalchemy.orm import Mapped, mapped_column, Session
from .leads import Base, engine, get_db, current_user, User, check_origin

class Trade(Base):
    __tablename__='promo_imported_trades'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('promo_users.id',ondelete='CASCADE'), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    symbol: Mapped[str] = mapped_column(String(75))
    net_pnl: Mapped[float] = mapped_column(Float)
    broker: Mapped[str] = mapped_column(String(35),default='Unspecified')

Base.metadata.create_all(engine)
router=APIRouter(prefix='/api/performance',tags=['personal-trade-import'])

class TradeItem(BaseModel):
    trade_date: date
    symbol: str = Field(min_length=1,max_length=75)
    net_pnl: float
    broker: str = Field(default='Unspecified',max_length=35)

class ImportPayload(BaseModel):
    trades: list[TradeItem] = Field(min_length=1,max_length=5000)
    confirm_net_after_costs: bool

@router.post('/import')
def import_trades(data:ImportPayload,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    check_origin(request)
    if not data.confirm_net_after_costs: raise HTTPException(422,'Import net P&L after brokerage, fees and taxes; confirm the data source first.')
    for t in data.trades:
        if not math.isfinite(t.net_pnl) or abs(t.net_pnl)>1e11:raise HTTPException(422,'Invalid or implausible P&L')
        if t.trade_date>date.today():raise HTTPException(422,'Future trade dates are not allowed')
    # Transactional replacement: user cannot overwrite another user's data.
    db.execute(delete(Trade).where(Trade.user_id==user.id))
    db.add_all(Trade(user_id=user.id, trade_date=t.trade_date, symbol=t.symbol.strip(),
                     net_pnl=round(t.net_pnl,2),broker=t.broker.strip() or 'Unspecified') for t in data.trades)
    db.commit()
    return {'ok':True,'imported_count':len(data.trades),'source':'user_supplied_csv_unverified'}

@router.get('')
def get_performance(user:User=Depends(current_user),db:Session=Depends(get_db)):
    trades=db.scalars(select(Trade).where(Trade.user_id==user.id).order_by(Trade.trade_date,Trade.id).limit(5001)).all()
    if len(trades)>5000: raise HTTPException(413,'Too many imported trades')
    return {'source':'user_supplied_csv_unverified','notice':'Imported trades are user-supplied, not independently verified brokerage performance. Net P&L is based on uploaded values.',
            'trades':[{'trade_date':t.trade_date.isoformat(),'symbol':t.symbol,'net_pnl':round(t.net_pnl,2),'broker':t.broker} for t in trades]}

@router.delete('')
def delete_performance(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    check_origin(request); db.execute(delete(Trade).where(Trade.user_id==user.id));db.commit();return {'ok':True}
