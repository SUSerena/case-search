"""
数据库操作模块
支持 SQLite（本地开发）和 PostgreSQL（Render 部署）
通过环境变量 DATABASE_URL 切换：未设置或以 sqlite 开头 → SQLite；以 postgres 开头 → PostgreSQL
"""
import os
import sqlite3

# 检测数据库类型
DATABASE_URL = os.environ.get('DATABASE_URL', '')
USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith('postgres'))

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor

# SQLite 数据库路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'data', 'case_search.db')


# ====================== PostgreSQL 适配层 ======================

class _PgCursorWrapper:
    """包装 psycopg2 游标，自动将 SQLite 风格 SQL 转换为 PostgreSQL"""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        # ?  → %s
        sql = sql.replace('?', '%s')
        # datetime('now','localtime') → NOW()
        sql = sql.replace("datetime('now','localtime')", "NOW()")
        # AUTOINCREMENT → SERIAL（PostgreSQL 用 SERIAL 自增）
        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')

        if params is not None:
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        """获取最近 INSERT 的自增 ID"""
        self._cursor.execute("SELECT lastval() AS id")
        row = self._cursor.fetchone()
        return row['id'] if row else None

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _PgConnWrapper:
    """包装 psycopg2 连接，使 cursor() 返回包装后的游标"""

    def __init__(self, dsn):
        self._conn = psycopg2.connect(dsn)

    def cursor(self):
        c = self._conn.cursor(cursor_factory=RealDictCursor)
        return _PgCursorWrapper(c)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_conn():
    """获取数据库连接（自动适配 SQLite / PostgreSQL）"""
    if USE_POSTGRES:
        return _PgConnWrapper(DATABASE_URL)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_conn()
    cursor = conn.cursor()

    # 项目主表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_name TEXT NOT NULL,
        project_type TEXT NOT NULL,
        sales_person TEXT,
        confirm_date TEXT,
        location TEXT,
        province TEXT,
        sea_area TEXT,
        coordinates TEXT,
        project_scale TEXT,
        construction_period TEXT,
        budget TEXT,
        description TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    )
    ''')

    # 迁移：为旧数据库添加新字段
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN province TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN sea_area TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN project_scale TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN construction_period TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN budget TEXT")
    except:
        pass

    # 海况参数表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sea_conditions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        water_depth REAL,
        water_level_diff REAL,
        max_wave_height REAL,
        max_flow_speed REAL,
        flow_direction TEXT,
        seabed_type TEXT,
        common_wind_direction TEXT,
        max_wind_direction TEXT,
        max_wind_speed REAL,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    ''')

    # 网箱技术参数表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cage_params (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        pipe_diameter TEXT,
        perimeter REAL,
        diameter REAL,
        side_length REAL,
        bracket_spacing TEXT,
        walkway_width TEXT,
        mooring_sleeve TEXT,
        anchor_point_count INTEGER,
        net_demand TEXT,
        cage_count INTEGER,
        cage_type TEXT,
        cage_shape TEXT DEFAULT 'circle',
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    ''')

    # 迁移：为旧数据库添加新字段
    try:
        cursor.execute("ALTER TABLE cage_params ADD COLUMN cage_shape TEXT DEFAULT 'circle'")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE cage_params ADD COLUMN side_length REAL")
    except:
        pass

    # 平台技术参数表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS platform_params (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        pipe_diameter TEXT,
        size_spec TEXT,
        shape_requirement TEXT,
       附属设施 TEXT,
        bearing_capacity TEXT,
        docking_ships TEXT,
        platform_area REAL,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    ''')

    # 防波堤技术参数表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS breakwater_params (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        pipe_diameter TEXT,
        spec_type TEXT,
        bracket_spacing TEXT,
        wave_reduction_rate TEXT,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    ''')

    # 图纸文件表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS drawings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_type TEXT,
        file_size INTEGER,
        drawing_type TEXT,
        upload_time TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    ''')

    # 项目照片表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_type TEXT,
        file_size INTEGER,
        photo_type TEXT,
        upload_time TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    ''')

    # 材料统计表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        category TEXT,
        material_name TEXT,
        model TEXT,
        unit TEXT,
        quantity REAL,
        unit_weight REAL,
        total_weight REAL,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    ''')

    # 用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        phone TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        is_active INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'approved',
        created_at TEXT DEFAULT (datetime('now','localtime')),
        last_login TEXT
    )
    ''')

    # 迁移：为旧数据库添加 status 字段
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'")
    except:
        pass

    # 访问日志表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS access_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        phone TEXT,
        username TEXT,
        ip_address TEXT,
        user_agent TEXT,
        login_time TEXT DEFAULT (datetime('now','localtime')),
        action TEXT
    )
    ''')

    conn.commit()
    conn.close()


