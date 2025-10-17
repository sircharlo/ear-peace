<script setup lang="ts">
import { ref, onMounted } from 'vue'
import ClipSelect from './components/ClipSelect.vue'
import MicCapture from './components/MicCapture.vue'
import ClipDetails from './components/ClipDetails.vue'
import type { Clip, MatchResult } from './api'
import { getAdUrl } from './api'

const selected = ref<Clip | null>(null)
const match = ref<MatchResult | null>(null)
const playing = ref(false)
const error = ref<string | null>(null)
const audioEl = ref<HTMLAudioElement | null>(null)
const adUrl = ref<string | null>(null)
let driftTimer: number | null = null
let syncWallMs = 0
let syncMediaSec = 0
// Small intentional delay to account for perceptual/transport lead. Tune as needed.
const syncBiasMs = ref(75)
// Capture pipeline bias (encoder lookahead, resampling). Helps reduce large swings.
const captureBiasMs = 80
const biasAnnounce = ref<string | null>(null)

onMounted(() => {
  const saved = localStorage.getItem('syncBiasMs')
  if (saved) {
    const n = parseInt(saved, 10)
    if (!Number.isNaN(n)) syncBiasMs.value = n
  }
  // Background prepare/build disabled
})

type MatchWithTiming = { result: MatchResult; listenStartMs: number; matchedAtMs: number }

async function onMatched(payload: MatchWithTiming) {
  match.value = payload.result
  if (!selected.value) return
  try {
    // Use the selected language-agnostic key with its language code.
    if (!adUrl.value) {
      adUrl.value = await getAdUrl(selected.value.id, selected.value.language || 'E')
    }
    await nextTickPlay(payload)
  } catch (e: any) {
    error.value = e?.message || 'Failed to load AD audio'
  }
}

async function nextTickPlay(payload: MatchWithTiming) {
  await Promise.resolve()
  const el = audioEl.value
  if (!el || !match.value || !adUrl.value) return
  el.src = adUrl.value
  // Compute media time at the moment the match was found: (matchedAt - listenStart) + offset + biases
  const startMediaMs = Math.max(0, (payload.matchedAtMs - payload.listenStartMs) + match.value.t_offset_ms + syncBiasMs.value + captureBiasMs)
  console.log('[Sync] Inputs:', {
    listenStartMs: payload.listenStartMs,
    matchedAtMs: payload.matchedAtMs,
    t_offset_ms: match.value.t_offset_ms,
    syncBiasMs: syncBiasMs.value,
    captureBiasMs,
    computedStartMediaMs: startMediaMs,
  })
  // Wait for metadata so seeking is stable before play
  await new Promise<void>((resolve) => {
    if (el.readyState >= 1) return resolve()
    const onMeta = () => { el.removeEventListener('loadedmetadata', onMeta); resolve() }
    el.addEventListener('loadedmetadata', onMeta)
  })
  console.log('[Sync] loadedmetadata at', performance.now())
  // Pre-seek close to the expected position accounting for time since match
  const tPreSeek = performance.now()
  el.currentTime = startMediaMs / 1000 + Math.max(0, (tPreSeek - payload.matchedAtMs) / 1000)
  console.log('[Sync] Pre-seek:', {
    tPreSeek,
    currentTime: el.currentTime,
    sinceMatchSec: Math.max(0, (tPreSeek - payload.matchedAtMs) / 1000)
  })
  try {
    await el.play()
    playing.value = true
    // After playback actually starts, correct for buffering delay precisely
    await new Promise<void>((resolve) => {
      let done = false
      const applyCorrection = () => {
        if (done) return
        done = true
        const tNow = performance.now()
        const expected = startMediaMs / 1000 + Math.max(0, (tNow - payload.matchedAtMs) / 1000)
        el.currentTime = expected
        console.log('[Sync] Playing correction:', {
          tNow,
          expected,
          bufferingMs: tNow - tPreSeek,
          finalCurrentTime: el.currentTime,
        })
        // Initialize drift control baseline now
        syncWallMs = performance.now()
        syncMediaSec = el.currentTime
        el.playbackRate = 1.0
        startDriftControl()
        resolve()
      }
      // Prefer 'playing', fall back to a short timeout if event doesn't fire
      const onPlaying = () => { el.removeEventListener('playing', onPlaying); applyCorrection() }
      el.addEventListener('playing', onPlaying, { once: true })
      setTimeout(applyCorrection, 500)
    })
  } catch (e: any) {
    error.value = 'Autoplay blocked: press Play to start'
  }
}

