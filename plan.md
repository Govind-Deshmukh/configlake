# ConfigLake — Security Fix Plan

Status: **AWAITING REVIEW**
Audited: 2026-06-06
Last updated: 2026-06-06

---

## How to read this

Each phase is a self-contained unit of work. Phase 1 must ship before anyone uses this with real secrets.
Phases 2 and 3 are required before calling it production-ready. Phase 4 is hardening for serious deployments.

Every item lists: what file changes, what the fix is, and why it matters.

---

## Phase 1 — Critical: Exploitable Right Now

**Target:** Fix before ANY real usage. These are live vulnerabilities.
**Estimated effort:** 1–2 days

---

### 1.1 Fix broken `write` role — universal access bug

**File:** `app/routes/api.py:207, 291, 330`

**Problem:** `require_project_permission('write')` is used but `'write'` is not in the role
hierarchy `{'owner': 3, 'maintainer': 2, 'reader': 1}`. Unknown keys resolve to level `0`.
Every authenticated user passes `user_level >= 0`. Non-owners can read/write/delete any
project's configs and secrets.

**Fix:** Replace every `'write'` with `'maintainer'` in api.py.

```python
# Before
@require_project_permission('write')

# After
@require_project_permission('maintainer')
```

Affected routes: `manage_config`, `delete_config_key`, `manage_secret`.

---

### 1.2 Fix IP whitelist bypass via raw X-Forwarded-For

**Files:** `app/utils/security.py:12`, `app/__init__.py:17`

**Problem:** `security.py` reads the raw `HTTP_X_FORWARDED_FOR` environ header directly,
bypassing `ProxyFix` entirely. An attacker sets `X-Forwarded-For: <whitelisted IP>` and
bypasses the whitelist from any IP.

**Fix part A** — Let ProxyFix handle the forwarded IP too:
```python
# app/__init__.py:17
# Before
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
# After
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)
```

**Fix part B** — Use Flask's already-resolved remote address:
```python
# app/utils/security.py:12
# Before
client_ip = request.environ.get('HTTP_X_FORWARDED_FOR') or request.remote_addr
# After
client_ip = request.remote_addr
```

ProxyFix with `x_for=1` already puts the correct IP into `request.remote_addr`.

---

### 1.3 Auth-gate setup endpoints after setup is complete

**File:** `app/routes/setup.py`

**Problem:** `/setup/restart`, `/setup/upload-db`, `/setup/generate-key`, `/setup/test-db`
have zero authentication. Any unauthenticated user can restart the server (DoS) or upload
files to `instance/`.

**Fix:** Add a `_setup_only()` guard to each. If users exist, reject with 403.

```python
def _setup_only():
    from app.models import User
    if User.query.count() > 0:
        return jsonify({'error': 'Setup already completed'}), 403
    return None

@setup_bp.route('/restart', methods=['POST'])
def restart():
    err = _setup_only()
    if err: return err
    # ... existing code

@setup_bp.route('/generate-key', methods=['POST'])
def generate_key():
    err = _setup_only()
    if err: return err
    # ... existing code

# Same for /test-db and /upload-db
```

Note: The admin restart is already at `POST /admin/restart` behind `@login_required`.
The setup `/restart` is only needed during first-time setup before any users exist.

---

### 1.4 Fix open redirect in login

**File:** `app/routes/auth.py:25-26`

**Problem:** `next` query parameter is redirected to without validation. An attacker sends
`/auth/login?next=https://evil.com` → user logs in → lands on attacker's site.

**Fix:**
```python
from urllib.parse import urlparse

# Before
next_page = request.args.get('next')
return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))

# After
next_page = request.args.get('next')
if next_page:
    parsed = urlparse(next_page)
    if parsed.netloc != '' or parsed.scheme != '':
        next_page = None  # External URL — reject it
return redirect(next_page or url_for('main.dashboard'))
```

---

### 1.5 Enable CSRF protection

**Files:** `app/__init__.py`, `config.py`, all HTML templates with forms, all JS fetch calls

**Problem:** Flask-WTF is installed but `CSRFProtect` is never initialized. Every POST
endpoint is vulnerable to cross-site request forgery.