# ====================== 用户相关操作 ======================

def create_user(username, phone, password_hash, role='user', status='pending'):
    """创建用户，返回用户ID。新注册用户默认 status=pending"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO users (username, phone, password_hash, role, status)
    VALUES (?, ?, ?, ?, ?)
    ''', (username, phone, password_hash, role, status))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


def get_user_by_username(username):
    """通过用户名查询用户"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_phone(phone):
    """通过手机号查询用户"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE phone = ?', (phone,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    """通过ID查询用户"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users():
    """获取所有用户"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users ORDER BY id')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_last_login(user_id):
    """更新最后登录时间"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_login = datetime('now','localtime') WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def toggle_user_status(user_id, is_active):
    """启用/禁用用户（兼容旧代码）"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_active = ? WHERE id = ?', (is_active, user_id))
    conn.commit()
    conn.close()


def update_user_status(user_id, status):
    """更新用户审核状态: pending/approved/disabled"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET status = ? WHERE id = ?', (status, user_id))
    conn.commit()
    conn.close()


def delete_user(user_id):
    """删除用户"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()


def get_pending_user_count():
    """获取待审核用户数量"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM users WHERE status = 'pending'")
    total = cursor.fetchone()['total']
    conn.close()
    return total


# ====================== 访问日志 ======================

