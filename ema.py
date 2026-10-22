"""Enterprise EMA login and API session.

EMA signs in through Auth0 and Microsoft in the browser, so a username/password token call
isn't possible. Like the Cypress EMA login (shared/login/login.ts), this opens the EMA login
page in a headless browser, signs in, then reads the session values the app stores in
sessionStorage. Everything after login is plain API calls.
"""
import json
import time
from urllib.parse import urlparse

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

import testData

LOGIN_TIMEOUT_MS = 60_000


def getEmaUrls(portalUrl, emaUrl=None):
    """Return the EMA web and API URLs.

    If emaUrl is given (e.g. https://ema-<env>-centralindia.siscompletedev.cloud/login), use it.
    Otherwise work them out from the Smart Portal URL (portalapp-web-<env>-... -> ema-<env>-...).
    """
    if emaUrl and emaUrl.strip():
        host = urlparse(emaUrl.strip()).hostname or ""
        if not host.startswith("ema-"):
            raise ValueError("The EMA URL should start with https://ema-…")
        return f"https://{host}", f"https://emaapi-{host[len('ema-'):]}/api"

    host = urlparse(portalUrl.strip()).hostname or ""
    if not host.startswith("portalapp-web-"):
        raise ValueError("The Smart Portal URL should start with https://portalapp-web-…")
    suffix = host[len("portalapp-web-"):]
    return f"https://ema-{suffix}", f"https://emaapi-{suffix}/api"


def _signInToMicrosoft(page, username, password, log):
    """Complete the Microsoft sign-in pages: pick or type the account, type the password, skip 'Stay signed in'."""
    accountTile = page.locator(f"[data-test-id='{username.lower()}']")
    emailInput = page.locator("input[type='email']")
    passwordInput = page.locator("input[name='passwd']")

    # Either an account picker (Cypress clicks the tile) or an email box appears first
    accountTile.or_(emailInput).or_(passwordInput).first.wait_for(timeout=LOGIN_TIMEOUT_MS)
    if accountTile.is_visible():
        log("  Microsoft: choosing account")
        accountTile.click()
    elif emailInput.is_visible():
        log("  Microsoft: entering email")
        emailInput.fill(username)
        page.locator("[type='submit']").click()

    log("  Microsoft: entering password")
    passwordInput.wait_for(timeout=LOGIN_TIMEOUT_MS)
    passwordInput.fill(password)
    page.locator("[type='submit']").click()

    # "Stay signed in?" prompt: answer No if it shows up
    noButton = page.locator("#idBtn_Back")
    try:
        noButton.wait_for(timeout=8_000)
        noButton.click()
    except PlaywrightTimeout:
        pass


def _isLoggedIn(page, emaUrl):
    """True once the browser is back on EMA (not the login page) and the app has stored its session."""
    return (page.url.startswith(emaUrl) and "/login" not in page.url
            and page.evaluate("() => !!sessionStorage.getItem('EnterpriseManagementSession')"))


def _waitForPage(page, checks, timeoutMs=LOGIN_TIMEOUT_MS):
    """Wait until one of the checks is true and return its name. Checks may fail while a page is loading."""
    deadline = time.monotonic() + timeoutMs / 1000
    while time.monotonic() < deadline:
        for name, check in checks.items():
            try:
                if check():
                    return name
            except Exception:
                pass
        page.wait_for_timeout(500)
    raise PlaywrightTimeout(f"EMA login didn't move on within {timeoutMs // 1000} seconds; stuck at {page.url.split('?')[0]}")


def _pickEnterprise(page, dropdown, enterpriseName):
    """Choose the enterprise in the login dropdown (orSelectEnterprise.selectEnterprise)."""
    dropdown.click()
    search = page.locator(".p-dropdown-filter-container input, .p-select-filter-container input")
    if search.count():
        search.first.fill(enterpriseName)
    page.locator("li").filter(has_text=enterpriseName).first.click()


