import os
import re
import time
import sqlite3
import uuid
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, session, redirect, url_for,
    render_template_string, abort, g, send_from_directory
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xrpradar-blog-dev-key-change-me")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "blog.db") if os.path.isdir(DATA_DIR) else "blog.db"
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads") if os.path.isdir(DATA_DIR) else "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

APP_VERSION = "v1"
LAST_UPDATED = "July 12, 2026"
START_TIME = time.time()

# ----------------------------------------------------------------------
# DATABASE
# ----------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            excerpt TEXT,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            published INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            FOREIGN KEY (post_id) REFERENCES posts (id)
        )
        """
    )
    conn.commit()
    conn.close()


init_db()

# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------

def slugify(title):
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-") or "post"


def unique_slug(title, exclude_id=None):
    db = get_db()
    base = slugify(title)
    slug = base
    n = 2
    while True:
        row = db.execute("SELECT id FROM posts WHERE slug = ?", (slug,)).fetchone()
        if row is None or (exclude_id is not None and row["id"] == exclude_id):
            return slug
        slug = f"{base}-{n}"
        n += 1


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def save_uploaded_images(post_id, files):
    db = get_db()
    for f in files:
        if not f or not f.filename or not allowed_file(f.filename):
            continue
        base = secure_filename(f.filename)
        name = base
        path = os.path.join(UPLOAD_DIR, name)
        n = 2
        while os.path.exists(path):
            root, ext = os.path.splitext(base)
            name = f"{root}-{n}{ext}"
            path = os.path.join(UPLOAD_DIR, name)
            n += 1
        f.save(path)
        db.execute("INSERT INTO images (post_id, filename) VALUES (?, ?)", (post_id, name))
    db.commit()


def render_content(content):
    """Replace {{img:filename}} tokens with actual image tags."""
    def repl(match):
        fname = match.group(1).strip()
        return f'<img src="/uploads/{fname}" alt="{fname}" class="post-img">'
    return re.sub(r"\{\{img:([^\}]+)\}\}", repl, content)


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapped


def uptime_str():
    secs = int(time.time() - START_TIME)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


# ----------------------------------------------------------------------
# SHARED STYLE
# ----------------------------------------------------------------------

BASE_CSS = """
:root {
    --hdr: #03b1fc;
    --tq: #00e5cc;
    --bg: #000000;
    --card: #0d0d0d;
    --line: #1c1c1c;
    --text: #e7ecf3;
    --muted: #8b93a7;
}
* { box-sizing: border-box; }
body {
    margin: 0;
    font-family: Calibri, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
}
.shell { max-width: 1400px; margin: 0 auto; }

/* HEADER */
header.site-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--card);
    border-bottom: 2px solid var(--hdr);
    padding: 16px 24px;
    gap: 20px;
}
.hdr-left a { color: var(--hdr); text-decoration: none; font-size: 24px; font-weight: bold; }
.hdr-left .tagline { color: var(--muted); font-size: 13px; margin-top: 2px; }
.hdr-center { flex: 1; display: flex; justify-content: center; }
.hdr-center .radar-icon { height: 64px; width: auto; opacity: 0.95; display: block; }
.hdr-right { text-align: right; font-size: 12px; color: var(--muted); line-height: 1.6; }
.live-badge { display: inline-flex; align-items: center; gap: 6px; color: var(--tq); font-weight: bold; font-size: 13px; }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--tq); box-shadow: 0 0 0 0 rgba(0,229,204,0.6); animation: pulse 1.6s infinite; }
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(0,229,204,0.6); }
  70% { box-shadow: 0 0 0 8px rgba(0,229,204,0); }
  100% { box-shadow: 0 0 0 0 rgba(0,229,204,0); }
}

/* LAYOUT: sidebar 20% / main 80% */
.layout { display: flex; min-height: 70vh; }
aside.sidebar {
    width: 20%;
    min-width: 220px;
    border-right: 1px solid var(--line);
    padding: 24px 18px;
}
main.content { width: 80%; padding: 24px 32px; }
.sb-block { margin-bottom: 28px; }
.sb-title { color: var(--hdr); font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }
.sb-list { list-style: none; padding: 0; margin: 0; }
.sb-list li { margin-bottom: 8px; }
.sb-list a { color: var(--text); text-decoration: none; font-size: 14px; }
.sb-list a:hover { color: var(--tq); }
.sb-cat-count { color: var(--muted); font-size: 12px; }
.search-form input { width: 100%; }

h1 { color: var(--hdr); font-size: 30px; margin-bottom: 6px; }
h2 { color: var(--text); font-size: 20px; }
.meta { color: var(--muted); font-size: 14px; margin-bottom: 20px; }
.excerpt { color: var(--muted); font-size: 16px; }
a.post-link { color: var(--text); text-decoration: none; }
a.post-link:hover { color: var(--tq); }
.post-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 16px;
}
.category-tag { display: inline-block; background: rgba(3,177,252,0.12); color: var(--hdr); font-size: 11px; padding: 2px 8px; border-radius: 10px; margin-bottom: 8px; }
.post-content { font-size: 16px; line-height: 1.7; white-space: pre-wrap; }
.post-img { max-width: 100%; border-radius: 6px; margin: 16px 0; display: block; border: 1px solid var(--line); }

.btn {
    display: inline-block;
    background: var(--hdr);
    color: #06111c;
    padding: 8px 14px;
    border-radius: 6px;
    text-decoration: none;
    font-weight: bold;
    border: none;
    cursor: pointer;
    font-family: Calibri, sans-serif;
    font-size: 14px;
}
.btn.secondary { background: transparent; color: var(--tq); border: 1px solid var(--tq); }
.btn.danger { background: #ff4d4f; color: white; }
.btn.small { padding: 4px 10px; font-size: 12px; }
input, textarea, select {
    width: 100%;
    background: #0a0a0a;
    border: 1px solid #2a2a2a;
    color: var(--text);
    padding: 9px;
    border-radius: 6px;
    font-family: Calibri, sans-serif;
    font-size: 14px;
    margin-bottom: 12px;
}
textarea { min-height: 240px; resize: vertical; }
label { color: var(--muted); font-size: 13px; display: block; margin-bottom: 4px; }
.row { display: flex; gap: 10px; align-items: center; margin-top: 6px; }
table { width: 100%; border-collapse: collapse; margin-top: 16px; }
th, td { text-align: left; padding: 9px; border-bottom: 1px solid var(--line); font-size: 14px; }
.badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.badge.pub { background: rgba(0,229,204,0.15); color: var(--tq); }
.badge.draft { background: rgba(139,147,167,0.15); color: var(--muted); }
.flash { background: rgba(3,177,252,0.12); color: var(--hdr); padding: 9px 14px; border-radius: 6px; margin-bottom: 14px; font-size: 13px; }
.hint { color: var(--muted); font-size: 12px; margin-top: -6px; margin-bottom: 12px; }

/* FOOTER */
footer.site-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-top: 1px solid var(--line);
    padding: 14px 24px;
    color: var(--muted);
    font-size: 12px;
}
#debug-panel {
    display: none;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 14px 18px;
    margin: 0 24px 14px;
    font-size: 12px;
    color: var(--muted);
}
#debug-panel div { margin-bottom: 4px; }

