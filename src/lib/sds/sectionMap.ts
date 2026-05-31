import type { SdsSectionMap, SdsSectionStatus } from "./types";

export const SDS_SECTION_HEADINGS: Record<number, string> = {
  1: "Identification",
  2: "Hazard(s) identification",
  3: "Composition/information on ingredients",
  4: "First-aid measures",
  5: "Fire-fighting measures",
  6: "Accidental release measures",
  7: "Handling and storage",
  8: "Exposure controls/personal protection",
  9: "Physical and chemical properties",
  10: "Stability and reactivity",
  11: "Toxicological information",
  12: "Ecological information",
  13: "Disposal considerations",
  14: "Transport information",
  15: "Regulatory information",
  16: "Other information",
};

type HeadingMatch = {
  sectionNumber: number;
  lineStart: number;
  lineEnd: number;
};

const SECTION_HEADING_RE = /^(?:(section|sec\.?)\s*)?(0?[1-9]|1[0-6])(?:\s*[:.)-]+\s*|\s+)(.*)$/i;
const MIN_USEFUL_SECTION_TEXT_LENGTH = 24;
const NUMERIC_HEADING_KEYWORDS: Record<number, RegExp> = {
  1: /\bidentification\b/i,
  2: /\bhazards?\b|\bhazard\(s\)\b/i,
  3: /\bcomposition\b|\bingredients?\b/i,
  4: /\bfirst[- ]aid\b/i,
  5: /\bfire[- ]fighting\b|\bfirefighting\b/i,
  6: /\baccidental release\b|\brelease measures\b/i,
  7: /\bhandling\b|\bstorage\b/i,
  8: /\bexposure controls?\b|\bpersonal protection\b/i,
  9: /\bphysical\b|\bchemical properties\b/i,
  10: /\bstability\b|\breactivity\b/i,
  11: /\btoxicological\b|\btoxicology\b/i,
  12: /\becological\b|\becology\b/i,
  13: /\bdisposal\b/i,
  14: /\btransport\b/i,
  15: /\bregulatory\b|\bregulation\b/i,
  16: /\bother information\b/i,
};

export function normalizeText(text: string): string {
  return text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => line.trim())
    .join("\n")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function mapSdsSections(documentId: string, text: string): SdsSectionMap {
  const normalizedText = normalizeText(text);
  const matches = findSectionHeadings(normalizedText);

  const sections = Array.from({ length: 16 }, (_, index) => {
    const sectionNumber = index + 1;
    const sectionMatches = matches.filter((match) => match.sectionNumber === sectionNumber);
    const firstMatch = sectionMatches[0];

    if (!firstMatch) {
      return {
        section_number: sectionNumber,
        heading: SDS_SECTION_HEADINGS[sectionNumber],
        text: "",
        confidence: 0,
        status: "missing" as const,
      };
    }

    const sectionText = extractSectionText(normalizedText, matches, firstMatch);
    const status = getSectionStatus(sectionMatches.length, sectionText);

    return {
      section_number: sectionNumber,
      heading: SDS_SECTION_HEADINGS[sectionNumber],
      text: sectionText,
      confidence: confidenceForStatus(status),
      status,
    };
  });

  return {
    document_id: documentId,
    sections,
  };
}

function findSectionHeadings(text: string): HeadingMatch[] {
  const matches: HeadingMatch[] = [];
  let offset = 0;

  for (const line of text.split("\n")) {
    const headingMatch = line.match(SECTION_HEADING_RE);
    if (headingMatch && isSdsSectionHeading(Number(headingMatch[2]), headingMatch[3], Boolean(headingMatch[1]))) {
      matches.push({
        sectionNumber: Number(headingMatch[2]),
        lineStart: offset,
        lineEnd: offset + line.length,
      });
    }
    offset += line.length + 1;
  }

  return matches.sort((a, b) => a.lineStart - b.lineStart);
}

function isSdsSectionHeading(sectionNumber: number, headingText: string, hasSectionPrefix: boolean): boolean {
  if (hasSectionPrefix) {
    return true;
  }

  return NUMERIC_HEADING_KEYWORDS[sectionNumber].test(headingText);
}

function extractSectionText(text: string, matches: HeadingMatch[], match: HeadingMatch): string {
  const nextMatch = matches.find((candidate) => candidate.lineStart > match.lineStart);
  const start = text[match.lineEnd] === "\n" ? match.lineEnd + 1 : match.lineEnd;
  const end = nextMatch?.lineStart ?? text.length;

  return normalizeText(text.slice(start, end));
}

function getSectionStatus(matchCount: number, text: string): SdsSectionStatus {
  if (matchCount > 1) {
    return "ambiguous";
  }

  if (text.length < MIN_USEFUL_SECTION_TEXT_LENGTH) {
    return "merged";
  }

  return "present";
}

function confidenceForStatus(status: SdsSectionStatus): number {
  if (status === "present") {
    return 0.95;
  }
  if (status === "missing") {
    return 0;
  }
  if (status === "ambiguous") {
    return 0.5;
  }
  return 0.45;
}