def getEmaSessionStorage(emaUrl, enterpriseName, username, password, log=print, headless=True, screenshotPath=None):
    """Log in to EMA for one enterprise in a headless browser and return its sessionStorage values."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            log(f"EMA: opening {emaUrl}/login")
            # Some EMA background requests stay open, so don't wait for the full "load" event
            page.goto(f"{emaUrl}/login", wait_until="domcontentloaded", timeout=LOGIN_TIMEOUT_MS)

            # Email, then Login (orLogin.email / orLogin.loginButton)
            page.locator("[data-test-id='enterprise-login-email-input']").fill(username.lower())
            page.locator("[data-test-id='enterprise-login-submit-button']").click()

            # EMA may show the enterprise dropdown or send the browser to Microsoft first, and skips the
            # dropdown when the account has only one enterprise, so handle each page as it comes
            dropdown = page.locator("[data-test-id='enterprise-login-enterprise-selection-dropdown']")
            enterprisePicked, microsoftSignIns = False, 0
            while True:
                pages = {"loggedIn": lambda: _isLoggedIn(page, emaUrl)}
                if not enterprisePicked:
                    pages["dropdown"] = dropdown.is_visible
                if microsoftSignIns < 2:
                    pages["microsoft"] = lambda: page.url.startswith("https://login.microsoftonline.com")
                found = _waitForPage(page, pages)
                if found == "loggedIn":
                    break
                if found == "dropdown":
                    log(f"EMA: selecting enterprise {enterpriseName}")
                    _pickEnterprise(page, dropdown, enterpriseName)
                    enterprisePicked = True
                else:
                    _signInToMicrosoft(page, username, password, log)
                    microsoftSignIns += 1

            storage = page.evaluate("() => Object.fromEntries(Object.entries(sessionStorage))")
            selectedName = json.loads(storage.get("SELECTED_ENTERPRISE") or "{}").get("enterpriseName", "")
            if selectedName.casefold() != enterpriseName.casefold():
                raise RuntimeError(
                    f"EMA opened '{selectedName or 'no enterprise'}' instead of '{enterpriseName}'. "
                    f"{username} must be an admin of {enterpriseName}: run step 2 (Create) again, "
                    "which now adds the login account as an admin.")
            log(f"EMA: logged in to {enterpriseName}")
            return storage
        except Exception:
            if screenshotPath:
                page.screenshot(path=screenshotPath, full_page=True)
                log(f"EMA: login failed at {page.url}; screenshot saved to {screenshotPath}")
            raise
        finally:
            browser.close()


def createEmaSession(portalUrl, enterpriseName, username, password, log=print, headless=True, screenshotPath=None,
                     emaUrl=None):
    """Return a requests session for EMA API calls on one enterprise (Authorization, Token and Enterprise headers)."""
    emaUrl, emaApiBase = getEmaUrls(portalUrl, emaUrl)
    storage = getEmaSessionStorage(emaUrl, enterpriseName, username, password, log, headless, screenshotPath)

    authToken = storage.get("AuthToken", "")
    session = requests.Session()
    session.apiBase = emaApiBase
    session.headers["Authorization"] = authToken if authToken.startswith("Bearer ") else f"Bearer {authToken}"
    session.headers["Token"] = storage["EnterpriseManagementSession"]

    # The Enterprise header carries the selected enterprise ID, as in the Cypress EMA scenario
    selected = storage.get("SELECTED_ENTERPRISE")
    if selected:
        session.headers["Enterprise"] = str(json.loads(selected)["enterpriseId"])
        session.enterpriseId = int(session.headers["Enterprise"])
    session.storageKeys = sorted(storage)
    return session


# ---------- EMA setup steps (ema-precondition.sc.ts) ----------

def sendAndReport(session, method, path, label, body=None, log=print):
    """Send a request to the EMA API, log the outcome and return the response (None if it failed)."""
    response = session.request(method, f"{session.apiBase}/{path}", json=body)
    log(f"{label}: status {response.status_code} [{method} {response.request.url}]"
        + ("" if response.ok else f" {response.text}"))
    return response if response.ok else None


def getJson(session, path):
    response = session.get(f"{session.apiBase}/{path}")
    response.raise_for_status()
    return response.json()


def createBusinessProfiles(session, profiles=testData.BUSINESS_PROFILES, log=print):
    """Create each business profile (permission group) and set its 8 tracker permissions. Returns True if all succeeded."""
    ok = True
    for profileName, level in profiles.items():
        response = sendAndReport(session, "POST", "BusinessGroupPermissionGroups/v01/",
                                 f"Create business profile {profileName}",
                                 {"permissionGroupName": profileName, "permissionGroupId": 0}, log)
        if response is None:
            ok = False
            continue

        profileId = response.json()["permissionGroupId"]
        for typeEnum, typeName in testData.TRACKER_PERMISSIONS:
            ok &= sendAndReport(session, "PUT", f"BusinessGroupPermissionGroups/v01/{profileId}/Permission",
                                f"  {typeName} = level {level}",
                                {"permissionGroupId": profileId, "permissionTypeEnum": typeEnum,
                                 "permissionLevelEnum": level, "permissionTypeName": typeName},
                                log) is not None
    return ok


def createBusinessGroup(session, group, log=print):
    """Create one business group and select its organizations. Returns True if all calls succeeded."""
    response = sendAndReport(session, "POST", "BusinessGroupManagement/v01/Add/",
                             f"Create business group {group['name']}", {"name": group["name"]}, log)
    if response is None:
        return False

    groupId = response.json()["businessGroupId"]
    facilityMap = getJson(session, f"BusinessGroupManagement/v01/BusinessGroup/{groupId}")["facilityMap"]

    # Same as Cypress: drop facilities with a repeated name, then select the ones in the group's org list
    facilities, seenNames = [], set()
    for facility in facilityMap:
        name = facility["facilityName"].strip()
        if name not in seenNames:
            seenNames.add(name)
            facilities.append(facility)
    for facility in facilities:
        if facility["facilityName"] in group["orgs"]:
            facility["selected"] = True

    selectedCount = sum(1 for f in facilities if f.get("selected"))
    return sendAndReport(session, "PUT", "BusinessGroupManagement/v01/BusinessGroup/",
                         f"  Select {selectedCount} organizations",
                         {"businessGroupId": groupId, "name": group["name"],
                          "enterpriseId": session.headers["Enterprise"], "facilityMap": facilities},
                         log) is not None


def userPayload(email, userBusinessGroups):
    """Body for FacilityUsers/v01/User/Set, built fresh per user (sisAutomationUserPayload in Cypress)."""
    return {
        "userInfo": {
            "lastName": email.split("@")[0], "middleInitial": "", "title": "", "firstName": "sis",
            "usrId": 0, "personId": 0, "email": email, "originalEmail": "",
            "profileLevelId": 0, "profileLevelName": "",
        },
        "userDetails": {
            "primaryPhone": "", "faxNumber": "", "dateOfBirth": "", "stateLicense": "", "slEffDate": "",
            "slExpDate": "", "deaLicense": "", "deaEffDate": "", "deaExpDate": "", "taxonomy": "",
            "physicianGroupNumber": "", "npiNumber": "", "federalTaxID": "", "serviceLevelNames": [],
            "idpIdentifier": "",
        },
        "userBusinessGroups": userBusinessGroups,
        "officeDetails": {
            "name": "", "primaryPhone": "", "faxNumber": "", "address1": "", "address2": "",
            "city": "", "state": None, "zip": "", "county": "", "country": None,
        },
        "payerIdentifiers": {},
    }


def mapUsersToBusinessGroups(session, groups, emails=testData.USER_EMAILS, log=print):
    """Give every user all of the enterprise's business groups, each with its profile. Returns (mapped, failed)."""
    groupIds = {g["name"]: g["businessGroupId"] for g in getJson(session, "BusinessGroupManagement/v01/BusinessGroups/")}
    profileIds = {p["permissionGroupName"]: p["permissionGroupId"] for p in getJson(session, "BusinessGroupPermissionGroups/v01/")}

    userBusinessGroups = [
        {"userId": 0, "businessGroupId": groupIds[g["name"]], "permissionGroupIds": [profileIds[g["profile"]]]}
        for g in groups
    ]

    mapped = failed = 0
    for email in emails:
        if sendAndReport(session, "POST", "FacilityUsers/v01/User/Set", f"Map user {email}",
                         userPayload(email, userBusinessGroups), log):
            mapped += 1
        else:
            failed += 1
    return mapped, failed