@media (max-width: 900px) {
    .layout { flex-direction: column; }
    aside.sidebar, main.content { width: 100%; }
    header.site-header { flex-wrap: wrap; }
    .hdr-center { order: 3; }
}
"""

HEADER_IMAGE_B64 = "iVBORw0KGgoAAAANSUhEUgAAATwAAACACAIAAAAZGELrAAABWGlDQ1BJQ0MgUHJvZmlsZQAAeJx9kLFLw1AQxr9WpaB1EB0cHDKJQ5SSCro4tBVEcQhVweqUvqapkMZHkiIFN/+Bgv+BCs5uFoc6OjgIopPo5uSk4KLleS+JpCJ6j+N+fO+74zggOW5wbvcDqDu+W1zKK5ulLSX1jAS9IAzm8Zyur0r+rj/j/T703k7LWb///43Biukxqp+UGcZdH0ioxPqezyXvE4+5tBRxS7IV8onkcsjngWe9WCC+JlZYzagQvxCr5R7d6uG63WDRDnL7tOlsrMk5lBNYxA48cNgw0IQCHdk//LOBv4BdcjfhUp+FGnzqyZEiJ5jEy3DAMAOVWEOGUpN3ju53F91PjbWDJ2ChI4S4iLWVDnA2Rydrx9rUPDAyBFy1ueEagdRHmaxWgddTYLgEjN5Qz7ZXzWrh9uk8MPAoxNskkDoEui0hPo6E6B5T8wNw6XwBA6diE8HYWhMAAQAASURBVHjanP1HsGRpliaGnXN+cbWr50+HyozMrMzSoku0mO7pajmCAzEEegCQQ4KwAckFQSM35BakERsuaIYFzWAUK8KwAAw2tJnBcESP6pkW1VVd1VWVOiMy5NOur/rl4cLfi4ysrkIP6XYjzMX16+/d59895z/n+76DT54+hZdvDP//3/D635+zFyIDIN7sSYSADEBE3nRCpxwCIAipmTlGDwxSp0AUreEYmKNQCZKI3pEUgMQxAgBz5BCAGQiBAZGQkAFj8MjMACQISW4/ODjHwIgIIUSOQmmOgWMUSQYxMjAwICIKwTFu34JIMXoA4BiBIyAhIjMjEhCRENFZZkZEJALAGByi2J4PDgFJAAAiMUeO4ea92wNvTxzy9vy9dHa2R0NEIaXzQRBtX2dmhAgMIUYkAoYYA8dIEIrBWBC063X0lqQinXnvgrNpUeokZb7+AzNzCJ5IIBFEjhzh+mORY2SOQsrIERERcHtSjeljjEonWaqM476pY+QkS6XS3gfTd8EZYFA6kVL0XRucA8TtMQEYXvzFGRgYGWIMUmuptDXGuT5Jc+DojNmeDZJSJUmMTFLFGIEhWMMcgEGXVQy8vU9SMUdEJKLtSQjOkhCABBy3v+/2dHIIQATM2z8Qx0iCmIGDjyFsv/tIJIQCjsE7QEQhUQhCYuboTAxRJmlwhjkKqUnIGAMwA8D2jpAyKSrbd4QgpDRt661Bwu1PAQjAjH8GZ/gzkIc/8coNvnA0OXwJsfwTb0WA+NJT/MkhIjAAAjMgCt5+wQiBth9EgAIAgD0AIyAiMjBHQiGAAEioYkg64RiJhMoqJASIgAJjtO0m372Vjnbrs0codTbeg+AAeHP22NYLZNDVcHz3DeSIAOnOgSRwfbd88kCmiZA6hsBCuXYFMSTlcDDZ6eqa0oIZSIjIGINrzp/JNBM6kUmipG5WC9O1wJwUlUpziD4a47pOjaYMiBBFWiCQbRbsHAQfXE9ZgTG4Zi3zARICiNCtZV7F6IM1Qmm3XuhqQloLlai8QEb2JikGmiB0m94YqTQKFUlGBuBAjCKrYvQghJAahMzKKhNogtdJkuaFAE6UCn1XVIWxpl43Qgog2WyaPBHGu0yJr3zty2988cv//P/1X7z7/T/B6Ove6+ntFMz+0cHXf+dvlWUlBcUQibBvGtt12WCo0sS1fYgxhhCZYwzemnRQBeuC88OdibfO9N16ufjw/fff+9GPNIlbt+8WWlycnJ49/miyuz+880YUqq2b5x++vbx4lkg5qArfrp5/9G5aTZnI+8AAOisjAXvHESRzt7qqdg++9W/8jawYnz/6wEdnTPfOv/xncbNgDH3TVru3dm/fGx3dXbbGGFdOjzaX57NHPwLm8b3PV/t3VqePOcTq4E4yHCZlJpUK1oaumX38LiAJnXrbhr4N1ugsd33j+p4ZvO2SotLFDiAImRCE2aN3+82SVCKSgoTmAEis8jKfHhTjfWva5vKkn5/161UyHE/uvtWtl6vnH5EQKilQCSEUM0ZvlNJ909z5wtf2Xn1Nor9zvB8Ws//yP//PgDHEyCABGCACBwBgvEY7ACIQADDGTyNR4hZE16BDEAhAACCXyxUAIPJ2z+sdXsYpwk/CFgAgvIRrAtzuREDbHwABBCAChC2sgQGQASUgASFIJRxno10A5OgkdLatOYTB8SshOsgnMDwwiG3EJB13TKsnH+u8NMY5y+XBHU9y2Vj2Ni2q9uxZUg6TNKXhznC6tzx7Yq3xxNExqiT2Jk0GMp9kWXn5/DF1q2o4WtWNIdVHFVZ1UlGSp+vOcSClVXN5kY+nQqWuM6E3oqlFWvarRToU3hnfriGG6C0ASRGCaZE1tCaYVigNJMJsJpLct63UTlDSr2b50WeS4bhZXLAQpNIY2escZOz6kOtc55VOc8/R9Nb1ndNZaFu3XmTD8fTu7Wj6QCxkturdfHM1GQ1QiBjc/Gq+sT7P86Zpikw739eQuoh379/Ze+uL7//oB//q9//YAiVpcbU4kesP7u4k9/6H/2MrEwdcWx98LBLlpOaMLEDwwXJUOmlWaxIizXJPUqTF8/Nn56tVcXJ2/vRpU29OTp/X63Wz2uRZdrVc6tnTZcfCrB8/emT+8I+TPK92j2SS+WJncfb47NmTqiqaztq4BKVCYOuCdgEIbN0keYZ9Hzh87he+3aQT23azxSUU483VrGeVDXdXF8/arm3Onj4/ef76N6WjtK2bnpNktBPySb++2nzww+zi3Js+uH6xWQ6PXkkHIxAiG4wYdMeqnl2U04MIyrOODF3n2+XG920MDhhg00rdCi2Fzrxpm8tL121EmsskMguh03L3SA8mq+Xm6vQ8xhh9hyR6hHY5WzXfz0d7nI+7drW6Oo/BJvmQkhQCChkQ5ff+0d/bf/X1L3/7txa1O7x17wu/+Gv/9G//1zpJrQ2AAOAZAm6zjU8ykE9AizeYBQBgBKBtloCoGHGbrQipM0mEJImEECSEIBJIQojtXUIiEtcb0ifbNpO4fokEkgAierGDQERJhC/2v95ZkhBEiEII9ib0DQSDSCrJOXrgmA130mIE0QPE8a3XbbtMi+Hozmu+b8z8XOclB5uUlYy2mV0mxQAFxYgILIVsllexb8vxVCpNUsmsksWg7/oiS5Cd75pQL7OikCopx1OZlbapVVZG54vpPkHUSVYe3gPnisP75d4dlFJllUxLlSTMPra1VCoZ7LC3SVFG17Oz2c5hWo1RSKUk27YYT7SU0+nOqCyGe7vHt45377wqi5LqhWQny5FQKSOavs2nhyBTMRhl1VBISUhSSKWlFIQ6KRIlfZdXlVCJjCZYW+UJMVfVwBrrTXfr1vF4WDnTqyQNEYOQ+0P11V/8pX4x+72//d8sWqd2j62QvjcDN7/7+hs7X/kL9WZTlOXpbCmFqrLMGUNCIGO0NkaWkrq6jjEy0rrpzi4unzw/+eEf/eF3/8Xvnp6eWg/AYIxn4NB3gp2zTkRXjkYhrUAQR2+98RBVkmqtBHKAIImC7UkprbTUGSgCDmh6KVAK+tpf+uu3vvyti9NnP/6nf3e9WC7Oz4wL07uvus1qs1wqLaLtkaG3frB/IKTqm2WwrphMo3PADiFKJZIyR/ZEJKRqL06CaZB59eQhCcyGOwAgSGbDsdlsOIYkK4mkTFIhlUpKiCG6Dr2VmqIzSCRVVu0eDo/vYYxmM2NndFakg+Hw1mtC6GhbDi72bTA1ESqliuGQiGNwSVmNjl8lIYrh9PD1t5rZ2fmD93YPj3Wq77/2+pP3361XSyElERPBzfefbnDwAkMkiMT2FSEEEREJASSQBBLJ7V5EJAQmzBCv83JkRmbchkW+BvxLcZa3AZmZtwurF/GZgOOLHXD7Cm6zbd5eMSBGiHz9Zo4cA3NAwOCt0JlMs3LvlqrGRIJjQCEBwNQr124AEEQS2kYolQwnzfmz6uBWe/E0oZDv7DOI0NcxxvbyBIIHmdjIohhTPiRB6XA3L0sO3rRtUQ12RoOeBXiPUuXV8OjooDx6lZH27t4vd49QqsHe/nSQ54d3ybdkN1QMmYNZXrWXz2PwQmfBtGZ5FZ0TWsl0oLMco6tGIxFtWRZKJ8NBdbA3Cd7lg7EoR355EQHS0c5wdy9J1MHhvgyehcr2bmXDUaoSRFRpgbYLtpfBh8jVeFIlSd80QFAUxdFkwIBpWY0GRVevpaTxaMjetW3b9V1nnRRC9qsvfOmL2WT/o3/1u08/fgTTozqSsQG82YG2ev2LfnxUR+psWGxakrJKtel6ZECBTWvbtmvavrM+HwzeffjxH3/vBx+8+87Td360vjhVaYqIWZoNpweUFzovtCBYXfnIhRLj179GxSiiAiREYGddveIQRVaCkM70wTUYnDcdB88cwHXgvUD60rf/8md//a9RktYnT6JHE4jZy2KEHOr5nHQWnIHQCSkCkPNBplmSD/rNhgGY/XapKbNM5QUJGbxReeX6tluctVcngEKXQxDke0NKA0O3WkRrVDHYrmCDs7oak0piiMG7GDwgSZ2hlMzs6sZsZsBRFUUyqISSpl7rolJpqYoirUYqSXy37DYz0yyTPJcycV2jknx89y3fdb5vX/vGLwXT/fj3/8l4d//O/fvo7Xs//L4gCiECADIyE1xvCIDMCEzIxBAZtiUV3sIQgIEJAADETdrMAkgzMiIAxOtcF/An1sZ88/imPvJJAn1dStmm1zexHK/jOL+0et5eARgQkAQwoJBCKlQaAKPrIQQESKtxDL48uOuN0dWgPnuitA7OMwddlIOj++3Fk+i6cve21Ko6ejUf7Q5u3xdpVu7fLo7uqSRRScYAaTUkocxqrhJVTPaqosDoA0lB0Dt2QmeD8fFrb5Q7++lw4pzP0nTn7mtkN0qK4WhUpSIYMzm+FyEOU53nqW1rJDLNOjpPUiZllQymRVFUmahGoyTLtNJFmlBw2d7RcrmRyL7c7QIQ4KAqxWBcDsc7w8F8tdGCRF5G76ld+m7NJFFIU6/MZiNVko0nSgoEVkIQ8HRnmAgxHQ+EpMA8LLO90ehqvXny7Ewpuem6rvfB9Ts7w2o8XT19+Pyj97t8tOx9t16wN2W/GJbJ8S/+pWr/2AMh4WLdDLIUgyMAqeRstTqbLxertTHu7OzinXff//D9D9fPH2tvffBAUknhus50ve1bjD54PxQRm6VvTTnd89nUcpRpnmQFChVDBI7MMfQtM4S+43YdbMs+sPfgewKIEV753Fe+8df/fS/U6YfvnD87cZjIaDgrEy3Wp89imunBEIJHswFAIK3KgetbRXp0cOxtb5qalBZSqzJDQpEkMUQOTED96pykykZT0goZODIJabsWgYGYI6DUHG0MLilGwbnQ98CeY0ACjtsCodRFSVJ265mSoltcOWcnh6/qYhC8jbY366t2cRpsG9kLQtd3aVkKqdvlFTPs3n6lmZ2vLp5/9hf+YjWZPnn/x7u7e4d7u6GrH370oVRqG83+7IaAiAQYP0EWEDAhRkBAvikSXcNXFQAAHAmYrxH7qRXspx7zTy0uvwA14Iui8LZI9vL+17AmUikCoJAcfGhrsCb2re9q161duyEpUchueWHXy2Ba22yUTl3XuK7uVzMOcfLKm6HdNOfPq72jdDTxziSjPamLZLhTnz1Lx1MtVZJmufTjnd2YFPV83q3nEXB89IosRwFRp+Xu/c86ko0nD0oXOYTQGRMirp4/zqeHfZSz2ayp63Z2ETbzen5pbZDDCTNmidh/4/PDg+NRoRP0RAjp0NluMN7xAGowwqTMRqN0MEWEsizH010E8M5yDLXjLkCqtWA2ISSJToBXraHoi6Iy3SZuFnuTcSC1alvv/dH+NM+zi3U3qAY+AodQZtnpbOFJFmVxcno+He3s7u4dHOyRN08/fMdenQRULYj1Yu6NFf1yj/q9r/xi9pmfcxEyrb230+HQdv2jp88707fGPZ0trXWDQRm6/p0PPqgvLjLkul4FwhABIXrnQghKp1oKa3q/WsHVkxAIfQflgfHedG2iCxLC2t7HIHSKQtA2V4sQ+j46iwKAPWAEpsHO/rf+2u/Eary6PH/8/vvr2gS7iUIXxcCv5w5I5iXHCM54Y5z3GL3MK1nk7fySAleTSWCGyCiEUBIAUQghJaJUadUvrmSaohBCJc70MXihktA13lkAjN4jYIwOEUkmCBhcH10PHIA9cyAElAIAxge3guvrxWVaTJRKutWSBKZVEU29fPKe71cQPaFAQIRom/Vk/4hImOUshJANxqvTpycf/Ojo9c8fvfJ6v5zfPj7Qgs5Onq0WSynFpzDBL5eLGCBetxuAbxa02+aF2HYXthFQyOEBSgUAHPilGIs3aS3inylGI36CzZtngJk+9TTfdC62Vaht4R0+ubiQSlBIZIYYgZCklnkVnI22b+fnROhNAz6iEBEiIkTnhKQQfDoY1+ePUch2vaC00tW4m511q1m5e8gQs+E0LQowtYxh984rIq9mH7/jmk2WpzIrszwFQEcaZdrZMBhUEbheLru+71eLEHxvnUdhAiApjKFbXHVdExgxH7Ezh3fvjXamu7fuehAFBc3B6IEhmUjaO7rtYqwGQ10OhO+Ho5FQ6vadV0WayiSJEZHBmd4b44zh6GPfdqvlwc5IVsOr09NKspQqzTOZZZu6EULYEMrRZDzd4chFli2bVkm6d3QQvJ9dXSWJLst8Z3e6MX69XMrYjUbjerVQSujB1MW4uLqaCjccVHH3tp4cJEkSOSipTWefn5ykeZpm6brryzzTiT55/OTD997ulwvbNiAkA9i2dd6maSqlGkx2pdJ90+gknQyHsltb75Fw1lhnbQwcvKubeQhOpYXMclKKAYFJKAXBIiMSIgYIkYT+2q//tTe+9Svzpn720YezixkE610PjGgaG0FWo8jMpgvRpYM9ij52M4hRFCNJoptfpGVZTnaNMSAJAbY9GGAAliotousAUegEGIKzCAAMvm1i8Ow9R5ZaYvTe9iQTEhI4sOuYWUiJgCothEpsvUny9O7nv76+umivnnNwOkuc6/JqsnvrXpql65OnAEFICRwoegjWt+3k8NW2Xtu+984lRdFtZlePP9Y6He3uB9vt7++r4N5/7x0Ugv9Mj+alxg/fhEDctr0QIwIBECAjIRAgokj37gqpUaUgFDByjBgjQkTcIhYjvEiv8b+/jYuIn8RlRABGBCAE/iQUAyPGyCFw9MjIwJSWMiuYmUMEiN4aDg6FQkDXbXQ+YEaZZlIJmQ2CtbZeBWdHd14b3X0zHU6DcyrLVTlsl1fDnT1BFG1XDYcORdRV1zdpkpb7t2ReRZ1G0+tqQkTseqlTTbHbbIhQSdq9c49UlpUjAa5fzbrVIniD0du+c84Wo0k5GORl5awRUgYfQr3yQonRXqXFreMD4Y3zoRqN69VcIg6Gg6rITVdXmiZFGtt1U28CCu98XlVNAK3Tg93pul6b2WVrTFoMbFcng502QNPbQSLHO7ut9c1qkQrcGQ2b5dJGPxoNhVCeqTOuMw4Qmnotlqc7x0fzNqJKqpRMxLoz3bOPXtnJ1MFdcftzyXCnSNPpaMDA9XqdaHm8O06UMs7O54sn773/5MP36tXKcwzBd/WmbzfGdFmakRCBYTCZHh7fqqpBvZx3pw+9tSH4Yv+OKIYoZFoUxjTGdCrLRJoyR0QiKUWWMxL7QADse2BvXfjsL/zaX/ydv7ly8eLxg+dPTrheRddFkap+tVnORTlGIWLfIjCmmSgqqRIwDTCLYggogJ2pN+VwnI/GbbvmEIBRpAlElDoLziRVAQwcmJmDtUQSCYL3SAjAhEhCADBEL3RGiOyN7zuh1TV5QFCSD5K03Mwui/He0Ruft23dzmahb4UUDNSvN5urS/AuesvAGCIzI7IxLQce37pruiY4p9IcmCGG9WoZYqg7MxlPvvnVr/zw+9+fX1xIITgyMP90nkNEYEYEuu7bICABIqBEJEABKER5/AYpRTIhlaJCRmaOCPEmtUW+rkq/AO01An8i2F4D9ZM0mV6sfxFezrJfLK8jBwsMABEBmCMgIglSmqT2pkEhovfe9Eigksz3HRLqNOsWF/l4L0lSEEoXA45O5oNo21QnyWRPJXq8u9d2few3zME1DXJgnY8H5XA0abvOAUXSlJYpGjBNOtxhoaBb2XpNHKNp1rOrEBllkiRpMhiXk53BeLp361Y53gVvtE7brhZplaR6VObjVz+fK9qcP7dMxL5pmlKp6SC3IEjqBEKS5w9P545kF9FTQsjGR2YQSiVlOb+aWaDBaIyCkFlGm6ZpmqfBOhOg1DQ7vySd7O3t7R/uMSV9RBfZeX9+OT+/nAcfhsq+/rm3VrF4enW17EMleTgcPnnw/oGwtz77pcEX/oKspnmWTIZVmaXGmHqxLAhN16/r5vzxk6fvvL04PwEAEJSkGRFKkt5b23d5XjhjvDHdxVl9cVaMRvsHR7KbB0p3dqeHX/lVVqozjfXGe6e0lnmBUkCMyIhJKosSEYN30bZsmr5t3/rWr/3F3/kPW1IPHnz45MGTsF5JDD2KRIBZLXE4ZgDfbrhrUBLqTCSaVBqbNjLHyJQkpFT0bnl5kSZJkhdd26kkgRCBRTIYIrKra9vUiAAxIoHUSQxBaoWI7D0goFRE6G3LzBCjrVdIQqY5bxN7FN7awd6xkGp5eT7YP87H+zE6U69C34EgSoskK5vVFbODyIyRY2RmEqLbrJKiqvZv1YtZkuXD6cFmfq51wiSmB4dN3SRFmun03T/9vlJiy3Lgn4TQNccGmQlh2ytFkigECYUkSQgkAkSxc+8toaSQUkiJUoAQgMiBOW5Xpdvs9meH1k+hkbbB9SUezE/NAhgAQCAgATB7F63hEBAAgDj66CxwRESVljIrvOnYO6ET322E0NG7cu+ovTrR5TgdjNYnD5Ji0J0/iTGkO4fg7c7uXlYUnE88EAihBVljJHKZ5zuHhwn4wJCE1hhz+ewR2F7l1fL0abderpaLdjHzDEk5Eknqnc0HwzxNJuMJQsyHY9S5UmpQDYbDMk3z5dkzMJv56bPhaKK01oJKKQ6OjkglNoqLVZ0WpRxM5nWfCmCRAOAw131bB+d9ZGNtppXOsjTLsywDIQxIG6mqSlmMUKnpzkSm6XA4tN6z0BHg0bMz29YYWSiRSTnMxOc/cz/ZPWp7c3K5nM1mQie3797ePP5oVOjs8BW1d3dvPCyqwbrZfPz0+bOTi03Tn5+erC6v1rOrpw8+bFZLnWU6yUgIgcIbmw2HWsokSXWSImBsGwhOCTr9+MPlx+/arm2WMy/TZ+ezq9Mnfdd4a2SSyjT11my5WkgIkqI1wRpwLnZ1t1p89lu/+ht/8281JjyZzS/Pr9rT5yLYlkkqyZt1TEvKCvYhLmfoOhrtk5ZbjpYPho1hAJEV0faoE0qS9exMJXm5s2f6NhiHoJiDVKpfzwECkoAYt43GGCIhCi05RBaEgNH3vmsgRASMzqIQ0XmKjEQqy33f2L4WaQbA1liQKngbg3XNhmMEJNKKhHB9yxDZ9rBlGDEQYrdZDg7vpMOdZnEmMg0EIUaVF0laDEeD06fPnDWrxaxvaySKkX9a3GPAyACAAohASBSSpKItMUsI3LZ89l7/kpRKqlQoLZREkkCCETmG6MMN7+Ll+vF2ofqp+tT2GUS6LkXdXDKuK8Y35I3rg1yHbXzpIQIzBM/BsrccPAQfbO9tn1Q7qqiAmZRSSaLL4fD2a9nOQb+ayzS1fRedUUonReW6Oq0Gg+n+ut6AFH3XayWGO/tJWUXTLc6eUZpNju82xpvlzCzOkGMx2d0y40gXHLxOU0GU5JUUKAg0ukIElKpdL42zTe+j73czMdCwvDxfPvu4HI4yrUSw42EZNitjrSiqzXr59Gqt80IIsenjar2WELSSq/msWy+OXr0vy5FKM0R0zXp6sKeSzEbcOzwElUKa3z7c79ru/HI2SpX1ARja3m5aW29qQOyMFRHWy1m9We3vTF4/nnCSPq/dg+fny/UGEdm0FJ2OPffN7a/8ss6LKFXTtU+fPP/4waN6PluvFsuL89Xl2Wq1ROCyqpCo3awpBnBuWFXrxdw7m1YjjTAoc4GkdFIOB4lSA42ticWgsoPdulurLBdayzQjVN4YRODIDBGkIObgLLMHju3Z0ztvfuGv/M/+k9m6vWq7CPHswUPRrTe9JSlkbxyQGo5AEHmO548hHeBwRFIiQrCOQ9zSPNkZlCoCAgldlD4E2zRCJ9XuIQO6dsUxCIHBGEBGQURy24YkqYILwECE3rQQvO9qRGBmkkLIhIQGIYLrGQgFRo4xuGD7tBgGFwglMPu+Ca4nqZgEEkXrwFkODjGCkKQSmRWoVLteJUmWj6b14gqAmSi4AADH9+4LjE8efFjk6fnzp0pKEgquW6cv1YEwXGMNEUmgVEJpEpKUJCm3jAkUQhx//ptKJ0JroZSQEgWRlIgSmKP3EAN9CrQvCKQvP7wpW1+3f7aovMYifqqyjACARC+qXYj0qaz5uhMVgSMwb3mkHJ3rNhy8zgqIVkrZXZ0F25UHd+vzp+xtvnvk6vXw9v3R4Z2mN/1quXz8/mBvn63Rabaaz9um1QJGe8dP3n87Mkghyv3bQmIMcTiZrK9mQchsfIDB990GnVWhYdPGZr03yH3XWe/LXGcQdjKFUhqQWVFqiIPR6ORqmea563qZJCYZeFLWeamT2Wwm01QTW+dYZShkmafsQ3CuWa7axcybfu/4dlJUVZ6rLOuN2xmVuRRSwHw+s+tV13Wg041xLjKjUGmhBFQSfN9LRQxUDasqT8Rw72TdPXnyPPSdyko2DbkO2+XhK2+Nj+8ZodfGnZ2dXl7N7XrdrWa2Xvu2BpUishKSTQ+mgWatbT1UwO3Szy9LGcPl0+75gzA/1a4V/drPz0oZ18u2jSI7uBXSUkgpVQI+QgAgAmQpE5SCpAxd560BBGQ0s/NBWf7l/9Hfmtf1s9lc52lfN7d2x22MjbFgOtCFnOyEYDGyv3g2GE9jNQZBwBiDC3XNIaLUKk1C10H0Ik1JaUDg6DhEleWUJIgQbOvqpbc9cgjWAjMDc4zbLmh0gUgAMAeHwN60N7R3AYwgNGnNMcKWsAygdAoskrSQUrerWVqUrtvE4IBRSkVS2b5DABSCUaDKZJZvAcYhNLNLSrJ0MEapk6zUSXH19JHr+73j21kio7fPP/5I6RQICSFEf0NBB8CI10tSRBIoFCktpRJKSaWu2U6CiEjc+covKZ1IpaVUSgkiRERGjEAcA3sH21/9Jxel241ualR0LQRAvg60jMDbLvLLK+AbyvM1gQMZf3biHSPEGF0fTMfRR9vHwJGjWV60l8+EVCgVRyfSIpse6ywfHb+ChN3iYri739drVU2cD9H2/fx8s6n3X3vLNytfL4IPIcL60dsgpC4GXb3eXJ4iczCNIBgOhruDdDwcyqyYjMe70+l8djXMtEQs8jzROurMhaCjV6O9VdvFzVIpFVCochSzAXpD3cqslplWs9Nn00EJCKPdvb7plBDT/T23WbBUqNNEUqYTJWlYJP1mWQ0H5+eXu1XqfOh6G0jJLM9S6azV1bBItVkvIPrZYokADDEvioO9nWw8XbN8+PyyrWshZPROmHUOYWdQje+8tg7y0dXi9Pw8MraLWT27RNsnSgxTpV2nuhUvnuHyjJZncXHmVxf1+fP5s4d2dQFdXWlZDSrn3HoxM53p+/7Z46cbEw6+9I2Nx26zDLaPPoAPSqWEyCEwMCkJANH7GAMBuNUc6tW3/+2/kY+nz89OkiKb7kwzpcaTSRe5SJRterV/iFrF3viLE2pWtHeXqgESSZ3a9ZJtT0qj0iLJOHg7v0SOwAwQwbrQO5WXKMit5916Fro62h4EMocYAniPMkGkGANgJCVj8AAcnUNmQoTgtwoB0rlSKYIHjEDIIXKIxXi/XS7yQeVM422DAM7UAOit1cVAqCxyICUREQUJqULwSMguyDxngBBCmlfl7sH+K6/v3rq1OHvW9Q0QcIwnH75HSuJ2hQhhi9HrFewWaCRJaKETmWitE6k1CZJyS1FEApRplm0jcwjBOYUkiDSziszA0QQXNp4A+V9L47MVhGwz5q2QY8vj2JKlXlCUX4bw9YL7EwEQf6JpYGYMngGAFBPH6M1mDQBpOZRJtjn5eHD0ChB501d33/AhhsjV9IhdMzx6NdjeXTx1Okm0KrIEurVv60IKmSWNMd160SxXyd6GnRmVGWTZ/OK8HOZFsdNv1uXOTiSR5eXVajOc7A6KTEpBSM5b5ZtutVr5EMMll+P9O3eLJLXMm/Ua2no9O58MKp3mp1ez0f7RZW0A0J2dbpqWZHKIQMXocFD5wMfT4WpTJ1pjaKVOSGlmBBKqKNzKatDe+w4z9vX64w/k4TEgzucLUQyCJte3O4UKwTSUPr5crZZrjgGY2fbYN6IYTt/8cjI9fv/DjxebmiLb+ln7+H3ZNQkGCKZtNrauvbOMKIQEQUiSpAJBRVrkebGzM6mGlSAcDqtuMnTWbdY1QJB3v2RIc2iFEM56IBA6iQQxBlAyBk+MwCiTVMTELi/6y5Ov/9pvq/H0bHEx2hljmsfo2ZvzWTPdmZxs1tXBYcgr26xjvwnNQo2mfdeoVJHU0XRoI0otyopDiMEJneWDcb+aQdehlIiMkCbkzeK8nl9xcAzMHNFamZcxepBSEkaIEBkJgzHI7G0PEIVWvm0QGCECRJLAbCNEDoF0wtGF0HnX68FgfnaSDyf15VOSigNFCAJjX6/TalpODk2/kSoJoQ/O6rSK3kAiZFJsaRgdCBDSde3BK6+9+rVfXDz5qDdOCplUw+gDpgoQgQRbH50FvKE2bEvEgqRWN4iVzC+0BBIoyCxNtzlqCMF5LYQkEpE5sGfP0fTRWnD2BWp5e537WQGSt2F1q/RiAAiMeL24/UTA8BKz6qcWt36ycBWjxQCu2yTVxDarNth2dqqKQXV0X2WDwe3P9Jvl/PI0m+zmZS5DP9jZdST1zg7nY16ev/nVz19dXaZIbta61WV9daWRjTddU2vX9kauTk4P9ibjqlidP0uUev7oY0ciT7Loze27d473pozMpv/hjz5oN5soZTqcqCRNlFzPZ7WUCrg1hkhN9w6lwPFwPN805L3USWvsarkSSg8H5erqKh0MtQQRrNZKJhkS39o7vqyfZkk63Nnp+n7jjEwkEJQiuzo/N5uNSAvLpKJNBSUYlrOrNz/3OSmET/NlY9fLFXLUxQBi8MtzHbpbd74wPrr34N33nnz3D9quF76n1ZWmiBxYSZWUxdGrIi10OSI9DChAJtumglZidzq6tT+9tTeajItE6wAxhmCtu5otLub1ZRt//O6PJKTMOVJq+tZ2tek69g4QAci7KHUCSHZ95Zazb/76b0xu35vVm/39vc35qQRKBoOT5yeT6Y4UMsqsd6sMfJUlc99zngWdAhJH5mBja5Oi6psNAEitrQlJXmw5pOg7RA2EWVF1s4vVYraVPapiEKzd6sm28SB6w7zVnQkkis4jQujbLQUfBAAzMkTTRggMwAQxBJSCBPTNKhsdiKzomjWS4uhVljvTITCb3qmN1AoBQmQOMdgeGEWaSpWiUJED6iRC7NcL19XP+u6z3/zl/buvhmZx/vhBXo2s94wIQrAg4MbGwEQA2/IrIQkplU4SqTVJeU2W+gQ/UuZFvi0uxRitCyQlCsFMkZE9R9tH37q1A7/FKv0ssPIn7KltUswvLXppy7b4FFEDt48RWAADYNjWG35KGwkYmSFytJZj0MUwmhaULg/uBdsnw6kuhqFvdTVCouB8vVxYlpvTJypJiM9UVtSerffRedPUAiEEtzw/T4c72Kwtct+11tqTZ33d2SQaK3XfG5WmDBGJ2sVireXGx3Yxhxj1zl6WFwx0dXkeT57sTndTnZ1fXFbjCTK//vprdb05P7+YjMd9PZetl6BiOoyrq7Pzx6raoXL88NklCUiq0aDIHRMk+Z1bB88vZtNhdT4za1SSAipu1+siS00jdTGQ0XVtv7u3u1kvpsd3Uk1zw0VWLS+utlo6QvC+B29evXtH9s0/+H/856uL8+H0cDqqhBjKW7dFmstiKIsdVe4wYoxRCI0CpRRKkkaQgg7Gxa1pNSpVIqSSQioplACiGHm0Mz02vjf9Vz93z3k/W9SPn15+/PHT5YK6dg1CAiCDiN6xNd52WK+/+PkvKm/f/t2/M37ljeWzx6dPHu8dHB5/9nPlzi5K6UxX160aTPrlFbSr0DWUVcY6HJYIwF0fTEd5ptPUOxeZE0oEcm86DsZ0KyCqhlNTX3Y2yCRDqTDJiVRUW2aAYASO0XctotCDYfSBIQIwAgGDM50UGEMkIsAYvGGIgEgoYvCAjETR9MH0uhw2s43QClDKNONVjN7H2JPTHkIwNSDHGFU+lEkeotfVjm3WQmiZFrZdISfRkgh88fDB8at3huVh8O7q5MTMZ4jIDFKlrGwIIQS/LfEwAEqZpIlOEhTyJzR3W+BInWki2kZAaYNAJMTIHKJ3pnNpGkzhZRdchwSAAeKnDoLXotqtPiDiTUb8ImAS8ScZLyPclJa3IRnii6uAYECA8ALY11kzEkoFKJAEJUlwhmSiypHOqoMv/3Jzda7KYbe8tPW6uzpBEsM7b7TLte3M1Yc/vvdLf6U7+2j19AGgcN4jBNt0AJCUg9eP7qy7fpjnDBA3i7ptPUOW59THzlr0lr0QO7voDHvTR+htMEIP77zmTPf844fO9M50g8kOFKPZ7BQQPAsN7v2PHnQ+But9t4EQjMxi8FUqqNqbffxhdXx3Y0IwNs3ScjDpm2VA8fZ770Pft5jkFRRZKUj39YqEgvFkdTXfu3UcrW26Pi2Li9my5/j67VuXD97h6dFivZFCmN4iQnC92yzKBPuLp0/fWRaTW6+8+SUW2oGGbMC6ECrRaSZ1kmih2WVZkkhKlNCEAmImIZFUJHKnkKkCQk8Qg3fEEhAkoZJiqJSvtGe03h9Ohoc75dFOdn452dTNel1vNnXTdJt157ouui6R/OiH3/34R3/crM/SvKRscOutr8/WC0Ydk4SJpEoGu1ORZo8efzB//N69L/1cx4I36yASgWDdGtkHb9hbAiSRKCm79Ryii94gROCwmZ8DSdQZowJIUUAEDwBMFBzLLCNB0Tnm6PsOIXprhVQcLHLk4AKTIMFy268JjJFAxBCZA0QPUqJWwRkGSsoBgA/WAINK8t6uSTBvYzSitxZFogZjDg6MB4hCqkgYvWFnohACReSwmp0W40LtTu+++UWtku/87j9gKYPpo3MyST1DNAYgRI4AUmmtslQoiUjX+hp+yUCCo/jKr/4biUq10IIUIgECM8bIgUPwPgQXvQ/OBuuIfzonCoHhU14U9GeyXX4pbCLSi/oTXe+MCNdhlraOEDed5221WaJURIJ5WxjD8b03kbi5OC33jmMMZrOQSS6TPAaPKhFazR68HYMJXT08ehXTcnPy0Nbr1enzzjhZlIM8s7bXUiKwStO8rJq2LgcjENp5PxhPPYlb9+597o3Xoml7UrKaNJvN3sFRkSbnH394efJcqGRnPCp3jzc2WB+TvASdbDb1ctWMxqPxzng0GnVdD5NDoRLTbgwT6NTXy/bydHx4PN070BiW640QIhHUWr+/NzFNt1iv7Xph1/Pg/GoxD81GRt8FDzIJpBaLxc999Qt7OQ0O76Tjva7tUEDvbLNcxL5Bb1SzMOv16PUv733uGy6bcjXNJse6Gg2Gxc5ksDPOJ4UaKT/QsYCugG6Ifeo2hV3tJbyX0UBxAk6xT4kHmjJNiYRUgJSkBClJmoQkTohyJUe5PpgOj/fG+5MqlYK9gehCcBA9sXDrBc+fzuenB69+sRgfBNtffvwutVePf/wny9lMqOxod2d8sL++ulw9eLccTyavfzEtMs/gnROA7D0ICqaL1iCgUJqtM6t59KZbXrJ3QokXRVfmGGMMIUTkaykoii3hYds/jd6TkNEHbxsI4VrfHSOgACmus8RtYdR73hZRiUgoZiSVCaUR0KzmiERSB+9RJoCCow/ek1SAlFYTlEqoFIBQiBg9OyfSTMRIBJSkUukYfF4NkAARbQiz589937m+td4xRwQRIyNKQlRpkuaZEGKbAhMRvqRwBQCppNRKEokYoiAEiDGwc84miUoSlRY260SSoWjYb3+5n5kk31SU4kt0aIpxy3vmF00dvg64yEyABBBv/C5e3OKnjho8AgSwHLwaTJLB8OqDH1T7t9r5x/36qjy4W04PcTBFncZ66epVjAE5al0EZzYXz0a3Xol9M8hUHJRrRyLaRx+8t3/rNjfdoKp6s1j0/cmjhzt7x9l0v+l6KUWV6r5pHzx4qFyXD3ayalQoIZLk7PkzKseHrygvdJpIUy88ptV0X5t64/zw8O7y8lwq3VnvIKkxH3OwptYqS6tqsXCb1WYwGFkWtl72elTkBQDMVnWZCPDuYt2xtaS0q2MaGju7ZKWMs5AKTuTs/ORz92+9cWf/2cVCVwMKVlFcLJa3D3bN8mrl+uj6w1c/kw6mIRmez9Zo62GZZVBXVZWqDINxV229vKoXs3Y1N02Tp3JU5dZbIcTx4eHh3j4JYYwFhEFVjIfjPM8YMQJEJCYJAFKIPBGI5F2AwNJ7YRpo17FZYLdJg52kspQFg9ST7NHio6wcs+vbdQsMg93bJ6ePvdnQyUdkOiHpzd29USLmZa4O7gWAqhycP36ipALnRJqGrvHBb0vHYBvf94wo8mrr14MgEALHANcaz4jgESIJRCaAAJGjIyEVA0dCABRJggJcXcfgCYmRWAiOAMQYmQEiO2AkkigVh2DXm2x6AMCA0ttGFYPgrJRJOpravhUqYWJBQqYZc2AitkFmpZDCG6ulitKSEH59xSBi2zipMJTnTx+fQcjL8gs//0vHR0fL+XxrX7Q+e/r4vXcie2YWQkmthBAv6rMvU/23lyppuz5PMxIUttKboJQKSkoplVAalBY6ETolqYJ110KDT/nb8I0AD/HaL4NfXut+wspgeKEQvI6r168Q0ja1phuN7qc/I4bIDESyHMokA6Z0vCuyavzKdH36KB3tDe9/6fSP/5Hv28GdN1zfJINRUo43F0+y8dS5UM+umvVqOLwltcoss6fJ8d3BaNL3rZC4ubyyshwc3NNFxqREMUgGw8l0t52dtC4ejcazxSLKhITg9Wazrj1iNZkSya7d6NFelWUBoDadynJnDAo0xiBAFHDr7i2zuAyExE4QT/IE+na8f9DIRGdJZFBKzE+fL9d1Mp18/PSkxuIwSzwKr5SNgNFlAKKa9Ky69TqD7t692z/63nfSnf1H3/04BtehPjg42BmU6ec//+P3PmoQsJhcPHtkeyNcN8h1qaaKks3q7LLt1qv51enzy5PTzWrZ973zTBKTJLfOQQxFkeV50fd923W2M3mqB8NK0LVdwdalSSu5bVJoqZ21QqpqPFRZbn1YbGommaRZAHbOaqnJh8V8Xa9Xy8tnAEwy2bvzmcnhPR9Mv7o6+eE/o1SXWemXJ4bSg9t3NfODH/2oW6129g5adlKItu+FTknIIk/NegmS5GBMGEgl3jZI27YkR2aOLtjIwQvPwCBSwBhJKkCMKJCRIXrTAxIAklTRuxA8CnldYokRGIGIQAaIgMwRAFFmGUlFQpDUJBMWDIAhhKQYMmOMBlGCTJE0MgNLleccg7cOBSJq9h4ARFpKKUCIJE11lrvgmdhbs1xcvfHNX2msW11dsjf98W0k+eS9d7yzkUEIsfU5e0G5wJdghYjy7OJcJno4GBBhjERISCSkkCSlEEqSE4p0QjqNbQP8Un/mX+t2U2q+DrUEW3ZkFIx8Y0wDNy3f6zU3f7r3c51Tq4RjEGmOSuiisus551U6nLJpzWrmne1XV0N4U2UlCd2trg7e+jnXNTLLt5eI58+epdVoPN1bnz2WQtjIwBwiJNUEKMmVcpsV9puqHCoplnUXQGHki/lCRL++OttYvn3/9d1Xpu1mZVFkZpWVQ9Lp3VtHNuJ6ui9jePz02XA4GubZoMpnl7NcJ+n+8dw/KYfjpq3zwWi4f2xkitZrgefPn4TxmIjKwdih1Hk11vlmfuoiN8uZJxUiM0Pf27peum7++ddeef+f/4PZg7cd42y5TnYPk9tv+L6tquLo9m1A+P7vnbYs0zzf39uDzWzx8O0PnrzXbjaLTe8ZkjQBFKTV8OjOjlJSSITrXjzFEIPzgfOkGg2Cj87a0BnnnO1N37c9CmCUkdk4H32EYML8EtgAEKZpWpYyybRKZZKCAFBK6wy7Zja/8qYlEsBRyqRezhCCyoroPQf/7I/+ISzPJ/c+k77+tfGwmj9/Xl9epmkeomdBGCJIwc4lecZ9B8wkFKMgoUSShXa7cCJG2JKwOHqOMd4ECFkUHLYBZFtDQY7eOwfAHAIAxxiIru3/eEsoiNeiGgDiGKM1qiiZfQg9ekFSui6iSIhdsC4b7awvHrNtZVIGjzEgaeQYYrBEItheqESkOQGTlKFrVZ7qvLTeIVHsbOcDL+r333ufdGKb+uLhB8H2KFWVJ6HpX6gXGBi2RWO8rnJfu/9xlIvlIs2zROskSYB95HgtqgPYOswgCRQCpQKxZTReh8sbn7uXg+rPwi3cJMcEuPWvuAm2n+zDP2lFtT10jCgVqhQFkZCuWZMYNxfPQ9+ko93Rnc+cv/udZnlRHd2f3P+S7+vFw7cRkSH268X69JHMimpnz/adEHKgkUyNpl8tr7JX7muCxabbmU6HElmmNtW+b0lgvdkMd/IucqqVF0IQVeVwPNrr5+cBKcmGRZYsV9jW7TTXHklniag3ve3v3z7UQlzOroLKhgdHl+fnO/tHkJZ1U2tBDqhZzExATTHNj7JqzN7uHx4ZH4pEW9ubrrtIdL1qyqpqe5ftHazrplutAsZJWZqzx3/y9/8btN1qVcs8V2fPKutds/mwu4r2FwBwd2/ceZsJXj169/L5Y7ua7+5Mdm/d/mxVuch1067rZr1e16vLum2C64NzbNzWzA0RCQWiQElAKEQikyQXYlDlNBxFoa3zg+EIdRoFBNc286vV1VmwPTIa79x6GZT83Le+3QW4PDu7Ortk04JKwdQxMiJG33drG0KExVVSDECoGNz54/cPfum3dl65v7y82KxXIst0krbGUJp6DkSS0coQ2k2ti8J1fYgdpkmSJjJNHd8wdgQhM6GISCwlSQUQ2VpRZKjkFqWMFEPk4KJzKDA6E31EUiDFNSkKOYYAcRtPAgmBJHzTMIMiGUlInZo6SkmAMkTHwNlw2m+ugu21zIRWJNF1rUwTZo8kRJKw89HbiGBNp5MkSVLjrOuNkDLLR9lwcn76mEPECCHGEIK3FqM7f/pQCJLFeOf2XdDJJ2TClyQADCDbup5dzfK8mIzHMcbIHCIHhsgQbiLzVn6DAsHxn8EY/+ubr153aF+Igfi6n3YdYz/dzv2EKslbbrOIro+uV3mZDEZ1s06qkY8hmxz6Zh2tUVmmi4ptP/v47WI06VdX3rTVwW3XtxxDUVVomtDXQsSj1z+XlwV0G9jUmOY6z5XWpjfPzk6C7SdHd8rpHlHYrDY0nhrAtBxjOZZIFGLsN11ts9EOqrR2/uT5aVlVJoQiS6sy32y6PiDOF+VoLIBnp08KjifPHx3duaszfbGc+YDH9+4kWTnWLq5NqiUgVlmyWV30bXd3d5J42/be2Q7KicRauZaZyly3jz46e/RhpmVeVWWRoAjgrWs3H//g0fxqWR0cDLJic/I8c6tbO4Pjyefv7O70m8WffP+H3/+T754/e7qcX7zUawMJADINKpFCCRJRKBYaKIJBYEZoARFhu1pkQgREjlt3ItJKSEUALBIlmQTRfLnyhpu6Gd9+ZbQz5vD6ZrG6ePrg8qM2uJaZvfdKJTt7B+PJZPfu68/OZ49++EcR5Wp2JZ8/6dZLrbVQUmZJ0zUKUxACBEmBUSWcZpAWSFJLBcElBC7NrDHb3JYIAyODFCojqUWaA3LwMXaN8FokpcwHwBhjIJX5tmb0GAMEHyMTEwmNpJADQAjBbr1oGEAVxbWWwDpMisis0pxjJJmEbultnQwmtl0H18XgAAK3noTYIlZqySHGEBBQChVIlKNJu1m1vUmrEZVVZDp78sj73q83Ks2DszI6Cr7I8unewfziue9q1zVpmobwU0Q3iCjKW28gEWklkyT46LyzzhtjjTHG9s4aZ4wzXejbaFoIHmDbg4031nD/OhkyXssDmK4le3ij8rs20eAXlxO86Qddd4UYIATgSEIjBCLS1TgZTKqDe0CYDKbjV96KzqmycnUtikImWew72zekVLV/NzgrsrLaPUJBLrJKCkwLa/pQr0SST45uD3Z2z2brZDCMIWoI0zuv5INxZ71O0/LWfZ0VpJMOpO2744MDNG3wIZvs9tYlSmWJ7DcboRSSyAjSJFmtl1migWO9WrX1ej2fxxAHg2FWFo5puLObJCrNyuX88mA8gCSd7k7JNG3fFkXheztfLYs8W12etwE7QO6aQsmIoLwtYnfncPLK3dtHh4fj0WCye9BQ4qvpKJXhg+/45eXZk4+S849+5TN37h4fHozyH/zRv/i7f/fv/OBP//RicWXr1UDiME8mk929e28dv/qZydG9avdgOJlSOZRZqbSWAokjRS/AE0cCFoRCkFSpTLKAKi1LqRVpFUl6z9b63pqurk3TbBt3V8+fnbz3o7MPfrw4O82yXOq0zKv14lKl5eHxK/deuatU0rTtxWz9i7/110hXl5cX2K00hHJnfzwcZkr7EJrNRqapt71bzSVRZCBAYh8iyqIUwdnTBwEx+rBVFEWOKBSQAiRSCUiJsFXYhrB1pQoBBJGQSIJ0BqQQJUOMvt+ShwHEdedjy+ciJimJKLrAMSIKkgpQECkkgOgBHCm1NULsmwWEILSWWgGykAoJgnEIBNF1i8ssL6vpfrtZN6uVSHOR5N67brNwpp/sHkdn2s3GuT5NhG9r39dtvZQUo3Heh2IyiSxe6FpfYhGjSPfuEBEKobQGZmuttd4aY52xprPGeGuc6WJvQtdy2HJf4k/1y8CfaVa+ld6/4FYivBAU3PRtt2bSiJG2PaQbWzgEBo4QIwpidohSZoU3fQyWfZBJJpI829ln52y7js7GEKJ3AEhSm+VljJBUI7NeVGUB3mmlvdDN1XmWFzzYHe4esW0vzk52948E+2qyw/nIhqCkZJVW48l4MMgHFTQbiZwqxX3NSR4Qo/eRpNY6UUpKqRItVJLmWVYM1puGBDXLGQS/vzO2zhGCkpRrdbFY+no1m81HeweRMC+Gd3ZGj84u67rduNBG3LSdAwKREGGpZG88qCSySyEMJDx58O7zjz9aXl5enD039RrTFBB33Lz/8AdT7NTy9Py9t7/4pS/s74yXZ8//8A9+38mEgD/76t3f/vYvDvfvyDufLaf7mTOv9xfV4jlePoXZs9np08XstFte9OsrW89du3TtarvZZmnrha03n3n14N/6K1/5wz/+uMwL1/aud8AspZBCybxQSUoiZRYYHYTG9XVXX81OT7xpvTMyK4vhYbue+2wsB4e2D21vN73/H/z7/1Pr7Pnjx/3iYnx41FoYTPfWV7O+65MsMbNLM78sqmEEKLJ0tDMFFH3XQrdyV8+CyOM2B4iBmYEkbJ3lgIAIpdou70inQkrfdRBsjA6QIQaODEgkEDnEwMCRveNggzfAATgiAQkBkWMMEBmQUchtVQkgsu9DcEQyWpMNJ+yBCXVayizjGIAhmM6bVqWZq9dJmhy/9jnX923bJcMxx4hSs3cQo1TJtoi9mp0hREGiX8wRYjRds7rquw2ArHb2GCXeWD5da3AAmFno6REibRVAHNkY5611xlprremt6W3X+b73vQ19y97/mbXri1SZfwZo8ZpKhgAUAYCYrktQW570VvcD8SX+GSADIjIyMiMD4dawn0ipYHrftwioq8l1ly5wM3uuskpXo9CbdLxb7t3KykFWVbooo+kkoUqUjSKQkCqRSQr5AEimmgThaO9osVyYepUnql1cScK9o6NienB5Na9Xy0yr2zsFAdTLGUs92zSpQCUlO5tiTIqCUFC0PoSr8zPb1akSgTlL0kGWKCm0llqQ67vD/b08zZq2E0IOJqOLjcUk87ZrbehcCDJd1r2xPi3L2abNdNIsFmlVmnrVb4wESLt5e/k4JR5XRQyuzBRsrkZ+M4bObRahr+8c7PddJ4jv3bm1vDw7ffyoa1e/8zv/7v/pP/s/fPe8/1fPmvH67I3TH01XJ/sivJZhJnFh49yx2TY8cSvVJCRCpC09CACLYrSpw4OnVyxKlVRtbxgpHZQkVb/p2KOFhJJMVwOZKGc6BIVISieh79vN0vWrYHqOwrezr337t7/y63/1C9/6lbtvfsWq9Narrz579GSzWDLZ/duv7dy+Oz8/s22dkqzPnwspyr3D6cHx0Z17Ms1Xy6XtOzd/HtuNp5TZMsQYPHP0MQamdDBEqQAQSDAjCrUtPgNC8A4AOHhvavaO1FYrs8U5IEYBgpmD9xAiRGAfmINKc0CKziJyDI6kQASGIIQCYNvWQqbFZD94G70LxgiCEBwhQQwcQjnZefVLP+e9b5smHU5Q6OAdBo4hxBCZWaokQmxXV+y9QPZdF71TCFfPHzEjlVU2mCIIuqEr3PB+OTILNTxCIpJSKgVA3jrnrbG9s9b2Zotb3/XB9KFvMPqfRCXyjcT2JoT+tELUte8MIlwDON7YPm5Be3MlwK118yeMjAgMSMy8/SGRhMwrZih2j4qDu1uH53z/ls4Hqhojyn5xprIiKXIK9tp8kqgcVipNe2NFVvV9vzo7S4vCmS4VxLbrXBTs8yKzlCqCe6/cI5UuZ/NBJtNE+65fzq4u5osAMqYZy2zTNH29UaYu82S1XHcMGvxEY+TQNf1gUPWd6eqVJITgtaAqz7I863pnTW9Jy6y4c3ToI5cSG1brpl+ePmWZZXl+ta4NqHa12J0M6sWlq9fk+wgCo59Sh83cO1MNBm+9+ZZOk8cfP/z8G6/3zYrYCg7ozd54cHV29s4Pv3/+6EPXrb7+za/9H//T//T//F/9f/6f//A72fzZW8//9N96ZffW8a1nrXtvUX9n1n6w6RsfEV9Yc3Kaplopa822jsAchdBdZ9fLJUOsV2siSTpBlNZGy4lK9Gdf3+03q9D1fbu09aa693rwiM6TIJIKUbGPSVZKAQ9/+Ad1VD1kJ6dnD773Bz/8vb/XNmtr4+rJw7y7rHZvbzpbDAfs3PrqIh+Np3fu3HnlHgp9cXaxqtcQgj17IJk8IkePDBwcRxdCICFVlqFU7COikDrbspFjYERSWYW01UUIEpKdi94LnQqpgYkZYZsSC7H9X2hNQgmVcQyIHKOLzggpRJJiBPY+xoAAtt6QIoFg2zVE551BQaFrkeHw/pvT27fZ9at1S1lOSYFSIkJXL/PBmJlD16RVKaRcnz3zts3ygk3ft6s8kZcnT0Qyynf2QSREJITYRtfIL24g1PAQBZFQUigG9s46a51x1lprjDPGORd6G0wXTYsxfGL2FG9cjT+ZFvIpG5ptI3jrinwD2mvB/I3+54UJzktXkxdEqJt6FQKSFCgIpQRS2XialON0tCuThAGH994iKdvL5zovSaqqKspc970BkfZNSyrN94983/oIejRNsrwq0vX5s2o4mNy6qzAWowkhZmWhJ8f17KLM0/WmWa83Sus09BfnZ0Krvusb4/KD252LbjO3XaeTpEqTpm2N80RoVgvjPQKsN03XtSkERJzP5l29adum6c1y3ayWC+NsmuXWulnb6WrcRxRSVKNxXo1qa0fTaWCan58ShMWzRztlqhANYwSoNNfnHz5550/Xy9VsPru4uOi79s033/zmL3wz2r5MMJNcJcL1nfd9rlGreHy89+u/8Zsfnpz+3//p95O0GHXzv/KNL3zxzTeePn32vYv1P3m+PO0dA4jrnAa21+0Yo3NuMCiNccxMRM45ZidEZGelpLzKCdi1pszEt7519/zpk//w3/niuz9+//T55fHRcDIsHGR6OEXTeraRoBiMGUERkk7zLD/94AfOtBUsefG0kPzql7+5/+rr84159KPvmfMH48O7e6++ng0H6c6OzrLhaBwYNpvm9OwUiIOx/uqxkJnnyNEhUuSolGbrOQQUAkkAEgrBRKQSRLlNoQFQKC11SjIhqQF5y5FGhTLNSKi47a6QEErJLJdpKXSGQN512xEe4B0QBWuC6UhIISWA8l3DrvPeCqG86xAx9r1O0s986y8c3n315KN3l/OVyCuS2nZtMNc7AMJgut8uLm23AY5dvXDGVGUFzljT5Ym+vDhPJvuUFBEgwrUpHl6bJuIWckKUe0BEQhJJZnbOeeecdcYab42zvTN9MCbaJpoOY3gpKX5BcXqpcsQ3EZdf9FqvRxtc15+YASJuc2NA4AgvNPGf0B5fLHdJkNxaSyIRyqQ6vOeaWpdDkgoi6Gpo27q9eM7OULB2/lwWo+LgTr1YyLzC6J01odkUuwflrVeJhKlXrl5PDo5kPhBp2tf1YDjW6NM0zYaTdnG5rDvrIwWzf3TQeoqAWTRXs3kxGu9UZVgvTVNTWqJULrJvNyhkmqYJeHbO1BuE2KzWg0HVrNbzy/OqLKy166Zxxo2GQ8qKWd0LooUTnQ2eA0K0MYYI1tjQ1cp1bW9VmunQdfV6Z2fsQ9SSYHX66jT7xle/MN7ZOz7cv318dPvW7UGehWAO9yYDBfvT0Xx+YYzNUzUdDco8ta5DlTrH7z1+trTyV4fL//g/+Z+3Tz7+ox9/8P9+PO+i14gxBkBkiMBARN57KWSWZvdfO7z/6jEibDb9z//850joxXwO7KM1rt+w63zbTIfqN3/1tbd/8La17Z/+4CMh0//t//rffPrs4qO3Pxoe34mRMcbd43ukUm9Ns95kiQwyG+Tl/Om7fdDlnc/uf+Gbsdzzsvj6L/zy/bc+/+CH3+svHqWD6brrBXOaZtPjQ5FVy6tZs1mzc9HaMH8OKvfBIUlvTGg2ONoX4wNoa4yOSAqdotRbI30iEjoRKuMQIocbXtG2wIbBtuwtIqEQSPKmOipJEIe41dADR44RAWVWkkog+hg8CgIQwdloOoieo5daE4LvuuFk96vf/m125umDD3oTsulBUk1c15pm4Z0RlEgh2dnx3kFXL+vZWd+sENhbN53sxr5zti+L8mq2pKQCwBhjDJGBmV5MBWAAiCEILHYQEaUkEgwxRO+ddc4457zpve296b1po2nYdMDhmjLy5xWM8ZORXwIwIgICbQvPW57yFrQoPtWuRbwuWW3zaQIAIZAYvBNJlu/dFmkOiMF0rmtkksQQXb0a7N+WUqajSbSWSThn0bV+swzOpINhvjNlkOy6aNrVx+8lWlqG4Ay0a1uv4nCPpY4RurbpXczYcrdG2wkkzIroukXjjLVDBRdnZ1eXF1IlTd+7rusXl+1yiSia5eWmaZFEVpbeQ7tZN5v1/Pw8zzOUwlpbJmmSZR5ENRhpSTLRaZ636/XXPnN3UpYPT5ed5yrTgaHMkvliHTqj8jx6zz66vlOAyjevHU0X5+cfPngQXOP6pUAaVuUrx/ubi5NRlQKE6U7WrtdKiCzXiaYsU48efrR48pE3DjT8r769d3AwevDP/rv/7uHm3csr31um616aEASAIcYvf/F+2/Zt1z8/uXzttbtt0zuPl1ftZmOdM0AMHDiY6FrgfrlY/Kvf+27TdGmqf+3Xvr5Ymv/2v/37v/Fr3/zt3/rKP/rH30t2D4eDnV/9jb9krL96/sQ0Z11rkL3UGklfPH/c9jw5ODaBL65miVK3DyZN3X/4wz/m+gK8QyHynanOCkl0eXJigycAcCYuTkEVzNDNT7rZ6Wgy9TqHNA/ry62tQ0RCqUkQSo1SAkqhE0AB3qFAUrT1RYneBtcLqU27AQ5CKQTeDh9EZBTAxCRk8BYJIbDQucrLrXEUkQ7ecvQcHUcPEIN3ktTh3Vde+co3fWeePXnsGbPxDiUlM7u+jq4nRCG07+t0OJRam6623QZR5llp15vdo6PF5YXruzItrq7m8YY9yAzbFXDw3nnv7bbSZARlEyG22h6KHIK1wVnvrHfGWROMCdZG20dbszXIga/7Mn/uPEu+plBgvO710ifOMttRQFvsflJ92lKUX2TZEBEiRw/OoNKkE1mMANg2a3A9AMukcM0mHw7Hh0dpWejxYVKNgrOua5XSSZYlWSbTwvZ9v5rx1fMykzLNQWehbySBqkY+8HDvIDSbcjRO8qKv6/t3b3nbRx+zokjLYXB+ubjaG1brtvfB921tuq7v7fzspN/MciWaxUWzXntG1Nn86uLy9Bnbbj2fI/JgWDnnSUgEsI4P7txpfUil8MaB62IMsqwEYt3WkUlyiN5AiMtNqwT0m3VW5J2PNnjTdipLpEJu19/6xtcmZT4dZId3bt2+dw8hnD35GGI33ZuicEVCAkIkKstsXGaTwaDZrBfZ7u0B/5W/9Jczb7/zL3//9x+vl31/62iv60wM7GIMkbccVJ0oItX3Rmv9/Nns/OLSWmttSNOiLEtjjUDJEACBOSKxEFqn5cnJ8u13nn3tK6+9/pnX2r579Pi5631nvfO+7urX3nrrjc9/bjLZRdSr2axru3K0k2i1Ovnw5MEDX6/84uzsvT999zu/vzp7MpkeXi2XGl05GJW37ndtu7xc2q51ACQFdE1YnkFaLh693a4u9t/6Bo0PnRAQbNjMpUhISCDBgNvBAqTkVjmg0pwQo+u3qV3ou+CsSNKIQEiRfXSGhCDSiBTBb1Pi6+mPJAEEMEutgvPBeZmkCBRsz95iDAJIIO7fe63aP7p4/Pjq8rKY7mfjfWdCtzj1feutAYhpVgbnZKKRIBhj2lqohJDYe9e2e3duz89Pu80ykXI+u+Brqta28MTemuhDsNY7742xpheUjnGrdQCEGIPz0bvgrLcuWhucDday7dm14Dx+wg3Gf51o+8KMAq+9W3+CN4HbQa8v9vyJojMgc3AAILKMVALMbjMPXZ2O99PJ/vQzX6v2Dse378cQ17MrItJajvd3k6xKB2Nve11UIPN2fpZI1FnSLee7r76RFJVQKlHSikIpfftoz5vec+xW82C6uu0h2NHeXgvJs5PTurer1p6enDmRbZbLZt04pq5umqtTKbVSsqnXjtFbH9p1v17U8zkC7+7tpknivLPOJWkWWEil5ldz68N8sVq1Hei8Gu88efy4Xi1J6ZKd6dv55Wy1aTB654zre94sRfQyWIxsjOfgx+Odbr14/uhB3fVZkd969f7O4e3BeOi7utAxLzKCoCR0nVFJKiQRcte75Hjyl748/sIv/Af9yY8fPXrvw7NWJMW3f+ubs8vF2WJ9tDf+1V/96ocPnofIq1XTd0ZIiSSiIKU0YvTBHxwe/M3/yb/3h7//h4zM2y80bp0JWCelSse2p1ffuJtl8k+++87f+o9+68c/fnD68JFtFufPnj788OHV5ZXOMlmkbd/JJG27VmRlNh53l4/dZjXKU+E2oV83q8vF/DxJB1cnD8Vouv/Zr9WbFgIbZz0AuBDbNdbzi6cfNYuTO9/6q2J06Pp1RBFjwM1KKc107VXIccsJoa3/vpBSKBFj8H0bnKM00dUIEEkoUhqFBGeiNaQUoEfgEK6bwESEKGIMQicco+97ISVJHYOLtmXXx67RSTo6vA1CL05OkmpUHhyjzIAoBhejZ2YOLklz29ZCKRKiW8yCD96Z6L3ZrILzUiTlaDgcDqs0WV6eL2dXUokY/E21OGzb0RwDM7rVSaznQqYjQASircIpRhe9984FZ4OzwZloXTQthw5i4E+Rn/jP2fBTfm34QrWHDEA3szD5BZhfwuy2gcRboaDQSbQGQgAAlFpI7bs6rcbFZFfo1JnOtY3MBopgNN0dHd7ZzC7yamyd9yJRWaYguLbWWSaSrAvQXZyQ60ajARHV58880mq1unz6cXN1VibSt40a7vSg55dn/eIyABnjMakWzx956wJit5gH05FQHIJxXqjU95uUgJ3DGMqyGAwqqdR6vW7qBhHretP3/Wo5b5tNML3veseSo7P1kqRuu0a1CzYtCxkjdHWtlEIOrm2Ao4YAto0uFFpjBCGkEmr/8OiXf+WXP/vlr6TVeDTdf/MLXzzc3zPdfLmcKVV409nWMYNSyhqXl8lv/uorX/3SF5LJV4yd+WffWT1rr3r4J7/3vdWqMZ4HWX7n7v77Hz4rpgUExsj5SJHWeu9OsjNk6ASh9eadkx8BhX7dAoBQcluGJCJrul//jZ//3/3v/53/63/xD9/90Y9idH/n7/7Ly8tVkpbRO2QXjV1fXpw9ev/i+VOKzrUb08xcs0KVpNN9CrZeLS7PTurNzLoOICqJRVW9+e1/u9yZmraPbWuDtaYHHxOKpz/+l5v52d2f/6v64NXojWvXTCKaLm4WpBWhRAaGKKTiyMxBkCShtyZn28HTzKzzUugsWBOdYyBdDIVKvTUcHQkBhIIE+IBbB5/or10ccEsZCOwNeBv6xjebNM8nt+80vWnqJhuOk8Eo+BiMXV087dfz6Ex0hiB404lE67R0q2W7mqOUgMI0G9OsiZTQKh8MmvX6i5978+tf+dIf/PN/KpTka2/DCJEhBojM0TP7aFuOUWAy4O1Kckuh9z56z95H76Kz7A1bw7bl0MN1pv3/i1jgxl0VbvjMN7QKuC5E4U/0iRg/6SHdlKu22U6SbmfAj1//UjHdL/KsnO636xUzDo7vp8Px6tnDw9c+8+zhk24xo3KYJMnezqg3zlqrBa6fPWwvT5PxtDy+H7xdPn2ADOnBkSBZP384GJQcWI92albGuNrYfr3qm2Z2cWm7jpKUnXPNol8tXddInQLE+uoseGuN930zyBMt9XK+ACIEWq83y+XKWrdtdXvnEEBLoZQmghQ9M+dpKomcM252GYUYjSfe2j5AiF40S15dklDJYMhMIlECosqziFAMdoKp3fJ5lSSvHN+y9YZcF/o6hs73F8tll6Zp13eutzvTUdP2HLtvfO2tgy/9myjz8uBuuv+F9vGjH7zz4cLD3v70P/j3fusP/+jdH7z9YHg4HN+d5DsJiXz/S1+J5SipKrWze/v+0X/01//G46tH08/v7L62W+5Xk7uTGLncq5Iy8zbmefHkdPHxhx/Pzp8BeGO6PE+LYtj3VutEKuVDePOzn5/sTGw/985Y0wOCIGE3c+5tYO7rBSHhtQsDDgcDOT4cvfrZfDhaLdehbdlaU6+JITbL2cMf3fnqt2nnHqYJEjenTzHPXL2GriGZbq1QmJmRRKIhRg5OSALkGBiQRJIIpYHB9WuSidCpUBoRUQgEZOc5BiklCS2FRmDvDPuwvTyJJENmji7aLpgOIaZpkk+mvfEcYLh/nIyn1hrTNfXsLLoeEaVSUinclrP6HgM3m4Vp63S8T0I1V6e+72SSbLV369nZZFC+cf/VH/zgB01d43YuxzbAxnjtAeYdkCCpBObD644wMMfI3m99tKL34Bw7E60Bt+WL0MvJ60+b/fUzGFE30iAk4q1tKtJL3R1+SZ/LiAwoSSqhEmYGItQaBaWTo+rW67ocqbzcufeaUElgGr3yuSTLve3Q90ma15t1u1nu3H1NVmNEnJ8+j3YjSBSpBGeK0WRy5zXX9/MnHzFpT2JQFMI1qW97j3K8z0nRbzbg29XJ03rTdL2tTx/brkaE4A17H0yn8rJfz/vFhS4rADabebCu7fp6U5vetl3ftm3bdiH4yNtEi/n6DggAH6MLTEoRUqZFokTfd0FXXqh+s47OUIyx77wzOkmK8YSIpLeJjCigIJYEk/Fg9vyDswc/fPL291y9yDKcnTx6+P7bvel0KjvTSUm+70c7pemtJHl0547MMSkG7Gn4yje/+Nf+5u/93u++8/YDnWrn4tOT8+FwkFRZupOwHAze+Ebx6pfH9+8JIeurNRvzw3/5z89OzxEUYEir9PDzh653oQ/ZqEyT0W//1i9+8Hj+6L2HHP2W3Pqbv/H1yXjw8cfPAMjZ7stffv1v/Lu//I//8Xe+9MW7CLhYrBEhxogo2PvgekLF26wKgYGUECovJ/c/mw+Gfdt29YaYOUaI4ekf/r29V97ig9dBiq1up99cCV2Y1aWCmJQ7nmPASChiZEAhtQZA39kQIxFtuYpI6GyPHIVMSUrArU9yBGCSEoExeHkdSzgY421PSpFUiADBcvBhvRQC8+FIiKRZLdi4cu9IV2PnnVSJSDKlEyRUaSZASCH7ehVN0y2XkYUzrbc2Hx14Y9r5BRIm+RA5yiT5ys//wuffelMArxazJx9+KKTire/klpbPkUOEGCA6YCcorRh4O/APogf2EDz7wM5BsOwteMPR/6xI+lMMGX+6T+PNPL9PnBdvlEef8rrYihy3QweJo4EYRZKBkCotkuGOLgdmfpGMdnU5jvUi1MvhZDqsynI8Tavcet7b32/aLiEeJCJ426zWdnHh+27wma8Vt+6jN65rrHGu79rzZ9NCXDx90ssynezJwc789CkBrzem3dTLJx+qtHSmCbZXScHBM5NMMtvW0Vmhtc6rfrVg75AwMocQt937rZ8ebQlGiCQEEQHCVowBzEIpisH37XZZiLrUOol957wvylKxFwJB6qgS7prQtVLKPJFgbYnt7kAVRVaqmNJKCkiT/O79+0muKJ1U09tf/cVf/OjDh/WyFkDDYaG1jtHvHN4htZnc/gqqfUC8evrk7/9X/7erzaZuzMOPz3WqO2NNbdYXKxreSw6/uH76+M4bqyLtHvyDP2hOTnUhD47vffM3f/P9D94PtYk+ehvW55tiNLAb/pMfPrW2RwAOdjt2+MMPnz1+fEakmRFJrlbmu9/7YDCo3n33wdXVDJH4prGPJIWQkSNzBGAk5AhI0rTrg8981SEJKdFZJXDn+Pj0B/8i9HX+mZ8HpWWe+qZ1m5nta5mX/cUzCi4djEEmzBi9RyKOCADbOOZ7wxxkohkwBg8xQIywNUIJAdgjc/SWhJBSIcTgDCFE76K3MTglNQqBwNx3odmohJKiIKCubYrxwc79tygpYgzACCQgcIyerRUoZJIQwurkUeh7RoEoXNcwgtSFt73v1lIliByc3T2+V1S5N2Y03U8lfu87f0RCbKPri41jgBAgOOAoRDoA3k6yjRDD9rfiECAY9gaDg+i27qyfCrM//fbTHC1eDOi7LmCI62z5RVjeahlvZiIgEjBwCOwtBEck1HAihHJ9L9PMb1aD4zsQOS2qaNvRdDef7oFInCyklBA8e59qtVnMI3PddIJtsXtkRcqry6IsWCZCazbt1aMPiuEYdMqD3dVqY1y4ePhec3ESSZum7paXCHQ9T8g5222kzkSS2nbVzc+FVgjUzS84OBRy6wgi8BNTEEK4frR95voyhTGEyJFD8MZY74yx1nkm9G3brxZ93/sIsVkxIoYQZYIkhlmSoVfgRQyppGGhFdtqNNoZ5NF3eYLLi0ut86/8wi/JJAVM7hwdzS+etr0hIpkmIMzx3QPi02K0m0zeuPzgB//l/+ZvPjo5b4UyjqVOUIrOWCKhKXHrjaL57hGFrn70h++7egWeVZVyqWrbtau2X2z6db8532TjzHWm77tuXTMRcGTXAbPW6lo1vc2fkELgpl5//Ruf/frPvfrjHz+QQsTIN3VGvOnkb/UnyMxap+CNSapXv/QNW29c3Qyne7w+/+APf3fnS7+BRaGLAnWCxJtnD1AlQKI/e4zRgdIoBMmUr68CyJEBYWtNvDVPJ6JoDXAA8CrJgcH3LREKKZROtjMNpBDE7GwbnUXmrbwWIbKz0TaEUWalkDqGOL39+vj4lQCksqJdzbvVUspEJSl7p5RmQQDR1ZvN6TPSWmZVcJ5jRMIYApIIrqUIMfisHFajcbe8evdP/yQ6d+fO8UcffLBZzBBga80BHLc6JIgROCBEgapk5usK93bwZAgcLESPHK452X9+jP2Ulu4lDL80NhevVfjMNxZQnwRmugnAiMDbifQEDEqhUsH0iAI4CiJVDI5efV0rRVJkg/HBrbvO+z4K8O3V+WXT9FKiTNIQuO26velOOpq6yFogESSDCZFYXl60mxqEEOVoNlu080uZVV1d+77tV4sY4urkIQkRvLGbpVAJcESk6K1ZXdl6DRyjNa5vgANJjTe3a7SKa+7K9ia2/j43AL7WuDHHGLfDvn0MzvrobPQx6JyzQfTOqUwEo3UiosvZlon2ZpUIGFUFAuRKFkmRlLsUWtescjKXF493dvfH072+r6ejke3Onj89bXo/Obq9d/tOImVozia3v5btfPZP/87/5dF3vruSVR2htYwg0izXOmGOVVWqoRzerahfzB4+j0652iWVGtwaM8HFgwterSXJiw8vmJkEus751oa+i21DHCF65pgkaWSIIW5puhwjEglZPH08+/CjZ0JK2NZmP3HtfGlYzE3xcjQazs9PN8sNdaZbXK0fv//x93/v6Ku/nkz3Tdts2zndxVk/eyYHE/a+P38stUIpg3OMkpSKzBwZr2fkKRAahQimC84ppb1pEVHoJAa3tZhCEIQChSIhIAQS5PvGtjUCYcQYA3Ck6JmD0FoKGZEGu4ciKWYnj6N1fb1p5+e6rNKiQog6z0NwzlqzWljTem9j8DItgw+olO+6rUTdtWvEmOaFUGoyGdtus7y8nEwnzJFDfPLeO1KpGB0wgGuvswMACB0EL1Bdj+XjGJkDcuAYIfpt7GWON1q8l0HJPwOynyI3v+RKgZ8MF7iZHH+DZb6Z3EXAW2XPlr8VmaPQqSgq9iEZ7+/c/4JK9GhnmhDjYJpXI0YBgtrlQkTXbWpnzM6tY42RvB1NBhB8U2+kbZr1ykdWu3c8yMXzB/XVWfSshtOuqUPX2L7fWl1LndpmbeqVkMqbdqtiCNYGayBG1zaua9h5hsgxAkcUcovGT1CLuB3acDPZaBtpUV4T0xERtk0JQCQkQsboMXq+Dk/AwYHpBIckETmxsHXseqlAKTWuEvA2T9NUKQzA7Hd3JpvFpm/Opzvy4ftvr+sGozh/8vHDBx84y+eXy7uf+znOjnarpJ99NLr/K/lo9/JHf/vRexenNQepW4cX89V//L/4X642648ePrJ9v/PGXX10B3gQu4CTveF4KJ1p+o5YHmbD5x88mZ3NmCn62C9MO+9c74LzHEMMfltpdM5vv1rIKEhseThSJQCx7+rg+xD8i0FQRBJgqxj7ZPkUgk906prV/OMfNZfPyNeb9Vwdvja9fT9E33W9znOzXtvzp6SQk4ydtVenKhtQUjDKiBB9eDHbVYjrsa6qqKROtxMGlNIxRKGSCEEqRUJvE3skZO+iM8wgk9zaPgRHSpIU17IWIQUAR1ZpDjKv69qbHrcXgGKYFkX0Jh+MQQrTd9C3Xb3kyNEa8AGE2nYcvDNJVgbTBFMLonw4UlJDdH3XLs/P7n/mzdnsajoZv/P9P5FScvTgG44W2CEwQGT2ACBvpgBt+cOeIWxn9/BNS/ZlyTz/9yrdGeKng62Hl9o8/KIxu502wNv5twTIzHw9uJ49x8jXz4YYXFwv893buihLFdX0bjGeZAp7IO9tQmgi53u3uvMn9bJWadHPL/O82MwvhjvTYZ5erpaXXUvZqNq/KwTNHn3g2xVGbJtNf/qMba/ygcxLjpt2dq7zHLVOy4Gtl66ttwOvt7MegjPsAm+DaKQb5hZ+MoXlBR8Er4X+W5Qy3py/G73EtZ4GkYG3xpPAEYJHQOZAwXGIBJ6ApNbe+0w58lxUZSIxBjdQnZZiXBSZAh/88SuvXT22RDJNVhePvnv+UHWdIIx5pV7Z+VxM9h2nnKdRybB+xPZ1y41QnEZ/cr48u2rLvPqT7333+fNnWZaWedGc1aLod159c/P4JNtLzXK+Olt1fS/0qqbktdePd/fG/+Sffp89MgDHGEME4L29fSnl2dkpXkdOFkIxRETc25nM5htnG0GIGG6YdNt+HiHErYCagZAIwW8JlbUDlQ88b9rOxS7me7e0Tqpx5WcLdp6Dd5sNdyufaorAMaBUrPJICUqJKDhsYw8DsjctBYNJAVlGOk2Vis74rpMCXb2Q1QgISWiVyhg9QAjWXY/AIZEOpn29ZAjAKKQiKYMzznqRya63TX8GHIlEF72GoGK6XJ7HyMlwEm309apdz2LgRKdBKO+j1AUg2nZdjPd0ki7np9EbEITMKtEoZPDBWquTrO/avdFoNJluFmcceo7uppjr4SYvkRAjxBs8UoTIHBk4QMSf8LmAPw+0P3NowCeRmq8HsdysfpkZP1nQBv5kwRNYULJzKNMyHY5Du2o3/1/e/ixG0ny7D8TOOf/lW2PNyD2z9uqu6r373su78HIbaiEpkZIoUaYHtqGBZ2DADzYwtmHAbwP7zWPAfvWDjTEMzBgeW5YsemyBmy4pkXdV39t7de1VuWdkrN/6X44fvojMrOq+l5SGUnaiKjszIuOLqDj/s/2WOXlBaVfEg6TTK0ZHJ8dnadcqz5lXQsio06E6zw6HQsrR8YF0ZmX3agdodHzoq2x0tO9rMz85cdY6Y7yrwPtycgwI1Xymwsh7VwxPSEpnK19Xy/ADYAJCRHHRgyMi0ktaWZccyuDSfutiDrdItovOt8m9fFF1IAEAOgsIggmRmU0UyjTUUM9jLkQNKTohw5ZGMDUJ0kShFHduvvVs70naa61ubhqHMhTsJbO2IiyMPs2YSSiyxfShZ0s1hkLkPrtx+/VX3gl/8P0P/uj3f1+E4ebmlhDy8GCfHR98+KGdjTbNbO/R43xSb29sAvDh8XEYSJJBEIREAsDleS0EOed+/ud//vT0dH9/j0gyeyJChH5v5Wx0dvPGxv/6P/tH/8v/1f9xdDYWgrwHZtZaD1Y6h0dDxw4YCISQCpRkA+yMitOkN5gdPceozyRc5UxRdtc22u1OMc+IoDgbcj6xdo7BFWQGQBHGAIhCiygFRCLlvUOwgsjNzlydczH38ixIuiKOVNiSYZifHhICMkgVeu9RacnKVAUzkA6Z2ZlSoNJxWpczAiIdAgpfFCAEIviqAFIkhXMGJRazUcleJx1BVIyHiKKaT9kxogSpddKpyyO/9L9tDTbK8ZCUFCDR+zCMizwrZ5Okk8pA58W83V05fvpIwtSZKf4U/RdBImzGd41DNrBj75H9OT+9IRbwF5XO/3Ifl0juzYM0SlNNjr08oFr6XxI1BmcijFXa0Um7mk0QKV7bRiHbnR4Lid5GSevs+Hg2HoYCrly90l3pT6eztN2bng3bg9VEYtxuR63ubDKZnJ1mRwfZZGyKwntv6wK989YAoqtKV1fOGJNndTY1ZebKnJd7muapIyKgwMbkTECDkjk37KRlhbwUp6Uvfodp+f8N1Yoa6zNqXgJCsSyymdgTe/ZOCQ4DBZ7brUhL4NJEBO1AoAoGEZl5wY7agQNfSwGDbj9KO4FWQrZAxrVPmGVlgb2vTL29Ek7uPyzK6eYrr9//4LvDe2fTSfY3/9F//D/4H/32f/l/+Sedbs/Udjadl2UZSErQ395c884fPj+OgyhNoqIsrOdWux1F6bNnB3k++5/9p//ht7/15p//+ScNXOGTTz4+PDzY2bkymcxwoVkN1hrv/PPnp9/7/qf/m//sH338yZPRaCaFQMROO/md3/mVH//kkXMOQDJJDBMAclUJqFeu3y1Gxw4UE7GzzlsplQQMQt3vddnbTrtTnjwuqkK2V7xzzK5BJqr2itARikAEMUmlWx2UATOC0iDAFYWvahloElJELSRl8wyVQqlICCQJ3rO3TNJbJ6REQO89kiCh2AMK1cjHERGiXFSM7EASO0cIqDV4jwCd1W1jjckzpWMgASyljorRsQ4ToaIgSYF9ORu1en0oMmeq/s516+zp86etXhcZwPtbb771nf/mH588v48/Pd4EUXCJZNdoyV4GPfClOcG/zcfCvGvhLySXjAFqHmAhibdEdwAwCgICkiLorKooCdr9qL/hvVVhsnbrTpkXnE9Scp6dL2ad/iBY3cGodfz8iTdWxuErd19jhoOToRfR0/v3RkcHdeVAhTJKbJmBsd5WdTkXQhej03JyYvKprQpXFd4aajqhRr+vkYBsINNIi6K2oYaf84eXkfly0NJF9F7+PgkhG8PCZqS8DNrLw6vmeBPCa0KBAtFLAUWNpsqjUGhJ3kAsoZNEgmeEECofioIQPIOH2lSoqWT0guraEDuf9Ab+0Z4sJ6uvvXX/808fffBQO/3P/sV3/8//xT+bzfPxZJKm6WBtdTadjifT3/47f+dv/52/+09/7/fStPW3fuNvVXX16MnTb3zjte3tzYODk14v/Z2//yv/1f/t9//4j38chEEQ6sZWYm1t/c6duw8f3icSzCylBEBrLSLMZtPHT44mkzzPC2bstDvT6ey73/vIgyYhgTSiEkp779nm0cp23G6N9x8iELITQgER5GMyWWXh5PnefDziymbD5769gjrwtgZAcAa8jwbr3nmhFXtGEiKIgBq9nIBQCR2YumDHIkyQSIYpAopAM3hXl1Iqa2tXW6E1gHdF6Zt1ixIAyM4tXBydAWZAxd4ye0ZewKSEBGabzxFo/cbdqL1azmd1OZU6JBXZKq+ziQjCtLfqTFnOTr21G1eukTXz8bC3ub1z41Vnqmw+7nb7pwf7t19/3YG4c+eNh/c+ZzZfHrSAkpkBHIBffr40B/63D9rFlnrxOwjgst/l0mfgfH4FHtgjERBSGCeru/HKOkmdrO4m7V63152PzyQBCVU4oaJkY+dK2O6OsyI/PiizTLoilgQI4+ksL8zZcJiNzrLTo2T9GgVhY2lbZ+O6yOrJcHb03MzHzlTcbMCaDdRSJmBpZ0/nHgcoFrZDl6LrC0FL8jxcLz6QRGOqRCRIno+uFrKxy9S0+CY35p8sCbVARHSmCKhOQhyE3A0l1zYr63ZEyLUA1Q3QOo/oKw8WWJBHj5EUzL6ohHMCnOumYXF6ymf73Ve/enDw5OSTR5MZVO3Bo2f7K6urYRg93T901s6L8qtfee9X//pf+9//5//bSVZIKT/48ANCTJL2rdtXvKt/+KOPqtp2u91nz0ezbF7Xufe8srJSluV4PHr48MG5HYwQQmtd1zUiKqUODk68p4VZVG2UllKlHkKSAQJygxYA8M71rt42s+Nicgqe2NbIoImlkrq3A0kYpYmbzo+fPgby2F5BBG8qYF+fHkabV6XW1nokJB2oMEJCV5dCKiApVOilEEoDMwtBDMgeZYDIrspBSGAPjoHJO8fOo0D2DprG2Dtu6jJgYOedJRLsjK9r34Dwkdg5V5VEZMoy6a31Nq6d7T02dcnWSRXWs5EtZ1F7oJNWOTkF55JOb/PqNSKYDQ9JiGKevfLGO7WpBInDJ4/WtnZXB4NWFAuUB08ffKkMm0AS4M91D/2lrowvA53+KoIWz1nvC/ItLYtjhIW0Ki78haKVTRWnOk5VlMRp3GolcRToKLXW1R6DQG1dv7G1s/vk83uqmvfScDydD2Jx49U7uYGzae4ZXV2RDk1Rhe1unWfInJ3smyKvZ2flZOhNDojNJgmYlo3qhZR7I31AC+QlISE2rP2FvtXLQdvIRaNYptXljxb3IEIStLzLohFAXmI1YTHCWojTApFXgpnBGguIEbExZiWhgGzta+eMFCKQrgKrUUQkg5B9RWxJSqgMSecsYGWaPiL21pZPHkXaDY/PPvv8wBv6bJJPs7KszO6Vq2trg4ePn0ZhJAjjNH3+fL+saudcksTdbu/o5Oj99++dnRWtdodI/+SD+94bAOe9b7hi1LxQpJeaB8zMdV2HYWhMjYhpmnjvm+mOdQ4RHQcoYkDhnQFfe1+x90LFnZ0b0/37ti4RGdB5Wybdjh5cs0hJtx9JeX2tl2WzLBvLVttb462FupZRrNs9YIFSI6GQyhtjTYkkwHkGz+wQkVRAQvqqsmVGACLQhFLogAJdZxmwF1oQKW8sIgmJ3tSmzJAZJbD33lpgB94RSWcNsF/Q7pmRGZG5tt4YIBkNtqenB0KG1tTsXUN/725dr+dntpgm3UF3c0vpAMCX82k1Hw+fPWIQ2zdvFdPZ7Gw0n43fee+d8fBgvd/9+MMP2VVfFrQLBYnLYyR8URiV/61r4y8L2sWaB8/VorEpshhRkA5QaZm2RZgIrbbe/TYgKh3IuI1hCiokkhvXrosgQqFtmdt81k7iw+NjNlVvZWXs5eH+fplnVZ6bolRxSyeJrQokcqYaP/20mo2r6ZBthSQX1tdLtn0TeEsBrcb5CxEJUCBSo7PxYh0LLxXGy63PC5ug8+FTk2wXZKcFW5gXLcK5Wy/DEt7tCZwkSCPZX+kAK2QUgNZZQZxq0QoFk1PgBAqlIK+wNgqRitpbiwjgrEMPjsA60GFc7D2K82xWl8O6PjktHo3z3LjxdNZqt9c3t4qyfPudt8uyPBkOJ7O5ULK0Ji+r49OhY+oN1lcG64zCM6swCAJdlcXG5sYrr7wymYyjKJrP5957IiGl1Dqo65IZwiD4tV//tf39vSzPkjjN85xEkKSduq4YtNTdhWWWq9AbZojaq/HqxnTvvneWCKhxmop7pKIwSVbX14/u/eTg0f3eYDOfThwBBUmzqgwHW4jaWQ7a3QZq4KoC2AslARwKYnYotAwiDygEgVIoFdclSYkqhmYSXuQLA2sA7zwqjQRE0puKwRMQMLP37BmI2DoQCNT0cYtFR9P+udpEnVVUypvSFBMUwlmTrKwrQfODz5GUThNna+dq9r6cjOpsBuDLItu8ftsaY8r82cPPgkDeufNqoNSPf/iv63L+xegTC9tneMl1Fv+tA/WLQXvuIXCpPF6AkZdicIyEqLQII5IBChGvbvZ2XzX5DGwt45YAHwowVdFd37qyuTYZT01ZxJpiLUBFJen1le7MOEA1PDpyjKPHnyMRCpGdHJp8avLJ/OhZOTrzpmRvllOwJeqDFm3qefzCIrYIUAKgAFouE5EWhpwM4iKILyTRCMVCGG05o7qok5cpuHngRSXcTNCbwRczMzSqCcjAKAUSgHeuyEvyEIpaK+5GMlEgiAXqkDANnSC0JjAGPAXSA3pLiIrAIUqJxnrRWtn77NN2kZ06391J89J99nzKOkjj5OHDxx89eLC5utpbGXzw0SdHJ0MiGo5GDORYDDZ3OiubRNoYz4zWc1mbRkrv9TfeuHX71r1790aj0be//W1reTabEuFv/MavO+fPzk48Q11X6+tbq4PBcHiGSGGQAqPjmiBADFB4JdDVGbJjANVeDfqr2f6DJdwTSKjOYNOT2rz5aqfTNqdPw6SV1RzJaLj/VKeJz+colYxSII3AQmsEsmXprVFRgkTsPQnp6oqIwHtmjyiQFKoAEG2ZoZSevVSh887XtTVVA9hDEt47FcXI4OragyNJ7Bm8R6IGVcjeoxDsPRvLHprNu7M+7g2CpGWr2jvL3uoobfdXx48/AVupOPULkK5zpmRT2SrzzlRl3t/cIZKuyo73nj3be342HL35xpuC+f5nPybCl/BN50F7Af1FBIS/mo/FJvY8XM9FnxbjLV5KoTOiQBU0r0Xvxp1084bNZ+VkBK6UJi/ns7TX987V8/F4OteSQoLjp09meZGXdZHl08q6PLO2no9G472nKgji3loxOkUBbKrJ03u2yAA8e+tMiQuCUZMsxSL3LTKnRJRIRCjPl68E4nzVsxSv4sYaZjGgokUviw3aZfG9RUgLIlxaMDTIi4sWZEGn8AyNtYNvApeZPRMAVKXxtlAA1hpmJyUAe2tRESGJVJOSCB6QKdbCe0/EJNGCrw0AE7IoKx/1emfzfLZ3kI3H0A8zwz/65LDyMJ/n3/z2z2+srj59vnc6HN+4ufXf++//9e9/75Oqrq0RK9vX41Y7DgKt1XQ6aSrMurZrq+uDtY2T09P7Dx68/tY7/cFge3OzruvDowNE7PX6BwcHdV1JqU5ODl977fUgCB89euisLcosCINOJ52OxjrQ3pfka2dLACZA1R7Eg43Jk086aXht92baansU0NoQSqcbV8f7jx7/6E9Rhd3uxujwMStdHD2tJ8Nk9yaqABkQiIREJFeVKoplFHvrSAhbGaGkd97WpTcWiZjZmxoFyShegLe8IyFRBoTC1wVJQgCflx4BpSRAW5XInhC9tbhwqfPQYBytRUASgoRAlOBsELej7sDUlasrKYPO6mZ2/Kgen1AcOWJTlTqMqnyWtrqtbn90sMfsnHVR0gmTFIydTIZBED55+iwrit/9h//gD/5//9zU5UsK4y8FLfyVJNiXMFIvKC0vt0C8cK9dvIPZMQoZrGzpKEYZsDWmGCMiW1dlU9XqzucZAXfXtmSS+tkY87P2yiBN2lGrMzw6srWdDU9NbYvhYTGbxN1BOZ/5KitOD6b7T0gqoQNbZDafNdPZCyXZJqkuJtgIKAAFMCAQctN1EiF6vMBRLKppAr5UHjfD4MtH3nK2tNS+W0jw+MXgEeAiTmFBsGL2nhs/ZM/A1nlkEARppARyHECg/Lz0CK4fwzhzSmCkMSalhGNpjbNlDaEWCGg9IUoh2Fp0IGWr9f73f7CBvvb4vLB7J0VemjCMqroejkbD8cg4224nDx8c7D8/kSpYufHW6rW789ODfHKWzbOyLH77H/zis6cjY/E3/+5v1WX99PETrfVXv/4tKYJ/+o//67KuqyL/1V/966cnx48e3dc6CrS21j98eO/J0+etVisIg//df/6/+Ie/8/d+7/f+YOfKppYwGp3YugDwTVsgglayfTvqbyEpCEKnI063vGqjr3o7V8JW5/T54zjtRVH87OEH0WDDzMfdO++p1opUsWdAIRpLS3aOtI56PbbMzolAg2NmZmOYHaEgJRuZGKFj9s6ZisG7siAiAA8enDFszKLgWtZgtmERNJNkgeCBSJCUJCU2+qGEBEwedKsVRq241XW2aq+slcOD6d4jHUWgQw8gdKCAXJX31rda/bWTR/e8b4pt2Rms27pkhKLIB+vrxtbvvvfG6HT47NE9IrqMJv5i0P4VRuxCPZXh0mRrGQqAl6MagAQISUEU9QZ1NkUhidFVebK2Yx2rKE77q3Gr621V1yY7OylqF/YGhcOqqpC5qisCzqcT9t67us4LV87rfDI/OvC2SlY36mxiZxNudCCXmxU8Nzug8zTatAkNb4GarQ8TX5xBi4J4MUhqvkOLA4AQLwbCC2npBbeqkQpjQMfsvW9g7czOs28+2Xm/ANOzZ++ZmW1DBBXMQMyenfUgPErBgMYzeC9jQQScW2c8OpACvLEeiTQBM9cOAiXKvF7f2Xny8NEVqHuof3I4fXQ6IyGF1vuHJ/OiTFttFbaHJ4XzKkraYbT25l/7TUtitv/A1lm722HPRWHywjHS8+d7Z6NpVVVS6e/9+ffuvvHmr/3Wbz+8/1BKvbe/P5lOvAdrXW0MokiSzkqva0yldfCVr7z1e7/3z95//+Pf/nt/99NPP5pPJ7gA2wAAAQW926+vvPLO9mtfq1XLBC3ZGQRhUM2G7X6vd+2VeO16t7v66P3vBJ0eA+juqh5sIhAKJYW0dYUM1liplLfO1ZWtKyLixmTdsQi0kCEKYu8BUYVtJGGKTEgNnk02bTzdGRCss6YiYPbWVVUzcwJAb+qGfIMkgPRiLcQL+gyhlACCQQjV7q96U9tsoqUfPf0sTFpWSiaSWhMSVHWr23YeB1u7o/1npi4ECcfc6q5m+by/Mth7/gwQ13d2i7qMdfzJj3+w9G3/dx+0l30HXiD9XHbfaja0hKjDYGVTR2lxukdCIKAzldBB1OlLpfprqyCDJGmXxbyYzcJWL263q6wAV20N+nlR5UWVjc9MmVlr8tPDYngIhPVsAt6ppFWOTur5GNjDYjm6DKpmfnvezp5L5DAw03J6di5htewd6EKGsrkrLfI0XkyxztWEl6rwC7FKbrzdEDyBW9bDi4BuuFbsvTvHinkPzjnPUFtfW2+dy41taRFpJBAEMlEikoKBFSpCwQRaETFoBMs8scxM1rKOW0HaGT17uNptl7PiyMC4smfj6de+9farr7/S67z3t/72f5S0Vzq9GyvX3qNOx0ldZvPJ4SNTFr/4H3zFWfOjH96bTLMFB0DFOmzNZ4XUwXw2/96/+ldhFP7qr//GZ589YBat7iBQoXfCizDurVkVFmU+HZ38/h/86de/+SvTyewP//APjHVKaWfscqwg2fv2ldtRf+BMRc6Z2gRpCgKqbDY/OUok2Szf+/Bf5pOTdPtGVRXJzm1AECJEErauvam99+ycs5WQ2tkanHV1besKmlfWWhJIQgISItsqc1XO1npnvbMiDBHZFHkTfUjCN6WRqxuVYxQE0LB+kJGRGh1Lj56BUAhJSMIZdqbV669tb+59/L1qcjA/egqMlKRIwjOHYUzOJq1WXeQ1c5i26yLPxqcoBINIur2To6PV3atlWeRlqdvdIG0z4v6jp6bKGqGfi+kxvrjb+XcbtAvqFi+V3BARMYhIBjKITD515Sxe3bR1qeK0tXVDKi2U9uVckKis96QCLerpMNa6KLLR/vOHT56eHJ/W8+n8ZD8/3c+P9201a2b3ti5ICl9XppwjAoKApZ/1BacBLyrkZb+KeKGxgQvFZrjc1dKScIcv3P78yV5Wfj73F2ygZY3vYGPNvYxY7xdfXFit8AKF5oHZs7VeIGsiYMwNzwtEBi0p1BBoJJBIKMATY21BoAgRSgbjMdZgwY9qOJ67V+6+8ZOP3q+M0QIKGRxNsqKq41YYhIOAtn/5F/9+HKw+2X8UtwbQbU/y8fjg+cZKBN48enR0fDReW1//23/nW+PxPMsMCjHPiyCKtNZ1XRLB6Ozk+HjYX91i0FLHEa7qYF2ubq3deRPBGlvbMgu1/vjjT6y1xpjlcsgvqAKE5L3srKdbV6WkuqgdIxIV4zE7V4+On37/D04f/NhWVXrltXJyGg82RdohkiQCzwzekSBvLQnhqpIEAjM7b8qiOWHZOXDOOcvOInlXl+CNN5W3toGMEglXV4jgnW1sbIXSKIQ3lWRw1iACCfK1XTrFNQBXRCFJKyRAb72rgbi7tjU6eDI9fNZ0fl4GlgAQO/01ZFBSsbN5npFQpIIoDKfH+8xeREkQxKOT46g/UEFY5rm1prO2Meivnew/n0/m4OpzGVRBl4L2380HX0bmXgra8zghFBKQXT7TrW7QGSAA6VAnHUCp0w4JffLw0/npsZNRf31beDM82D/cO5jN58PjE+u8K7NseGDLrDw78nUOiOx9M3DyVeVMgbh0FyEGQGICooU08wJIfL4wxQvgJS5kLKHR11yEIl0y9+MLKhOfk1Uujd4RF22rP4/J5r26eMc2P4CFlUJjtbq46RKG3VTW2OyHauu9I0HCeawsRkp4wEnBjFAbLJwnxMoxCjIemUkydBRoAYcz00rbnVT/4EcfdpRS1ug0LT199MnDg/2SJHZWVuJW8mjvcdRZV/0BBjA/fPbO62sHz/dHZ1kYRvNZefOV3bKsDg/HJMXa2hYQVVVOAHGSrqxtGsdCRkxKpwm0VmRnM97cthJdNs5P9+r5yFrLzksp67q21jjXsD4ZkUgoYKnTTm9z03t03tbzeXZ6bMpCCFRRmvRWk86q6m3X+UQqrVe32RkAIqUJwNvaVaUzpXd10Gp7W5v51JuawSOzMzV4671tWtlGUKkxrAD2pDV7x+x8cz3eoRTAzM4hgmx0kgFcXSEBoXC2XtBFrPXeCa1VFDtTu3IGzhKhM246OhVaB62uDFNPwgMqoRSJKI6d97ay1lbWOYd+9dqN6emRqwsRtUAF+Xye9Aa1MR4MOW71B4N+v5pPD5490iryzjT5ttnTwtI09t9R0OIXZlGXAPZCoQpk1JKttq1ynba9Z2CvkrQcndTziTUVkgAZqjAUYTw8PKwrQzqY7D0hYG+q7GSvno9sNmdbI0lE8LVpbCPAu2bhChdF62JmtAxAupQtL02RLsZJS8gWnt/ynEtxAW9a6E5eKEk23mFNaXYegrzkY1wQqS5KaFjeZ/nFxeCLF7dGEh7QIwrEbqANQyBkJKQmQqBAEpNs5mkxskQGIMc0dz6V4mg4f+3ttx7eu0dF3lbgiNL1lZ/7hXe/+vXXfvKTvbOzcW9l05buFJ1TaqUdHz9+8ODjB9ks857r2iKKH/3ws8kkW1ldnc9mvX5fEhjjSOqysnG7U9UWgbPpEFUSrQ9M4IKQoBqb6VF2dgjOCBLO2bquut2ec85797u/+7sHB0d5npGKHITdTpKkajqfz46e5cd7rpi6urBl6arK5PPKlK7OFYlgfdcDCxmpKBUq8NZV05EtciSUUjKwUqrOZowOmeu84LpwdcneNt0pSYlIJMQ5mcPbulE/ZGtMWZAUUgcIwM4IgUog1zmid8YQCebzk9uTUCpNpQ5cObNVQYKA2dQ1SUUy9CRRSutc2u5JlL7OnbFCBaAD42prLRP117fjMDw7PZKknOeyyNuDVe9dMZ3IIGp3+wQcafn4k4+kCtg5ZwsAELzoMv/dfdAXFC0ue/kAkCKtZdwSOgLv6tmpq0pXFzJMbF2EaVfo0NW1q4xQKmgPgLSr89nRns2npsir+cQWc2TPtvbWgPfsbNMhNt57F1zW80x44dkH54hfPPelx+WFMSD65m4MHjw0M6pzQl5DXXyhskU+X7zCUgiPAcAzkAX0C9oj86Jy9ufxyOdiQMzQkMu4ofmxB3YM4DwzMCIIgkES9CIVKckeE03ssR0ITVRZZoBBIDxDySiI5h48CiFkXpmK1bXbr3zvR9/XUfhgf/gLv/VLQOInHz4g8LbKqnq0stabTwodD2w9v72Z7V7dOB5WdV179q1O2monnW5fCGlNbU3+3lffGQ5HZT5jV0yHR2wsefPu22+asau9qIzVzgpN0yf3s+GhUvra1at/46+9V1VmeDZtio2qqsbjGWIodQoy2FzvilYbhTRFzrYKNRWzzFsjJKpu15cZOQ77G15K0lrqVAShd7Y4O3FVQVoLGZCWzUweGUlpW9fNxIRIABJ7760BZgRwpvSmBmZvayEVIAI7BPTOIjIJ4Uzh68IDk3dSSPaMznhnUSpmT+iREGVIQah0BIzsodk7oQxRBqRDkMoaq3UQx6lg7+vcOiejltAhI1hnhNStOE3a3TzL67oCcOV8HCZpmrTHZ6ciCJN2F8G3kqSYTkdnJ76cNMR98eUaMX+1QYuXgVbN5MkDLOTd0KMINJIAFAhOdXoqStiapvzwzlfzs2R122QZIFnnTTazeQbe2zIz+cwVU1/X4D0DgzHL9/4lAaplBAKc2xwQXKxnz4N2MUS+CNqlFBhceGAvTFAauv7yd16q/5EBPfvlItb7c8np8+tqgnIRrefJdmlouJwSunPQxTlQqhk9C8JIiU6grGdE2kylQpQCE7XAY0khBAIDTg3nxkcSCismFVoZzMaja7euD+f1g/v3ONB/+Pvf+8533j88HF67uVq72YPH9979xs8J16rH7vrG6n/8P3zrn/yTPz4ZFkorZyqBWFU1e0BwdVV5a06PTqwD65z3RaR1HIeCIay71pdjO0X22fSs277qZ2fTsz1gDgL6rd/89r/6s4/OzsZNMTMcDmvD7dZ6FPXCNOxurtjuLnjTrkYtDfPctnr9/sa6QfLAUJVB0oMoZPAkAlIBMlXToatLRNRJKqMYGNgYWxZI6K2jpn5WgU67utVm9q623tXeukXj4WxTE7mqdLVdLOmct2Xui5zAM9ECq0dSIC9kuhmYLREBEJJAQUJrInSmQiaUCoQAIlJaS0XstZJmlpXlHIRgIY0xzlQArKI0afWmo/HKxvbo+ICiyBS5CtPWYH06PAbAqNXupimCj9vpkwcPOBt5b//9BC2+AGC8UKtYMvI8o5BBu+vYklKdnZv5yYFM2iAEAMggElJX04ktcyQqTg6K4VE5Hbm6KEfHrpg1kx5vKjYGLgLpXBwD4VJdjEQIoqEEIMILajjLPxsq+9LqoKmLFzpGgAALErwDZGBaNGVIl0Q9fMP9AIKLIVSj4s8XYbwYWPnFWcAvrckYlstcXCby80tlRNhMdStSpYOtVKwmSgtINTEQM2oJgUBmsAihRGBROwTgqYEgCObDk1/8xtc+/PgTa+ter1U4H7ZXH+2N7Qnd3f3qv/7oh+vbN4L2lloZfPfPn58dTBnrPM/ardQ79+bb725srX364QfAPomTurZVbQHAOfPGW++S9D73Zup1jGFvtfTVYLX3j37jV9//7p8Pzw68t7Np9gd/8H3vhbO2OY+IdBj3WslAB51uB+XmNa8TlIKnp2dnxWwyX9lYtyhKU5uzEyU0RDFIBC/T9R1AKCfDOpuxdYSkWx32tulGvKlIKSIiqYRWJNBb64vClEUzqQYkQoUkAAhILPdy3pmKGcB7ZE/skR2yA2B2dinXCMwMUrH3Ami5PvVKh0DKO+udEUKgUiCIgSWiRtRBPBmdoJbGOWetqZsKPArSFsigKrK0v1KXWTYaiiQRSrd7K7PjgyCMVBwlWg33n62ubzz+7FM3P/v3lmnxZXYtXqCjEABJodK2yAAcSqpmI5NPkBQpDc4JHXhrTZHppKuitJ5PnKmkDsxs7PKZMzWRAGY2ZtmKLsUjLpsEMZ8DFxmajhYX/t8L8abz1LqoVBf29cyLMv5cfW5Z/zbSC0u96MuLGwR23PCl0DMz+mZytSzZeYF6ak4GPpfbuzSkavpY30yrmtC+eBoQK7Gaai3paldnxoUCGahyjAhKkCRyAAAcE2sSEwOBkJl1nZBZBY/O6trbO2+9+fvf+dMoEBD3V7/1a1du/NJr9LVUdDHivaNnmzuvmSjKx3v9Xj/LZtZWcZI4U5PAuqriOF4ZrFpnsvmsMu7a1Z3/8Hf+zh/9wZ9MxiemqPvpjo/7vf4GdfqVt/uf3Xv66JNwXbc3Wvkw++Y33ozj+OjohEiQCIIglTICkgaytZtXKNCePXocz8vZeHr77h3DPK1Km2VgHEYxxQEzICkAqOdTbrhy1skwIiVtkSEyeyt1QDpga2w1d3Vp5tM6nzjrUCihFEktVIAyJBmQUCCUkEqoQMiAZIwA4B16T2gQHLJDZxvpcMdEJIgYBAEgmEop5Rm8c1rGMogZvTMFIgMJrSNi9mWZtlrZZAyEKJSrDbP13nhrhJDOuyLLEChI0zKf5+OhEBKJolanKIqku+Ksi+Lw+NmTJEnPDvdmJ/vsLQD++wxavCSnesH4Iyka3Q12hiR5a1WrjwJ10kYlgUhICUzN0K8cnZhs4uvKzM68qQE8OMfWLXLVBf6KLgpiOJeHuEy7b/oeXHphw8LVGr/AH0YE8OelMTYlfQN2uGylfV7i8gVEcRF8fLFCWpa7S4dQ/nJFvMUva6wJmxUDI2JDDIQ0CtJARVqGAl2zkCLQUgpEKTHQaBkaokPBAgEmlS3YRkiGbRLSo+PR+s72a6+88i//5E/TrWvdt74OQ4Gmf998HMkwtOl4djg5fjw9G3306XeFwq/92m9VUe/w4acHTx/WlVnb3Lz75hv373/qPGgdzqbje/fvzSbTTjdl7wmDgbrhXJiJIjt5svfoAxb1+utrrbXW8MnZu1+9nXN1ejJjD1HY3lp9ZaWzezI/Wbu+uX71qgdRT8bTw+eTs8nb3/wFEcUno9OqqjkvdBhRHDCzqznsdJ137CwJLVSk4gTBuaoQQYiAUoYopMnn9Xxui4odoNA67qiko+OOitoySISKSSoSAkiSUEQKAIkkkpRa6zBFAvCe2An2jaqQB0/O+cZ5CgWScFXJzggZOGslEikFQroqQ2dJBoSE3hCir8s8n0MYSB0765wz1KBAvGXvfV1WRRYnLU8IQpj5TEWpCGNnXRjHRZ51+32uSh0lYO3J0/vsaqmSf29BSy8RBpaJi0EIEUXsnAgC0qEME1+XrsjYewBvsqnJZjrtizCeP39opmcA3pW5NzV4RvaA/kvmaESwAEhedKeXZOcaYeJzOBYvtq/4AkbrBYd7XubuRstqEaUOcClkubwxL1E+3EC/PF4UwOeav5fGwnAhVHk+3ILLHsKIDMBSyIU1tyAgUbMAxFhjqsRWSwGDIKyYhICIOJYYk5cCjPcS+KxyEREJEOgJ6oLFB48PvvLOO7evXfkX3/kz0C2K4hqCWT5vBWucz9srK95aU1QrO739k2cypN2t9PnQAPtIiYO9Z/sPTjtyy7Mr7Nxb0D4KYukrfO/VXwjrbhoN+snm6fGPi9NHUVe3B23d0yrVhOKjzx4bxSqQQqmIev321igbBv3g7ut3lNLZZHQ6ms0n06//4q8k3e79+58XVeXmOTofdmNT1QwCkYQMEEnqiBl00pJh4E2FSIjCG1OXWTWb2NIgKRXGKm5HnXUVd0WYktDczOBRChmKIFVhSwcJ6ZikbhSq0Tvv6+aA1CQIGi0sxsaSD8gbxx5QaQxCVxcAIASxqb2QqBQy2DxvNFa9rUUQlHVJRI69CmOSwlkDi39WclUFzgNJqYIgjufjiVTKOyOkqotSRlE9nyaRFoyz8WT7ys6zz+9pGeio9VcatC92iS9CNi53tvCCHS0TEoG1XBU2G5l8Dshsam8qW9dEgqQClK7IiuPn6B03cpLeI7olTJCaPhTOGboXrgUX+AfEJpIX+xteBimcw5guE/Qv58dFJJ+Pkmgp94mN6wKzWyqANo5J/sI8YRnhF4yey3F74RLISxAye/YXNt2L7cLy0EEiJI+kpJQCEyVaWjCwljSqwCKtxRAgWg8oKHdgwTI4RcwCGJkAneNTYwMS9x89/tYv//LG5tX85JTLs+NyXHtdD/N8tL/av4Kozk4PJ+OzST7sbl+vww4l7bTfOzmbdrF9u/9La627bE0A6e3OV9db11W7tZq+0lK7g/b2HCbPZz8u6oO8nFHIsicx8xGoaTa348rVBpVea72mZPvk9MmcZ2+/++ZKt3s2mz959nxycvbet395dXvrow/eH43HXNdQVkE78cxVWQul08EWSm2yTAShQLbzUTUdAUpmV80zUxXsHKIgKZpRMDdeGSh0lEgdqrgVRImOUxlGQgoiREHEjr0jYEFC6ECHUaCjJE1ASO98w/dwVcmARArYOmtRKIxCZnDGIjpB5NijDKXUpsiad5hQCqW07JlZCkVBKLR2xjbSVmw8kFBJK+r0vPVx0pqdHJEO2NTA4LyNknZdzJI47nT7D9//4etf/crBo4emNg2xm/4dzJxepPW8YD7AL1pIN0KiNXvHzoKv0Tnw4G3F3kHDwAgik83Lk+dgqqWkq4fLJrlNFC1y4BdsDV5YwwIi8aLE5aVN7iXb+Qtba+DzUdnlKAM8B34ugpkdLnBOi+hb8ASQcVEFLM4Mv5wGL6XfGC7joBdz4uX+dknLb6oG5zwgSimkFEIILcVqojcTFSkKpGwFgogUcicED1BYDgREyksEZpg6njkuXBUqHObuMLNWyBtX+zOWt+/e2d698ujxs9P5uPLBBmvqlqkQN69eAyxefXXrF7/+jevtlZbA3/wbb6904pmL193mjegdZlnYWSRTrYN+vG6cv5581VTWpVzL3DoznR9n83FVliu3uu1eArV5/OmemVrpkp2rv6hlL88nk/npK++8sb2zPc2Le/cejk6Hd9959+Yb7330wY8Pj4+wtlhUFIVhEhezuUraOu2JIJZB6L2TGovhQTU+I6VBSLZs64IEISkGYOeZQSglg0gGkdAanHVVbrNJNT+rpscmP3XFxBQTX83YVWxLtqU3uTc12MrmU2Lf2dwN0jVTWQSWStq6BmRSmr1lQIoiFKqZPIMQRMIzk47YeWsKkoqQvK0YGIk8Agklg1AHoWtIIY6BgaWIW52w3Q87HRXocjaSUjtkHcQ6DIvJMNR6Y2f33o++u7m9IwTtP7wnhfyrzbQ/zRbk3PjHf+HRlu9ZQGAL4AGYbc3OLrrJKjfjU19kXFfNQB7ZLwOfAcU5yw/QAzJQ8+dSSHERtIS4nDw1E6nzqTIu6vYXkYh8qUXmi4XO0s0esalam7ODLyMX4ZL+9oJJAGLZ4/IXcNiXymP2S3TGRZIHAKmEEEtQiEBCEWtxtRtstlQvEEoKJUWsUBAadpHCmkWoAIVlRA8wqwAFALppXZQg2itrW5sbnY2t1sbNq9sbWWnC7ooebDy499nUjDZ2b/ajdOt668Yr3bfevvlL3/7KlcFGJ07XAvnGze3d1bXNRFzbHvQ6LYpsKWci0AUXw/rQSOMUneHesNhrxf28GI9GB3l+5q1hw5PDYriXk5Ub/btra7dB6jTqVtmotRHfvH0jq93Hnz0ZD8c3Xn/r2p03nj178vD+51BmaD0qmXbbRVGBCsP2qghiX5XO1sj1fP+RM162ehRF3jtvqqVarxAylFFLBLFQmkiAd64uXDlzVeZsya4iZBJCaqmDQGkVJWmUtKJ2N0zbSmmpdRjEzrKO2vHKZtpfcYZNZeIkds575wjRA0ipUEgmQqG8c0jAjkmGQkpbFSQUkGDvEQDFAikptFY6VGHAzpuqJCGT/kCGrbDV8eyjTi+IWwxOoHSm8s55UwvA9d0rp8+f1nV1/eYrn//4h1JTQxjAv4ocSz/191ysVH5GVY1Lnarld73zdcXGgDMX4IUFZhWXUsK0KInp/MhogpAXbtpLCYpm8w2XYIqNvOJSO+MCILEYHjNefsSLAwlfKhYulRN8MT9CXPIPGhbfpX51cXycb28u7srnMAvEBTy9ScQeWEgSghAwDdS1Xni9q9cS5ZFqz55ZkyfBcwdE6BANusy7rKZGXDOVnFt3YNXG9s0rV7ZWN9qfHwyPZxwm7cL4iQ9r569evXrw5NGgVV+/0mutpiNvklAfH88+eXamQtrn+qPnB9PKbHfCO3e2XDC58Xrv5771ZtpPzurx2E8z8IPtm69e+2pRjKWUkmQSdYtyXBaTclpH1N3svboS3lq78kantX56+HB69kxF1faNqzmqB/efFaPxK2+90xmsP3r88PnTJy4bowdKkqTbs8bUtY9XtnTaMkVRjU9tNinOTkhGMm5zoxphLQrJDUNPL6yMwXtfl67KfJ2Dr5k9IgU6SNJ2Z2V1sHn1yq27Gzde729eC1v9tL++snllbefm+rUbm9dudTd2e2ubzruqyNeuXu1trLPzs9Gk3ekGSpVZBswoUASh956QoC4bOXNAIQIF7MGDVJpUCOA9W0QJJCRANc+0jjorg2I+Ye+R0VqTnw3L6ajMciVVnU1RSleX3hqwtTPl1u614elRNpns3LhxevismI8EoHyxsv23/vyif48AONdG/alxjud6K+xeVM+4nI3FC/Oa89nQggTLlxERL1TpDQHn3Ld6gUaEJfTCNxo/jXL6pV+wcKiHS6ugpl5lfKGKvgjFS2RkPJ84MSysBvFF0+zzrxZACzhf8zRrpgXgeJFvhSCUUgKKIBA77eB6R222A+dYSuiFSgtMQsHscsOBJqnAsw8JJfFJ6R2YAOVJpWll80q/VZhq7sSPHh3OJ/lnj/fuHY7W+hvP9o4nmXntzqtXNgdPjw7HQf9o9dYBJ8+P5JNCPZrRpy581r7yoGo9LNlp6iWKwFzZ6d+8c02FqqqqsNXGpL8SrIakhmdPWnHPmmJt5XoSrwCitz5zduvau4P06rPDD548+B6ndvfOzRL0w0eH0sPNt94WgT45PTvcfwpljqRE0m0PBiB1MZ1LoUkHpphW46Ev564qVNIGIUQQIJHJZkRKqMB7h6SQiE1hipk3BdgKvWFvwzjavHrzyq3Xrt9+5dqtW73V1VavH4axdb6urQDQRAI9gVMCdRTrtBMm7e7KyrOHH0RBtHXtldZgtd8fHB8cCCXavdVsPmNnVJz4BiZua+8YhATHqLRQyuYZIIAQKImdJSFRCGR0eTE/OazLIkxSVNqxtY34I3pCdGUxHR4AcNrtS8J6PjVlfvXV144ePWTwQZL0ur1n9z4TQI3rAf2VRezFW/g8aF9KTUvJJSR8QSbjZwQtXRKnh3PTTUQBTC+ukfCFUCdcyNkvrCiQQJynUV6QIS/bWS9fh/NRM57PqgiJftpwHC/YOedYJ7yg+jRzZUBGB8gX46fzMTWeH2GNxtsSzggMhIGQgCRJrKXqZj/oBbr0thfjaqLWEqUlee+FJCmEQFdb9s4T0djyQe6ARBm3Zbt7ZS3IPInAn42L45OxhPDZ1IKBdquzv39CMjg9G5/M651XXysrc//J/r4REwF1e3V47xBHHla7cGayiXx2DM9n+Sc2eHjvgZof3bm2c+vW1ZVOqxyP7NQdHz7IsuM06gmhs3ykdWvQf60t10TQGueHUNrPnvxh2IZb735tUuPB3uHqYP36629aDB5+8pOjhx8GUYoodXfQ3thAHZWzKTmPSrs6N8UcTM2AOm57ABEEQgcIDCCkChuLLSRydeGqHL1HcAAcp+0bd9984yvfunb7le3dnZVBz3DAuI1gXDVj79GXYCtg74wp82w8Gp0cnlRFBSikEq1269nDz3eu3er0BipJt67fOt7fK4tsdWurzObMCETOmqYqb6ahKCQJ2ZD+VBgLKbjRoJchkWBrbDEzdWWd9d6CUIKQXUVEQkodhNV8gt5BXaatdjY6tbbevXVnfHQ8m4yjNN3c3X366cfnfFr8i8ZLXzZvwp95WzxPuXxJrbwpFy+zfP4SQQtyGUgLVw68YOL4S4cCvtxj04L/ek6aW0IRz/Poxd50qcr+shDdBYXwywQt6UVdvPM5VvPkcTl4Xta/uBikLfk7S9nnxcBsgXhs1vm05OsKgSTiQF3tBpuxJsmx5u1OEElROVcaRgGAECtCdLVzpeep90yQla5SiuMuxulZCbbMkzgovJ7WJklXRhAGKLpJuj/OlA6CMD6bzH78o/eTWL9+69rpwcE4aOl2K1wf8GpCTskSOAD38PSkdNnUnAX9p741Odu/3ZHvvPl6RPDs4NMHhyeD3i4h1tZmzk/Hp7fa766sbDlX3Xv+L/ee/ZlWfOPt96YVj8fZ7pUrt99++2xa3Hv/z44//LMkHQSdgWz3Wps7pjLF6Qkyk9BCR6QVgHNlreK2ZYfIJKXJ50QSUAotk05bx4kpS1vnyBaY07Rz/ZU7X/naz73+5t12KxHsA0Une9l+LVo3vlGezbLpA1OrIH41r+qTo+ezwsyyOs+KbDqdTyeuruezUae/Us1nEnnz2i0hdVHmW1evFbWZnJ2sbGwhiqrInAf2XinV6B8QkHNWKs3eCKkcAgJ4z0DUsOpsXQglSRJ7SyogBJLK15Uty6Q/MMXc1aUOwqrIralcXe3cuG1Nuf/gnrX26u3b89HoL+xp8cUk/JLPFr68y7kABV6y2FoGG1xQZ+ilIvNc9/inXIYEELjcvS63L42hYoNxWgYjfrGXRiSC5vO8N72ocokvJk6XhV59M73Chb5IU2njlyjzvMzGOy+Flysiapyy6ZzZgwsIxqWUjue3XvgaNM+GiJr034mC9VTtdsO1ttQaVuIoIJoaloRNrKahZPCBQiQeOzBguxGr9vrVW7fT/nUvayeCXKw55pOSP3q4L2S39NROUhVEQmuUmnTkPD/49JOPP/w4H5995bUbW6l+9uDeyXQYdDtoh9hv27qsaYLZPMhDbK2X8fpBvHN8tCeGj67d2L375q3K0P7zcTWfw9TXWR4YkVI8Nnsffv7/Odr/IOyuvP6Nb62sb2OY3Hjt7TBqPX7y9PMffSc7fLp6871o+zpFUTRYq6aT+vRYIOruQESpCELnal9X7ICRmJ1Q0lU1O0ciFIJXN1ZbqyvOM7PzVUaet268+vp7P/fOW6/vbq1p8uy9B5xls4OT9PBs3ntrtxpHWalo7U4ddZ+8/0FtpowyjNsqDBodL2PqIs9MXa6urp4ePrn92tthuzUZnyHJjWuvAMrh0WG7v+pROFMT0aIYI0Jg9l4FIXkHtPAZaWCSi3LRe9KKlEYhRBCSEM6Vpsjidh8FlbMRE2qp2ds6m/varG1fFVIcP71vrQui1sra1l+oXPHFRetPL49floTDLxtT0QW35oU+D/AvCNoLEWK8RNa5FIQEL/elcM4KeFFiBi5T4BcJFugF0YkF/Gg5BQbEFwnuLxH6+aUz6LxlRWCmRQjyuToGInrg5faIGRpWPENDiEcQDWmEiQARUcaB6oSiH6v1lkpCWdVOCRlqrNgDspaEAq0Hxw6JSrYtHQZJK0iTg6nPgm5382q733JCPdrPPnxw9HB/1B1cO55X7SBgDPb29+fzeV0bQHF08Hxta7u9uvXxB58mYL712rVra63jj3/w/j/9r6qk097ebl2/yeBhkDCSEN7X5WHQGTrgg886rf72VvfwJ1OVd/u9K9u9t0w+/uj5P3/0/P1hfXj3q9/4xi/+cmuwOYFo58arxWx279OfPHr/T8nBys33ZK+PUeisAcv2bEgMwWBVhDEyMjERkZDVPAcBKoqDdsdbSyICdGu7WytrgwqliJJyfAZZdu3Vu6+89c7qSqcVKefsNCtq5ytrhuOx0deC/qZcRWyrYGslXFfF6cHRTz5L+xqQhVRh2hJCUTPidLbIssHG9uzsZGP3aqe3aq07PTqSOti4sjsZHk/Ho6Q7WJzF3nFtCNF7FlKqJFFI3hkvtGd3DpUhlIgIOhJhi5RGEuxrk8+DMIna3TLPXJUjkatLAnCmZmM7a1tpr/f0k4+STlsHwY27r//lg/Yv3tAucfOXt7Vw8Xa/rHbG8MWgBUC4pKnxhSJULJcrS1EXJgBCsUzp9OLxQbiAUtAlA/om6365qga+QO7Bc10vgkvyFJdFjS9n2i8sv/DSXpeAETzhJdD/olHHC3QHXxj5EpFAKXnxLAhJ7PTjbiS323LuvEbeSFQrVoaxZG5pcoxnhdNEoSQLrmTn4l7S38qMP8zEfDobnp5NoZW2O3F/7SQzn93fW1vbOJvlx+P56WS6t394djZ6+uRh2GpV+cwat3X9xua1G9O8/rM/+mOz//BvfOPut955LZkePPv8s2lhKvB5OVXtCKWoZid+PhpHa8aq1viT69dutMqNk4M6L4pqOBydPrbert/eeevn397aunqU+XDzWhyln73/o49/8r3J86ft/na8cZMloNLAzs3mdnhGUunBqkragOxqA+CdM8zOFFWQtnTc8sZwbYlEMujEg/XSMCKXZyMzOd3cvXbn7ffW+t0k1Na6s+msqirLak4budxwqQh3QpRt8LU5Gc4+GlXHB2HXgbcoFCAKFYZJSkppqYG5KuskbbGvHZvrd97M83w+nz+7/2kUx6vbV588+NwzR91+ORvZIgdrSVKgtSCiMBKCnK1B6sWpLkgHUZi2UWlPKmy1EdnOp9X0lIQIojQfnxCRdx6FJNG0RcrVVas/WNnaefrpB66uQdDKxvbPDlr80nflC6LddCHc/SIo6nx0RJfyEF7+4uWIRWzyzU+5EnHeM178tcyCy0xLL6TQxb6HFqyAcyHyF3ay9LKT/SV+z9KfkhC+LFHzT3l5XnyqyxdhwWVoFNpflAZoanDR1FdSyCaxNGEspEwinSrabIu1llQK12JdeZs7Pi1N5QFA5JWd1twOKNHuMIOJWtlYXZVBAIGQgZat1dPDJ4/ufT6dnTw9yU+G0zhJQ6mz2Xw4HjkAoQNGMt5PJuNIShlE/Y0NRLLO1nX5oz//7p9854/ns/k7d2/daAlx9EBPj8zp3vDRJ5Pj/flsPD051Gn76ATqvTOanjx4fvT82RO242P3w/a23nlzEwc0MwpWrq1cuTE/Pvzx9//04Ol94UVr/bbqDLz0jq3N5lxZobWMk3B1Q2gNLIDRmwqISFA5nUgVhq2W98ZkGVIQpGqwtctSCSWwNvODPZ3E1+6+uzHod2LlvSurihBQtu9/XvJgrX33to46cKJg4qzbP/vw4dnDn8S90jPUVY1CCqWcrZFEECU6jEjKusyRQCks5rPb77w3PDk6G46iVvfBR++n/UHU7u49/ARIBmmnnJw4V0lJaadb56WIYtKhtyULwSgabW2BxNZ7bwFZSlXOzhA9ACslPZCrSzOfgSASAtijVKS1LfMobu/eefP5px+Zumhcc18MWrysC/MiWrgBLSw+adm14uX29gtkegYQDcz9hQUs/swW+suTLcMiUfGLahhLVTVCaPwZmhqZiJGAGYmAxHl2PReuWBw3TfV5IaR6KQQbE9lzBl8jPk705TbavlFtQ2BqhsbnKoPN0BqQSCxbWUQkD0QIiH7RCBERIAskIWQcahaNAykJIbSW/Vitp8FWN8xtHaFIQ1F4MatML9LGcSRFo5C+GkvvzAyjK+s7UgK34rgdDudBXozz0hxORs+PxkfPJu2g7S083DscjyfeGPBcZpk11mXT7PggaXeFDFrtDilVZFncbl159VUiebR39Cd/8t33f/x+OZ8OAtptqevdcFWUG9qvS7OqTEsbNxlX87lJZvGWwc062OlW3fiUKFy/GQ+2tJKffP9PP/ngB1VRJ+1B1N+kUHuyzlszHSupk/VdGacyShGYdEhKIJG3tckyW+VChSpKdRKZPHOlIeLB1WukpRMBepjtP6mrOmp1rly93Y5DJPDeCSEJvY4H01nL52WHB7D3GM/ujY7vy35QVflk/7RB8lZV7b0XUpqqyEanzN55JiG9q501Sdqej49v3n0rL/JHH/04bveT/srjTz/oXb0BwGd7z8K0jeyqYsLepd1VY2rnWUQheOdRgJQklEcA59E6zyDihIidrbytvXXAIAPt2C/aJxTsvRAabMXGxa3u1s1Xzw73xieHwCyEeCloL2dXejF38Iud4DkqCC6vK784xEKklyzhL4ftZV/mRovpC14Hl/ci8ovz6xfpO3hpPXMeby+aXF1IJp478yyeIl96yo3WwdI+utns0heUJZfDY4aXxXTw8gnVOBhIBPTN7qdZ9zIAYpwkgZaIXhAGSkqhkKidxEBIAnqpSgPdDdRaSysJK3EggIyDQSgACFBaz4NISaJZ7SuGQsTbuzsUiDxqO93fOyk/ezKbFe7hqB7P3PZgO0jXahCns0nUanW6PSLhnB9sbBR1VeWZq0odhEmrq4JAKH12cjzY2ty4clXIYOvmK9fu3CUdTQv7/PnhZFKUrGrUQodhlLo8M9OzwhdPy2JvNH92PDueONHZ6Gxcbae9KAjmp0f/4v/xf5rkRdy7ErdXVdry5Dybej4xo9MgSNo37ogwcEXJVcUeRBSSDnxt6umwKkrSQoUxO19Oz+rJjKROV1da/a4DckVeHD6ZHO2TFILExsZmu91igKKqrXOAQpNN2v3APYvwYbedKVV+9OO9+MbtaNAbPdhnP3PsnHHWGKEDIbWzpsxyREISQqoyy8IozubDtd1rm1duHD9/uvfg08HGFaHk6eHe+vVXWchiNhECbD4WKFXUFlpZYxdDJyF11EahGmVc8I4Iddp2rnJ1QQCAImj1mKStChCCpARmQOEZfFUSY9Tp17aOk/j46WMCyGbTnxG0+MWgxYWxzc/q4i59+J9iBXSxZfni5AbPi8gvh0kS4ouDMVoOjZvoXeRevFQOvOC1c4ncs7z94lovYMYkEJD4/FjAc5QVAr4If2oS7Mv74YVrPNHC7R1RADPzokheTKyRAEEIFegAABGl9YgERH63E8SBDIIwCaNWIHY6cahkojAQNEhkW8lRbWOtnOW1WKyECklc3ej0up1kdQvDduZFrYM5608fz06n2dNxMZtW26vrcxuUjp8/fbyxsdnvdKIwlISzs9HN2zc7SeqKPJ9N0lY7aXfCOBI6GB4dtdptqdTmtSufffrpvKg2b99Z2dnWYTw+eB4G0GmnQuvC2NqjJyF0FIRpEEa9duv6tSvrq72IgJxFQaYq67Jqb92O0CttXKBNlVfDI84LrbVIO6rVBe8BPAqiMCIlCZFNXY6GKEiGgSlLV82ryVgEadJNV65dYyFMXpijx9lo2JQlSmsi6K6sWuus83XlhAyVwkjNwlhJFURRC6U8O55MZtX6V9+aHoyK42fe2yrPrXUIQgSBDkP0ps7GQioVtcIolIR1NY97K51+f+f67ScPPz959rS7tVMWhTX1YPtKMR2jrVyZu2IexB1S2gOxs0AAQCAIUBA1gvcOnI/abVPObTkHRBWmCFDOhuyYdMCM3hmUCoUSUnqAOE1Jy/76+vHTR7Yuran+jYIWf0Zl+9My7Yv9H18KV3GO+wXgC6JM06d+6Ri5Efu42B4tgxYReblYQm46WG5AjktExEW8LRlBiI11JS2fHi3Qy8iISCyWiZwaBz281A9ferJfHNQtVMwBQSzkYxZ02IvynHjh2QfkvZdSBFr1WmFbQyrtV19/5e7ta9u9FOoqN9ZaH2kcJLTbEQpBEDuGbhREklNFSqATamUwkFFqUTmhjIg4DE2dzwp77+nJZ/vH8+HJeiupo/jzz+4XZ8Ov/cK333j37aqu957tEZGOo43tnXavt351t9PtemutwzBJlA5GJ8dpu9XqdkkIYJJBlLTbADgej/cPD7z3aRisdFtrvdZ6v7W91ru+vb612t7oJDurKyvdNIp02umsbG7KOMlrqztr09FpbE/ntc2nU5vN7SzTKgj6KyzIl4XNCmBQaatZdHlruSptmQfdHghVjofldOSdJ4Fb13ZBh9ZTPR0W46G1iN4ba4IwJISo1Q2iOJBCEAGiDqIwjKVWgiQjSam0lg8eZa3tJDs+K0cjEui8d3Vuy9yWU1fnRFKFYdzq6UDESezr+fhkr7e6iYBSyt7OlYPHD0enR+u716psxoj9rc1iNg2VctY1wvJBHHsk0BJRMrMKY++9tzU42yQOb2sUS5cXks55VxbMTCokEQRpV6fthtTinF/Z2BY6mJwcz0fHtq7/UkELF5mWLtHLltaMgC8mVX4xwV6kTVzIRCzBwHAOynVfkJXCn7L+OUcsvkjLwYuhMSIxiEVGXfqOcCPtBcQgAMVSpR3PXe6RPKJflP1ACGIpCdOk6EvIpcu7ZT7XPW8Su4OmT4WGcyhXb9/56m/9g3f/7j9k8MNHn+NihbMw40Mh41Clkeq1w+v99Mpa9zd++x+88yu/ytde71+94at89PT5Rj+52qNrPVVb7sdKE5Ye26GonQuEkFJtDnrW2oOjUeZo6OMqTK3Ep2f+8wP7g08eSQ+7Gztz0qfDyfbG5nvf+ubW7tazBw/GJyeVdbdfu7O2ubF1ZVdoqaTM5vPDZ0+tYRVGJOjZgwfd1ZUgDIaHx2Ecsbe2Lqu8PHj+/HT/sJzlo9FkfHbqbA3ep1HQbUVJEJCUjOSJWGiK4grw2aPH9z/88PP3f3D6+OHx4bGdzsA4qSMgAUgiCNA5EFLFbdVuEaKtKraWrbN1Ba5WnT4KKo4O2Fln7OrW+mB3JxZQ1LUri2Ka+dp6bgTJrVaB9dxf3VTEYRB45611AKCl0jpUQSiFmBaz6aiu64AcV7Pnpiy8M0QoldJxW4epUBKcLacHZnycn+wff/7heO9JUZbz6bgwVdLuX7v1yrPPPprOJoPNzaLMAx0PNrfqsqrmU83O5nNkr7sroGNva0D0zgqtG1E4KTUqXReZSlqEohyPRRA6Z1xVIIIMI5KB1AnpgNnZqqyrSkQpC22NnZ0eS63lv4kS6gIn++IiEpbBTF/46UvOQC8lpfPelb9g0sfIxCiB7RcTOoAFlABLPccFbBeZv5D1EF5UGUeAF/tS5svCTC/U+heUgUs/YH75ERqqLDdBu6ANIiE4DzL41u/87lt/4xerTjtuXdu8fnPvow/mJ6ekVNN1A5IWspPGrUSlSq4k0au/9uuzQftw9OEs4+wU39jdqQ8fXOnh1W5ymhVExKRzazbapNANUlXUEqROtELBEPJMRlZHZxUxp6ccfvj0w0Do1Xa3RKUi+drmZtRqZXn28I8/tWUehEEURqenQyno6Plza21vdW00moyHI6njzupaNpv4On/4kx8O91YCqUxVZdlseHgwH4+qPOPKZHV1dpo/fVZ//vBhu7OyPlhZGfTjJAEUpbEAaKpqNBqRDvI827v3uakKEUilQ9QBCGBfB2loK2snExFIJIK6tHNGQewc6qCZ0SGimU9MPvfOevY6jnob67auQ7bVdDYfnznrnHMAQCysqafjaV4+SnpruxsbWqNUqjZ1bYwkb0yd1bb2WDvX7fvnn//E2rEzhZAyDNpIaKqizo6L07kvczAleSYiFKK/tnnn7a90dq6NJmfVNJ+OxyoNX//WL33vv/knh85svfIae1dk5ebt1yb7T+1s1Fnpj0+PMe1QmAKRIF1Nh0RCJS12Nko7tsgIcCEmpJQzlYpa7Cw454xRMhRh4E1tsgwASYpyPguSdtztCR3qQMmfqVTMXxq6X2hlLxaMl6zgvrSV/fLf1jDmLt+FF3wD+LK49ct8e9nK44ID+/Ij4sst98VlNRa5vOQELcSYeHmcXMCVzk+txRmxLJL5glgLQLSYX3tLceeb/53/8Ju/9ks/+fh7EMh00+1sXO2urE+OjqUQ3CgdaRWGmhGEDKsia71yd203OT77CQEOZPDQCq3wq29sz06eOILVRCrJp5lBxLmp2lqSV6eVud1pRwHOrIwH7Up3hnP7+Okz3d35/HA8PDja6K8+H47DNLy1dtOReL539Nn7H1y/sbu1u1tmuXE+baVFnv/wT/5lPpv92j/8nf7amopiYHmy/3R4/Gx2dgrOHj0A9jzY2Bod74/2n8sgwCgCTSSjUApbTsvpzNR8dHDEzhB48tY5x+xcXXtrhVRCSRkEYZKADhDA24o8OWYhSUphqhJyx96yrUXclknLm2ohj9YIk9rKzcbgnXeu1U4RUDo7tL7IS1MbRhZKASJ5RoCyzlJBzx5+Muh0Yi1JkHO2mE2ntjQ2H03K0pCI4tPRmTFjAKnD2FX5fPjQZlMuC3Q1IktkKSSJALWSYTjPx5999AO695FSOu30QHjV7qad3lf+2q//2e/9P8tsfvdr3zwZnkJZ7t55+8M/+H+xM53+6jzPVJiiDFxdqSTxjVsfoSBpvWcSdT5DUmFnUBVTKZVKu75RfQhb1tTeVIzs2Xnrqvm8aM3TNJVRXOVz+SXcV74stuIb7bIvIQXwi854L28t+QtrTP6L8JJfOCNQAp6n85/K2uULIz762XTfJhu+lIsZX4p+RLgMdfgZB9aFqurymgh8jWH86//T//nbP//173/v/23y0W63XfoCimw+GZFQJFWzvBVCGgdBEEqE9WvX7/7816fTjyPk1jR21F+J6jDAtNc9fP60l3AciKmFUGNXA8pQefl4YrdXW71UjCugKFIirrA1M1VWZU8ePjs9Oby2vVkhJl63FNrpSVHUe8+Pk05nWvvZ/cfVeNIbdLNszoJI6SAKx6dnvc2Nla0rDz/8iQo4Vmpsam9qm83YO+62oySq+33HUJlKCs0Ihi17cKYm7YQEJkDPztTeVM5bYo5CTVIAe+CafcBl6cGDdxSkIo5r71WSQDn3ZUkoHQgZWm8qbytnSAhJOiRBdnRq8zkCIXAk0Re5lzQaz0xWsPeeXbM88wu4oPPW2Czf23ss8Upj8SAFkghKU0/n84O9A8fombx3ri7qbOzyqTelFqiEkEEgwtB7Mt57W7tqDlNCKYUM1m9sdNbXAx3ZohBhlI2Hnf7qzbfe++QH/+qj7/3Z9btvHj28f+XW9fbKqi+z2phksGmlBucZGIUUQptiRiQZPMVpIGUxOfG2EkqrMHWmFCrQURtIiCAy2cyZGqwHQJIShazyQkdRurJ6dHL0ZeAKvIQ0uDw6ehFzfAktiC+9q3khUXrhRIeXnHB+dgX+JZey4NYtP1/quhdmO9hgis6xFs2E6RwBAue2kyjwIu75YsWzJN0iLLrfxVNbumstD51ztPbC3HDhSduIP6Jnb3/hP/ofv/fLv/rHv/ePT5896LTm5F2Q7I4Opu//3j8WUhAJIQWSAEIhVBTI2tS/+9/9h92Ej6en+cwOoDc/nRBWyUqQStgRRT90Y8OkfT/0cagYpatdu5PsDvoZx0VrcOii/YzGtSwtA5luol5/8+7WzmrSad++vn779s5GKneD6vWdzp0+tnwJAI7CJ8+OJ+PZ9VvXVzfXZ+Ozqqz6q4NsMrn30Q/7ne48m6PJsSpDHSpJh3tPKWqDCtg5LnPB3teVyaZ1USzU6xjBOVeWdj4GawIhlZTnCBcSEqVUUgohQGoiwbayxYxIUNL23oGrgQg8gKtdUZCKRBQzAJuSXW2ttXUtCdM4zKaZ925yNnZ15eqqSTPIgtkjsECorImlmpZZq7vW7bQ7rThIkrnxB8fDg72DbDIspsNqOqxGh2Z6xlVO7IMgEEHoEI13dV3Vdd2wcESgVdpVaVe3V6rapu3u7iuvzsYT652OQoEYtzplUcyGR3WR9dZ35mfHvV7v5PmTtLdazEZKa+vBLzwHyFlLJFTSQamtqdlZX5VSKe9ZBTEKhaSCtNOIvHpTAYErMkCMeqveWQYIo2h2diK/JFwXHBi/xFd4eAHUuzBTbkzLcbmlZLxMKF3ybwDov5V/Af8lboB4QVfwwPKi+1w2y8jQWNHB4gyhxa4GG03SBtG/mEvjudc1XQT/Enu1VEhc3m6By+KFF1+d5a/9B7/xtd/8+7//X/5fn37wftIR+srGfJi59Lied3xtRRh49mydkEoJisLAGf/226+0O+mHH/3YxepK1Pns84P7D+6vbrV7u3dSaUASoyJJo6IoJfoc0JqKxc9d62fWDY0/PjwqvKwhtFQiBIPVQbK6qdPeeHQmZDFkOdIhUkf4UM1PV7S7uSFfYV+xeLoZP5zTaFYL6dNWb3176/TwcHR8OlhZPTx8DlUh87FUKmi1JgejQCqwtqyqjf6ge/Xahz/4V95Yl+fovQfPtvIqRgT2FpGFEEKJhWKOFCi1kAGRYEAkHUQhkmB2bC2XBYWp6K+zN5zNbDaiSiEFi1feVbbKZdoRlYEyd9adTXNAdEIGcWSt4+HcSUJSJEVjSEjIkm0+n0RSPN9/1lvpYe3OJtPPP/3k5OBpMT6zVU7ghVQ6jAERvEOlmNnkmWen45SBZJrKuC1AyKQVRUkQp6iDKps9e/CoKitWKo5CcF6tSQP+yu1X8uHhbHjc6q/Y+ay7NtCtnmM3Hw0dkA9TIMHAzKSjRCctIGLHJCUIpToDYC8lAQoZRAu1es8qCInb8+EBKg3WmmKugnh2vDfY3u3uXJUv0Le/ZJXKl9vCRRO31MHnhpqzzMeXibMNt+zLXPP+ih35Fo3wIhcSMCznvgtEPi/8JWFhEEL+QhrmgmdzDsNYqiQ2yhYvWvUsi/4LFs4luCIREqN8+2/++o//8J8//PM/Ye+wtWIyRWkr6W6dfvITXmChBaJAJq1C570hSHauPz07m2bzqBJPxuajTz5bDXk9hI7049IfDctB0jeWPYqhQWlq7+jVq6uG8f5REaeYEq2vr5bx2tAFW61BEMZzpzzglc3t4RHMM+8ro3XroArKoitgHlHR4fmWn2x1zG6fDkvz8SnqwQ3LJg4FsTHGKkZXFOV8poRUJJAkBGHtWUh5sr83HwVhFE5ne+Bqb413Vqarydb2/Oh5a21QTIitc7IRTUOHjIxIkoUWMkzbbRVoB1xn84oZZcDOcQ0iSV1tfTYCLykJUQogcGUhVGiNBWCpEy/JmJKEzObFoNeTUTgDruaTGrjZEzetnEQs60xOT0+de5gkLs8fffZBOZl4V3jvlQqCOJUqYmxU7ivjHSol2oOkvxp2BySkUoGOUonkwQMySenqSkiZ9vrT8WRjZ/fg4b3exrZ1ZmVjq7e1u3Pjlc9+9N2TJw+v37x9drR/87W3njz8VAisijzqroFjV2WkNABVswlbT1KHvb4pMpvPVNJpyDDOGCkkG+tJeOO89wCspESt0BkpFVdVOR21NzblSyq/X+hOmzqXL4C7l26LgC85b5xj4S9vcZpoR2Zmt5Rf4f/WOfaSdgQsrTk8MHpkBJQN1oq9v9jQLubfDpdny6ISxkskpHMJOHqhA+BLLlyLVW8T2HhxL/acdrqDfv/+J/e8r0kFQhkhvFMb6ze/8tkff1/EiSKyjkGoIAx0EFljVm7evPNzP/fsB7//el9FKnq4P7sxiAIovRfeREFl0Ldy5/fnrsB2S9dKGKH82iD5yaMDjeFgrUedQaG3o2jlSpDESg8zN53b08J3AtiJaDsVw4ySJNrQ6cM975SXgZ3MimE9jYrjnerptpp+c6v9rE7v7c/356ePH3xa5ZNW3K69VyqojTXzmuKOE6AEaRAV+2w2CSIpQy2kcHOr0k779msiiqMyZ7ZMiFpDg9sUREKHaVfqWITJxtZ6pOS8KAvnWYb12cgYo1LF6P1swoCoIjcbQdACgWY2MdNJtLZOSPnpAZDSSSs7fY4sJLizo+Oo3Wqv9MswHJ2dOG8QFDCyUIQktZsVZeDGD37y/XIyNvlMEJJSOk6FVrY2+fwQFjbdXgqtRG/l5ivJ4EpdlrauamOy2b4t5mwqFoS28mUlgyjqtJHUZDrfvfvO/Y/e1+Ozcp7BDXf9rfdOHj84Pjiodna8dcV81umvjvee6LjF1pBQILWvaxnGKKSHOmx3kASCEEEStHqNHD8C5aOTIO6qVt/ZSukA2j12NTIjCRVopcN6nrXWN5ql5TkD9qJvbRA9uKShfmk/+1M03HiBQ0a+tPi9EOGmSyYa/6aB+mLMLrl+fIn9R3CRERcRyOcU8wVckXlpwbXAKp43uefAqQtCH1GDA0EUSIgol7yf5YuDhAKxgToz3v7mt6ndvfXu19Zv3pqNR0h5O+qYcfn6nVtVPn/26JGWARETClMUK6+9+e7f/q3Njd7zT390ay1lpw6PJ+zM1lonCpKdlZVidjYrrCPvSAPoCGcKyrSbKpIh4q0bd8zK7izeCVubaRx7x4XxWe1ZojFeSrrel50AQHBHw2rKgeYwJXaCVNTudEfF1tNyd4RJYk929fFaN6rVaoX9yfCgrqbo2DvW/fXBjTud1Y1Ou6MQXZmbbI7eWFvbypiadW+tdfUVWxRVngGQyUsWAoVUURJ2ulLH7cFme+NK2FvbufXqyuqABZWOnYwgiPPZ1NtaBFpGbWArBDpGrgufT4PumjM1WyPTFkqVnx6x9SQDU86FlEJIb42pDQURMtSzmQcHQIiCpGQEYu+JbD5184mvaxUGpEIWITA646wz7Cpva6HDoN0VQUphouJW3F+nMAKBQisZBEIHOu2QkGyMqQpjqiKb27ouirkX6vob7xSz6enzR3Weha3OYOfq0eP7VZFvbm4+ffxg89ar+48e6DBSQhrPQkpvrQCsi0zGidABexZKe2tVFOu4xUBsnatLFFrqGImhMaEQqnm7B2HobG3yWae/IpA0fJHA3oDliS50Pi8jh+HcJJl/Gobx3NeK4fKZgPBTI/bfLGgXHqFLgP6FXAv58zn0Jdmn5ZzX+0vH0zkfZ2kFBkAXAOOlVgZKXLA05AIRgYhEggSSQCFISCTZWNiKdu/6V7++u7W2d//e7PjwW9/8dhAkh/ceFCdHN2/euPLu15KtayKKotXNdH23d/vOq3/r723dvPnsgx/6/Qe2qJ8eTslVtTFT0ZaD1Y3VzvRsFAtFICzLkCvJ5aR0N3evSxltbuxw0gnirgraR7kcpGJc+5mBK33ZlvjKulxrESAcFR48jnN2HmKNCsATbPcx1B7IA4Zn2dazarO2do32d5L51uaGD3YPD58U9TRub7YGW+xQC2HyeXF27PK8KjLrSrAs4o4abATrm7asiWnn5qs66QTtlf72rXhlS6crK1dfifsbOulg2ArTdrebes+TzBokIKqy3BrL1qm0rVtdO5+h894YVpqzKSOJKAEEUtoWWTE6RRCkQ1POSCgkZFvrKBFpG0kWZ8e+KXFJMjM4A9YggCD0zqMKGYX3DM55V3tjkC2SVGErGmzJuEsqZCQRxFIH4J331rPXQRKm3aDVbQ020/Uryfp21F2XOnTW2XI+Hw0B5fU33hEE+4/uK4C1rd2w03306cdxp5/PZ2EQ5NNZ0NtA8OVsijoM0jZIpZO2DEPvvSsLEgKRrKnY+iBKAdEVBXsfxG0EBjbOlAjIzgoUjXC6LTIphORLAig/ky97qcVdWrvhyyCLl6jwl2ReLvPdeKGShNxAGAguHt79JWN2edl0sYbFS1eBfoH19R4AUdD5RS6kHJtKgBjQ48uYMDjvdZEWYMPlov9CUIYQPVGDl2LPwLVs93/5P/lPetc2/vl/8X84+uDH4/3p3vfu/P3/yX968Ogg7nQePNuPBxtr126s3Xlt7qU3ddBb1a3W0x/8ycl3v3OtH9nSe+tnOu6trg12r8qkPc5OhGXjfG5gagz4HNlykORStwZ9G3T7EQcxOk05CS3g7kAdzdzZ3AmF6NEyhgpvD2B/bCc5JIEoKq4sr4S8FuK+wWubZCpX5qbmzqfFLxzY3bvhD6+p53/9jX4/+ZvD0fOv/8LXSYR/9E9/7+nDR1LBzBhA8HHKnLLWQatNUllTX7lxN15Zuf3uu6fHZ5/+6x93t7aZwVUFA7u6zsZnkm3UQkJRWDZ1xYG2WW6q2lkPzDJIZBTVKvCmCuKkrCuOO7bIhXfeOTMdOWfQWxDBOUbGOQvOM4KUmqRIVjeK6dh6Z8EIRlMVAkGFusq9dQzOIAogBnCIAMKxd+yFDiKQilGAFBIRCU8efeLKvLEed94LHQVxilIJHUbtbtTpx4NNZ62vijqfTE+PPn//e9tXr9+488ajzz6M0vTa3TePnj04m0x10jk+PFJxa2VzZ3z03FalKIuaPSKhUlhJHbdEHJuyJCl8aep6zuylDmXaKqdjFEAoTC2cdegrFILREyoZAPV6s9lUAAYL9f0LQ8jL2vzn89RlWHn+Sw2ILsML/bnIA10Ipl7goBaMeORzPiBdoiXQi5yeRaUKcL5uWfz3guQh0wKljAur8UtUYLqYNy+uUCzvuwQ/ns+VljcmosVOSQhqWlpBiICiWfZ4j+K9v/Ebd3/l5//1v/i9+vSR1n0u6+F4cvUbv5hneWkNJp0rV68+ePRwPM9tWa1d2UUiNtXo4/dtkdUOHIgxC93ptdc3O7Ha7UeTg6Oj02mgdQVUuLyr6opaV3auXN1uRVEQCVkBPSpXVZT2Y00eTgp+NufMcSsl5xertkEgrOW9mY8VErEDnM+ZGUBhbXg6wckMCFkClzx4Vm95GG6Ls/VOdOXWa612xGy7G9tV7cJWO+324t5me2W9u76hgsRWtjTV9VtvvPftXxzs7KadnvFw8HSflHbW1kXuvS9nU1tVg7V+f201L8osyxyAYyhnWZmXXBVRqy2CUIYxW+sBhY7N7Ay0JvaYtEkqMAYF1rMZyUDowOQzIgmeGTwiO2sFeAFesmHvHLCvLQFIRcVs4o1BFMwOwCF68N7WhTeVjFq6vSKTvgg6Kkqj3sCzr6ZnQiihA5RaRolOUh23SEVCaULBno1jYIFSqShqr25tXr/V7XSSNLr6yi1T+/sf/uv1K1c3r956/vhRFEbZbBr3et3e4Gx/r7YWwHlrAYQMQhnFri7YOSJRDIdNrHhjqtlESAXOIREK9M6aYo7OC0nsvAq00FpJGcWpIBmfby8uZsWXedzNtIXPI+ynas68oBFxHm94SaLh4mZL1Zil4sRC97+Z3y7GtkALtn0TwwLPUcewBDCTB8FAzR5ncZ/FJy7ZAhdHElxwgC8veqFpTeES/w7xwou6qYcFw7mZbcMjIJJCKIkM7N2r3/7Vn//7v/Xhd//w8Xf+v762J49OWr3e9rtf33zr5w4fP3S1a7/yTlUVG7u7caDX1/sHjx5JXyYJzA8eSdKttDWajCXJ9dWWSJJkZSDGw8cPn3uUT6Z2ytgOjRYS2uu3bl4NVB2qKG33h25lLDoy0tOSMweHGT88862EVmMKBQYCgdECPJ/Y4zkqBQQwmfvhhB8c+pMcRyVnBQBimIAxIKVHFx+bLYDhtjzzVZbX4tlw9uzZqfHqja99fWVz9/bdu6003d7egtqenhwHrfT2G+8mnVbl/P7TZ+wcAHpTZeMJAwotq9lMKdFqJQycV7Xx3ktZTufFdO5NFXd6qtUGIgYWQjN7dg68ZSkFIrMXSZcQvDGevStz70pgxgXfAgQJb4wxVjir2diqckSNnWkxOUP2RODZN92Pc7WrCiLQrb5ur4SdjagzQBAkpI5jb6x3tdBJ2F4RUaLDtkq7iBLZMwM77631VW2qDK31rnZVFidRu50K9kKqu2+8VZv6w/ffv/P2V7Ki9ABlPm+vbpRlOdx/KqQAKUUQsrPeO29tY3nqygq8BWY2FgRJFbjGoa+xlfCOXd1YD6FzSgcqjKfHB7HSEpQAD4AOPSKK5hoXyL5mPgp+kV09f4m/23n7yEu533O26sKvCi+8cs710/AC/4T8En5qic5HyXyOOYILN50XXDPlssVGaKjwl9lI55fRYH0b6w7GZhC14O9iA1vmBkXBL6i+XfyqBVwEAcA3Im8kkUggkgejouRrv/mbj46fHdy7Bz4++uwxG7vy2p31199Rrf705KSl2GaTZ+PRz7WC3fX+kw8/EIeHmdyK45xF3el3E7aiagsJB2dZzOHqzrUP9ib3DyZrKz0tQSl7f+x3Vls7O7egtQ2UWaXmajURYWHluOBE0/O5O804VnCjIxUyAloGRTCr/fM5r3VEqvhoyqcTOB3D3hEBc9zmRr+9sqgC8AzOmFC2PjZf0/jHr4WZqo5HJ/bzvfl7b99d29kGhjjROg4kOGPcZw/vRXFaOygsG+OiID4+PJJS7N68nsRxWeTs7Gm71e60TV2dnZ1aIABv5lU2Hps8C5NEd3qqFbMx9XTsAYQKrLMAgsBT2iYgV8wIAUnKKLZFxqZRvXWN4aFnh4yIjfNYXGYjjlDqIB+dknOkpPeOGdl4X+YkKGi1ZNwRUUe1+kG6knZ7JCifTvKzUyKIuysIEgnBsclnfmJsVSG6xmMJEUlKIYSbnSipgiQ5mZ8Eu9vra6tsZpPD7O2vvDM5O33/X/7R9t23nt3/TEqs5uP5fAZKIhGogHTA5ITUgGjLwnsXpD2CyFSZUAEDyzAOpC5mZ+wMytg5yx64yhkCRNZBFMdJRnAyPpYgNKIDrAFc433MixaXX0YNvQxQ5C8aar3Epl0AMZaqMJcwTHg5Ml7EdeBLpMCL25w7gFwGN1zWhVrMkJtO9fJpIC4imURj+dyQWxcMPl4oPV6yy7rkz4ViUQksHLAQiYSQgAREdVXf/ep7GGR73/9B9vzA5GfZ2XDrldeEDtP+yvHx8drOFW3mo/ufyM3rn/75d7/y6m6QTR99/nB3W40nRazbHcbHz0cOgiqv2sLO6/2nB9F6GmTtMAzRgVeC++10a+vGjY2NfqITKFUU5t7PLWhBgvDRyDGhs76XYKQWfkCVg0DAaOaOZ8gKjs/8/tBPxziegjUgBJQZKe07LShqUCkQ8tihs7Vygx/XXwvEn78Zlt9cI5NcGexur2+t5lkZp9H9jz91dWFQCBJFlmsdeJAgKFltX1/pO2sGa6vZfB4mSa/b3r5xjUjc+/QTc+JZCjPPp6fDYjoKwiTodKWWiIhKozMNdtgZwx6cKVScgND16aFudVSYeHZSSmcc8sVbSuiIlApbLQDhvQEhbZaBNWwdKsEAzhqwDj1IrWXSlnFbRK24u+YByumpBN9dW7XEHIcyjJwx3jpvjTeOmFAqEcbMwtu6MYwXJFQUtfq9pN3uJGESakF1nQ87rU5rsDqt3Vd/6Zf+6J/+k7X5bGVtfbL3OJuckQpVELqiAGG9sFLHzpSmyEkIbwykzlnrTKVbXQBwrhY6kEFcjE8iCkQkfTFzAEKF3tQqCqM0dSghDCVKyQ4AFAMiWPAeAYCbEpbhZRA/gOdLKhZ86Y8XRUyxobM2JSstRCHOSXkXFeplPdFFwr6k4I0/hWpwgYt4UTWOkGmh8X1ZnXUxQQIi4he12xaP2/DjgZfiNYQoEcViFkUIJBa1+vLvRsUGSQgtb7xxZXTwY5NPTVmc3n8atFplVZbWpes7T7//w/LZ4zSNSzNfS1LB/vTglMN4Pp9nhwe0tqMR7z89PN4/1YHSaWQErA9aK+uC9kbDvIyk8OS7aTjY2NHp7mrgutpAMDiauUkldISJxv3M5xYA+XDqt/uy8N4zKgJB7BA+PrDPRjj1nE3h7ACLDJlZiIacxMiQZ540VRkYz1+5AwT4o4/qcnb9R0XVpx9sqOoNPTrOZlLIKAnHowkJGaQpyVCGui7rh598TKTKstJJvLO7Y53bf/DYmDJKko1vff3s5HQyHR08fGSdsfN5NpoUoxNmjlcGQisKIyAAZ1QQemtcbZEIw4SruSuLoKVVu8dEQCSkJkG2KgEEevYAqJVK0zBQ7ZUVK4JydAKCfGnrmZFSMDtjnFRaRMp7JiSQyrMT7Lyt0nYnc2U9H07NXEdRqBUgoYwsWvYkBDJw417bpBApiAC9qwRBGIW9TiuJEynE6qDTaienp3v7z/ZmlV27cu3bv/ZbP/zTf3H7K98ApdFZEpKta+CZRNJWeaP/BJ5kGNV5RiCFDs1sotO2qSo2nrQG702RJYONejaqrJFEhtl7ABnItd0wTiRJ4XnpQ06uUTxCcc5f8eceN41L+oVO22WTqsvw+RfVZhZy4SQu8m0TusuwWhpyLKKdUEIjHnuZQnspF79Au6XLdIXLWsrLDS0u6vVFM34hFoXnYuUXlvAggAAFIAkAgSgXWlKi0XBa3kxgw9hqmElJL0z6XAgftlrdrf7J59xeW9dRSq0BBdHN11//8x99Z3Jcb2zsuL1nh9aMD3F1a/vqzdsmm7fUqBaBD9Jen0PBeVlNhuO1NY0BYRIkYSKVm1Q8hv5WurYTu1bInuRnJ6qodRDqzKCTPKsxEiwJejF6AY9zj4yWeUVDW9GzOQQReqbp1E8nEMUIjLVpmgRoxXx9HfOKDyew2vd/761QK/hbr9P//U/yP/3kle+J+K/F37kZl0cH9w+HV9f7Yb/b+3A6b7XiuirrIk97G93BuquLMpudPTk+enAPPHtbMfi00/78R9+1Ve2dFZLA2ap01llXF63VNR0GjQWgq0s0hghJSo/CAdgiJxS+ru1sglKjChmhno29bUwiPYAnFEIpHSdhtwNhFAhV1GUY6CpDAF/Xhph1K5VRDEDovSsqLYXS0haTeT4jv5602uQYmIv51Hn2zFVRmapiICAtlSYZyCAK0lRFiSBwppBotCDORrNy6tIUhTjb9xjHK+tr127dmWXF0ydPeqsbg+1r+Xg6WN08fHxfBoKZwXj2talKAkalhA4QhU7b3jtXVULoej7FXAAJ542vLHufT4Zhux1Gce7BGWvmk2p2Jm7cilY3082rjcVIk5wEgGBYmrMujKhoaTLTIBN5IR/Bl6V98Rztixf+jbSMWAEkgOS59ukyPYrlkuYcySAAGUkS/v/b+5MYy7bsTA9ca+29T3f7a62bm3n3+hfxIl60DJJBMpgkRVGZSrGElKoSWZBQQAFCCYWaaKqBBtJQIwFV0wJUCSlblbKyIZmpYBMko494Ea91f967W29229PuZq0anHvN/QUzcy4grzsMcLdjZtf93n322mv9//cr+QVKHHN7lbxILEBBvJr4fCYZZBXuc7V0XyRHy2eCr2TVZCZBIkQS0UREWqAd87QnJ1SoaE1UbTvMtN6BiYPEWXDAZDZ8c+ntNO4Nx9s7adZ942u/dPb4sY7T3/3bf+d//X/+Dy49yZ2pmqYwAxptDa7fcKrwzcliNj3Yfzvav4bszs/OTkN4mheDhX2tv7PRP78/ayTq7/aiA11v9rZ0ujWpNcZxP4ZOophwWkPjwlZGC5ZulwxhGURAbJA2KP78Qjb2MF/IcgJKkVKtYwfyEvqpXN/C/SGNMjxZht/5XKQiuDfncYz/9X+Y/bdN9acPbn+oJt/o/OjNTvndv/zzN955V0nY2t2+89qdR/ceMkunP7z5xlsmpovT86OnT21lUYEtS1sVvi5E61CWgIBxCiJaB2QmYpNmYpSOEwkOghfnSEcCZJRiXYuAL1OWhlk0aVRR8NYXCwkOEVvOAxpCpbU2cdohhcE7QGrKGpEoUnHcZ5GVd1MBhNXN2uUFM3eHo45RWrgo8sVkyoguuOCscGBptyxskLDlBGodxSkCNPm8Wc6M1q9/8ctPT07PTo+yXn9j77rpDU4fPpw8O9h55c7OrTv5bLq5u1NWlVaqHTcoE3nrxHsC4bbTBkDGuLpk35CK2TkyOjSVyXpA4OqKnRMJdZXH2qAwF7PIRMvJhAOMrt+pqkK3/pYVH6WtBwREAgqvNkEWEAbmz5jXXxSx+NLZ9jNCIiAC1C25d92DpTWXolVirfSBsMKbalm5w/EqjHK1nWu1psC9YJSuMiHb73PV3oKXvhoRSL3Q96/KdnqRBgDriY5qB8iECpEI1aqH3NKlZBUtolbIuHXaAJECxSB8/sxff2tki6lSQoBZp7e5s7sxHj7/+GExX0yr2avvvnb9zf3B7r6t82c/f3x6McHOgEaDXC8Wsyf5yb3f+vVvXs7zfr8fRaKj+W7cpEk3GWzI1O5t9tJeDwZ3kuFG6bAM0SChSFEA5CB5zb2IlELvZBijIiIJmcHSQqzFLSFfSlpIWaw7egJ7W+AC9BL53AE9OA16g6718KsH2hs8LHkzpp0YtyKlFBpo7tq3DszTG+n5bbu8+8n9V25ff+dL76BSSmkgkyRGR6o76E/yPO73KfGURnFjQaSYTYAg3dwBAWLgUNXLol7WKopVHOs4IU3iGUmBMOgYSIv3iBD1+mxru6hDU+ukAxwQxIw26tNnREbESdCidJJkUZYCiohy+azKC47S7sa20gZAXFGKsypW7KwAKSJfN0aZ3b3rSdqtq3J6+bysKmEJzCJ+ncSyii1czyEAm9q50nT6470DUreYHWSd21/9+u5yenlyuFgsMlIuwL2PP3py//7WrduvfO7zUZwCmabX10obHRVVJcGtTGhak9agNDu/jshgQSE0rDyuc2cFmHSrAXdEAN5S1m1sNZ3Ptm6+ZTZ29UttXARRSLRyHoOsHAfAwAQowOEFYeazFvMXuGNS8CJgbqUfkhUc+Upk33rfcC3Kh5dzfa54Lu3q+gVFRbvFvaThUFfwmhVMBlqZZEtN00J0NZ9dk2rawJwrmePVEIhWRrxWydjWw1fJ8Wv3XtuUImrzB0g46EggVMYkg83o9HhZz6fs3WKx+J/+2/96462v3vjKr442Pz/eSyGa1bY7vn0n7Y2f/8PvuDzvZN1o86A3Pjn68cn3fvje7t4eaqPjbNjzQ+kLJrOSO9mgO9jONl412dgQPZhJlspGQiGAIZg1YAiZofYcI4wSqoERoHSCJChq4VzSpbqEpgC2wCIc4OQCxn147To9v5Reqqogk6X71p307pIjhP0E9zL14Nz96LFksdScfFy/fc386e0OHE6mhdtXShdluXt9d2t3DxAD4ZPnz85OzlzdsDCVEMdxXeSuqtlZ00nRWS6XzA0FVErZwkLwKkq4bjAEQJQkAR+AhIxG73UcN1ojqtAUwl5FsY57gqT7JecLEeTgMXi2dahLbyKTYNM4Jj04uNO+RPV8apLEsQ+24caxdwr0cLQ92t4S4fl0Op/NWQkpJQrA+xCIOQjL1eu7ZuEGEQ8eQlVAb9gb9E+Pn9979lSEu73O3p1Xtm+/sahKbVI0JolTW7p777331pe+EsfJcGtLJXFwlQQnHNAY7yyxwk4X6qadbpLRHDyIgFLIGJzVJgFEQtFJj5QmthBYCECYtM5n8/TyvHf9lmZp4x7bNzG9bF1HFJAAKxceILVBQvgLjoI1PAUBCdQVplQhaQASeimg9UqesY7FgiumIYrg+le77THLZw+y+IJIugbEom6HNgArtcOq3bXy2ymEFQXmhZyYXhBTVzqN9dy15ScjIiq1hiEToBBesdTxRRhX+2elgnXAgfm8nDfledPMLp69910Td+O09+5f//107/az73/n0UdPhuPJ9TcOzuyNLNobbO1Zz/bZ0TjONq5tjb5yfTTcHA/6WZacXB6el+cXErqggu5Z5PFonCR9z1TVLtZpFpkIERRc1lw0kGl0woOEmgA2CBAWTiZeEpT9Di8YbQPVAm0lANDrShBUBnYGcHNI00U4mmNRub/9ewkz3Ujxla7OHccKv/2xy2s17KBh/9zvn/vhrp690pejfHE5Wwz6qVb9G6/eyReLXrfz5KMPj+7e15FBxNA4MoYQmG1wDdrCaGXSBChWXkItNidXLMR71EaahpSC2LTvH2YWFleWiBS8a1mWgKh0HHV7AlJVFUjBghrQNXWzzFUUcfDlbEpaRVlXmH1dQfC+acQ7XyzY+ajb3drZ7/XHnrn2rkbQvQ4HDs4FV4dg2zMXkVo1K1GhCIJv36YCgav5+YOLY2sBxaQdBFxcLJaX58loMx1sJL1Rd7zlVJz2+or98wef7t56pXft+u7N20f3P6U0CfOaA5lUqThhH0jHwdfc1CpOQlMDqShKbVVoE7F3IAGVjrNudzBoLs8CB2USEnS2Dk1VXp7rrKPFBwirdutLvaWXFsuqbSTA6sqyhy+srCum2Vo9v5b1klkDmV7uIjEKAgSBAKxectatdmdGbFnsqxhLIL5iG7dLm6U9o6xWJvDKuA6I2NZaq2L7pTktISpQtJ7m0kvhCKtSmWjdMV5pMRRdyUKAieCztv+XwjwIA1BTh7qi2WG5vBQWjfHgl/+z/9vm57/07MHjH/2jv2urSmum69DZPMh2N+pCK3ZNCEZkfiTh5ph52WsapY2JTJpFI1QdDM999sR3rw2lZ5TCuJfFIUpJxIrkFiY1H+cBhUyK25kyCnIrhw0PNI0TQCssyIJ5YERwNYQgN6+jIkw03Nmmh+f+0wssHJxP3f/9b0Z7fTNv2BAmChJCF/jbn4Q4Mu0Zr5H00O1fU5NN7XJjQwCtTJUvB8PBcjZN4zgE1CYlDYQQQmD23laIQAZdmZuoS0mCEoBrJMIoDa7xTWF6G1CRAIsLSNjmvBIKaK0iQ1qFsmim57o3cFXBwZs4wb0bzadzDp7FKYEyXzoGFceABMHacinMvspDXYW69nXO1nUGG+Nr15JOrwm+qqqyLnWSksJ6emmLmUgAMqu0VFq/ruJAAosX9sLM3otYRcrEWoQ51NDO+pTmuqjAV8vL5fnz7mhz+86bvfFm1RTHTx/s3Lhlun1vKyIKwhicsA/eMjsQCN75chnhSJkoeC/CFEXCzMEFV+skBUStTSUiRME1cX+UTy8BxFWLZ3/6TzR4LwLC/CJYFdZgBgRgAkCWNvdNhABfCiJAuurfIpDGNm+sHZK2IettbM+L3FbmVdNLXmo4r5cuqfZ0vcZcaEASRYga1oWvICMTtghZIUABUQgKiFvAGqJaT4jVuuekeO3QARTVJmsRwUvJHWq9CbcyRyIkUut/JiHwqjGGVwLpK/QFMlN+adPQUzTvbI7f/Ob/4yu/9e89Pjz74//x/z178mnS60VZR0VpJaOLo8HrB3sf/OE/4LL0Kop6mV8U5XkEJv7g8XEuZnvcM0aCMpf1LCR2vDH+yjja6GZ7G2knoYXFLCOj4NHEX1Sw2dcGeJBipGHp5cfH/tzywSbcHMLA0NxJ6WGcqigOjZZIYdXA9bG8c522e1A09OEzOLrg//xX8FduRSFADvj+pd2O9ZdG+tsf55+eqF6G7eRAAR+561XyURfDoL48Pb2MDU7Oz6qiLotcGTPc3p3OcgnWNXXc6epIV3MITRN1h6yU+BqIMDCiaI2IJrjKl7lO+6B1q1IUDqR0AM+BUSlUikwUgnfL8/IkSrb2EZjSTm9jxxX55OGH5GNXlabbRURbLOPOkHSPg2sxjhRFdnLmq3ywcW1zb1+lmaC2vqmsY0Bnm2pywcEK8JqJSW24IbBAsMKO2QG0s8/2gKXWu45SpFclpEgIFdcNkoGmmOaXy7PD177xrVff/Yp4Pjs92d7cfmbisixIq+B9K1/35UIlnbjT5brkwDqOgAMHR6SDtSZJODhtEvbON43zlrQmpVWnh1otn91dHj4kCVq8lauF1A5ISHBNOVzzTQVXxGDVhq1CK6UhDVc6wZWCrG3eoshaR4UiwsICIsgMEJCZryiIQV44YpGE1sYgVIAOFCGjgIbWEEcIqIQQGJEImRAFFDN4YEDSCCQUAACYVsaEFfIOhJEUfZbU9mI6dNXTbst8aRt90h5s1/4IXJkNfmHyhCjDjT3meW8Ybdz+ws7Nb/yrf/g/5xcX+emzuDfaeutL8WA8O3rev3bz9S99+d4f/8Hk8YPeeJtBdJrqBiaHJ7tffkdhWdSLZWk2t6Jxb+PCLsG7a3t7v/dudFFlpPS4qxIHgvjg0tcBt3sIAk6gDmIB//xBczKTTsc8OvE7HbWVkoCcViEG7mXoLDSF1A3sjugsl/ef4ckcHh3yb77B/9df686qUAj8/Y/Pzxf1qG9Odjv/4j6aWAcvLEhKCMOl35qF/paajcIi6pIx0fWDg4ujo5989zuhqZUxJu2IxCzg6tLb0sSxig1pDABBkZhItKamUuJFhJ2rT55FaR+VXr2dOLCwUrHE6MqCnXVVyQhczDFKUJuoOxTlqulF/+BONb2sF5MoSnxdhrpSUcqBlSFXFzbPlVJcV76pe+Ot8e6eqJiUaYJ3WoOiUNngGhVFGlNnK2BEAmAnzrJ3wAE4ACFpLcKExMLCoe3NCgsCATOzW935Ube1WPCOkMSVd//iX9oy33/7S0nWzefztN+bXJ62YyrbFL3RpgQXmirq9E3W864Jtg7eEqKJu7aulA9A2pV5OhgFVzf5gkMwWY90IqSBhV2uo0yB0sAeggcOyF4CA/Pq2bcDHuBVmvmKvkJACpVuf5M2pI3SbWYUKtLrKJv2jAoSGEMADhK8BAfBYQgQPIQAHCB4YAYJwowcMHgIXsLq+YD4VeOaA0hY3Vl4NXkSCFcx0Gvef7uXr+rtVUOt7UmhtCiAdiKNL6EVZe3/YQQQYRHmwCwszCGEEAIHZm4/wFVoIbf1Agbb7L7xzvYrB8vlUbq9+9N//AfTR3ddtRDmjdfeYcTuaOvtb/3OqN/5yT/+e2f3Ph5sbAXmqDvodzqe3Wy6YFd2trpiC+f98fTS6wVGmw3sJD760gZ4laWRLhwum/DhSTgrZX+kIoWlh8NpuD/jZ1N+OgMO2DNweCShCa/v69wCCNzo092nblIrDNhUeJnzwzO4rGRh4Zde4f/u9ztawJH++x8cfng4G6UQy+McH21sn9+4FnQcewZbK0KpIdqg6bY+I6BG8AK6/dQkcfrRT75PUby7f3O2rJvSArC3llCiTkbGuGIJIkhggkOW1plsrbd1gaFWkVFJFziA9+AcgqAitrWvyzpf+KpA9iGfQ/CC6GzjFlPUKhpumqRTTS4IIOoN4m6fTIIiwVbeWrENEfmqjFQ02tkFQ2iUdba21jY1e8vBt6gN9g0EK75mW4qtAbh17OsoUVGmkw6hFmZCRFIoBNw2QfXKTtYuEGYSJKVJvLhaGWVM3FR+Ni+6/XGez7y3+fTCLiY6TtPxNoAiUsFaHSX1/Dw0dXAWEVWcmLQTbMO2Sbo9V5dx1iXE/OKIfaXTXjradHUVnNNRTCbW6AK3jeKXpqKywqnx1RBllbG6HpusppdK0yr2YqUBXDHx2qsCCAdgJ+36ZGk/BuCXpBPhKlbval9e/ZCgICghBhIglnaejAEUYWgDcZQgiChkQoJV7U1rFTQBEkkgABFq8+LbbGFmIlpX/rQ+4jK/wFzg6pTTrur1YaBFYdCqyXwl2hJXnzx9sPf5N5jS+ac/nj/4uekNADjd3Bns33z1a78SZ9mn3/nf7n37XzBLOhhLkO5g6Lx1CIF0nMTzo9PdVylXZWTicT9dlMtuZAMdNv7tCjsLi0sP88Y/X8i0kWsjlRgsHcyr8GzKxwvIHQw7kCk5nYu18KNHsLNtf/VOpJhihb/7jvm73w/TBaYjYk2GpD+Q69v4t95IWFEQmXt57OLYlXvEd653glaX9UXUs/23443t5MnDwckZKIfP/P4bclcjqsvDBWxMFSDC7vWDhx/97PNf+UYSPVkAiGcTp/X8Qqdx1O2wz9j5UEy9ieI4lXxOIEZjhTr4yhcL099EQDKKUZC9qgopc5MkQXrNxTFIENLN/NLWJUaxoC4vjtj7dLzT3zsoLk5UFDfLeWdrH1CIUlSqbir2TmnVH4wb55A9uuDaaSVqEQAfxNtgK3ZOOCCCIiSt23EAtEtUK0RhDqSIyACAKC8elEAQEdAAaIA5WGAPEigyDESCXOYc2Kp0nLzqqoK0IaW4qiB4UlpHaXF2aOI0ynrBWUTSJlFJGgTE+2Y5BURGSbOuqwoADsI6yQS8ilPrQ9Idlc4F63zTKED9i3E6q90V2+bAuse7YlG8UP8i4dq3CgIsbSkhIiIhCAcJHtgLOwgemVECMIvwy4DGf5OxbyUqlLXmsZ2dkrrKnQRCBGrTcX4xpG4VzEErTAVcGeAF2shmbqudIBxWT5oDM6/2cGZhD+w5eG4rAh/Y+9bqIcEDB+YAwMBt/RGshc2b271+efePvrM4XwRnm+V0560vfe1v/h+PHnz63j/4/zz+3p91NsYmzlxjdRx1+32KdBOkWSyDbZwLUScejsZ723pnJ3OWlpes4tEg20FbjXsdRipZKgeoVQCJDRzNQ17D6VJShb0YAODLtxQAFEC9kXp0zMU8fOWGXliYAN3aJUyD7uB4BNd38K09/NKejpDmli8d3lv4I452E9q0eUfrZiE78e1RNPZhqrOT8RCfHsZ1k1g7OYgeZIY08AI6z08WyK7T733ww+/u335TkCbnF4ASmjrUpbCnyLSFD6ECtjoy2NQoLCZuqsZXhVYQ90fAItZT1hER8Q61DoF9mZeTMynn7J13lXgXmtqXeTO9cEXevX4rHW34qgw+cF1F3aHpdk2n28yn7GoEFSstGNgFz4RxKgBKRaHOQ1Wxq4O3bGthVkRKG02GlEIJwp4UKa1RmG0lVypXBPEBtUalkWKldTveJ2GFKMDgvVYaOIi3yCJCptMdbe1enB0H5mY6dfmMgcX6qNdHUipOmQMp0xTz4L2OMxVFOk4Q0delQd0ZbwQI7L0tcwFIukMRck0d6srbJk5ThWReDu8QuTLTrJWA0o6b2/qTX3h9uEW3iYhwCO3BWALzaq0GaWvaEFa7r7TO9XUKAf6beOhtg6oFogIQtSdnVOuaHBWskrpXC3oNKqbPSpEFJLSURWFhFuD2qXrhIBI4+FW5y7z6DQGERQJwYM+rL1lVyZ458Oqe9MI3gYCBg47iuN+589brj3/yw+nzC3bOu/C1//N/ib3xx9/+I7+Yak3eis1zQVZaGaPi3lBl3fzstKnrqD+Mevu9ze2DnQEFjGlgdFiQ2Uiyz+9u9NN4bvmsECISlEhj4+A8FyLkAKhhNFQXS3k8kcMJ6JTKPBSl+uQIJuwhxakTreDmho4zuDGir19XB10lDEWQmcOZEyCcN4A6emuUHD+9/M5ffvCdP/0JWN2nrtAsHU2vD5J8qU6Ww0FUX9MTRXg+L49LJb7evLZ3970fgvCXf/WbDz76sFwsojSxVR2aOul22TsR8N5CcCqK0cSBAygVGtsUM8WVTjLKumQijBOwNTsrwbrphS3mzXJqp6fBViIcfGDnmB0i+nKGqLrX7ygTLY+eBFv3D+4kg6Evy9nDe4CQph2xDbAEADMYojARButcMWfv2NbiGxAm0kopRUSIwE4kACGRZu+Cd6hjlXbFB18VRArRQJQKKRYEESLSOtZaI6DWMRGxbdruhgQmExVNvXX9pjKmzpe+yu1y2iqs4sEmeycIcXfg6hKZTdoJzpLSHIKvSlTK1WVvMFZRVC8WtpgDUGf7Gipji0UIPs66riwUqegFIU1+Ib/jJd3TVbOq9bGtdq316ZcDMEsQZA8c2kW7Pq++3JH+q3HV8tm0rs9iqNr+k9KoDLUrlgyozxhrZSVVlFbK9BLkRl4onlpqzuoc6wGCMK931/Ze08Z/sTAgs4AA4/qZM4vnEFanXWF54RBEACAlwfpev98dDbtZ+uE//zbFRmtV5XmUdHZfe6Msq/zkmHS098Uv77z1TrFcBmdNb+Saulks2h+SjEZRb7fITRaShNNlMym8vjkYvrbZd6IR8edHoQk4t5LE2DTiPVQezpZgOng+8XtdGEbYibibYd/AOOL+kCaCj8+4ttKJaZBgbGgY40UtUytzD3nAM+sRIS/kZMIPS1TSDELxs4/u/Ys/+pP7j58K07sHX4jTGPrzWzuF4vHJpbsRP420LsvyZw/P9w72RuMh+/C9P/7DzmDTA83Pz01sfF37pm7nJYhK2PliqWwDKKi0eOedbcoSXY6A8cYuaY2C3tbgnbs4ttWyqQq7nIZ6CSEEDhJCG63W3qGb6YnpdFTSKU6eoDLDm6+CCNva5QsWqwC5bnSno3ojMgaEfTkP+RxEfLlgWwL7Vh6jWol7S0vWiUoyUISkBA3GGSCF4AkV6ogVBc+oENuWqlJESiGZpEtRpzPY0HHsmgaQEYSFlTaV86PrB/PLUx1Cfnmkkzi9dhtIqyQ2Sce7WpHyTYWAri4BMMq6wTkkEmYDlPUHRb4IdWlMlgzH3nsClOABJEpTBS0j6mriuhIPXOma2sdnlMAirfqqbQsJsCAzhFWd2XaYhBmvhHNrG81qjHSVSfmS3b4VObzk9mnFUoSkQGvShoxGncDKENdqEGl1WYuuWXnu4Qoei6v2FBAqXAcHgPCqN9xWCm2zjQOs5jqhPR2sA+dl1ZsSFnYcAki4YuO0zy94O+oNXnntzUXp99/4chA8e/xAQpmfnc4ffvyFX/mmIG3efvWb/9n/5eY7744Obly/c+fi8EhpUknGtU26nTKfi+dstCtpVs4nUpbHJ3k21rc3rw3jviYqg5zk4Fg2u3JzqDYz7CR0XsqkEAL/a6+a33szefuAhmPcHuH/4e1oc4eSPqaxGMKLS3lyys+nvqhFGJSGQsALOi9Fg/eP/cMzUYEYca6JbPH4458+O3m+nFZPj04fPT+51tvpDFXcgc/drn1v085mmZtnMT28qCiNx+PB9u61uz9/7/DRvTe//PXlbF5MJ1GaucZR2wr0YvNlWM6kKbU27AMYLdYH2/h6Sex0koYiD7YChXY+rS4OfV1Ui4nNZ+JqbuG3K+aJAAQAAfbV2SEo7YtFlPX7+3eqyQUgkNIYfLOYq0hTd6CijIjq5QKrJYF3xTzYmgMrE5kkVsDCAYC1VmRi1DEqjSZCFeso02k3yno67uru0HT6AgRthImOlFKkDEZxpIxJUyHNAtl4m7SuqlKZCCQgKFvX3e39NOuIa5Znh2S07gx12qG1CL+cHEWdLipjkq7SSqddCQEQhD1bN9jaCbap8oXu9JSOmqLg4IWdbyquK4U6g1YJvH5nw5V4eM1tkDVeQtap6Fd+9ra9LJ8psD8Titk2nEXROpOSEBSAbt000CofSCORrP5GoVKrklgjaoXKoFKgFJJBpYjWMSWrwCsACK1bUARBWJzl0EiwIqHtIwmIrFUfgCyrcn1tKZRVMEjbSpZWCXZVJ7fXclhX0e1xgVtOFQKT4G/92jfzyeXl8xNB/fY3vnn35+/7fBbqmbfNvR/++Ot/82/tf+mrP/qDP/zwn/795z/+k5tvv37t81999snHaRLVda3SuFkswfNg/+bmRn/ATnHe2Y5Y9w31e2l/M9MM8HQi2wO8MaSRwUjD2YIjI185gL/xZvrqWDuByvHCgUI6L/lJIUXlexHsJf71Lbk9Bk1UOnx0Kvee86MzeX7OJxcyLXFRYtPgvAQXGOPouC4++tH3DE69h3LZPD98/vG9RzcG+8MdPQkT1YNZ2l2EdIz+4Sf3bNx77c3XojTdvXbw8U9/4Ky9/tpb+WJBWoNAnS8lOB1H4m0oc24KAgFS3nn2Dry3ZQ7eSl2IdxBcsHV1eeqX86Ys6mIuzjELUaTjbtTp6bSn4g4oDUEARbxtphdESkDq5Sw01fLomZ2fs60JAKMYopgIgm2gypXYZj71TQmIJk61SYCDuAalTaVkZgneB+t9YFARaB042Kph1DpJOASVZFHWbSHfpLU2hgA4cNzthSBCZJ3v72zHcafMZyQg4hCUTrON6wfF5LzOl5T2dKdvOgNh34La7XJmsoErc1/nUacvLL6pfF22KvwkyxprGZVShr0jomp2bpI0iuPlxYmiuHtl7F5thitOE73g+67Oiutl3EauXhljkf5K5uQ6d+6FZIpW1gJp++atxHcFNFxbbTSiQaVBKSSNOkJt2nRdbK1wytAVOEZeMgC1ji1h8UFcw74WZyVYYSfMrWyEgFcuHXjpVCrygqOzulkpRBRB4TWSg7E99rb1f3vGFea2+m7q+s3XXu1H0f27H3GxfOeXfvloWR3evUvM9XSiu1vf+i/+q+GtO//0v//vTj/4oSung3GWF9M3v/DFZ/ce5NPLwEKKysuLvc+/s//a/vzxx9PDZ2jAUT27tA+eNDd2b7y+rSc1X5aglZCCLKG85iSSL16Lbo8MAtQMTZBY0ZMifGGkMoXPcvd0ms8evX8n1RHAhvbvbJuDTrWdVa9v62EECLSsVGU5MhgZ7HShk1FTcpzFe6935iePIu1JiV+42cXsZ+99uD/a2d3pHy6fcFbSeOO8yZrp8uGjR3GSmSgyWdcQ/uz7f/7q2+8Mt69dHj6LNIamWJ6d+KZw5bLO53W1LJdL8RyCLyaX9WJS17WrS5svq/llPZ+Vk0tbLXyZ26oU7zgwaaNMSqQFiIGkhby3USxAEgI7RuFqMQm25qogECQmZXS3H/XGwuyXM3SVW0xcXZE2Jk1VZNjVUlUovi21AiOLAVBCCpRBbZA0au2bslXCqSgmHaHRAJj2x0lvIN5pUrrTtS4EEZ3EIXDVNKNrN32Ze1uhNqozcELZaMs2VXF5wprQJKTjqNsLdUkgtshJKRDUSRYaq+MkeCvt4R8gONfUlYpiFSWuKpSmKO02VWnSNE4SrXTU7j4IIMirCGTxyEyrvlTbnH0J10j42aStz+bbvthj6UUSjyC2mxSgCCOgsCCh0FWErFoFpbelr1KwJvyDIlQKUAMgM19hWYHbMwZLWzWJrJq9gSUEkiAKRHs0HtiAxCiitBFaWYp4dd5eu4Daf6kwiAL4TKZIWzuvm1WySsAGQUES2eh0vvOv/miwMz69nNhQ7r352iu//Pbh94rZExrs7O6/+uqf/b3/0c4v4k5KyoRsM+j+dNmU0zlpAYTq8mJre2fr5ljUOcvzyaKc5kV/txONx8ibjfVFoxJFncRv9EgROs/drtruoEEonZw2rBCuJcoDIOLPJ/71obZCh0WF5fMHy6cHvVvzBprlLrl0O9ajLLw99M9mxXFfFjJ6NNeXVbCBRhkNIyyazMkrv/F/+lt/8b/+L0iHWYfO7s0xav7su3/G4avbtw5cV58sfxJlO2/8+79z47L8s3/+B6fPn33lN37dWxeR/uC7f/yN3/39reu702ePXbl8+ytfvfnabY2+G0eGUGO8KMqyLBUSYZhVfrK0isRWyyqfLy/P5sfPFlXFgkgmSiKVJAQ6OIciIdiWFISISmcMFsgTqfaAxk1tVIwcIFArAyKjm2KBruZ82iynlGQqyYxRrm7EWkUISKIS0UncHcb9DetsCAGVVlEEICwSDxQIirBrciKTjjY6o+3i/BicG2zuWOes83EsTWNFKwXa13ldFOl4u2lqVBDKJYtuiuVgY3zCLEhRpw/CZGLSppmdRd2+q2pSJu5vVPML35RKaTEJsDBi453WGkhcuagmp6HX27j5Ztrrnz/5dDDoKZUO4YUWF6/IZiCrbu8LoASuZrJroyy8EBKtGWjw0nd6IdDHdoYEwkDtPUF45Z0zaiVaJk2qLYzbLnE7ByZqZYzUWvleypVvT6QszGG1dL0Xb8E58E6CRbYrkUbwrRoCV0G2q5vJizT3q5SotuNPuuUaI6563W193Co9ryyKiOhD2NoYDRPz9P6nJta2KJ48eJTub5oun/zkA1vVjv3dH/24OD+O0iTqDUyvz5R++Vv/3tEn9+7/6HveeVLaN350Y3/31uby+CGCjdWYKyo4xmzM8Or1UeimqhubyvHHZzxZ+i/fMlpjiuQEFk5Oa5l66UdYWeknaqdDBvkvnpeLKigVuaKcl/XE25PF4dHJ+WRiF3k5y0MTMIHmVscdDMMwTax1xdLVjAS4nCXkOoPk/PDTnycZELo3vnn95Nnp+z/8dJxufOsL775y7cb2djruRlvX3sjjwez5cRRFCDg9uTg+eqxI6yAP3//Jrc+988Vf/Q1GAFQb23uDa7fi0VZtkt7O7u7BLT0YmcFWZ2tv4+arW6++Pb555+2vf3O8f6ubdiU4E8Xd4SiKU+e8SdNv/Na//xt//fdf+8KXrr/y1ue/9itf/2u/vffqG53RRtztZb3B3s1bu9f2h8OhiaN+f5B1ekYbqatmdhnqpVtOQbyKY9KZOBuaWpgFFFOkuhvJYFtFXdFxPNjsbB50tg/QdNo7OGqDEoK3ZCLfFK5YsufrN28Swnx62dnYpjhryjLOelonHJhIhdDEWaecXQJbJKXijhfY2BidPnmosk7cHwX2oalQoFlMdNKNeuN4MG4juaMktU2ljFFacwhsrTaGg7flwhWz4OomL3du3iDxl4dPWwMtA3Cb/SEswEKCgshq5chZk2JoHQ25Bghj240S/IXMnnWC1boBS4Bhzae4auQgqCtcI6JSv+AZakXkCAioZOXD55XrHqSFaLZ0TGGWECA49Fba9nVrjgQC9ugZRLhdfiiKgEWv1RFrLiSRMhFqUjoiMmtCMjN7Dk4RMwBxm+wCK5gHCyAMu9np8yeuKS8vLjtp9vTHP937jTvXPr+7/YV3z59fuKogOAIVE7Hpj+Pe6Jf/2m9Nj56//yd/lHQzHUeCMLzzan/XVGcPLg8n3c7OuLPh/VyA6qmSOH54ePeNa29vZFQFdX/ifum2jgwtG2lQCKHtmBWWmwCjFB5cNB+dwc+Owk9//Ke3vv6FxTQ8vjfLT0+Cq7rb2d6bm83hR0k8GB9sxN3NzmD3hqZt4w/S2Vt31KSAqY4/PJXDXD2/m/3S5/7jXvZeUT2gNIhqvG3iaOPzb7017I6rqg6LxiS2gfPRzm71hS9NTp4++ejDyfEh59XHf/4nYvn6G6997hu/8vzk0CjdFPnkcqrjJCEzmc96vd5T56um7o6GDHB+cspIW9cOsr1r1199bdRNfvtv/I2mrp8dH3sXFIP3vtfvbl+/0dsYeYbpdPaT7//gjc99/cu/8x8RYlPb+eSSg9MI+eV50+TB4cXpyWI27UX6/HneBK90jEDc5MFaE3UGu/tJf+yVAW0YjGtCEO/qcnF2lI12upv7yWDgq3mzXHpBdI6d0yYCgIjC0w9/uv/2ux2gi6ePs9G2SjpNmaf9cWxia3PtLCAlnWE9eYbaQHD1/PLyOEFA3zjf1MJMaYQI6XA3cAAA9l5YdBS7uqIVEBxJaUGoq1wBQAiDa7fjXm9+9OzxD7976513lrMNRXFfBAACthOcVcQUSztQfan5BKhkbTi8Os7KS+CWq8nNuqW0yo5cmW/k5aRpEiQgtYqYbOeuL4UHtWY5WFkGV2sQ26fEvJ6m+lbbKK3g0fP6U7wGuK6FFdy2mVqxxZXdAVERKSTSKk50FOs4NlGqTBTFMZkVVIaQ6Or4TbQybxEBURwnt/b3T58+mk4u9m7cGHS6xTLvbG5Ksqmya7bm6uzI25qUcVWTdft//W//nQd37/7g//ePssG4u3d9cHBn/wtfe+Xzr75+bVDOT01PK9ysazcvqunFWdx5C1yh9LNbewe3NzLnBVR4dTf6cBacYEwYEdQBgkAnJqnD//ax/Qd/wT89DHOfgOjZyYOt2wfC8PBP/2h59NgHtZzU81lV+gsX+6Pjw0lxPqnLo3xa+jIFaJq8q5ov73Wu9/naVkg74/z0aV082xrv8Mng2o2vfvFXf3u8t/fjp5OpCx6zmoaPF843pe2Nulny6C//5OEnH0QkBC5O09/7O//5smms5/npaYRy/eatOO08fXjfINx+7fW0P6Css7F9rapq0nT8+NHTux+WTb11/XrUHTyZzBs0Encu8qKpq2F/YBn/6J/8f2sX8iAe1ScfvH/v04/Pzyd541yc6k7/8fGxHg5f+/wX77z2+sbe9de/9LW02z19/GDv4GbU6bjATVEj6mtvvfuF3/wP7nzt1/o33tDDcbFY5tMLb0sk6m7tC0h+8thWc5N108FQRcZ0B+lgpKNYgkeQrDvsdPrHD+4OD+7o7nB+cmiyDmgDwWWDIQXQkUEUZG/zmQDqbEhKp3GSzy51bxD1R3YxRVIUxRycrwrUEQCI96bTFRBf5Eob0kbEi3fsGpbQ27je271t4u5wc/Ps0afWur3XXle6M4LVSLIV4MpKE7WSRK3cbIK0RjrQS+QmvCJFALVhVnpda9Pa77YKjV3l7LVXkkZFoBQqswrL+Yyfft3wWo1y29lMAPHAfpVxIqEd2LRDJmEPzCjSBnB+Jjt67QoEIWk33bZIVkSkkDRFsdKRioyKojjOoiSJklQZrZRawTLacpkUKaOMIWOUMYI0Go+2hoNPP3hfKbrz6iuffvihyrq/8l/8N/07r5huFQ9eKU/PipOnvnEakSQ8+ujnTz/+CL1jEYV47a3Pb7717m7XbafN2fxkMU/zSg4Pj731d27sXxzP2R+L4c3xaKs3NCbc2NQ5Y2CYWGHAVGNPYwD5i/vuX94Pn56ruqBuRw1HEne362o8e360884b1975Ivowefzx+YfvE8Yg3aP3Htgnl2nln35w7/jZ6dnzo0pr0zGRqjaTqAeLragZhrPGLbF77atf/w9+/ff+k9HbX9o4uJXFMY42a508n0x91qO024/UzrCz342/8Pqd17789Xd/9Te+8LVffveXv/ng3idA9PTBwyzLtm/dDiYu6vLs8jLudA9u3TG9/snZ2Twvzi/OmqYeX7vuPefFglH3R+OLxXxZFIIqybplXTx89GSpTG9j88njx5sHN9Ph+PU33l5MJrPLi0VVTeeLKDKbu3sf/uC7RuHerVemi2mUptvXrj18/+ePPr178Oob2we3dNxJOoPe5ubk9OTxBz+7PD1JBhumO7LegYTFyfP50aO4008GG6jAVUvfNP2dffZOGx3pKO30JXA+nXY3r1GSXRw9jdNuurHj6sokaTk7j5NOf2fPNpYU2WLhihkHr7O+UibtdJYXp6rXj3ujenZukgyVscu5MjGZxKSpcNBpGnd6vpi7MlcmCrZuc3d9XaBKCEwzn6VZ7OuqLstMgeru3r5CRLQTyauW02ro2XKelFqtw5VLdpWI0foHgHTrem8BLSvREinEdo9q92YCQmwdfIpQG1IajSJaWe3+dYHS6yHM+k+ro+l68AKrFRsgBAntRh5eirq+mtz6NgVkVSOv62EdRWSMNpE2kY6MjuIoTkycxnEaxRHploXBgEREymhljDZGGaOMIdLdTmd6djg7Ox4NR1VTnxwf1bNJaWVwa3fzdpeDAb219foXdt/6Qnl2ePHww9nzRygeSaW9QdrpdOJkv6/vbPfu/vyjT352f3bJLLKxf+s3fvPXn35099HH7/U2h9loa2d3cGM0HCUKEbMIxwkRgmMYRGQF/vKhff8QkkxhAOckeKxrJOUQ0rrcLae5Mm7/q18d3nytvjh//v0/nj95wIuFzedH959cPjmaH59VJR9P66Pz/Pnz07OzyXLRYFP3s7Rk88MffKziTtQbnNVMTXm+WF4en8RaLc+Om6I42B0ni8u3+lF1fvqTH/2gsdX163tc13c/fP/8/FyZqHBEBF1QAAAftUlEQVTc395+fnY2mc0uz863xhvjjU1blcbEs7JcFjlpbW0TdXoQxy4vkMPm7l4I7IIEkTiOmiCUpOxD2s1iE/m6fP3tz58fn9753BdN0p2eH4WibIrlxnDrzmtv/OU/+yf5dKrjpD8cl8v59u7O4ZP7VeW2D27tvPLm6Obt07OzsrHeNfPzo+V0lm1sqigJLgy2r/kmXxw/j5K4v73vqsoVCwbujrc5ePChLnMEctYW+SLujADR1pWOTDbeCbZx1dJWy6g/iuMOkKBvbDEVAWWiSJksjZfzqSiFZEAEtSalfVmoOBNmQHJVoeOE2fsib9+t3jodpxTFyqRxNgBQyhgyanZ6HCXR7PCx2rzxOq+qTRH2EMLK43oFgVDtzDZqt892VgNIq6YRKSJ11aOSdR/qigu1WufQbtRtAjoBadSatEGl2woU/0qqCIAAy6pxtAa9vcjIFWnHshDaTbj9GFbB0LgKhX9BvGjlF8jSaqiUUpGhONYmUlGso0hro7TRxkRRaqLoqgMuIoSgSKlodUHbrFJaaa2UhGp6DkB1XYCvnW3qy7PJs4eDTbtxY7O3/fqtX/rN8etvN5511Bm/9jlSqUoiW9cskiRJXVdP7j/6zr/6ftBjlQ73PveF/Vde+el3/pKtj3pZ7V1Z1W+8sr3Z37os4HjJd4/cPOdOjIMUNcIffGBPK0pTnC9YhLQBbyXrSNLB4EWATZSxjRYnp6NXbtz51u9GcTZ/+FHwTV5UQpAkpp6f58dPgq2ZkmnuHz05OTw5a5Dml5dPT06g259ezHAx4To/PzquF4u6WNRN8847n5sfP8vPzz/9yY//8T/9wzhNv/PtP37/pz9XOooT84M/+3Z3tHFyfjkaj0GkyAsl8OYbb+7v7h8/eZTX9dnJ6eXZMaUJA3AQVMpXVbWcN8vptYObSbfvnY20ccxpmpng6suL119/CzjMLy9H27sq7Tz85KO4093eP2im08vj50dPH6XdQafbe//7f3ly9KyztaO6/WVVi7PXb72SXNs/KxqbZNnGbtTtp4NRd2fPVuX8+GnWHbiq1MZ0Rtvimmp+LhK6g5EP3haL0NS9wbZ1TQihWczjTqqiGJURQJ3o5emJ0iru9RGkXs6Vpt5o5J0zBPXkLHiPptMfbQTnyrKIeiMQNp1e1B2y98ABSAXbqCgmAiBSScq2BkS2tQiTiYRDaGza39AmBmGXT/Ozx+xrX0zVeO8173xwlr1ntm31uDKe0qpT3OZ6EBGRotUI50qcvxqhINFLPre2Wn45n64VGNEqyKrdt1et2hXCbT0+opd7WisZx1UmAKxPpbJawVfTKFxx6BBQodB6ktx+e71O62t1U4TakImVMTrKdNZRxhC14SKoTQQgwBCCD+yBWaHSUWxMFEVGGa20UUoppUkpYj87PU6iOEuTxXxKSoWmXD57evzh3dnTe7PDexdPng43osHNrZ2vf2v06pe6ezey0Y5O+6Obb0Sj3dr0D48me1/4pTvf+mv7776O2Pz0n/3Bs59+sLO3t3nrpknjprHaRFFndDQzdYDvP5I//UjunvKy8j8/De89RiGcLThKqKl4fgEiaBLhAESU9DCKpVxG3g7yk9MiP977td/ZuPPG8uQ5u8rbxtoa2Ie6bpYLu5xH4ly+mFlve1uPzybH01nUHbrJKTYFVPlHP/g+1kUf3fknH7vL8wfvvz85PQkqOZ9Od64fdLLsyaefFs43Zfn404/BJBx3Lk6OBFUyGvWyLE6zZ5/ef/70kRkMl0Uxn01CUaaDfmDudXvEMjl8WlycFLPp7sFNjGLnmq4xN/b2t0YbJ48fZv1xWdaCoHSso7hcLA7vfTToDZjg+MkjDs4JzMtc62g+u5zXVd7486J68uDexz/63tbtV3s7e3Xtxxubvc5oOZvk5+dZb+yqcn74pDMaldNzZbSOEwVSL6dAOLy2b6u8mk11NqSo46si2KqpCx2lKxyoBBNFti5MmkZp5m0j7OM0a+rGEJanz4J1Ku0Oxpvz+QyiGIi4KYG0SlIk7Yqlb2qdpO37VsUJhODyBdtaWDi4dpsQDnF3iGSCtcXpI1fNgYXrQunelmuqYBvvnLADeYkmfAWRuFI4tWKgdmCzTpJcSTBaKTK8hAp/EQ6yioRt1x4BtQlZ6yK2hdKJMH8GR36FYnohX7pKA1vri1nWW+4qdGudQIKiEFADXHkHaSXAam9DyqCKlUnjbrc7HA2HG6PRxnC8GSeJZ+ettbb21gbvVzt7Ky9XtIr7olbeo9Dbi8PnWdpBonwx1SZ2zgJIs7SLJ9P86Hh5+gzj7o3be4NBQxw6OzoejTdffdV0KOp3s1Gy+9rNm1+6rvx702f3Hn/nx9OHD41RR4cndePG2zvBcdmgoKDZntSS13BnVzHApyf49AKNATKCGrwVWyKB7o+wqaDMUZDTDtQFuAado0j3/6vf2+jF/rK7t/flX7fLy/zsWEXGLucEiqKkqcr87KSaXfim4eAmjz69fPq4djJbLDzo5Xw+nc2y3vDycvL+hx/P8+LJ42f7Nw46o/F4Y/vg+vVP33/vgx/9gIw5fvpkdn6ysX+wdeNOMt4MIlWetwqV6clxXS4dIIcQmqq8PHbOb+/f7GSdxlq7nPm6rq29nM9ARYPRWCM1zjnvy7qazadRr8teesORqxvSJkpTk3V6o20lcPn0oSuXo2t7RWMFKev0bVluDIaxs8/f/5Exye61gxhVqCwoE3yIk+T00b10uKmiqFkssuHm8uIkTjtsa1LobM3MaX/snAss6WA7ONeq0l2dI4FSmnREJkIEm8/S7jDOOouzQxNnogyxry8PmaE72lZKzU+PSKtkY5sBSJnQ1L5cinhEJG0AwdcVkgIWQvDOIofgGZRCCcii4owFjDbV5VNfLoAhjhIVdGzrytt6lW7UplnhFUP8xVlXOIh4YQ/i29W7cp4LC3uRsHK9rRJs1zBHXgtIr8LYW/7Mev23OmBh/ius81VmPH/GVHCl5lh53tvCmVpaIq24xKgIUCEpUhpQA2lQ1CpqiHBl4jdRlHa7o63tvf0bN27fvHlrY3sbjWqaqsrzqihcUwfvWufSSrC5chBI8CEwEykIfn5x6rwLQQiYiJyrhH2rpra5s4tycTarGnKWuG6E4s4wi5PZ5n7UHyfj6wuDjx9+9zvP33tw9v7xsx/fG/R6ujc0Wacu6nyxNFnaVC7NTNbZYol9gH4HbAMNY5xSkonSqDwNE9kYzV/fLjrGRh2OO2BSBQFmF8iuFVXzf/lrnd++0d0y/rGNdr/6Ta316d1PuC5RkZABCehdXeRNuVSKmnxZnB+iMaNbb54/e1qfX+TLWbffU8LTi/PhoHfy+MlserlzcOPZ8fFiPo98/dFPfxxAbJWHpr711hfTjZ2Li4lzVitVnJ5mJgbg+eTCGCNCzezCzs7qs1Nq6l/6zd8NdbM4P9NZN9vcts66uh6ONgX0dDlvXLOczpiIdIRKBed1nB4/up/E2eG9T67dvLN/53Wj8flHPwdrtw4OyskZWrsx3Bp1ujI/f/rpJ5s3XgUdT6ez88Pn2XBIOtZxp7dzfXF2qqJExan3oTMYcbDBW+9qAKmXC4riKO02+UJFUdIfizAR2WIK4nXSIR3pJFHG+KYOLEmn6+pCUCllgnXlxTGiHu3szc+PXF2rrOOKPNiGlEKFIOCrikIIZS7MutMbbl3Lsl53vK2ULmYXpDWCBGcBIEp6Ju0orevpCQhEadeYSOnOCJiFA6HACm76oipdbZKyDnFvpbwMqyZta4UJLOwBQitPaTdGbLV+3Moqrrw+n4m1XVW53J5LBf819lp5AUO/svOtnEYMgQECCCOvGchKg1KgCJRGrVEbNAaNAUWodNsDAGUQFZAiY5LuaLC5u7m1u7W1PegPmDkvqmJZVPmiKQpbW2BmZmk9TMwheO+99877EJhFRAFU+ZydFQ4KlSKq6wYBhIMIt+g431SX9z959pP38mnlKq6W9fKinp83y2l5+tGjo588fPbdp/n9cnE8EwTHqNPe1t5O8CHt9zv9sWPXH6bdNB31xnEcmoB5CaVDE0N/TE2NGTQ7o6N446dxei/pNTSYp93KOh2pJMokOKhKHKX8n35dK5A7o/TL29GjmuXON3o9dtX9wU4n6cZ2aYNlQIyyFLkGwN612/tf/xaHcPTDP3PFDDmcX54NhoNlXiWRmR0/P3z6VJKkrKvT0/Neqh5+8DPUyN4ZE2+/8vrCumoxL0+eN5cXFOzi8iKfXqJvkm7fREkzuWjOj9A3y8l0e//G7be/ePenP6wbq5M46fSa5Vy0ZmXqupyfHk2ePuh3u2dPHzfFot/tXb9x+/2/+PZ4c2t5fnT0+F7SGxy89WVD9OC9H6D3rfl5uLU73Nw+evJgNjnFJFVxj4OfnDzXygy2rx/e/zi/PL/2ua/bqnJ1CSAheAlBRXExOUUQQeJg2XOUdrxvdJKiJrZNaCpBMZ0+oiaFOolcPndVoZJMx0lT5ByCIpWfH/fHI66r+dkxEYGwq0sVx7aulImRTCiXoS5Mf8jOxp2eSTr1dFIuluyaplioKAZU4AIZQ2mmyATnXTn3ZR6bKLCo7nAPEUgppbXShpSStiG8zpJdnUVX3MKwzoJu1xtfuWqBadV2bq0/L3x8axLGFW1pJW9cRQF8tl98BY96+WCL8AKA2O6s6xtBq1kKAK2jQEdoYiDdeiNJKVCKtCaKUGnSCnUEJkIdoYpUFMX9Xmc47A1GWa+LRIsyn8ymi+mkWsybovKuYQkrcx6zd85b56z11nLwErx3tsWOsKtCU4uANto5J8xIASRwsBIYRSsSJXb68OOzDz/KT6f586PH3/n22Y9+cPz9D07eu3v56LEPTW9n99rrb9aOCfjy5DjudqOsW8zL2OgoThznO+NYqe60gYuFiICOUFgWF76HRzJ8kmSDs0l6dlyPo+39LBnF2sUxRPraNiSpfOOG/NbrmVLkAw8MvDHSf/7otP/WnWvXe6F+vPfmYPp8mS8qk0TAnqJo9Oo7t3/r94f7tz/9g3+QHz2qqkVZVgJIOuoN+k2VT46fOuGkPwDh+WwBrj65/zNXTEO9EF97MrUHBLYXR3Z+6aoSnHNN6ZsKEJVJAMBXc29rnfQ5jm9//kuzfH5+etTki8REnd6Qg48pSkmZYKvTYy3k8vzy8JmJov3X3jp9ej+fT67tX3/88580zqLpbOztXp48K5bz4JwPbnp+0htu9oej46ePTLeXdAZJkp49+bQs88HuDUF6/v4Pm6rYuP354H0zv0AkE8U6Tp2tg6+10QLsqqUIEBoTxyDKVaVJM5dPUWkdJaS0iow4X+fzEAKRAlKhaaK0K7bmplheHJOJxEQCYrpDH0KU9USCrwsSwCghpFBVJuuwsC3mwTfVcgocTNZrAcjMoTvaygYbvY3t4fb29PE9Y7SwqHi4CYCklGonH9ogqSusDCpFxigTtXB0QbVOl1u7z2GlXQD5t+bI48uBl59Zji/qZuSryz6TxAW44jziSiCMq1iDFbQKtaY0jnqjZLgZ9fom66EyIiioQAEprciQikBppSMyidIRmUjFMUVEkSatGEJZlJPzy8uz48XktFzObV0LM5IgUEvmCN4zBw4+eM/sg/feNa4pI6WCs8E5FkFAo41zFjGsMhAE2De+qVEo63UjE/ui9MupXxz52TmHyoaqs7Ud9YYN0423vljWdbmYgai0NwiNL+cLZ5u8qOoqbPUwTkfnRVTXkHSwKaSYI4dw+2aqxnyZ87Xa1M8mQ4wUdk7OJ52wSGIcd6MzwOGWMlhVvnQee7H5+ZPwh+8/i7tVpuvjD3+0PKpO7x6z84ptb+9mf+/VnXd/pVnO3/97/6/J/Y+M1qEp2DcY/OTJB+f3fzY9fGjLHIIN3iZp11Uhv3yenz9bnXe8TQZbOurWl+dga9SgTQyI7J0E29ZnmoTrhSuXJu1LHHMcU7dfLKZuuVwePikvztIovv3a23t33synF5PDRwevveVYqrJ0zm0f3Kjy4ujh3b3bry8vL4vpRWc87o3HF8fP2uwHUopFhNTW9YMin7sQ+uNtNNH84tTWDcWpijPbFMuzI99U/eu3EdmXuWsaHcVJr+/ZC2HUGbT+EGZHyiSdLiCyqxSZ4BoEMVmXkNh5cRYJOYCOY9+4KOtXs7Pi9LlSIEkGcYZa67QbvEfCqDN0y4XLlyrJ2FqVJCIcXG0XZ66uVJRG/REgiLMiHrQyUZL1Bq6ue1vbvV53dvSUdKQw6QMq0kRaK2WI1BpHjlrHJk7iTjfL+nGamSQhrYEIVyo/QG4BEvSSiR0B6AVVYi3rXRPWXjK4rwpmfCk9U14CtV0FPrfda4KrmNkrpExrRyKkOI26/WQ4Tkab3Y3tbDhSUYJKCwuHVr/Y3mQ0KU3KoDYUxSqKCE1woVjMpyfHhw/unzx+PD05qRYTX1cCQkRaRWu6wdpS3B7sQwjesbNcNyiCgTk4UiQAWadTVdXKKr+CpAMCBFfbuhRnAQUVaq0RI+cCC6fD3cH2DRvYMV47uLlYLJTWrm6cD9ropD/Mhlt2uXz++Nnu9XGUbATCEKRYgneAsQHXJP6u2mgmh89/8j/9o/Oj096gux3jrSi4i2Mt1c3NrLDuw/nFe/PT59Z/eDn9n9+7aNTZ/vbH/uST4lmJZ/rR+x9zXYrAta/9Vm//djO/+PSf/t385Emcdrgpmtkh1wtfTNjWLfFDQgOhsYuLxaJQca+8eOKq5fqlURu3vyyouC7YOkRFSq8YutwAIAsKe5svnGvIJKbTD5T0RhvV5Vl+fuzKua2Wy9n87OxkWRSLy8n07LlHM9je72/tOi9BRcV8Nj1+7nVkTHT26B7oJBnvzi7Oy3zqG8stHIUMJD0VZ/PZNKBxQouT5wKBAwNScN7XtatyX+aDnWtaG1suy/kk7o1M2m3KuXCIu132HhHEu7jXN2m3XsyyzS1S2tclcCCtlUlcXQTvgNAkvWC90aaannC1QB2BiQUEkNhZUip43yzOQ1UoEysdoTJplrCIZ0toot7IJJm3TZNPXLVkaxGJnXNV0xTLxcV5nGTVxXlgVqJS5rAyv5NqI5ZBSOkoSpOs28u6/bTbTTvdKMlI6TZJr8UX04uUyJYY3OK7r/D7679fC/3pyrT6kv92neK1aizBS07Xq4X+UkoPwVXkHq0DY3USZd2oN4y7w6w7NHEGCMISGs+uEWslWBFeBcyT1jpSJialCZHZ+aquFvNqPqmKeWgaZo+EREprpXVESqnWwSuIAIGDBGbn2NlgG99U4J1CUloLUvBeEaGAd4GAADWRJlS4RsH7ULumsnVdFUVTVQECGkVxB+NeYBFkRRp15NmDoDKRTmJtMmUM+vr4ydOqydNu38SbkZHKQhSjraVyyhcc6UXYzKaL2dPvff/+j3+IiwtflhdHz+LAzfnRK2nY1Zg5Nc6i02oWDX/a7T3coPHJe0/9U3l299OLs0Nhbzq9wSuf23rji7PHn1x+8mMVJd56l19IaK4qJiRSUSrers4sHECldnoo7NuXSSXddGOvt7mto7TMFwIkgiF4Zi/AQUSAgg+2zNkHnfZIx8uz44NXP1fMp8V87l0TgietHct8Ms0nlwCYbWy7ACfPnswvT4VMPp+V86kPgCYppmdVUZrBZjGf17Nz39SBAwuqKK3r2gVg75rGI6ri8liYkXSwNZJuhx2uWpaXJ+mg7+pGK23rojsaCSB4JyImThCEOYCATlMVxeI8ArFvOHgkFC8cgjK6yecq6SGCNlE9u/DljCIDOm6rD2ViEVFJBt6DsI5SXzdaK1svnWu0ybL+FgdfTE68zYWZtGnbTBIkOEcUKdLsbDO9EPEKddQGcIAwtwR/AKWItFZREidpFMc60lqtlLfeh1XIPIerUrZdsW1nFqEFm6+pFGuDAcLVLro+Cb/QAbftpc80oF6um9srW+4EXtkFARBlJTLUaZxmUZYakyAqb61rKlcXbAv2deucRGBZWZUEhEVgpcUSadEziAiqPd4bIo1atSSAlcCZmVlEAocgIYjz7Gp2dXCNUkab2CutAZvlQhnlvF0NwBCZ22pDtfMmUhGRUVFESYwm1umgv3OdklRHUfCuWCyz3kC0Qa2VUgq1LfPQ5L1Okk8vrQuvXB+MxsNllXaHEhCCRSSy6trlke11D/fefY0z9cEf/vNPfvLJ0eHhJx9+0k1jbuqmyOfTaTVbHn3y6FYv5vJC1VHxUXP0k+PlZPbBz37EXpBMaGpu6tnje89/8CcI5J3nULHNV3y/F3dYBS+gf55dwa68+rzJemgSFWWjvVtRd9CUBfsmeNtaPtbEW2TvQwidwUZVLKvLc4hSint1Ubu69q4WERVnUXfDNWU9v9RxWlaFzS99WQlF3rtqdg7AOu571zT5edQdMUM9uwzOESlhAKU5cDm/9L4B1ICmWpyJiNaRqxcCCBwIyZYLDk09P08H46bISVkQSbOhqysF4ryLuz1gdrYhE5HSdT5TaAAh2Ia0Jk22WPqmEvY6ygAgThI7O3flguIktGkzDCKgs1SZJJRLt5yTVhw8IILWUWegk8wuptX8DI0mpZU2Aky+AREARVFkooSFtYLi8tDZSpnOUKkIVTsSWRng274woQAyB8fOBe9DcMG5YBv2jQSPEtZq+lbO2CrsaX14pfW2KFciixdaRqQrj/3agrDqDLflpFrF7l1lP6/y8l4kzbbfs71eBIhIR9rEWkeAEmzj68rXObsKQmgVmO3tA19EvAswcwgtKhmlVY9Qu2h1HJOi9svWs6UA0DIlA7JI8OBda/3ThHGnE2WZOCfMUZICaSbUWaKz7ub1G1HWrasKqGXrGtIGI0NxR8fdKOv1N7ZIad/UaZIhSGNd1h8qRNeU4h0BN1VZLeaGfKjzxKid7RT00PokeKYI2QOBi7ON6Ukax3zw1XdD6Bx/eH9y+HyxWJyeHj+5/+kPv/+X3//OX5w+fVovJrFWm9FmOCE7cc8Pnz65f7euag7cFknV5Ky6OFZk2jkBgqB4AqGXHggrH3T76kOwhFdvAwLvQrWYP793/umPm8tn1eXTZvLMLy9CNddJR0dZi62XELobWxTF3lmTpqIinfSEkQO7csa2kRCywYZJEldMy+l5sLZZTn1TmayLwn55ARCAtInTJp8KQDbc9HUebLHCmwCYOBVvfZUDUZR0m/wSgKM4ccXcxIaDIIKrl1pp8IG0SrKOL2bB+qzTc+WyyadJ1g2ByRgiQwSEBNIes5SOYnEhOBtlHfZNaKoo6SqtI6PdciJ2iW2oMQCuwjNQmkqqpVLc0rNUnHY2r0fZgG1hy6lSRscpKYXBYV0gM5AhpY2JlNLMwRDVs4sQnLZlAyq86NyucwVa1PoL0Gnwq57wioHm1/1e9SKXHV6CLa5azb8wXA1XLp91eUz/ht7V1WcVwFXSh/4ro9r199GLejafXpynvSFp5W3dFEsoFtCU4OxnforSYAzoGJQBvZZtvezlVwRGo4qpDTfhENhD63oCBvEQGLwDW0NTQbAAIc/npZf+xtZstgQipjgaZtXzp8EyRPp8WgRvASOVRGE2AWigQZAhsAdv6+ViWVQqSoOA1p2k20NjSxu0MU2ZK6MoygjJlXmTXwZbnk/KS5+8+7mm1/98CZn1UjgwBpdLcdWd2Yc7u8Wnr/3H/0n2yi9/9I//4clf/IvDhw8AHIAFgKP77/WG+z//7vdGG6PRxsajx0/u371rjHFVA1Ct/0tVaPLQTOHf9gj/utfrxWe9t+1Frpy/fFGTTyAaQjakpBtnHSnr8mKCZJhdGZSFFIwJUa/iuJqfSricL4tsvOnKyje1zGeuXAIaH/eI9GIyQY26DNlop2a1fHq/gUjI5GXNXBBFOrE1GHa1zeewLC1ly6IONg+ULs7P49oKGJNm1WIZJ6nL57osN6/fmpyeKx2VpVMazw+Puo6DgCCpKLInVZT1os5AxTGACAf2wS4mpHW9OPdlkdeSjbZt45bTaTOfI0FAjYCiI4xiVKV4L4sLjDRLpDo668bigXyZTy5sPgHU2npAdPkU5hOVdlRvA5w1oKQOwbta/MXJc0LB3/4P/1NUClGxBA68AotDS9kPK2ww8+ZodHDjQGvd1PbJs+eLxXRVI60gLisgIrTG1ReL6rMvKvILnr+sG88vZIqMa4rES3PZK6BiG6mCLzL4MIDo1YaAJEioNKoICVuyXMuLXKfavmBCgiIkg0pTK59uUY2ynm5pQqVAVOsuFmYR95JhXlr7LvtGvGs1z8JAJtnY3CnqCkhHSWwULeeTpqoRVSv00lrFaeKaPDTWN/7GK6/Wtjk/PUSKKIpJx0nW905UHJvEhKDJaCRIuj3PQAKuLpp8Hhrb292Ph1sbvWhnd2dw45cuC1zkq6hBCWJrhbra2F30tuui7N3/Z//Ls+/9S+HQTSIUWBaVdwGFhaTbyZq89BxMnHV73Xw5Cz4QoYl0XeXt2eezRM5/20MnPVQpobfFVF7Srq/3AllnlTJIiAbb6WhPx5ktC4piRMWuFlQmG/S2r1PUbYppefnUVyWCEiREVoqCdxIcgI6Hm6RNMz0TZNKdqDcEttXsQscdk2a+KdlZEdFR2tnaC64uJ+eAlI13m/m5q/NstJOfH6o4JjImyWy5iNKOzefs/fjglq+KarGMu30gqPO5oDJp5pvadHvBWwA0SVeZOASHgCZNivMTRGiKBQQbD7aS/qZBKU+fNctLhdCSxERpiBIBEO/I10IadWJ647g3ECBgX+ez0JSIqJJO8DYUC8UBo4SyHqImE3nnCQTqYn70CIleEP3/3ePfPf7d438Xj/8/5NvZ2NmgS7wAAAAASUVORK5CYII="

RADAR_SVG = f'''<img class="radar-icon" src="data:image/png;base64,{HEADER_IMAGE_B64}" alt="XRPRadar">'''

FOOTER_BLOCK = """
<div id="debug-panel">
  <div>App Version: {{ version }}</div>
  <div>Last Updated: {{ last_updated }}</div>
  <div>Uptime: {{ uptime }}</div>
  <div>Published Posts: {{ pub_count }}</div>
  <div>Draft Posts: {{ draft_count }}</div>
  <div>Server Time (UTC): {{ server_time }}</div>
