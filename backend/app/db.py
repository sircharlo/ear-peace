from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Generator

from sqlmodel import SQLModel, Field, create_engine, Session, select

DB_PATH = Path(os.getenv("EARPEACE_DB_PATH", "storage/app.db")).resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
ENGINE = create_engine(f"sqlite:///{DB_PATH}", echo=False)


class MediaAsset(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ad_key: str = Field(index=True)
    ad_lang: str = Field(index=True)
    non_ad_key: str = Field(index=True)
    mp4_path: str | None = None
    wav_path: str | None = None
    file_size: int | None = None
    status: str = Field(default="pending", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(ENGINE)
    # Best-effort migration: add file_size column if missing (SQLite only)
    try:
        with ENGINE.connect() as conn:
            cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(mediaasset);")]
            if "file_size" not in cols:
                conn.exec_driver_sql("ALTER TABLE mediaasset ADD COLUMN file_size INTEGER;")
    except Exception:
        # Non-fatal if migration fails; code can operate without the column in fresh DBs
        pass


def get_session() -> Generator[Session, None, None]:
    with Session(ENGINE) as session:
        yield session


def upsert_media_asset(*, ad_key: str, ad_lang: str, non_ad_key: str, mp4_path: str | None, wav_path: str | None, file_size: int | None, status: str) -> MediaAsset:
    with Session(ENGINE) as session:
        stmt = select(MediaAsset).where(MediaAsset.non_ad_key == non_ad_key)
        asset = session.exec(stmt).first()
        if asset is None:
            asset = MediaAsset(
                ad_key=ad_key, ad_lang=ad_lang, non_ad_key=non_ad_key,
                mp4_path=mp4_path, wav_path=wav_path, file_size=file_size, status=status,
            )
            session.add(asset)
        else:
            asset.ad_key = ad_key
            asset.ad_lang = ad_lang
            asset.mp4_path = mp4_path
            asset.wav_path = wav_path
            asset.file_size = file_size
            asset.status = status
            asset.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(asset)
        return asset


def get_assets_by_status(status: str) -> list[MediaAsset]:
    with Session(ENGINE) as session:
        stmt = select(MediaAsset).where(MediaAsset.status == status)
        return list(session.exec(stmt).all())


class CustomMedia(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    title: str | None = None
    file_path: str
    file_size: int | None = None
    wav_path: str | None = None
    status: str = Field(default="pending", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


def upsert_custom_media(*, key: str, title: str | None, file_path: str, file_size: int | None, wav_path: str | None, status: str) -> CustomMedia:
    with Session(ENGINE) as session:
        stmt = select(CustomMedia).where(CustomMedia.key == key)
        row = session.exec(stmt).first()
        if row is None:
            row = CustomMedia(key=key, title=title, file_path=file_path, file_size=file_size, wav_path=wav_path, status=status)
            session.add(row)
        else:
            row.title = title
            row.file_path = file_path
            row.file_size = file_size
            row.wav_path = wav_path
            row.status = status
            row.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(row)
        return row


def get_custom_by_status(status: str) -> list[CustomMedia]:
    with Session(ENGINE) as session:
        stmt = select(CustomMedia).where(CustomMedia.status == status)
        return list(session.exec(stmt).all())


def get_all_custom() -> list[CustomMedia]:
    with Session(ENGINE) as session:
        stmt = select(CustomMedia)
        return list(session.exec(stmt).all())


def delete_custom_by_key(key: str) -> None:
    with Session(ENGINE) as session:
        stmt = select(CustomMedia).where(CustomMedia.key == key)
        row = session.exec(stmt).first()
        if row:
            session.delete(row)
            session.commit()


def get_asset_by_non_ad(non_ad_key: str) -> MediaAsset | None:
    with Session(ENGINE) as session:
        stmt = select(MediaAsset).where(MediaAsset.non_ad_key == non_ad_key)
        return session.exec(stmt).first()


def get_all_assets() -> list[MediaAsset]:
    with Session(ENGINE) as session:
        stmt = select(MediaAsset)
        return list(session.exec(stmt).all())


def delete_asset_by_paths(mp4_path: str | None, wav_path: str | None) -> None:
    with Session(ENGINE) as session:
        stmt = select(MediaAsset)
        for asset in session.exec(stmt).all():
            if (mp4_path and asset.mp4_path == mp4_path) or (wav_path and asset.wav_path == wav_path):
                session.delete(asset)
                session.commit()
                return


def delete_asset_by_nonad(non_ad_key: str) -> None:
    with Session(ENGINE) as session:
        stmt = select(MediaAsset).where(MediaAsset.non_ad_key == non_ad_key)
        asset = session.exec(stmt).first()
        if asset:
            session.delete(asset)
            session.commit()
