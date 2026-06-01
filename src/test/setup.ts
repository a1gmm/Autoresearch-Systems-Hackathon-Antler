import "@testing-library/jest-dom/vitest";

// Tests run offline and deterministic: default the research pool to fixture mode.
// Production defaults to live (config.ts); individual tests that exercise the live
// fail-closed path set RESEARCH_MODE="live" explicitly and restore it afterward.
process.env.RESEARCH_MODE ??= "fixture";