</div>
<footer class="site-footer">
  <span>\u00a9\ufe0f Copyright 2026 Red Rio Ventures, LLC. All rights reserved globally.</span>
  <span class="row">
    <button class="btn secondary small" onclick="document.getElementById('debug-panel').style.display = document.getElementById('debug-panel').style.display === 'block' ? 'none' : 'block';">Debug</button>
    <span>{{ version }} &middot; Last update: {{ last_updated }}</span>
  </span>
</footer>
"""

HEADER_BLOCK = """
<header class="site-header">
  <div class="hdr-left">
    <a href="{{ url_for('index') }}">XRPRadar Blog</a>
    <div class="tagline">XRP market insight &amp; product notes</div>
  </div>
  <div class="hdr-center">""" + RADAR_SVG + """</div>
  <div class="hdr-right">
    <div class="live-badge"><span class="live-dot"></span>LIVE</div>
    <div>{{ version }}</div>
    <div>Updated {{ last_updated }}</div>
  </div>
</header>
"""


def sidebar_html():
    return """
<aside class="sidebar">
  <div class="sb-block">
    <div class="sb-title">Search</div>
    <form class="search-form" method="get" action="{{ url_for('search') }}">
      <input type="text" name="q" placeholder="Search posts..." value="{{ query|default('') }}">
    </form>
  </div>
  <div class="sb-block">
    <div class="sb-title">Recent Posts</div>
    <ul class="sb-list">
      {% for rp in recent_posts %}
      <li><a href="{{ url_for('show_post', slug=rp['slug']) }}">{{ rp['title'] }}</a></li>
      {% else %}
      <li class="sb-cat-count">No posts yet.</li>
      {% endfor %}
    </ul>
  </div>
  <div class="sb-block">
    <div class="sb-title">Categories</div>
    <ul class="sb-list">
      {% for c in categories %}
      <li><a href="{{ url_for('by_category', category=c['category']) }}">{{ c['category'] }}</a> <span class="sb-cat-count">({{ c['n'] }})</span></li>
      {% else %}
      <li class="sb-cat-count">No categories yet.</li>
      {% endfor %}
    </ul>
  </div>
