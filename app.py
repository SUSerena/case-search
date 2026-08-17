"""
深水网箱/浮动平台历史案例智能检索系统
Flask 主应用
"""
import os
import sys
import json
from datetime import datetime

# 确保项目根目录在路径中
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, session
from utils.db import (
    init_db, get_project_list, get_project_detail,
    project_exists, insert_project, add_drawing, add_photo,
    get_all_projects_for_matching, update_project, get_conn,
    get_all_users, toggle_user_status, get_access_logs,
    update_user_status, delete_user, get_pending_user_count,
    delete_project, delete_drawing, delete_photo,
    replace_drawing, replace_photo
)
from utils.matcher import match_projects
from utils.parser import parse_project_excel, import_project_from_excel, parse_smart
from utils.tender_parser import parse_tender_document, get_supported_formats
from utils.init_data import init_sample_data
from utils.location import get_all_sea_areas
from utils.auth import login_required, admin_required, do_login, do_register, do_logout, current_user, is_logged_in

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB 上传限制
app.secret_key = os.environ.get('SECRET_KEY', 'case-search-secret-2026')

# 确保数据目录存在
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, 'drawings'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, 'photos'), exist_ok=True)


# ====================== 全局登录拦截 ======================
# 无需登录的白名单路由
_PUBLIC_ENDPOINTS = {'login', 'register', 'logout', 'static'}


@app.before_request
def _check_login():
    """所有非白名单路由都需要登录"""
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return None
    if not is_logged_in():
        return redirect(url_for('login'))
    return None


# ====================== 页面路由 ======================

@app.route('/')
@login_required
def index():
    """首页 - 项目案例库"""
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 12, type=int)
    project_type = request.args.get('type', 'all')
    keyword = request.args.get('keyword', '')

    result = get_project_list(page=page, page_size=page_size,
                              project_type=project_type, keyword=keyword)

    # 计算总页数
    total_pages = (result['total'] + page_size - 1) // page_size

    return render_template('index.html',
                           projects=result['list'],
                           total=result['total'],
                           page=page,
                           page_size=page_size,
                           total_pages=total_pages,
                           project_type=project_type,
                           keyword=keyword)


@app.route('/search')
@login_required
def search_page():
    """智能检索页"""
    return render_template('search.html')


@app.route('/project/<int:project_id>')
@login_required
def project_detail(project_id):
    """案例详情页"""
    project = get_project_detail(project_id)
    if not project:
        return "项目不存在", 404
    return render_template('detail.html', project=project)


@app.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def project_edit(project_id):
    """案例编辑页"""
    project = get_project_detail(project_id)
    if not project:
        return "项目不存在", 404

    if request.method == 'POST':
        # 保存修改
        data = _parse_project_form(request.form)
        update_project(project_id, data)
        return redirect(url_for('project_detail', project_id=project_id))

    return render_template('edit.html', project=project, sea_areas=get_all_sea_areas())


# ====================== 删除/替换操作 ======================

def _safe_remove_file(file_path):
    """安全删除文件"""
    if file_path:
        full_path = os.path.join(BASE_DIR, file_path) if not os.path.isabs(file_path) else file_path
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception:
            pass


@app.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
def project_delete(project_id):
    """删除案例（级联删除）"""
    project = get_project_detail(project_id)
    if not project:
        return "项目不存在", 404
    # 删除关联文件
    for d in project.get('drawings', []):
        _safe_remove_file(d.get('file_path'))
    for p in project.get('photos', []):
        _safe_remove_file(p.get('file_path'))
    delete_project(project_id)
    return redirect(url_for('index', deleted='1'))


@app.route('/project/<int:project_id>/drawing/<int:drawing_id>/delete', methods=['POST'])
@login_required
def drawing_delete(project_id, drawing_id):
    """删除单张图纸"""
    file_path = delete_drawing(drawing_id)
    _safe_remove_file(file_path)
    return redirect(url_for('project_detail', project_id=project_id))


