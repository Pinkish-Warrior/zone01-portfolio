#!/usr/bin/env python3
"""
01Founders / Zone01 - Project Portfolio Exporter
Fetches XP, skills, audits given/received, and projects.

.env file:
  JWT_TOKEN=eyJ...      (optional — auto-read from browser if omitted)
  STUDENT_LOGIN=your-student-username
  STUDENT_ID=your-numeric-id
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime

API_URL      = "https://learn.01founders.co/api/graphql-engine/v1/graphql"
KEYRING_SVC  = "01founders-portfolio"
KEYRING_USER = "jwt-token"


# ──────────────────────────────────────────────
# KEYCHAIN HELPERS
# ──────────────────────────────────────────────

def _keychain_get() -> str:
    try:
        import keyring
        return keyring.get_password(KEYRING_SVC, KEYRING_USER) or ""
    except Exception:
        return ""


def _keychain_set(token: str) -> None:
    try:
        import keyring
        keyring.set_password(KEYRING_SVC, KEYRING_USER, token)
    except Exception:
        pass


# ──────────────────────────────────────────────
# ENV LOADER
# ──────────────────────────────────────────────

def load_env() -> dict:
    config = {"token": "", "login": "", "student_id": ""}
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    # 1 — read .env for login + student_id
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("STUDENT_LOGIN="):
                    config["login"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("STUDENT_ID="):
                    config["student_id"] = line.split("=", 1)[1].strip().strip('"').strip("'")
        if config["login"]:
            print(f"  ✓ Student login: {config['login']}")
        if config["student_id"]:
            print(f"  ✓ Student ID: {config['student_id']}")

    # 2 — fall back to env vars (used by CI via GitHub Secrets)
    if not config["login"]:
        config["login"] = os.environ.get("STUDENT_LOGIN", "").strip()
    if not config["student_id"]:
        config["student_id"] = os.environ.get("STUDENT_ID", "").strip()
    env_token = os.environ.get("JWT_TOKEN", "").strip()
    if env_token:
        print("  ✓ Token loaded from environment variable")
        config["token"] = env_token

    # 3 — token: keychain (local runs), then prompt once on miss
    if not config["token"]:
        token = _keychain_get()
        if token:
            print("  ✓ Token loaded from macOS Keychain")
            config["token"] = token
        else:
            print("  ℹ No token in Keychain — paste it once and it will be saved securely.")
            print()
            print("  How to get your JWT token:")
            print("  1. Open Google Chrome and go to https://learn.01founders.co")
            print("  2. Press F12 to open DevTools")
            print("  3. Click the 'Application' tab at the top of DevTools")
            print("  4. In the left sidebar, find 'Storage' and expand it")
            print("  5. Click 'Local Storage' to expand it")
            print("  6. Click 'https://learn.01founders.co'")
            print("  7. Find the key 'jwt-token' in the table")
            print("  8. Copy the value (it starts with eyJ...)")
            print()
            config["token"] = input("  Paste JWT token here: ").strip()
            if config["token"]:
                _keychain_set(config["token"])
                print("  ✓ Saved to macOS Keychain — won't be asked again until it expires")

    if not config["login"]:
        config["login"] = input("  Your student username: ").strip()
    return config


# ──────────────────────────────────────────────
# GRAPHQL QUERIES
# ──────────────────────────────────────────────

def make_queries(login: str) -> dict:
    lf  = f'login: {{_eq: "{login}"}}'
    ulf = f'userLogin: {{_eq: "{login}"}}'
    alf = f'auditorLogin: {{_eq: "{login}"}}'
    return {

        # ── User profile + audit totals directly from user object
        "user": f"""
{{
  user(where: {{{lf}}}) {{
    id
    login
    email
    createdAt
    campus
    totalUp
    totalDown
    auditRatio
  }}
}}""",

        # ── All transactions (filtered to xp + skills in Python)
        "transactions": f"""
{{
  transactions: transaction(
    where: {{
      {ulf}
    }}
    order_by: {{createdAt: asc}}
  ) {{
    type
    amount
    createdAt
    path
    object {{ name type }}
  }}
}}""",

        # ── Audits this user GAVE (they were the auditor)
        "audits_given": f"""
{{
  audits_given: audit(
    where: {{
      {alf}
      grade: {{_is_null: false}}
    }}
    order_by: {{createdAt: desc}}
  ) {{
    grade
    createdAt
    group {{
      object {{ name type }}
      members {{ user {{ login }} }}
    }}
  }}
}}""",

        # ── Audits this user RECEIVED (they were the auditee / group member)
        "audits_received": f"""
{{
  audits_received: audit(
    where: {{
      group: {{
        members: {{
          user: {{{lf}}}
        }}
      }}
      grade: {{_is_null: false}}
    }}
    order_by: {{createdAt: desc}}
  ) {{
    grade
    createdAt
    group {{
      object {{ name type }}
    }}
  }}
}}""",

        # ── Project progress
        "progress": f"""
{{
  progress(
    where: {{user: {{{lf}}}}}
    order_by: {{updatedAt: desc}}
  ) {{
    grade
    createdAt
    updatedAt
    path
    object {{ name type }}
  }}
}}""",
    }


# ──────────────────────────────────────────────
# FETCHER
# ──────────────────────────────────────────────

def gql(token: str, query: str) -> dict:
    payload = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  ✗ HTTP {e.code}: {body[:200]}")
        return {}
    except Exception as ex:
        print(f"  ✗ Error: {ex}")
        return {}


def fetch_all(token: str, login: str) -> dict:
    queries = make_queries(login)
    labels = {
        "user":            "User profile + audit ratio",
        "transactions":    "XP & skill transactions",
        "audits_given":    "Audits you gave",
        "audits_received": "Audits you received",
        "progress":        "Project progress",
    }
    data = {}
    for key, query in queries.items():
        print(f"  → Fetching {labels[key]}...")
        resp = gql(token, query)
        if "data" in resp:
            data[key] = resp["data"].get(key, [])
        elif "errors" in resp:
            msg = resp["errors"][0].get("message", "unknown")
            print(f"    ⚠ API error: {msg}")
            data[key] = []
        else:
            data[key] = []
    return data


# ──────────────────────────────────────────────
# DATA PROCESSING
# ──────────────────────────────────────────────

def fmt_bytes(n: int) -> str:
    """Convert bytes to human-readable kB/MB."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f} MB"
    if n >= 1_000:
        return f"{n/1_000:.0f} kB"
    return str(n)


