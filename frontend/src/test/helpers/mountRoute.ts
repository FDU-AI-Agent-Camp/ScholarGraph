import { flushPromises, mount, type Stubs, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { routes } from '@/router/index'

import { routerViewShell } from './routerViewShell'

/** Wait until lazy ``RouterView`` children finish mounting under load. */
export async function waitForRouterViewRender(wrapper: VueWrapper): Promise<void> {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await flushPromises()
    await nextTick()
    const shell = wrapper.find('#router-view-shell')
    if (!shell.exists()) {
      continue
    }
    const inner = shell.element.innerHTML.replace(/<!--.*?-->/g, '').trim()
    if (inner.length > 0) {
      return
    }
  }
  throw new Error('RouterView did not render route component in time')
}

export async function mountAppRoute(path: string, stubs: Stubs): Promise<{ wrapper: VueWrapper; router: Router }> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes,
  })
  await router.push(path)
  await router.isReady()

  const wrapper = mount(routerViewShell, {
    global: {
      plugins: [router],
      stubs,
    },
    attachTo: document.body,
  })
  await waitForRouterViewRender(wrapper)
  return { wrapper, router }
}
