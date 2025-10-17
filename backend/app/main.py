from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional

from fastapi.middleware.cors import CORSMiddleware
import httpx
import re
import os
from pathlib import Path
import asyncio
import subprocess
from .db import (
    create_db_and_tables,
    upsert_media_asset,
    get_assets_by_status,
    get_asset_by_non_ad,
    get_all_assets,
    upsert_custom_media,
    get_all_custom,
    get_custom_by_status,
    delete_custom_by_key,
    delete_asset_by_paths,
    delete_asset_by_nonad,
)
from . import fp as fplib

app = FastAPI(title="EarPeace Backend", version="0.1.0")

# CORS for local dev and configurable origins via env
_env_origins = os.getenv("EARPEACE_CORS_ORIGINS")
if _env_origins:
    _allow_origins = [o.strip() for o in _env_origins.split(",") if o.strip()]
else:
    _allow_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on startup (after app is created)
@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()
    # Start maintenance scheduler if enabled
    try:
        interval = int(os.getenv("EARPEACE_CRON_INTERVAL_SECONDS", "86400"))
    except Exception:
        interval = 86400
    if interval > 0:
        asyncio.get_event_loop().create_task(_maintenance_scheduler(interval))


class Clip(BaseModel):
    id: str  # languageAgnosticNaturalKey
    title: str
    duration_ms: Optional[int] = None
    fingerprint_status: str = "pending"
    # Optional extra metadata
    language: Optional[str] = None  # languageCode (e.g., 'E')


class MatchResult(BaseModel):
    clip_id: str
    t_offset_ms: int
    confidence: float


JW_BASE = "https://b.jw-cdn.org/apis/mediator/v1"
JW_CATEGORY_URL = JW_BASE + "/categories/E/VODMidweekMeetingAD?detailed=1&mediaLimit=0&clientType=www"
STORAGE_DIR = Path(os.getenv("EARPEACE_STORAGE_DIR", "backend/storage")).resolve()
INDEX_DIR = STORAGE_DIR / "indexes"
TEMP_DIR = STORAGE_DIR / "tmp"
CUSTOM_DIR = STORAGE_DIR / "custom"

# Maintenance state
LAST_MAINTENANCE_AT: Optional[float] = None


def _ms_from_seconds(sec: Optional[float]) -> Optional[int]:
    if sec is None:
        return None
    try:
        return int(round(sec * 1000))
    except Exception:
        return None


def pick_preferred_file(files: list) -> Optional[dict]:
    if not files:
        return None
    labels = {f.get("label"): f for f in files}
    for l in ["240p", "360p", "480p", "720p", "144p"]:
        if l in labels and labels[l].get("progressiveDownloadURL"):
            return labels[l]
    for f in files:
        if f.get("progressiveDownloadURL"):
            return f
    return None


def compute_non_ad_natural_key(ad_natural_key: str) -> Optional[str]:
    # Examples: pub-sjjm_E_539_VIDEO  |  pub-jwb_E_201908_104_VIDEO
    try:
        lowered = ad_natural_key.lower()
        # find the last numeric group between underscores
        m = re.search(r"_(\d+)_video$", lowered)
        if not m:
            return None
        num = int(m.group(1))
        delta = 500 if "sjj" in lowered else 100
        new_num = max(0, num - delta)
        # replace only the last occurrence of _{num}_VIDEO (case-preserving VIDEO)
        return re.sub(r"_(\d+)(_VIDEO)$", f"_{new_num}\\2", ad_natural_key)
    except Exception:
        return None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/clips/week", response_model=List[Clip])
async def get_weekly_clips() -> List[Clip]:
    # Fetch the AD category and map to clip items
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(JW_CATEGORY_URL)
        r.raise_for_status()
        data = r.json()

    media = (data or {}).get("category", {}).get("media", []) or []
    lang_code = (data or {}).get("language", {}).get("languageCode", "E")
    clips: List[Clip] = []
    for item in media:
        nat = item.get("languageAgnosticNaturalKey") or item.get("naturalKey")
        title = item.get("title") or "Untitled"
        duration_s = item.get("duration")
        duration_ms = _ms_from_seconds(duration_s)
        if not nat:
            continue
        clips.append(
            Clip(
                id=nat,
                title=title,
                duration_ms=duration_ms,
                fingerprint_status="pending",
                language=lang_code,
            )
        )
    return clips


