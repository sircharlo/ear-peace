<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import type { Clip } from '../api'
import { getNonAdItem, enqueueFingerprint, buildFingerprints, getFingerprintStatus } from '../api'

const props = defineProps<{ clip: Clip }>()
const loading = ref(false)
const error = ref<string | null>(null)
const nonAdKey = ref<string | null>(null)
const nonAdUrl = ref<string | null>(null)
const prepStatus = ref<string | null>(null)
const prepping = ref(false)
const fpStatus = ref<string>('unknown')
const building = ref(false)

function statusColor(status: string): string {
  if (status === 'indexed') return '#16a34a' // green
  if (status === 'prepared' || status === 'downloading' || status === 'downloaded') return '#f59e0b' // amber
  return '#9ca3af' // gray
}

function pickUrl(files: any[]): string | null {
  if (!files || !Array.isArray(files)) return null
  const byLabel: Record<string, any> = {}
  for (const f of files) byLabel[f.label || ''] = f
  const order = ['240p', '360p', '480p', '720p', '144p']
  for (const l of order) if (byLabel[l]?.progressiveDownloadURL) return byLabel[l].progressiveDownloadURL
  const first = files.find((f: any) => f.progressiveDownloadURL)
  return first?.progressiveDownloadURL || null
}

async function load() {
  loading.value = true
  error.value = null
  nonAdKey.value = null
  nonAdUrl.value = null
  prepStatus.value = null
  fpStatus.value = 'unknown'
  try {
    const data = await getNonAdItem(props.clip.id, props.clip.language || 'E')
    nonAdKey.value = data.naturalKey
    nonAdUrl.value = pickUrl(data.files)
    await refreshStatus()
  } catch (e: any) {
    error.value = e?.message || 'Failed to load non-AD mapping'
  } finally {
    loading.value = false
  }
}

async function prepare() {
  if (!props.clip?.id) return
  prepping.value = true
  prepStatus.value = 'Preparing media (download + wav)…'
  error.value = null
  try {
    const res = await enqueueFingerprint(props.clip.id, props.clip.language || 'E')
    prepStatus.value = `Prepared: ${res.wav}`
    await refreshStatus()
  } catch (e: any) {
    error.value = e?.message || 'Preparation failed (ffmpeg missing?)'
  } finally {
    prepping.value = false
  }
}

async function refreshStatus() {
  if (!nonAdKey.value) return
  try {
    const s = await getFingerprintStatus(nonAdKey.value)
    fpStatus.value = s.status
  } catch {
    fpStatus.value = 'unknown'
  }
}

async function buildFp() {
  building.value = true
  try {
    await buildFingerprints()
    await refreshStatus()
  } catch (e: any) {
    error.value = e?.message || 'Build failed'
  } finally {
    building.value = false
  }
}

onMounted(load)
watch(() => props.clip.id, load)
</script>

<template>
  <section aria-labelledby="details-title">
    <h2 id="details-title">Clip details</h2>
    <div role="status" aria-live="polite" v-if="loading">Loading mapping…</div>
    <div role="alert" v-if="error">{{ error }}</div>
    <dl v-if="!loading && !error">
      <dt>AD naturalKey</dt>
      <dd><code>{{ clip.id }}</code></dd>
      <dt>Non-AD naturalKey</dt>
      <dd><code>{{ nonAdKey || 'computing…' }}</code></dd>
      <dt>Sample Non-AD URL</dt>
      <dd>
        <a v-if="nonAdUrl" :href="nonAdUrl" target="_blank" rel="noopener">Open non-AD video</a>
        <span v-else>Pending</span>
      </dd>
      <dt>Preparation</dt>
      <dd>
        <button @click="prepare" :disabled="prepping">{{ prepping ? 'Preparing…' : 'Prepare for fingerprinting' }}</button>
        <div role="status" aria-live="polite" v-if="prepStatus">{{ prepStatus }}</div>
      </dd>
      <dt>Fingerprint status</dt>
      <dd>
        <span style="display:inline-flex; align-items:center; gap:.5rem;">
          <span :style="{ width: '10px', height: '10px', borderRadius: '9999px', backgroundColor: statusColor(fpStatus) }"></span>
          <span>{{ fpStatus }}</span>
          <span v-if="fpStatus==='indexed'" style="padding:2px 6px; border:1px solid #16a34a; color:#16a34a; border-radius:9999px; font-size:.85em;">Indexed</span>
        </span>
        <button @click="buildFp" :disabled="building || fpStatus==='indexed'" style="margin-left:.5rem;">{{ building ? 'Building…' : 'Build fingerprints' }}</button>
        <button @click="refreshStatus" style="margin-left:.5rem;">Refresh</button>
      </dd>
    </dl>
  </section>
</template>

<style scoped>
dt { font-weight: 600; margin-top: .5rem; }
dd { margin-left: 0; margin-bottom: .25rem; }
</style>