def setEnterpriseLimits(session, recordLimit, businessGroupLimit, log=print):
    """Set the tracker record limit and business group facility limit. Returns True if it succeeded."""
    config = getJson(session, "EnterpriseConfiguration/v01/")[0]
    return sendAndReport(session, "PUT", "EnterpriseConfiguration/v01/",
                         f"Set record limit {recordLimit}, business group limit {businessGroupLimit}",
                         {"id": config["id"], "enterpriseId": config["enterpriseId"],
                          "trackerItemsLimit": recordLimit, "businessGroupFacilityLimit": businessGroupLimit,
                          "itemSelectionLimit": testData.ITEM_SELECTION_LIMIT,
                          "distributedJobExpirationTime": testData.DISTRIBUTED_JOB_EXPIRATION_TIME},
                         log) is not None


def setupEmaForEnterprise(session, enterpriseName, emails=testData.USER_EMAILS, log=print, limits=None):
    """Run the 4 EMA steps for one enterprise on an already logged-in EMA session. Returns a summary dict.

    limits: optional {"recordLimit": ..., "businessGroupLimit": ...} to override the test data values.
    """
    data = {**testData.EMA_ENTERPRISES[enterpriseName], **(limits or {})}
    profilesOk = createBusinessProfiles(session, log=log)
    groupsOk = sum(createBusinessGroup(session, group, log) for group in data["groups"])
    usersMapped, usersFailed = mapUsersToBusinessGroups(session, data["groups"], emails, log)
    limitsOk = setEnterpriseLimits(session, data["recordLimit"], data["businessGroupLimit"], log)
    return {
        "profilesCreated": profilesOk,
        "groupsCreated": groupsOk,
        "groupsFailed": len(data["groups"]) - groupsOk,
        "usersMapped": usersMapped,
        "usersFailed": usersFailed,
        "limitsSet": limitsOk,
    }