class PreprocessRequest(BaseModel):
    clip_urls: List[str]


@app.post("/fingerprint/preprocess")
def preprocess_fingerprints(req: PreprocessRequest) -> dict:
    # TODO: queue background job to download, fingerprint, and store hashes
    if not req.clip_urls:
        raise HTTPException(status_code=400, detail="clip_urls cannot be empty")
    return {"queued": len(req.clip_urls)}


@app.post("/match", response_model=MatchResult)
async def match_clip(
    audio: UploadFile = File(...),
    clip_id: Optional[str] = Query(None, description="Restrict matching to this AD naturalKey"),
    lang: str = Query("E", description="Language code for clip_id resolution if needed"),
) -> MatchResult:
    # Convert to WAV (mono/16k), fingerprint, and match against indexed references
    if audio.content_type not in ("audio/webm", "audio/webm;codecs=opus", "audio/wav", "audio/x-wav", "audio/mpeg"):
        raise HTTPException(status_code=415, detail=f"Unsupported content-type: {audio.content_type}")

    # Ensure temp dir
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    # Save upload to temp file
    raw_path = TEMP_DIR / "query_input.bin"
    with open(raw_path, "wb") as f:
        f.write(await audio.read())

    # Transcode to WAV mono/16k
    q_wav = TEMP_DIR / "query.wav"
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", str(raw_path),
        "-ac", "1", "-ar", "16000", str(q_wav)
    ]
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0 or not q_wav.exists():
            raise RuntimeError("ffmpeg failed to transcode query")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="ffmpeg not found. Please install ffmpeg.")

    # Build index map from DB (indexed assets)
    indexed = get_assets_by_status("indexed")
    custom_indexed = get_custom_by_status("indexed")
    indices = {}
    if clip_id:
        # Support custom media restriction
        if clip_id.startswith("custom:"):
            key = clip_id.split(":", 1)[1]
            idx_path = INDEX_DIR / f"custom_{key}.fp"
            if idx_path.exists():
                indices[clip_id] = idx_path
            if not indices:
                raise HTTPException(status_code=400, detail="No custom index available for requested key")
            # proceed to match only against this custom index
        else:
            # Restrict to selected clip only
            non_ad_hint = compute_non_ad_natural_key(clip_id)
            if non_ad_hint:
                idx_path = INDEX_DIR / f"{non_ad_hint.replace('/', '_')}.fp"
                if idx_path.exists():
                    indices[non_ad_hint] = idx_path
            # If not found by hint, try to resolve actual naturalKey via JW
            if not indices:
                # Reuse non-ad resolver to get actual key
                url = f"{JW_BASE}/media-items/{lang}/{non_ad_hint or clip_id}?clientType=www"
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.get(url)
                    if r.status_code == 200:
                        data = r.json()
                        media = ((data or {}).get("media") or [{}])[0] or {}
                        non_ad_key = media.get("naturalKey")
                        if non_ad_key:
                            idx_path = INDEX_DIR / f"{non_ad_key.replace('/', '_')}.fp"
                            if idx_path.exists():
                                indices[non_ad_key] = idx_path
    else:
        for asset in indexed:
            idx_path = INDEX_DIR / f"{asset.non_ad_key.replace('/', '_')}.fp"
            if idx_path.exists():
                indices[asset.non_ad_key] = idx_path
        for cm in custom_indexed:
            idx_path = INDEX_DIR / f"custom_{cm.key}.fp"
            if idx_path.exists():
                indices[f"custom:{cm.key}"] = idx_path

    if not indices:
        raise HTTPException(status_code=400, detail="No indexed references available. Prepare and build fingerprints first.")

    # Run match
    try:
        best_key, offset_sec, conf = fplib.match_query(q_wav, indices)
    except Exception:
        raise HTTPException(status_code=500, detail="Matching failed")

    if not best_key or conf <= 0:
        raise HTTPException(status_code=404, detail="No match found")

    # Map non-AD key back to AD key for client convenience, or custom key
    out_clip_id: str
    if clip_id and clip_id.startswith("custom:"):
        out_clip_id = clip_id
    else:
        asset = get_asset_by_non_ad(best_key)
        out_clip_id = asset.ad_key if asset else (clip_id or best_key)
    return MatchResult(clip_id=out_clip_id, t_offset_ms=int(round(offset_sec * 1000)), confidence=float(conf))


