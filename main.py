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

APP_VERSION = "v10"
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS site_stats (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO site_stats (key, value) VALUES ('visitor_count', 102394)"
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
@import url('https://fonts.googleapis.com/css2?family=Dancing+Script:wght@600&display=swap');
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
    background: #000000;
    border-bottom: 2px solid var(--hdr);
    padding: 16px 24px;
    gap: 20px;
}
.hdr-left-block { display: flex; flex-direction: column; gap: 10px; }
.brand-row { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.sat-icon { width: 64px; height: 64px; border-radius: 14px; display: block; }
.brand-text { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.brand-title { color: #ffffff; font-size: 34px; font-weight: bold; font-style: italic; }
.brand-script { color: #ffffff; font-size: 26px; font-family: 'Dancing Script', cursive; }
.hdr-tagline { color: #ffffff; font-size: 20px; }
.hdr-tagline em { font-style: italic; }
.cta-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.visit-btn {
    background: var(--hdr);
    color: #06111c;
    font-weight: bold;
    padding: 10px 18px;
    border-radius: 8px;
    text-decoration: none;
    font-size: 15px;
    font-family: Calibri, sans-serif;
}
.suffixes { color: #ffffff; font-size: 15px; }
.hdr-right { text-align: right; font-size: 12px; color: var(--muted); line-height: 1.6; white-space: nowrap; }
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
}
"""

SAT_ICON_B64 = (
    "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"
    "RivhqP8NoKUzzimDiUsAAAAASUVORK5CYII="
)

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
  <span>\u00a9\ufe0f Copyright 2026 Red Rio Ventures, LLC. All rights reserved globally. &middot; Visitors: {{ visitor_count }}</span>
  <span class="row">
    <button class="btn secondary small" onclick="document.getElementById(\'debug-panel\').style.display = document.getElementById(\'debug-panel\').style.display === \'block\' ? \'none\' : \'block\';">Debug</button>
    <span>{{ version }} &middot; Last update: {{ last_updated }}</span>
  </span>
</footer>
"""

HEADER_BLOCK = '''
<header class="site-header">
  <div class="hdr-left-block">
    <div class="brand-row">
      <img class="sat-icon" src="data:image/png;base64,''' + SAT_ICON_B64 + '''" alt="XRPRadar Satellite">
      <div class="brand-text">
        <span class="brand-title">XRPRadar</span><span class="brand-script">Blog for xrpradar Web</span>
      </div>
    </div>
    <div class="hdr-tagline">The <em>NEW</em> XRP Intelligence Standard</div>
    <div class="cta-row">
      <a class="visit-btn" href="https://xrpradar.com" target="_blank" rel="noopener">Visit xrpradar</a>
      <span class="suffixes">.com, .net, .xyz</span>
    </div>
  </div>
  <div class="hdr-right">
    <div class="live-badge"><span class="live-dot"></span>LIVE</div>
    <div>{{ version }}</div>
    <div>Updated {{ last_updated }}</div>
  </div>
</header>
'''


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


def get_visitor_count(db):
    row = db.execute("SELECT value FROM site_stats WHERE key = 'visitor_count'").fetchone()
    return row["value"] if row else 102394


def bump_visitor_count(db):
    """Returns the count to display for THIS visit, then increments for the next one."""
    current = get_visitor_count(db)
    db.execute("UPDATE site_stats SET value = value + 1 WHERE key = 'visitor_count'")
    db.commit()
    return current


def footer_ctx(db, visitor_count=None):
    pub_count = db.execute("SELECT COUNT(*) c FROM posts WHERE published = 1").fetchone()["c"]
    draft_count = db.execute("SELECT COUNT(*) c FROM posts WHERE published = 0").fetchone()["c"]
    if visitor_count is None:
        visitor_count = get_visitor_count(db)
    return dict(
        version=APP_VERSION,
        last_updated=LAST_UPDATED,
        uptime=uptime_str(),
        pub_count=pub_count,
        draft_count=draft_count,
        server_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        visitor_count=f"{visitor_count:,}",
    )


# ----------------------------------------------------------------------
# PUBLIC ROUTES
# ----------------------------------------------------------------------

@app.route("/")
def index():
    db = get_db()
    visitor_count = bump_visitor_count(db)
    posts = db.execute("SELECT * FROM posts WHERE published = 1 ORDER BY created_at DESC").fetchall()
    recent_posts, categories = sidebar_context(db)
    return render_template_string(
        INDEX_TEMPLATE, posts=posts, heading="XRPRadar Blog",
        subheading="XRP market insight, product updates, and notes from Red Rio Ventures.",
        recent_posts=recent_posts, categories=categories, **footer_ctx(db, visitor_count)
    )


@app.route("/category/<category>")
def by_category(category):
    db = get_db()
    visitor_count = bump_visitor_count(db)
    posts = db.execute(
        "SELECT * FROM posts WHERE published = 1 AND category = ? ORDER BY created_at DESC", (category,)
    ).fetchall()
    recent_posts, categories = sidebar_context(db)
    return render_template_string(
        INDEX_TEMPLATE, posts=posts, heading=f"Category: {category}",
        subheading=f"{len(posts)} post(s) in {category}.",
        recent_posts=recent_posts, categories=categories, **footer_ctx(db, visitor_count)
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
    visitor_count = bump_visitor_count(db)
    recent_posts, categories = sidebar_context(db)
    return render_template_string(
        POST_TEMPLATE, post=post, rendered_content=render_content(post["content"]),
        recent_posts=recent_posts, categories=categories, **footer_ctx(db, visitor_count)
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


# ----------------------------------------------------------------------
# DO NOT DELETE \u2014 COPYRIGHT ARCHIVE ROUTE
# ----------------------------------------------------------------------
# This route is intentionally NOT linked from any nav, sidebar, sitemap,
# or other page on the site. It exists solely as a timestamped legal
# record of site content for copyright purposes, matching the frozen
# archive pattern used on XRPRadar (/copyright7_26, /copyright7_26_b).
# Lock date below is fixed and must never be changed on future edits.
# DO NOT DELETE THIS ROUTE OR THIS COMMENT BLOCK.
# ----------------------------------------------------------------------

ARCHIVE_LOCK_DATE = "July 12, 2026"
ARCHIVE_ROUTE_PATH = "/archivexrpblogcopyright12July2026"

ARCHIVE_TEMPLATE = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>Copyright Archive \u2014 DO NOT DELETE</title>
<style>
:root { --hdr: #03b1fc; --tq: #00e5cc; --bg: #000000; --card: #0d0d0d; --line: #1c1c1c; --text: #e7ecf3; --muted: #8b93a7; }
* { box-sizing: border-box; }
body { margin: 0; font-family: Calibri, 'Segoe UI', sans-serif; background: #000; color: var(--text); position: relative; }
.wm-layer {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    pointer-events: none; z-index: 999; overflow: hidden;
    display: flex; flex-wrap: wrap; align-content: space-around; justify-content: space-around;
    opacity: 0.07;
}
.wm-layer span {
    display: inline-block; transform: rotate(-30deg);
    font-size: 22px; font-weight: bold; color: var(--tq);
    white-space: nowrap; margin: 40px;
}
.wrap { max-width: 900px; margin: 0 auto; padding: 40px 24px 80px; position: relative; z-index: 1; }
.lockbar { background: #3a0000; border: 1px solid #ff4d4f; color: #ff9d9d; padding: 12px 18px; border-radius: 6px; font-weight: bold; margin-bottom: 24px; text-align: center; }
h1 { color: var(--hdr); font-size: 26px; margin-bottom: 4px; }
.meta { color: var(--muted); font-size: 14px; margin-bottom: 28px; }
.meta strong { color: var(--tq); }
.archive-card { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 18px; margin-bottom: 14px; }
.archive-card h2 { margin: 0 0 6px; font-size: 17px; color: var(--text); }
.archive-card .status { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 10px; margin-bottom: 8px; }
.status.pub { background: rgba(0,229,204,0.15); color: var(--tq); }
.status.draft { background: rgba(139,147,167,0.15); color: var(--muted); }
.archive-card .body { font-size: 14px; color: var(--muted); white-space: pre-wrap; line-height: 1.6; }
footer { text-align: center; color: var(--muted); font-size: 12px; padding: 30px 20px; border-top: 1px solid var(--line); margin-top: 30px; }
</style>
</head><body>
<div class="wm-layer">
{% for i in range(40) %}<span>\u00a9 RED RIO VENTURES, LLC \u2014 ARCHIVED COPY</span>{% endfor %}
</div>
<div class="wrap">
  <div class="lockbar">DO NOT DELETE \u2014 THIS PAGE IS A LOCKED COPYRIGHT ARCHIVE</div>
  <h1>XRPRadar Blog \u2014 Copyright Archive</h1>
  <div class="meta">
    Archive locked: <strong>{{ archive_date }}</strong> &middot;
    Snapshot rendered: <strong>{{ server_time }}</strong><br>
    This page is intentionally unlinked from site navigation. It exists as a timestamped record of published content for copyright documentation.
  </div>
  {% for p in posts %}
  <div class="archive-card">
    <span class="status {{ 'pub' if p['published'] else 'draft' }}">{{ 'Published' if p['published'] else 'Draft' }}</span>
    <h2>{{ p['title'] }} <span style="color:var(--muted); font-weight:normal; font-size:13px;">({{ p['category'] }})</span></h2>
    <div class="meta" style="margin-bottom:8px;">Created {{ p['created_at'] }} &middot; Last updated {{ p['updated_at'] }}</div>
    <div class="body">{{ p['content'] }}</div>
  </div>
  {% else %}
  <p class="meta">No posts recorded at time of this snapshot.</p>
  {% endfor %}
  <footer>\u00a9\ufe0f Copyright 2026 Red Rio Ventures, LLC. All rights reserved globally. \u2014 Archived record, not for public distribution.</footer>
</div>
</body></html>
"""


@app.route(ARCHIVE_ROUTE_PATH)
def _do_not_delete_copyright_archive():
    """
    DO NOT DELETE.
    Hidden, unlinked copyright archive snapshot. No nav/sidebar/sitemap
    reference exists anywhere in this app pointing to this route.
    Serves a timestamped, watermarked record of all post content
    (published and draft) for copyright/legal purposes.
    """
    db = get_db()
    posts = db.execute("SELECT * FROM posts ORDER BY created_at DESC").fetchall()
    server_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    return render_template_string(
        ARCHIVE_TEMPLATE, posts=posts, archive_date=ARCHIVE_LOCK_DATE, server_time=server_time
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
