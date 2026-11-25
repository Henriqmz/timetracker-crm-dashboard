from __future__ import annotations

import argparse
import html
import json
import os
import secrets
from http import cookies
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .database import AnalyticsDB
from .seed_demo import seed_demo_database
from .totp import generate_totp, verify_totp

SESSIONS: set[str] = set()

COMMON_THEME_CSS = """
  :root, [data-theme="dark"] {
    --bg: #050a0f;
    --surface: #0b1219;
    --surface-2: #111b24;
    --surface-hover: #172430;
    --text: #f0f7fc;
    --muted: #9ab3c8;
    --accent: #d4f1ff;
    --accent-ink: #050a0f;
    --accent-border: rgba(212, 241, 255, 0.34);
    --border: rgba(212, 241, 255, 0.14);
    --shadow: 0 24px 54px rgba(0, 0, 0, 0.55);
  }
  [data-theme="light"] {
    --bg: #f0f7fc;
    --surface: #ffffff;
    --surface-2: #e3eef6;
    --surface-hover: #d5e5f1;
    --text: #050a0f;
    --muted: #395064;
    --accent: #050a0f;
    --accent-ink: #f0f7fc;
    --accent-border: rgba(5, 10, 15, 0.3);
    --border: rgba(5, 10, 15, 0.14);
    --shadow: 0 18px 40px rgba(5, 10, 15, 0.1);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    transition: background-color 0.25s ease, color 0.25s ease;
  }
  .theme-btn {
    display: inline-flex; align-items: center; gap: 0.45rem;
    padding: 0.45rem 0.85rem; border-radius: 999px;
    border: 1px solid var(--accent-border); background: var(--surface); color: var(--text);
    font: inherit; font-size: 0.8rem; font-weight: 700; cursor: pointer;
  }
  .theme-btn:hover { background: var(--surface-hover); }
"""

LOGIN_HTML = f"""<!doctype html>
<html lang="pt-BR" data-theme="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Login 2FA — TimeTracker Analytics</title>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet" />
  <style>
    {COMMON_THEME_CSS}
    body {{ display: grid; place-items: center; padding: 24px; }}
    .card {{
      background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--accent);
      padding: 2rem; border-radius: 18px; width: min(390px, 100%); box-shadow: var(--shadow);
    }}
    .top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; }}
    h1 {{ font-size: 1.22rem; margin: 0; font-weight: 800; }}
    p {{ margin: 0.35rem 0 0; font-size: 0.84rem; color: var(--muted); }}
    label {{ display: block; margin-top: 1rem; font-size: 0.82rem; font-weight: 600; color: var(--muted); }}
    input {{
      width: 100%; padding: 0.65rem 0.8rem; margin-top: 0.3rem; border-radius: 9px;
      border: 1px solid var(--border); background: var(--bg); color: var(--text); font: inherit;
    }}
    .submit-btn {{
      width: 100%; margin-top: 1.5rem; padding: 0.78rem; border: 0; border-radius: 10px;
      background: var(--accent); color: var(--accent-ink); font: inherit; font-weight: 800; cursor: pointer;
    }}
    .err {{ color: #fca5a5; font-size: 0.84rem; margin-top: 0.75rem; }}
  </style>
</head>
<body>
  <form class="card" method="POST" action="/login">
    <div class="top">
      <div>
        <h1>TimeTracker 2FA</h1>
        <p>Autenticação TOTP (RFC 6238)</p>
      </div>
      <button id="themeToggle" class="theme-btn" type="button"><span id="themeIcon">☀</span></button>
    </div>
    <label>Usuário<input name="username" value="admin" required /></label>
    <label>Senha<input type="password" name="password" required /></label>
    <label>Código 2FA (6 dígitos)<input name="totp" inputmode="numeric" maxlength="6" placeholder="000000" required /></label>
    {{error_block}}
    <button class="submit-btn" type="submit">Entrar no Painel</button>
  </form>
  <script>
    const root = document.documentElement;
    function applyTheme(t) {{
      root.setAttribute("data-theme", t);
      localStorage.setItem("tt-theme", t);
      document.getElementById("themeIcon").textContent = t === "light" ? "☾" : "☀";
    }}
    applyTheme(localStorage.getItem("tt-theme") || "dark");
    document.getElementById("themeToggle").addEventListener("click", () => {{
      applyTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark");
    }});
  </script>
</body>
</html>
"""