@app.route('/project/<int:project_id>/drawing/<int:drawing_id>/replace', methods=['POST'])
@login_required
def drawing_replace(project_id, drawing_id):
    """替换图纸文件"""
    if 'file' not in request.files:
        return redirect(url_for('project_detail', project_id=project_id))
    f = request.files['file']
    if not f.filename:
        return redirect(url_for('project_detail', project_id=project_id))

    # 保存旧路径，稍后删除旧文件
    old_path = None
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT file_path FROM drawings WHERE id = ?', (drawing_id,))
    row = cur.fetchone()
    if row:
        old_path = dict(row)['file_path']
    conn.close()

    upload_dir = os.path.join(BASE_DIR, 'static', 'uploads', 'drawings')
    os.makedirs(upload_dir, exist_ok=True)
    import uuid
    ext = os.path.splitext(f.filename)[1].lower()
    new_name = f'drawing_{project_id}_{uuid.uuid4().hex[:8]}{ext}'
    save_path = os.path.join(upload_dir, new_name)
    f.save(save_path)
    rel_path = os.path.join('static', 'uploads', 'drawings', new_name)

    replace_drawing(drawing_id, f.filename, rel_path, ext.lstrip('.'), os.path.getsize(save_path))
    _safe_remove_file(old_path)
    return redirect(url_for('project_detail', project_id=project_id))


@app.route('/project/<int:project_id>/photo/<int:photo_id>/delete', methods=['POST'])
@login_required
def photo_delete(project_id, photo_id):
    """删除单张照片"""
    file_path = delete_photo(photo_id)
    _safe_remove_file(file_path)
    return redirect(url_for('project_detail', project_id=project_id))


@app.route('/project/<int:project_id>/photo/<int:photo_id>/replace', methods=['POST'])
@login_required
def photo_replace(project_id, photo_id):
    """替换照片文件"""
    if 'file' not in request.files:
        return redirect(url_for('project_detail', project_id=project_id))
    f = request.files['file']
    if not f.filename:
        return redirect(url_for('project_detail', project_id=project_id))

    old_path = None
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT file_path FROM photos WHERE id = ?', (photo_id,))
    row = cur.fetchone()
    if row:
        old_path = dict(row)['file_path']
    conn.close()

    upload_dir = os.path.join(BASE_DIR, 'static', 'uploads', 'photos')
    os.makedirs(upload_dir, exist_ok=True)
    import uuid
    ext = os.path.splitext(f.filename)[1].lower()
    new_name = f'photo_{project_id}_{uuid.uuid4().hex[:8]}{ext}'
    save_path = os.path.join(upload_dir, new_name)
    f.save(save_path)
    rel_path = os.path.join('static', 'uploads', 'photos', new_name)

    replace_photo(photo_id, f.filename, rel_path, ext.lstrip('.'), os.path.getsize(save_path))
    _safe_remove_file(old_path)
    return redirect(url_for('project_detail', project_id=project_id))


@app.route('/import')
@login_required
def import_page():
    """数据导入页"""
    return render_template('import.html')


# ====================== 认证路由 ======================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页"""
    if current_user():
        return redirect(url_for('index'))

    if request.method == 'POST':
        username_or_phone = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        success, message, user = do_login(username_or_phone, password)
        if success:
            return redirect(url_for('index'))
        return render_template('login.html', error=message, username=username_or_phone)

    # 注册成功后的提示
    info = None
    if request.args.get('registered') == '1':
        info = '注册成功，您的账号正在等待管理员审核，审核通过后即可登录使用'

    return render_template('login.html', info=info)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """注册页"""
    if current_user():
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')

        success, message, user = do_register(username, phone, password)
        if success:
            # 注册成功，跳转登录页并显示提示
            return redirect(url_for('login', registered='1'))
        return render_template('register.html', error=message,
                               username=username, phone=phone)

    return render_template('register.html')


@app.route('/logout')
def logout():
    """登出"""
    do_logout()
    return redirect(url_for('login'))


# ====================== 管理后台 ======================

@app.route('/admin/users')
@admin_required
def admin_users():
    """用户管理"""
    users = get_all_users()
    pending_count = get_pending_user_count()
    return render_template('admin_users.html', users=users, pending_count=pending_count)


