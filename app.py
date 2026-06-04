from flask import Flask, render_template, jsonify, request
import sqlite3
import os

app = Flask(__name__)
DATABASE = 'ride.db'

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS profile
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  nickname TEXT,
                  motto TEXT,
                  location TEXT)''')
    
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

    if not c.execute('SELECT * FROM profile').fetchone():
        c.execute('INSERT INTO profile (nickname, motto, location) VALUES (?, ?, ?)',
                  ('一禄', '每一次踩踏，都是向自由的靠近', '北京'))
    
    if not c.execute('SELECT * FROM stats').fetchone():
        c.execute('INSERT INTO stats (total_km, total_cost, maintenance_status) VALUES (?, ?, ?)',
                  (468, 2680, '良好'))
    
    if not c.execute('SELECT * FROM ride_records').fetchone():
        records = [
            ('2026-05-04', 35.5, 22.3, '周末骑行'),
            ('2026-05-03', 28.8, 20.1, '日常通勤'),
            ('2026-05-02', 42.1, 24.5, '郊区骑行'),
            ('2026-05-01', 55.0, 21.8, '假期长途'),
            ('2026-04-30', 18.3, 19.2, '傍晚骑行'),
        ]
        c.executemany('INSERT INTO ride_records (date, distance, avg_speed, note) VALUES (?, ?, ?, ?)', records)
    
    if not c.execute('SELECT * FROM expenses').fetchone():
        expenses = [
            ('2026-05-04', 180, '装备', '刹车皮'),
            ('2026-05-03', 50, '餐饮', '骑行后加餐'),
            ('2026-05-02', 320, '装备', '新轮胎'),
            ('2026-05-01', 150, '交通', '停车费'),
            ('2026-04-30', 80, '餐饮', '能量补给'),
        ]
        c.executemany('INSERT INTO expenses (date, amount, category, description) VALUES (?, ?, ?, ?)', expenses)
    
    if not c.execute('SELECT * FROM equipment').fetchone():
        equipments = [
            ('自行车', '良好', '2026-05-01'),
            ('骑行眼镜', '一般', '2026-04-15'),
            ('头盔', '良好', '2026-05-01'),
            ('骑行手套', '需维修', '2026-03-20'),
            ('骑行服', '良好', '2026-04-01'),
            ('骑行鞋', '一般', '2026-03-10'),
        ]
        c.executemany('INSERT INTO equipment (name, status, last_maintenance) VALUES (?, ?, ?)', equipments)
    
    if not c.execute('SELECT * FROM maintenance_tasks').fetchone():
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
        'location': profile[3]
    })

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
    init_db()
    app.run(debug=False, host='0.0.0.0', port=5000)
