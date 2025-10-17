<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getWeeklyClips, type Clip } from '../api'

type UiClip = { clip: Clip }
const clips = ref<UiClip[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const emit = defineEmits<{ (e: 'select', clip: Clip): void }>()

async function loadClips() {
  loading.value = true
  try {
    const base = await getWeeklyClips()
    clips.value = base.map(c => ({ clip: c }))
  } catch (e: any) {
    error.value = e?.message || 'Failed to load clips'
  } finally {
    loading.value = false
  }
}

onMounted(loadClips)

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
        <!-- Status details are loaded on demand in ClipDetails.vue to avoid heavy initial fetches. -->
      </li>
    </ul>
  </section>
</template>

<style scoped>
button { font-size: 1.125rem; padding: 0.75rem 1rem; }
</style>
