from __future__ import annotations
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
import secrets
import urllib.parse
import httpx
from fastapi import Cookie, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, inspect, text
from sqlalchemy.orm import Session, selectinload
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .models import ApiKey, Application, AuditLog, Ban, ClientSession, HwidResetRequest, License, LicensedUser, Owner, PanelMember, Reseller, Webhook
from .schemas import InitRequest, LicenseAuthRequest
from .security import create_owner_token, create_panel_token, decode_owner_token, decode_panel_token, generate_app_credentials, generate_signing_keys, hash_password, hash_secret, sign_payload, verify_password, verify_secret

Base.metadata.create_all(bind=engine)

def migrate_legacy_schema():
    """Small compatibility migration for older Vivet SQLite databases."""
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "applications" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("applications")}
    if "version" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE applications ADD COLUMN version VARCHAR(32) NOT NULL DEFAULT '1.0.0'"))

migrate_legacy_schema()
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / 'static'
TEMPLATE_DIR = BASE_DIR / 'templates'

app = FastAPI(title=settings.app_name, version='0.3.0')
app.mount('/static', StaticFiles(directory=str(STATIC_DIR), check_dir=True), name='static')
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
NAV=[('/dashboard','Dashboard'),('/dashboard/applications','Applications'),('/dashboard/licenses','Licenses'),('/dashboard/users','Users'),('/dashboard/resellers','Resellers'),('/dashboard/hwid-resets','HWID Resets'),('/dashboard/bans','Bans'),('/dashboard/analytics','Analytics'),('/dashboard/logs','Logs'),('/dashboard/settings','Settings'),('/dashboard/api-keys','API Keys'),('/dashboard/webhooks','Webhooks'),('/dashboard/discord','Discord Access')]

def now_utc(): return datetime.now(timezone.utc)
def aware(value):
    if value is None:return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
def log(db,owner_id,event,detail=None,application_id=None,ip=None): db.add(AuditLog(owner_id=owner_id,application_id=application_id,event=event,detail=detail,ip_address=ip))
def seed_default_owner():
    with SessionLocal() as db:
        username=settings.owner_username.strip().lower()
        owner=db.scalar(select(Owner).where(Owner.username==username))
        if not owner:
            db.add(Owner(username=username,password_hash=hash_password(settings.owner_password))); db.commit()
seed_default_owner()

@app.middleware('http')
async def no_cache(request,call_next):
    response=await call_next(request)
    if request.url.path.startswith('/static/'):
        response.headers['Cache-Control']='no-store, max-age=0'
    return response

class Principal:
    def __init__(self, id: str, username: str, role: str = "owner", discord_id: str | None = None):
        self.id, self.username, self.role, self.discord_id = id, username, role, discord_id

def current_owner(owner_token:str|None=Cookie(default=None),db:Session=Depends(get_db)):
    payload=decode_panel_token(owner_token or '')
    if not payload: raise HTTPException(401,'Login required')
    if payload.get("kind", "owner") == "owner":
        owner=db.get(Owner,payload.get("sub"))
        if owner: return Principal(owner.id, owner.username, "owner")
    if payload.get("kind") == "discord":
        member=db.get(PanelMember,payload.get("sub"))
        if member and member.enabled: return Principal(member.owner_id, member.discord_username, member.role, member.discord_id)
    raise HTTPException(401,'Login required')

def ctx(request,owner,active,**kwargs): return {'request':request,'owner':owner,'active':active,'nav':NAV,**kwargs}
def signed_response(application,payload,http_status=200): return JSONResponse({'payload':payload,'signature':sign_payload(application.signing_private_key,payload)},status_code=http_status)

@app.get('/health')
def health(): return {'ok':True,'service':'Vivet'}
@app.get('/')
def home(): return RedirectResponse('/login')
@app.get('/login',response_class=HTMLResponse)
def login_page(request:Request): return templates.TemplateResponse('login.html',{'request':request,'error':None})
@app.post('/login')
def login(request:Request,username:str=Form(...),password:str=Form(...),db:Session=Depends(get_db)):
    owner=db.scalar(select(Owner).where(Owner.username==username.strip().lower()))
    if not owner or not verify_password(password,owner.password_hash): return templates.TemplateResponse('login.html',{'request':request,'error':'Invalid username or password.'},status_code=401)
    response=RedirectResponse('/dashboard',303); response.set_cookie('owner_token',create_owner_token(owner.id),httponly=True,secure=settings.cookie_secure,samesite='lax',max_age=settings.jwt_expire_minutes*60); return response

