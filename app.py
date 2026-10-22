import os
import re
from urllib.parse import urlparse

import msal
import requests
from dotenv import dotenv_values, load_dotenv, set_key, unset_key

import testData

load_dotenv()  # reads settings from the .env file next to this script

TENANT_ID = "1f8aefe1-eac8-4532-9c55-115d46c686ee"
DEFAULT_PORTAL_URL = "https://portalapp-web-367287e2-centralindia.siscompletedev.cloud"

# Enterprises that must never be deleted
KEEP_ENTERPRISE_NAMES = {"DevEnterprise"}
KEEP_ENTERPRISE_IDS = {1}

# Users that must never be deleted (PROTECTED_USERS in .env, plus the .env login account; lowercase)
KEEP_USER_EMAILS = {email.casefold() for email in testData.envEmails("PROTECTED_USERS") + testData.envEmails("PORTAL_USER")}


# ---------- Login ----------

def getApiBase(portalUrl):
    """Turn the Smart Portal web URL into its API URL (portalapp-web-... -> portalapp-api-.../api)."""
    host = urlparse(portalUrl.strip()).hostname or ""
    if not host.startswith("portalapp-web-"):
        raise ValueError("The Smart Portal URL should start with https://portalapp-web-…")
    return f"https://{host.replace('portalapp-web-', 'portalapp-api-', 1)}/api"


def getEnvironmentId(portalUrl):
    """Return the environment ID from the portal URL, e.g. 367287e2 (used for tenant names)."""
    host = urlparse(portalUrl.strip()).hostname or ""
    return host.split("-")[2] if host.count("-") >= 3 else ""


def getAzureAdToken(username, password):
    """Sign in to Azure AD with the given username/password and return an access token."""
    client_id = os.environ["CLIENT_ID"].strip()
    app = msal.PublicClientApplication(client_id, authority=f"https://login.microsoftonline.com/{TENANT_ID}")
    result = app.acquire_token_by_username_password(username, password, scopes=[f"{client_id}/.default"])
    if "access_token" not in result:
        raise RuntimeError(f"Login failed: {result.get('error_description') or result.get('error')}")
    return result["access_token"]


def createPortalSession(portalUrl=DEFAULT_PORTAL_URL, username=None, password=None):
    """Return a requests session carrying the Azure AD token and the portal session ID."""
    session = requests.Session()
    session.apiBase = getApiBase(portalUrl)
    session.envId = getEnvironmentId(portalUrl)
    session.username = username or os.environ["PORTAL_USER"]
    session.headers["Authorization"] = (
        f"Bearer {getAzureAdToken(session.username, password or os.environ['PORTAL_PASSWORD'])}"
    )

    # Portal login: exchange the Azure AD token for a session ID, sent as the "token" header on every call
    response = session.get(f"{session.apiBase}/ActiveDirectoryAuthentication/v01/Login")
    response.raise_for_status()
    session.headers["token"] = response.json()
    return session


def enterpriseApi(session):
    return f"{session.apiBase}/EnterpriseManagement/v01/1"


def usersApi(session):
    return f"{session.apiBase}/Users/v01"


def getJson(session, url):
    """GET a URL and return the JSON body, failing on HTTP errors."""
    response = session.get(url)
    response.raise_for_status()
    return response.json()


def apiTag(response):
    """The call as [METHOD url], logged with each result so the log shows which API was hit."""
    return f"[{response.request.method} {response.request.url}]"


def deleteAndReport(session, url, label, log=print):
    """DELETE a URL, log the outcome and return True if it succeeded."""
    response = session.delete(url)
    log(f"Delete {label}: status {response.status_code} {apiTag(response)} {response.text}")
    return response.ok


# ---------- Enterprises ----------

def getEnterprises(session, log=print):
    """Return the list of all enterprises."""
    url = f"{enterpriseApi(session)}/EnterpriseNames/"
    enterprises = getJson(session, url)
    log(f"Enterprises ({len(enterprises)}): status 200 [GET {url}]")
    for enterprise in enterprises:
        log(f"  ID {enterprise['enterpriseId']}: {enterprise['enterpriseName']}")
    return enterprises


def shouldKeepEnterprise(enterprise):
    """True if this enterprise is protected and must not be deleted."""
    return (
        enterprise["enterpriseName"] in KEEP_ENTERPRISE_NAMES
        or enterprise["enterpriseId"] in KEEP_ENTERPRISE_IDS
    )


