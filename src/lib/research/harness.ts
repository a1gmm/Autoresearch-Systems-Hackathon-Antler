import type { AgentRole, HarnessToolId } from "./toolCatalog";
import { getTool, isToolScopedToRole } from "./toolCatalog";

export type HarnessCall = {
  tool_id: HarnessToolId;
  ts: string;
};

export type HarnessContext = {
  role: AgentRole;
  allowed_tools: HarnessToolId[];
  blocked_tools: HarnessToolId[];
  calls: HarnessCall[];
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
  allowed_tools: HarnessToolId[];
  blocked_tools: HarnessToolId[];
}): HarnessContext {
  const calls: HarnessCall[] = [];
  const allowedTools = [...input.allowed_tools];
  const blockedTools = [...input.blocked_tools];

  return {
    role: input.role,
    allowed_tools: allowedTools,
    blocked_tools: blockedTools,
    calls,
    callTool(toolId: HarnessToolId) {
      assertToolAllowed(input.role, toolId, allowedTools, blockedTools);
      calls.push({ tool_id: toolId, ts: new Date().toISOString() });
    }
  };
}

export function assertToolAllowed(
  role: AgentRole,
  toolId: HarnessToolId,
  allowedTools: readonly HarnessToolId[],
  blockedTools: readonly HarnessToolId[]
) {
  getTool(toolId);
  if (blockedTools.includes(toolId)) {
    throw new HarnessToolScopeError(`${role} cannot call blocked tool ${toolId}`);
  }
  if (!allowedTools.includes(toolId)) {
    throw new HarnessToolScopeError(`${role} was not granted tool ${toolId}`);
  }
  if (!isToolScopedToRole(toolId, role)) {
    throw new HarnessToolScopeError(`${toolId} is not scoped to ${role}`);
  }
}