**Fix part A** — Initialize in `create_app()`:
```python
# app/__init__.py
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    csrf.init_app(app)
    # ... rest of init

    # Exempt the read-only API endpoints that use Bearer tokens
    csrf.exempt(api_bp)
    csrf.exempt(setup_bp)   # Setup has its own _setup_only() guard
```

**Fix part B** — Add to `config.py`:
```python
WTF_CSRF_TIME_LIMIT = 3600  # 1 hour
```

**Fix part C** — Add CSRF token to every HTML form:
```html
<form method="POST">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    ...
</form>
```

**Fix part D** — Add header to every `fetch()` POST in JS:
```javascript
// Add a meta tag to base.html
<meta name="csrf-token" content="{{ csrf_token() }}">

// In all JS fetch() calls:
headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
}
```

Affected JS files: `environment.html`, `admin/panel.html`, `setup/index.html`.

---

## Phase 2 — High: Serious Weaknesses

**Target:** Fix before the first real team or production deployment.
**Estimated effort:** 3–4 days

---

### 2.1 Generate and persist SECRET_KEY during setup

**Files:** `config.py`, `app/routes/setup.py`

**Problem:** `SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()` — if not
set, every process restart generates a new key, invalidating all sessions immediately.
Setup wizard writes `CONFIGLAKE_MASTER_KEY` to `.env` but never writes `SECRET_KEY`.

**Fix:** In `setup.py` `complete()` route, generate and persist `SECRET_KEY` alongside the
master key:
```python
import secrets as secrets_module
_write_env('SECRET_KEY', secrets_module.token_hex(32))
_write_env('CONFIGLAKE_MASTER_KEY', master_key)
```

Also harden `config.py` to fail loudly rather than silently use a random key:
```python
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    import warnings
    warnings.warn(
        "SECRET_KEY not set — using a random key. All sessions will be lost on restart.",
        stacklevel=2
    )
    SECRET_KEY = os.urandom(32).hex()
```

---

### 2.2 Set session cookie security flags

**File:** `config.py`

**Problem:** Session cookie has no `Secure`, `HttpOnly`, or `SameSite` flags. On HTTP,
the cookie travels in cleartext. JavaScript can read it. Missing `SameSite` weakens CSRF
defense.

**Fix:**
```python
SESSION_COOKIE_SECURE   = os.environ.get('SSL_MODE', '') in ('self-signed', 'manual')
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
REMEMBER_COOKIE_SECURE   = SESSION_COOKIE_SECURE
REMEMBER_COOKIE_HTTPONLY = True
```

---

### 2.3 Add security response headers

**File:** `app/__init__.py`

**Problem:** Zero `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`,
`Strict-Transport-Security`, or `Referrer-Policy`. UI is embeddable in iframes
(clickjacking). XSS has unlimited blast radius.

**Fix:** Add to `create_app()` after_request:
```python
@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options']           = 'DENY'
    response.headers['X-Content-Type-Options']    = 'nosniff'
    response.headers['Referrer-Policy']           = 'strict-origin-when-cross-origin'
    response.headers['X-XSS-Protection']          = '0'  # Modern browsers: disable legacy
    response.headers['Content-Security-Policy']   = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; "
        "connect-src 'self';"
    )
    ssl_mode = os.environ.get('SSL_MODE', '')
    if ssl_mode in ('self-signed', 'manual'):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response
```

Note: `'unsafe-inline'` for scripts is a CSP compromise because the templates use inline
`<script>` blocks. A follow-up phase should move all JS to static files to allow removing
`'unsafe-inline'`.

---

### 2.4 Hash API tokens at storage

**Files:** `app/models/api_token.py`, `app/routes/api.py` (create/revoke/toggle),
`app/utils/security.py` (require_api_token), `app/utils/encryption.py`

**Problem:** API tokens stored as plaintext. DB read access = immediate full access to all
secrets via all tokens.

**Fix:** Store `sha256(token)`. Return the raw token only at creation time (it can never be
retrieved again — same pattern as GitHub PATs).

```python
# app/utils/encryption.py — add:
import hashlib

@staticmethod
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
```

```python
# api.py create_api_token — store hash:
token = EncryptionManager.generate_api_token()
token_hash = EncryptionManager.hash_token(token)
api_token = APIToken(token=token_hash, ...)  # store hash
return jsonify({'token': token, ...})        # return raw once
```

