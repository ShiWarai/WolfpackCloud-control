<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { accountApi, type AccountResponse } from '@/api/account'
import { networksApi, type Network } from '@/api/networks'
import DefaultLayout from '@/layouts/DefaultLayout.vue'

const loading = ref(true)
const error = ref<string | null>(null)
const account = ref<AccountResponse | null>(null)

const newNetworkName = ref('')
const newRosDomainId = ref<number>(0)
const creatingNetwork = ref(false)
const networkFormError = ref<string | null>(null)
const deletingNetworkId = ref<number | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    account.value = await accountApi.getAccount()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

async function createNetwork() {
  networkFormError.value = null
  const name = newNetworkName.value.trim()
  const rid = Number(newRosDomainId.value)
  if (!name) {
    networkFormError.value = 'Укажите имя сети'
    return
  }
  if (Number.isNaN(rid) || rid < 0 || rid > 101) {
    networkFormError.value = 'ROS_DOMAIN_ID должен быть от 0 до 101'
    return
  }
  creatingNetwork.value = true
  try {
    await networksApi.create({ name, ros_domain_id: rid })
    newNetworkName.value = ''
    newRosDomainId.value = 0
    await load()
  } catch (e: unknown) {
    const err = e as { response?: { status?: number; data?: { detail?: string } } }
    if (err.response?.status === 409) {
      networkFormError.value =
        err.response?.data?.detail || 'Сеть с таким ROS_DOMAIN_ID уже есть'
    } else {
      networkFormError.value =
        err.response?.data?.detail || 'Не удалось создать сеть'
    }
  } finally {
    creatingNetwork.value = false
  }
}

async function removeNetwork(n: Network) {
  const ok = window.confirm(
    `Удалить сеть «${n.name}» (DOMAIN ${n.ros_domain_id})? Роботы от неё отвяжутся.`,
  )
  if (!ok) return
  deletingNetworkId.value = n.id
  networkFormError.value = null
  try {
    await networksApi.delete(n.id)
    await load()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    networkFormError.value = err.response?.data?.detail || 'Не удалось удалить сеть'
  } finally {
    deletingNetworkId.value = null
  }
}

onMounted(load)
</script>

<template>
  <DefaultLayout>
    <div class="term-page-title-row">
      <h1 class="term-page-title">Аккаунт</h1>
    </div>

    <div v-if="error" class="term-alert term-alert-error">{{ error }}</div>
    <div v-if="loading" class="term-card">Загрузка...</div>

    <template v-else-if="account">
      <div class="term-card term-mb-1">
        <h2>Профиль</h2>
        <table class="term-table">
          <tbody>
            <tr>
              <td style="color: var(--text-dim); width: 35%;">Имя</td>
              <td>{{ account.user.name }}</td>
            </tr>
            <tr>
              <td style="color: var(--text-dim);">Email</td>
              <td>{{ account.user.email }}</td>
            </tr>
            <tr>
              <td style="color: var(--text-dim);">Роль</td>
              <td>{{ account.user.role }}</td>
            </tr>
          </tbody>
        </table>
        <p class="term-mt-1 term-text-dim term-fs-2xs">
          Смена пароля и MFA — в Keycloak Account Console.
        </p>
        <a
          :href="account.keycloak_account_url"
          target="_blank"
          rel="noopener noreferrer"
          class="term-btn term-btn-primary term-mt-1"
        >
          Открыть Keycloak Account
        </a>
      </div>

      <div class="term-card">
        <h2>Сети (ROS_DOMAIN_ID)</h2>
        <p class="term-text-dim term-fs-2xs term-mb-1">
          Каждая сеть — один DOMAIN_ID для DDS/Zenoh; робота привязываете на странице робота.
          Логи rosout фильтруются по этой привязке.
        </p>

        <div v-if="networkFormError" class="term-alert term-alert-error term-mb-1">
          {{ networkFormError }}
        </div>

        <form class="term-form term-mb-1" @submit.prevent="createNetwork">
          <div class="term-field" style="flex: 1; min-width: 8rem;">
            <label for="netName">Имя сети</label>
            <input
              id="netName"
              v-model="newNetworkName"
              type="text"
              class="term-input"
              maxlength="255"
              autocomplete="off"
              placeholder="Напр. Lab floor A"
            />
          </div>
          <div class="term-field" style="width: 8rem;">
            <label for="rosDom">DOMAIN_ID</label>
            <input
              id="rosDom"
              v-model.number="newRosDomainId"
              type="number"
              min="0"
              max="101"
              class="term-input"
            />
          </div>
          <div class="term-field" style="align-self: flex-end;">
            <button
              type="submit"
              class="term-btn term-btn-primary"
              :disabled="creatingNetwork"
            >
              {{ creatingNetwork ? 'Создание…' : 'Создать' }}
            </button>
          </div>
        </form>

        <p v-if="!account.networks.length" class="term-text-dim">
          Пока нет сетей — добавьте через форму выше.
        </p>
        <table v-else class="term-table">
          <thead>
            <tr>
              <th style="color: var(--text-dim);">ID</th>
              <th style="color: var(--text-dim);">Имя</th>
              <th style="color: var(--text-dim);">ROS_DOMAIN_ID</th>
              <th style="color: var(--text-dim);">Роботов</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="n in account.networks" :key="n.id">
              <td>{{ n.id }}</td>
              <td>{{ n.name }}</td>
              <td>{{ n.ros_domain_id }}</td>
              <td>{{ n.robot_count ?? 0 }}</td>
              <td style="text-align: right;">
                <button
                  type="button"
                  class="term-btn term-btn-delete term-fs-2xs"
                  :disabled="deletingNetworkId !== null"
                  @click="removeNetwork(n)"
                >
                  {{ deletingNetworkId === n.id ? '…' : 'Удалить' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </DefaultLayout>
</template>
