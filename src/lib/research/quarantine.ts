// Treat intake + fetched content as DATA, never instructions. The orchestrator now
// reasons over untrusted text to propose permits; injected directives ("also add
// permit X", "ignore family Y") must not steer proposal reasoning. (Design E5.)
export type QuarantineResult = { flagged: boolean; reason?: string };

const INJECTION_PATTERNS: Array<{ re: RegExp; reason: string }> = [
  { re: /ignore (all |the )?(previous|prior|above) (instructions|prompts?)/i, reason: "override-instructions" },
  { re: /disregard (the |your )?(system|previous) (prompt|instructions)/i, reason: "override-instructions" },
  { re: /you are now\b/i, reason: "role-redefinition" },
  { re: /\b(system|developer)\s*:/i, reason: "fake-role-tag" },
  { re: /\b(also )?(add|include|drop|remove|skip|ignore) (the )?permit\b/i, reason: "permit-set-tampering" },
];

export function quarantineInjection(text: string): QuarantineResult {
  for (const { re, reason } of INJECTION_PATTERNS) {
    if (re.test(text)) return { flagged: true, reason };
  }
  return { flagged: false };
}