```python
# security.py require_api_token — look up by hash:
from app.utils.encryption import EncryptionManager
token_hash = EncryptionManager.hash_token(token)
api_token = APIToken.query.filter_by(token=token_hash, is_active=True).first()
```

Migration: existing tokens in DB are plaintext — they need to be invalidated and reissued,
OR a `token_version` column is added and the lookup is tried on both formats during a
transition window, then the plaintext column dropped.

---

### 2.5 Add rate limiting and account lockout

**Files:** `app/__init__.py`, `app/routes/auth.py`, `requirements.txt`

**Problem:** Login endpoint has no throttling. Brute force at network speed is possible.

**Fix:** Add `flask-limiter` to requirements.txt.

```python
# app/__init__.py
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=[])

def create_app():
    ...
    limiter.init_app(app)
```

```python
# app/routes/auth.py — login route:
from app import limiter

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 30 per hour")
def login():
    ...
```

```python
# app/routes/api.py — API token endpoints:
@limiter.limit("60 per minute")
@require_api_token()
def get_secrets(...):
```

Also add a failed-attempt counter to the `User` model:
```python
failed_login_attempts = db.Column(db.Integer, default=0)
locked_until = db.Column(db.DateTime, nullable=True)
```

Lock the account for 15 minutes after 10 consecutive failures.

---

### 2.6 Close open registration

**File:** `app/routes/auth.py`

**Problem:** Anyone who can reach the server can create an account. For a secrets manager
this is unacceptable.

**Fix options (pick one):**

**Option A — Disable registration entirely, admin creates users:**
Add `REGISTRATION_ENABLED = os.environ.get('REGISTRATION_ENABLED', 'false').lower() == 'true'`
to config. Default is disabled. The setup wizard already creates the first admin via its own
flow.

**Option B — Admin-issued invite tokens:**
Admin generates a single-use token, shares it out of band. Registration requires a valid
token. Tokens expire after 24 hours.

Recommended: Option A for now (simpler, implementable in one hour), Option B as a follow-up.

---

### 2.7 Protect admin export with a password

**Files:** `app/routes/main.py` (admin_export), `app/templates/admin/panel.html`

**Problem:** The export JSON contains environment encryption keys + all encrypted secrets.
It is a complete decryption kit. Currently it's a plain GET download with no password
confirmation. Anyone who clicks the link while authenticated as admin gets everything.

**Fix:** Change the export endpoint to require a password confirmation POST. Encrypt the
export JSON using the same PBKDF2 + Fernet pattern as the per-project backup before
sending it as a download. The user must supply their password to decrypt it for import.

Additional: display a warning in the UI that the export file contains cryptographic
material and must be stored securely.

---

### 2.8 Add file upload size limits

**File:** `config.py`

**Problem:** No `MAX_CONTENT_LENGTH`. A 4 GB file upload to `/admin/import` or
`/setup/upload-db` will attempt to load entirely into memory.

**Fix:**
```python
MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32 MB
```

Add a 413 error handler:
```python
@app.errorhandler(413)
def request_too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 32 MB.'}), 413
```

---

### 2.9 Harden file permissions on sensitive files

**Files:** `app/routes/setup.py` (`_generate_self_signed_cert`, `_save_cert_content`,
`_write_env`), `app/routes/main.py` (`_update_env_file`)

**Problem:** Private key and `.env` files are written with default umask (644). They should
be readable only by the app user.

**Fix:** After writing each sensitive file, `chmod` it:
```python
import stat, os

# After writing key.pem:
os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)  # 600

# After writing .env:
os.chmod(env_path, stat.S_IRUSR | stat.S_IWUSR)  # 600
```

---

### 2.10 Scrub database credentials from logs

**File:** `app/routes/setup.py`

**Problem:** `logger.info("Setup completed (type=%s, db=%s, ssl=%s).", setup_type, db_type, ssl_mode)`
— `db_type` is safe, but the db_uri variable elsewhere could leak passwords if logged.

**Fix:** Never log `db_uri` or any variable derived from it. Log only `db_type` (sqlite /
postgresql / mysql). In `_build_db_uri()`, the return value must never appear in any log
line.

---

## Phase 3 — Medium: Hardening

**Target:** Before calling this "production hardened." Mostly polish and technical debt.
**Estimated effort:** 2–3 days

---

