from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from research_core.models import ScopePack


@dataclass(frozen=True)
class ProgramHypothesis:
    id: str
    question: str
    claim_to_test: str


@dataclass(frozen=True)
class ProgramRegistryEntry:
    id: str
    family: str
    name: str
    what_it_does: str
    jurisdiction: str
    authority_source_url: str
    authority_rank: int
    hypotheses: tuple[ProgramHypothesis, ...]
    triggered_by: Callable[[ScopePack], bool]


def _has_equipment(scope: ScopePack) -> bool:
    return len(scope.project_change.equipment) > 0


def _has_chemicals(scope: ScopePack) -> bool:
    return len(scope.project_change.chemicals) > 0


def _has_waste(scope: ScopePack) -> bool:
    return len(scope.project_change.waste_streams) > 0


def _has_code_or_acres(scope: ScopePack) -> bool:
    return (
        bool(scope.facility.sic)
        or bool(scope.facility.naics)
        or scope.project_change.disturbance_acres is not None
    )


def _discharge_possible(scope: ScopePack) -> bool:
    return scope.project_change.process_discharge is not False


def _hypothesis(id: str, question: str, claim_to_test: str) -> ProgramHypothesis:
    return ProgramHypothesis(id=id, question=question, claim_to_test=claim_to_test)


