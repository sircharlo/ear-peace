<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listStorage, deleteStorage } from '../api'

const files = ref<{ rel_path: string; size: number }[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    files.value = await listStorage()
  } catch (e: any) {
    error.value = e?.message || 'Failed to list storage'
  } finally {
    loading.value = false
  }
}

async function remove(rel_path: string) {
  if (!confirm(`Delete ${rel_path}? This will also clean DB/index entries if applicable.`)) return
  try {
    await deleteStorage(rel_path)
    await load()
  } catch (e: any) {
    alert(e?.message || 'Failed to delete')
  }
}

onMounted(load)
</script>

<template>
  <div class="box">
    <h3 class="title is-5">Manage Storage</h3>
    <div v-if="error" class="notification is-danger">{{ error }}</div>
    <button class="button is-link" :class="{ 'is-loading': loading }" @click="load">Refresh</button>
    <div class="table-container" style="margin-top:1rem;">
      <table class="table is-fullwidth is-striped is-hoverable">
        <thead>
          <tr>
            <th>Path</th>
            <th>Size</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in files" :key="f.rel_path">
            <td><code>{{ f.rel_path }}</code></td>
            <td>{{ (f.size/1024/1024).toFixed(2) }} MB</td>
            <td><button class="button is-small is-danger" @click="remove(f.rel_path)">Delete</button></td>
          </tr>
          <tr v-if="!files.length && !loading">
            <td colspan="3" class="has-text-centered has-text-grey">No files</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.table-container { max-height: 60vh; overflow:auto; }
</style>