### 3.1 Replace Werkzeug dev server with Gunicorn

**Files:** `requirements.txt`, `startup.sh`, `docker-compose.yml`, `app.py`

**Problem:** `app.run()` is Werkzeug's development server. Not suitable for production:
single-threaded worker model, no graceful reload, `FLASK_DEBUG=true` exposes a code
execution debugger.

**Fix:** Add `gunicorn` to requirements.txt. Update startup:
```bash
# startup.sh
gunicorn \
  --workers 2 \
  --bind 0.0.0.0:${PORT:-5000} \
  --timeout 60 \
  --access-logfile - \
  "app:create_app()"
```

For HTTPS, Gunicorn accepts `--certfile` and `--keyfile` flags.

Note: The supervisor/restart pattern in `app.py` was built around Werkzeug. With Gunicorn,
the restart mechanism should use `kill -HUP <gunicorn_master_pid>` (graceful reload) instead
of `os._exit(42)`. This is a meaningful architectural change — design it separately.

---

### 3.2 Configurable API token expiry

**File:** `app/routes/api.py:130`

**Problem:** `expires_at = datetime.utcnow() + timedelta(days=365)` is hardcoded.

**Fix:** Accept `ttl_days` in the create token request (default 90, max 365):
```python
data = request.get_json() or {}
ttl_days = min(int(data.get('ttl_days', 90)), 365)
expires_at = datetime.utcnow() + timedelta(days=ttl_days)
```

Update the UI to show a TTL selector (90 days / 180 days / 365 days / custom).

---

### 3.3 Fix CORS initialization

**File:** `app/__init__.py:20`

**Problem:** `CORS(app, origins=[], supports_credentials=True)` — `supports_credentials=True`
at the global level is dangerous. The custom after_request handler is the real gate, so
the global CORS init is redundant and misleading.

**Fix:**
```python
# Remove the flask-cors global init entirely.
# The custom after_request handler is sufficient and explicit.
# CORS(app, ...) — DELETE THIS LINE
```

Remove `flask-cors` from requirements.txt since the custom handler handles everything.

---

### 3.4 Upgrade PBKDF2 iterations to current standard

**File:** `app/utils/encryption.py:22`

**Problem:** 100,000 PBKDF2-SHA256 iterations. NIST SP 800-132 (2023) recommends 600,000+.
This only affects the per-project encrypted backup/restore password derivation.

**Fix:**
```python
# Before
iterations=100000,
# After
iterations=600000,
```

Note: This is not backwards-compatible with existing backups. Old backups were encrypted
with 100k iterations and must be decrypted with 100k. New backups use 600k. Store the
iteration count in the backup's `info.json` so the restore function reads it dynamically.

---

### 3.5 Fix Fernet double base64 encoding

**File:** `app/utils/encryption.py:33-35`

**Problem:** Fernet already outputs URL-safe base64. Wrapping it in standard base64 again
doubles the encoding unnecessarily. Every stored secret value is about 33% larger than
it needs to be.

**Fix:**
```python
# Before
encrypted_value = fernet.encrypt(value.encode())
return base64.b64encode(encrypted_value).decode()

# After
return fernet.encrypt(value.encode()).decode()
```

```python
# Corresponding decrypt fix:
# Before
decoded_value = base64.b64decode(encrypted_value.encode())
decrypted_value = fernet.decrypt(decoded_value)

# After
decrypted_value = fernet.decrypt(encrypted_value.encode())
```

**IMPORTANT:** This changes the on-disk format of every stored secret. A migration is
required. Options:
- Write a one-time migration script that reads every secret with the old decryption path
  and re-encrypts with the new path.
- OR keep the old path in `decrypt_value` as a fallback: try new format, fall back to
  double-decoded format, then re-save in new format on next write.

Do not deploy this without the migration.

---

### 3.6 Update cryptography library

**File:** `requirements.txt`

**Problem:** `cryptography==41.0.7` is ~2 years out of date. Several CVEs have been issued
since 41.x (though none directly affect Fernet operations, running a secrets manager on
outdated crypto primitives is a liability).

**Fix:**
```
cryptography>=43.0.0
```

Test all Fernet operations, TLS cert generation, and PBKDF2 after upgrading. The library
has had API changes in the `cryptography.hazmat.primitives.asymmetric` module that may
affect cert generation.

