"""CBO Seeder: Streamlit UI for resetting Smart Portal and EMA test data.

Run with:  python run cbo     (or: streamlit run ui.py)
"""
import importlib
import json
import os
import time
import re
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

import app
import ema
import testData

# Streamlit only reloads ui.py when it changes; reload the other modules too, so a page refresh picks up their edits
for module in (testData, app, ema):
    importlib.reload(module)

st.set_page_config(page_title="CBO Seeder", page_icon="🧪", layout="centered")

HERE = Path(__file__).parent
SETTINGS_FILE = HERE / "localSettings.json"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@sisfirst\.com$", re.IGNORECASE)
STEPS = {
    "delete": ("Delete old test data", "Enterprises, and your team's users"),
    "create": ("Create Smart Portal data", "Users, grant access, org sync, enterprises"),
    "ema": ("Set up EMA", "Profiles, business groups, users, limits"),
}

st.markdown("""
<style>
  /* Hide the Deploy button and the ⋮ menu in the top-right corner */
  [data-testid="stToolbar"], [data-testid="stAppDeployButton"], [data-testid="stMainMenu"] { display: none !important; }
  header[data-testid="stHeader"] { background: transparent; }

  .block-container { padding-top: 2.4rem; padding-bottom: 3rem; max-width: 1400px; }

  /* Cards: white, rounded, soft shadow, no border */
  [class*="st-key-card-"] { background: #ffffff; border: none !important; border-radius: 16px;
                            box-shadow: 0 1px 2px rgba(16, 24, 40, .04), 0 4px 16px rgba(16, 24, 40, .05);
                            padding: 22px 26px !important; }

  /* Labels and inputs */
  [data-testid="stWidgetLabel"] p { font-size: .95rem; font-weight: 500; color: #1f2937; }
  [data-testid="stTextInputRootElement"], [data-testid="stTextArea"] textarea, [data-baseweb="select"] > div {
      background: #f1f4f9 !important; border: 1px solid #e8ecf3 !important; border-radius: 10px !important; }
  [data-testid="stTextInputRootElement"] input { font-size: 1rem; padding: 12px 14px; }
  [data-testid="stTextInputRootElement"]:focus-within { border-color: #3d5bc9 !important; }

  /* Buttons */
  .stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {
      border-radius: 10px; font-weight: 600; padding: 10px 22px; min-height: 46px; }
  .stButton button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"],
  [data-testid="stFormSubmitButton"] button[kind="primary"] {
      background: #3d5bc9; border-color: #3d5bc9; box-shadow: 0 2px 6px rgba(61, 91, 201, .25); }
  .stButton button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button:hover { background: #3450b5; }

  /* Header: gradient icon and gradient title */
  .app-head { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
  .app-mark { width: 46px; height: 46px; border-radius: 12px; flex: none; display: grid; place-items: center;
              background: linear-gradient(135deg, #3b6cf6 0%, #7c3aed 100%);
              box-shadow: 0 8px 20px rgba(91, 76, 240, .25); }
  .app-head h1 { display: inline-block; font-size: 1.45rem; font-weight: 700; margin: 0; padding: 0; line-height: 1.15;
                 background: linear-gradient(90deg, #3b6cf6 0%, #8b5cf6 50%, #f97316 100%);
                 -webkit-background-clip: text; background-clip: text; color: transparent; }
  .app-head p { margin: 2px 0 0; color: #5b6472; font-size: .9rem; }
  .chip { margin-left: auto; font-size: .85rem; font-weight: 600; padding: 8px 16px; border-radius: 10px;
          white-space: nowrap; background: #fff; border: 1px solid #e8ecf3; }
  .chip-ok { color: #15803d; }
  .chip-off { color: #5b6472; }

  /* Card titles */
  .sec { display: flex; align-items: center; gap: 10px; margin: 0 0 2px; }
  .sec-n { width: 26px; height: 26px; border-radius: 8px; background: #eef2ff; color: #3d5bc9;
           display: grid; place-items: center; font-weight: 700; font-size: 13px; flex: none; }
  .sec-n.done { background: #3d5bc9; color: #fff; }
  .sec h3 { font-size: 1.3rem; font-weight: 700; margin: 0; padding: 0; color: #111827; }
  .sec-sub { color: #5b6472; font-size: .92rem; margin: 2px 0 12px 36px; }

  .tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 6px 0 8px; }
  .tile { border: 1px solid #e8ecf3; border-radius: 12px; padding: 12px 14px; background: #f8fafc; min-width: 0; }
  .tile b { display: block; font-size: .95rem; }
  .tile span { display: block; font-size: .8rem; color: #5b6472; }
  .tile i { font-style: normal; font-size: .75rem; font-weight: 600; padding: 2px 9px; border-radius: 99px;
            display: inline-block; margin-top: 8px; background: #eef1f5; color: #5b6472; }
  .tile.ok { border-color: #86efac; background: #f0fdf4; } .tile.ok i { background: #dcfce7; color: #15803d; }
  .tile.bad { border-color: #fca5a5; background: #fef2f2; } .tile.bad i { background: #fee2e2; color: #b91c1c; }
  @media (max-width: 640px) { .tiles { grid-template-columns: 1fr; } .app-mark { width: 40px; height: 40px; } }

  .facts { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: .88rem; color: #5b6472; margin-top: 4px; }
  .facts b { color: #111827; font-weight: 600; }

  /* Team picker: a popover styled like a dropdown */
  .picker-label { font-size: .95rem; font-weight: 500; color: #1f2937; margin: 0 0 -6px; }
  [class*="st-key-teamPicker"] button { justify-content: space-between; background: #f1f4f9; border: 1px solid #e8ecf3;
                                        font-weight: 400; color: #111827; min-height: 42px; }
  [class*="st-key-teamPicker"] button > div { width: 100%; justify-content: space-between; }
  [class*="st-key-teamPicker"] button > div > div:first-child { flex: 1; text-align: left; justify-content: flex-start !important; }
  [class*="st-key-teamPicker"] button [data-testid="stMarkdownContainer"],
  [class*="st-key-teamPicker"] button [data-testid="stMarkdownContainer"] p { width: 100%; text-align: left !important; }
  [class*="st-key-pickTeam-"] button { justify-content: flex-start; font-weight: 500; padding: 6px 10px; min-height: 36px; }
  [class*="st-key-pickTeam-"] button > div, [class*="st-key-pickTeam-"] button p { width: 100%; justify-content: flex-start;
                                                                                  text-align: left; }
  [class*="st-key-pickTeam-"] button:hover { background: #eef2ff; color: #3d5bc9; }
  [class*="st-key-deleteTeam-"] button { color: #b91c1c; min-height: 36px; padding: 6px; }
  [class*="st-key-deleteTeam-"] button:hover { background: #fee2e2; }

  .st-key-clearLog { display: none; }

  /* Enterprise table: hide the show/hide columns, download, search and fullscreen toolbar */
  .st-key-card-enterprises [data-testid="stElementToolbar"] { display: none; }
  /* "Choose enterprises": no show/hide arrow, and the label no longer collapses the table */
  .st-key-card-enterprises [data-testid="stExpander"] summary [data-testid="stIconMaterial"] { display: none; }
  .st-key-card-enterprises [data-testid="stExpander"] summary { pointer-events: none; cursor: default; }

  /* Output log heading */
  .log-head { display: flex; justify-content: space-between; color: #8a94a6; font-size: 1.02rem;
              margin: 28px 2px 8px; }

  /* Live step logs: same dark navy as the output log */
  [data-testid="stCode"] pre { background: #0f172a !important; border-radius: 12px; }
  [data-testid="stCode"] code { color: #cbd5e1 !important; }
</style>
""", unsafe_allow_html=True)


