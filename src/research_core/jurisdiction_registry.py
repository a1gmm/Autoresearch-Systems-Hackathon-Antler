from __future__ import annotations

from dataclasses import dataclass

from research_core.jurisdiction_skills import normalize_county_name


@dataclass(frozen=True)
class AirDistrict:
    id: str
    name: str
    counties: tuple[str, ...]
    website: str


@dataclass(frozen=True)
class RegionalWaterBoard:
    id: str
    name: str
    coverage: str


@dataclass(frozen=True)
class AirDistrictResolution:
    county: str
    districts: tuple[AirDistrict, ...]
    needs_geometry: bool


@dataclass(frozen=True)
class WaterBoardResolution:
    county: str
    boards: tuple[RegionalWaterBoard, ...]
    needs_geometry: bool


AIR_DISTRICTS: tuple[AirDistrict, ...] = (
    AirDistrict("amador-county-apcd", "Amador County APCD", ("Amador",), "https://www.amadorgov.org"),
    AirDistrict("antelope-valley-aqmd", "Antelope Valley AQMD", ("Los Angeles",), "https://www.avaqmd.ca.gov"),
    AirDistrict("bay-area-aqmd", "Bay Area AQMD", ("Alameda", "Contra Costa", "Marin", "Napa", "San Francisco", "San Mateo", "Santa Clara", "Solano", "Sonoma"), "https://www.baaqmd.gov"),
    AirDistrict("butte-county-aqmd", "Butte County AQMD", ("Butte",), "https://www.bcaqmd.org"),
    AirDistrict("calaveras-county-apcd", "Calaveras County APCD", ("Calaveras",), "https://ema.calaverasgov.us"),
    AirDistrict("colusa-county-apcd", "Colusa County APCD", ("Colusa",), "https://www.countyofcolusaca.gov"),
    AirDistrict("eastern-kern-apcd", "Eastern Kern APCD", ("Kern",), "https://www.kernair.org"),
    AirDistrict("el-dorado-county-aqmd", "El Dorado County AQMD", ("El Dorado",), "https://www.eldoradocounty.ca.gov"),
    AirDistrict("feather-river-aqmd", "Feather River AQMD", ("Sutter", "Yuba"), "https://www.fraqmd.org"),
    AirDistrict("glenn-county-apcd", "Glenn County APCD", ("Glenn",), "https://www.countyofglenn.net"),
    AirDistrict("great-basin-unified-apcd", "Great Basin Unified APCD", ("Alpine", "Inyo", "Mono"), "https://www.gbuapcd.org"),
    AirDistrict("imperial-county-apcd", "Imperial County APCD", ("Imperial",), "https://www.imperialcounty.net"),
    AirDistrict("lake-county-aqmd", "Lake County AQMD", ("Lake",), "https://www.lcaqmd.net"),
    AirDistrict("lassen-county-apcd", "Lassen County APCD", ("Lassen",), "https://www.lassenair.org"),
    AirDistrict("mariposa-county-apcd", "Mariposa County APCD", ("Mariposa",), "https://www.mariposacounty.org"),
    AirDistrict("mendocino-county-aqmd", "Mendocino County AQMD", ("Mendocino",), "https://www.co.mendocino.ca.us"),
    AirDistrict("modoc-county-apcd", "Modoc County APCD", ("Modoc",), "https://www.co.modoc.ca.us"),
    AirDistrict("mojave-desert-aqmd", "Mojave Desert AQMD", ("San Bernardino", "Riverside"), "https://www.mdaqmd.ca.gov"),
    AirDistrict("monterey-bay-ard", "Monterey Bay Air Resources District", ("Monterey", "San Benito", "Santa Cruz"), "https://www.mbard.org"),
    AirDistrict("north-coast-unified-aqmd", "North Coast Unified AQMD", ("Del Norte", "Humboldt", "Trinity"), "https://www.ncuaqmd.org"),
    AirDistrict("northern-sierra-aqmd", "Northern Sierra AQMD", ("Nevada", "Plumas", "Sierra"), "https://www.myairdistrict.com"),
    AirDistrict("northern-sonoma-county-apcd", "Northern Sonoma County APCD", ("Sonoma",), "https://www.nosocoair.ca.gov"),
    AirDistrict("placer-county-apcd", "Placer County APCD", ("Placer",), "https://www.placer.ca.gov"),
    AirDistrict("sacramento-metro-aqmd", "Sacramento Metropolitan AQMD", ("Sacramento",), "https://www.airquality.org"),
    AirDistrict("san-diego-county-apcd", "San Diego County APCD", ("San Diego",), "https://www.sdapcd.org"),
    AirDistrict("san-joaquin-valley-apcd", "San Joaquin Valley Unified APCD", ("Fresno", "Kings", "Madera", "Merced", "San Joaquin", "Stanislaus", "Tulare", "Kern"), "https://www.valleyair.org"),
    AirDistrict("san-luis-obispo-county-apcd", "San Luis Obispo County APCD", ("San Luis Obispo",), "https://www.slocleanair.org"),
    AirDistrict("santa-barbara-county-apcd", "Santa Barbara County APCD", ("Santa Barbara",), "https://www.ourair.org"),
    AirDistrict("shasta-county-aqmd", "Shasta County AQMD", ("Shasta",), "https://www.co.shasta.ca.us"),
    AirDistrict("siskiyou-county-apcd", "Siskiyou County APCD", ("Siskiyou",), "https://www.co.siskiyou.ca.us"),
    AirDistrict("south-coast-aqmd", "South Coast AQMD", ("Orange", "Los Angeles", "San Bernardino", "Riverside"), "https://www.aqmd.gov"),
    AirDistrict("tehama-county-apcd", "Tehama County APCD", ("Tehama",), "https://www.tehcoapcd.net"),
    AirDistrict("tuolumne-county-apcd", "Tuolumne County APCD", ("Tuolumne",), "https://www.co.tuolumne.ca.us"),
    AirDistrict("ventura-county-apcd", "Ventura County APCD", ("Ventura",), "https://www.vcapcd.org"),
    AirDistrict("yolo-solano-aqmd", "Yolo-Solano AQMD", ("Yolo", "Solano"), "https://www.ysaqmd.org"),
)


