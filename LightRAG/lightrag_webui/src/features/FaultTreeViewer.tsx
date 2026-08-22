import { useEffect, useRef } from 'react'
import { mountFaultTreeApp } from '@/fault-tree-app/src/main.js'
import { useSettingsStore } from '@/stores/settings'

export default function FaultTreeViewer() {
  const mountRef = useRef<HTMLDivElement | null>(null)
  const currentTab = useSettingsStore.use.currentTab()
  const isFaultTreeTabActive = currentTab === 'fault-tree'

  useEffect(() => {
    if (!isFaultTreeTabActive || !mountRef.current) {
      return
    }

    const mountedApp = mountFaultTreeApp(mountRef.current, { embedded: true })

    return () => {
      mountedApp.unmount()
    }
  }, [isFaultTreeTabActive])

  return (
    <div className="h-full w-full overflow-hidden bg-background">
      {isFaultTreeTabActive ? <div ref={mountRef} className="h-full w-full" /> : null}
    </div>
  )
}