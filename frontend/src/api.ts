import axios from 'axios'

const apiBase = (import.meta as any).env?.VITE_API_URL || (typeof window !== 'undefined' ? `${window.location.origin}` : 'http://127.0.0.1:8000')
const api = axios.create({ baseURL: apiBase })

export type Clip = { id: string; title: string; duration_ms?: number; fingerprint_status: string; language?: string }
export type MatchResult = { clip_id: string; t_offset_ms: number; confidence: number }
export type AssetSummary = { ad_key: string; ad_lang: string; non_ad_key: string; mp4_path?: string | null; wav_path?: string | null; status: string; updated_at?: string | null }
export type CustomMedia = { key: string; title?: string | null; file_path: string; file_size?: number | null; wav_path?: string | null; status: string; updated_at?: string | null }

export async function getWeeklyClips(): Promise<Clip[]> {
  const { data } = await api.get<Clip[]>('/clips/week')
  return data
}

export async function matchBlob(blob: Blob, clipId?: string, lang: string = 'E'): Promise<MatchResult> {
  const fd = new FormData()
  fd.append('audio', blob, 'sample.webm')
  const { data } = await api.post<MatchResult>('/match', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params: clipId ? { clip_id: clipId, lang } : {},
  })
  return data
}

export async function getAdUrl(clip_id: string, lang: string = 'E'): Promise<string> {
  const { data } = await api.get<{ clip_id: string; ad_url: string }>(`/ad-url`, { params: { clip_id, lang } })
  return data.ad_url
}

export async function getNonAdItem(adNaturalKey: string, adLang: string = 'E'): Promise<{ naturalKey: string; title?: string; duration?: number; files: any[] }> {
  const { data } = await api.get(`/nonad-item`, { params: { ad_natural_key: adNaturalKey, ad_lang: adLang } })
  return data
}

export async function enqueueFingerprint(adNaturalKey: string, adLang: string = 'E'): Promise<{ non_ad_key: string; downloaded: string; wav: string; status: string }> {
  const { data } = await api.post(`/fingerprint/enqueue`, { ad_natural_key: adNaturalKey, ad_lang: adLang })
  return data
}

export async function buildFingerprints(): Promise<{ indexed: number }> {
  const { data } = await api.post(`/fingerprint/build`)
  return data
}

export async function getFingerprintStatus(nonAdKey: string): Promise<{ status: string; ad_key?: string; ad_lang?: string; mp4_path?: string; wav_path?: string; non_ad_key?: string }> {
  const { data } = await api.get(`/fingerprint/status`, { params: { non_ad_key: nonAdKey } })
  return data
}

export async function prepareAll(): Promise<{ queued: number }> {
  const { data } = await api.post(`/fingerprint/prepare-all`)
  return data
}

export async function getAssets(): Promise<AssetSummary[]> {
  const { data } = await api.get<AssetSummary[]>(`/fingerprint/assets`)
  return data
}

export async function getAdminStatus(): Promise<{ last_maintenance_at?: number | null; interval_seconds: number; counts: Record<string, number>; total_assets: number }> {
  const { data } = await api.get(`/admin/status`)
  return data
}

export async function startMaintenance(): Promise<{ started: boolean }> {
  const { data } = await api.post(`/admin/maintenance`)
  return data
}

export async function listCustom(): Promise<CustomMedia[]> {
  const { data } = await api.get<CustomMedia[]>(`/admin/custom/list`)
  return data
}

export async function uploadCustom(files: File[], onProgress?: (percent: number) => void): Promise<{ keys: string[]; started: boolean }> {
  const fd = new FormData()
  for (const f of files) fd.append('files', f)
  const { data } = await api.post(`/admin/custom/upload`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (!onProgress) return
      if (e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
  })
  return data
}

export async function getCustomStatus(key: string): Promise<{ key?: string; status: string; file_path?: string; wav_path?: string; updated_at?: string | null }> {
  const { data } = await api.get(`/admin/custom/status`, { params: { key } })
  return data
}

export async function deleteCustom(key: string): Promise<{ deleted: boolean }> {
  const { data } = await api.delete(`/admin/custom`, { params: { key } })
  return data
}

export function getCustomFileUrl(key: string): string {
  return `${apiBase}/custom/file?key=${encodeURIComponent(key)}`
}

export async function listStorage(): Promise<{ rel_path: string; size: number }[]> {
  const { data } = await api.get(`/admin/storage/list`)
  return data
}

export async function deleteStorage(rel_path: string): Promise<{ deleted: boolean }> {
  const { data } = await api.delete(`/admin/storage`, { params: { rel_path } })
  return data
}
