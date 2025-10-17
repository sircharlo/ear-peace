from __future__ import annotations

import math
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
from scipy.io import wavfile
from scipy.signal import stft

# Simple landmark-style fingerprinting (lightweight placeholder)
# - Create STFT
# - For each time frame, pick top-K frequency bins
# - Create hashes by pairing peaks within a local time window

@dataclass
class FPIndex:
    sr: int
    hop: int
    hash_to_times: Dict[int, List[int]]  # hash -> list of frame indices

# Tunable fingerprint parameters
N_FFT = 2048
HOP = 512
TOP_K = 5
FAN_OUT = 5
MIN_DT = 1
MAX_DT = 50


def read_mono_wav(path: Path) -> Tuple[int, np.ndarray]:
    sr, y = wavfile.read(str(path))
    y = y.astype(np.float32)
    if y.ndim == 2:
        y = y.mean(axis=1)
    # normalize
    if np.max(np.abs(y)) > 0:
        y = y / np.max(np.abs(y))
    return sr, y


def compute_peaks(y: np.ndarray, sr: int, n_fft: int = N_FFT, hop: int = HOP, top_k: int = TOP_K) -> Tuple[np.ndarray, int]:
    # STFT magnitude
    _, _, Z = stft(y, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, nfft=n_fft, boundary=None)
    S = np.abs(Z)  # shape: (freq_bins, frames)
    # Log magnitude for dynamic range compression
    S_log = np.log1p(S)
    # For each frame, pick top_k peaks (frequency bin indices)
    peaks = np.argpartition(-S_log, kth=min(top_k, S_log.shape[0]-1), axis=0)[:top_k, :]
    # peaks shape (top_k, frames)
    return peaks.astype(np.int32), hop


def build_hashes(peaks: np.ndarray, fan_out: int = FAN_OUT, min_dt: int = MIN_DT, max_dt: int = MAX_DT) -> List[Tuple[int, int]]:
    # peaks: (top_k, frames) of freq bins
    top_k, frames = peaks.shape
    hashes: List[Tuple[int, int]] = []
    for t in range(frames):
        anchors = peaks[:, t]
        for k in range(top_k):
            f1 = int(anchors[k])
            # pair with peaks in future frames within [min_dt, max_dt]
            for dt in range(min_dt, min(max_dt, frames - t)):
                tgt = peaks[:, t + dt]
                for m in range(min(fan_out, top_k)):
                    f2 = int(tgt[m])
                    # pack (f1, f2, dt) into a 32-bit-ish hash
                    h = ((f1 & 0x3FF) << 20) | ((f2 & 0x3FF) << 10) | (dt & 0x3FF)
                    hashes.append((h, t))
    return hashes


def index_reference(wav_path: Path) -> FPIndex:
    sr, y = read_mono_wav(wav_path)
    peaks, hop = compute_peaks(y, sr)
    hashes = build_hashes(peaks)
    table: Dict[int, List[int]] = {}
    for h, t in hashes:
        table.setdefault(h, []).append(t)
    return FPIndex(sr=sr, hop=hop, hash_to_times=table)


def save_index(idx: FPIndex, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'wb') as f:
        pickle.dump(idx, f, protocol=pickle.HIGHEST_PROTOCOL)


def load_index(path: Path) -> FPIndex:
    with open(path, 'rb') as f:
        return pickle.load(f)


def match_query(query_wav: Path, indices: Dict[str, Path]) -> Tuple[str | None, float, float]:
    """
    Returns (best_key, offset_seconds, confidence)
    confidence is a simple normalized score in [0,1].
    """
    # Build query hashes
    sr, y = read_mono_wav(query_wav)
    peaks, hop = compute_peaks(y, sr)
    q_hashes = build_hashes(peaks)
    if not q_hashes:
        return None, 0.0, 0.0

    # For each reference, accumulate offset votes
    best_key = None
    best_votes = 0
    best_offset_frames = 0

    for key, idx_path in indices.items():
        try:
            idx = load_index(idx_path)
        except Exception:
            continue
        # histogram of offsets: (ref_t - query_t)
        offsets: Dict[int, int] = {}
        hits = 0
        for h, tq in q_hashes:
            tlist = idx.hash_to_times.get(h)
            if not tlist:
                continue
            for tr in tlist:
                off = tr - tq
                offsets[off] = offsets.get(off, 0) + 1
                hits += 1
        if not offsets:
            continue
        # take the most common offset
        off_frames, votes = max(offsets.items(), key=lambda kv: kv[1])
        if votes > best_votes:
            best_votes = votes
            best_offset_frames = off_frames
            best_key = key

    if best_key is None:
        return None, 0.0, 0.0

    # Convert frames to seconds using query hop (approx)
    offset_seconds = (best_offset_frames * hop) / float(sr)
    # confidence: votes normalized by total q_hashes (clipped)
    confidence = min(1.0, best_votes / max(1, len(q_hashes)))
    return best_key, offset_seconds, confidence