# ---------- Saved files ----------

def readJson(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def writeJson(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def loadTeams():
    """Saved teams from .env; when there are none, the DEFAULT_USERS list from .env as a built-in team."""
    return app.loadTeams() or ({"Everyone (Cypress list)": testData.USER_EMAILS} if testData.USER_EMAILS else {})


def rememberEnvironment(portalUrl, emaUrl):
    settings = readJson(SETTINGS_FILE, {})
    recent = [{"portalUrl": portalUrl, "emaUrl": emaUrl}]
    recent += [r for r in settings.get("recent", []) if isinstance(r, dict) and r.get("portalUrl") != portalUrl]
    settings["recent"] = recent[:6]
    writeJson(SETTINGS_FILE, settings)


def addLog(line):
    """Add a line to the page log and print the same line in the terminal."""
    stamped = f"{datetime.now():%H:%M:%S}  {line}"
    state.log.append(stamped)
    try:
        print(stamped, flush=True)
    except (OSError, UnicodeError):
        pass
    return stamped


def section(number, title, subtitle, done=False):
    st.markdown(f'<div class="sec"><span class="sec-n{" done" if done else ""}">{"✓" if done else number}</span>'
                f'<h3>{title}</h3></div><p class="sec-sub">{subtitle}</p>', unsafe_allow_html=True)


# ---------- Page state ----------

state = st.session_state
state.setdefault("credentials", None)
state.setdefault("log", [])
state.setdefault("results", {})
state.setdefault("lastRun", None)
# The team box starts empty: every run is for the users you pick or paste, never a default list
state.setdefault("teamUsers", "")
def freshEnterpriseTable():
    """Nothing is ticked at first: pick only the enterprises your story needs."""
    return pd.DataFrame([
        {
            "Create": False,
            "Enterprise": name,
            "Tenant 1": False,
            "Tenant 2": False,
            "Record limit": data["recordLimit"],
            "Group limit": data["businessGroupLimit"],
            "EMA": False,
        }
        for name, data in testData.EMA_ENTERPRISES.items()
    ])


def resetForNewTeam():
    """A different team starts clean: no enterprises picked, no previous results, confirmation unticked."""
    state.enterpriseTable = freshEnterpriseTable()
    state.enterpriseEditorVersion = state.get("enterpriseEditorVersion", 0) + 1
    state.results, state.lastRun = {}, None
    state.confirmWipe = False


if "enterpriseTable" not in state:
    state.enterpriseTable = freshEnterpriseTable()


def parseTeamUsers(text):
    """Return (valid unique emails, invalid entries) from the team box."""
    seen, valid, invalid = set(), [], []
    for entry in re.split(r"[\s,;]+", text):
        if not entry:
            continue
        if not EMAIL_PATTERN.match(entry):
            invalid.append(entry)
        elif entry.casefold() not in seen:
            seen.add(entry.casefold())
            valid.append(entry)
    return valid, invalid


# ---------- Running steps ----------

class StepLog:
    """Log for one running step: adds each line to the Output Log, redraws it live, and moves the progress bar."""

    def __init__(self, title, expectedCalls, progressSlot, drawLog):
        self.title = title
        self.expected = max(expectedCalls, 1)
        self.calls = 0
        self.progressSlot = progressSlot
        self.drawLog = drawLog
        self.lastDraw = 0.0
        self.progressSlot.progress(0.0, text=f"{title}: starting…")

    def __call__(self, line):
        addLog(line)
        if "status " in line:
            self.calls += 1
        self.progressSlot.progress(min(self.calls / self.expected, 0.99),
                                   text=f"{self.title}: {self.calls} of about {self.expected} calls")
        # Redraw the Output Log at most once a second; each redraw reloads its frame
        if time.monotonic() - self.lastDraw >= 1:
            self.drawLog()
            self.lastDraw = time.monotonic()

    def finish(self):
        self.drawLog()


def freshPortalSession():
    """Log in again so a long run never starts with an expired token."""
    creds = state.credentials
    return app.createPortalSession(creds["portalUrl"], creds["username"], creds["password"])


def runDelete(log, plan):
    session = freshPortalSession()
    entDeleted, entFailed = app.deleteEnterprises(session, log)
    usrDeleted, usrFailed = app.deleteUsers(session, log, onlyEmails=plan["emails"])
    failed = entFailed + usrFailed
    return not failed, f"{entDeleted} enterprises and {usrDeleted} users deleted · {failed} failed", True


def runCreate(log, plan):
    result = app.createSmartPortalData(freshPortalSession(), plan["emails"], plan["createNames"], log,
                                       plan["tenantsByName"])
    failed = result["usersFailed"] + result["enterprisesFailed"]
    ok = not failed and result["accessGranted"] and result["organizationsSynced"]
    text = (f"{result['usersCreated']} users and {result['enterprisesCreated']} enterprises created · {failed} failed · "
            f"grant access {'OK' if result['accessGranted'] else 'FAILED'} · "
            f"org sync {'OK' if result['organizationsSynced'] else 'FAILED'}")
    return ok, text, not result["enterprisesFailed"]


def runEma(log, plan):
    creds = state.credentials
    results = ema.setupEma(creds["portalUrl"], creds["username"], creds["password"], plan["emaNames"],
                           plan["emails"], log, limitsByName=plan["limitsByName"], emaUrl=creds["emaUrl"])
    okNames = [n for n, r in results.items() if app.isEmaOk(r)]
    badNames = [n for n in results if n not in okNames]
    text = f"{len(okNames)} of {len(results)} enterprises set up" + (f" · failed: {', '.join(badNames)}" if badNames else "")
    return not badNames, text, not badNames


RUNNERS = {"delete": runDelete, "create": runCreate, "ema": runEma}


def expectedCalls(step, plan):
    """Rough number of API calls a step makes, for the progress bar."""
    users = len(plan["emails"])
    if step == "delete":
        # Two list calls, the team's users, and a guess at the enterprises left from the last run
        return 2 + users + len(testData.EMA_ENTERPRISES)
    if step == "create":
        return 2 * users + 3 + sum(2 + users + len(plan["tenantsByName"][n]) for n in plan["createNames"])
    groups = sum(len(testData.EMA_ENTERPRISES[n]["groups"]) for n in plan["emaNames"])
    return len(plan["emaNames"]) * (27 + users + 1) + 2 * groups


def runSteps(steps, plan, progressSlot, drawLog):
    """Run steps in order, showing every line live in the Output Log. Stops when a step leaves the data unsafe."""
    state.results = {}
    for step in steps:
        title = STEPS[step][0]
        log = StepLog(title, expectedCalls(step, plan), progressSlot, drawLog)
        log(f"===== {title} =====")
        try:
            ok, text, canContinue = RUNNERS[step](log, plan)
        except Exception as error:
            log(f"Stopped: {error}")
            ok, text, canContinue = False, f"Stopped: {error}", False
        log(f"{title}: {'PASSED' if ok else 'FAILED'} · {text}")
        log.finish()
        state.results[step] = (ok, text)
        if not canContinue and step != steps[-1]:
            state.results["stopped"] = (False, f"Stopped after “{title}”, so the next steps were not run.")
            break
    state.lastRun = datetime.now()
    st.rerun()


# ---------- Header ----------

creds = state.credentials
chip = (f'<span class="chip chip-ok">● Connected · {app.getEnvironmentId(creds["portalUrl"])}</span>' if creds
        else '<span class="chip chip-off">Not connected</span>')
st.markdown(f"""
<div class="app-head">
  <span class="app-mark"><svg width="20" height="20" viewBox="0 0 24 24"><path fill="#fb923c"
    d="M13.5 2 5 13.5h6L10 22l9-12.5h-6.2z"/></svg></span>
  <div><h1>CBO Seeder</h1><p>Smart Portal &amp; EMA test data seeder</p></div>
  {chip}
</div>""", unsafe_allow_html=True)
st.write("")

# ---------- 1. Environment ----------

with st.container(border=True, key="card-environment"):
    section(1, "Environment", "Connected. Both Smart Portal and EMA use this login." if creds else
            "Where to run, and the account to log in with. Both Smart Portal and EMA use this login.", done=bool(creds))
    if creds:
        envId = app.getEnvironmentId(creds["portalUrl"])
        st.markdown(f'<div class="facts"><span>Environment <b>{envId}</b></span>'
                    f'<span>Tenants <b>{envId}t1</b>, <b>{envId}t2</b></span>'
                    f'<span>EMA <b>{creds["emaUrl"].replace("https://", "")}</b></span>'
                    f'<span>User <b>{escape(creds["username"])}</b></span></div>', unsafe_allow_html=True)

    # Once connected, the login form folds away; open it to switch environment or account
    loginBox = st.expander("Change environment or account", expanded=False) if creds else st.container()
    with loginBox:
        recent = [r for r in readJson(SETTINGS_FILE, {}).get("recent", []) if isinstance(r, dict)]
        last = recent[0] if recent else {}

        if recent and len(recent) > 1:
            pick = st.selectbox("Recent environments", range(len(recent)),
                                format_func=lambda i: app.getEnvironmentId(recent[i]["portalUrl"]) or recent[i]["portalUrl"])
            last = recent[pick]

        with st.form("connect", border=False):
            c1, c2 = st.columns(2)
            portalUrl = c1.text_input("Smart Portal base URL", value=last.get("portalUrl") or os.environ.get("PORTAL_URL", ""),
                                      placeholder="https://portalapp-web-12345e2-centralindia.siscompletedev.cloud")
            emaUrl = c2.text_input("EMA base URL", value=last.get("emaUrl", ""),
                                   placeholder="https://ema-12345e2-centralindia.siscompletedev.cloud",
                                   help="Leave empty to work it out from the portal URL")
            c3, c4 = st.columns(2)
            username = c3.text_input("Username")
            password = c4.text_input("Password", type="password", help="Kept only while this page is open. Not saved.")
            connectClicked = st.form_submit_button("Connect" if not creds else "Reconnect", type="primary")

        if connectClicked:
            state.credentials = None
            if not (portalUrl.strip() and username.strip() and password):
                st.error("Enter the Smart Portal URL, username and password.")
            else:
                try:
                    emaWeb, emaApi = ema.getEmaUrls(portalUrl, emaUrl)
                    with st.spinner("Logging in to Smart Portal…"):
                        app.createPortalSession(portalUrl.strip(), username.strip(), password)
                    state.credentials = {"portalUrl": portalUrl.strip(), "emaUrl": emaWeb, "emaApi": emaApi,
                                         "username": username.strip(), "password": password}
                    rememberEnvironment(portalUrl.strip(), emaUrl.strip())
                    addLog(f"Connected to {app.getEnvironmentId(portalUrl)} as {username}")
                    st.rerun()
                except Exception as error:
                    st.error(f"Couldn't connect: {error}")

# Everything below needs a working login: show it only after Connect succeeds
if not state.credentials:
    st.caption("Connect to an environment to choose your team and enterprises.")
    st.stop()

# Team users and Enterprises sit side by side to save scrolling
teamColumn, enterpriseColumn = st.columns([1, 1.45], gap="medium")

# ---------- 2. Team users ----------

with teamColumn.container(border=True, key="card-team"):
    teamEmails, invalid = parseTeamUsers(state.teamUsers)
    section(2, "Team users", "Only these users are deleted, re-created in Smart Portal, added as admins to the enterprises you pick "
            "and mapped in EMA. Other users are left alone.",
            done=bool(teamEmails) and not invalid)
    teams = loadTeams()

    savedTeams = app.loadTeams()

    def pickTeam(name):
        state.teamUsers = "\n".join(teams[name])
        state.teamPicker = False  # close the list

    def deleteTeam(name):
        app.deleteTeam(name)
        st.toast(f"Deleted team “{name}”")

    # A team list with a delete icon beside each saved team (a plain dropdown can't hold buttons)
    boxKey = {e.casefold() for e in teamEmails}
    pickedName = next((n for n, m in teams.items() if boxKey and {x.casefold() for x in m} == boxKey), None)
    st.markdown('<p class="picker-label">Choose a saved team, or paste emails below</p>', unsafe_allow_html=True)
    # on_change="rerun" makes the open state trackable, so picking a team can close the list
    with st.popover(pickedName or "Choose a team", width="stretch", key="teamPicker", on_change="rerun"):
        for name, members in teams.items():
            t1, t2 = st.columns([8, 1], vertical_alignment="center", gap="small")
            t1.button(f"{name} · {len(members)} users", key=f"pickTeam-{name}", type="tertiary", width="stretch",
                      on_click=pickTeam, args=(name,))
            # Only teams saved in .env can be deleted, not the built-in DEFAULT_USERS list shown when there are none
            if name in savedTeams:
                t2.button(":material/delete:", key=f"deleteTeam-{name}", help=f"Delete team “{name}”", type="tertiary",
                          on_click=deleteTeam, args=(name,))
    st.text_area("One email per line", key="teamUsers", height=180, label_visibility="collapsed",
                 placeholder="Paste your team's emails, one per line\nuser1@sisfirst.com\nuser2@sisfirst.com")
    teamEmails, invalid = parseTeamUsers(state.teamUsers)

    # Name the list: a saved team if the box matches it exactly, otherwise "custom list"
    teamKey = {e.casefold() for e in teamEmails}
    # The team changed since the last run of the page: reset enterprises, results and the confirmation
    if state.get("lastTeamKey") is not None and state.lastTeamKey != teamKey:
        resetForNewTeam()
        if state.log:
            addLog(f"Team changed to {len(teamEmails)} users: enterprises, results and confirmation reset")
    state.lastTeamKey = teamKey
    teamName = next((name for name, members in teams.items() if {m.casefold() for m in members} == teamKey and teamKey),
                    "custom list")
    s1, s2 = st.columns([1.6, 1], vertical_alignment="center")
    s1.markdown((f"**{teamName} · {len(teamEmails)} users**" if teamEmails else "**No users yet**")
                + (" · " + ", ".join(f"`{x}` ignored" for x in invalid[:5]) if invalid else ""))
    with s2.popover("Save as team", width="stretch"):
        newTeam = st.text_input("Team name", placeholder="e.g. Pit-Crew")
        if st.button("Save", disabled=not (newTeam.strip() and teamEmails)):
            app.saveTeam(newTeam.strip(), teamEmails)
            st.success(f"Saved {len(teamEmails)} users as “{newTeam.strip()}”.")


# ---------- 3. Enterprises ----------

state.setdefault("enterpriseEditorVersion", 0)


def applyEnterpriseEdits():
    """Save the table edits. Ticking Create also ticks EMA and the default tenants; unticking it clears them."""
    editorKey = f"enterpriseEditor{state.enterpriseEditorVersion}"
    table = state.enterpriseTable.copy()
    for row, changes in state[editorKey]["edited_rows"].items():
        for column, value in changes.items():
            table.at[row, column] = value
        if "Create" in changes:
            table.at[row, "EMA"] = changes["Create"]
            if not changes["Create"]:
                table.at[row, "Tenant 1"] = table.at[row, "Tenant 2"] = False
            elif not (table.at[row, "Tenant 1"] or table.at[row, "Tenant 2"]):
                tenantIds = app.getTenantIds(table.at[row, "Enterprise"])
                table.at[row, "Tenant 1"], table.at[row, "Tenant 2"] = 1 in tenantIds, 2 in tenantIds
    state.enterpriseTable = table
    # A new key draws the editor fresh from the saved table, so the auto-ticked boxes show up
    state.enterpriseEditorVersion += 1


with enterpriseColumn.container(border=True, key="card-enterprises"):
    edited = state.enterpriseTable
    pickedAny = bool(edited["Create"].any() or edited["EMA"].any())
    section(3, "Enterprises", "Tick only the enterprises your story needs: Create adds it in Smart Portal, "
            "EMA sets it up in EMA.", done=pickedAny)
    # Keep the label and expanded flag fixed: changing either redraws the expander closed after every tick
    with st.expander("Choose enterprises", expanded=True):
        edited = st.data_editor(
            state.enterpriseTable, hide_index=True, width="stretch", disabled=["Enterprise"],
            key=f"enterpriseEditor{state.enterpriseEditorVersion}", on_change=applyEnterpriseEdits,
            column_config={
                "Create": st.column_config.CheckboxColumn("Create", help="Create in Smart Portal", width="small"),
                "Enterprise": st.column_config.TextColumn("Enterprise", width="medium"),
                "Tenant 1": st.column_config.CheckboxColumn("t1", width="small"),
                "Tenant 2": st.column_config.CheckboxColumn("t2", width="small"),
                "Record limit": st.column_config.NumberColumn("Records", min_value=1, step=1, width="small"),
                "Group limit": st.column_config.NumberColumn("Groups", min_value=1, step=1, width="small",
                                                             help="Business group facility limit (EMA)"),
                "EMA": st.column_config.CheckboxColumn("EMA", help="Set up in EMA", width="small"),
            },
        )
        st.caption(f"{int(edited['Create'].sum())} to create · {int(edited['EMA'].sum())} in EMA · "
                   "DevEnterprise is never touched.")
    noTenant = edited[edited["Create"] & ~edited["Tenant 1"] & ~edited["Tenant 2"]]["Enterprise"].tolist()
    if noTenant:
        st.warning("Pick at least one tenant for: " + ", ".join(noTenant))
    emaNotCreated = edited[edited["EMA"] & ~edited["Create"]]["Enterprise"].tolist()
    if emaNotCreated:
        st.info("Run all 3 steps deletes every enterprise first, so also tick Create for: " + ", ".join(emaNotCreated))

plan = {
    "emails": teamEmails,
    "createNames": edited[edited["Create"]]["Enterprise"].tolist(),
    "emaNames": edited[edited["EMA"]]["Enterprise"].tolist(),
    "tenantsByName": {
        row["Enterprise"]: [t for t, on in ((1, row["Tenant 1"]), (2, row["Tenant 2"])) if on]
        for _, row in edited.iterrows()
    },
    "limitsByName": {
        row["Enterprise"]: {"recordLimit": int(row["Record limit"]), "businessGroupLimit": int(row["Group limit"])}
        for _, row in edited.iterrows()
    },
}

# ---------- 4. Run ----------

pendingRun = progressSlot = None

with st.container(border=True, key="card-run"):
    section(4, "Run", "Runs in order. Each step logs in fresh, so long runs don't hit an expired login.")

    tiles = ""
    for key, (title, sub) in STEPS.items():
        ok, text = state.results.get(key, (None, ""))
        cls, label = ("ok", "Done") if ok else ("bad", "Failed") if ok is False else ("", "Not run")
        tiles += f'<div class="tile {cls}"><b>{title}</b><span>{sub}</span><i>{label}</i></div>'
    st.markdown(f'<div class="tiles">{tiles}</div>', unsafe_allow_html=True)

    blocker = ("Connect to an environment in step 1." if not creds
               else "Choose a team or paste your team's emails in step 2." if not teamEmails
               else "Pick at least one enterprise in step 3." if not pickedAny
               else "Fix the enterprise tenants in step 3." if noTenant else "")
    if blocker:
        st.info(blocker)
    else:
        envId = app.getEnvironmentId(creds["portalUrl"])

        confirmed = st.checkbox(key="confirmWipe", label=f"I checked with my team that **{envId}** can be wiped and re-seeded. "
                                "Deleted data can't be restored.")
        runAll = st.button(f"Reset {envId} for {teamName} ({len(teamEmails)} users) — run all 3 steps",
                           type="primary", disabled=not confirmed, width="stretch")

        st.caption("Or run one step")
        b1, b2, b3 = st.columns(3)
        runDel = b1.button("1 · Delete", disabled=not confirmed, width="stretch")
        runCre = b2.button("2 · Create", disabled=not plan["createNames"], width="stretch")
        runEm = b3.button("3 · EMA", disabled=not plan["emaNames"], width="stretch",
                          help="Logs in to EMA once per enterprise, about 15 seconds each. Run after step 2.")

        # Steps run at the end of the page, once the Output Log exists, so it can show every line live
        pendingRun = (["delete", "create", "ema"] if runAll else ["delete"] if runDel
                      else ["create"] if runCre else ["ema"] if runEm else None)
        progressSlot = st.empty()

    if state.results:
        st.markdown(f"**Last run · {state.lastRun:%H:%M:%S}**")
        for step, (ok, text) in state.results.items():
            (st.success if ok else st.error)(f"**{STEPS.get(step, ('Stopped',))[0]}:** {text}")

# ---------- Log ----------

# The log is drawn straight into the page (not a frame), so live updates swap rows in place without blinking.
# Everything is scoped under #cbo-log so the styles don't leak into the rest of the page.
LOG_CSS = """
#cbo-log { background: #0f172a; border-radius: 16px; overflow: hidden; font-family: Inter, system-ui, sans-serif; }
#cbo-log .bar { display: flex; gap: 12px; align-items: center; padding: 10px 12px 10px 100px; }
#cbo-log .q { flex: 1; min-width: 0; background: #0b1222; color: #e2e8f0; border: 1px solid #1e293b; border-radius: 10px;
              padding: 11px 16px; font: inherit; font-size: 15px; outline: none; }
#cbo-log .q::placeholder { color: #64748b; }
#cbo-log .q:focus { border-color: #3d5bc9; }
#cbo-log label { color: #a5b4fc; font-size: 14px; display: flex; align-items: center; gap: 8px; white-space: nowrap;
                 cursor: pointer; margin: 0; }
#cbo-log label input { width: 17px; height: 17px; accent-color: #2563eb; margin: 0; }
#cbo-log button { background: #1e293b; color: #e2e8f0; border: 1px solid #334155; border-radius: 10px; padding: 9px 14px;
                  font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; }
#cbo-log button:hover { background: #273449; }
#cbo-log button:disabled { opacity: .45; cursor: not-allowed; }
/* column-reverse keeps the view pinned to the newest line without any script */
#cbo-log .scroll { height: 420px; overflow: auto; border-top: 1px solid #1e293b; display: flex; flex-direction: column-reverse; }
/* margin-bottom: auto keeps a short table at the top instead of the bottom */
#cbo-log .inner { margin-bottom: auto; }
#cbo-log table { width: 100%; border-collapse: collapse; font-size: 13px; color: #cbd5e1; margin: 0; border: none; }
#cbo-log th { position: sticky; top: 0; z-index: 1; background: #111a2e; color: #e2e8f0; font-weight: 700; font-size: 14px;
              text-align: left; padding: 11px 12px; border: none; border-bottom: 1px solid #1e293b; }
#cbo-log th:last-child, #cbo-log td:last-child { text-align: right; }
#cbo-log td { padding: 6px 12px; border: none; border-bottom: 1px solid #16213a; vertical-align: top; background: transparent; }
#cbo-log td.t { color: #94a3b8; white-space: nowrap; width: 90px; font-variant-numeric: tabular-nums; }
#cbo-log td.mt { width: 70px; }
#cbo-log td.api { font-family: Consolas, "Cascadia Mono", Menlo, monospace; font-size: 12px; color: #93c5fd;
                  word-break: break-all; max-width: 380px; }
#cbo-log td.m { font-family: Consolas, "Cascadia Mono", Menlo, monospace; white-space: pre-wrap; word-break: break-word; }
#cbo-log td.s { width: 90px; }
#cbo-log td.d { color: #94a3b8; white-space: nowrap; width: 80px; font-variant-numeric: tabular-nums; }
#cbo-log .method { display: inline-block; min-width: 54px; text-align: center; padding: 2px 6px; border-radius: 6px;
                   font-size: 11px; font-weight: 700; letter-spacing: .02em; }
#cbo-log .GET { background: rgba(59,130,246,.18); color: #93c5fd; }
#cbo-log .POST { background: rgba(34,197,94,.16); color: #86efac; }
#cbo-log .PUT, #cbo-log .PATCH { background: rgba(245,158,11,.18); color: #fcd34d; }
#cbo-log .DELETE { background: rgba(239,68,68,.18); color: #fca5a5; }
#cbo-log .pill { display: inline-block; padding: 2px 9px; border-radius: 99px; font-size: 12px; font-weight: 600; }
#cbo-log .pill.ok { background: rgba(34,197,94,.15); color: #4ade80; }
#cbo-log .pill.bad { background: rgba(239,68,68,.15); color: #f87171; }
#cbo-log tr.err td.m { color: #fca5a5; }
#cbo-log tr.pass td.m { color: #86efac; font-weight: 600; }
#cbo-log tr.head td.m { color: #a5b4fc; font-weight: 600; }
#cbo-log .nomatch td { color: #64748b; text-align: center; padding: 40px 0; }
"""

# Runs after every redraw: puts back the filter, Auto-scroll, scroll position and focus from before the redraw
LOG_JS = """
(() => {
  const root = document.getElementById("cbo-log");
  if (!root) return;
  const saved = window.__cboLog || (window.__cboLog = { q: "", auto: true, scroll: 0, focused: false, caret: 0 });
  const q = root.querySelector(".q"), auto = root.querySelector(".auto"), scroll = root.querySelector(".scroll");
  const copy = root.querySelector(".copy"), noMatch = root.querySelector(".nomatch");
  const rows = Array.from(root.querySelectorAll("tbody tr[data-raw]"));
  q.value = saved.q;
  auto.checked = saved.auto;

  function apply() {
    const term = q.value.trim().toLowerCase();
    let shown = 0;
    rows.forEach(tr => {
      const show = !term || tr.dataset.raw.toLowerCase().includes(term);
      tr.style.display = show ? "" : "none";
      shown += show;
    });
    noMatch.style.display = rows.length && !shown ? "" : "none";
  }

  q.oninput = () => { saved.q = q.value; saved.caret = q.selectionStart; apply(); };
  q.onfocus = () => { saved.focused = true; };
  q.onblur = () => { saved.focused = false; };
  auto.onchange = () => { saved.auto = auto.checked; if (saved.auto) scroll.scrollTop = 0; };
  scroll.onscroll = () => { saved.scroll = scroll.scrollTop; };
  root.querySelector(".clear").onclick = () => {
    const hidden = document.querySelector(".st-key-clearLog button");
    if (hidden) hidden.click();
  };
  copy.onclick = async () => {
    const text = rows.filter(tr => tr.style.display !== "none").map(tr => tr.dataset.raw).join("\\n");
    try { await navigator.clipboard.writeText(text); }
    catch (e) {
      const t = document.createElement("textarea");
      t.value = text; document.body.appendChild(t); t.select();
      document.execCommand("copy"); t.remove();
    }
    copy.textContent = "Copied"; setTimeout(() => copy.textContent = "Copy", 1500);
  };

  apply();
  // With column-reverse, scrollTop 0 is the newest line
  scroll.scrollTop = saved.auto ? 0 : saved.scroll;
  if (saved.focused) { q.focus(); q.setSelectionRange(saved.caret, saved.caret); }
})();
"""

CALL_PATTERN = re.compile(r"\[(GET|POST|PUT|PATCH|DELETE) (\S+)\]")


def parseLogLine(raw):
    """Split "HH:MM:SS  label: status NNN [METHOD url] body" into the parts the log table shows."""
    match = re.match(r"(\d\d:\d\d:\d\d)  (.*)\Z", raw, re.S)
    time_, text = (match.group(1), match.group(2)) if match else ("", raw)
    call = CALL_PATTERN.search(text)
    method, url = (call.group(1), call.group(2)) if call else ("", "")
    if call:
        text = text.replace(call.group(0), "").rstrip()
    code = (re.search(r"status (\d{3})", text) or [None, ""])[1]
    # "0 failed" and names like "usersFailed" are not failures; "2 failed", "FAILED", errors and stops are
    failed = bool(re.search(r"\b[1-9]\d* failed\b", text, re.I) or re.search(r"\bFAILED\b|failed:", text)
                  or re.search(r"\b(error|stopped)\b", text, re.I) or code[:1] in ("4", "5"))
    return {
        "time": time_, "method": method, "url": url, "code": code, "failed": failed,
        "api": re.sub(r"^https?://[^/]+", "", url),
        "passed": not failed and not code and bool(re.search(r"\bPASSED\b|: done:", text)),
        "head": text.startswith("====="),
        "message": re.sub(r":?\s*status \d{3}", "", text, count=1) if code else text,
    }


def formatSeconds(seconds):
    return "" if seconds is None else f"{seconds // 60}m {seconds % 60}s" if seconds >= 60 else f"{seconds}s"


def toSeconds(clock):
    h, m, s = map(int, clock.split(":"))
    return h * 3600 + m * 60 + s


def buildLogHtml(lines, running=False):
    """The Output Log as HTML: filter bar, then a table of Time, Method, API, Message, Status, Duration."""
    rows, previous = [], None
    for raw in lines:
        r = parseLogLine(raw)
        duration = (toSeconds(r["time"]) - toSeconds(previous)) % 86400 if r["time"] and previous else None
        previous = r["time"] or previous
        status = (f'<span class="pill {"bad" if r["failed"] else "ok"}">{r["code"]}</span>' if r["code"]
                  else '<span class="pill bad">Failed</span>' if r["failed"]
                  else '<span class="pill ok">Passed</span>' if r["passed"] else "")
        rowClass = "err" if r["failed"] else "pass" if r["passed"] else "head" if r["head"] else ""
        method = f'<span class="method {r["method"]}">{r["method"]}</span>' if r["method"] else ""
        rows.append(
            f'<tr class="{rowClass}" data-raw="{escape(raw)}"><td class="t">{r["time"]}</td><td class="mt">{method}</td>'
            f'<td class="api" title="{escape(r["url"])}">{escape(r["api"])}</td><td class="m">{escape(r["message"])}</td>'
            f'<td class="s">{status}</td><td class="d">{formatSeconds(duration)}</td></tr>')
    return (f"<style>{LOG_CSS}</style>"
            '<div id="cbo-log"><div class="bar">'
            '<input class="q" type="text" placeholder="Filter by API, method, status or text" autocomplete="off">'
            '<label><input class="auto" type="checkbox" checked> Auto-scroll</label>'
            '<button class="copy" type="button">Copy</button>'
            # Clearing reruns the page, which would stop a run, so it's off while steps run
            f'<button class="clear" type="button"{" disabled title='Available when the run finishes'" if running else ""}>'
            'Clear</button></div>'
            '<div class="scroll"><div class="inner"><table><thead><tr><th>Time</th><th>Method</th><th>API</th><th>Message</th>'
            '<th>Status</th><th>Duration</th></tr></thead><tbody>'
            + "".join(rows) +
            '<tr class="nomatch" style="display:none"><td colspan="6">No lines match.</td></tr>'
            f"</tbody></table></div></div></div><script>{LOG_JS}</script>")


def logTotal(lines):
    """Time from the first to the last log line, e.g. 3m 12s."""
    times = [toSeconds(l[:8]) for l in lines if re.match(r"\d\d:\d\d:\d\d  ", l)]
    return formatSeconds((times[-1] - times[0]) % 86400) if len(times) > 1 else "0s"


def showConsole(target, lines, running=False):
    """Draw (or redraw in place) the Output Log into a placeholder."""
    target.html(buildLogHtml(lines, running), unsafe_allow_javascript=True)


logHeadSlot, logSlot = st.empty(), st.empty()


def drawLog(running=False):
    logHeadSlot.markdown(f'<div class="log-head"><span>Output Log</span>'
                         f'<span>{len(state.log)} lines · Total: {logTotal(state.log)}</span></div>',
                         unsafe_allow_html=True)
    showConsole(logSlot, state.log, running)


def clearLog():
    state.log = []


# The log's Clear button (plain HTML) clicks this hidden Streamlit button, which can change the page state
st.button("Clear log", key="clearLog", on_click=clearLog)


# The Output Log appears once a step has been run, and stays for the rest of the session
if pendingRun:
    state.hasRun = True
if state.get("hasRun"):
    drawLog()
if pendingRun:
    runSteps(pendingRun, plan, progressSlot, lambda: drawLog(running=True))