</aside>
"""


def sidebar_context(db):
    recent_posts = db.execute(
        "SELECT * FROM posts WHERE published = 1 ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    categories = db.execute(
        "SELECT category, COUNT(*) as n FROM posts WHERE published = 1 GROUP BY category ORDER BY category"
    ).fetchall()
    return recent_posts, categories


# ----------------------------------------------------------------------
# PUBLIC TEMPLATES
# ----------------------------------------------------------------------

INDEX_TEMPLATE = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>XRPRadar Blog</title><style>""" + BASE_CSS + """</style></head><body>
<div class="shell">
""" + HEADER_BLOCK + """
<div class="layout">
""" + sidebar_html() + """
  <main class="content">
    <h1>{{ heading }}</h1>
    <p class="meta">{{ subheading }}</p>
    {% if posts %}
      {% for p in posts %}
      <div class="post-card">
        <div class="category-tag">{{ p['category'] }}</div>
        <a class="post-link" href="{{ url_for('show_post', slug=p['slug']) }}"><h2>{{ p['title'] }}</h2></a>
        <div class="meta">{{ p['created_at'] }}</div>
        <div class="excerpt">{{ p['excerpt'] }}</div>
      </div>
      {% endfor %}
    {% else %}
      <p class="meta">No posts found.</p>
    {% endif %}
  </main>
</div>
</div>
""" + FOOTER_BLOCK + """
</body></html>
"""

