from flask import Flask, render_template, jsonify, request, redirect, url_for, session, make_response
import sqlite3
import os
import secrets
import threading
import time
import shutil
import base64
import io
from datetime import datetime
from collections import defaultdict

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ========== 安全配置 ==========
# 部署时必须设置 ACCESS_KEY 环境变量
ACCESS_KEY = os.environ.get('ACCESS_KEY', '')
if not ACCESS_KEY:
    print('⚠️ 未设置 ACCESS_KEY，使用随机密码（仅限开发）')
    ACCESS_KEY = secrets.token_hex(16)
    print(f'🔑 本次密码: {ACCESS_KEY}')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ---- Session Cookie 加固 ----
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,   # JS 无法读取 cookie，防 XSS 窃取
    SESSION_COOKIE_SAMESITE='Lax',  # 防 CSRF
    SESSION_COOKIE_SECURE=False,    # 本机部署无 HTTPS，设 False
)

# ---- 登录频率限制 ----
LOGIN_ATTEMPTS = defaultdict(list)  # {ip: [timestamp, ...]}
MAX_ATTEMPTS = 5       # 最多尝试次数
ATTEMPT_WINDOW = 300   # 5分钟内

def is_rate_limited(ip):
    now = time.time()
    attempts = [t for t in LOGIN_ATTEMPTS.get(ip, []) if now - t < ATTEMPT_WINDOW]
    LOGIN_ATTEMPTS[ip] = attempts
    return len(attempts) >= MAX_ATTEMPTS

def record_attempt(ip):
    LOGIN_ATTEMPTS[ip].append(time.time())

@app.after_request
def security_headers(response):
    """添加安全响应头（轻量级，不阻断正常功能）"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response
DATABASE = 'ride.db'
BACKUP_DIR = 'backups'
BACKUP_KEEP_DAYS = 30  # 只保留最近 30 天的备份

def do_backup():
    """执行数据库备份"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    today = datetime.now().strftime('%Y-%m-%d')
    backup_name = f'ride_{today}.db'
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    if not os.path.exists(backup_path):
        shutil.copy2(DATABASE, backup_path)
        print(f'📦 数据库已备份: {backup_path}')
        # 清理过期备份
        cutoff = datetime.now().timestamp() - BACKUP_KEEP_DAYS * 86400
        for f in os.listdir(BACKUP_DIR):
            fp = os.path.join(BACKUP_DIR, f)
            if f.startswith('ride_') and f.endswith('.db'):
                if os.path.getmtime(fp) < cutoff:
                    os.remove(fp)
                    print(f'🗑️ 清理过期备份: {f}')

def backup_loop():
    """后台线程：每 30 秒检查一次，在 00:00-00:01 之间触发备份"""
    backed_up_today = False
    while True:
        now = datetime.now()
        if now.hour == 0 and now.minute == 0 and not backed_up_today:
            do_backup()
            backed_up_today = True
        elif now.hour == 1:
            backed_up_today = False  # 凌晨1点重置标志
        time.sleep(30)

