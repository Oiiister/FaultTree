declare module '@/fault-tree-app/src/main.js' {
  import type { App } from 'vue'
  import type { Router } from 'vue-router'

  export interface FaultTreeMountOptions {
    embedded?: boolean
  }

  export interface FaultTreeMountedApp {
    app: App<Element>
    router: Router
    unmount: () => void
  }

  export function mountFaultTreeApp(
    target: Element | string,
    options?: FaultTreeMountOptions
  ): FaultTreeMountedApp
}