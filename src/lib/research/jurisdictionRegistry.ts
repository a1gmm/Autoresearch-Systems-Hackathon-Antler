// California jurisdiction registry. Resolves WHICH local authority's rules apply
// to a facility by location. Air districts and regional water boards are FINITE
// and fully enumerated here (verified against arb.ca.gov / waterboards.ca.gov).
//
// Honest limits, by design:
//  - Five+ counties are split across air districts by sub-county geometry (LA,
//    San Bernardino, Riverside, Kern, Sonoma, Solano). resolveAirDistrict flags
//    these as needsGeometry: the caller must resolve by point-in-polygon, not by
//    county name alone.
//  - CUPAs (~81) and per-county/city fire+building codes are NOT enumerated here.
//    The fire/building layer is effectively unbounded (~480 cities x 3-year code
//    cycles) and must be resolved per-jurisdiction at runtime, not pre-tabled.

export type AirDistrict = { id: string; name: string; counties: string[]; website: string };
export type RegionalWaterBoard = { id: string; name: string; coverage: string };

export const AIR_DISTRICTS: AirDistrict[] = [
  { id: "amador-county-apcd", name: "Amador County APCD", counties: ["Amador"], website: "https://www.amadorgov.org" },
  { id: "antelope-valley-aqmd", name: "Antelope Valley AQMD", counties: ["Los Angeles"], website: "https://www.avaqmd.ca.gov" },
  { id: "bay-area-aqmd", name: "Bay Area AQMD", counties: ["Alameda", "Contra Costa", "Marin", "Napa", "San Francisco", "San Mateo", "Santa Clara", "Solano", "Sonoma"], website: "https://www.baaqmd.gov" },
  { id: "butte-county-aqmd", name: "Butte County AQMD", counties: ["Butte"], website: "https://www.bcaqmd.org" },
  { id: "calaveras-county-apcd", name: "Calaveras County APCD", counties: ["Calaveras"], website: "https://ema.calaverasgov.us" },
  { id: "colusa-county-apcd", name: "Colusa County APCD", counties: ["Colusa"], website: "https://www.countyofcolusaca.gov" },
  { id: "eastern-kern-apcd", name: "Eastern Kern APCD", counties: ["Kern"], website: "https://www.kernair.org" },
  { id: "el-dorado-county-aqmd", name: "El Dorado County AQMD", counties: ["El Dorado"], website: "https://www.eldoradocounty.ca.gov" },
  { id: "feather-river-aqmd", name: "Feather River AQMD", counties: ["Sutter", "Yuba"], website: "https://www.fraqmd.org" },
  { id: "glenn-county-apcd", name: "Glenn County APCD", counties: ["Glenn"], website: "https://www.countyofglenn.net" },
  { id: "great-basin-unified-apcd", name: "Great Basin Unified APCD", counties: ["Alpine", "Inyo", "Mono"], website: "https://www.gbuapcd.org" },
  { id: "imperial-county-apcd", name: "Imperial County APCD", counties: ["Imperial"], website: "https://www.imperialcounty.net" },
  { id: "lake-county-aqmd", name: "Lake County AQMD", counties: ["Lake"], website: "https://www.lcaqmd.net" },
  { id: "lassen-county-apcd", name: "Lassen County APCD", counties: ["Lassen"], website: "https://www.lassenair.org" },
  { id: "mariposa-county-apcd", name: "Mariposa County APCD", counties: ["Mariposa"], website: "https://www.mariposacounty.org" },
  { id: "mendocino-county-aqmd", name: "Mendocino County AQMD", counties: ["Mendocino"], website: "https://www.co.mendocino.ca.us" },
  { id: "modoc-county-apcd", name: "Modoc County APCD", counties: ["Modoc"], website: "https://www.co.modoc.ca.us" },
  { id: "mojave-desert-aqmd", name: "Mojave Desert AQMD", counties: ["San Bernardino", "Riverside"], website: "https://www.mdaqmd.ca.gov" },
  { id: "monterey-bay-ard", name: "Monterey Bay Air Resources District", counties: ["Monterey", "San Benito", "Santa Cruz"], website: "https://www.mbard.org" },
  { id: "north-coast-unified-aqmd", name: "North Coast Unified AQMD", counties: ["Del Norte", "Humboldt", "Trinity"], website: "https://www.ncuaqmd.org" },
  { id: "northern-sierra-aqmd", name: "Northern Sierra AQMD", counties: ["Nevada", "Plumas", "Sierra"], website: "https://www.myairdistrict.com" },
  { id: "northern-sonoma-county-apcd", name: "Northern Sonoma County APCD", counties: ["Sonoma"], website: "https://www.nosocoair.ca.gov" },
  { id: "placer-county-apcd", name: "Placer County APCD", counties: ["Placer"], website: "https://www.placer.ca.gov" },
  { id: "sacramento-metro-aqmd", name: "Sacramento Metropolitan AQMD", counties: ["Sacramento"], website: "https://www.airquality.org" },
  { id: "san-diego-county-apcd", name: "San Diego County APCD", counties: ["San Diego"], website: "https://www.sdapcd.org" },
  { id: "san-joaquin-valley-apcd", name: "San Joaquin Valley Unified APCD", counties: ["Fresno", "Kings", "Madera", "Merced", "San Joaquin", "Stanislaus", "Tulare", "Kern"], website: "https://www.valleyair.org" },
  { id: "san-luis-obispo-county-apcd", name: "San Luis Obispo County APCD", counties: ["San Luis Obispo"], website: "https://www.slocleanair.org" },
  { id: "santa-barbara-county-apcd", name: "Santa Barbara County APCD", counties: ["Santa Barbara"], website: "https://www.ourair.org" },
  { id: "shasta-county-aqmd", name: "Shasta County AQMD", counties: ["Shasta"], website: "https://www.co.shasta.ca.us" },
  { id: "siskiyou-county-apcd", name: "Siskiyou County APCD", counties: ["Siskiyou"], website: "https://www.co.siskiyou.ca.us" },
  { id: "south-coast-aqmd", name: "South Coast AQMD", counties: ["Orange", "Los Angeles", "San Bernardino", "Riverside"], website: "https://www.aqmd.gov" },
  { id: "tehama-county-apcd", name: "Tehama County APCD", counties: ["Tehama"], website: "https://www.tehcoapcd.net" },
  { id: "tuolumne-county-apcd", name: "Tuolumne County APCD", counties: ["Tuolumne"], website: "https://www.co.tuolumne.ca.us" },
  { id: "ventura-county-apcd", name: "Ventura County APCD", counties: ["Ventura"], website: "https://www.vcapcd.org" },
  { id: "yolo-solano-aqmd", name: "Yolo-Solano AQMD", counties: ["Yolo", "Solano"], website: "https://www.ysaqmd.org" },
];