---

### 3.7 Scrub CSP unsafe-inline by moving JS to static files

**Files:** All templates with inline `<script>` blocks

**Problem:** Phase 2.3 adds a CSP but requires `'unsafe-inline'` for scripts because all
JavaScript is inline in Jinja templates. This makes CSP weaker than it should be.

**Fix:** Move all inline `<script>` blocks to files in `app/static/js/`. Pass template
variables via `data-*` attributes or a JSON object injected into a single `<script>` tag
per page. This allows removing `'unsafe-inline'` from the CSP.

This is the largest single refactoring task in this list. Estimated 1 day.

---

### 3.8 Add audit logging

**Files:** New `app/models/audit_log.py`, `app/utils/audit.py`, all route files

**Problem:** No record of who accessed what, when, from where. Cannot detect compromise,
investigate incidents, or meet compliance requirements.

**Minimum audit events to log:**

| Event | Data to record |
|---|---|
| Login success / failure | username, IP, timestamp, user agent |
| Secret read via API | token_id, project_id, environment, IP, timestamp |
| Secret created / updated / deleted | user_id, project_id, environment, key name, timestamp |
| Admin export | user_id, IP, timestamp |
| Admin import | user_id, IP, timestamp, projects affected |
| Key rotation | user_id, timestamp |
| Token created / revoked | user_id, token_id, timestamp |
| Server restart | triggered_by, timestamp |

**Model:**
```python
class AuditLog(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    timestamp  = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    event      = db.Column(db.String(50), nullable=False, index=True)
    actor_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    actor_ip   = db.Column(db.String(45))  # IPv6 max length
    project_id = db.Column(db.Integer, nullable=True)
    detail     = db.Column(db.Text)        # JSON blob of event-specific data
```

Expose a read-only audit log page in the admin panel (paginated, filterable by event type
and date range).

---

## Phase 4 — Production Hardening

**Target:** Before marketing this to teams handling sensitive data.
**Estimated effort:** 1–2 weeks

---

### 4.1 TOTP / MFA support

Add time-based one-time password (TOTP) as an optional second factor. Library: `pyotp`.
Admin should be able to require MFA for all users. Store `totp_secret` (encrypted at rest
with master key) on the User model. QR code enrollment via the profile page.

---

### 4.2 Admin-issued invite system (if Option A chosen in 2.6)

Generate single-use invite tokens with 24-hour expiry. Admin creates invite from the
Users panel, copies a link, sends it out of band. Invite tokens are consumed on
registration.

---

### 4.3 Password complexity policy

Currently minimum 8 characters is the only rule. Add:
- At least one uppercase, one lowercase, one digit, one special character
- Block the top 10,000 common passwords (have-i-been-pwned list)
- Configurable via an admin setting

---

### 4.4 Docker image hardening

**File:** `Dockerfile` (if it exists), `docker-compose.yml`

- Run as non-root user (`USER configlake`)
- Read-only root filesystem (`read_only: true` in compose)
- Drop all capabilities except `NET_BIND_SERVICE`
- No `privileged: true`
- Mount `.env` as a Docker secret, not a volume file
- Health check via `/auth/login` (HEAD, unauthenticated) not `/` which redirects

---

### 4.5 Secret rotation hooks

Allow users to configure a webhook URL per environment. When a secret is rotated
(value updated), ConfigLake POSTs a notification to the webhook so downstream services
can trigger a rolling restart. This closes the gap between "secrets updated" and
"services using the new secrets" without manual coordination.

---

### 4.6 CVE monitoring and dependency update policy

- Pin all dependencies with exact versions in `requirements.txt`
- Add a `requirements.dev.txt` for test/lint tooling
- Set up GitHub Dependabot or equivalent to open PRs on CVEs
- Commit to patching critical CVEs in crypto dependencies within 48 hours

---

## Summary

| Phase | Items | Effort | Gate |
|---|---|---|---|
| Phase 1 — Critical | 5 items | 1–2 days | Must fix before any real usage |
| Phase 2 — High | 10 items | 3–4 days | Must fix before team deployment |
| Phase 3 — Medium | 8 items | 2–3 days | Required for production hardening |
| Phase 4 — Full hardening | 6 items | 1–2 weeks | Enterprise / compliance ready |

**Current status: Phase 1 not started.**
