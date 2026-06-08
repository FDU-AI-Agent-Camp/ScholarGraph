import { defineComponent, h } from 'vue'
import { RouterView } from 'vue-router'

/** Minimal shell that renders the active route component. */
export const routerViewShell = defineComponent({
  setup() {
    return () => h('div', { id: 'router-view-shell' }, [h(RouterView)])
  },
})
