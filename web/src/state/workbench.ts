import type { InjectionKey, Ref } from 'vue'

import type { WorkspaceResponse } from '@/types/workbench'

export interface WorkbenchContext {
  workspace: Ref<WorkspaceResponse | null>
  loading: Ref<boolean>
  error: Ref<string>
  operationsOpen: Ref<boolean>
  refreshWorkspace: (options?: { silent?: boolean }) => Promise<void>
}

export const workbenchKey = Symbol('workbench') as InjectionKey<WorkbenchContext>