PROGRAM_REGISTRY: tuple[ProgramRegistryEntry, ...] = (
    ProgramRegistryEntry(
        id="scaqmd-permit-to-construct",
        family="air",
        name="SCAQMD Permit to Construct (Rule 201)",
        what_it_does=(
            "Authorizes installing/modifying equipment that may emit air "
            "contaminants."
        ),
        jurisdiction="SCAQMD",
        authority_source_url=(
            "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-201.pdf"
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-AIR-201",
                "Does the new equipment require an SCAQMD Permit to Construct?",
                (
                    "SCAQMD Permit to Construct may apply before installing "
                    "emitting equipment."
                ),
            ),
            _hypothesis(
                "H-AIR-VOC",
                "Do solvent VOC emissions require additional review?",
                "Solvent use may create VOC-related review needs.",
            ),
        ),
        triggered_by=_has_equipment,
    ),
    ProgramRegistryEntry(
        id="scaqmd-rule-219-exemption",
        family="air",
        name="SCAQMD Rule 219 exemption",
        what_it_does=(
            "Exempts listed equipment from written permit requirements if "
            "conditions are met."
        ),
        jurisdiction="SCAQMD",
        authority_source_url=(
            "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-219.pdf"
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-AIR-219",
                "Is Rule 219 exemption available?",
                "Rule 219 may exempt listed equipment if conditions are satisfied.",
            ),
        ),
        triggered_by=_has_equipment,
    ),
    ProgramRegistryEntry(
        id="scaqmd-rule-222-registration",
        family="air",
        name="SCAQMD Rule 222 registration",
        what_it_does=(
            "Registration path for specified equipment categories instead of a "
            "full permit."
        ),
        jurisdiction="SCAQMD",
        authority_source_url=(
            "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-222.pdf"
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-AIR-222",
                "Does Rule 222 registration apply instead?",
                "Rule 222 registration may apply to specified equipment categories.",
            ),
        ),
        triggered_by=_has_equipment,
    ),
    ProgramRegistryEntry(
        id="ca-industrial-general-permit",
        family="stormwater",
        name="California Industrial General Permit (IGP)",
        what_it_does=(
            "Stormwater coverage triggered by industrial activity SIC/NAICS codes."
        ),
        jurisdiction="California Water Boards",
        authority_source_url=(
            "https://www.waterboards.ca.gov/water_issues/programs/stormwater/"
            "industrial.html"
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-STORM-IGP",
                "Does SIC/NAICS trigger Industrial General Permit coverage?",
                "SIC/NAICS may trigger California Industrial General Permit coverage.",
            ),
        ),
        triggered_by=_has_code_or_acres,
    ),
    ProgramRegistryEntry(
        id="ca-construction-general-permit",
        family="stormwater",
        name="California Construction General Permit (CGP)",
        what_it_does=(
            "Stormwater coverage for construction disturbing one or more acres."
        ),
        jurisdiction="California Water Boards",
        authority_source_url=(
            "https://www.waterboards.ca.gov/water_issues/programs/stormwater/"
            "construction.html"
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-STORM-CGP",
                "Does construction disturb one or more acres?",
                (
                    "Construction disturbance at or above one acre may require "
                    "construction stormwater permit coverage."
                ),
            ),
        ),
        triggered_by=_has_code_or_acres,
    ),
    ProgramRegistryEntry(
        id="ca-hmbp",
        family="hazmat",
        name="California Hazardous Materials Business Plan (HMBP)",
        what_it_does=(
            "Reporting plan triggered by hazardous material quantities at or above "
            "thresholds."
        ),
        jurisdiction="CalEPA / local CUPA",
        authority_source_url="https://calepa.ca.gov/cupa/hazardous-materials-business-plan/",
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-HAZMAT-HMBP",
                "Does hazardous material quantity exceed HMBP thresholds?",
                (
                    "Hazardous material quantities at or above HMBP thresholds "
                    "require a business plan."
                ),
            ),
        ),
        triggered_by=_has_chemicals,
    ),
    ProgramRegistryEntry(
        id="epa-hazwaste-generator",
        family="waste",
        name="EPA Hazardous Waste Generator Category",
        what_it_does=(
            "Generator status (VSQG/SQG/LQG) based on monthly hazardous waste "
            "quantity."
        ),
        jurisdiction="US EPA / CA DTSC",
        authority_source_url=(
            "https://www.epa.gov/hwgenerators/categories-hazardous-waste-generators"
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-WASTE-GENERATOR",
                "Does waste generation change hazardous waste generator status?",
                "Spent solvent or process waste may affect generator category.",
            ),
        ),
        triggered_by=_has_waste,
    ),
    ProgramRegistryEntry(
        id="epa-pretreatment",
        family="wastewater",
        name="EPA National Pretreatment Program",
        what_it_does=(
            "Pretreatment requirements for industrial process wastewater discharges."
        ),
        jurisdiction="US EPA",
        authority_source_url="https://www.epa.gov/npdes/national-pretreatment-program",
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-WASTEWATER-PRETREATMENT",
                "Does process wastewater discharge require pretreatment review?",
                "Industrial process wastewater may require pretreatment review.",
            ),
        ),
        triggered_by=_discharge_possible,
    ),
    ProgramRegistryEntry(
        id="ca-ust-program",
        family="hazmat",
        name="Underground Storage Tank (UST) Program",
        what_it_does=(
            "Leak prevention, monitoring, and permitting for tanks storing "
            "hazardous substances substantially beneath ground."
        ),
        jurisdiction="State Water Board; administered by the local CUPA",
        authority_source_url=(
            "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?"
            "lawCode=HSC&sectionNum=25281."
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-HAZMAT-UST",
                "Does the facility have a regulated underground storage tank?",
                (
                    "Any qualifying underground tank storing a hazardous substance "
                    "is regulated (farm/residential <=1,100 gal exemptions aside)."
                ),
            ),
        ),
        triggered_by=_has_chemicals,
    ),
    ProgramRegistryEntry(
        id="ca-apsa-spcc",
        family="hazmat",
        name="Aboveground Petroleum Storage Act (APSA)",
        what_it_does=(
            "Requires an SPCC plan and CUPA registration for aboveground petroleum "
            "storage."
        ),
        jurisdiction=(
            "CAL FIRE Office of the State Fire Marshal; administered by the local "
            "CUPA"
        ),
        authority_source_url=(
            "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?"
            "lawCode=HSC&sectionNum=25270."
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-HAZMAT-APSA",
                (
                    "Does aggregate aboveground petroleum storage reach the APSA "
                    "threshold?"
                ),
                (
                    "Aggregate aboveground petroleum capacity of 1,320 gallons or "
                    "more (containers >=55 gal) triggers APSA."
                ),
            ),
        ),
        triggered_by=_has_chemicals,
    ),
    ProgramRegistryEntry(
        id="ca-calarp-program",
        family="hazmat",
        name="California Accidental Release Prevention (CalARP)",
        what_it_does=(
            "Requires a Risk Management Plan for processes holding a regulated "
            "substance above its threshold quantity."
        ),
        jurisdiction="CalEPA; administered by the local UPA/CUPA",
        authority_source_url=(
            "https://calepa.ca.gov/wp-content/uploads/2024/08/"
            "California-Code-of-Regulations-Title-19-Division-5-Chapter-2-"
            "%E2%80%93-California-Accidental-Release-Prevention.pdf"
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-HAZMAT-CALARP",
                (
                    "Does a process hold a regulated substance above its CalARP "
                    "threshold quantity?"
                ),
                (
                    "Per-substance threshold quantities in 19 CCR 5130.6 Tables "
                    "1-3 determine RMP applicability."
                ),
            ),
        ),
        triggered_by=_has_chemicals,
    ),
    ProgramRegistryEntry(
        id="ca-ab2588-hot-spots",
        family="air",
        name='AB 2588 Air Toxics "Hot Spots"',
        what_it_does=(
            "Toxic air emissions inventory, risk assessment, and public "
            "notification for stationary sources."
        ),
        jurisdiction=(
            "CARB statewide guidelines; administered by the local air district"
        ),
        authority_source_url=(
            "https://ww2.arb.ca.gov/our-work/programs/ab-2588-air-toxics-hot-spots"
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-AIR-AB2588",
                "Is the facility subject to AB 2588 air-toxics reporting?",
                (
                    "Stationary sources emitting Appendix A substances report per "
                    "district-defined inclusion criteria (no single statewide "
                    "tonnage)."
                ),
            ),
        ),
        triggered_by=_has_equipment,
    ),
    ProgramRegistryEntry(
        id="ca-prop-65",
        family="hazmat",
        name="Proposition 65",
        what_it_does=(
            "Warning and discharge requirements for chemicals on the OEHHA Prop "
            "65 list."
        ),
        jurisdiction="OEHHA lists; enforced by the AG, DAs, and private litigants",
        authority_source_url=(
            "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?"
            "lawCode=HSC&sectionNum=25249.6."
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-HAZMAT-PROP65",
                (
                    "Does the facility expose people to a Prop 65-listed chemical "
                    "above safe-harbor levels?"
                ),
                (
                    "Businesses with 10+ employees must warn before exposing "
                    "individuals to a listed chemical above its safe-harbor level."
                ),
            ),
        ),
        triggered_by=_has_chemicals,
    ),
    ProgramRegistryEntry(
        id="ca-title22-hazwaste",
        family="waste",
        name="California Hazardous Waste (Title 22, non-RCRA)",
        what_it_does=(
            "California-only hazardous wastes broader than federal RCRA "
            "(STLC/TTLC criteria)."
        ),
        jurisdiction="DTSC; administered by the local CUPA",
        authority_source_url="https://dtsc.ca.gov/non-rcra-hazardous-wastes/",
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-WASTE-CA-TITLE22",
                "Is the waste a California-only (non-RCRA) hazardous waste?",
                (
                    "A waste may be California hazardous under 22 CCR 66261.24 "
                    "(STLC/TTLC) even if not federally hazardous."
                ),
            ),
        ),
        triggered_by=_has_waste,
    ),
    ProgramRegistryEntry(
        id="ca-medical-waste",
        family="waste",
        name="Medical Waste Management Act",
        what_it_does=(
            "Registration and management of medical/biohazardous and sharps waste."
        ),
        jurisdiction="CDPH; enforced by the local enforcement agency",
        authority_source_url=(
            "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?"
            "lawCode=HSC&sectionNum=117600."
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-WASTE-MEDICAL",
                "Does the facility generate regulated medical waste?",
                (
                    "Generating 200 lb/month or more of medical waste makes a "
                    "facility a Large Quantity Generator requiring registration "
                    "and a management plan."
                ),
            ),
        ),
        triggered_by=_has_waste,
    ),
    ProgramRegistryEntry(
        id="ca-universal-waste",
        family="waste",
        name="Universal Waste (batteries, lamps, e-waste)",
        what_it_does=(
            "Streamlined management of universal wastes (batteries, lamps, "
            "electronics, mercury devices)."
        ),
        jurisdiction="DTSC; administered by the local CUPA",
        authority_source_url=(
            "https://dtsc.ca.gov/requirements-for-handlers-and-or-recyclers/"
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-WASTE-UNIVERSAL",
                "Does the facility accumulate universal waste?",
                (
                    "Batteries, lamps, electronic devices, and mercury devices "
                    "are managed under universal-waste handler standards (22 CCR "
                    "66273)."
                ),
            ),
        ),
        triggered_by=_has_waste,
    ),
    ProgramRegistryEntry(
        id="ca-title-v-permit",
        family="air",
        name="Federal Title V Operating Permit (CA air districts)",
        what_it_does=(
            "Consolidated operating permit for major stationary sources, issued "
            "by CA air districts."
        ),
        jurisdiction="US EPA delegated to the local air district",
        authority_source_url=(
            "https://ww2.arb.ca.gov/our-work/programs/"
            "federal-clean-air-act-title-v-operating-permits/fcaa-title-v-overview"
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-AIR-TITLE-V",
                (
                    "Is the facility a major source requiring a Title V operating "
                    "permit?"
                ),
                (
                    "Potential to emit >=100 tpy of a regulated pollutant (lower "
                    "in nonattainment; 10/25 tpy HAP) makes a source a Title V "
                    "major source."
                ),
            ),
        ),
        triggered_by=_has_equipment,
    ),
    ProgramRegistryEntry(
        id="ca-wdr-npdes",
        family="wastewater",
        name="NPDES Individual Permit / Waste Discharge Requirements (WDRs)",
        what_it_does=(
            "Regional Water Board permit for process wastewater discharged to "
            "surface water or land, not covered by the IGP or POTW pretreatment."
        ),
        jurisdiction="Regional Water Quality Control Board (one of 9)",
        authority_source_url=(
            "https://www.waterboards.ca.gov/water_issues/programs/"
            "waste_discharge_requirements/"
        ),
        authority_rank=1,
        hypotheses=(
            _hypothesis(
                "H-WASTEWATER-WDR",
                "Does the discharge require an individual NPDES permit or WDRs?",
                (
                    "Discharge of waste to waters of the state/US may require "
                    "WDRs (Porter-Cologne, Water Code 13260) or an individual "
                    "NPDES permit."
                ),
            ),
        ),
        triggered_by=_discharge_possible,
    ),
)


def all_programs() -> tuple[ProgramRegistryEntry, ...]:
    return PROGRAM_REGISTRY


def programs_for_family(family: str) -> tuple[ProgramRegistryEntry, ...]:
    return tuple(program for program in PROGRAM_REGISTRY if program.family == family)
