<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getAssets, getAdminStatus, startMaintenance, type AssetSummary } from '../api'
import AdminUpload from './AdminUpload.vue'
import AdminManage from './AdminManage.vue'

const tab = ref<'overview' | 'upload' | 'manage'>('overview')
const loading = ref(false)
const error = ref<string | null>(null)
const assets = ref<AssetSummary[]>([])
const status = ref<{ last_maintenance_at?: number | null; interval_seconds: number; counts: Record<string, number>; total_assets: number } | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const [a, s] = await Promise.all([
      getAssets(),
      getAdminStatus(),
    ])
    assets.value = a
    status.value = s
  } catch (e: any) {
    error.value = e?.message || 'Failed to load admin status'
  } finally {
    loading.value = false
  }
}

async function triggerMaintenance() {
  loading.value = true
  error.value = null
  try {
    await startMaintenance()
    await load()
  } catch (e: any) {
    error.value = e?.message || 'Failed to start maintenance'
  } finally {
    loading.value = false
  }
}

onMounted(() => { load() })
</script>

<template>
  <section class="section">
    <div class="container">
      <h1 class="title">Admin</h1>
      <p class="subtitle">Maintenance, custom uploads, and storage management</p>

      <div class="tabs is-boxed">
        <ul>
          <li :class="{ 'is-active': tab==='overview' }"><a @click.prevent="tab='overview'">Overview</a></li>
          <li :class="{ 'is-active': tab==='upload' }"><a @click.prevent="tab='upload'">Upload</a></li>
          <li :class="{ 'is-active': tab==='manage' }"><a @click.prevent="tab='manage'">Manage</a></li>
        </ul>
      </div>

      <div v-if="error" class="notification is-danger">{{ error }}</div>

      <template v-if="tab==='overview'">
        <div class="buttons">
          <button class="button is-link" :class="{ 'is-loading': loading }" @click="load">Refresh</button>
          <button class="button is-primary" :disabled="loading" @click="triggerMaintenance">Run maintenance</button>
        </div>

        <div class="box" v-if="status">
          <h2 class="title is-5">Summary</h2>
          <div class="columns is-multiline">
            <div class="column is-one-quarter" v-for="(count, key) in status!.counts" :key="key">
              <div class="notification is-light">
                <strong>{{ key }}</strong>
                <div>{{ count }}</div>
              </div>
            </div>
          </div>
          <p><strong>Total:</strong> {{ status!.total_assets }}</p>
          <p><strong>Last maintenance:</strong> {{ status!.last_maintenance_at ? new Date(status!.last_maintenance_at * 1000).toLocaleString() : 'never' }}</p>
          <p><strong>Interval (s):</strong> {{ status!.interval_seconds }}</p>
        </div>

        <div class="box">
          <h2 class="title is-5">API Assets</h2>
          <div class="table-container">
            <table class="table is-striped is-fullwidth is-hoverable">
              <thead>
                <tr>
                  <th>AD Key</th>
                  <th>Lang</th>
                  <th>Non-AD Key</th>
                  <th>Status</th>
                  <th>Updated</th>
                  <th>MP4</th>
                  <th>WAV</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="a in assets" :key="a.non_ad_key">
                  <td>{{ a.ad_key }}</td>
                  <td>{{ a.ad_lang }}</td>
                  <td><code>{{ a.non_ad_key }}</code></td>
                  <td><span class="tag" :class="{ 'is-info': a.status==='prepared', 'is-success': a.status==='indexed', 'is-warning': a.status==='downloading' || a.status==='downloaded' }">{{ a.status }}</span></td>
                  <td>{{ a.updated_at ? new Date(a.updated_at).toLocaleString() : '' }}</td>
                  <td>{{ a.mp4_path ? 'yes' : '' }}</td>
                  <td>{{ a.wav_path ? 'yes' : '' }}</td>
                </tr>
                <tr v-if="assets.length === 0">
                  <td colspan="7" class="has-text-centered has-text-grey">No assets yet</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>

      <template v-else-if="tab==='upload'">
        <AdminUpload />
      </template>

      <template v-else>
        <AdminManage />
      </template>
    </div>
  </section>
</template>

<style scoped>
.table-container { max-height: 60vh; overflow:auto; }
</style>