DASHBOARD_HTML = f"""<!doctype html>
<html lang="pt-BR" data-theme="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>TimeTracker Analytics Dashboard</title>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    {COMMON_THEME_CSS}
    body {{ padding: 26px 18px 42px; }}
    .shell {{
      max-width: 1160px; margin: 0 auto; background: var(--surface);
      border: 1px solid var(--border); border-radius: 20px; box-shadow: var(--shadow); overflow: hidden;
    }}
    .shell-header {{
      padding: 20px 26px; border-bottom: 1px solid var(--border); background: var(--surface-2);
      display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 1rem;
    }}
    .brand {{ display: flex; align-items: center; gap: 0.8rem; }}
    .logo-mark {{
      width: 36px; height: 36px; border-radius: 10px; background: var(--accent); color: var(--accent-ink);
      display: grid; place-items: center; font-weight: 900; font-size: 0.9rem;
    }}
    .brand-title {{ font-weight: 800; font-size: 1.08rem; }}
    .brand-sub {{ font-size: 0.78rem; color: var(--muted); }}
    .shell-body {{ padding: 24px 26px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.9rem; margin-bottom: 20px; }}
    .kpi {{
      background: var(--surface-2); border: 1px solid var(--border); border-left: 4px solid var(--accent);
      border-radius: 12px; padding: 0.95rem 1.1rem;
    }}
    .kpi-label {{ font-size: 0.72rem; color: var(--muted); font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }}
    .kpi-val {{ font-size: 1.7rem; font-weight: 800; color: var(--accent); margin-top: 0.2rem; }}
    .grid {{ display: grid; grid-template-columns: 1.1fr 0.9fr 1fr; gap: 1rem; }}
    .card {{
      background: var(--surface-2); border: 1px solid var(--border); border-radius: 14px; padding: 1.2rem;
    }}
    .card h3 {{ margin: 0 0 0.9rem; font-size: 0.98rem; }}
    ul {{ list-style: none; padding: 0; margin: 0; }}
    li {{
      padding: 0.65rem 0; border-bottom: 1px solid var(--border);
      font-size: 0.83rem; line-height: 1.45;
    }}
    li:last-child {{ border-bottom: 0; }}
    .mono {{ font-family: "JetBrains Mono", monospace; font-size: 0.74rem; color: var(--muted); }}
    @media (max-width: 920px) {{
      .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header class="shell-header">
      <div class="brand">
        <span class="logo-mark">TT</span>
        <div>
          <div class="brand-title">TimeTracker Analytics</div>
          <div class="brand-sub">Compensação UTC-3 · Auditoria de Anomalias · Sessão 2FA TOTP</div>
        </div>
      </div>
      <button id="themeToggle" class="theme-btn" type="button">
        <span id="themeIcon">☀</span>
        <span id="themeLabel">Modo Claro</span>
      </button>
    </header>

    <main class="shell-body">
      <section class="kpi-grid">
        <div class="kpi"><div class="kpi-label">Total Apontado</div><div class="kpi-val" id="totalHours">--</div></div>
        <div class="kpi"><div class="kpi-label">Colaboradores</div><div class="kpi-val" id="totalUsers">--</div></div>
        <div class="kpi"><div class="kpi-label">Projetos Ativos</div><div class="kpi-val" id="totalProjects">--</div></div>
        <div class="kpi"><div class="kpi-label">Alertas Auditoria</div><div class="kpi-val" id="totalAlerts">--</div></div>
      </section>

      <section class="grid">
        <div class="card"><h3>Horas por Pessoa</h3><canvas id="userChart"></canvas></div>
        <div class="card"><h3>Horas por Projeto</h3><canvas id="projectChart"></canvas></div>
        <div class="card"><h3>Alertas de Auditoria</h3><ul id="alertsList"></ul></div>
      </section>
    </main>
  </div>

  <script>
    const root = document.documentElement;
    let metricsCache = null;
    let userChartInst = null;
    let projChartInst = null;

    function applyTheme(t) {{
      root.setAttribute("data-theme", t);
      localStorage.setItem("tt-theme", t);
      document.getElementById("themeIcon").textContent = t === "light" ? "☾" : "☀";
      document.getElementById("themeLabel").textContent = t === "light" ? "Modo Escuro" : "Modo Claro";
      if (metricsCache) renderCharts(metricsCache);
    }}

    function renderCharts(data) {{
      const isLight = root.getAttribute("data-theme") === "light";
      const txtColor = isLight ? "#050a0f" : "#f0f7fc";
      const gridColor = isLight ? "rgba(5,10,15,0.1)" : "rgba(212,241,255,0.1)";
      const barColor = isLight ? "#0b2540" : "#bfe9ff";

      if (userChartInst) userChartInst.destroy();
      if (projChartInst) projChartInst.destroy();

      userChartInst = new Chart(document.getElementById("userChart"), {{
        type: "bar",
        data: {{
          labels: data.by_user.map(x => x.user_name),
          datasets: [{{ label: "Horas", data: data.by_user.map(x => x.hours), backgroundColor: barColor, borderRadius: 6 }}]
        }},
        options: {{
          plugins: {{ legend: {{ labels: {{ color: txtColor }} }} }},
          scales: {{
            x: {{ ticks: {{ color: txtColor }}, grid: {{ color: gridColor }} }},
            y: {{ ticks: {{ color: txtColor }}, grid: {{ color: gridColor }} }}
          }}
        }}
      }});

      projChartInst = new Chart(document.getElementById("projectChart"), {{
        type: "doughnut",
        data: {{
          labels: data.by_project.map(x => x.project_name),
          datasets: [{{ data: data.by_project.map(x => x.hours), backgroundColor: isLight ? ["#050a0f", "#2b4c6f", "#5b86ad"] : ["#d4f1ff", "#7cc6ee", "#3a7ca5"], borderWidth: 0 }}]
        }},
        options: {{ animation: false, plugins: {{ legend: {{ labels: {{ color: txtColor }} }} }} }}
      }});
    }}

    applyTheme(localStorage.getItem("tt-theme") || "dark");
    document.getElementById("themeToggle").addEventListener("click", () => {{
      applyTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark");
    }});

    fetch("/api/metrics").then(r => r.json()).then(data => {{
      metricsCache = data;
      document.getElementById("totalHours").textContent = data.total_hours.toFixed(1) + "h";
      document.getElementById("totalUsers").textContent = data.by_user.length;
      document.getElementById("totalProjects").textContent = data.by_project.length;
      document.getElementById("totalAlerts").textContent = data.alerts.length;
      renderCharts(data);

      const ul = document.getElementById("alertsList");
      ul.innerHTML = "";
      data.alerts.forEach(a => {{
        const li = document.createElement("li");
        li.innerHTML = `<span class="mono">[${{a.severity}}] ${{a.work_date}}</span><br /><strong>${{a.user_name}}:</strong> ${{a.message}}`;
        ul.appendChild(li);
      }});
    }});
  </script>
</body>
</html>
"""


