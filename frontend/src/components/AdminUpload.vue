<script setup lang="ts">
import { ref } from 'vue'
import { uploadCustom, getCustomStatus } from '../api'

const files = ref<FileList | null>(null)
const uploading = ref(false)
const progress = ref(0)
const statusMsg = ref<string>('')
const lastKeys = ref<string[]>([])

async function onUpload() {
  if (!files.value || files.value.length === 0) return
  uploading.value = true
  progress.value = 0
  statusMsg.value = ''
  try {
    const fs: File[] = Array.from(files.value)
    const res = await uploadCustom(fs, (p) => { progress.value = p })
    lastKeys.value = res.keys
    statusMsg.value = 'Upload complete. Preparing and indexing…'
    // Poll statuses briefly
    const start = Date.now()
    const timeoutMs = 30000
    while (Date.now() - start < timeoutMs) {
      const statuses = await Promise.all(res.keys.map(k => getCustomStatus(k)))
      if (statuses.every(s => s.status === 'indexed')) { statusMsg.value = 'Indexed.'; break }
      if (statuses.some(s => s.status === 'prepared' || s.status === 'downloaded')) {
        statusMsg.value = 'Transcoding / indexing…'
      }
      await new Promise(r => setTimeout(r, 1500))
    }
  } catch (e: any) {
    statusMsg.value = e?.message || 'Upload failed'
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="box">
    <h3 class="title is-5">Upload Custom Media</h3>
    <div class="field">
      <div class="file has-name is-fullwidth">
        <label class="file-label">
          <input class="file-input" type="file" multiple accept="audio/*,video/*" @change="(e:any)=>{files = e.target.files}" />
          <span class="file-cta">
            <span class="file-icon"><i class="fas fa-upload"></i></span>
            <span class="file-label">Choose files…</span>
          </span>
          <span class="file-name">{{ files?.length ? files.length + ' file(s) selected' : 'No files selected' }}</span>
        </label>
      </div>
    </div>
    <div class="field is-grouped">
      <div class="control">
        <button class="button is-primary" :class="{ 'is-loading': uploading }" :disabled="!files || !files.length" @click="onUpload">Upload</button>
      </div>
    </div>
    <progress class="progress is-link" :value="progress" max="100" v-if="uploading || progress>0">{{ progress }}%</progress>
    <p v-if="statusMsg">{{ statusMsg }}</p>
    <div v-if="lastKeys.length">
      <p><strong>Uploaded keys:</strong> {{ lastKeys.join(', ') }}</p>
    </div>
  </div>
</template>

<style scoped>
</style>
