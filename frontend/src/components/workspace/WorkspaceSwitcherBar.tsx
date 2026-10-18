import { ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import {
  clearCurrentWorkspaceId,
  getCurrentWorkspaceId,
  listWorkspaces,
  setCurrentWorkspaceId,
  WORKSPACE_CHANGED_EVENT,
  WorkspaceInfo
} from '@/api/lightrag'
import { cn, errorMessage } from '@/lib/utils'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/Select'

const DEFAULT_WORKSPACE_OPTION = '__default_workspace__'

const toWorkspaceOptionValue = (workspaceId?: string | null): string => {
  const trimmed = typeof workspaceId === 'string' ? workspaceId.trim() : ''
  return trimmed ? trimmed : DEFAULT_WORKSPACE_OPTION
}

type WorkspaceSwitcherBarProps = {
  className?: string
  currentWorkspaceClassName?: string
  selectTriggerClassName?: string
  actions?: ReactNode
  description?: ReactNode
  workspaces?: WorkspaceInfo[]
  selectedWorkspaceId?: string | null
  isLoadingWorkspaces?: boolean
  onValueChange?: (workspaceId: string | null) => void | Promise<void>
  onWorkspaceChanged?: (workspaceId: string | null) => void | Promise<void>
}

export default function WorkspaceSwitcherBar({
  className,
  currentWorkspaceClassName,
  selectTriggerClassName,
  actions,
  description,
  workspaces: controlledWorkspaces,
  selectedWorkspaceId: controlledSelectedWorkspaceId,
  isLoadingWorkspaces: controlledIsLoadingWorkspaces,
  onValueChange,
  onWorkspaceChanged
}: WorkspaceSwitcherBarProps) {
  const { t } = useTranslation()
  const [internalWorkspaces, setInternalWorkspaces] = useState<WorkspaceInfo[]>([])
  const [internalIsLoadingWorkspaces, setInternalIsLoadingWorkspaces] = useState(false)
  const [internalSelectedWorkspaceId, setInternalSelectedWorkspaceId] = useState<string | null>(() => getCurrentWorkspaceId())

  const isControlled = controlledWorkspaces !== undefined
  const workspaces = controlledWorkspaces ?? internalWorkspaces
  const isLoadingWorkspaces = controlledIsLoadingWorkspaces ?? internalIsLoadingWorkspaces
  const selectedWorkspaceId = controlledSelectedWorkspaceId !== undefined
    ? controlledSelectedWorkspaceId
    : internalSelectedWorkspaceId

  const loadWorkspaces = useCallback(async (showErrorToast: boolean = false) => {
    if (isControlled) {
      return
    }

    setInternalIsLoadingWorkspaces(true)
    try {
      const response = await listWorkspaces()
      setInternalWorkspaces(response.workspaces)
      setInternalSelectedWorkspaceId(getCurrentWorkspaceId())
    } catch (err) {
      console.error('Failed to load workspaces:', err)
      if (showErrorToast) {
        toast.error(t('workspaceSelector.loadFailed', { error: errorMessage(err) }))
      }
    } finally {
      setInternalIsLoadingWorkspaces(false)
    }
  }, [isControlled, t])

  const handleWorkspaceChange = useCallback(async (value: string) => {
    const nextWorkspaceId = value === DEFAULT_WORKSPACE_OPTION ? null : value
    const currentWorkspaceId = getCurrentWorkspaceId()

    if (currentWorkspaceId === nextWorkspaceId) {
      return
    }

    if (nextWorkspaceId) {
      setCurrentWorkspaceId(nextWorkspaceId)
    } else {
      clearCurrentWorkspaceId()
    }

    if (controlledSelectedWorkspaceId === undefined) {
      setInternalSelectedWorkspaceId(nextWorkspaceId)
    }

    await onValueChange?.(nextWorkspaceId)
    await onWorkspaceChanged?.(nextWorkspaceId)
  }, [controlledSelectedWorkspaceId, onValueChange, onWorkspaceChanged])

  useEffect(() => {
    if (isControlled) {
      return
    }

    void loadWorkspaces(false)
  }, [isControlled, loadWorkspaces])

  useEffect(() => {
    const handleWorkspaceChanged = () => {
      if (controlledSelectedWorkspaceId === undefined) {
        setInternalSelectedWorkspaceId(getCurrentWorkspaceId())
      }
      void loadWorkspaces(false)
    }

    window.addEventListener(WORKSPACE_CHANGED_EVENT, handleWorkspaceChanged)
    return () => {
      window.removeEventListener(WORKSPACE_CHANGED_EVENT, handleWorkspaceChanged)
    }
  }, [controlledSelectedWorkspaceId, loadWorkspaces])

  const workspaceOptions = useMemo<WorkspaceInfo[]>(() => {
    if (workspaces.length > 0) {
      return workspaces
    }

    return [{
      id: '',
      display_name: t('workspaceSelector.defaultOption'),
      created_at: '',
      updated_at: '',
      is_default: true
    }]
  }, [t, workspaces])

  const currentWorkspaceLabel = useMemo(() => {
    const matchedWorkspace = workspaceOptions.find(workspace => workspace.id === (selectedWorkspaceId || ''))
    return matchedWorkspace?.display_name || t('workspaceSelector.defaultOption')
  }, [selectedWorkspaceId, t, workspaceOptions])

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div className="flex min-w-[220px] flex-col gap-1 md:max-w-xl">
          <span className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
            {t('workspaceSelector.label')}
          </span>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Select
              value={toWorkspaceOptionValue(selectedWorkspaceId)}
              onValueChange={(value) => {
                void handleWorkspaceChange(value)
              }}
            >
              <SelectTrigger className={cn('min-w-[220px] bg-background/80 sm:flex-1', selectTriggerClassName)} disabled={isLoadingWorkspaces}>
                <SelectValue placeholder={t('workspaceSelector.placeholder')} />
              </SelectTrigger>
              <SelectContent>
                {workspaceOptions.map((workspace) => (
                  <SelectItem
                    key={`workspace-${workspace.id || 'default'}`}
                    value={toWorkspaceOptionValue(workspace.id)}
                  >
                    {workspace.display_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {actions}
          </div>
        </div>
        <div className={cn('text-muted-foreground text-sm', currentWorkspaceClassName)}>
          {t('workspaceSelector.current', { name: currentWorkspaceLabel })}
        </div>
      </div>
      {description ? <div className="text-muted-foreground text-sm">{description}</div> : null}
    </div>
  )
}