@app.get('/login/discord')
def discord_login():
    if not settings.discord_application_id or not settings.discord_client_secret:
        return RedirectResponse('/login?discord=disabled',303)
    params={
        'client_id':settings.discord_application_id,
        'redirect_uri':settings.base_url.rstrip('/')+'/auth/discord/callback',
        'response_type':'code','scope':'identify'
    }
    return RedirectResponse('https://discord.com/oauth2/authorize?'+urllib.parse.urlencode(params))

@app.get('/auth/discord/callback')
async def discord_callback(code:str,db:Session=Depends(get_db)):
    redirect_uri=settings.base_url.rstrip('/')+'/auth/discord/callback'
    async with httpx.AsyncClient(timeout=15) as client:
        token=await client.post('https://discord.com/api/oauth2/token',data={'client_id':settings.discord_application_id,'client_secret':settings.discord_client_secret,'grant_type':'authorization_code','code':code,'redirect_uri':redirect_uri},headers={'Content-Type':'application/x-www-form-urlencoded'})
        if token.status_code!=200: return RedirectResponse('/login?discord=failed',303)
        access=token.json().get('access_token')
        user=await client.get('https://discord.com/api/users/@me',headers={'Authorization':f'Bearer {access}'})
        if user.status_code!=200: return RedirectResponse('/login?discord=failed',303)
    data=user.json(); member=db.scalar(select(PanelMember).where(PanelMember.discord_id==str(data['id']),PanelMember.enabled==True))
    if not member: return RedirectResponse('/login?discord=unauthorized',303)
    member.discord_username=data.get('global_name') or data.get('username') or member.discord_username; db.commit()
    response=RedirectResponse('/dashboard',303); response.set_cookie('owner_token',create_panel_token(member.id,'discord'),httponly=True,secure=settings.cookie_secure,samesite='lax',max_age=settings.jwt_expire_minutes*60); return response

@app.post('/logout')
def logout():
    r=RedirectResponse('/login',303); r.delete_cookie('owner_token'); return r

