import type { Permission, PermissionScope, ApprovalRequest } from './types.js'
import { randomUUID } from 'node:crypto'

export class PermissionManager {
  private permissions: Map<string, Permission> = new Map()
  private approvals: Map<string, ApprovalRequest> = new Map()
  private roleHierarchy: Map<string, string[]> = new Map()

  constructor() {
    this.defineRole('admin', ['*:*'])
    this.defineRole('developer', ['filesystem:*', 'exec:read', 'network:http'])
    this.defineRole('user', ['filesystem:read', 'network:http'])
    this.defineRole('guest', ['filesystem:read'])
  }

  defineRole(role: string, scopes: string[]): void {
    const parsed: PermissionScope[] = scopes.map(s => {
      const parts = s.split(':')
      const resource = parts[0] ?? ''
      const actionRaw = parts[1]
      const action: PermissionScope['action'] = (actionRaw === '*' || !actionRaw) ? 'read' : actionRaw as PermissionScope['action']
      return { resource, action }
    })
    this.permissions.set(`role:${role}`, { id: `role:${role}`, role, scopes: parsed })
  }

  addRoleInheritance(parent: string, child: string): void {
    const existing = this.roleHierarchy.get(child) ?? []
    existing.push(parent)
    this.roleHierarchy.set(child, existing)
  }

  checkPermission(role: string, required: PermissionScope): boolean {
    const perm = this.permissions.get(`role:${role}`)
    if (!perm) return false

    if (this.hasScope(perm.scopes, { resource: '*', action: 'admin' })) return true

    const effectiveScopes = [...perm.scopes]
    const inherited = this.roleHierarchy.get(role) ?? []
    for (const parentRole of inherited) {
      const parentPerm = this.permissions.get(`role:${parentRole}`)
      if (parentPerm) effectiveScopes.push(...parentPerm.scopes)
    }

    return this.hasScope(effectiveScopes, required)
  }

  requestApproval(opts: {
    toolName: string
    arguments: Record<string, unknown>
    userId?: string
    sessionId: string
    reason: string
  }): ApprovalRequest {
    const request: ApprovalRequest = {
      id: randomUUID(),
      toolCallId: randomUUID(),
      toolName: opts.toolName,
      arguments: opts.arguments,
      userId: opts.userId,
      sessionId: opts.sessionId,
      reason: opts.reason,
      requestedAt: new Date(),
      status: 'pending',
    }
    this.approvals.set(request.id, request)
    return request
  }

  approveApproval(id: string, decidedBy: string): ApprovalRequest | undefined {
    const req = this.approvals.get(id)
    if (!req || req.status !== 'pending') return undefined
    req.status = 'approved'
    req.decidedBy = decidedBy
    req.decidedAt = new Date()
    return req
  }

  rejectApproval(id: string, decidedBy: string): ApprovalRequest | undefined {
    const req = this.approvals.get(id)
    if (!req || req.status !== 'pending') return undefined
    req.status = 'rejected'
    req.decidedBy = decidedBy
    req.decidedAt = new Date()
    return req
  }

  getPendingApprovals(): ApprovalRequest[] {
    return Array.from(this.approvals.values()).filter(a => a.status === 'pending')
  }

  getApproval(id: string): ApprovalRequest | undefined {
    return this.approvals.get(id)
  }

  listApprovals(filter?: { status?: string }): ApprovalRequest[] {
    let result = Array.from(this.approvals.values())
    if (filter?.status) result = result.filter(a => a.status === filter.status)
    return result.sort((a, b) => b.requestedAt.getTime() - a.requestedAt.getTime())
  }

  private hasScope(scopes: PermissionScope[], required: PermissionScope): boolean {
    return scopes.some(s => {
      const resourceMatch = s.resource === '*' || s.resource === required.resource
      const actionMatch = s.action === 'admin' || s.action === undefined || s.action === required.action
      return resourceMatch && actionMatch
    })
  }
}