def deleteEnterprise(session, enterprise, log=print):
    """Delete one enterprise and log the result."""
    enterprise_id = enterprise["enterpriseId"]
    return deleteAndReport(
        session,
        f"{enterpriseApi(session)}/Enterprises/{enterprise_id}",
        f"enterprise {enterprise['enterpriseName']} (ID {enterprise_id})",
        log,
    )


def deleteEnterprises(session, log=print):
    """Delete every enterprise except the protected ones. Returns (deleted, failed) counts."""
    deleted = failed = 0
    for enterprise in getEnterprises(session, log):
        if not shouldKeepEnterprise(enterprise):
            if deleteEnterprise(session, enterprise, log):
                deleted += 1
            else:
                failed += 1
    return deleted, failed


# ---------- Users ----------

def getUsers(session, log=print):
    """Return the list of all users."""
    url = f"{usersApi(session)}/All"
    users = getJson(session, url)
    log(f"Users ({len(users)}): status 200 [GET {url}]")
    for user in users:
        log(f"  ID {user.get('userId')}: {user.get('email')}")
    return users


def shouldKeepUser(user, session=None):
    """True if this user is protected and must not be deleted. The account logged in for this session is protected too."""
    email = (user.get("email") or "").strip().casefold()
    loginUser = (getattr(session, "username", "") or "").strip().casefold()
    # Keep users with a missing email too, rather than risk deleting the wrong one
    return not email or email in KEEP_USER_EMAILS or email == loginUser


def deleteUser(session, user, log=print):
    """Delete one user and log the result."""
    label = f"user {user['email']} (ID {user['userId']})"

    # Last safety check: never delete a protected user, even if called directly
    if shouldKeepUser(user, session):
        log(f"Skip {label}: protected user")
        return False

    return deleteAndReport(session, f"{usersApi(session)}/{user['userId']}", label, log)


def isTeamUser(user, onlyEmails):
    """True if onlyEmails is None (everyone) or the user's email is in it, ignoring case."""
    if onlyEmails is None:
        return True
    return (user.get("email") or "").strip().casefold() in {e.strip().casefold() for e in onlyEmails}


def deleteUsers(session, log=print, onlyEmails=None):
    """Delete users except the protected ones. Returns (deleted, failed) counts.

    onlyEmails: delete only these users (e.g. one team); None deletes every unprotected user, like Cypress.
    """
    deleted = failed = 0
    for user in getUsers(session, log):
        if not shouldKeepUser(user, session) and isTeamUser(user, onlyEmails):
            if deleteUser(session, user, log):
                deleted += 1
            else:
                failed += 1
    return deleted, failed


# ---------- Create Smart Portal data ----------

def sendAndReport(session, method, url, label, body=None, log=print):
    """Send a request with an optional JSON body, log the outcome and return the response (None if it failed)."""
    response = session.request(method, url, json=body)
    log(f"{label}: status {response.status_code} {apiTag(response)}" + ("" if response.ok else f" {response.text}"))
    return response if response.ok else None


def createUsers(session, emails=testData.USER_EMAILS, log=print):
    """Add each email as a user with the default permission group, skipping active users. Returns (created, failed)."""
    activeEmails = {
        (user.get("email") or "").casefold()
        for user in getJson(session, f"{usersApi(session)}/All")
        if user.get("isActive")
    }
    created = failed = 0
    for email in emails:
        if email.casefold() in activeEmails:
            log(f"Skip user {email}: already active")
            continue

        response = sendAndReport(session, "POST", f"{usersApi(session)}/", f"Add user {email}",
                                 {"lastKnownGoodEmail": "", "email": email}, log)
        if response is None:
            failed += 1
            continue

        userId = response.json()["userId"]
        if sendAndReport(session, "PUT", f"{usersApi(session)}/{userId}/PermissionGroups",
                         f"  Default permission group for {email} (ID {userId})", [1], log):
            created += 1
        else:
            failed += 1
    return created, failed


def grantAccess(session, log=print):
    """Request access to tenants 1 and 2. Returns True if the server reports success."""
    response = sendAndReport(session, "POST", f"{session.apiBase}/SISComplete/v01/1/RequestGrantAccess",
                             f"Grant access to tenants {testData.TENANT_IDS}",
                             {"tenantIds": testData.TENANT_IDS, "accessDurationInDays": testData.GRANT_ACCESS_DAYS},
                             log)
    return response is not None and response.json().get("success") is True


def syncOrganizations(session, log=print):
    """Synchronize organization units for tenants 1 and 2. Returns True if all succeeded."""
    results = [
        sendAndReport(session, "POST",
                      f"{session.apiBase}/SISComplete_EnterpriseMaster_Sync/v01/1/Tenants/{tenantId}/OrganizationUnits/Synchronize",
                      f"Sync organizations for tenant {tenantId}", log=log)
        for tenantId in testData.TENANT_IDS
    ]
    return all(results)


