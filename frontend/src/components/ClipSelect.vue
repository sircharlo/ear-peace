<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { getWeeklyClips, type Clip, getNonAdItem, getFingerprintStatus } from '../api'

type UiClip = { clip: Clip; nonAdKey?: string; status: string }
const clips = ref<UiClip[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
let refreshTimer: number | null = null

const emit = defineEmits<{ (e: 'select', clip: Clip): void }>()

function statusColor(status: string): string {
  if (status === 'indexed') return '#16a34a'
  if (status === 'prepared' || status === 'downloading' || status === 'downloaded') return '#f59e0b'
  return '#9ca3af'
}

async function loadClips() {
  loading.value = true
  try {
    const base = await getWeeklyClips()
    clips.value = base.map(c => ({ clip: c, status: 'pending' }))
    await refreshStatuses()
    startPeriodicRefresh()
  } catch (e: any) {
    error.value = e?.message || 'Failed to load clips'
  } finally {
    loading.value = false
  }
}

async function refreshStatuses() {
  await Promise.all(clips.value.map(async (uc) => {
    try {
      if (!uc.nonAdKey) {
        const nonad = await getNonAdItem(uc.clip.id, uc.clip.language || 'E')
        uc.nonAdKey = nonad.naturalKey
      }
      const s = await getFingerprintStatus(uc.nonAdKey!)
      uc.status = s.status === 'indexed' ? 'indexed' : (s.status || 'pending')
    } catch {
      uc.status = 'pending'
    }
  }))
}

function startPeriodicRefresh() {
  stopPeriodicRefresh()
  const tick = async () => {
    if (clips.value.every(c => c.status === 'indexed')) { stopPeriodicRefresh(); return }
    await refreshStatuses()
  }
  refreshTimer = window.setInterval(tick, 15000)
}

function stopPeriodicRefresh() {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
}

onMounted(loadClips)
onUnmounted(stopPeriodicRefresh)

function choose(c: UiClip) {
  emit('select', c.clip)
}
</script>

<template>
  <section aria-labelledby="clip-list-title">
    <h1 id="clip-list-title">Select the desired file</h1>
    <div role="status" aria-live="polite" v-if="loading">Loading clips…</div>
    <div role="alert" v-if="error">{{ error }}</div>
    <ul v-if="clips.length" style="list-style: none; padding: 0;">
      <li v-for="uc in clips" :key="uc.clip.id" style="margin-bottom: 0.5rem; display:flex; align-items:center; gap:.5rem;">
        <button :aria-label="'Select ' + uc.clip.title" @click="choose(uc)">
          {{ uc.clip.title }}
        </button>
        <span style="display:inline-flex; align-items:center; gap:.4rem; font-size:.9rem;">
          <span :style="{ width: '10px', height: '10px', borderRadius: '9999px', backgroundColor: statusColor(uc.status) }"></span>
          <span>{{ uc.status === 'indexed' ? 'Indexed' : 'Pending' }}</span>
        </span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
button { font-size: 1.125rem; padding: 0.75rem 1rem; }
</style>