@app.get('/dashboard',response_class=HTMLResponse)
def dashboard(request:Request,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    apps=db.scalars(select(Application).options(selectinload(Application.licenses),selectinload(Application.users)).where(Application.owner_id==owner.id).order_by(Application.created_at.desc())).all()
    licenses=[lic for a in apps for lic in a.licenses]; users=[u for a in apps for u in a.users]; now=now_utc()
    active_licenses=sum(not x.banned and (not x.expires_at or aware(x.expires_at)>now) for x in licenses)
    online=sum(bool(x.last_used_at and aware(x.last_used_at)>now-timedelta(minutes=5) and not x.banned) for x in licenses)
    logs=db.scalars(select(AuditLog).where(AuditLog.owner_id==owner.id).order_by(AuditLog.created_at.desc()).limit(6)).all()
    chart=[]; chart_total=0
    for offset in range(6,-1,-1):
        day=(now-timedelta(days=offset)).date(); count=db.scalar(select(func.count(AuditLog.id)).where(AuditLog.owner_id==owner.id,AuditLog.event=='license.auth',func.date(AuditLog.created_at)==day.isoformat())) or 0; chart_total+=count; chart.append({'label':day.strftime('%a'),'count':count})
    peak=max([x['count'] for x in chart] or [0]);
    for x in chart:x['height']=max(4,round(x['count']/peak*88)) if peak else 4
    stats={'apps':len(apps),'enabled_apps':sum(a.enabled for a in apps),'licenses':len(licenses),'active_licenses':active_licenses,'users':len(users),'online':online}
    return templates.TemplateResponse('dashboard.html',ctx(request,owner,'Dashboard',apps=apps,stats=stats,logs=logs,chart=chart,chart_values=[x['count'] for x in chart],chart_total=chart_total))

@app.get('/dashboard/applications',response_class=HTMLResponse)
def applications(request:Request,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    rows=db.scalars(select(Application).options(selectinload(Application.licenses)).where(Application.owner_id==owner.id).order_by(Application.created_at.desc())).all()
    return templates.TemplateResponse('applications.html',ctx(request,owner,'Applications',heading='Applications',subheading='Manage every software application connected to Vivet.',modal_id='create-app',action_label='Create Application',summary=[],table_title='All Applications',rows=rows,columns=['Name','App ID','Version','Licenses','Status','Action'],empty_text='No applications yet.'))
@app.post('/dashboard/apps')
def create_app(name:str=Form(...),version:str=Form('1.0.0'),owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    public_id,secret=generate_app_credentials(); private,public=generate_signing_keys(); a=Application(owner_id=owner.id,name=name.strip(),version=version.strip(),public_id=public_id,secret_hash=hash_secret(secret),signing_private_key=private,signing_public_key=public); db.add(a); log(db,owner.id,'application.created',a.name,a.id); db.commit(); db.refresh(a); return RedirectResponse(f'/dashboard/apps/{a.id}?secret={secret}',303)
@app.post('/dashboard/apps/{app_id}/toggle')
def toggle_app(app_id:str,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    a=db.scalar(select(Application).where(Application.id==app_id,Application.owner_id==owner.id));
    if not a:raise HTTPException(404)
    a.enabled=not a.enabled; log(db,owner.id,'application.status',f'{a.name}: {"enabled" if a.enabled else "disabled"}',a.id); db.commit(); return RedirectResponse('/dashboard/applications',303)

@app.get('/dashboard/licenses',response_class=HTMLResponse)
def licenses_page(request:Request,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    apps=db.scalars(select(Application).where(Application.owner_id==owner.id).order_by(Application.name)).all(); raw=db.scalars(select(License).join(Application).options(selectinload(License.application)).where(Application.owner_id==owner.id).order_by(License.created_at.desc())).all(); now=now_utc(); rows=[]
    for x in raw:
        status='Banned' if x.banned else ('Expired' if x.expires_at and aware(x.expires_at)<=now else 'Active'); rows.append(type('LicenseView',(),{'id':x.id,'key':x.key,'application':x.application,'status':status,'expires':'Lifetime' if not x.expires_at else aware(x.expires_at).strftime('%Y-%m-%d'),'hwid':x.hwid,'banned':x.banned})())
    summary=[{'label':'Total','value':len(rows),'note':'All generated keys'},{'label':'Active','value':sum(x.status=='Active' for x in rows),'note':'Usable now'},{'label':'Bound','value':sum(bool(x.hwid) for x in rows),'note':'HWID attached'}]
    return templates.TemplateResponse('licenses.html',ctx(request,owner,'Licenses',heading='Licenses',subheading='Generate, ban, reset, and delete license keys.',modal_id='create-license' if apps else None,action_label='Generate License',summary=summary,table_title='License Keys',rows=rows,apps=apps,columns=['License','Application','Status','Expires','HWID','Actions'],empty_text='No licenses yet. Create an application first, then generate a license.'))
@app.post('/dashboard/licenses')
def create_licenses(application_id:str=Form(...),duration_days:int=Form(30),quantity:int=Form(1),note:str=Form(''),owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    a=db.scalar(select(Application).where(Application.id==application_id,Application.owner_id==owner.id));
    if not a:raise HTTPException(404)
    quantity=max(1,min(quantity,100)); exp=now_utc()+timedelta(days=duration_days) if duration_days>0 else None
    for _ in range(quantity):db.add(License(application_id=a.id,key='VVT-'+'-'.join(secrets.token_hex(2).upper() for _ in range(4)),expires_at=exp,note=note.strip() or None))
    log(db,owner.id,'license.generated',f'{quantity} license(s) for {a.name}',a.id); db.commit(); return RedirectResponse('/dashboard/licenses',303)
@app.post('/dashboard/licenses/{license_id}/reset-hwid')
def reset_hwid(license_id:str,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    x=db.scalar(select(License).join(Application).where(License.id==license_id,Application.owner_id==owner.id));
    if not x:raise HTTPException(404)
    x.hwid=None; log(db,owner.id,'license.hwid_reset',x.key,x.application_id); db.commit(); return RedirectResponse(request_ref('/dashboard/licenses'),303)
def request_ref(default): return default
@app.post('/dashboard/licenses/{license_id}/toggle-ban')
def toggle_license_ban(license_id:str,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    x=db.scalar(select(License).join(Application).where(License.id==license_id,Application.owner_id==owner.id));
    if not x:raise HTTPException(404)
    x.banned=not x.banned; log(db,owner.id,'license.ban',f'{x.key}: {x.banned}',x.application_id); db.commit(); return RedirectResponse('/dashboard/licenses',303)
@app.post('/dashboard/licenses/{license_id}/delete')
def delete_license(license_id:str,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    x=db.scalar(select(License).join(Application).where(License.id==license_id,Application.owner_id==owner.id));
    if not x:raise HTTPException(404)
    db.delete(x); log(db,owner.id,'license.deleted',x.key,x.application_id); db.commit(); return RedirectResponse('/dashboard/licenses',303)

# Generic management pages
def generic_page(request,owner,active,heading,subheading,rows,columns,table_rows,empty,modal_id=None,action=None,modal_html='',summary=None):
    return templates.TemplateResponse('simple_rows.html',ctx(request,owner,active,heading=heading,subheading=subheading,modal_id=modal_id,action_label=action,summary=summary or [],table_title=heading,rows=rows,columns=columns,table_rows=table_rows,modal_html=modal_html,empty_text=empty))
def modal(title, action, fields, button='Create', tone='default'):
    meta = {
        'Create reseller': ('♙+', 'Add a reseller and choose their starting credit balance.'),
        'Create user': ('♙', 'Create a secure user account for one of your applications.'),
        'Add ban': ('◇', 'Block an IP address, HWID, or username from authenticating.'),
        'Create API key': ('</>', 'Generate a secure API key. It will only be shown once.'),
        'Add webhook': ('⌬', 'Send selected Vivet events to an external endpoint.'),
    }
    icon, description = meta.get(title, ('＋', 'Enter the details below to continue.'))
    body = ''.join(
        f'<label class="modal-field"><span>{escape(label)}</span>{field}</label>'
        for label, field in fields
    )
    tone_class = ' modal-danger' if tone == 'danger' else ''
    return (
        f'<dialog id="create-item" class="modal{tone_class}">'
        f'<form method="post" action="{action}">'
        f'<div class="modal-head"><div class="modal-title-wrap"><span class="modal-icon">{icon}</span>'
        f'<div><h2>{escape(title)}</h2><p>{escape(description)}</p></div></div>'
        f'<button type="button" class="modal-close" data-close aria-label="Close">×</button></div>'
        f'<div class="modal-body">{body}</div>'
        f'<div class="modal-actions"><button type="button" class="secondary-btn" data-close>Cancel</button>'
        f'<button class="primary modal-submit"><span>{escape(button)}</span></button></div>'
        f'</form></dialog>'
    )

@app.get('/dashboard/users',response_class=HTMLResponse)
def users_page(request:Request,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    apps=db.scalars(select(Application).where(Application.owner_id==owner.id)).all(); rows=db.scalars(select(LicensedUser).join(Application).options(selectinload(LicensedUser.application)).where(Application.owner_id==owner.id).order_by(LicensedUser.created_at.desc())).all(); trs=''.join(f'<tr><td>{escape(u.username)}</td><td>{escape(u.application.name)}</td><td><span class="status-pill {"off" if u.banned else ""}">{"Banned" if u.banned else "Active"}</span></td><td>{"Bound" if u.hwid else "Unbound"}</td><td>{aware(u.last_login_at).strftime("%Y-%m-%d %H:%M") if u.last_login_at else "Never"}</td><td><form method="post" action="/dashboard/users/{u.id}/toggle-ban"><button class="mini-btn danger">{"Unban" if u.banned else "Ban"}</button></form></td></tr>' for u in rows); options=''.join(f'<option value="{a.id}">{escape(a.name)}</option>' for a in apps); m=modal('Create user','/dashboard/users',[('Application',f'<select name="application_id">{options}</select>'),('Username','<input name="username" required>'),('Password','<input type="password" name="password" minlength="8" required>'),('Duration days','<input type="number" name="duration_days" value="30" min="0">')]) if apps else ''
    return generic_page(request,owner,'Users','Users','Application username/password accounts.',rows,['Username','Application','Status','HWID','Last login','Action'],trs,'No users yet.','create-item' if apps else None,'Create User',m)
@app.post('/dashboard/users')
def create_user(application_id:str=Form(...),username:str=Form(...),password:str=Form(...),duration_days:int=Form(30),owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    a=db.scalar(select(Application).where(Application.id==application_id,Application.owner_id==owner.id));
    if not a:raise HTTPException(404)
    db.add(LicensedUser(application_id=a.id,username=username.strip(),password_hash=hash_password(password),expires_at=now_utc()+timedelta(days=duration_days) if duration_days>0 else None)); log(db,owner.id,'user.created',username,a.id); db.commit(); return RedirectResponse('/dashboard/users',303)
@app.post('/dashboard/users/{user_id}/toggle-ban')
def toggle_user(user_id:str,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    u=db.scalar(select(LicensedUser).join(Application).where(LicensedUser.id==user_id,Application.owner_id==owner.id));
    if not u:raise HTTPException(404)
    u.banned=not u.banned; db.commit(); return RedirectResponse('/dashboard/users',303)

@app.get('/dashboard/resellers',response_class=HTMLResponse)
def resellers_page(request:Request,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    rows=db.scalars(select(Reseller).where(Reseller.owner_id==owner.id).order_by(Reseller.created_at.desc())).all(); trs=''.join(f'<tr><td>{escape(r.username)}</td><td>{r.credits}</td><td>{"Enabled" if r.enabled else "Disabled"}</td><td><form method="post" action="/dashboard/resellers/{r.id}/toggle"><button class="mini-btn">Toggle</button></form></td></tr>' for r in rows); m=modal('Create reseller','/dashboard/resellers',[('Username','<input name="username" placeholder="Enter reseller username" autocomplete="off" required>'),('Credits','<input type="number" name="credits" value="0" min="0" step="1">')]); return generic_page(request,owner,'Resellers','Resellers','Create reseller accounts and assign credits.',rows,['Username','Credits','Status','Action'],trs,'No resellers yet.','create-item','Create Reseller',m)
@app.post('/dashboard/resellers')
def create_reseller(username:str=Form(...),credits:int=Form(0),owner:Owner=Depends(current_owner),db:Session=Depends(get_db)): db.add(Reseller(owner_id=owner.id,username=username.strip(),credits=max(0,credits))); log(db,owner.id,'reseller.created',username); db.commit(); return RedirectResponse('/dashboard/resellers',303)
@app.post('/dashboard/resellers/{rid}/toggle')
def toggle_reseller(rid:str,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    r=db.scalar(select(Reseller).where(Reseller.id==rid,Reseller.owner_id==owner.id));
    if not r:raise HTTPException(404)
    r.enabled=not r.enabled; db.commit(); return RedirectResponse('/dashboard/resellers',303)

@app.get('/dashboard/hwid-resets',response_class=HTMLResponse)
def reset_page(request:Request,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    rows=db.scalars(select(HwidResetRequest).where(HwidResetRequest.owner_id==owner.id).order_by(HwidResetRequest.created_at.desc())).all(); trs=''.join(f'<tr><td>{escape((db.get(License,r.license_id).key if db.get(License,r.license_id) else "Deleted license"))}</td><td>{escape(r.reason or "—")}</td><td>{escape(r.status.title())}</td><td>{r.created_at.strftime("%Y-%m-%d %H:%M")}</td><td>{"<form method=\"post\" action=\"/dashboard/hwid-resets/"+r.id+"/approve\"><button class=\"mini-btn\">Approve</button></form>" if r.status=="pending" else "—"}</td></tr>' for r in rows); return generic_page(request,owner,'HWID Resets','HWID Reset Requests','Requests submitted for manual review.',rows,['License','Reason','Status','Created','Action'],trs,'No HWID reset requests.')
@app.post('/dashboard/hwid-resets/{rid}/approve')
def approve_reset(rid:str,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    r=db.scalar(select(HwidResetRequest).where(HwidResetRequest.id==rid,HwidResetRequest.owner_id==owner.id));
    if not r:raise HTTPException(404)
    lic=db.get(License,r.license_id)
    if lic:lic.hwid=None
    r.status='approved'; db.commit(); return RedirectResponse('/dashboard/hwid-resets',303)

@app.get('/dashboard/bans',response_class=HTMLResponse)
def bans_page(request:Request,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    rows=db.scalars(select(Ban).where(Ban.owner_id==owner.id).order_by(Ban.created_at.desc())).all(); trs=''.join(f'<tr><td>{escape(b.kind.upper())}</td><td><code>{escape(b.value)}</code></td><td>{escape(b.reason or "—")}</td><td>{b.created_at.strftime("%Y-%m-%d")}</td><td><form method="post" action="/dashboard/bans/{b.id}/delete"><button class="mini-btn danger">Remove</button></form></td></tr>' for b in rows); m=modal('Add ban','/dashboard/bans',[('Type','<select name="kind"><option>ip</option><option>hwid</option><option>username</option></select>'),('Value','<input name="value" required>'),('Reason','<input name="reason">')]); return generic_page(request,owner,'Bans','Bans','Block IP addresses, HWIDs, or usernames.',rows,['Type','Value','Reason','Created','Action'],trs,'No platform bans.','create-item','Add Ban',m)
@app.post('/dashboard/bans')
def create_ban(kind:str=Form(...),value:str=Form(...),reason:str=Form(''),owner:Owner=Depends(current_owner),db:Session=Depends(get_db)): db.add(Ban(owner_id=owner.id,kind=kind,value=value.strip(),reason=reason.strip() or None)); db.commit(); return RedirectResponse('/dashboard/bans',303)
@app.post('/dashboard/bans/{bid}/delete')
def delete_ban(bid:str,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    b=db.scalar(select(Ban).where(Ban.id==bid,Ban.owner_id==owner.id));
    if b:db.delete(b);db.commit()
    return RedirectResponse('/dashboard/bans',303)

@app.get('/dashboard/analytics',response_class=HTMLResponse)
def analytics(request:Request,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    logs=db.scalars(select(AuditLog).where(AuditLog.owner_id==owner.id).order_by(AuditLog.created_at.desc())).all(); success=sum(l.event=='license.auth' and l.detail=='Authenticated' for l in logs); failures=sum(l.event=='license.auth' and l.detail!='Authenticated' for l in logs); rows=[1]; trs=f'<tr><td>Successful authentications</td><td>{success}</td></tr><tr><td>Failed authentications</td><td>{failures}</td></tr><tr><td>Total logged events</td><td>{len(logs)}</td></tr>'; return generic_page(request,owner,'Analytics','Analytics','Live totals calculated from audit logs.',rows,['Metric','Value'],trs,'No analytics yet.',summary=[{'label':'Success','value':success,'note':'Authenticated'},{'label':'Failed','value':failures,'note':'Rejected'},{'label':'Events','value':len(logs),'note':'All activity'}])
@app.get('/dashboard/logs',response_class=HTMLResponse)
def logs_page(request:Request,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    rows=db.scalars(select(AuditLog).where(AuditLog.owner_id==owner.id).order_by(AuditLog.created_at.desc()).limit(500)).all(); trs=''.join(f'<tr><td>{l.created_at.strftime("%Y-%m-%d %H:%M:%S")}</td><td>{escape(l.event)}</td><td>{escape(l.detail or "—")}</td><td>{escape(l.ip_address or "—")}</td></tr>' for l in rows); return generic_page(request,owner,'Logs','Audit Logs','Real owner and client API activity.',rows,['Time','Event','Details','IP'],trs,'No logs yet.')

@app.get('/dashboard/settings',response_class=HTMLResponse)
def settings_page(request:Request,message:str|None=None,owner:Owner=Depends(current_owner)): return templates.TemplateResponse('settings.html',ctx(request,owner,'Settings',message=message))
@app.post('/dashboard/settings/password')
def change_password(current_password:str=Form(...),new_password:str=Form(...),owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    if not verify_password(current_password,owner.password_hash):return RedirectResponse('/dashboard/settings?message=Current+password+is+incorrect',303)
    owner.password_hash=hash_password(new_password); db.commit(); return RedirectResponse('/dashboard/settings?message=Password+updated',303)

@app.get('/dashboard/api-keys',response_class=HTMLResponse)
def keys_page(request:Request,new_key:str|None=None,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    rows=db.scalars(select(ApiKey).where(ApiKey.owner_id==owner.id).order_by(ApiKey.created_at.desc())).all(); trs=(''.join(f'<tr><td>{escape(k.name)}</td><td><code>{escape(k.key_prefix)}••••••••</code></td><td>{"Enabled" if k.enabled else "Disabled"}</td><td>{k.created_at.strftime("%Y-%m-%d")}</td><td><form method="post" action="/dashboard/api-keys/{k.id}/delete"><button class="mini-btn danger">Revoke</button></form></td></tr>' for k in rows)+(f'<tr class="new-secret"><td colspan="5">New key (shown once): <code>{escape(new_key)}</code></td></tr>' if new_key else '')); m=modal('Create API key','/dashboard/api-keys',[('Name','<input name="name" required>')]); return generic_page(request,owner,'API Keys','API Keys','Seller/admin keys are shown only once.',rows or ([1] if new_key else []),['Name','Key','Status','Created','Action'],trs,'No API keys yet.','create-item','Create API Key',m)
@app.post('/dashboard/api-keys')
def create_key(name:str=Form(...),owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    raw='vvt_'+secrets.token_urlsafe(32); db.add(ApiKey(owner_id=owner.id,name=name.strip(),key_hash=hash_secret(raw),key_prefix=raw[:12])); db.commit(); return RedirectResponse('/dashboard/api-keys?new_key='+raw,303)
@app.post('/dashboard/api-keys/{kid}/delete')
def delete_key(kid:str,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    k=db.scalar(select(ApiKey).where(ApiKey.id==kid,ApiKey.owner_id==owner.id));
    if k:db.delete(k);db.commit()
    return RedirectResponse('/dashboard/api-keys',303)

@app.get('/dashboard/webhooks',response_class=HTMLResponse)
def webhooks_page(request:Request,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    rows=db.scalars(select(Webhook).where(Webhook.owner_id==owner.id).order_by(Webhook.created_at.desc())).all(); trs=''.join(f'<tr><td>{escape(w.name)}</td><td><code>{escape(w.url)}</code></td><td>{escape(w.event)}</td><td>{"Enabled" if w.enabled else "Disabled"}</td><td><form method="post" action="/dashboard/webhooks/{w.id}/delete"><button class="mini-btn danger">Delete</button></form></td></tr>' for w in rows); m=modal('Add webhook','/dashboard/webhooks',[('Name','<input name="name" required>'),('URL','<input type="url" name="url" required>'),('Event','<select name="event"><option>license.auth</option><option>license.generated</option><option>user.created</option></select>')]); return generic_page(request,owner,'Webhooks','Webhooks','Store webhook endpoints for platform events.',rows,['Name','URL','Event','Status','Action'],trs,'No webhooks configured.','create-item','Add Webhook',m)
@app.post('/dashboard/webhooks')
def create_webhook(name:str=Form(...),url:str=Form(...),event:str=Form(...),owner:Owner=Depends(current_owner),db:Session=Depends(get_db)): db.add(Webhook(owner_id=owner.id,name=name.strip(),url=url.strip(),event=event)); db.commit(); return RedirectResponse('/dashboard/webhooks',303)
@app.post('/dashboard/webhooks/{wid}/delete')
def delete_webhook(wid:str,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    w=db.scalar(select(Webhook).where(Webhook.id==wid,Webhook.owner_id==owner.id));
    if w:db.delete(w);db.commit()
    return RedirectResponse('/dashboard/webhooks',303)

@app.get('/dashboard/discord',response_class=HTMLResponse)
def discord_access_page(request:Request,owner=Depends(current_owner),db:Session=Depends(get_db)):
    rows=db.scalars(select(PanelMember).where(PanelMember.owner_id==owner.id).order_by(PanelMember.enabled.desc(),PanelMember.created_at.desc())).all()
    configured=bool(settings.discord_application_id and settings.discord_client_secret and settings.discord_bot_token)
    return templates.TemplateResponse('discord_access.html',ctx(request,owner,'Discord Access',rows=rows,configured=configured,guild_id=settings.discord_guild_id))

@app.post('/dashboard/discord/{member_id}/toggle')
def toggle_discord_member(member_id:str,owner=Depends(current_owner),db:Session=Depends(get_db)):
    member=db.scalar(select(PanelMember).where(PanelMember.id==member_id,PanelMember.owner_id==owner.id))
    if not member: raise HTTPException(404)
    member.enabled=not member.enabled; log(db,owner.id,'discord.auth.toggle',f'{member.discord_username}: {member.enabled}'); db.commit()
    return RedirectResponse('/dashboard/discord',303)

@app.get('/dashboard/apps/{app_id}',response_class=HTMLResponse)
def app_detail(app_id:str,request:Request,secret:str|None=None,owner:Owner=Depends(current_owner),db:Session=Depends(get_db)):
    a=db.scalar(select(Application).options(selectinload(Application.licenses),selectinload(Application.users)).where(Application.id==app_id,Application.owner_id==owner.id));
    if not a:raise HTTPException(404)
    return templates.TemplateResponse('app_detail.html',ctx(request,owner,'Applications',application=a,licenses=a.licenses,new_secret=secret))
@app.post('/dashboard/apps/{app_id}/licenses')
def app_create_license(app_id:str,duration_days:int=Form(30),note:str=Form(''),owner:Owner=Depends(current_owner),db:Session=Depends(get_db)): return create_licenses(app_id,duration_days,1,note,owner,db)

@app.post('/api/v1/init')
def api_init(data:InitRequest,request:Request,db:Session=Depends(get_db)):
    a=db.scalar(select(Application).where(Application.public_id==data.app_id));
    if not a or not a.enabled or not verify_secret(data.app_secret,a.secret_hash):raise HTTPException(401,'Invalid application credentials')
    sid=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(24);db.add(ClientSession(id=sid,application_id=a.id,nonce=nonce,expires_at=now_utc()+timedelta(minutes=5)));log(db,a.owner_id,'session.init','Client session created',a.id,request.client.host if request.client else None);db.commit();return signed_response(a,{'success':True,'session_id':sid,'nonce':nonce,'expires_in':300,'server_time':now_utc().isoformat(),'public_key':a.signing_public_key})
@app.post('/api/v1/license/auth')
def api_license_auth(data:LicenseAuthRequest,request:Request,db:Session=Depends(get_db)):
    a=db.scalar(select(Application).where(Application.public_id==data.app_id));
    if not a or not a.enabled:raise HTTPException(404,'Application not found')
    ip=request.client.host if request.client else None; ban=db.scalar(select(Ban).where(Ban.owner_id==a.owner_id,((Ban.kind=='ip')&(Ban.value==ip))|((Ban.kind=='hwid')&(Ban.value==data.hwid))))
    if ban:return signed_response(a,{'success':False,'message':'Client banned'},403)
    s=db.get(ClientSession,data.session_id); now=now_utc()
    if not s or s.application_id!=a.id or s.used or aware(s.expires_at)<now:return signed_response(a,{'success':False,'message':'Invalid or expired session'},401)
    s.used=True;x=db.scalar(select(License).where(License.application_id==a.id,License.key==data.license_key))
    if not x:result={'success':False,'message':'Invalid license'}
    elif x.banned:result={'success':False,'message':'License banned'}
    elif x.expires_at and aware(x.expires_at)<now:result={'success':False,'message':'License expired'}
    elif x.hwid and x.hwid!=data.hwid:result={'success':False,'message':'HWID mismatch'}
    else:
        if not x.hwid:x.hwid=data.hwid
        x.last_used_at=now;result={'success':True,'message':'Authenticated','license':{'expires_at':aware(x.expires_at).isoformat() if x.expires_at else None,'hwid_bound':True},'server_time':now.isoformat()}
    log(db,a.owner_id,'license.auth',result['message'],a.id,ip);db.commit();return signed_response(a,result,200 if result['success'] else 401)