POST_TEMPLATE = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ post['title'] }} \u2014 XRPRadar Blog</title><style>""" + BASE_CSS + """</style></head><body>
<div class="shell">
""" + HEADER_BLOCK + """
<div class="layout">
""" + sidebar_html() + """
  <main class="content">
    <a class="btn secondary small" href="{{ url_for('index') }}">&larr; All posts</a>
    <div class="category-tag" style="margin-top:16px;">{{ post['category'] }}</div>
    <h1>{{ post['title'] }}</h1>
    <div class="meta">{{ post['created_at'] }}</div>
    <div class="post-content">{{ rendered_content|safe }}</div>
  </main>
</div>
</div>
""" + FOOTER_BLOCK + """
</body></html>
"""

# ----------------------------------------------------------------------
# ADMIN TEMPLATES
# ----------------------------------------------------------------------

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin Login \u2014 XRPRadar Blog</title><style>""" + BASE_CSS + """</style></head><body>
<div class="shell">
""" + HEADER_BLOCK + """
<div style="max-width:400px; margin:40px auto; padding:0 20px;">
  <h1>Admin Login</h1>
  {% if error %}<div class="flash" style="color:#ff4d4f;">{{ error }}</div>{% endif %}
  <form method="post">
    <label>Password</label>
    <input type="password" name="password" autofocus>
    <button class="btn" type="submit">Log in</button>
  </form>
</div>
""" + FOOTER_BLOCK + """
</body></html>
"""

ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin \u2014 XRPRadar Blog</title><style>""" + BASE_CSS + """</style></head><body>
<div class="shell">
""" + HEADER_BLOCK + """
<div style="max-width:1000px; margin:0 auto; padding:24px 20px 60px;">
  <div class="row" style="justify-content:space-between;">
    <h1>Admin</h1>
    <a class="btn secondary" href="{{ url_for('admin_logout') }}">Log out</a>
  </div>
  {% if flash_msg %}<div class="flash">{{ flash_msg }}</div>{% endif %}

  <h2>New Post</h2>
  <form method="post" action="{{ url_for('admin_new_post') }}" enctype="multipart/form-data">
    <label>Title</label>
    <input type="text" name="title" required>
    <label>Category</label>
    <input type="text" name="category" value="General">
    <label>Excerpt (shown on the blog homepage)</label>
    <input type="text" name="excerpt">
    <label>Images (optional \u2014 upload, then reference in content as {{ '{{img:filename.jpg}}' }})</label>
    <input type="file" name="images" multiple accept="image/png,image/jpeg,image/gif,image/webp">
    <div class="hint">Use the exact filename you're uploading, e.g. {{ '{{img:chart.png}}' }}, anywhere in the content below.</div>
    <label>Content</label>
    <textarea name="content" required></textarea>
    <div class="row">
      <button class="btn" type="submit" name="publish" value="1">Publish</button>
      <button class="btn secondary" type="submit" name="publish" value="0">Save as Draft</button>
    </div>
  </form>

  <h2 style="margin-top:40px;">All Posts</h2>
  <table>
    <tr><th>Title</th><th>Category</th><th>Status</th><th>Created</th><th>Actions</th></tr>
    {% for p in posts %}
    <tr>
      <td>{{ p['title'] }}</td>
      <td>{{ p['category'] }}</td>
      <td>{% if p['published'] %}<span class="badge pub">Published</span>{% else %}<span class="badge draft">Draft</span>{% endif %}</td>
      <td>{{ p['created_at'] }}</td>
      <td>
        <a class="btn secondary small" href="{{ url_for('admin_edit_post', post_id=p['id']) }}">Edit</a>
        <form style="display:inline" method="post" action="{{ url_for('admin_toggle_publish', post_id=p['id']) }}">
          <button class="btn secondary small" type="submit">{% if p['published'] %}Unpublish{% else %}Publish{% endif %}</button>
        </form>
        <form style="display:inline" method="post" action="{{ url_for('admin_delete_post', post_id=p['id']) }}" onsubmit="return confirm('Delete this post?');">
          <button class="btn danger small" type="submit">Delete</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </table>
