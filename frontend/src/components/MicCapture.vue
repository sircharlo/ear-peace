<script setup lang="ts">
import { ref } from 'vue'
import { matchBlob, type MatchResult } from '../api'

const recording = ref(false)
const progressText = ref('')
const error = ref<string | null>(null)
let mediaRecorder: MediaRecorder | null = null
let chunks: Blob[] = []
let listenStartMs = 0

type MatchWithTiming = { result: MatchResult; listenStartMs: number; matchedAtMs: number }
const emit = defineEmits<{ (e: 'matched', payload: MatchWithTiming): void }>()
const props = defineProps<{ clipId?: string; lang?: string }>()

async function start() {
  error.value = null
  progressText.value = 'Requesting microphone permission…'
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    chunks = []
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })
    mediaRecorder.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data) }
    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: 'audio/webm' })
      progressText.value = 'Analyzing…'
      try {
        const result = await matchBlob(blob, props.clipId, props.lang || 'E')
        const matchedAtMs = performance.now()
        emit('matched', { result, listenStartMs, matchedAtMs })
      } catch (e: any) {
        error.value = e?.message || 'Matching failed'
      } finally {
        progressText.value = ''
      }
    }
    recording.value = true
    progressText.value = 'Listening for up to 30 seconds…'
    listenStartMs = performance.now()
    mediaRecorder.start()
    // Stop after 30 seconds automatically
    setTimeout(() => { if (mediaRecorder && recording.value) stop() }, 30000)
  } catch (e: any) {
    error.value = e?.message || 'Microphone access failed'
    recording.value = false
    progressText.value = ''
  }
}

function stop() {
  if (mediaRecorder && recording.value) {
    recording.value = false
    mediaRecorder.stop()
  }
}
</script>

<template>
  <section aria-labelledby="listen-title">
    <h2 id="listen-title">Listen for the clip</h2>
    <div role="status" aria-live="polite">{{ progressText }}</div>
    <div role="alert" v-if="error">{{ error }}</div>
    <div style="display:flex; gap: .5rem;">
      <button @click="start" :disabled="recording" aria-label="Start listening">Start</button>
      <button @click="stop" :disabled="!recording" aria-label="Stop listening">Stop</button>
    </div>
  </section>
</template>

<style scoped>
button { font-size: 1.125rem; padding: 0.75rem 1rem; }
</style>