SPLIT_AIR_COUNTIES: frozenset[str] = frozenset(
    ["Kern", "Los Angeles", "Riverside", "San Bernardino", "Solano", "Sonoma"]
)


REGIONAL_WATER_BOARDS: tuple[RegionalWaterBoard, ...] = (
    RegionalWaterBoard("region-1-north-coast", "North Coast Regional Water Quality Control Board", "Del Norte, Humboldt, Mendocino, and north-coastal watersheds"),
    RegionalWaterBoard("region-2-san-francisco-bay", "San Francisco Bay Regional Water Quality Control Board", "San Francisco Bay Area watersheds"),
    RegionalWaterBoard("region-3-central-coast", "Central Coast Regional Water Quality Control Board", "Santa Cruz to Ventura coastal watersheds"),
    RegionalWaterBoard("region-4-los-angeles", "Los Angeles Regional Water Quality Control Board", "Los Angeles and Ventura coastal watersheds"),
    RegionalWaterBoard("region-5-central-valley", "Central Valley Regional Water Quality Control Board", "Sacramento and San Joaquin valleys (largest region)"),
    RegionalWaterBoard("region-6-lahontan", "Lahontan Regional Water Quality Control Board", "Eastern Sierra / Lake Tahoe / high desert"),
    RegionalWaterBoard("region-7-colorado-river-basin", "Colorado River Basin Regional Water Quality Control Board", "Imperial and eastern desert watersheds"),
    RegionalWaterBoard("region-8-santa-ana", "Santa Ana Regional Water Quality Control Board", "Santa Ana River watershed (Orange + parts of Riverside/San Bernardino)"),
    RegionalWaterBoard("region-9-san-diego", "San Diego Regional Water Quality Control Board", "San Diego region watersheds"),
)


COUNTY_WATER_REGIONS: dict[str, tuple[int, ...]] = {
    "Alameda": (2,),
    "Alpine": (6,),
    "Amador": (5,),
    "Butte": (5,),
    "Calaveras": (5,),
    "Colusa": (5,),
    "Contra Costa": (2, 5),
    "Del Norte": (1,),
    "El Dorado": (5, 6),
    "Fresno": (5,),
    "Glenn": (1, 5),
    "Humboldt": (1,),
    "Imperial": (7, 9),
    "Inyo": (6,),
    "Kern": (3, 5, 6),
    "Kings": (5,),
    "Lake": (1, 5),
    "Lassen": (5, 6),
    "Los Angeles": (4, 6),
    "Madera": (5,),
    "Marin": (1, 2),
    "Mariposa": (5,),
    "Mendocino": (1,),
    "Merced": (5,),
    "Modoc": (1, 5, 6),
    "Mono": (6,),
    "Monterey": (3,),
    "Napa": (2, 5),
    "Nevada": (5, 6),
    "Orange": (8,),
    "Placer": (5, 6),
    "Plumas": (5,),
    "Riverside": (7, 8, 9),
    "Sacramento": (5,),
    "San Benito": (3, 5),
    "San Bernardino": (6, 7, 8),
    "San Diego": (7, 9),
    "San Francisco": (2,),
    "San Joaquin": (5,),
    "San Luis Obispo": (3, 5),
    "San Mateo": (2, 3),
    "Santa Barbara": (3, 4),
    "Santa Clara": (2, 3),
    "Santa Cruz": (3,),
    "Shasta": (5,),
    "Sierra": (5, 6),
    "Siskiyou": (1, 5),
    "Solano": (2, 5),
    "Sonoma": (1, 2),
    "Stanislaus": (5,),
    "Sutter": (5,),
    "Tehama": (5,),
    "Trinity": (1,),
    "Tulare": (5,),
    "Tuolumne": (5,),
    "Ventura": (3, 4),
    "Yolo": (5,),
    "Yuba": (5,),
}


BOARD_BY_REGION: dict[int, RegionalWaterBoard] = {
    int(board.id.split("-")[1]): board for board in REGIONAL_WATER_BOARDS
}


def resolve_air_district(county: str) -> AirDistrictResolution:
    norm = normalize_county_name(county).lower()
    districts = tuple(
        district
        for district in AIR_DISTRICTS
        if any(c.lower() == norm for c in district.counties)
    )
    return AirDistrictResolution(
        county=county,
        districts=districts,
        needs_geometry=len(districts) > 1,
    )


def resolve_water_board(county: str) -> WaterBoardResolution:
    norm = normalize_county_name(county)
    key = next(
        (c for c in COUNTY_WATER_REGIONS if c.lower() == norm.lower()),
        None,
    )
    regions = COUNTY_WATER_REGIONS[key] if key else ()
    boards = tuple(
        BOARD_BY_REGION[region]
        for region in regions
        if region in BOARD_BY_REGION
    )
    return WaterBoardResolution(
        county=county,
        boards=boards,
        needs_geometry=len(boards) > 1,
    )
