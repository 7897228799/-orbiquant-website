"""Admin-only local CSV export; requires database access on operator's machine."""
import csv
import sys
from sqlalchemy import select
from .leads import DB, User

out = sys.argv[1] if len(sys.argv)>1 else 'opted_in_contacts.csv'
with DB() as db, open(out,'w',newline='',encoding='utf-8-sig') as f:
    writer=csv.writer(f)
    writer.writerow(['name','email','broker_interests','registered_utc'])
    for user in db.scalars(select(User).where(User.contact_opt_in.is_(True))).all():
        writer.writerow([user.name,user.email,user.broker_interests,user.created_at.isoformat()])
print('Exported contacts who explicitly opted in:',out)
