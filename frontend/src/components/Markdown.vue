<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps<{ source: string }>()
const html = computed(() => (props.source ? marked.parse(props.source, { async: false }) as string : ''))
</script>

<template>
  <div class="md" v-html="html" />
</template>

<style scoped>
.md :deep(h1), .md :deep(h2), .md :deep(h3) { margin: 0.6em 0 0.3em; }
.md :deep(p) { line-height: 1.6; }
.md :deep(table) { border-collapse: collapse; margin: 0.5em 0; }
.md :deep(th), .md :deep(td) { border: 1px solid #333; padding: 4px 8px; }
.md :deep(code) { background: rgba(255,255,255,0.08); padding: 1px 4px; border-radius: 4px; }
.md :deep(pre) { background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px; overflow: auto; }
</style>
