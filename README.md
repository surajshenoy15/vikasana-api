# Vikasana Foundation — FastAPI Backend

## Endpoints (Login only for now)

| Method | URL              | Auth    | What it does              |
|--------|------------------|---------|---------------------------|
| POST   | /api/auth/login  | None    | Login, get JWT token      |
| GET    | /api/auth/me     | Bearer  | Get current admin info    |
| POST   | /api/auth/logout | Bearer  | Logout (delete token)     |
| GET    | /health          | None    | Server health check       |

---

## Setup on your VPS (31.97.230.171)

### 1. Upload project to VPS
```bash
scp -r vikasana-api/ harshith@31.97.230.171:~/
```

### 2. SSH into VPS and set up
```bash
ssh harshith@31.97.230.171
cd vikasana-api

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Create .env from example
```bash
cp .env.example .env
nano .env
```

Fill in with your real values:
```env
DATABASE_URL=postgresql+asyncpg://admin:StrongPass@123@127.0.0.1:5433/appdb
DATABASE_SYNC_URL=postgresql://admin:StrongPass@123@127.0.0.1:5433/appdb
SECRET_KEY=<run: python3 -c "import secrets; print(secrets.token_hex(32))">
ALLOWED_ORIGINS=http://localhost:5173,http://31.97.230.171
APP_ENV=production
DEBUG=false
```

### 4. Run migration (creates admins table)
```bash
alembic upgrade head
```

You'll see the `admins` table appear in DBeaver alongside your existing tables.

### 5. Create first admin
```bash
# Edit SEED_ADMIN_* in .env first, then:
python seed_admin.py
```

### 6. Start the server
```bash
# Dev (with auto-reload)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

API now live at: http://31.97.230.171:8000
Swagger UI at:   http://31.97.230.171:8000/docs  (only when DEBUG=true)

### 7. Test login
```bash
curl -X POST http://31.97.230.171:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@vikasanafoundation.org", "password": "ChangeMe@2025"}'
```

---

## Connect React Frontend

In your `AuthContext.jsx`, replace the mock login:

```js
const login = async ({ email, password }) => {
  const res = await fetch('http://31.97.230.171:8000/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const data = await res.json()

  if (!res.ok) return { success: false, message: data.detail }

  sessionStorage.setItem('vf_token', data.access_token)
  sessionStorage.setItem('vf_admin', JSON.stringify(data.admin))
  setAdmin(data.admin)
  return { success: true }
}

const logout = () => {
  sessionStorage.removeItem('vf_token')
  sessionStorage.removeItem('vf_admin')
  setAdmin(null)
}
```

For any protected call:
```js
const res = await fetch('http://31.97.230.171:8000/api/auth/me', {
  headers: { 'Authorization': `Bearer ${sessionStorage.getItem('vf_token')}` }
})
```

---

## Adding More Features Later

When you're ready to add students, activities, etc:

```
app/
  models/    ← add user.py, activity.py etc
  schemas/   ← add user.py, activity.py etc
  controllers/ ← add user_controller.py etc
  routes/    ← add users.py etc
```

Then in `main.py`, just add:
```python
from app.routes.users import router as users_router
app.include_router(users_router, prefix="/api")
```
