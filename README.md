# ⚡ CBO Seeder

**Automated precondition seeder for Smart Portal and Enterprise EMA.**

CBO Seeder drives the Smart Portal and EMA REST APIs to reset the test data that the CBO automation tests depend on: it deletes old test data, creates users and enterprises in Smart Portal, then sets up business profiles, business groups, user mappings and limits in EMA. It replaces the Cypress precondition specs in `SISDomainsAutomation/cypress/e2e/qc/shared/cbo-precondition/` and runs the same API calls, with a browser only for the EMA login.

> Step 1 deletes data in a shared environment and can't be undone. Check with your team before you run it.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Launcher Commands](#launcher-commands)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Modes of Operation](#modes-of-operation)
  - [Web Page](#web-page)
  - [Terminal](#terminal)
- [Workflow Pipeline](#workflow-pipeline)
  - [The Three Steps](#the-three-steps)
  - [Per-Enterprise EMA Flow](#per-enterprise-ema-flow)
  - [Safety Rules](#safety-rules)
- [Modules](#modules)
  - [Smart Portal (app.py)](#smart-portal-apppy)
  - [EMA (ema.py)](#ema-emapy)
  - [Test Data (testData.py)](#test-data-testdatapy)
  - [Web Page (ui.py)](#web-page-uipy)
- [How Login Works](#how-login-works)
- [API Endpoints Hit](#api-endpoints-hit)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)

---

## Features

- **Three-step reset**: delete old test data, create Smart Portal data, set up EMA. Run all three in order, or one at a time
- **Team-scoped**: only the users of the chosen team are deleted, re-created and mapped. Other users are left alone
- **Pick only what your story needs**: choose which enterprises to create and set up in EMA, their tenants, record limit and business group limit
- **Saved teams**: save a user list as a team, pick it later from a list, delete it with one click
- **Live Output Log**: every API call with its method, endpoint, status and duration, updated live during a run, with filter, auto-scroll, copy and clear
- **Safe by default**: DevEnterprise, protected users and the logged-in account are never deleted; a confirmation is required before deleting; a run stops when a step leaves the data unsafe for the next one
- **Fresh login per step**: each step logs in again, so long runs don't hit an expired token
- **Emails stay private**: every email lives in `.env`, never in code or git
- **Web page or terminal**: the same steps run from the browser or the command line

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.12+ (tested on 3.14) |
| Web page | Streamlit |
| HTTP client | requests |
| Smart Portal login | MSAL (Azure AD username/password flow) |
| EMA login | Playwright with headless Chromium |
| Tables | pandas |
| Settings | python-dotenv (`.env`) |

---

## Getting Started

### Prerequisites

- **Python** 3.12 or later
- Access to the Smart Portal environment, and the values for `.env` (ask the team)

### Installation

```powershell
git clone <repository-url>
cd pythonProject-cbo
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
copy .env.example .env
```

Then open `.env` and fill in the values (see [Environment Variables](#environment-variables)). They are not stored in the code or in git.

### Running

```powershell
python run cbo                 # open the web page
python run cbo --port 8600     # open the web page on another port
```

The page opens at **http://localhost:8501** (or the port you give).

---

## Launcher Commands

`python run cbo` always uses the project's `.venv`, even when started with the global `python`. `.\run` (run.bat) does the same.

| Command | Description |
|---------|-------------|
| `python run cbo` | Open the web page on port 8501 |
| `python run cbo --port 8600` | Open the web page on another port |
| `python run cbo --team pitCrew` | Run all 3 steps in the terminal for a saved team |
| `python run cbo --users user1@sisfirst.com,user2@sisfirst.com` | Run all 3 steps for these users |
| `python run cbo --team pitCrew --only ema` | Run only some steps (`delete`, `create`, `ema`) |
| `python run cbo --team pitCrew --skip delete` | Skip steps, e.g. create + EMA and keep existing data |
| `python run cbo --team pitCrew --portal-url <url>` | Use another environment |
| `python run cbo --team pitCrew --show-browser` | Watch the EMA logins |
| `python run cbo --help` | List the terminal options |
| `python ema.py --team pitCrew "Atlanta State Enterprise"` | EMA setup for one enterprise |
| `.\run`, `.\run --port 8600`, `.\run --only ema` | The same, through run.bat |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│             Web page (ui.py, Streamlit)  or  Terminal         │
│  Environment · Team users · Enterprises · Run · Output Log    │
└───────────────┬──────────────────────────────┬───────────────┘
                │                              │
┌───────────────▼──────────────┐  ┌────────────▼───────────────┐
│  app.py  (Smart Portal)      │  │  ema.py  (Enterprise EMA)  │
│                              │  │                            │
│  Login: Azure AD (MSAL)      │  │  Login: headless Chromium  │
│   → portal session ID        │  │   → Auth0 → Microsoft      │
│                              │  │   → session from the page  │
│  1. Delete enterprises/users │  │                            │
│  2. Create users, grant      │  │  3. Business profiles      │
│     access, sync orgs,       │  │     Business groups + orgs │
│     enterprises + admins,    │  │     Map users to groups    │
│     tenants, Auth0 IDP       │  │     Record / group limits  │
└───────────────┬──────────────┘  └────────────┬───────────────┘
                │                              │
                │      testData.py  (enterprises, groups, limits)
                │      .env         (login, emails, teams)
                │                              │
┌───────────────▼──────────────┐  ┌────────────▼───────────────┐
│  Smart Portal API            │  │  EMA API                   │
│  portalapp-api-<env>/api     │  │  emaapi-<env>/api          │
└──────────────────────────────┘  └────────────────────────────┘
```

---

## Project Structure

```
pythonProject-cbo/
├── run                  # Launcher: python run cbo [options]; always uses .venv
├── run.bat              # Same launcher for .\run
├── app.py               # Smart Portal login, steps 1 and 2, saved teams, terminal command
├── ema.py               # EMA browser login and step 3
├── testData.py          # Enterprises, tenants, profiles, business groups, limits (no emails)
├── ui.py                # Streamlit web page
├── requirements.txt     # Python packages
├── .env.example         # Template for .env (no values)
├── .env                 # Your login, emails and teams (not in git)
├── .streamlit/
│   └── config.toml      # Page theme (colors, font, radius)
├── localSettings.json   # Recent environments on this machine (not in git)
└── .gitignore
```

---

## Modes of Operation

### Web Page

1. **Environment**: enter the Smart Portal URL, EMA URL (optional, worked out from the portal URL), username and password, then click **Connect**. Once connected, the card folds to one line (environment, tenants, EMA, user); open **Change environment or account** to switch. The rest of the page appears only after a successful connect.
2. **Team users**: choose a saved team from the list (each has a delete icon), or paste emails, one per line. **Save as team** stores the list in `.env`. Changing the team resets the enterprises, previous results and the confirmation.
3. **Enterprises**: tick **Create** for each enterprise your story needs. Ticking Create also ticks **EMA** and the enterprise's default tenants; you can still change tenants, record limit and group limit. Nothing is ticked at first.
4. **Run**: tick the confirmation, then click **Run all 3 steps**, or run one step (**1 · Delete**, **2 · Create**, **3 · EMA**). A progress bar shows the current step, and each step's tile shows Done or Failed when it finishes.
5. **Output Log**: appears after the first run. One row per line with **Time, Method, API, Message, Status, Duration**. Passed results show green, failures red. Filter by API, method, status or text; **Copy** copies the visible lines; **Clear** empties the log (off while a run is going). The same lines are printed in the terminal.

Team users and Enterprises sit side by side to save scrolling.

### Terminal

Every run is for one team: a saved team name (a `TEAM_<name>` line in `.env`, upper/lower case ignored) or a list of emails. Only those users are deleted, created and mapped. A summary is printed at the end. If a delete fails, create and EMA don't run; if an enterprise fails to create, EMA doesn't run.

```powershell
python run cbo --team pitCrew                                  # all 3 steps for a saved team
python run cbo --users user1@sisfirst.com,user2@sisfirst.com   # all 3 steps for these users
python run cbo --team pitCrew --only ema                       # only EMA setup
```

The terminal runs all enterprises from `testData.py`; choosing enterprises is on the web page.

---

## Workflow Pipeline

### The Three Steps

| Step | What it does | Replaces Cypress spec |
|---|---|---|
| **1. Delete old test data** | Deletes every enterprise except DevEnterprise, and the team's users (never protected users or the logged-in account) | `delete-smartportal-precondition.spec.ts` |
| **2. Create Smart Portal data** | Adds the team's users (skipping already active ones) with the default permission group, grants access to tenants 1 and 2 for 14 days, syncs organizations for both tenants, then creates each chosen enterprise with its admins (the team plus the login account), tenants and the Auth0 IDP | `smartportal-precondition.spec.ts` |
| **3. Set up EMA** | For each chosen enterprise: logs in to EMA, creates 3 business profiles, the business groups with their organizations, maps the team's users to the groups, and sets the limits | `ema-atlanta/central/california/georgia/florida-enterprise.spec.ts` |

Step 1 deletes **all** test enterprises (they're shared and re-created in step 2), but only the team's users.

### Per-Enterprise EMA Flow

```
Open EMA login → enter email → (Microsoft sign-in / pick enterprise, in whatever order EMA asks)
    → check EMA opened the right enterprise → read the session from the page
        → 3 business profiles × 8 tracker permissions
        → business groups → select their organizations
        → map every team user to all groups with the group's profile
        → set record limit and business group limit
```

| Business profile | Permission level on all 8 trackers |
|---|---|
| `systemAdministrator` | 3, full |
| `ViewSystemPermission` | 2, view |
| `NoneSystemPermission` | 1, none |

| Enterprise | Business groups | Record limit | Group limit |
|---|---|---|---|
| Atlanta State Enterprise | East, West, North, South | 10000 | 15 |
| Central State Enterprise | East, West, North, South | 6 | 15 |
| California State Enterprise | East, West (5 orgs), North, South | 10000 | 5 |
| Georgia State Enterprise | East (none), West (view), North, South | 10000 | 15 |
| Florida State Enterprise | South | 10000 | 15 |
| ConfigManagement Enterprise | East, West (tenant 1 only) | 10000 | 15 |
| SingleTenant Enterprise | East, West (tenant 2 only) | 10000 | 15 |

### Safety Rules

- **DevEnterprise** (ID 1) is never deleted.
- **Users in `PROTECTED_USERS`**, the `.env` login account, and the account logged in on the page are never deleted. Users without an email are kept too.
- **Only the team's users** are deleted; everyone else is left alone.
- **Confirmation**: the page requires ticking "I checked with my team…" before step 1 can run.
- **Wrong enterprise guard**: if EMA opens a different enterprise than the one asked for (for example because the login account isn't its admin), EMA setup stops instead of changing the wrong enterprise.
- **Stop on unsafe state**: if a step fails in a way that leaves the data unsafe, the next steps don't run.

---

## Modules

### Smart Portal (app.py)

| Function | Description |
|----------|-------------|
| `createPortalSession(portalUrl, username, password)` | Azure AD token, then a portal session ID; returns a `requests` session with both headers |
| `deleteEnterprises(session, log)` | Lists enterprises and deletes every unprotected one |
| `deleteUsers(session, log, onlyEmails)` | Deletes the team's users, skipping protected users and the login account |
| `createUsers(session, emails, log)` | Adds users that aren't active yet, with the default permission group |
| `grantAccess(session, log)` | Requests access to tenants 1 and 2 |
| `syncOrganizations(session, log)` | Syncs organization units for tenants 1 and 2 |
| `createEnterprise(session, name, adminEmails, log, tenantIds)` | Creates one enterprise with admins, tenants and the Auth0 IDP |
| `createSmartPortalData(...)` | Runs step 2 in Cypress order and returns a summary |
| `loadTeams()`, `saveTeam()`, `deleteTeam()` | Read, add and remove `TEAM_<name>` lines in `.env` |
| `main()` | The terminal command (`--team`, `--users`, `--only`, `--skip`, `--portal-url`, `--show-browser`) |

Every call is logged as `label: status NNN [METHOD url]`, which the Output Log splits into columns.

### EMA (ema.py)

| Function | Description |
|----------|-------------|
| `getEmaUrls(portalUrl, emaUrl)` | Works out the EMA web and API URLs from the portal URL |
| `getEmaSessionStorage(...)` | Logs in with headless Chromium and returns the page's session values |
| `createEmaSession(...)` | Returns a `requests` session with `Authorization`, `Token` and `Enterprise` headers |
| `createBusinessProfiles(session, ...)` | Creates the 3 profiles and sets their 8 tracker permissions |
| `createBusinessGroup(session, group, log)` | Creates a group and selects its organizations |
| `mapUsersToBusinessGroups(session, groups, emails, log)` | Maps every team user to all groups |
| `setEnterpriseLimits(session, recordLimit, groupLimit, log)` | Sets the record and business group limits |
| `setupEma(...)` | Runs step 3 for each enterprise and returns a result per enterprise |

### Test Data (testData.py)

| Name | Contents |
|------|----------|
| `ENTERPRISE_NAMES` | The 7 enterprises created in Smart Portal |
| `TENANT_ONE_ONLY`, `TENANT_TWO_ONLY` | Enterprises that get only one tenant |
| `TENANT_IDS`, `GRANT_ACCESS_DAYS` | Tenants for grant access and organization sync, and the access length |
| `TRACKER_PERMISSIONS`, `BUSINESS_PROFILES` | The 8 tracker permissions and the 3 profiles |
| `EMA_ENTERPRISES` | Business groups, organizations and limits per enterprise |
| `EMA_ENTERPRISE_NAMES` | Enterprises the Cypress EMA specs run |
| `USER_EMAILS` | Read from `DEFAULT_USERS` in `.env`; no emails are stored in this file |

Copied from `SISDomainsAutomation/cypress/fixtures/shared/precondition.td.ts`. `KEEP_ENTERPRISE_NAMES` in `app.py` lists enterprises that are never deleted.

### Web Page (ui.py)

| Part | Description |
|------|-------------|
| Environment card | Connect form; folds to a summary once connected |
| Team picker | Saved teams with delete icons, paste box, **Save as team** |
| Enterprise table | Create / tenants / limits / EMA per enterprise |
| Run card | Step tiles, confirmation, run buttons, progress bar |
| Output Log | Live table of every call; filter, auto-scroll, copy, clear |

The page reloads `app.py`, `ema.py` and `testData.py` on every refresh, so edits to them show without a restart. Changes to `.env` or `.streamlit/config.toml` need a restart.

---

## How Login Works

- **Smart Portal**: gets an Azure AD token with the username and password (MSAL, using `CLIENT_ID`), then calls `ActiveDirectoryAuthentication/v01/Login` for a portal session ID. Calls send `Authorization: Bearer <token>` and `token: <session ID>`.
- **EMA**: signs in through Auth0 and Microsoft, so `ema.py` opens the EMA login page in headless Chromium, enters the email, handles the Microsoft sign-in and the enterprise dropdown in whatever order EMA shows them, and checks that EMA opened the requested enterprise. It then reads `AuthToken`, `EnterpriseManagementSession` and `SELECTED_ENTERPRISE` from the page and makes plain API calls. It logs in once per enterprise, which takes about 15–30 seconds.

The login account must be an admin of an enterprise for EMA to offer it, which is why step 2 adds the login account as an admin of every enterprise it creates.

---

## API Endpoints Hit

Smart Portal calls go to `https://portalapp-api-<env>/api`; EMA calls go to `https://emaapi-<env>/api`.

| Category | Method | Endpoint |
|----------|--------|----------|
| **Auth** | POST | `https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token` (MSAL) |
| | GET | `/ActiveDirectoryAuthentication/v01/Login` |
| **Enterprises** | GET | `/EnterpriseManagement/v01/1/EnterpriseNames/` |
| | DELETE | `/EnterpriseManagement/v01/1/Enterprises/{enterpriseId}` |
| | POST | `/EnterpriseManagement/v01/1/Enterprises/New/` |
| | POST | `/EnterpriseManagement/v01/1/EnterpriseAdminUsers/{enterpriseId}` |
| | POST | `/EnterpriseManagement/v01/1/AddTenant/` |
| | POST | `/EnterpriseManagement/v01/1/Enterprises/{enterpriseId}/Register/` |
| **Users** | GET | `/Users/v01/All` |
| | DELETE | `/Users/v01/{userId}` |
| | POST | `/Users/v01/` |
| | PUT | `/Users/v01/{userId}/PermissionGroups` |
| **Access & sync** | POST | `/SISComplete/v01/1/RequestGrantAccess` |
| | POST | `/SISComplete_EnterpriseMaster_Sync/v01/1/Tenants/{tenantId}/OrganizationUnits/Synchronize` |
| **EMA profiles** | POST | `/BusinessGroupPermissionGroups/v01/` |
| | GET | `/BusinessGroupPermissionGroups/v01/` |
| | PUT | `/BusinessGroupPermissionGroups/v01/{profileId}/Permission` |
| **EMA groups** | POST | `/BusinessGroupManagement/v01/Add/` |
| | GET | `/BusinessGroupManagement/v01/BusinessGroup/{groupId}` |
| | PUT | `/BusinessGroupManagement/v01/BusinessGroup/` |
| | GET | `/BusinessGroupManagement/v01/BusinessGroups/` |
| **EMA users** | POST | `/FacilityUsers/v01/User/Set` |
| **EMA limits** | GET | `/EnterpriseConfiguration/v01/` |
| | PUT | `/EnterpriseConfiguration/v01/` |

---

## Configuration

| File | Purpose |
|------|---------|
| `requirements.txt` | Python packages |
| `.env` / `.env.example` | Login, emails and saved teams (see below) |
| `.streamlit/config.toml` | Page theme: colors, Inter font, rounded corners; hides the Deploy button |
| `localSettings.json` | Recent environments, per machine |
| `.gitignore` | Ignores `.env`, `.venv/`, `localSettings.json`, `teams.json`, screenshots and caches |

---

## Environment Variables

All in `.env`. Emails are sensitive, so they live only here, never in the code.

| Variable | Required | Description |
|----------|----------|-------------|
| `PORTAL_USER` | Yes | Account that logs in to Smart Portal and EMA |
| `PORTAL_PASSWORD` | Yes | Its password |
| `CLIENT_ID` | Yes | Azure AD app (client) ID of the Smart Portal |
| `PORTAL_URL` | No | Default environment (Smart Portal web URL) |
| `DEFAULT_USERS` | No | Comma-separated emails for the built-in team, shown when no teams are saved |
| `PROTECTED_USERS` | No | Comma-separated emails step 1 never deletes. The login account is always protected too |
| `TEAM_<name>` | No | A saved team, e.g. `TEAM_pitCrew=user1@sisfirst.com,user2@sisfirst.com`. Underscores in the name show as spaces. **Save as team** and the delete icon on the page add and remove these lines |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Start with `python run cbo` (uses `.venv`), not `streamlit run` from the global Python. |
| `Login failed: ...` (AADSTS error) | Check `PORTAL_USER`, `PORTAL_PASSWORD` and `CLIENT_ID` in `.env`. |
| EMA setup stops with "EMA opened 'X' instead of 'Y'" | The login account isn't an admin of that enterprise. Run step 2 (Create) again; it adds the login account as admin. |
| EMA login stops at `https://undefined/authorize` | The enterprise has no IDP yet. Run step 2 first and let it finish. |
| EMA login times out | Run with `--show-browser` to watch where it stops. |
| Status 401 in the middle of a run | The login expired. Run again; each step logs in fresh. |
| Changes to `.env` or the theme don't show | Stop the page and start it again with `python run cbo`. |
| Port already in use | Use another port: `python run cbo --port 8600`. |