@app.get("/ad-url")
async def get_ad_url(
    clip_id: str = Query(..., description="languageAgnosticNaturalKey (e.g., pub-..._VIDEO)"),
    lang: str = Query("E", description="languageCode, e.g., 'E'"),
) -> dict:
    # Resolve the AD media item and choose a progressiveDownloadURL (prefer mp4 240p/360p for lighter bandwidth)
    url = f"{JW_BASE}/media-items/{lang}/{clip_id}?clientType=www"
    print("Attempting to fetch AD item:", url)
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="AD item not found")
        r.raise_for_status()
        data = r.json()

    files = (((data or {}).get("media") or [{}])[0] or {}).get("files", []) or []
    if not files:
        raise HTTPException(status_code=404, detail="No files available for AD item")

    # Pick a reasonable file (prefer 240p/360p mp4 for compatibility)
    chosen = pick_preferred_file(files) or files[0]

    ad_url = chosen.get("progressiveDownloadURL")
    if not ad_url:
        raise HTTPException(status_code=404, detail="No progressiveDownloadURL available")
    return {"clip_id": clip_id, "ad_url": ad_url}


@app.get("/nonad-item")
async def get_non_ad_item(
    ad_natural_key: str = Query(..., description="AD languageAgnosticNaturalKey (e.g., pub-..._VIDEO)"),
    ad_lang: str = Query("E", description="languageCode, e.g., 'E'"),
) -> dict:
    non_ad_key = compute_non_ad_natural_key(ad_natural_key)
    if not non_ad_key:
        raise HTTPException(status_code=400, detail="Could not compute non-AD naturalKey from input")

    url = f"{JW_BASE}/media-items/{ad_lang}/{non_ad_key}?clientType=www"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="Non-AD item not found")
        r.raise_for_status()
        data = r.json()

    # Return a compact subset: key, files, title, duration
    media = ((data or {}).get("media") or [{}])[0] or {}
    return {
        "naturalKey": media.get("naturalKey", non_ad_key),
        "title": media.get("title"),
        "duration": media.get("duration"),
        "files": media.get("files", []),
    }


# -------- Maintenance (scheduler/admin) --------
async def _prepare_all_sync() -> int:
    # Fetch weekly clips and prepare sequentially
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(JW_CATEGORY_URL)
        r.raise_for_status()
        data = r.json()
    media = (data or {}).get("category", {}).get("media", []) or []
    ad_lang = (data or {}).get("language", {}).get("languageCode", "E")

    prepared = 0
    for item in media:
        ad_key = item.get("languageAgnosticNaturalKey") or item.get("naturalKey")
        if not ad_key:
            continue
        non_ad_hint = compute_non_ad_natural_key(ad_key) or ""
        asset = get_asset_by_non_ad(non_ad_hint) if non_ad_hint else None
        if asset and asset.status in ("prepared", "indexed"):
            continue
        try:
            await _prepare_non_ad(ad_key, ad_lang)
            prepared += 1
        except Exception:
            continue
    return prepared


async def run_maintenance() -> dict:
    global LAST_MAINTENANCE_AT
    prepared = await _prepare_all_sync()
    built = (await fingerprint_build()).get("indexed", 0)
    LAST_MAINTENANCE_AT = asyncio.get_event_loop().time()
    return {"prepared": prepared, "indexed": built, "last_run": LAST_MAINTENANCE_AT}


