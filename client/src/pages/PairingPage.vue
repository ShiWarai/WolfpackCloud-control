<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { pairingApi } from '@/api'
import { useRobotsStore } from '@/stores'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import type { PairCodeInfo } from '@/types'

const router = useRouter()
const robotsStore = useRobotsStore()

const code = ref('')
const robotName = ref('')
const codeInfo = ref<PairCodeInfo | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const success = ref(false)

const codeInputs = ref<string[]>(['', '', '', '', '', '', '', ''])

function handleCodeInput(index: number, event: Event) {
  const input = event.target as HTMLInputElement
  const value = input.value.toUpperCase().replace(/[^A-Z0-9]/g, '')
  
  codeInputs.value[index] = value.slice(0, 1)
  
  if (value && index < 7) {
    const nextInput = document.getElementById(`code-${index + 1}`)
    nextInput?.focus()
  }
  
  code.value = codeInputs.value.join('')
  
  if (code.value.length === 8) {
    fetchCodeInfo()
  }
}

function handleKeyDown(index: number, event: KeyboardEvent) {
  if (event.key === 'Backspace' && !codeInputs.value[index] && index > 0) {
    const prevInput = document.getElementById(`code-${index - 1}`)
    prevInput?.focus()
  }
}

function handlePaste(event: ClipboardEvent) {
  event.preventDefault()
  const pastedText = event.clipboardData?.getData('text').toUpperCase().replace(/[^A-Z0-9]/g, '') || ''
  
  for (let i = 0; i < 8; i++) {
    codeInputs.value[i] = pastedText[i] || ''
  }
  
  code.value = codeInputs.value.join('')
  
  if (code.value.length === 8) {
    fetchCodeInfo()
  }
}

async function fetchCodeInfo() {
  if (code.value.length !== 8) return
  
  loading.value = true
  error.value = null
  codeInfo.value = null
  
  try {
    codeInfo.value = await pairingApi.getCodeInfo(code.value)
    
    if (codeInfo.value.robot) {
      robotName.value = codeInfo.value.robot.name
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Код не найден'
  } finally {
    loading.value = false
  }
}

async function confirmPairing() {
  loading.value = true
  error.value = null
  
  try {
    await pairingApi.confirm(code.value, robotName.value || undefined)
    success.value = true
    
    await robotsStore.fetchRobots()
    
    setTimeout(() => {
      router.push('/robots')
    }, 2000)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Ошибка подтверждения'
  } finally {
    loading.value = false
  }
}

function reset() {
  code.value = ''
  codeInputs.value = ['', '', '', '', '', '', '', '']
  robotName.value = ''
  codeInfo.value = null
  error.value = null
  success.value = false
  
  const firstInput = document.getElementById('code-0')
  firstInput?.focus()
}
</script>

<template>
  <DefaultLayout>
    <div style="max-width: 30rem; margin: 0 auto;">
      <div class="term-page-title-row">
        <h1 class="term-page-title">Привязка робота</h1>
      </div>
      <p class="term-text-dim term-mb-1">
        Введите 8-значный код с экрана робота
      </p>

      <div v-if="success" class="term-card term-alert-success" style="text-align: center; border-color: rgba(34, 197, 94, 0.5);">
        <p style="font-size: 1.25rem; margin: 0.5rem 0;">Робот успешно привязан!</p>
        <p class="term-text-dim">Перенаправление...</p>
      </div>

      <div v-else class="term-card">
        <div v-if="error" class="term-alert term-alert-error">
          {{ error }}
        </div>

        <div class="term-form">
          <div class="term-field">
            <label style="text-align: center; display: block;">Код привязки</label>
            <div
              style="display: flex; justify-content: center; gap: 0.375rem; margin-top: 0.5rem;"
              @paste="handlePaste"
            >
              <input
                v-for="(_, index) in codeInputs"
                :id="`code-${index}`"
                :key="index"
                v-model="codeInputs[index]"
                type="text"
                maxlength="1"
                class="term-code-input"
                @input="handleCodeInput(index, $event)"
                @keydown="handleKeyDown(index, $event)"
              />
            </div>
          </div>

          <div v-if="loading" style="text-align: center; padding: 1rem 0;">
            <p class="term-text-dim">Проверка кода...</p>
          </div>

          <div v-else-if="codeInfo">
            <div class="term-card" style="background: var(--bg); margin-top: 1rem;">
              <h2 style="margin-bottom: 0.5rem;">Информация о роботе</h2>
              <table class="term-table" style="font-size: var(--fs-2xs);">
                <tbody>
                  <tr>
                    <td style="color: var(--text-dim); width: 40%;">Hostname</td>
                    <td>{{ codeInfo.robot?.hostname }}</td>
                  </tr>
                  <tr>
                    <td style="color: var(--text-dim);">IP-адрес</td>
                    <td>{{ codeInfo.robot?.ip_address || '—' }}</td>
                  </tr>
                  <tr>
                    <td style="color: var(--text-dim);">Архитектура</td>
                    <td>{{ codeInfo.robot?.architecture }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="codeInfo.status === 'pending'" class="term-field" style="margin-top: 1rem;">
              <label for="robotName">Имя робота (опционально)</label>
              <input
                id="robotName"
                v-model="robotName"
                type="text"
                class="term-input"
                style="max-width: none;"
                placeholder="Понятное имя для робота"
              />
            </div>

            <div v-if="codeInfo.status === 'pending'" style="display: flex; gap: 0.5rem; margin-top: 1rem;">
              <button type="button" @click="reset" class="term-btn" style="flex: 1;">
                Отмена
              </button>
              <button
                type="button"
                @click="confirmPairing"
                :disabled="loading"
                class="term-btn term-btn-primary"
                style="flex: 1;"
              >
                Подтвердить
              </button>
            </div>

            <div v-else-if="codeInfo.status === 'confirmed'" class="term-alert" style="border-color: #fbbf24; color: #fbbf24; margin-top: 1rem; text-align: center;">
              Этот код уже был использован
            </div>

            <div v-else-if="codeInfo.status === 'expired'" class="term-alert term-alert-error" style="margin-top: 1rem; text-align: center;">
              Срок действия кода истёк
            </div>
          </div>
        </div>
      </div>

      <div class="term-card term-mt-1">
        <h2>Как получить код?</h2>
        <ol style="padding-left: 1.25rem; margin: 0; color: var(--text-dim); font-size: var(--fs-sm);">
          <li>Установите агент на робота</li>
          <li>Запустите команду установки</li>
          <li>Код появится в терминале</li>
          <li>Введите код здесь в течение 15 минут</li>
        </ol>
      </div>
    </div>
  </DefaultLayout>
</template>

<style scoped>
.term-code-input {
  width: 2.25rem;
  height: 2.75rem;
  text-align: center;
  font-size: 1.25rem;
  font-family: var(--font);
  font-weight: 600;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--accent);
  text-transform: uppercase;
  outline: none;
}

.term-code-input:focus {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 2px rgba(230, 126, 34, 0.2);
}
</style>