</div>
""" + FOOTER_BLOCK + """
</body></html>
"""

EDIT_TEMPLATE = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Edit Post \u2014 XRPRadar Blog</title><style>""" + BASE_CSS + """</style></head><body>
<div class="shell">
""" + HEADER_BLOCK + """
<div style="max-width:1000px; margin:0 auto; padding:24px 20px 60px;">
  <a class="btn secondary small" href="{{ url_for('admin') }}">&larr; Back to admin</a>
  <h1 style="margin-top:20px;">Edit Post</h1>
  <form method="post" enctype="multipart/form-data">
    <label>Title</label>
    <input type="text" name="title" value="{{ post['title'] }}" required>
    <label>Category</label>
    <input type="text" name="category" value="{{ post['category'] }}">
    <label>Excerpt</label>
    <input type="text" name="excerpt" value="{{ post['excerpt'] or '' }}">
    <label>Existing Images</label>
    <div class="hint">{% for img in images %}{{ img['filename'] }}{% if not loop.last %}, {% endif %}{% else %}None uploaded{% endfor %}</div>
    <label>Add More Images (optional)</label>
    <input type="file" name="images" multiple accept="image/png,image/jpeg,image/gif,image/webp">
    <label>Content</label>
    <textarea name="content" required>{{ post['content'] }}</textarea>
    <button class="btn" type="submit">Save Changes</button>
  </form>
</div>
""" + FOOTER_BLOCK + """
</body></html>
"""


