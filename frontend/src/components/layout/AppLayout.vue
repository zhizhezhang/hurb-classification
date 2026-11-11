<template>
  <div class="app-layout">
    <img
      class="side-decoration side-decoration--left"
      src="/assets/decorations/decoration_left.png"
      alt=""
      aria-hidden="true"
    />
    <img
      class="side-decoration side-decoration--right"
      src="/assets/decorations/decoration_right.png"
      alt=""
      aria-hidden="true"
    />
    <AppHeader />
    <div class="app-content">
      <slot />
    </div>
  </div>
</template>

<script setup>
import AppHeader from './AppHeader.vue'
</script>