async def _maintenance_scheduler(interval_seconds: int) -> None:
    global LAST_MAINTENANCE_AT
    while True:
        try:
            await run_maintenance()
        except Exception:
            pass
        # sleep for interval
        await asyncio.sleep(max(60, interval_seconds))


@app.get("/admin/status")
async def admin_status() -> dict:
    try:
        interval = int(os.getenv("EARPEACE_CRON_INTERVAL_SECONDS", "86400"))
    except Exception:
        interval = 86400
    # summarize counts by status
    assets = get_all_assets()
    counts: dict[str, int] = {}
    for a in assets:
        counts[a.status] = counts.get(a.status, 0) + 1
    return {
        "last_maintenance_at": LAST_MAINTENANCE_AT,
        "interval_seconds": interval,
        "counts": counts,
        "total_assets": len(assets),
    }


@app.post("/admin/maintenance")
async def admin_maintenance() -> dict:
    # trigger in background
    asyncio.create_task(run_maintenance())
    return {"started": True}


@app.get("/fingerprint/assets")
async def fingerprint_assets() -> list[dict]:
    out = []
    for a in get_all_assets():
        out.append({
            "ad_key": a.ad_key,
            "ad_lang": a.ad_lang,
            "non_ad_key": a.non_ad_key,
            "mp4_path": a.mp4_path,
            "wav_path": a.wav_path,
            "status": a.status,
            "updated_at": a.updated_at.isoformat() if hasattr(a, "updated_at") and a.updated_at else None,
        })
    return out


# -------- Custom media endpoints --------
class CustomUploadResponse(BaseModel):
    keys: List[str]
    started: bool = True


@app.post("/admin/custom/upload", response_model=CustomUploadResponse)
async def admin_custom_upload(files: List[UploadFile] = File(...)) -> CustomUploadResponse:
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    keys: List[str] = []
    for f in files:
        # derive a safe key from filename (without extension)
        name = Path(f.filename or "file").stem
        base_key = re.sub(r"[^a-zA-Z0-9_-]", "_", name).strip("_") or "media"
        key = base_key
        i = 1
        while any(cm.key == key for cm in get_all_custom()):
            key = f"{base_key}_{i}"
            i += 1
        # save upload to disk under custom dir
        dst_path = CUSTOM_DIR / f"{key}{Path(f.filename or '').suffix or '.bin'}"
        with open(dst_path, "wb") as out:
            out.write(await f.read())
        size = dst_path.stat().st_size
        upsert_custom_media(key=key, title=name, file_path=str(dst_path), file_size=size, wav_path=None, status="downloaded")
        # background prepare and index
        asyncio.create_task(_prepare_and_index_custom(key))
        keys.append(key)
    return CustomUploadResponse(keys=keys, started=True)


@app.get("/admin/custom/list")
async def admin_custom_list() -> list[dict]:
    out = []
    for cm in get_all_custom():
        out.append({
            "key": cm.key,
            "title": cm.title,
            "file_path": cm.file_path,
            "file_size": cm.file_size,
            "wav_path": cm.wav_path,
            "status": cm.status,
            "updated_at": cm.updated_at.isoformat() if cm.updated_at else None,
        })
    return out


@app.get("/admin/custom/status")
async def admin_custom_status(key: str = Query(...)) -> dict:
    for cm in get_all_custom():
        if cm.key == key:
            return {
                "key": cm.key,
                "status": cm.status,
                "file_path": cm.file_path,
                "wav_path": cm.wav_path,
                "updated_at": cm.updated_at.isoformat() if cm.updated_at else None,
            }
    return {"status": "missing"}


@app.delete("/admin/custom")
async def admin_custom_delete(key: str = Query(...)) -> dict:
    # delete files and index
    idx_path = INDEX_DIR / f"custom_{key}.fp"
    try:
        for cm in get_all_custom():
            if cm.key == key:
                try:
                    if cm.file_path and Path(cm.file_path).exists():
                        Path(cm.file_path).unlink(missing_ok=True)
                    if cm.wav_path and Path(cm.wav_path).exists():
                        Path(cm.wav_path).unlink(missing_ok=True)
                except Exception:
                    pass
                break
        idx_path.unlink(missing_ok=True)
    finally:
        delete_custom_by_key(key)
    return {"deleted": True}


