import os


SOURCES = {
    "UNSC": "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
    "OFAC_SDN": "https://www.treasury.gov/ofac/downloads/sdn.csv",
    "OFAC_NON_SDN": "https://www.treasury.gov/ofac/downloads/consolidated/cons_prim.csv",
    "UK": "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.csv",
    "EU": "https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw",
    "WORLD_BANK": "https://www.worldbank.org/en/projects-operations/procurement/debarred-firms",
    "UNGM": os.environ.get("UNGM_API_URL", "").strip(),
}

SOURCE_PAGES = {
    "UNSC": "https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list",
    "OFAC_SDN": "https://sanctionslist.ofac.treas.gov/Home/SdnList",
    "OFAC_NON_SDN": "https://sanctionslist.ofac.treas.gov/Home/ConsolidatedList",
    "UK": "https://www.gov.uk/government/publications/the-uk-sanctions-list",
    "EU": "https://webgate.ec.europa.eu/fsd/fsf/#!/files",
    "WORLD_BANK": "https://www.worldbank.org/en/projects-operations/procurement/debarred-firms",
    "UNGM": "https://www.ungm.org/",
}

SOURCE_DETAILS = {
    "UNSC": {
        "title": "UN Security Council Consolidated List",
        "description": "Individuals and entities subject to UN Security Council sanctions.",
        "access": "Public",
    },
    "OFAC_SDN": {
        "title": "US Specially Designated Nationals (SDN) List",
        "description": "Specially Designated Nationals and Blocked Persons published by OFAC.",
        "access": "Public",
    },
    "OFAC_NON_SDN": {
        "title": "US Office of Foreign Assets Control (OFAC) Consolidated List",
        "description": "OFAC consolidated non-SDN sanctions data, including aliases and addresses.",
        "access": "Public",
    },
    "UK": {
        "title": "UK Sanctions List",
        "description": "Current UK designations published by the Foreign, Commonwealth & Development Office.",
        "access": "Public",
    },
    "EU": {
        "title": "EU Consolidated Financial Sanctions List",
        "description": "Persons, groups and organizations subject to EU financial sanctions.",
        "access": "Public",
    },
    "WORLD_BANK": {
        "title": "World Bank Ineligible Firms and Individuals",
        "description": "Debarred and cross-debarred firms and individuals from the World Bank list.",
        "access": "Public",
    },
    "UNGM": {
        "title": "UNGM Ineligibility List",
        "description": "UNGM ineligibility records; integration requires an authorized endpoint and token.",
        "access": "Restricted",
    },
}