@app.route('/admin/users/<int:user_id>/approve', methods=['POST'])
@admin_required
def admin_approve_user(user_id):
    """通过审核"""
    update_user_status(user_id, 'approved')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/reject', methods=['POST'])
@admin_required
def admin_reject_user(user_id):
    """拒绝注册（删除用户）"""
    delete_user(user_id)
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/disable', methods=['POST'])
@admin_required
def admin_disable_user(user_id):
    """禁用用户"""
    update_user_status(user_id, 'disabled')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/enable', methods=['POST'])
@admin_required
def admin_enable_user(user_id):
    """启用用户"""
    update_user_status(user_id, 'approved')
    return redirect(url_for('admin_users'))


@app.route('/admin/logs')
@admin_required
def admin_logs():
    """访问日志"""
    page = request.args.get('page', 1, type=int)
    page_size = 20
    result = get_access_logs(page=page, page_size=page_size)
    total_pages = (result['total'] + page_size - 1) // page_size
    return render_template('admin_logs.html',
                           logs=result['list'],
                           total=result['total'],
                           page=page,
                           total_pages=total_pages)


# ====================== API 接口 ======================

@app.route('/api/search', methods=['POST'])
def api_search():
    """智能检索API"""
    query = request.get_json() or {}

    # 获取所有项目
    all_projects = get_all_projects_for_matching()

    if not all_projects:
        return jsonify({
            'success': True,
            'results': [],
            'total': 0,
            'message': '暂无项目数据'
        })

    # 执行匹配
    results = match_projects(query, all_projects, top_n=20)

    return jsonify({
        'success': True,
        'results': results,
        'total': len(results),
        'query': query
    })


@app.route('/api/projects', methods=['GET'])
def api_projects():
    """获取项目列表API"""
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    project_type = request.args.get('type', 'all')
    keyword = request.args.get('keyword', '')

    result = get_project_list(page=page, page_size=page_size,
                              project_type=project_type, keyword=keyword)
    return jsonify({
        'success': True,
        'data': result
    })


@app.route('/api/projects/<int:project_id>', methods=['GET'])
def api_project_detail(project_id):
    """获取项目详情API"""
    project = get_project_detail(project_id)
    if not project:
        return jsonify({'success': False, 'message': '项目不存在'}), 404
    return jsonify({'success': True, 'data': project})


@app.route('/api/import/excel', methods=['POST'])
def api_import_excel():
    """智能识别导入项目信息（支持Excel/Word/PDF/TXT）"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '请选择文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '请选择文件'}), 400

    # 保存文件
    filename = file.filename
    save_path = os.path.join(UPLOAD_DIR, 'temp', filename)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file.save(save_path)

    try:
        # 智能识别解析
        data, raw_text, file_format = parse_smart(save_path)

        # 删除临时文件
        try:
            os.remove(save_path)
        except:
            pass

        return jsonify({
            'success': True,
            'message': f'智能识别完成（{file_format}格式）',
            'parsed_data': data,
            'raw_text': raw_text[:5000],
            'file_format': file_format
        })

    except Exception as e:
        # 删除临时文件
        try:
            os.remove(save_path)
        except:
            pass
        return jsonify({'success': False, 'message': f'解析失败：{str(e)}'}), 500


@app.route('/api/import/confirm', methods=['POST'])
def api_import_confirm():
    """确认导入：用户确认智能识别结果后保存"""
    data = request.get_json() or {}

    project_name = data.get('project_name', '').strip()
    if not project_name:
        return jsonify({'success': False, 'message': '项目名称不能为空'}), 400

    if project_exists(project_name):
        return jsonify({'success': False, 'message': f"项目 '{project_name}' 已存在"}), 400

    try:
        project_id = insert_project(data)
        return jsonify({
            'success': True,
            'message': f'导入成功：{project_name}',
            'project_id': project_id
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存失败：{str(e)}'}), 500


# ====================== 文件服务 ======================

@app.route('/file/drawing/<int:file_id>')
def serve_drawing(file_id):
    """通过ID提供图纸文件下载/预览，避免URL编码问题"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM drawings WHERE id = ?', (file_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return "文件不存在", 404

    file_path = row['file_path']
    # 转换为绝对路径
    if not os.path.isabs(file_path):
        abs_path = os.path.join(BASE_DIR, file_path)
    else:
        abs_path = file_path

    if not os.path.exists(abs_path):
        return "文件不存在", 404

    file_name = row['file_name']
    return send_from_directory(
        os.path.dirname(abs_path),
        os.path.basename(abs_path),
        as_attachment=False,
        download_name=file_name
    )


