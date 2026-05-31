import type { AgentRole, HarnessToolId } from "./toolCatalog";
import { getTool, isToolScopedToRole } from "./toolCatalog";

export type HarnessCall = {
  readonly tool_id: HarnessToolId;
  readonly ts: string;
};

export type HarnessContext = {
  readonly role: AgentRole;
  allowed_tools: readonly HarnessToolId[];
  blocked_tools: readonly HarnessToolId[];
  readonly calls: readonly HarnessCall[];
  callTool: (toolId: HarnessToolId) => void;
};

export class HarnessToolScopeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "HarnessToolScopeError";
  }
}

export function createHarnessContext(input: {
  role: AgentRole;
  allowed_tools: readonly HarnessToolId[];
  blocked_tools: readonly HarnessToolId[];
}): HarnessContext {
  const role = input.role;
  const calls: HarnessCall[] = [];
  const allowedTools = Object.freeze([...input.allowed_tools]);
  const blockedTools = Object.freeze([...input.blocked_tools]);
  const allowedToolSet = new Set(input.allowed_tools);
  const blockedToolSet = new Set(input.blocked_tools);

  return {
    role,
    allowed_tools: allowedTools,
    blocked_tools: blockedTools,
    get calls() {
      return Object.freeze(calls.map((call) => ({ ...call })));
    },
    callTool(toolId: HarnessToolId) {
      assertToolAllowed(role, toolId, allowedToolSet, blockedToolSet);
      calls.push({ tool_id: toolId, ts: new Date().toISOString() });
    }
  };
}

export function assertToolAllowed(
  role: AgentRole,
  toolId: HarnessToolId,
  allowedTools: ReadonlySet<HarnessToolId>,
  blockedTools: ReadonlySet<HarnessToolId>
) {
  getTool(toolId);
  if (blockedTools.has(toolId)) {
    throw new HarnessToolScopeError(`${role} cannot call blocked tool ${toolId}`);
  }
  if (!allowedTools.has(toolId)) {
    throw new HarnessToolScopeError(`${role} was not granted tool ${toolId}`);
  }
  if (!isToolScopedToRole(toolId, role)) {
    throw new HarnessToolScopeError(`${toolId} is not scoped to ${role}`);
  }
}