@app.get("/custom/file")
async def custom_file(key: str = Query(...)):
    for cm in get_all_custom():
        if cm.key == key and cm.file_path and Path(cm.file_path).exists():
            # Let browser infer type by extension
            return FileResponse(path=cm.file_path)
    raise HTTPException(status_code=404, detail="File not found")


def _safe_join_storage(rel_path: str) -> Path:
    p = (STORAGE_DIR / rel_path).resolve()
    if not str(p).startswith(str(STORAGE_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    return p


@app.get("/admin/storage/list")
async def admin_storage_list() -> list[dict]:
    out: list[dict] = []
    for root, dirs, files in os.walk(STORAGE_DIR):
        for fn in files:
            full = Path(root) / fn
            # skip DB file
            if full.name.endswith(".db"):
                continue
            rel = str(full.relative_to(STORAGE_DIR))
            try:
                size = full.stat().st_size
            except Exception:
                size = 0
            out.append({"rel_path": rel, "size": size})
    out.sort(key=lambda x: x["rel_path"])
    return out


@app.delete("/admin/storage")
async def admin_storage_delete(rel_path: str = Query(...)) -> dict:
    target = _safe_join_storage(rel_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    # Attempt DB cleanup for API media
    try:
        delete_asset_by_paths(str(target), None)
    except Exception:
        pass
    # Attempt DB cleanup for custom media
    try:
        # find custom by file path or wav path
        for cm in get_all_custom():
            if cm.file_path == str(target) or cm.wav_path == str(target):
                # delete index
                idxp = INDEX_DIR / f"custom_{cm.key}.fp"
                idxp.unlink(missing_ok=True)
                delete_custom_by_key(cm.key)
                break
    except Exception:
        pass
    # Attempt to remove API index if rel path resembles wav or by non-ad key derivation
    try:
        # if filename corresponds to a non_ad key base
        base = target.stem
        idx_try = INDEX_DIR / f"{base}.fp"
        idx_try.unlink(missing_ok=True)
    except Exception:
        pass
    # finally delete file
    try:
        target.unlink(missing_ok=True)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete file")
    return {"deleted": True}


async def _prepare_and_index_custom(key: str) -> None:
    # load record
    target = None
    for cm in get_all_custom():
        if cm.key == key:
            target = cm
            break
    if not target:
        return
    # transcode to wav mono/16k
    wav_path = CUSTOM_DIR / f"{key}.wav"
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", str(target.file_path),
        "-ac", "1", "-ar", "16000", str(wav_path)
    ]
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            return
    except FileNotFoundError:
        return
    upsert_custom_media(key=key, title=target.title, file_path=target.file_path, file_size=target.file_size, wav_path=str(wav_path), status="prepared")
    # build index
    try:
        idx = fplib.index_reference(wav_path)
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        fplib.save_index(idx, INDEX_DIR / f"custom_{key}.fp")
        upsert_custom_media(key=key, title=target.title, file_path=target.file_path, file_size=target.file_size, wav_path=str(wav_path), status="indexed")
    except Exception:
        pass


class EnqueueRequest(BaseModel):
    ad_natural_key: str
    ad_lang: str = "E"


async def _prepare_non_ad(ad_natural_key: str, ad_lang: str) -> dict:
    non_ad_key_hint = compute_non_ad_natural_key(ad_natural_key)
    if not non_ad_key_hint:
        raise HTTPException(status_code=400, detail="Invalid naturalKey")

    url = f"{JW_BASE}/media-items/{ad_lang}/{non_ad_key_hint}?clientType=www"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="Non-AD item not found")
        r.raise_for_status()
        data = r.json()

    media = ((data or {}).get("media") or [{}])[0] or {}
    non_ad_key = media.get("naturalKey") or non_ad_key_hint
    files = media.get("files", []) or []
    chosen = pick_preferred_file(files) or (files[0] if files else None)
    if not chosen or not chosen.get("progressiveDownloadURL"):
        raise HTTPException(status_code=404, detail="No downloadable file found")

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    base_name = non_ad_key.replace("/", "_")
    src_path = STORAGE_DIR / f"{base_name}.mp4"
    wav_path = STORAGE_DIR / f"{base_name}.wav"

    upsert_media_asset(
        ad_key=ad_natural_key,
        ad_lang=ad_lang,
        non_ad_key=non_ad_key,
        mp4_path=str(src_path),
        wav_path=None,
        status="downloading",
    )

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("GET", chosen["progressiveDownloadURL"]) as resp:
            resp.raise_for_status()
            with open(src_path, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)

    upsert_media_asset(
        ad_key=ad_natural_key,
        ad_lang=ad_lang,
        non_ad_key=non_ad_key,
        mp4_path=str(src_path),
        wav_path=None,
        status="downloaded",
    )

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", str(src_path),
        "-ac", "1", "-ar", "16000", str(wav_path)
    ]
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("ffmpeg failed")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="ffmpeg not found. Please install ffmpeg.")

    upsert_media_asset(
        ad_key=ad_natural_key,
        ad_lang=ad_lang,
        non_ad_key=non_ad_key,
        mp4_path=str(src_path),
        wav_path=str(wav_path),
        status="prepared",
    )

    return {
        "non_ad_key": non_ad_key,
        "downloaded": str(src_path),
        "wav": str(wav_path),
        "status": "prepared"
    }