def getTenantIds(enterpriseName):
    """Tenants to add to an enterprise: [1] or [2] for the single-tenant ones, otherwise [1, 2]."""
    if enterpriseName in testData.TENANT_ONE_ONLY:
        return [1]
    if enterpriseName in testData.TENANT_TWO_ONLY:
        return [2]
    return [1, 2]


def createEnterprise(session, enterpriseName, adminEmails=testData.USER_EMAILS, log=print, tenantIds=None):
    """Create one enterprise with its admin users, tenants and Auth0 IDP. Returns True if every call succeeded."""
    response = sendAndReport(session, "POST", f"{enterpriseApi(session)}/Enterprises/New/",
                             f"Create enterprise {enterpriseName}",
                             {"enterpriseType": 1, "enterpriseId": 1, "enterpriseName": enterpriseName}, log)
    if response is None:
        return False

    enterpriseId = response.json()["enterpriseId"]
    ok = True

    for email in adminEmails:
        ok &= sendAndReport(session, "POST", f"{enterpriseApi(session)}/EnterpriseAdminUsers/{enterpriseId}",
                            f"  Add admin {email}", {"email": email, "userId": 0}, log) is not None

    for tenantId in tenantIds or getTenantIds(enterpriseName):
        tenantName = f"{session.envId}t{tenantId}"
        ok &= sendAndReport(session, "POST", f"{enterpriseApi(session)}/AddTenant/",
                            f"  Add tenant {tenantName}",
                            {"enterpriseId": enterpriseId, "tenantId": tenantId, "tenantName": tenantName},
                            log) is not None

    ok &= sendAndReport(session, "POST", f"{enterpriseApi(session)}/Enterprises/{enterpriseId}/Register/",
                        f"  Register IDP {testData.AUTH0_DOMAIN}",
                        {"auth0Domain": testData.AUTH0_DOMAIN, "sISCompleteTenantName": "", "sISCompleteSiteUrl": "",
                         "sISCompleteAPIUrl": "", "pPESiteUrl": "", "pPEPhysicianSiteUrl": ""},
                        log) is not None
    return ok


def createSmartPortalData(session, emails=testData.USER_EMAILS, enterpriseNames=testData.ENTERPRISE_NAMES, log=print,
                          tenantsByName=None):
    """Run all Smart Portal precondition steps in Cypress order. Returns a summary dict."""
    usersCreated, usersFailed = createUsers(session, emails, log)
    accessGranted = grantAccess(session, log)
    orgsSynced = syncOrganizations(session, log)
    tenantsByName = tenantsByName or {}
    # The login account must be an admin too: EMA setup logs in with it, and EMA only offers its own enterprises
    adminEmails = list(emails)
    if session.username.casefold() not in {e.casefold() for e in adminEmails}:
        adminEmails.append(session.username)
    enterprisesOk = [name for name in enterpriseNames
                     if createEnterprise(session, name, adminEmails, log, tenantsByName.get(name))]
    return {
        "usersCreated": usersCreated,
        "usersFailed": usersFailed,
        "accessGranted": accessGranted,
        "organizationsSynced": orgsSynced,
        "enterprisesCreated": len(enterprisesOk),
        "enterprisesFailed": len(enterpriseNames) - len(enterprisesOk),
    }


# ---------- Main ----------

STEPS = ["delete", "create", "ema"]
TEAM_PREFIX = "TEAM_"


def teamSettingName(teamName):
    """The .env setting for a team, e.g. "Pit Crew" -> TEAM_Pit_Crew."""
    return TEAM_PREFIX + re.sub(r"[^A-Za-z0-9]+", "_", teamName.strip()).strip("_")


def loadTeams():
    """Saved teams from .env (TEAM_<name>=email1,email2): {team name: [emails]}. Read fresh, so saves show at once."""
    return {
        key[len(TEAM_PREFIX):].replace("_", " "): [e.strip() for e in (value or "").split(",") if e.strip()]
        for key, value in dotenv_values(testData.ENV_FILE).items()
        if key.startswith(TEAM_PREFIX) and len(key) > len(TEAM_PREFIX)
    }


def saveTeam(teamName, emails):
    """Save a team to .env, replacing a team with the same name."""
    set_key(testData.ENV_FILE, teamSettingName(teamName), ",".join(emails), quote_mode="never")


def deleteTeam(teamName):
    """Remove a team from .env."""
    unset_key(testData.ENV_FILE, teamSettingName(teamName), quote_mode="never")