def make_handler(db: AnalyticsDB, admin_user: str, admin_pass: str, totp_secret: str):
    class DashboardHandler(BaseHTTPRequestHandler):
        def _is_authenticated(self) -> bool:
            raw_cookie = self.headers.get("Cookie", "")
            jar = cookies.SimpleCookie(raw_cookie)
            token = jar.get("session_id")
            return bool(token and token.value in SESSIONS)

        def _send_html(self, body: str, status: int = 200) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:
            if self.path == "/login":
                self._send_html(LOGIN_HTML.replace("{error_block}", ""))
                return
            if not self._is_authenticated():
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
                return
            if self.path == "/api/metrics":
                payload = json.dumps(db.get_dashboard_metrics(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self._send_html(DASHBOARD_HTML)

        def do_POST(self) -> None:
            if self.path != "/login":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            user = (form.get("username") or [""])[0]
            pw = (form.get("password") or [""])[0]
            code = (form.get("totp") or [""])[0]
            if user == admin_user and pw == admin_pass and verify_totp(totp_secret, code):
                sid = secrets.token_hex(24)
                SESSIONS.add(sid)
                self.send_response(302)
                self.send_header("Set-Cookie", f"session_id={sid}; HttpOnly; SameSite=Strict; Path=/")
                self.send_header("Location", "/")
                self.end_headers()
                return
            err = f'<div class="err">{html.escape("Credenciais ou código 2FA inválidos.")}</div>'
            self._send_html(LOGIN_HTML.replace("{error_block}", err), status=401)

    return DashboardHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="TimeTracker 2FA Analytics Dashboard")
    parser.add_argument("--demo", action="store_true", help="Popula banco demo e exibe credenciais de teste")
    args = parser.parse_args()

    db_path = Path(os.getenv("DB_PATH", "data/timetracker.db"))
    if args.demo and not db_path.exists():
        seed_demo_database(db_path)

    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("DASHBOARD_PORT", "8088"))
    admin_user = os.getenv("DASHBOARD_ADMIN_USER", "admin")
    admin_pass = os.getenv("DASHBOARD_ADMIN_PASSWORD", "demo1234")
    totp_secret = os.getenv("DASHBOARD_TOTP_SECRET", "JBSWY3DPEHPK3PXP")

    db = AnalyticsDB(db_path)
    server = HTTPServer((host, port), make_handler(db, admin_user, admin_pass, totp_secret))
    print(f"Dashboard rodando em http://{host}:{port}")
    if args.demo:
        print(f"[DEMO] Usuário: {admin_user} | Senha: {admin_pass} | Código 2FA agora: {generate_totp(totp_secret)}")
    server.serve_forever()


if __name__ == "__main__":
    main()
