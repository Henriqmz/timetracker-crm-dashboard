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

LOGIN_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <title>Login 2FA — TimeTracker Analytics</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; display: grid; place-items: center; min-height: 100vh; margin: 0; }
    .card { background: #1e293b; padding: 2rem; border-radius: 12px; width: 340px; box-shadow: 0 10px 30px rgba(0,0,0,.35); }
    h1 { font-size: 1.25rem; margin-top: 0; }
    label { display: block; margin-top: 1rem; font-size: .85rem; color: #94a3b8; }
    input { width: 100%; padding: .6rem; margin-top: .25rem; border-radius: 6px; border: 1px solid #334155; background: #0f172a; color: #fff; box-sizing: border-box; }
    button { width: 100%; margin-top: 1.5rem; padding: .75rem; border: 0; border-radius: 6px; background: #38bdf8; color: #0f172a; font-weight: 700; cursor: pointer; }
    .err { color: #fca5a5; font-size: .85rem; margin-top: .75rem; }
  </style>
</head>
<body>
  <form class="card" method="POST" action="/login">
    <h1>TimeTracker Analytics (2FA)</h1>
    <label>Usuário<input name="username" value="admin" required /></label>
    <label>Senha<input type="password" name="password" required /></label>
    <label>Código 2FA (6 dígitos)<input name="totp" inputmode="numeric" maxlength="6" required /></label>
    {error_block}
    <button type="submit">Entrar</button>
  </form>
</body>
</html>
"""

DASHBOARD_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <title>TimeTracker Analytics Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 2rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.25rem; margin-top: 1.5rem; }
    .card { background: #1e293b; padding: 1.25rem; border-radius: 12px; }
    .kpi { font-size: 2rem; font-weight: 800; color: #38bdf8; }
    ul { padding-left: 1.2rem; }
    li { margin-bottom: .4rem; font-size: .9rem; }
  </style>
</head>
<body>
  <h1>TimeTracker Analytics — Visão Consolidada</h1>
  <div class="card">Total Apontado: <span class="kpi" id="totalHours">--</span> horas</div>
  <div class="grid">
    <div class="card"><h3>Horas por Pessoa</h3><canvas id="userChart"></canvas></div>
    <div class="card"><h3>Horas por Projeto</h3><canvas id="projectChart"></canvas></div>
    <div class="card"><h3>Alertas de Auditoria</h3><ul id="alertsList"></ul></div>
  </div>
  <script>
    fetch('/api/metrics').then(r => r.json()).then(data => {
      document.getElementById('totalHours').textContent = data.total_hours.toFixed(1);
      new Chart(document.getElementById('userChart'), {
        type: 'bar',
        data: { labels: data.by_user.map(x => x.user_name), datasets: [{ label: 'Horas', data: data.by_user.map(x => x.hours), backgroundColor: '#38bdf8' }] }
      });
      new Chart(document.getElementById('projectChart'), {
        type: 'doughnut',
        data: { labels: data.by_project.map(x => x.project_name), datasets: [{ data: data.by_project.map(x => x.hours), backgroundColor: ['#38bdf8', '#818cf8', '#34d399', '#fbbf24'] }] }
      });
      const ul = document.getElementById('alertsList');
      data.alerts.forEach(a => {
        const li = document.createElement('li');
        li.textContent = `[${a.severity}] ${a.work_date} • ${a.user_name}: ${a.message}`;
        ul.appendChild(li);
      });
    });
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