def add_access_log(user_id, phone, username, ip_address, user_agent, action):
    """记录访问日志"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO access_logs (user_id, phone, username, ip_address, user_agent, action)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, phone, username, ip_address, user_agent, action))
    conn.commit()
    conn.close()


def get_access_logs(page=1, page_size=20):
    """分页获取访问日志"""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) as total FROM access_logs')
    total = cursor.fetchone()['total']

    offset = (page - 1) * page_size
    cursor.execute('''
    SELECT * FROM access_logs ORDER BY id DESC LIMIT ? OFFSET ?
    ''', (page_size, offset))
    logs = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {'total': total, 'page': page, 'page_size': page_size, 'list': logs}


def project_exists(project_name):
    """检查项目是否已存在"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM projects WHERE project_name = ?', (project_name,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def update_project_fields(project_id, fields):
    """
    批量更新项目字段（只更新非空字段，不影响已有值）
    用于"补充已有项目资料"模式
    - 主表字段：UPDATE（只更新有值的字段）
    - 海况/网箱子表：存在则 UPDATE，不存在则 INSERT
    """
    conn = get_conn()
    cursor = conn.cursor()

    # ---- 主表字段 ----
    main_fields = ['project_name', 'project_type', 'sales_person', 'confirm_date',
                   'location', 'province', 'sea_area', 'coordinates', 'description',
                   'project_scale', 'construction_period', 'budget']
    updates = []
    params = []
    for f in main_fields:
        val = fields.get(f)
        if val is not None and str(val).strip():
            updates.append(f'{f} = ?')
            params.append(val)
    if updates:
        params.append(project_id)
        cursor.execute(f'UPDATE projects SET {", ".join(updates)} WHERE id = ?', params)

    # ---- 海况参数（UPDATE or INSERT）----
    sea = fields.get('sea_conditions', {})
    sea_map = {
        'water_depth': 'water_depth',
        'water_level_diff': 'water_level_diff',
        'max_wave_height': 'max_wave_height',
        'max_flow_speed': 'max_flow_speed',
        'flow_direction': 'flow_direction',
        'max_wind_speed': 'max_wind_speed',
        'common_wind_direction': 'common_wind_direction',
        'seabed_type': 'seabed_type',
    }
    sea_data = {}
    for field_name, db_col in sea_map.items():
        val = sea.get(field_name)
        if val is not None and str(val).strip():
            sea_data[db_col] = val
    if sea_data:
        cursor.execute('SELECT id FROM sea_conditions WHERE project_id = ?', (project_id,))
        existing = cursor.fetchone()
        if existing:
            set_clauses = ', '.join(f'{k} = ?' for k in sea_data)
            cursor.execute(f'UPDATE sea_conditions SET {set_clauses} WHERE project_id = ?',
                           list(sea_data.values()) + [project_id])
        else:
            cols = ['project_id'] + list(sea_data.keys())
            placeholders = ', '.join('?' for _ in cols)
            cursor.execute(f'INSERT INTO sea_conditions ({", ".join(cols)}) VALUES ({placeholders})',
                           [project_id] + list(sea_data.values()))

    # ---- 网箱参数（UPDATE or INSERT，支持圆形和方形）----
    cage_map = {
        'pipe_diameter': 'pipe_diameter',
        'perimeter': 'perimeter',
        'diameter': 'diameter',
        'side_length': 'side_length',
        'cage_type': 'cage_type',
        'cage_count': 'cage_count',
        'bracket_spacing': 'bracket_spacing',
        'walkway_width': 'walkway_width',
        'anchor_point_count': 'anchor_point_count',
        'net_demand': 'net_demand',
    }
    # 检查 cage_params_circle, cage_params_square, cage_params (兼容)
    for source_key, default_shape in [('cage_params_circle', 'circle'),
                                       ('cage_params_square', 'square'),
                                       ('cage_params', None)]:
        cage = fields.get(source_key, {})
        if not cage:
            continue
        shape = cage.get('cage_shape') or default_shape or 'circle'
        cage_data = {}
        for field_name, db_col in cage_map.items():
            val = cage.get(field_name)
            if val is not None and str(val).strip():
                cage_data[db_col] = val
        if not cage_data:
            continue
        # 按 shape 查找已有记录
        cursor.execute('SELECT id FROM cage_params WHERE project_id = ? AND cage_shape = ?',
                       (project_id, shape))
        existing = cursor.fetchone()
        if existing:
            set_clauses = ', '.join(f'{k} = ?' for k in cage_data)
            cursor.execute(f'UPDATE cage_params SET {set_clauses} WHERE project_id = ? AND cage_shape = ?',
                           list(cage_data.values()) + [project_id, shape])
        else:
            cols = ['project_id', 'cage_shape'] + list(cage_data.keys())
            placeholders = ', '.join('?' for _ in cols)
            cursor.execute(f'INSERT INTO cage_params ({", ".join(cols)}) VALUES ({placeholders})',
                           [project_id, shape] + list(cage_data.values()))

    conn.commit()
    conn.close()