# 登录页 HTML（与网站绿色骑行风格一致）
LOGIN_PAGE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>登录</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, #2d5a3d, #1a3c24);
    font-family: 'Segoe UI', 'Noto Sans SC', sans-serif;
  }
  .login-box {
    background: #fff; border-radius: 16px; padding: 48px 36px 36px;
    width: 380px; max-width: 90vw; box-shadow: 0 20px 60px rgba(0,0,0,0.35);
  }
  .login-box .icon {
    text-align: center; font-size: 3.5rem; margin-bottom: 12px;
  }
  .login-box h2 {
    text-align: center; color: #2d5a3d; margin-bottom: 8px;
    font-size: 1.5rem; font-weight: 700;
  }
  .login-box .sub {
    text-align: center; color: #999; font-size: 0.85rem; margin-bottom: 28px;
  }
  .login-box input {
    width: 100%; padding: 14px 16px; border: 2px solid #e0e0e0;
    border-radius: 10px; font-size: 1rem; outline: none;
    transition: border-color 0.3s; font-family: inherit;
  }
  .login-box input:focus { border-color: #2d5a3d; }
  .login-box button {
    width: 100%; padding: 14px; margin-top: 20px;
    background: linear-gradient(135deg, #2d5a3d, #1a3c24);
    color: #fff; border: none; border-radius: 10px;
    font-size: 1.05rem; font-weight: 600; cursor: pointer;
    transition: opacity 0.3s; font-family: inherit;
  }
  .login-box button:hover { opacity: 0.9; }
  .login-box .error {
    color: #e53935; text-align: center; margin-top: 16px;
    font-size: 0.9rem; display: none;
  }
</style>
</head>
<body>
<div class="login-box">
  <div class="icon">🔐</div>
  <h2>骑行数据面板</h2>
  <p class="sub">请输入访问密码</p>
  <form method="POST" id="loginForm">
    <input type="password" name="password" placeholder="密码" autofocus required>
    <button type="submit">🏍️ 进入</button>
    <p class="error" id="err">密码错误，请重试</p>
  </form>
</div>
{error_script}
</body>
</html>
'''

@app.before_request
def check_access():
    # 登录页本身、静态文件不拦截
    if request.path == '/login' or request.path.startswith('/static'):
        return
    # 已登录通过
    if session.get('authed'):
        return
    # 跳转登录页，记住原本要去哪
    return redirect(url_for('login', next=request.url))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # 频率限制检查
        ip = request.remote_addr
        if is_rate_limited(ip):
            time_left = int(ATTEMPT_WINDOW - (time.time() - min(LOGIN_ATTEMPTS[ip])))
            return f'<h2>🚫 登录尝试过多</h2><p>请 {time_left} 秒后再试。</p>', 429
        if request.form.get('password') == ACCESS_KEY:
            session['authed'] = True
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect('/')
        else:
            record_attempt(ip)
            return LOGIN_PAGE.replace('{error_script}', '<script>document.getElementById("err").style.display="block"</script>')
    return LOGIN_PAGE.replace('{error_script}', '')

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS profile
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  nickname TEXT,
                  motto TEXT,
                  location TEXT,
                  avatar TEXT DEFAULT '🚴')''')
    # 兼容旧数据库：无 avatar 列时自动添加
    c.execute("PRAGMA table_info(profile)")
    columns = [col[1] for col in c.fetchall()]
    if 'avatar' not in columns:
        c.execute("ALTER TABLE profile ADD COLUMN avatar TEXT DEFAULT '🚴'")
    
    c.execute('''CREATE TABLE IF NOT EXISTS stats
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  total_km INTEGER,
                  total_cost INTEGER,
                  maintenance_status TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS ride_records
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT,
                  distance REAL,
                  avg_speed REAL,
                  note TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS expenses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT,
                  amount REAL,
                  category TEXT,
                  description TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS equipment
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT,
                  status TEXT,
                  last_maintenance TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS maintenance_tasks
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT,
                  current_value INTEGER,
                  max_value INTEGER,
                  unit TEXT)''')
 
    c.execute('''CREATE TABLE IF NOT EXISTS food_recipes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT,
                  category TEXT,
                  difficulty TEXT,
                  cook_time INTEGER,
                  calories INTEGER,
                  equipment TEXT,
                  ingredients TEXT,
                  steps TEXT,
                  tips TEXT)''')

    # 只在数据库首次创建时插入种子数据，避免重启时重新插入
    c.execute('''CREATE TABLE IF NOT EXISTS _meta
                 (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute("SELECT value FROM _meta WHERE key='seeded'")
    already_seeded = c.fetchone()

    if not already_seeded:
        c.execute("INSERT OR REPLACE INTO _meta (key, value) VALUES ('seeded', '1')")

        c.execute('INSERT INTO profile (nickname, motto, location, avatar) VALUES (?, ?, ?, ?)',
                  ('一禄', '每一次踩踏，都是自由的宣告。', '北京', '🚴'))

        c.execute('INSERT INTO stats (total_km, total_cost, maintenance_status) VALUES (?, ?, ?)',
                  (468, 2680, '良好'))

        records = [
            ('2026-06-15', 35.5, 22.3, '骑行第一天！'),
            ('2026-06-14', 28.8, 20.1, '日常通勤'),
            ('2026-06-13', 42.1, 24.5, '郊区骑行'),
            ('2026-06-12', 55.0, 21.8, '假期长途'),
            ('2026-06-11', 18.3, 19.2, '傍晚骑行'),
        ]
        c.executemany('INSERT INTO ride_records (date, distance, avg_speed, note) VALUES (?, ?, ?, ?)', records)

        expenses = [
            ('2026-06-15', 180, '装备', '刹车皮'),
            ('2026-06-14', 50, '餐饮', '骑行后加餐'),
            ('2026-06-13', 320, '装备', '新轮胎'),
            ('2026-06-12', 150, '交通', '停车费'),
            ('2026-06-11', 80, '餐饮', '能量补给'),
        ]
        c.executemany('INSERT INTO expenses (date, amount, category, description) VALUES (?, ?, ?, ?)', expenses)
        equipments = [
            ('自行车', '良好', '2026-05-01'),
            ('骑行眼镜', '一般', '2026-04-15'),
            ('头盔', '良好', '2026-05-01'),
            ('骑行手套', '需维修', '2026-03-20'),
            ('骑行服', '良好', '2026-04-01'),
            ('骑行鞋', '一般', '2026-03-10'),
        ]
        c.executemany('INSERT INTO equipment (name, status, last_maintenance) VALUES (?, ?, ?)', equipments)

        tasks = [
            ('链条', 2800, 3000, 'km'),
            ('刹车皮', 1200, 2000, 'km'),
            ('轮胎', 3500, 5000, 'km'),
            ('变速线', 4800, 5000, 'km'),
            ('脚踏板', 12, 24, '个月'),
        ]
        c.executemany('INSERT INTO maintenance_tasks (name, current_value, max_value, unit) VALUES (?, ?, ?, ?)', tasks)

    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/profile')
def profile_api():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM profile WHERE id=1')
    profile = c.fetchone()
    conn.close()
    return jsonify({
        'nickname': profile[1],
        'motto': profile[2],
        'location': profile[3],
        'avatar': profile[4] if len(profile) > 4 else '🚴'
    })

@app.route('/api/profile', methods=['PUT'])
def update_profile():
    data = request.get_json()
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('UPDATE profile SET nickname=?, motto=?, location=?, avatar=? WHERE id=1',
              (data.get('nickname'), data.get('motto'), data.get('location'), data.get('avatar')))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/profile/avatar', methods=['POST'])
def upload_avatar():
    """上传头像图片，返回 base64 data URL"""
    file = request.files.get('avatar')
    if not file or file.filename == '':
        return jsonify({'error': '未选择文件'}), 400
    # 限制大小 5MB
    data = file.read()
    if len(data) > 5 * 1024 * 1024:
        return jsonify({'error': '图片不能超过 5MB'}), 400
    # 用 Pillow 缩放
    if HAS_PIL:
        img = Image.open(io.BytesIO(data))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.thumbnail((200, 200), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        data = buf.getvalue()
    # 转 base64
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
    mime = f'image/{ext}' if ext in ('png','gif','webp') else 'image/jpeg'
    b64 = base64.b64encode(data).decode()
    avatar_url = f'data:{mime};base64,{b64}'
    # 存入数据库
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('UPDATE profile SET avatar=? WHERE id=1', (avatar_url,))
    conn.commit()
    conn.close()
    return jsonify({'avatar': avatar_url, 'success': True})

@app.route('/api/stats')
def stats_api():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM stats WHERE id=1')
    stats = c.fetchone()
    conn.close()
    return jsonify({
        'totalKm': stats[1],
        'totalCost': stats[2],
        'maintenanceStatus': stats[3]
    })

@app.route('/api/location')
def location_api():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT location FROM profile WHERE id=1')
    result = c.fetchone()
    conn.close()
    return jsonify({'location': result[0] if result else '北京'})


@app.route('/api/ride/history')
def ride_history():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT date, SUM(distance) as total FROM ride_records GROUP BY date ORDER BY date DESC LIMIT 30')
    records = c.fetchall()
    conn.close()
    return jsonify([{
        'date': r[0],
        'km': round(r[1], 2)
    } for r in records])



@app.route('/api/ride_record', methods=['POST'])
def add_ride_record():
    data = request.get_json()
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('INSERT INTO ride_records (date, distance, avg_speed, note) VALUES (?, ?, ?, ?)',
              (data['date'], data['distance'], data.get('avgSpeed', 0), data.get('note', '')))
    conn.commit()
    record_id = c.lastrowid
    conn.close()
    return jsonify({'id': record_id, 'success': True})

@app.route('/api/ride_record/<int:id>', methods=['PUT', 'DELETE'])
def modify_ride_record(id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    if request.method == 'PUT':
        data = request.get_json()
        c.execute('UPDATE ride_records SET date=?, distance=?, avg_speed=?, note=? WHERE id=?',
                  (data['date'], data['distance'], data.get('avgSpeed', 0), data.get('note', ''), id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        c.execute('DELETE FROM ride_records WHERE id=?', (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/ride_records')
def ride_records_api():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM ride_records ORDER BY date DESC LIMIT 10')
    records = c.fetchall()
    conn.close()
    return jsonify([{
        'id': r[0],
        'date': r[1],
        'distance': r[2],
        'avgSpeed': r[3],
        'note': r[4]
    } for r in records])

@app.route('/api/ride_stats/<period>')
def ride_stats_api(period):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    if period == 'day':
        c.execute('SELECT date, SUM(distance) FROM ride_records GROUP BY date ORDER BY date DESC LIMIT 30')
    elif period == 'month':
        c.execute('SELECT strftime("%Y-%m", date) as month, SUM(distance) FROM ride_records GROUP BY month ORDER BY month DESC LIMIT 12')
    else:
        c.execute('SELECT strftime("%Y", date) as year, SUM(distance) FROM ride_records GROUP BY year ORDER BY year DESC LIMIT 5')
    
    records = c.fetchall()
    conn.close()
    
    labels = [r[0] for r in records]
    values = [r[1] for r in records]
    
    return jsonify({'labels': labels, 'values': values})

@app.route('/api/expense_record', methods=['POST'])
def add_expense_record():
    data = request.get_json()
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('INSERT INTO expenses (date, amount, category, description) VALUES (?, ?, ?, ?)',
              (data['date'], data['amount'], data['category'], data.get('description', '')))
    conn.commit()
    record_id = c.lastrowid
    conn.close()
    return jsonify({'id': record_id, 'success': True})

@app.route('/api/expense_record/<int:id>', methods=['PUT', 'DELETE'])
def modify_expense_record(id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    if request.method == 'PUT':
        data = request.get_json()
        c.execute('UPDATE expenses SET date=?, amount=?, category=?, description=? WHERE id=?',
                  (data['date'], data['amount'], data['category'], data.get('description', ''), id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        c.execute('DELETE FROM expenses WHERE id=?', (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/expenses')
def expenses_api():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM expenses ORDER BY date DESC')
    records = c.fetchall()
    conn.close()
    return jsonify([{
        'id': r[0],
        'date': r[1],
        'amount': r[2],
        'category': r[3],
        'description': r[4]
    } for r in records])

@app.route('/api/expense_stats/<period>')
def expense_stats_api(period):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    if period == 'day':
        c.execute('SELECT date, SUM(amount) FROM expenses GROUP BY date ORDER BY date DESC LIMIT 30')
    elif period == 'month':
        c.execute('SELECT strftime("%Y-%m", date) as month, SUM(amount) FROM expenses GROUP BY month ORDER BY month DESC LIMIT 12')
    else:
        c.execute('SELECT strftime("%Y", date) as year, SUM(amount) FROM expenses GROUP BY year ORDER BY year DESC LIMIT 5')
    
    records = c.fetchall()
    conn.close()
    
    labels = [r[0] for r in records]
    values = [r[1] for r in records]
    
    return jsonify({'labels': labels, 'values': values})

@app.route('/api/equipment')
def equipment_api():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM equipment')
    equipments = c.fetchall()
    conn.close()
    return jsonify([{
        'id': e[0],
        'name': e[1],
        'status': e[2],
        'lastMaintenance': e[3]
    } for e in equipments])

@app.route('/api/maintenance')
def maintenance_api():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM maintenance_tasks')
    tasks = c.fetchall()
    conn.close()
    return jsonify([{
        'id': t[0],
        'name': t[1],
        'currentValue': t[2],
        'maxValue': t[3],
        'unit': t[4]
    } for t in tasks])


@app.route('/ride-stats')
def ride_stats():
    return render_template('骑行统计.html')

@app.route('/expense-stats')
def expense_stats():
    return render_template('花销统计.html')

@app.route('/ride-map')
def ride_map():
    return render_template('骑行地图.html')

@app.route('/equipment')
def equipment():
    return render_template('装备维修.html')


@app.route('/food')
def food():
    return render_template('露营美食.html')

@app.route('/api/food/recipes')
def food_recipes_api():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    category = request.args.get('category', '')
    if category:
        c.execute('SELECT * FROM food_recipes WHERE category=? ORDER BY id DESC', (category,))
    else:
        c.execute('SELECT * FROM food_recipes ORDER BY id DESC')
    recipes = c.fetchall()
    conn.close()
    return jsonify([{
        'id': r[0],
        'name': r[1],
        'category': r[2],
        'difficulty': r[3],
        'cookTime': r[4],
        'calories': r[5],
        'equipment': r[6],
        'ingredients': r[7],
        'steps': r[8],
        'tips': r[9]
    } for r in recipes])

@app.route('/api/food/recipe', methods=['POST'])
def add_food_recipe():
    data = request.get_json()
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('INSERT INTO food_recipes (name, category, difficulty, cook_time, calories, equipment, ingredients, steps, tips) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
              (data['name'], data['category'], data['difficulty'], data['cookTime'], data['calories'], data['equipment'], data['ingredients'], data['steps'], data.get('tips', '')))
    conn.commit()
    record_id = c.lastrowid
    conn.close()
    return jsonify({'id': record_id, 'success': True})

@app.route('/api/food/recipe/<int:id>', methods=['PUT', 'DELETE'])
def modify_food_recipe(id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    if request.method == 'PUT':
        data = request.get_json()
        c.execute('UPDATE food_recipes SET name=?, category=?, difficulty=?, cook_time=?, calories=?, equipment=?, ingredients=?, steps=?, tips=? WHERE id=?',
                  (data['name'], data['category'], data['difficulty'], data['cookTime'], data['calories'], data['equipment'], data['ingredients'], data['steps'], data.get('tips', ''), id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        c.execute('DELETE FROM food_recipes WHERE id=?', (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/food/categories')
def food_categories_api():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT DISTINCT category FROM food_recipes ORDER BY category')
    categories = [r[0] for r in c.fetchall()]
    conn.close()
    return jsonify(categories)
if __name__ == '__main__':
    import sys
    from waitress import serve
    # Windows 下控制台设置 UTF-8 编码，避免 emoji 乱码
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
    init_db()
    # 启动后台备份线程（守护线程，主进程退出时自动结束）
    t = threading.Thread(target=backup_loop, daemon=True)
    t.start()
    print('⏰ 自动备份已启用（每天 00:00，保留最近30天）')
    if ACCESS_KEY == '123':
        print('⚠️ 使用默认密码 123，公网部署请设置 ACCESS_KEY 环境变量！')
    else:
        print('🔒 访问保护已开启（密码登入）')
    print('🚀 Waitress 生产服务器启动: http://0.0.0.0:5000')
    if os.environ.get('ACCESS_KEY'):
        print('🔒 访问保护已开启（密码登入）')
    serve(app, host='0.0.0.0', port=5000)