// Counties split across more than one air district (resolution needs geometry).
export const SPLIT_AIR_COUNTIES: ReadonlySet<string> = new Set(["Kern", "Los Angeles", "Riverside", "San Bernardino", "Solano", "Sonoma"]);

export const REGIONAL_WATER_BOARDS: RegionalWaterBoard[] = [
  { id: "region-1-north-coast", name: "North Coast Regional Water Quality Control Board", coverage: "Del Norte, Humboldt, Mendocino, and north-coastal watersheds" },
  { id: "region-2-san-francisco-bay", name: "San Francisco Bay Regional Water Quality Control Board", coverage: "San Francisco Bay Area watersheds" },
  { id: "region-3-central-coast", name: "Central Coast Regional Water Quality Control Board", coverage: "Santa Cruz to Ventura coastal watersheds" },
  { id: "region-4-los-angeles", name: "Los Angeles Regional Water Quality Control Board", coverage: "Los Angeles and Ventura coastal watersheds" },
  { id: "region-5-central-valley", name: "Central Valley Regional Water Quality Control Board", coverage: "Sacramento and San Joaquin valleys (largest region)" },
  { id: "region-6-lahontan", name: "Lahontan Regional Water Quality Control Board", coverage: "Eastern Sierra / Lake Tahoe / high desert" },
  { id: "region-7-colorado-river-basin", name: "Colorado River Basin Regional Water Quality Control Board", coverage: "Imperial and eastern desert watersheds" },
  { id: "region-8-santa-ana", name: "Santa Ana Regional Water Quality Control Board", coverage: "Santa Ana River watershed (Orange + parts of Riverside/San Bernardino)" },
  { id: "region-9-san-diego", name: "San Diego Regional Water Quality Control Board", coverage: "San Diego region watersheds" },
];

