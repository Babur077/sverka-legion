export const MODULE_WORKSPACE_KEYS = ['bank_rrn'] as const;

export type ModuleWorkspaceKey = typeof MODULE_WORKSPACE_KEYS[number];

export function hasModuleWorkspace(workspace?: string | null): workspace is ModuleWorkspaceKey {
  return !!workspace && (MODULE_WORKSPACE_KEYS as readonly string[]).includes(workspace);
}
