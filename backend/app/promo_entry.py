"""Only promotional endpoints and a static SPA. Does NOT import the trading backend."""
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from .promo_main import app

STATIC_DIR=Path(os.getenv('ORBIQUANT_STATIC_DIR',str(Path(__file__).resolve().parents[2]/'frontend'/'dist')))

class PromoFiles(StaticFiles):
    async def get_response(self,path,scope):
        try:
            resp=await super().get_response(path,scope)
        except HTTPException as ex:
            if ex.status_code!=404:raise
            resp=None
        if resp is not None and resp.status_code!=404:return resp
        if path.startswith('api/') or '.' in Path(path).name:
            if resp is not None: return resp
            raise HTTPException(404)
        return await super().get_response('index.html',scope)

app.mount('/',PromoFiles(directory=str(STATIC_DIR),html=True,check_dir=False),name='promo_site')