def insert_project(data):
    """
    插入新项目
    data: dict 包含项目所有信息
    返回: 新插入的项目ID
    """
    conn = get_conn()
    cursor = conn.cursor()

    # 插入主表
    cursor.execute('''
    INSERT INTO projects (project_name, project_type, sales_person, confirm_date, 
                          location, province, sea_area, coordinates,
                          project_scale, construction_period, budget, description)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('project_name', ''),
        data.get('project_type', ''),
        data.get('sales_person', ''),
        data.get('confirm_date', ''),
        data.get('location', ''),
        data.get('province', ''),
        data.get('sea_area', ''),
        data.get('coordinates', ''),
        data.get('project_scale', ''),
        data.get('construction_period', ''),
        data.get('budget', ''),
        data.get('description', '')
    ))
    project_id = cursor.lastrowid

    # 插入海况参数
    sea = data.get('sea_conditions', {})
    if sea:
        cursor.execute('''
        INSERT INTO sea_conditions (project_id, water_depth, water_level_diff, max_wave_height,
                                     max_flow_speed, flow_direction, seabed_type,
                                     common_wind_direction, max_wind_direction, max_wind_speed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_id,
            sea.get('water_depth'),
            sea.get('water_level_diff'),
            sea.get('max_wave_height'),
            sea.get('max_flow_speed'),
            sea.get('flow_direction', ''),
            sea.get('seabed_type', ''),
            sea.get('common_wind_direction', ''),
            sea.get('max_wind_direction', ''),
            sea.get('max_wind_speed')
        ))

    # 插入网箱参数 — 支持圆形和方形
    for shape_key, shape_val in [('cage_params_circle', 'circle'), ('cage_params_square', 'square'), ('cage_params', None)]:
        cage = data.get(shape_key, {})
        if not cage:
            continue
        shape = cage.get('cage_shape') or shape_val or 'circle'
        cursor.execute('''
        INSERT INTO cage_params (project_id, pipe_diameter, perimeter, diameter, side_length,
                                  bracket_spacing, walkway_width, mooring_sleeve, anchor_point_count,
                                  net_demand, cage_count, cage_type, cage_shape)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_id,
            cage.get('pipe_diameter', ''),
            cage.get('perimeter'),
            cage.get('diameter'),
            cage.get('side_length'),
            cage.get('bracket_spacing', ''),
            cage.get('walkway_width', ''),
            cage.get('mooring_sleeve', ''),
            cage.get('anchor_point_count'),
            cage.get('net_demand', ''),
            cage.get('cage_count'),
            cage.get('cage_type', ''),
            shape
        ))

    # 插入平台参数
    platform = data.get('platform_params', {})
    if platform:
        cursor.execute('''
        INSERT INTO platform_params (project_id, pipe_diameter, size_spec, shape_requirement,
                                      附属设施, bearing_capacity, docking_ships, platform_area)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_id,
            platform.get('pipe_diameter', ''),
            platform.get('size_spec', ''),
            platform.get('shape_requirement', ''),
            platform.get('附属设施', ''),
            platform.get('bearing_capacity', ''),
            platform.get('docking_ships', ''),
            platform.get('platform_area')
        ))

    # 插入防波堤参数
    breakwater = data.get('breakwater_params', {})
    if breakwater:
        cursor.execute('''
        INSERT INTO breakwater_params (project_id, pipe_diameter, spec_type, bracket_spacing,
                                        wave_reduction_rate)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            project_id,
            breakwater.get('pipe_diameter', ''),
            breakwater.get('spec_type', ''),
            breakwater.get('bracket_spacing', ''),
            breakwater.get('wave_reduction_rate', '')
        ))

    conn.commit()
    conn.close()
    return project_id


def get_project_list(page=1, page_size=20, project_type=None, keyword=None):
    """获取项目列表"""
    conn = get_conn()
    cursor = conn.cursor()

    where_clauses = []
    params = []

    if project_type and project_type != 'all':
        where_clauses.append('p.project_type LIKE ?')
        params.append(f'%{project_type}%')

    if keyword:
        where_clauses.append('(p.project_name LIKE ? OR p.description LIKE ? OR p.location LIKE ?)')
        kw = f'%{keyword}%'
        params.extend([kw, kw, kw])

    where_sql = ''
    if where_clauses:
        where_sql = 'WHERE ' + ' AND '.join(where_clauses)

    # 总数
    cursor.execute(f'SELECT COUNT(*) as total FROM projects p {where_sql}', params)
    total = cursor.fetchone()['total']

    # 分页数据
    offset = (page - 1) * page_size
    cursor.execute(f'''
    SELECT p.*, 
           sc.water_depth, sc.max_wave_height, sc.max_flow_speed,
           cp.pipe_diameter as cage_pipe_dia, cp.perimeter, cp.diameter, cp.cage_count,
           pp.pipe_diameter as platform_pipe_dia, pp.platform_area
    FROM projects p
    LEFT JOIN sea_conditions sc ON p.id = sc.project_id
    LEFT JOIN cage_params cp ON p.id = cp.project_id
    LEFT JOIN platform_params pp ON p.id = pp.project_id
    {where_sql}
    ORDER BY p.id DESC
    LIMIT ? OFFSET ?
    ''', params + [page_size, offset])

    projects = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {
        'total': total,
        'page': page,
        'page_size': page_size,
        'list': projects
    }


def get_project_detail(project_id):
    """获取项目详情"""
    conn = get_conn()
    cursor = conn.cursor()

    # 主信息
    cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
    project = cursor.fetchone()
    if not project:
        conn.close()
        return None
    project = dict(project)

    # 海况
    cursor.execute('SELECT * FROM sea_conditions WHERE project_id = ?', (project_id,))
    sea = cursor.fetchone()
    project['sea_conditions'] = dict(sea) if sea else {}

    # 网箱参数 — 支持圆形和方形两种
    cursor.execute('SELECT * FROM cage_params WHERE project_id = ?', (project_id,))
    cage_rows = cursor.fetchall()
    project['cage_params_circle'] = {}
    project['cage_params_square'] = {}
    project['cage_params'] = {}  # 兼容旧代码
    for row in cage_rows:
        row_dict = dict(row)
        shape = row_dict.get('cage_shape', 'circle')
        if shape == 'square':
            project['cage_params_square'] = row_dict
        else:
            project['cage_params_circle'] = row_dict
            project['cage_params'] = row_dict  # 兼容旧代码（优先圆形）

    # 平台参数
    cursor.execute('SELECT * FROM platform_params WHERE project_id = ?', (project_id,))
    platform = cursor.fetchone()
    project['platform_params'] = dict(platform) if platform else {}

    # 防波堤参数
    cursor.execute('SELECT * FROM breakwater_params WHERE project_id = ?', (project_id,))
    breakwater = cursor.fetchone()
    project['breakwater_params'] = dict(breakwater) if breakwater else {}

    # 图纸
    cursor.execute('SELECT * FROM drawings WHERE project_id = ? ORDER BY id', (project_id,))
    project['drawings'] = [dict(row) for row in cursor.fetchall()]

    # 照片
    cursor.execute('SELECT * FROM photos WHERE project_id = ? ORDER BY id', (project_id,))
    project['photos'] = [dict(row) for row in cursor.fetchall()]

    # 材料
    cursor.execute('SELECT * FROM materials WHERE project_id = ? ORDER BY category, id', (project_id,))
    project['materials'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return project


def add_drawing(project_id, file_name, file_path, file_type, file_size, drawing_type=''):
    """添加图纸记录"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO drawings (project_id, file_name, file_path, file_type, file_size, drawing_type)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (project_id, file_name, file_path, file_type, file_size, drawing_type))
    conn.commit()
    conn.close()


def add_photo(project_id, file_name, file_path, file_type, file_size, photo_type=''):
    """添加照片记录"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO photos (project_id, file_name, file_path, file_type, file_size, photo_type)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (project_id, file_name, file_path, file_type, file_size, photo_type))
    conn.commit()
    conn.close()


# ====================== 删除/替换操作 ======================

def delete_project(project_id):
    """删除项目及其所有关联数据（级联删除）"""
    conn = get_conn()
    cursor = conn.cursor()
    # 删除关联表
    cursor.execute('DELETE FROM drawings WHERE project_id = ?', (project_id,))
    cursor.execute('DELETE FROM photos WHERE project_id = ?', (project_id,))
    cursor.execute('DELETE FROM materials WHERE project_id = ?', (project_id,))
    cursor.execute('DELETE FROM sea_conditions WHERE project_id = ?', (project_id,))
    cursor.execute('DELETE FROM cage_params WHERE project_id = ?', (project_id,))
    cursor.execute('DELETE FROM platform_params WHERE project_id = ?', (project_id,))
    cursor.execute('DELETE FROM breakwater_params WHERE project_id = ?', (project_id,))
    cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    conn.commit()
    conn.close()


def delete_drawing(drawing_id):
    """删除图纸记录，返回文件路径供删除文件"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT file_path FROM drawings WHERE id = ?', (drawing_id,))
    row = cursor.fetchone()
    file_path = dict(row)['file_path'] if row else None
    cursor.execute('DELETE FROM drawings WHERE id = ?', (drawing_id,))
    conn.commit()
    conn.close()
    return file_path


def delete_photo(photo_id):
    """删除照片记录，返回文件路径供删除文件"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT file_path FROM photos WHERE id = ?', (photo_id,))
    row = cursor.fetchone()
    file_path = dict(row)['file_path'] if row else None
    cursor.execute('DELETE FROM photos WHERE id = ?', (photo_id,))
    conn.commit()
    conn.close()
    return file_path


def replace_drawing(drawing_id, file_name, file_path, file_type, file_size):
    """替换图纸文件信息"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE drawings SET file_name = ?, file_path = ?, file_type = ?, file_size = ?
    WHERE id = ?
    ''', (file_name, file_path, file_type, file_size, drawing_id))
    conn.commit()
    conn.close()


