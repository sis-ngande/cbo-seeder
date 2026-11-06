from urllib.parse import urlparse

import msal
import requests
from dotenv import load_dotenv

import testData

load_dotenv(testData.ENV_FILE)  # reads settings from the .env file next to this script

TENANT_ID = "1f8aefe1-eac8-4532-9c55-115d46c686ee"
CLIENT_ID = "090066bd-d788-4f22-922e-bb51d26b3619"  # Smart Portal's Azure AD app (public, not a secret)

# Enterprises that must never be deleted
KEEP_ENTERPRISE_NAMES = {"DevEnterprise"}
KEEP_ENTERPRISE_IDS = {1}

# Users that must never be deleted (lowercase). The logged-in account is always kept too.
KEEP_USER_EMAILS = {email.casefold() for email in testData.PROTECTED_USER_EMAILS}


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
    app = msal.PublicClientApplication(CLIENT_ID, authority=f"https://login.microsoftonline.com/{TENANT_ID}")
    result = app.acquire_token_by_username_password(username, password, scopes=[f"{CLIENT_ID}/.default"])
    if "access_token" not in result:
        raise RuntimeError(f"Login failed: {result.get('error_description') or result.get('error')}")
    return result["access_token"]


def createPortalSession(portalUrl, username, password):
    """Return a requests session carrying the Azure AD token and the portal session ID.

    The password comes from the page's login form and is never saved."""
    session = requests.Session()
    session.apiBase = getApiBase(portalUrl)
    session.envId = getEnvironmentId(portalUrl)
    session.username = username
    session.headers["Authorization"] = f"Bearer {getAzureAdToken(username, password)}"

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

def findUsers(session, emails, log=print):
    """Return {typed email (lowercase): [its Smart Portal users]} for the typed emails only.

    The API has no lookup by email, so this reads the user list once to get the IDs, keeps only the typed emails
    and drops everyone else straight away: other users are never logged, counted or kept."""
    wanted = {e.strip().casefold() for e in emails}
    url = f"{usersApi(session)}/All"
    found = {}
    for user in getJson(session, url):
        email = (user.get("email") or "").strip().casefold()
        if email in wanted:
            found.setdefault(email, []).append(user)
    log(f"Look up {len(wanted)} typed users: {len(found)} already exist: status 200 [GET {url}]")
    return found


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


def deleteUsers(session, log=print, onlyEmails=()):
    """Delete only the given users (the team typed on the page), never protected ones. Returns (deleted, failed) counts."""
    deleted = failed = 0
    for users in findUsers(session, onlyEmails, log).values():
        for user in users:
            if shouldKeepUser(user, session):
                continue
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


def createUsers(session, emails=(), log=print):
    """Create each typed email as a fresh user with the default permission group. Returns (created, failed).

    A user that already exists is deleted first, then created again. Protected users and the login account are
    never deleted: an active one is kept as it is."""
    existing = findUsers(session, emails, log)
    created = failed = 0
    for email in emails:
        matches = existing.get(email.strip().casefold(), [])
        if any(shouldKeepUser(user, session) for user in matches):
            if any(user.get("isActive") for user in matches):
                log(f"Skip user {email}: protected, kept as it is")
                continue
        elif matches:
            log(f"User {email} already exists: deleting it first")
            if not all([deleteUser(session, user, log) for user in matches]):
                failed += 1
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


def createEnterprise(session, enterpriseName, adminEmails=(), log=print, tenantIds=None):
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


def createSmartPortalData(session, emails=(), enterpriseNames=testData.ENTERPRISE_NAMES, log=print,
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


# ---------- Results ----------

def isEmaOk(result):
    """True if an EMA setup result has no error and nothing failed."""
    return ("error" not in result and result["profilesCreated"] and not result["groupsFailed"]
            and not result["usersFailed"] and result["limitsSet"])