def format_xp_uk(amount: float) -> str:
    """Convert large number to human-readable M/K."""
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.2f}M"
    elif amount >= 1_000:
        return f"{amount / 1_000:.1f}K"
    else:
        return str(round(amount))


def process(raw: dict, fallback_login: str) -> dict:
    user = (raw.get("user") or [{}])[0]
    if not user:
        user = {"login": fallback_login, "email": "", "createdAt": "", "campus": ""}

    # ── XP events over time
    xp_events = []
    total_xp = 0
    # ── Skills (highest level per skill)
    skills = {}

    for t in raw.get("transactions", []):
        ttype = t.get("type", "")
        if ttype == "xp":
            total_xp += t.get("amount", 0)
            xp_events.append({
                "date":       t.get("createdAt", "")[:10],
                "amount":     t.get("amount", 0),
                "cumulative": total_xp,
                "project":    (t.get("object") or {}).get("name", t.get("path", "—")),
            })
        elif ttype.startswith("skill_"):
            skill_name = ttype.replace("skill_", "").replace("_", " ").title()
            skills[skill_name] = max(skills.get(skill_name, 0), t.get("amount", 0))

    # ── Skill categories
    SKILL_CATEGORIES = {
        "Languages":        ["Go", "Python", "Js", "C", "Rust", "Sql"],
        "Frontend":         ["Html", "Css", "Front-End"],
        "Backend":          ["Back-End", "Django", "Graphql"],
        "DevOps & Tools":   ["Docker", "Unix", "Git", "Sys-Admin"],
        "Computer Science": ["Algo", "Prog", "Ai", "Stats"],
        "Game Dev":         ["Game"],
    }
    skill_to_cat = {s: cat for cat, lst in SKILL_CATEGORIES.items() for s in lst}
    categorized_skills = {}
    for skill, val in skills.items():
        cat = skill_to_cat.get(skill, "Other")
        if cat not in categorized_skills:
            categorized_skills[cat] = []
        categorized_skills[cat].append({"name": skill, "level": val})
    for cat in categorized_skills:
        categorized_skills[cat].sort(key=lambda x: -x["level"])

    # ── Projects
    seen = set()
    projects = []
    for p in raw.get("progress", []):
        obj  = p.get("object") or {}
        name = obj.get("name") or p.get("path", "").split("/")[-1]
        if not name or name in seen:
            continue
        seen.add(name)
        grade = p.get("grade")
        projects.append({
            "name":   name,
            "type":   obj.get("type", "—"),
            "grade":  round(grade * 100) if grade is not None else None,
            "passed": grade is not None and grade >= 1.0,
            "date":   (p.get("updatedAt") or p.get("createdAt") or "")[:10],
        })

    # ── Audits — prefer user-level totals (most accurate), fall back to counting
    total_up   = user.get("totalUp")    # bytes the user audited
    total_down = user.get("totalDown")  # bytes the user was audited
    audit_ratio = user.get("auditRatio")

    audits_given_count    = len(raw.get("audits_given", []))
    audits_received_count = len(raw.get("audits_received", []))

    # Recent audit details for display
    audits_given_detail    = raw.get("audits_given", [])[:10]
    audits_received_detail = raw.get("audits_received", [])[:10]

    return {
        "user":                   user,
        "total_xp":               total_xp,
        "xp_events":              xp_events,
        "skills":                 dict(sorted(skills.items(), key=lambda x: -x[1])),
        "categorized_skills":     categorized_skills,
        "projects":               projects,
        "projects_passed":        sum(1 for p in projects if p["passed"]),
        "projects_total":         len(projects),
        "audits_given_count":     audits_given_count,
        "audits_received_count":  audits_received_count,
        "audits_given_detail":    audits_given_detail,
        "audits_received_detail": audits_received_detail,
        "total_up":               total_up,
        "total_down":             total_down,
        "audit_ratio":            audit_ratio,
        "total_up_fmt":           fmt_bytes(total_up)   if total_up   is not None else "—",
        "total_down_fmt":         fmt_bytes(total_down) if total_down is not None else "—",
        "audit_ratio_fmt":        f"{audit_ratio:.2f}"  if audit_ratio is not None else "—",
        "total_xp_fmt":           format_xp_uk(total_xp),
    }