def describeResult(result):
    """One readable line for an EMA setup result. Says 'failed' only when something did."""
    parts = [
        "profiles created" if result["profilesCreated"] else "some profiles FAILED",
        f"{result['groupsCreated']} business groups",
        f"{result['usersMapped']} users mapped",
        "limits set" if result["limitsSet"] else "limits FAILED",
    ]
    if result["groupsFailed"]:
        parts.append(f"{result['groupsFailed']} business groups FAILED")
    if result["usersFailed"]:
        parts.append(f"{result['usersFailed']} users FAILED")
    allOk = result["profilesCreated"] and result["limitsSet"] and not result["groupsFailed"] and not result["usersFailed"]
    return ("done: " if allOk else "") + ", ".join(parts)


def setupEma(portalUrl, username, password, enterpriseNames=testData.EMA_ENTERPRISE_NAMES,
             emails=testData.USER_EMAILS, log=print, headless=True, limitsByName=None, emaUrl=None):
    """Log in to EMA for each enterprise and run its EMA setup. Returns {enterpriseName: summary or error}."""
    results = {}
    limitsByName = limitsByName or {}
    for enterpriseName in enterpriseNames:
        log(f"===== EMA: {enterpriseName} =====")
        try:
            session = createEmaSession(portalUrl, enterpriseName, username, password, log, headless, emaUrl=emaUrl)
            results[enterpriseName] = setupEmaForEnterprise(session, enterpriseName, emails, log,
                                                            limitsByName.get(enterpriseName))
        except Exception as error:
            log(f"EMA setup for {enterpriseName} stopped: {error}")
            results[enterpriseName] = {"error": str(error)}
        if "error" not in results[enterpriseName]:
            log(f"{enterpriseName}: {describeResult(results[enterpriseName])}")
    return results


# ---------- Run from the terminal ----------

def main():
    import argparse
    import os

    from dotenv import load_dotenv

    import app

    load_dotenv()
    parser = argparse.ArgumentParser(description="Set up Enterprise EMA preconditions for one team's users.")
    team = parser.add_mutually_exclusive_group(required=True)
    team.add_argument("--team", help="Saved team name (TEAM_<name> in .env), e.g. --team Pit-Crew")
    team.add_argument("--users", help="Comma-separated emails, e.g. --users user1@sisfirst.com,user2@sisfirst.com")
    parser.add_argument("enterprises", nargs="*", default=testData.EMA_ENTERPRISE_NAMES,
                        help="Enterprise names to set up (default: Atlanta, Central, California, Georgia, Florida)")
    parser.add_argument("--portal-url", default=os.environ.get("PORTAL_URL",
                        "https://portalapp-web-367287e2-centralindia.siscompletedev.cloud"))
    parser.add_argument("--show-browser", action="store_true", help="Show the browser during EMA login")
    args = parser.parse_args()

    emails = app.getTeamEmails(args.team, args.users)
    print(f"Team: {args.team or 'custom'} ({len(emails)} users)")
    results = setupEma(args.portal_url, os.environ["PORTAL_USER"], os.environ["PORTAL_PASSWORD"],
                       args.enterprises, emails, headless=not args.show_browser)

    print("\n===== Summary =====")
    for name, result in results.items():
        print(f"{'FAILED' if 'error' in result or result.get('groupsFailed') or result.get('usersFailed') or not result.get('limitsSet') else 'OK    '}  {name}: {result}")


if __name__ == "__main__":
    main()