def footer_ctx(db):
    pub_count = db.execute("SELECT COUNT(*) c FROM posts WHERE published = 1").fetchone()["c"]
    draft_count = db.execute("SELECT COUNT(*) c FROM posts WHERE published = 0").fetchone()["c"]
    return dict(
        version=APP_VERSION,
        last_updated=LAST_UPDATED,
        uptime=uptime_str(),
        pub_count=pub_count,
        draft_count=draft_count,
        server_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ----------------------------------------------------------------------
# PUBLIC ROUTES
# ----------------------------------------------------------------------

@app.route("/")
def index():
    db = get_db()
    posts = db.execute("SELECT * FROM posts WHERE published = 1 ORDER BY created_at DESC").fetchall()
    recent_posts, categories = sidebar_context(db)
    return render_template_string(
        INDEX_TEMPLATE, posts=posts, heading="XRPRadar Blog",
        subheading="XRP market insight, product updates, and notes from Red Rio Ventures.",
        recent_posts=recent_posts, categories=categories, **footer_ctx(db)
    )


@app.route("/category/<category>")
def by_category(category):
    db = get_db()
    posts = db.execute(
        "SELECT * FROM posts WHERE published = 1 AND category = ? ORDER BY created_at DESC", (category,)
    ).fetchall()
    recent_posts, categories = sidebar_context(db)
    return render_template_string(
        INDEX_TEMPLATE, posts=posts, heading=f"Category: {category}",
        subheading=f"{len(posts)} post(s) in {category}.",
        recent_posts=recent_posts, categories=categories, **footer_ctx(db)
    )


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    db = get_db()
    if q:
        like = f"%{q}%"
        posts = db.execute(
            "SELECT * FROM posts WHERE published = 1 AND (title LIKE ? OR content LIKE ?) ORDER BY created_at DESC",
            (like, like),
        ).fetchall()
    else:
        posts = []
    recent_posts, categories = sidebar_context(db)
    return render_template_string(
        INDEX_TEMPLATE, posts=posts, heading=f'Search: "{q}"' if q else "Search",
        subheading=f"{len(posts)} result(s).",
        recent_posts=recent_posts, categories=categories, query=q, **footer_ctx(db)
    )


@app.route("/post/<slug>")
def show_post(slug):
    db = get_db()
    post = db.execute("SELECT * FROM posts WHERE slug = ? AND published = 1", (slug,)).fetchone()
    if post is None:
        abort(404)
    recent_posts, categories = sidebar_context(db)
    return render_template_string(
        POST_TEMPLATE, post=post, rendered_content=render_content(post["content"]),
        recent_posts=recent_posts, categories=categories, **footer_ctx(db)
    )


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ----------------------------------------------------------------------
# ADMIN ROUTES
# ----------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))
        error = "Incorrect password."
    db = get_db()
    return render_template_string(LOGIN_TEMPLATE, error=error, **footer_ctx(db))


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin():
    db = get_db()
    posts = db.execute("SELECT * FROM posts ORDER BY created_at DESC").fetchall()
    flash_msg = request.args.get("msg")
    return render_template_string(ADMIN_TEMPLATE, posts=posts, flash_msg=flash_msg, **footer_ctx(db))


@app.route("/admin/post/new", methods=["POST"])
@login_required
def admin_new_post():
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip() or "General"
    excerpt = request.form.get("excerpt", "").strip()
    content = request.form.get("content", "").strip()
    publish = request.form.get("publish", "0") == "1"

    if not title or not content:
        return redirect(url_for("admin", msg="Title and content are required."))

    slug = unique_slug(title)
    now = datetime.utcnow().strftime("%B %d, %Y")

    db = get_db()
    cur = db.execute(
        "INSERT INTO posts (slug, title, excerpt, content, category, published, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (slug, title, excerpt, content, category, 1 if publish else 0, now, now),
    )
    db.commit()
    post_id = cur.lastrowid

    files = request.files.getlist("images")
    save_uploaded_images(post_id, files)

    return redirect(url_for("admin", msg="Post saved."))


@app.route("/admin/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit_post(post_id):
    db = get_db()
    post = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if post is None:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip() or "General"
        excerpt = request.form.get("excerpt", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            return redirect(url_for("admin_edit_post", post_id=post_id))
        slug = unique_slug(title, exclude_id=post_id)
        now = datetime.utcnow().strftime("%B %d, %Y")
        db.execute(
            "UPDATE posts SET title=?, excerpt=?, content=?, category=?, slug=?, updated_at=? WHERE id=?",
            (title, excerpt, content, category, slug, now, post_id),
        )
        db.commit()
        files = request.files.getlist("images")
        save_uploaded_images(post_id, files)
        return redirect(url_for("admin", msg="Post updated."))

    images = db.execute("SELECT * FROM images WHERE post_id = ?", (post_id,)).fetchall()
    return render_template_string(EDIT_TEMPLATE, post=post, images=images, **footer_ctx(db))


@app.route("/admin/post/<int:post_id>/publish", methods=["POST"])
@login_required
def admin_toggle_publish(post_id):
    db = get_db()
    post = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if post is None:
        abort(404)
    new_state = 0 if post["published"] else 1
    db.execute("UPDATE posts SET published = ? WHERE id = ?", (new_state, post_id))
    db.commit()
    return redirect(url_for("admin"))


@app.route("/admin/post/<int:post_id>/delete", methods=["POST"])
@login_required
def admin_delete_post(post_id):
    db = get_db()
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db.execute("DELETE FROM images WHERE post_id = ?", (post_id,))
    db.commit()
    return redirect(url_for("admin", msg="Post deleted."))


@app.errorhandler(404)
def not_found(e):
    return "<h1 style='font-family:Calibri;color:#e7ecf3;background:#000;padding:60px;text-align:center;'>404 \u2014 Not found</h1>", 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