# ──────────────────────────────────────────────
# HTML GENERATOR
# ──────────────────────────────────────────────

def build_html(d: dict) -> str:
    user      = d["user"]
    login     = user.get("login", "Unknown")
    email     = user.get("email", "") or "—"
    campus    = user.get("campus", "") or "01Founders"
    joined    = (user.get("createdAt") or "")[:10] or "—"
    generated = datetime.now().strftime("%d %B %Y, %H:%M")

    xp_labels      = json.dumps([e["date"]       for e in d["xp_events"]])
    xp_values      = json.dumps([e["cumulative"] for e in d["xp_events"]])
    xp_amounts     = json.dumps([e["amount"]     for e in d["xp_events"]])
    xp_projects_js = json.dumps([e["project"]   for e in d["xp_events"]])

    # Skills — top 15, sorted descending
    top_skills = list(d["skills"].items())[:15]
    skill_labels_js = json.dumps([s[0] for s in top_skills])
    skill_values_js = json.dumps([s[1] for s in top_skills])

    top_skills_html = ""
    max_skill = max((s[1] for s in top_skills), default=1)
    for skill, val in top_skills[:10]:
        pct = int(val / max_skill * 100)
        top_skills_html += f"""
        <div class="skill-row">
          <span class="skill-name">{skill}</span>
          <div class="skill-bar-bg"><div class="skill-bar-fill" style="width:{pct}%"></div></div>
          <span class="skill-val">{val}</span>
        </div>"""

    # Skill category cards
    category_cards_html = ""
    for cat, skills_list in d["categorized_skills"].items():
        max_level = max((s["level"] for s in skills_list), default=1)
        items_html = ""
        for s in skills_list:
            pct = int(s["level"] / max_level * 100)
            items_html += f"""
            <div class="skill-row">
              <span class="skill-name">{s['name']}</span>
              <div class="skill-bar-bg"><div class="skill-bar-fill" style="width:{pct}%"></div></div>
              <span class="skill-val">{s['level']}</span>
            </div>"""
        category_cards_html += f"""
        <div class="card cat-card">
          <p class="card-title">{cat}</p>
          {items_html}
        </div>"""

    projects_rows = ""
    for p in d["projects"]:
        grade_str = f"{p['grade']}%" if p["grade"] is not None else "—"
        badge = '<span class="badge pass">PASS</span>' if p["passed"] else '<span class="badge fail">—</span>'
        projects_rows += f"""
        <tr>
          <td class="proj-name">{p['name']}</td>
          <td><span class="type-tag">{p['type']}</span></td>
          <td>{grade_str}</td>
          <td>{badge}</td>
          <td class="date-col">{p['date']}</td>
        </tr>"""

    # Audit detail rows
    def audit_rows(audits, role):
        rows = ""
        for a in audits:
            grp = a.get("group") or {}
            obj = grp.get("object") or {}
            name  = obj.get("name", "—")
            grade = a.get("grade")
            grade_str = f"{round(grade*100)}%" if grade is not None else "—"
            passed = grade is not None and grade >= 1.0
            badge = '<span class="badge pass">PASS</span>' if passed else '<span class="badge fail">FAIL</span>'
            date  = (a.get("createdAt") or "")[:10]
            rows += f"""
            <tr>
              <td class="proj-name">{name}</td>
              <td>{grade_str}</td>
              <td>{badge}</td>
              <td class="date-col">{date}</td>
            </tr>"""
        return rows or f'<tr><td colspan="4" style="color:var(--muted);padding:24px;text-align:center">No {role} found.</td></tr>'

    given_rows    = audit_rows(d["audits_given_detail"],    "audits given")
    received_rows = audit_rows(d["audits_received_detail"], "audits received")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><polygon points='50,5 95,27.5 95,72.5 50,95 5,72.5 5,27.5' fill='%237fff6e'/><text y='68' x='50' text-anchor='middle' font-size='52' font-family='sans-serif' fill='%230a0a0f' font-weight='bold'>01</text></svg>"/>
