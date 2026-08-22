<template>
  <div class="fault-tree-app-shell">
    <router-view />
  </div>
</template>

<script setup>
</script>

<style scoped>
.fault-tree-app-shell {
  height: 100%;
  width: 100%;
  overflow: hidden;
}

.fault-tree-app-shell :deep(*) {
  box-sizing: border-box;
}
</style>