<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listCustom, type CustomMedia } from '../api'

const items = ref<CustomMedia[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const emit = defineEmits<{ (e: 'select', key: string): void }>()

async function load() {
  loading.value = true
  error.value = null
  try {
    items.value = await listCustom()
  } catch (e: any) {
    error.value = e?.message || 'Failed to load custom media'
  } finally {
    loading.value = false
  }
}

function choose(key: string) {
  emit('select', key)
}

onMounted(load)
</script>

<template>
  <section aria-labelledby="custom-list-title">
    <h1 id="custom-list-title">Select custom media</h1>
    <div role="status" aria-live="polite" v-if="loading">Loading…</div>
    <div role="alert" v-if="error">{{ error }}</div>
    <ul v-if="items.length" style="list-style:none; padding:0;">
      <li v-for="m in items" :key="m.key" style="margin-bottom: .5rem; display:flex; align-items:center; gap:.5rem;">
        <button @click="choose(m.key)">{{ m.title || m.key }}</button>
        <span class="tag" :class="{ 'is-warning': m.status==='prepared' || m.status==='downloaded', 'is-success': m.status==='indexed' }">{{ m.status }}</span>
        <span class="has-text-grey" v-if="m.file_size">{{ (m.file_size/1024/1024).toFixed(2) }} MB</span>
      </li>
    </ul>
    <p v-else-if="!loading" class="has-text-grey">No custom media uploaded yet.</p>
  </section>
</template>

<style scoped>
button { font-size: 1.125rem; padding: 0.75rem 1rem; }
</style>
