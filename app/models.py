from __future__ import annotations
from datetime import datetime, timezone
import uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Owner(Base):
    __tablename__='owners'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    username: Mapped[str]=mapped_column(String(64),unique=True,index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    apps: Mapped[list['Application']]=relationship(back_populates='owner',cascade='all, delete-orphan')

class PanelMember(Base):
    __tablename__ = "panel_members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    discord_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    discord_username: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Application(Base):
    __tablename__='applications'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    owner_id: Mapped[str]=mapped_column(ForeignKey('owners.id',ondelete='CASCADE'),index=True)
    name: Mapped[str]=mapped_column(String(100))
    version: Mapped[str]=mapped_column(String(32),default='1.0.0')
    public_id: Mapped[str]=mapped_column(String(40),unique=True,index=True)
    secret_hash: Mapped[str]=mapped_column(String(255))
    signing_private_key: Mapped[str]=mapped_column(Text)
    signing_public_key: Mapped[str]=mapped_column(Text)
    enabled: Mapped[bool]=mapped_column(Boolean,default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    owner: Mapped['Owner']=relationship(back_populates='apps')
    licenses: Mapped[list['License']]=relationship(back_populates='application',cascade='all, delete-orphan')
    sessions: Mapped[list['ClientSession']]=relationship(back_populates='application',cascade='all, delete-orphan')
    users: Mapped[list['LicensedUser']]=relationship(back_populates='application',cascade='all, delete-orphan')

class License(Base):
    __tablename__='licenses'; __table_args__=(UniqueConstraint('application_id','key',name='uq_app_license_key'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    application_id: Mapped[str]=mapped_column(ForeignKey('applications.id',ondelete='CASCADE'),index=True)
    key: Mapped[str]=mapped_column(String(100),index=True)
    expires_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    hwid: Mapped[str|None]=mapped_column(String(255),nullable=True)
    banned: Mapped[bool]=mapped_column(Boolean,default=False)
    note: Mapped[str|None]=mapped_column(String(255),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    last_used_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    application: Mapped['Application']=relationship(back_populates='licenses')

class LicensedUser(Base):
    __tablename__='licensed_users'; __table_args__=(UniqueConstraint('application_id','username',name='uq_app_user'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    application_id: Mapped[str]=mapped_column(ForeignKey('applications.id',ondelete='CASCADE'),index=True)
    username: Mapped[str]=mapped_column(String(64),index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    hwid: Mapped[str|None]=mapped_column(String(255),nullable=True)
    banned: Mapped[bool]=mapped_column(Boolean,default=False)
    expires_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    last_login_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    application: Mapped['Application']=relationship(back_populates='users')

class Reseller(Base):
    __tablename__='resellers'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    owner_id: Mapped[str]=mapped_column(ForeignKey('owners.id',ondelete='CASCADE'),index=True)
    username: Mapped[str]=mapped_column(String(64),index=True)
    credits: Mapped[int]=mapped_column(Integer,default=0)
    enabled: Mapped[bool]=mapped_column(Boolean,default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class HwidResetRequest(Base):
    __tablename__='hwid_reset_requests'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    owner_id: Mapped[str]=mapped_column(ForeKey('owners.id',ondelete='CASCADE'),index=True) if False else mapped_column(ForeignKey('owners.id',ondelete='CASCADE'),index=True)
    license_id: Mapped[str]=mapped_column(ForeignKey('licenses.id',ondelete='CASCADE'),index=True)
    reason: Mapped[str|None]=mapped_column(String(255),nullable=True)
    status: Mapped[str]=mapped_column(String(20),default='pending')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class Ban(Base):
    __tablename__='bans'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    owner_id: Mapped[str]=mapped_column(ForeignKey('owners.id',ondelete='CASCADE'),index=True)
    kind: Mapped[str]=mapped_column(String(20))
    value: Mapped[str]=mapped_column(String(255),index=True)
    reason: Mapped[str|None]=mapped_column(String(255),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class ApiKey(Base):
    __tablename__='api_keys'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    owner_id: Mapped[str]=mapped_column(ForeignKey('owners.id',ondelete='CASCADE'),index=True)
    name: Mapped[str]=mapped_column(String(80))
    key_hash: Mapped[str]=mapped_column(String(255))
    key_prefix: Mapped[str]=mapped_column(String(16))
    enabled: Mapped[bool]=mapped_column(Boolean,default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class Webhook(Base):
    __tablename__='webhooks'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    owner_id: Mapped[str]=mapped_column(ForeignKey('owners.id',ondelete='CASCADE'),index=True)
    name: Mapped[str]=mapped_column(String(80))
    url: Mapped[str]=mapped_column(String(500))
    event: Mapped[str]=mapped_column(String(80),default='license.auth')
    enabled: Mapped[bool]=mapped_column(Boolean,default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class ClientSession(Base):
    __tablename__='client_sessions'
    id: Mapped[str]=mapped_column(String(64),primary_key=True)
    application_id: Mapped[str]=mapped_column(ForeignKey('applications.id',ondelete='CASCADE'),index=True)
    nonce: Mapped[str]=mapped_column(String(64))
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    used: Mapped[bool]=mapped_column(Boolean,default=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    application: Mapped['Application']=relationship(back_populates='sessions')

class AuditLog(Base):
    __tablename__='audit_logs'
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    owner_id: Mapped[str|None]=mapped_column(String(36),nullable=True,index=True)
    application_id: Mapped[str|None]=mapped_column(String(36),nullable=True,index=True)
    event: Mapped[str]=mapped_column(String(80))
    ip_address: Mapped[str|None]=mapped_column(String(64),nullable=True)
    detail: Mapped[str|None]=mapped_column(Text,nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