def getTeamEmails(teamName=None, users=None):
    """Return the team's emails from --users (comma separated) or --team (a TEAM_<name> setting in .env)."""
    if users:
        emails = [e.strip() for e in users.split(",") if e.strip()]
    else:
        teams = loadTeams()
        wanted = teamSettingName(teamName or "").casefold()
        match = next((name for name in teams if teamSettingName(name).casefold() == wanted), None)
        if not match:
            raise SystemExit(f"Team '{teamName}' not found. Saved teams: {', '.join(teams) or 'none'}")
        emails = teams[match]
    if not emails:
        raise SystemExit("The team has no users.")
    return emails


def parseArgs():
    import argparse

    parser = argparse.ArgumentParser(
        description="Reset Smart Portal and EMA test data for one team: delete old data, create Smart Portal data, "
                    "set up EMA. Only the team's users are deleted, created and mapped.")
    team = parser.add_mutually_exclusive_group(required=True)
    team.add_argument("--team", help="Saved team name (TEAM_<name> in .env), e.g. --team Pit-Crew")
    team.add_argument("--users", help="Comma-separated emails, e.g. --users user1@sisfirst.com,user2@sisfirst.com")
    parser.add_argument("--only", nargs="+", choices=STEPS, help="Run only these steps, e.g. --only ema")
    parser.add_argument("--skip", nargs="+", choices=STEPS, default=[], help="Skip these steps, e.g. --skip delete")
    parser.add_argument("--portal-url", default=os.environ.get("PORTAL_URL", DEFAULT_PORTAL_URL),
                        help="Smart Portal URL of the environment (default: PORTAL_URL in .env, else 367287e2 dev)")
    parser.add_argument("--show-browser", action="store_true", help="Show the browser during EMA login")
    return parser.parse_args()


def main():
    import ema

    args = parseArgs()
    emails = getTeamEmails(args.team, args.users)
    steps = [step for step in (args.only or STEPS) if step not in args.skip]
    username, password = os.environ["PORTAL_USER"], os.environ["PORTAL_PASSWORD"]
    summary = {}

    print(f"Environment {getEnvironmentId(args.portal_url)}  |  team: {args.team or 'custom'} "
          f"({len(emails)} users)  |  steps: {', '.join(steps)}")
    session = createPortalSession(args.portal_url, username, password)

    # 1. delete all test enterprises, and the team's users (protected users are always kept)
    if "delete" in steps:
        print("\n===== 1. Delete old test data =====")
        enterprisesDeleted, enterprisesFailed = deleteEnterprises(session)
        usersDeleted, usersFailed = deleteUsers(session, onlyEmails=emails)
        summary["Delete"] = (f"{enterprisesDeleted} enterprises, {usersDeleted} users deleted  |  "
                             f"{enterprisesFailed + usersFailed} failed")
        if enterprisesFailed + usersFailed:
            # Old data is still there; creating now would make duplicates
            steps = ["delete"]
            summary["Stopped"] = "some deletes failed, so create and EMA were not run"

    # 2. create smart portal data
    if "create" in steps:
        print("\n===== 2. Create Smart Portal data =====")
        result = createSmartPortalData(session, emails)
        summary["Smart Portal"] = (
            f"{result['usersCreated']} users, {result['enterprisesCreated']} enterprises created  |  "
            f"{result['usersFailed'] + result['enterprisesFailed']} failed  |  "
            f"grant access {'OK' if result['accessGranted'] else 'FAILED'}  |  "
            f"org sync {'OK' if result['organizationsSynced'] else 'FAILED'}"
        )
        if result["enterprisesFailed"]:
            # EMA login needs every enterprise and its IDP to exist
            steps = [step for step in steps if step != "ema"]
            summary["Stopped"] = "some enterprises failed to create, so EMA was not run"

    # 3. set up EMA for the State enterprises
    if "ema" in steps:
        print("\n===== 3. Set up EMA =====")
        results = ema.setupEma(args.portal_url, username, password, emails=emails, headless=not args.show_browser)
        summary["EMA"] = "  |  ".join(
            f"{'OK' if isEmaOk(result) else 'FAILED'} {name.replace(' State Enterprise', '')}"
            for name, result in results.items()
        )

    print("\n===== Summary =====")
    for step, text in summary.items():
        print(f"{step + ':':<14}{text}")


def isEmaOk(result):
    """True if an EMA setup result has no error and nothing failed."""
    return ("error" not in result and result["profilesCreated"] and not result["groupsFailed"]
            and not result["usersFailed"] and result["limitsSet"])


if __name__ == "__main__":
    main()
