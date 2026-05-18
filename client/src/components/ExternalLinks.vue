<script setup lang="ts">
defineProps<{
  robotId?: number
}>()

const keycloakUrl = import.meta.env.VITE_KEYCLOAK_URL || ''
</script>

<template>
  <div class="term-card">
    <h2>Внешние сервисы</h2>
    <p class="term-text-dim term-fs-2xs">
      В WolfpackCloud Control мониторинг Influx/Grafana не подключён. Авторизация — Keycloak.
    </p>
    <div v-if="keycloakUrl" class="term-mt-1">
      <a
        :href="keycloakUrl"
        target="_blank"
        rel="noopener noreferrer"
        class="term-btn"
      >
        Keycloak
      </a>
    </div>
  </div>
</template>