export type AirDistrictResolution = {
  county: string;
  districts: AirDistrict[];
  // True when the county spans multiple air districts and a precise answer needs
  // sub-county geometry (lat/long), not just the county name. The caller must
  // not pick one arbitrarily — that would be a guess.
  needsGeometry: boolean;
};

// Resolve the candidate air district(s) for a county. Returns every district that
// covers the county; needsGeometry is true when there is more than one (the five
// known sub-county splits). Unknown county -> empty (never a guess).
export function resolveAirDistrict(county: string): AirDistrictResolution {
  const norm = county.trim().toLowerCase();
  const districts = AIR_DISTRICTS.filter((d) => d.counties.some((c) => c.toLowerCase() === norm));
  return { county, districts, needsGeometry: districts.length > 1 };
}

// County -> Regional Water Quality Control Board region number(s).
// Source: State Water Resources Control Board "The Nine Regional Water Quality
// Control Boards in California" fact sheet (waterboards.ca.gov). Region lines are
// HYDROLOGIC (watershed), not county lines, so many counties span multiple
// regions; those are listed with every region the fact sheet names. The legally
// controlling boundary is the GIS layer — multi-region counties therefore need
// sub-county geometry to pin a single board (needsGeometry below).
export const COUNTY_WATER_REGIONS: Readonly<Record<string, number[]>> = {
  Alameda: [2], Alpine: [6], Amador: [5], Butte: [5], Calaveras: [5], Colusa: [5],
  "Contra Costa": [2, 5], "Del Norte": [1], "El Dorado": [5, 6], Fresno: [5], Glenn: [1, 5],
  Humboldt: [1], Imperial: [7, 9], Inyo: [6], Kern: [3, 5, 6], Kings: [5], Lake: [1, 5],
  Lassen: [5, 6], "Los Angeles": [4, 6], Madera: [5], Marin: [1, 2], Mariposa: [5],
  Mendocino: [1], Merced: [5], Modoc: [1, 5, 6], Mono: [6], Monterey: [3], Napa: [2, 5],
  Nevada: [5, 6], Orange: [8], Placer: [5, 6], Plumas: [5], Riverside: [7, 8, 9],
  Sacramento: [5], "San Benito": [3, 5], "San Bernardino": [6, 7, 8], "San Diego": [7, 9],
  "San Francisco": [2], "San Joaquin": [5], "San Luis Obispo": [3, 5], "San Mateo": [2, 3],
  "Santa Barbara": [3, 4], "Santa Clara": [2, 3], "Santa Cruz": [3], Shasta: [5], Sierra: [5, 6],
  Siskiyou: [1, 5], Solano: [2, 5], Sonoma: [1, 2], Stanislaus: [5], Sutter: [5], Tehama: [5],
  Trinity: [1], Tulare: [5], Tuolumne: [5], Ventura: [3, 4], Yolo: [5], Yuba: [5],
};

const BOARD_BY_REGION = new Map<number, RegionalWaterBoard>(
  REGIONAL_WATER_BOARDS.map((b) => [Number(b.id.split("-")[1]), b]),
);

export type WaterBoardResolution = {
  county: string;
  boards: RegionalWaterBoard[];
  // True when the county spans more than one region — a single board can't be
  // chosen on the county name alone (needs sub-county watershed geometry).
  needsGeometry: boolean;
};

// Resolve the regional water board(s) for a county. Returns every board whose
// region covers the county; needsGeometry is true when more than one does.
// Unknown county -> empty (never a guess).
export function resolveWaterBoard(county: string): WaterBoardResolution {
  const norm = county.trim().replace(/\s+county$/i, "");
  const key = Object.keys(COUNTY_WATER_REGIONS).find((c) => c.toLowerCase() === norm.toLowerCase());
  const regions = key ? COUNTY_WATER_REGIONS[key] : [];
  const boards = regions.map((n) => BOARD_BY_REGION.get(n)).filter((b): b is RegionalWaterBoard => !!b);
  return { county, boards, needsGeometry: boards.length > 1 };
}