@app.route('/file/photo/<int:file_id>')
def serve_photo(file_id):
    """通过ID提供照片文件"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM photos WHERE id = ?', (file_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return "文件不存在", 404

    file_path = row['file_path']
    if not os.path.isabs(file_path):
        abs_path = os.path.join(BASE_DIR, file_path)
    else:
        abs_path = file_path

    if not os.path.exists(abs_path):
        return "文件不存在", 404

    return send_from_directory(
        os.path.dirname(abs_path),
        os.path.basename(abs_path),
        as_attachment=False,
        download_name=row['file_name']
    )


@app.route('/api/upload/drawing/<int:project_id>', methods=['POST'])
def api_upload_drawing(project_id):
    """上传图纸文件"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '请选择文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '请选择文件'}), 400

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    # 支持的格式：PDF、图片、CAD图纸、Excel材料表
    supported_exts = ['.pdf', '.png', '.jpg', '.jpeg', '.gif', '.bmp',
                      '.dwg', '.dxf', '.xls', '.xlsx']
    if ext not in supported_exts:
        return jsonify({'success': False, 'message': '不支持的文件格式，支持PDF/图片/CAD/Excel'}), 400

    # 保存文件
    save_name = f"{project_id}_{int(datetime.now().timestamp())}_{filename}"
    save_path = os.path.join(UPLOAD_DIR, 'drawings', save_name)
    file.save(save_path)

    file_size = os.path.getsize(save_path)

    # 确定文件类型
    if ext == '.pdf':
        file_type = 'pdf'
    elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
        file_type = 'image'
    elif ext in ['.dwg', '.dxf']:
        file_type = 'cad'
    else:
        file_type = 'excel'

    # 识别图纸类型
    drawing_type = request.form.get('drawing_type', '')
    if not drawing_type:
        if '框架' in filename:
            drawing_type = '框架图'
        elif '锚固' in filename:
            drawing_type = '锚固图'
        elif '平面' in filename or '布局' in filename:
            drawing_type = '总平面图'
        elif '材料' in filename:
            drawing_type = '材料统计'
        elif ext in ['.dwg', '.dxf']:
            drawing_type = 'CAD图纸'

    add_drawing(project_id, filename, f'static/uploads/drawings/{save_name}',
                file_type, file_size, drawing_type)

    return jsonify({
        'success': True,
        'message': '上传成功',
        'file_name': filename,
        'file_path': f'static/uploads/drawings/{save_name}',
        'file_type': file_type,
        'drawing_type': drawing_type
    })