<title>{login} — 01Founders Portfolio</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0a0a0f; --surface: #111118; --surface2: #18181f;
    --border: #2a2a38; --accent: #7fff6e; --accent2: #6eb8ff; --accent3: #ff6eb4;
    --text: #e8e8f0; --muted: #666680;
    --font: 'Syne', sans-serif; --mono: 'DM Mono', monospace;
  }}
  html {{ scroll-behavior: smooth; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font); min-height: 100vh; overflow-x: hidden; }}
  body::before {{
    content: ''; position: fixed; inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E");
    pointer-events: none; z-index: 0; opacity: .4;
  }}
  /* ── HERO ── */
  .hero {{ position: relative; padding: 80px 60px 60px; border-bottom: 1px solid var(--border); overflow: hidden; }}
  .hero::after {{ content: ''; position: absolute; top: -120px; right: -80px; width: 500px; height: 500px; background: radial-gradient(circle, rgba(127,255,110,.12) 0%, transparent 70%); pointer-events: none; }}
  .hero-tag {{ font-family: var(--mono); font-size: 11px; letter-spacing: .2em; color: var(--accent); text-transform: uppercase; margin-bottom: 16px; opacity: .8; }}
  .hero h1 {{ font-size: clamp(28px, 4vw, 52px); font-weight: 800; line-height: .95; letter-spacing: -.03em; margin-bottom: 20px; }}
  .hero h1 span {{ color: var(--accent); }}
  .hero-meta {{ font-family: var(--mono); font-size: 13px; color: var(--muted); display: flex; gap: 32px; flex-wrap: wrap; margin-top: 24px; }}
  .hero-meta b {{ color: var(--text); display: block; margin-bottom: 2px; }}
  /* ── STATS ── */
  .stats-bar {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); border-bottom: 1px solid var(--border); }}
  .stat-cell {{ padding: 28px 32px; border-right: 1px solid var(--border); transition: background .2s; }}
  .stat-cell:last-child {{ border-right: none; }}
  .stat-cell:hover {{ background: var(--surface2); }}
  .stat-num {{ font-size: 40px; font-weight: 800; letter-spacing: -.04em; line-height: 1; margin-bottom: 6px; }}
  .stat-num.green {{ color: var(--accent); }} .stat-num.blue {{ color: var(--accent2); }} .stat-num.pink {{ color: var(--accent3); }}
  .stat-label {{ font-family: var(--mono); font-size: 10px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }}
  .stat-sub {{ font-family: var(--mono); font-size: 10px; color: var(--muted); margin-top: 4px; }}
  /* ── LAYOUT ── */
  .main {{ padding: 48px 60px; }}
  .section-title {{ font-family: var(--mono); font-size: 11px; letter-spacing: .2em; text-transform: uppercase; color: var(--accent); margin-bottom: 20px; padding-bottom: 10px; border-bottom: 1px solid var(--border); }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 32px; }}
  .grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 24px; margin-bottom: 32px; }}
  @media(max-width:900px) {{ .grid-2,.grid-3 {{ grid-template-columns: 1fr; }} .hero,.main {{ padding: 40px 24px; }} }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 28px; margin-bottom: 0; }}
  .card-title {{ font-size: 12px; font-family: var(--mono); color: var(--muted); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 20px; }}
  .chart-wrap {{ position: relative; height: 200px; }}
  /* ── SKILLS ── */
  .skill-row {{ display: grid; grid-template-columns: 120px 1fr 36px; align-items: center; gap: 12px; margin-bottom: 10px; }}
  .skill-name {{ font-size: 12px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .skill-bar-bg {{ background: var(--surface2); border-radius: 2px; height: 5px; overflow: hidden; }}
  .skill-bar-fill {{ height: 100%; background: var(--accent2); border-radius: 2px; }}
  .skill-val {{ font-family: var(--mono); font-size: 11px; color: var(--muted); text-align: right; }}
  /* ── AUDIT RATIO ── */
  .ratio-display {{ text-align: center; padding: 20px 0; }}
  .ratio-big {{ font-size: 64px; font-weight: 800; letter-spacing: -.04em; color: var(--accent); line-height: 1; }}
  .ratio-label {{ font-family: var(--mono); font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .1em; margin-top: 8px; }}
  .ratio-detail {{ font-family: var(--mono); font-size: 11px; color: var(--muted); margin-top: 16px; display: flex; justify-content: space-around; }}
  .ratio-detail span b {{ color: var(--text); display: block; font-size: 14px; }}
  /* ── TABLES ── */
  .table-wrap {{ overflow-x: auto; margin-bottom: 32px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  thead tr {{ border-bottom: 1px solid var(--border); }}
  th {{ font-family: var(--mono); font-size: 10px; letter-spacing: .15em; text-transform: uppercase; color: var(--muted); text-align: left; padding: 10px 14px; font-weight: 400; }}
  td {{ padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,.04); vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: var(--surface2); }}
  .proj-name {{ font-weight: 700; max-width: 260px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .type-tag {{ font-family: var(--mono); font-size: 10px; background: var(--surface2); border: 1px solid var(--border); padding: 2px 8px; border-radius: 2px; color: var(--muted); text-transform: uppercase; }}
  .badge {{ display: inline-block; font-family: var(--mono); font-size: 10px; letter-spacing: .1em; padding: 2px 8px; border-radius: 2px; }}
  .badge.pass {{ background: rgba(127,255,110,.12); color: var(--accent); border: 1px solid rgba(127,255,110,.25); }}
  .badge.fail {{ background: rgba(255,80,80,.1); color: #ff8080; border: 1px solid rgba(255,80,80,.2); }}
  .date-col {{ font-family: var(--mono); font-size: 11px; color: var(--muted); }}
  .email-blur {{ cursor: pointer; filter: blur(5px); transition: filter .3s; user-select: none; }}
  .email-blur:hover {{ filter: blur(3px); }}
  .email-blur.revealed {{ filter: none; user-select: text; }}
  .search-bar {{ width: 100%; background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 12px 16px; color: var(--text); font-family: var(--mono); font-size: 13px; margin-bottom: 16px; outline: none; transition: border-color .2s; }}
  .search-bar:focus {{ border-color: var(--accent); }}
  .search-bar::placeholder {{ color: var(--muted); }}
  /* ── TABS ── */
  .tabs {{ display: flex; gap: 2px; margin-bottom: 0; border-bottom: 1px solid var(--border); }}
  .tab {{ font-family: var(--mono); font-size: 11px; letter-spacing: .1em; text-transform: uppercase; padding: 10px 20px; cursor: pointer; color: var(--muted); border-bottom: 2px solid transparent; transition: all .15s; margin-bottom: -1px; }}
  .tab.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
  .tab-panel {{ display: none; }} .tab-panel.active {{ display: block; }}
  /* ── FOOTER ── */
  footer {{ border-top: 1px solid var(--border); padding: 24px 60px; font-family: var(--mono); font-size: 11px; color: var(--muted); display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }}
  @keyframes fadeUp {{ from {{ opacity:0; transform: translateY(16px); }} to {{ opacity:1; transform: translateY(0); }} }}
  .hero,.stats-bar,.card,.table-wrap {{ animation: fadeUp .45s ease both; }}
  .stats-bar {{ animation-delay:.08s; }} .grid-2 .card:nth-child(2) {{ animation-delay:.12s; }} .table-wrap {{ animation-delay:.18s; }}
  /* ── PDF BUTTON ── */
  .pdf-btn {{ font-family: var(--mono); font-size: 11px; letter-spacing: .1em; text-transform: uppercase; padding: 10px 20px; background: transparent; border: 1px solid var(--accent); color: var(--accent); border-radius: 4px; cursor: pointer; transition: all .2s; margin-top: 20px; display: inline-block; }}
  .pdf-btn:hover {{ background: var(--accent); color: var(--bg); }}
  /* ── SKILL CATEGORIES ── */
  .cat-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; margin-bottom: 32px; }}
  .cat-card .card-title {{ color: var(--accent2); }}
  /* ── PRINT ── */
  @media print {{
    body {{ background: white; color: #111; }}
    body::before {{ display: none; }}
    .pdf-btn, .search-bar, .tabs, footer, .chart-wrap, canvas {{ display: none !important; }}
    .tab-panel {{ display: block !important; }}
    .hero {{ padding: 24px; border: none; }}
    .hero::after {{ display: none; }}
    .hero h1 {{ font-size: 28px; color: #111; }}
    .hero h1 span {{ color: #111; }}
    .hero-tag, .hero-meta b {{ color: #444; }}
    .stats-bar {{ border: 1px solid #ddd; }}
    .stat-cell {{ border-right: 1px solid #ddd; }}
    .stat-num {{ color: #111 !important; font-size: 24px; }}
    .stat-label, .stat-sub {{ color: #555; }}
    .main {{ padding: 16px 24px; }}
    .card {{ border: 1px solid #ddd; background: white; break-inside: avoid; }}
    .card-title {{ color: #555; }}
    .cat-card .card-title {{ color: #222; font-weight: 700; }}
    .skill-bar-fill {{ background: #333 !important; }}
    .skill-name, .skill-val {{ color: #111; }}
    .section-title {{ color: #222; border-color: #ddd; }}
    th {{ color: #555; }} td {{ color: #111; border-color: #eee; }}
    .badge.pass {{ background: #e8f5e9; color: #2e7d32; border-color: #a5d6a7; }}
    .badge.fail {{ background: #ffebee; color: #c62828; border-color: #ef9a9a; }}
    .type-tag {{ color: #555; border-color: #ddd; background: #f5f5f5; }}
    .grid-2, .cat-grid {{ grid-template-columns: 1fr 1fr; }}
    .email-blur {{ filter: none !important; }}
    .table-wrap {{ margin-bottom: 16px; }}
    a {{ text-decoration: none; color: inherit; }}
  }}
</style>
</head>
<body>

<header class="hero">
  <p class="hero-tag">01Founders · Portfolio Export</p>
  <h1>Hello,<br/><span>{login}</span></h1>
  <div class="hero-meta">
    <div><b>Campus</b>{campus}</div>
    <div><b>Email</b><span class="email-blur" onclick="this.classList.toggle('revealed')" title="Click to reveal">{email}</span></div>
    <div><b>Joined</b>{joined}</div>
    <div><b>Generated</b>{generated}</div>
  </div>
  <button class="pdf-btn" onclick="window.print()">Export as PDF</button>
</header>

<!-- STATS BAR -->
<div class="stats-bar">
  <div class="stat-cell">
    <div class="stat-num green">{d['total_xp_fmt']}</div>
    <div class="stat-label">Total XP</div>
  </div>
  <div class="stat-cell">
    <div class="stat-num blue">{d['projects_total']}</div>
    <div class="stat-label">Projects Attempted</div>
  </div>
  <div class="stat-cell">
    <div class="stat-num green">{d['projects_passed']}</div>
    <div class="stat-label">Projects Passed</div>
  </div>
  <div class="stat-cell">
    <div class="stat-num pink">{d['audits_given_count']}</div>
    <div class="stat-label">Audits Given</div>
    <div class="stat-sub">{d['total_up_fmt']} uploaded</div>
  </div>
  <div class="stat-cell">
    <div class="stat-num blue">{d['audits_received_count']}</div>
    <div class="stat-label">Audits Received</div>
    <div class="stat-sub">{d['total_down_fmt']} reviewed</div>
  </div>
  <div class="stat-cell">
    <div class="stat-num green">{d['audit_ratio_fmt']}</div>
    <div class="stat-label">Audit Ratio</div>
  </div>
</div>

<main class="main">

  <!-- ROW 1: XP + Audit Ratio -->
  <div class="grid-2">
    <div class="card">
      <p class="card-title">XP Growth Over Time</p>
      <div class="chart-wrap"><canvas id="xpChart"></canvas></div>
    </div>
    <div class="card">
      <p class="card-title">Audit Ratio</p>
      <div class="ratio-display">
        <div class="ratio-big">{d['audit_ratio_fmt']}</div>
        <div class="ratio-label">Given ÷ Received</div>
        <div class="ratio-detail">
          <span><b>{d['total_up_fmt']}</b>Given (Up)</span>
          <span><b>{d['total_down_fmt']}</b>Received (Down)</span>
        </div>
      </div>
      <canvas id="auditChart" style="max-height:80px;margin-top:16px"></canvas>
    </div>
  </div>

  <!-- ROW 2: Skills + XP per project -->
  <div class="grid-2">
    <div class="card">
      <p class="card-title">Skills</p>
      {top_skills_html or '<p style="color:var(--muted);font-size:13px;padding:8px 0">No skill transactions found.</p>'}
    </div>
    <div class="card">
      <p class="card-title">Top XP Projects</p>
      <div class="chart-wrap" style="height:280px"><canvas id="barChart"></canvas></div>
    </div>
  </div>

  <!-- SKILLS BY CATEGORY -->
  <p class="section-title" style="margin-top:8px">Skills by Category</p>
  <div class="cat-grid">
    {category_cards_html}
  </div>

  <!-- PROJECTS TABLE -->
  <p class="section-title">Projects</p>
  <input class="search-bar" type="text" id="searchInput" placeholder="Search projects..." oninput="filterTable('projectsTable', this.value)"/>
  <div class="table-wrap">
    <table id="projectsTable">
      <thead><tr><th>Name</th><th>Type</th><th>Grade</th><th>Status</th><th>Date</th></tr></thead>
      <tbody>
        {projects_rows or '<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:32px">No projects found.</td></tr>'}
      </tbody>
    </table>
  </div>

  <!-- AUDITS TABS -->
  <p class="section-title">Audit History</p>
  <div class="card" style="padding:0;margin-bottom:32px">
    <div class="tabs">
      <div class="tab active" onclick="switchTab('given')">Audits Given ({d['audits_given_count']})</div>
      <div class="tab" onclick="switchTab('received')">Audits Received ({d['audits_received_count']})</div>
    </div>
    <div style="padding:0 20px 20px">
      <div id="tab-given" class="tab-panel active">
        <table>
          <thead><tr><th>Project</th><th>Grade</th><th>Result</th><th>Date</th></tr></thead>
          <tbody>{given_rows}</tbody>
        </table>
      </div>
      <div id="tab-received" class="tab-panel">
        <table>
          <thead><tr><th>Project</th><th>Grade</th><th>Result</th><th>Date</th></tr></thead>
          <tbody>{received_rows}</tbody>
        </table>
      </div>
    </div>
  </div>

</main>

<footer>
  <span>⬡ 01Founders Portfolio — {login}</span>
  <span>Exported {generated}</span>
</footer>

<script>
// ── DATA ──
const xpLabels     = {xp_labels};
const xpValues     = {xp_values};
const xpAmounts    = {xp_amounts};
const xpProjects   = {xp_projects_js};
const skillLabels  = {skill_labels_js};
const skillValues  = {skill_values_js};
const totalUp      = {d['total_up'] or 0};
const totalDown    = {d['total_down'] or 0};

// ── XP LINE CHART ──
if (xpLabels.length > 0) {{
  new Chart(document.getElementById('xpChart').getContext('2d'), {{
    type: 'line',
    data: {{ labels: xpLabels, datasets: [{{ data: xpValues, borderColor: '#7fff6e', backgroundColor: 'rgba(127,255,110,.08)', borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, fill: true, tension: .4 }}] }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{
        title: (i) => xpProjects[i[0].dataIndex] || xpLabels[i[0].dataIndex],
        label: (i) => ` +${{xpAmounts[i.dataIndex].toLocaleString()}} XP  (total: ${{i.raw.toLocaleString()}})`
      }}, backgroundColor: '#18181f', borderColor: '#2a2a38', borderWidth: 1, titleColor: '#e8e8f0', bodyColor: '#7fff6e' }} }},
      scales: {{ x: {{ ticks: {{ color: '#666680', font: {{ family: 'DM Mono', size: 10 }}, maxTicksLimit: 8, maxRotation: 0 }}, grid: {{ display: false }} }}, y: {{ grid: {{ color: 'rgba(255,255,255,.05)' }}, ticks: {{ color: '#666680', font: {{ family: 'DM Mono', size: 10 }}, maxTicksLimit: 5, callback: (v) => v >= 1e6 ? (v/1e6).toFixed(1)+'M' : v >= 1e3 ? (v/1e3).toFixed(0)+'K' : v }} }} }}
    }}
  }});
}}

  // ── AUDIT DOUGHNUT ──
  if (totalUp > 0 || totalDown > 0) {{
  new Chart(document.getElementById('auditChart').getContext('2d'), {{
    type: 'doughnut',
    data: {{ labels: ['Given (Up)', 'Received (Down)'], datasets: [{{ data: [totalUp, totalDown], backgroundColor: ['rgba(127,255,110,.7)', 'rgba(110,184,255,.7)'], borderWidth: 0, hoverOffset: 4 }}] }},
    options: {{
      responsive: true, maintainAspectRatio: true,
      plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#666680', font: {{ family: 'DM Mono', size: 10 }}, padding: 16 }} }}, tooltip: {{ backgroundColor: '#18181f', borderColor: '#2a2a38', borderWidth: 1, titleColor: '#e8e8f0', bodyColor: '#7fff6e' }} }},
      cutout: '65%'
    }}
  }});
}}

  // ── XP BAR CHART ──
  const barData = xpAmounts.map((a,i) => ({{amt:a,proj:xpProjects[i]}})).filter(x=>x.amt>0).sort((a,b)=>b.amt-a.amt).slice(0,15);
  if (barData.length > 0) {{
    new Chart(document.getElementById('barChart').getContext('2d'), {{
      type: 'bar',
      data: {{ labels: barData.map(x=>x.proj), datasets: [{{ data: barData.map(x=>x.amt), backgroundColor: 'rgba(255,110,180,.6)', borderRadius: 2 }}] }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }}, tooltip: {{ backgroundColor: '#18181f', borderColor: '#2a2a38', borderWidth: 1, titleColor: '#e8e8f0', bodyColor: '#ff6eb4' }} }},
        scales: {{ x: {{ ticks: {{ color: '#666680', font: {{ family: 'DM Mono', size: 9 }}, maxRotation: 45, minRotation: 45 }}, grid: {{ display: false }} }}, y: {{ ticks: {{ color: '#666680', font: {{ family: 'DM Mono', size: 10 }}, maxTicksLimit: 4, callback: (v) => v >= 1e6 ? (v/1e6).toFixed(1)+'M' : v >= 1e3 ? (v/1e3).toFixed(0)+'K' : v }}, grid: {{ color: 'rgba(255,255,255,.05)' }} }} }}
      }}
    }});
  }}

// ── SEARCH ──
function filterTable(id, q) {{
  document.querySelectorAll('#' + id + ' tbody tr').forEach(r =>
    r.style.display = r.textContent.toLowerCase().includes(q.toLowerCase()) ? '' : 'none'
  );
}}

// ── TABS ──
function switchTab(name) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelector(`[onclick="switchTab('${{name}}')"]`).classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}}
</script>
</body>
</html>"""


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    print("\n╔══════════════════════════════════════╗")
    print("║  01Founders Portfolio Exporter       ║")
    print("╚══════════════════════════════════════╝\n")

    config = load_env()
    token, student_login = config["token"], config["login"]
    if not token or not student_login:
        print("✗ Token and login are both required. Exiting.")
        sys.exit(1)

    print(f"\n[1/3] Fetching data for '{student_login}'...")
    raw = fetch_all(token, student_login)

    # Detect expired token: user profile came back empty
    if not raw.get("user"):
        print("\n  ⚠ No data returned — token may have expired.")
        if not sys.stdin.isatty():
            print("  ✗ Running in CI — update the JWT_TOKEN secret in GitHub:")
            print("    Repo → Settings → Secrets and variables → Actions → JWT_TOKEN")
            sys.exit(1)
        _keychain_set("")   # clear stale token
        print()
        print("  Get a fresh token:")
        print("  1. Open Google Chrome and go to https://learn.01founders.co")
        print("  2. Press F12 to open DevTools")
        print("  3. Click the 'Application' tab at the top of DevTools")
        print("  4. In the left sidebar, find 'Storage' and expand it")
        print("  5. Click 'Local Storage' to expand it")
        print("  6. Click 'https://learn.01founders.co'")
        print("  7. Find the key 'jwt-token' in the table")
        print("  8. Copy the value (it starts with eyJ...)")
        print()
        new_token = input("  Paste new JWT token here: ").strip()
        if not new_token:
            print("✗ No token provided. Exiting.")
            sys.exit(1)
        _keychain_set(new_token)
        print("  ✓ New token saved to Keychain. Re-fetching...\n")
        raw = fetch_all(new_token, student_login)

    print("\n[2/3] Processing...")
    processed = process(raw, student_login)
    print(f"  ✓ XP: {processed['total_xp']:,}")
    print(f"  ✓ Skills: {len(processed['skills'])}")
    print(f"  ✓ Projects: {processed['projects_total']} ({processed['projects_passed']} passed)")
    print(f"  ✓ Audits given: {processed['audits_given_count']}  |  received: {processed['audits_received_count']}")
    print(f"  ✓ Audit ratio: {processed['audit_ratio_fmt']}")

    print("\n[3/3] Building HTML report...")
    html = build_html(processed)

    html_file = f"{student_login}_01founders_portfolio.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✓ HTML report → {html_file}")

    json_file = f"{student_login}_01founders_raw.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, default=str)
    print(f"✓ Raw backup  → {json_file}")
    print("\n  Open the HTML file in your browser!\n")


if __name__ == "__main__":
    main()