function onSelect(c: Clip) {
  selected.value = c
  match.value = null
  adUrl.value = null
  error.value = null
  stopDriftControl()
  // Prefetch AD URL to reduce start latency
  getAdUrl(c.id, c.language || 'E').then(url => { adUrl.value = url }).catch(() => {})
}

function togglePlay() {
  const el = audioEl.value
  if (!el) return
  if (el.paused) { el.play(); playing.value = true; startDriftControl() } else { el.pause(); playing.value = false; stopDriftControl() }
}

function startDriftControl() {
  const el = audioEl.value
  if (!el) return
  if (driftTimer !== null) return
  syncWallMs = performance.now()
  syncMediaSec = el.currentTime
  driftTimer = window.setInterval(() => {
    const el = audioEl.value
    if (!el || el.paused) return
    const now = performance.now()
    const expected = syncMediaSec + (now - syncWallMs) / 1000
    const drift = el.currentTime - expected
    // If large drift, hard-correct
    if (Math.abs(drift) > 0.25) {
      el.currentTime = expected
      // reset baseline
      syncWallMs = performance.now()
      syncMediaSec = el.currentTime
      el.playbackRate = 1.0
      return
    }
    // Small drift: gently pull back with playbackRate
    const correction = Math.max(-0.02, Math.min(0.02, -drift * 0.5))
    el.playbackRate = 1.0 + correction
  }, 1000)
}

function stopDriftControl() {
  if (driftTimer !== null) {
    window.clearInterval(driftTimer)
    driftTimer = null
  }
  const el = audioEl.value
  if (el) el.playbackRate = 1.0
}

function adjustBias(deltaMs: number) {
  syncBiasMs.value += deltaMs
  localStorage.setItem('syncBiasMs', String(syncBiasMs.value))
  biasAnnounce.value = `Sync bias set to ${syncBiasMs.value} milliseconds`
  setTimeout(() => { if (biasAnnounce.value) biasAnnounce.value = '' }, 1000)
  const el = audioEl.value
  if (!el || el.paused) return
  // Apply immediately: shift playback position and reset drift baseline
  const deltaSec = deltaMs / 1000
  el.currentTime = Math.max(0, el.currentTime + deltaSec)
  syncWallMs = performance.now()
  syncMediaSec = el.currentTime
  el.playbackRate = 1.0
}
</script>

<template>
  <main>
    <h1 id="app-title">EarPeace</h1>
    <p id="app-desc">Select the clip once it starts playing in the Kingdom Hall, and we will sync the Audio Description version of the file so that you can listen along with your headphones.</p>

    <div role="region" aria-labelledby="select-title" v-if="!selected">
      <ClipSelect @select="onSelect" />
    </div>

    <div role="region" aria-labelledby="listen-title" v-else-if="!match">
      <ClipDetails :clip="selected!" />
      <MicCapture :clip-id="selected!.id" :lang="selected!.language || 'E'" @matched="onMatched" />
      <button @click="() => { selected = null as any }" aria-label="Change selection">Change selection</button>
    </div>

    <div role="region" aria-labelledby="play-title" v-else>
      <h2 id="play-title">Audio Description</h2>
      <div role="alert" v-if="error">{{ error }}</div>
      <audio ref="audioEl" controls aria-label="Audio Description Player"></audio>
      <div style="margin-top: .5rem;">
        <button @click="togglePlay">{{ playing ? 'Pause' : 'Play' }}</button>
        <button @click="() => { match = null as any; adUrl = null as any; playing = false }">Re-listen and resync</button>
        <span style="margin-left: .5rem;">Bias: {{ syncBiasMs }} ms</span>
        <button @click="() => adjustBias(-25)" aria-label="Decrease sync bias by 25 milliseconds" title="-25 ms">-25ms</button>
        <button @click="() => adjustBias(25)" aria-label="Increase sync bias by 25 milliseconds" title="+25 ms">+25ms</button>
      </div>
      <div role="status" aria-live="polite" style="height:1px; overflow:hidden;">{{ biasAnnounce }}</div>
      <p aria-live="polite">Matched clip: {{ match.clip_id }}, offset: {{ (match.t_offset_ms/1000).toFixed(2) }}s, confidence: {{ (match.confidence*100).toFixed(0) }}%</p>
    </div>
  </main>
</template>

<style scoped>
main { max-width: 720px; margin: 0 auto; padding: 1rem; }
button { font-size: 1.125rem; padding: 0.75rem 1rem; margin-right: .5rem; }
</style>