@app.route('/api/import/tender', methods=['POST'])
def api_import_tender():
    """招标文件智能分析导入"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '请选择文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '请选择文件'}), 400

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    # 支持的格式
    supported = ['.docx', '.pdf', '.txt', '.doc']
    if ext not in supported:
        return jsonify({
            'success': False,
            'message': f'不支持的格式 {ext}，支持 Word/PDF/TXT 格式'
        }), 400

    # 保存文件
    save_name = f"tender_{int(datetime.now().timestamp())}_{filename}"
    save_path = os.path.join(UPLOAD_DIR, 'tender', save_name)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file.save(save_path)

    # 解析招标文件
    try:
        result = parse_tender_document(save_path)
        if not result:
            return jsonify({
                'success': False,
                'message': '未能从文件中提取到有效内容，请检查文件格式'
            }), 400

        return jsonify({
            'success': True,
            'message': '解析成功，请确认后保存',
            'project_name': result['project_name'],
            'parsed_data': result
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'解析失败：{str(e)}'}), 500


@app.route('/api/import/tender/save', methods=['POST'])
def api_save_tender():
    """保存招标文件解析结果为新项目"""
    data = request.get_json() or {}
    project_data = data.get('project_data', {})

    if not project_data.get('project_name'):
        return jsonify({'success': False, 'message': '项目名称不能为空'}), 400

    if project_exists(project_data['project_name']):
        return jsonify({
            'success': False,
            'message': f"项目 '{project_data['project_name']}' 已存在"
        }), 400

    project_id = insert_project(project_data)

    return jsonify({
        'success': True,
        'message': '保存成功',
        'project_id': project_id,
        'project_name': project_data['project_name']
    })


def _parse_project_form(form):
    """从表单数据解析项目信息"""
    def safe_float(val):
        try:
            return float(val) if val else None
        except (ValueError, TypeError):
            return None

    def safe_int(val):
        try:
            return int(val) if val else None
        except (ValueError, TypeError):
            return None

    data = {
        'project_name': form.get('project_name', ''),
        'project_type': form.get('project_type', ''),
        'sales_person': form.get('sales_person', ''),
        'confirm_date': form.get('confirm_date', ''),
        'location': form.get('location', ''),
        'province': form.get('province', ''),
        'sea_area': form.get('sea_area', ''),
        'coordinates': form.get('coordinates', ''),
        'project_scale': form.get('project_scale', ''),
        'construction_period': form.get('construction_period', ''),
        'budget': form.get('budget', ''),
        'description': form.get('description', ''),
        'sea_conditions': {
            'water_depth': safe_float(form.get('water_depth')),
            'water_level_diff': safe_float(form.get('water_level_diff')),
            'max_wave_height': safe_float(form.get('max_wave_height')),
            'max_flow_speed': safe_float(form.get('max_flow_speed')),
            'flow_direction': form.get('flow_direction', ''),
            'seabed_type': form.get('seabed_type', ''),
            'common_wind_direction': form.get('common_wind_direction', ''),
            'max_wind_direction': form.get('max_wind_direction', ''),
            'max_wind_speed': safe_float(form.get('max_wind_speed')),
        },
        'cage_params': {
            'pipe_diameter': form.get('cage_pipe_diameter', ''),
            'perimeter': safe_float(form.get('cage_perimeter')),
            'diameter': safe_float(form.get('cage_diameter')),
            'bracket_spacing': form.get('cage_bracket_spacing', ''),
            'walkway_width': form.get('cage_walkway_width', ''),
            'mooring_sleeve': form.get('cage_mooring_sleeve', ''),
            'anchor_point_count': safe_int(form.get('cage_anchor_point_count')),
            'net_demand': form.get('cage_net_demand', ''),
            'cage_count': safe_int(form.get('cage_cage_count')),
            'cage_type': form.get('cage_cage_type', ''),
        },
        'platform_params': {
            'pipe_diameter': form.get('platform_pipe_diameter', ''),
            'size_spec': form.get('platform_size_spec', ''),
            'shape_requirement': form.get('platform_shape_requirement', ''),
            '附属设施': form.get('platform_附属设施', ''),
            'bearing_capacity': form.get('platform_bearing_capacity', ''),
            'docking_ships': form.get('platform_docking_ships', ''),
            'platform_area': safe_float(form.get('platform_platform_area')),
        },
        'breakwater_params': {
            'pipe_diameter': form.get('breakwater_pipe_diameter', ''),
            'spec_type': form.get('breakwater_spec_type', ''),
            'bracket_spacing': form.get('breakwater_bracket_spacing', ''),
            'wave_reduction_rate': form.get('breakwater_wave_reduction_rate', ''),
        }
    }

    return data


# ====================== 初始化 ======================
# Render 部署：gunicorn 不会执行 __main__ 块，需要模块级别初始化
# 本地开发：python app.py 也会执行此块
_db_initialized = False

def initialize():
    """应用初始化：建表 + 导入样例数据"""
    global _db_initialized
    if _db_initialized:
        return
    init_db()
    init_sample_data()
    _db_initialized = True


# 模块加载时自动初始化（兼容 gunicorn 和 python app.py 两种启动方式）
initialize()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("深水网箱/浮动平台历史案例智能检索系统")
    print(f"访问地址: http://127.0.0.1:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