def replace_photo(photo_id, file_name, file_path, file_type, file_size):
    """替换照片文件信息"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE photos SET file_name = ?, file_path = ?, file_type = ?, file_size = ?
    WHERE id = ?
    ''', (file_name, file_path, file_type, file_size, photo_id))
    conn.commit()
    conn.close()


def add_materials(project_id, materials_list):
    """批量添加材料记录"""
    if not materials_list:
        return
    conn = get_conn()
    cursor = conn.cursor()
    for m in materials_list:
        cursor.execute('''
        INSERT INTO materials (project_id, category, material_name, model, unit, 
                               quantity, unit_weight, total_weight)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_id,
            m.get('category', ''),
            m.get('material_name', ''),
            m.get('model', ''),
            m.get('unit', ''),
            m.get('quantity'),
            m.get('unit_weight'),
            m.get('total_weight')
        ))
    conn.commit()
    conn.close()


def get_all_projects_for_matching():
    """获取所有项目用于匹配计算"""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute('''
    SELECT p.*,
           sc.water_depth, sc.water_level_diff, sc.max_wave_height, sc.max_flow_speed,
           sc.flow_direction, sc.seabed_type, sc.max_wind_speed,
           cp.pipe_diameter as cage_pipe_dia, cp.perimeter, cp.diameter,
           cp.anchor_point_count, cp.cage_count, cp.cage_type, cp.net_demand,
           cp.walkway_width,
           pp.pipe_diameter as platform_pipe_dia, pp.platform_area, pp.size_spec,
           bp.pipe_diameter as breakwater_pipe_dia, bp.spec_type, bp.wave_reduction_rate
    FROM projects p
    LEFT JOIN sea_conditions sc ON p.id = sc.project_id
    LEFT JOIN cage_params cp ON p.id = cp.project_id
    LEFT JOIN platform_params pp ON p.id = pp.project_id
    LEFT JOIN breakwater_params bp ON p.id = bp.project_id
    ORDER BY p.id
    ''')

    projects = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return projects


def update_project(project_id, data):
    """
    更新项目信息
    project_id: 项目ID
    data: dict 包含要更新的字段
    """
    conn = get_conn()
    cursor = conn.cursor()

    # 更新主表
    cursor.execute('''
    UPDATE projects SET 
        project_name = ?,
        project_type = ?,
        sales_person = ?,
        confirm_date = ?,
        location = ?,
        province = ?,
        sea_area = ?,
        coordinates = ?,
        project_scale = ?,
        construction_period = ?,
        budget = ?,
        description = ?,
        updated_at = datetime('now','localtime')
    WHERE id = ?
    ''', (
        data.get('project_name', ''),
        data.get('project_type', ''),
        data.get('sales_person', ''),
        data.get('confirm_date', ''),
        data.get('location', ''),
        data.get('province', ''),
        data.get('sea_area', ''),
        data.get('coordinates', ''),
        data.get('project_scale', ''),
        data.get('construction_period', ''),
        data.get('budget', ''),
        data.get('description', ''),
        project_id
    ))

    # 更新海况参数
    sea = data.get('sea_conditions', {})
    if sea:
        cursor.execute('SELECT id FROM sea_conditions WHERE project_id = ?', (project_id,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute('''
            UPDATE sea_conditions SET
                water_depth = ?,
                water_level_diff = ?,
                max_wave_height = ?,
                max_flow_speed = ?,
                flow_direction = ?,
                seabed_type = ?,
                common_wind_direction = ?,
                max_wind_direction = ?,
                max_wind_speed = ?
            WHERE project_id = ?
            ''', (
                sea.get('water_depth'),
                sea.get('water_level_diff'),
                sea.get('max_wave_height'),
                sea.get('max_flow_speed'),
                sea.get('flow_direction', ''),
                sea.get('seabed_type', ''),
                sea.get('common_wind_direction', ''),
                sea.get('max_wind_direction', ''),
                sea.get('max_wind_speed'),
                project_id
            ))
        else:
            cursor.execute('''
            INSERT INTO sea_conditions (project_id, water_depth, water_level_diff, max_wave_height,
                                         max_flow_speed, flow_direction, seabed_type,
                                         common_wind_direction, max_wind_direction, max_wind_speed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                project_id,
                sea.get('water_depth'),
                sea.get('water_level_diff'),
                sea.get('max_wave_height'),
                sea.get('max_flow_speed'),
                sea.get('flow_direction', ''),
                sea.get('seabed_type', ''),
                sea.get('common_wind_direction', ''),
                sea.get('max_wind_direction', ''),
                sea.get('max_wind_speed')
            ))

    # 更新网箱参数 — 支持圆形和方形
    # 先删除旧记录，再插入新记录
    cursor.execute('DELETE FROM cage_params WHERE project_id = ?', (project_id,))
    for shape_key, shape_val in [('cage_params_circle', 'circle'), ('cage_params_square', 'square'), ('cage_params', None)]:
        cage = data.get(shape_key, {})
        if not cage:
            continue
        shape = cage.get('cage_shape') or shape_val or 'circle'
        cursor.execute('''
        INSERT INTO cage_params (project_id, pipe_diameter, perimeter, diameter, side_length,
                                  bracket_spacing, walkway_width, mooring_sleeve, anchor_point_count,
                                  net_demand, cage_count, cage_type, cage_shape)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_id,
            cage.get('pipe_diameter', ''),
            cage.get('perimeter'),
            cage.get('diameter'),
            cage.get('side_length'),
            cage.get('bracket_spacing', ''),
            cage.get('walkway_width', ''),
            cage.get('mooring_sleeve', ''),
            cage.get('anchor_point_count'),
            cage.get('net_demand', ''),
            cage.get('cage_count'),
            cage.get('cage_type', ''),
            shape
        ))

    # 更新平台参数
    platform = data.get('platform_params', {})
    if platform:
        cursor.execute('SELECT id FROM platform_params WHERE project_id = ?', (project_id,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute('''
            UPDATE platform_params SET
                pipe_diameter = ?,
                size_spec = ?,
                shape_requirement = ?,
                附属设施 = ?,
                bearing_capacity = ?,
                docking_ships = ?,
                platform_area = ?
            WHERE project_id = ?
            ''', (
                platform.get('pipe_diameter', ''),
                platform.get('size_spec', ''),
                platform.get('shape_requirement', ''),
                platform.get('附属设施', ''),
                platform.get('bearing_capacity', ''),
                platform.get('docking_ships', ''),
                platform.get('platform_area'),
                project_id
            ))
        else:
            cursor.execute('''
            INSERT INTO platform_params (project_id, pipe_diameter, size_spec, shape_requirement,
                                          附属设施, bearing_capacity, docking_ships, platform_area)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                project_id,
                platform.get('pipe_diameter', ''),
                platform.get('size_spec', ''),
                platform.get('shape_requirement', ''),
                platform.get('附属设施', ''),
                platform.get('bearing_capacity', ''),
                platform.get('docking_ships', ''),
                platform.get('platform_area')
            ))

    # 更新防波堤参数
    breakwater = data.get('breakwater_params', {})
    if breakwater:
        cursor.execute('SELECT id FROM breakwater_params WHERE project_id = ?', (project_id,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute('''
            UPDATE breakwater_params SET
                pipe_diameter = ?,
                spec_type = ?,
                bracket_spacing = ?,
                wave_reduction_rate = ?
            WHERE project_id = ?
            ''', (
                breakwater.get('pipe_diameter', ''),
                breakwater.get('spec_type', ''),
                breakwater.get('bracket_spacing', ''),
                breakwater.get('wave_reduction_rate', ''),
                project_id
            ))
        else:
            cursor.execute('''
            INSERT INTO breakwater_params (project_id, pipe_diameter, spec_type, bracket_spacing,
                                            wave_reduction_rate)
            VALUES (?, ?, ?, ?, ?)
            ''', (
                project_id,
                breakwater.get('pipe_diameter', ''),
                breakwater.get('spec_type', ''),
                breakwater.get('bracket_spacing', ''),
                breakwater.get('wave_reduction_rate', '')
            ))

    conn.commit()
    conn.close()
    return True
