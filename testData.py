"""Smart Portal precondition test data.

Copied from SISDomainsAutomation/cypress/fixtures/shared/precondition.td.ts
(tdUserMailList, tdEnterprisesList, tdToneTenantEnterprise, tdTtwoTenantEnterprise).

Emails are sensitive, so they are never kept in code: they come from the .env file.
"""
import os

from dotenv import load_dotenv

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(ENV_FILE)


def envEmails(name):
    """Emails from a comma-separated .env setting, e.g. DEFAULT_USERS=a@company.com,b@company.com."""
    return [email.strip() for email in (os.environ.get(name) or "").split(",") if email.strip()]


# Users created in Smart Portal and added as admins to every enterprise (DEFAULT_USERS in .env)
USER_EMAILS = envEmails("DEFAULT_USERS")

# Enterprises created in Smart Portal, in Cypress order
ENTERPRISE_NAMES = [
    "Atlanta State Enterprise",
    "Central State Enterprise",  # RecordLimit Enterprise
    "California State Enterprise",
    "Georgia State Enterprise",
    "Florida State Enterprise",  # Single Business Enterprise
    "ConfigManagement Enterprise",  # Single Tenant Enterprise (tenant 1 only)
    "SingleTenant Enterprise",  # Single Tenant Enterprise (tenant 2 only)
]

# Enterprises that get only one tenant; all others get tenants 1 and 2
TENANT_ONE_ONLY = {"ConfigManagement Enterprise"}
TENANT_TWO_ONLY = {"SingleTenant Enterprise"}

# Tenants used for grant access and organization sync
TENANT_IDS = [1, 2]
GRANT_ACCESS_DAYS = 14

# IDP registered on every enterprise (hard-coded in the Cypress spec)
AUTH0_DOMAIN = "siscomplete-dev.us.auth0.com"


# ---------- Enterprise EMA ----------

# Tracker permissions set on every business profile: (permissionTypeEnum, permissionTypeName)
TRACKER_PERMISSIONS = [
    (8, "Trackers: Coding/Charge Entry"),
    (9, "Trackers: Cases To Code"),
    (10, "Trackers: Revenue Cycle Management"),
    (11, "Trackers: Charge Entry"),
    (12, "Trackers: Remittance Posting"),
    (13, "Trackers: Insurance Billing"),
    (14, "Trackers: Financial Clearance"),
    (25, "Trackers: Balance Reconciliation"),
]

# Business profiles (EMA permission groups) and their permission level: 3 = full, 2 = view, 1 = none
FULL_PROFILE = "systemAdministrator"
VIEW_PROFILE = "ViewSystemPermission"
NONE_PROFILE = "NoneSystemPermission"
BUSINESS_PROFILES = {FULL_PROFILE: 3, VIEW_PROFILE: 2, NONE_PROFILE: 1}

# Organizations selected in business groups
ALL_ORGS = [
    "Ambulatory Surgery Center East Side",
    "Internal",
    "Sales",
    "ASC - For Adult Learning",
    "CBO_Eligibility01",
    "Gem_Org001",  # These org can be used while working in stories
    "Gem_Org002",
    "Gem_Org003",
    "Gem_Org004",
    "Gem_Org005",
    "Gem_Org006",
    "Gem_Org007",
    "Gem_Org008",
    "Gem_Org009",
    "Gem_Org010",
    "Gem_Org011",
    "Gem_Org012",
    "Gem_Org021",
    "Gem_Org014",
]
CALIFORNIA_ORGS = ["Gem_Org001", "Gem_Org002", "Gem_Org003", "Gem_Org004", "Gem_Org005"]


def businessGroup(name, profile=FULL_PROFILE, orgs=ALL_ORGS):
    return {"name": name, "profile": profile, "orgs": orgs}


# EMA setup per enterprise: business groups, record limit and business group facility limit
EMA_ENTERPRISES = {
    "Atlanta State Enterprise": {
        "groups": [businessGroup(f"Atlanta {side} Business Group") for side in ("East", "West", "North", "South")],
        "recordLimit": 10000, "businessGroupLimit": 15,
    },
    "Central State Enterprise": {  # RecordLimit Enterprise
        "groups": [businessGroup(f"Central {side} Business Group") for side in ("East", "West", "North", "South")],
        "recordLimit": 6, "businessGroupLimit": 15,
    },
    "California State Enterprise": {
        "groups": [
            businessGroup("California East Business Group"),
            businessGroup("California West Business Group", orgs=CALIFORNIA_ORGS),
            businessGroup("California North Business Group"),
            businessGroup("California South Business Group"),
        ],
        "recordLimit": 10000, "businessGroupLimit": 5,
    },
    "Georgia State Enterprise": {
        "groups": [
            businessGroup("Georgia East Business Group", NONE_PROFILE),
            businessGroup("Georgia West Business Group", VIEW_PROFILE),
            businessGroup("Georgia North Business Group"),
            businessGroup("Georgia South Business Group"),
        ],
        "recordLimit": 10000, "businessGroupLimit": 15,
    },
    "Florida State Enterprise": {  # Single Business Enterprise
        "groups": [businessGroup("Florida South Business Group")],
        "recordLimit": 10000, "businessGroupLimit": 15,
    },
    # ConfigManagement and SingleTenant have test data in Cypress but no EMA spec runs them
    "ConfigManagement Enterprise": {
        "groups": [businessGroup(f"ConfigManagement {side} Business Group") for side in ("East", "West")],
        "recordLimit": 10000, "businessGroupLimit": 15,
    },
    "SingleTenant Enterprise": {
        "groups": [businessGroup(f"SingleTenant {side} Business Group") for side in ("East", "West")],
        "recordLimit": 10000, "businessGroupLimit": 15,
    },
}

# Enterprises the Cypress EMA specs actually run (ema-atlanta/central/california/georgia/florida)
EMA_ENTERPRISE_NAMES = [
    "Atlanta State Enterprise",
    "Central State Enterprise",
    "California State Enterprise",
    "Georgia State Enterprise",
    "Florida State Enterprise",
]

# Fixed values the Cypress EMA scenario sends when setting limits
ITEM_SELECTION_LIMIT = 152
DISTRIBUTED_JOB_EXPIRATION_TIME = 3600