@app.post("/fingerprint/enqueue")
async def fingerprint_enqueue(payload: EnqueueRequest) -> dict:
    return await _prepare_non_ad(payload.ad_natural_key, payload.ad_lang)


@app.post("/fingerprint/prepare-all")
async def fingerprint_prepare_all() -> dict:
    # Fetch weekly clips
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(JW_CATEGORY_URL)
        r.raise_for_status()
        data = r.json()
    media = (data or {}).get("category", {}).get("media", []) or []
    ad_lang = (data or {}).get("language", {}).get("languageCode", "E")

    queued = 0
    for item in media:
        ad_key = item.get("languageAgnosticNaturalKey") or item.get("naturalKey")
        if not ad_key:
            continue
        # Try to compute non-AD hint to see if we already have it indexed
        non_ad_hint = compute_non_ad_natural_key(ad_key) or ""
        asset = get_asset_by_non_ad(non_ad_hint) if non_ad_hint else None
        if asset and asset.status in ("prepared", "indexed", "downloading", "downloaded"):
            continue
        # queue as background task (fire-and-forget)
        asyncio.create_task(_prepare_non_ad(ad_key, ad_lang))
        queued += 1

    return {"queued": queued}


@app.post("/fingerprint/build")
async def fingerprint_build() -> dict:
    """Build fingerprint indexes for all prepared WAVs."""
    prepared = get_assets_by_status("prepared")
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    built = 0
    for asset in prepared:
        if not asset.wav_path:
            continue
        wav_path = Path(asset.wav_path)
        if not wav_path.exists():
            continue
        idx_path = INDEX_DIR / f"{asset.non_ad_key.replace('/', '_')}.fp"
        try:
            idx = fplib.index_reference(wav_path)
            fplib.save_index(idx, idx_path)
            upsert_media_asset(
                ad_key=asset.ad_key,
                ad_lang=asset.ad_lang,
                non_ad_key=asset.non_ad_key,
                mp4_path=asset.mp4_path,
                wav_path=asset.wav_path,
                status="indexed",
            )
            built += 1
        except Exception:
            # leave status as prepared on failure
            continue
    return {"indexed": built}


@app.get("/fingerprint/status")
async def fingerprint_status(non_ad_key: str = Query(...)) -> dict:
    asset = get_asset_by_non_ad(non_ad_key)
    if not asset:
        return {"status": "missing"}
    return {
        "ad_key": asset.ad_key,
        "ad_lang": asset.ad_lang,
        "non_ad_key": asset.non_ad_key,
        "mp4_path": asset.mp4_path,
        "wav_path": asset.wav_path,
        "status": asset.status,
    }
