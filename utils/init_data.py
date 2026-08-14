"""
样例数据初始化
导入真实项目数据 + 补充模拟案例数据
"""
import os
import shutil
from utils.db import init_db, insert_project, add_drawing, add_photo, add_materials, project_exists, get_conn, update_project
from utils.db import get_user_by_username, create_user
from utils.parser import parse_project_excel, parse_materials_excel
from utils.location import detect_location
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')


def init_sample_data():
    """初始化样例数据"""
    # 确保数据库已创建
    init_db()

    # 导入真实项目
    _import_real_projects()

    # 补充模拟项目
    _import_mock_projects()

    # 更新所有项目的地域信息（省份、海域）
    _update_location_info()

    # 创建默认管理员账号
    _create_default_admin()

    print("样例数据初始化完成！")


def _create_default_admin():
    """创建默认管理员账号 admin/admin123"""
    if get_user_by_username('admin'):
        return  # 已存在
    create_user('admin', '13800000000', generate_password_hash('admin123'), role='admin', status='approved')
    print("  创建默认管理员: admin / admin123")


def _update_location_info():
    """更新已有项目的地域信息（省份、海域）"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT id, project_name, location, description FROM projects')
    projects = cursor.fetchall()

    updated_count = 0
    for p in projects:
        text = f"{p['project_name']} {p['location'] or ''} {p['description'] or ''}"
        city, province, sea_area = detect_location(text)

        # 只有在字段为空时才更新
        if (city or province or sea_area):
            cursor.execute('''
                UPDATE projects SET
                    location = COALESCE(NULLIF(location, ''), ?),
                    province = COALESCE(NULLIF(province, ''), ?),
                    sea_area = COALESCE(NULLIF(sea_area, ''), ?)
                WHERE id = ?
            ''', (city or '', province or '', sea_area or '', p['id']))
            updated_count += 1

    conn.commit()
    conn.close()

    if updated_count > 0:
        print(f"  更新地域信息: {updated_count} 个项目")


def _copy_file_to_uploads(src_path, sub_dir='drawings'):
    """将文件复制到uploads目录，返回相对路径"""
    dest_dir = os.path.join(UPLOAD_DIR, sub_dir)
    os.makedirs(dest_dir, exist_ok=True)

    filename = os.path.basename(src_path)
    dest_path = os.path.join(dest_dir, filename)

    # 如果已存在，先删除
    if os.path.exists(dest_path):
        try:
            os.remove(dest_path)
        except:
            pass

    try:
        shutil.copy2(src_path, dest_path)
        return f'static/uploads/{sub_dir}/{filename}'
    except Exception as e:
        print(f"  复制文件失败: {e}")
        return src_path


def _import_real_projects():
    """导入真实的连云港海州湾项目"""
    xiangmu_dir = os.path.join(DATA_DIR, 'xiangmu', '项目需求')
    tuzhi_dir = os.path.join(DATA_DIR, 'tuzhi', '启航图纸')

    if not os.path.isdir(xiangmu_dir):
        print("  项目需求目录不存在，跳过真实项目导入")
        return

    # 导入两个真实项目
    excel_files = []
    for f in os.listdir(xiangmu_dir):
        if f.endswith('.xls') or f.endswith('.xlsx'):
            excel_files.append(os.path.join(xiangmu_dir, f))

    for excel_path in excel_files:
        try:
            data = parse_project_excel(excel_path)
            if not data['project_name']:
                continue

            if project_exists(data['project_name']):
                print(f"  项目已存在: {data['project_name']}，跳过")
                continue

            # 平台面积估算
            if '平台' in data['project_type'] and not data['platform_params'].get('platform_area'):
                data['platform_params']['platform_area'] = 1122.0

            project_id = insert_project(data)
            print(f"  导入项目: {data['project_name']} (ID: {project_id})")

            # 关联图纸（从启航图纸目录）
            if os.path.isdir(tuzhi_dir):
                for f in sorted(os.listdir(tuzhi_dir)):
                    fpath = os.path.join(tuzhi_dir, f)
                    if not os.path.isfile(fpath):
                        continue

                    # 只导入"连云港海州湾项目"相关的图纸
                    if '海州湾' not in f and '连云港' not in f:
                        continue

                    # 判断文件类型
                    ext = os.path.splitext(f)[1].lower()
                    if ext == '.pdf':
                        ftype = 'pdf'
                    elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp'):
                        ftype = 'image'
                    elif ext in ('.xls', '.xlsx'):
                        ftype = 'excel'

                        # 如果是材料统计表，解析并导入材料数据
                        if '材料统计' in f:
                            try:
                                materials = parse_materials_excel(fpath)
                                if materials:
                                    add_materials(project_id, materials)
                                    print(f"    导入材料: {len(materials)} 条")
                            except Exception as e:
                                print(f"    材料解析失败: {e}")
                        continue
                    else:
                        continue

                    fsize = os.path.getsize(fpath)

                    # 识别图纸类型
                    dtype = ''
                    if '框架' in f:
                        dtype = '框架图'
                    elif '锚固' in f:
                        dtype = '锚固图'
                    elif '平面' in f or '布局' in f:
                        dtype = '总平面图'

                    # 复制文件到uploads
                    rel_path = _copy_file_to_uploads(fpath, 'drawings')

                    add_drawing(project_id, f, rel_path, ftype, fsize, dtype)
                    print(f"    添加图纸: {f}")

            # 关联项目需求中的图片
            for f in os.listdir(xiangmu_dir):
                fpath = os.path.join(xiangmu_dir, f)
                if os.path.isfile(fpath) and f.lower().endswith(('.png', '.jpg', '.jpeg')):
                    fsize = os.path.getsize(fpath)
                    # 复制文件
                    rel_path = _copy_file_to_uploads(fpath, 'photos')
                    add_photo(project_id, f, rel_path, 'image', fsize, '项目图片')
                    print(f"    添加照片: {f}")

        except Exception as e:
            print(f"  导入项目失败 {excel_path}: {e}")
            import traceback
            traceback.print_exc()


def _import_mock_projects():
    """补充模拟项目数据，让案例库更丰富"""
    mock_projects = [
        {
            'project_name': '青岛黄岛深水网箱养殖项目',
            'project_type': '网箱',
            'sales_person': '张伟',
            'confirm_date': '2025-09-20',
            'location': '青岛',
            'coordinates': '120°12E，35°56N',
            'description': '大型深水抗风浪网箱养殖项目，主要养殖大黄鱼和石斑鱼。采用HDPE框架结构，配重金属网衣。',
            'sea_conditions': {
                'water_depth': 25.0,
                'water_level_diff': 2.8,
                'max_wave_height': 5.5,
                'max_flow_speed': 1.2,
                'flow_direction': '东南西北往复流',
                'seabed_type': '沙质硬底',
                'common_wind_direction': '东南风',
                'max_wind_direction': '西北风',
                'max_wind_speed': 35.0
            },
            'cage_params': {
                'pipe_diameter': 'DN500,双层',
                'perimeter': 120.0,
                'diameter': 38.2,
                'bracket_spacing': '1540mm',
                'walkway_width': '2.0m',
                'mooring_sleeve': '有',
                'anchor_point_count': 12,
                'net_demand': '超高分子量聚乙烯网衣，网目30mm，网深8m，配盖网和撑网架',
                'cage_count': 8,
                'cage_type': '圆形、抗风浪型'
            },
            'platform_params': {},
            'breakwater_params': {}
        },
        {
            'project_name': '福建宁德三都澳渔旅平台项目',
            'project_type': '平台＋网箱',
            'sales_person': '陈建国',
            'confirm_date': '2025-11-15',
            'location': '宁德',
            'coordinates': '119°38E，26°38N',
            'description': '综合性海洋渔旅平台，包含休闲垂钓、海上餐厅、住宿等功能，配套深水网箱养殖区。',
            'sea_conditions': {
                'water_depth': 18.0,
                'water_level_diff': 4.2,
                'max_wave_height': 3.0,
                'max_flow_speed': 1.5,
                'flow_direction': '旋转流',
                'seabed_type': '淤泥质',
                'common_wind_direction': '东北风',
                'max_wind_direction': '台风',
                'max_wind_speed': 40.0
            },
            'cage_params': {
                'pipe_diameter': 'DN400,双层',
                'perimeter': 90.0,
                'diameter': 28.6,
                'bracket_spacing': '1540mm',
                'walkway_width': '1.5m',
                'mooring_sleeve': '有',
                'anchor_point_count': 8,
                'net_demand': '尼龙网衣，网目25mm，网深6m',
                'cage_count': 6,
                'cage_type': '圆形'
            },
            'platform_params': {
                'pipe_diameter': 'DN630，双层',
                'size_spec': '长方形 30m×20m',
                'shape_requirement': '双层结构，上层住宿，下层餐饮',
                '附属设施': '休闲垂钓区、海上餐厅、客房6间、观景平台',
                'bearing_capacity': '300人',
                'docking_ships': '可停靠2艘快艇',
                'platform_area': 600.0
            },
            'breakwater_params': {}
        },
        {
            'project_name': '海南文昌海水养殖网箱基地',
            'project_type': '网箱',
            'sales_person': '李明',
            'confirm_date': '2025-06-30',
            'location': '文昌',
            'coordinates': '110°55E，19°42N',
            'description': '规模化深水网箱养殖基地，主要养殖军曹鱼、金鲳鱼等热带海水鱼类。',
            'sea_conditions': {
                'water_depth': 30.0,
                'water_level_diff': 1.5,
                'max_wave_height': 4.0,
                'max_flow_speed': 0.8,
                'flow_direction': '往复流',
                'seabed_type': '沙质',
                'common_wind_direction': '东风',
                'max_wind_direction': '台风',
                'max_wind_speed': 45.0
            },
            'cage_params': {
                'pipe_diameter': 'DN500,双层双侧',
                'perimeter': 160.0,
                'diameter': 50.9,
                'bracket_spacing': '1540mm',
                'walkway_width': '2.5m',
                'mooring_sleeve': '有，加强型',
                'anchor_point_count': 16,
                'net_demand': '铜合金网衣，网目28mm，网深12m，配撑网架',
                'cage_count': 20,
                'cage_type': '圆形、深海型'
            },
            'platform_params': {},
            'breakwater_params': {}
        },
        {
            'project_name': '浙江舟山休闲渔业综合体',
            'project_type': '平台＋网箱',
            'sales_person': '王芳',
            'confirm_date': '2025-08-10',
            'location': '舟山',
            'coordinates': '122°20E，30°08N',
            'description': '集养殖、垂钓、餐饮、观光于一体的海上休闲渔业综合体平台。',
            'sea_conditions': {
                'water_depth': 22.0,
                'water_level_diff': 3.0,
                'max_wave_height': 3.5,
                'max_flow_speed': 2.0,
                'flow_direction': '东南西北往复流',
                'seabed_type': '粉砂质',
                'common_wind_direction': '东南风',
                'max_wind_direction': '西北风',
                'max_wind_speed': 38.0
            },
            'cage_params': {
                'pipe_diameter': 'DN400,双层',
                'perimeter': 80.0,
                'diameter': 25.5,
                'bracket_spacing': '1540mm',
                'walkway_width': '1.8m',
                'mooring_sleeve': '有',
                'anchor_point_count': 10,
                'net_demand': '聚乙烯网衣，网目20mm，网深5m，配盖网',
                'cage_count': 12,
                'cage_type': '方形、组合式'
            },
            'platform_params': {
                'pipe_diameter': 'DN500，双层',
                'size_spec': '正方形 40m×40m，环形布局',
                'shape_requirement': '回字形布局，中间为垂钓区',
                '附属设施': '垂钓平台、海鲜餐厅、休息区、儿童游乐区',
                'bearing_capacity': '200人',
                'docking_ships': '可停靠4艘游钓船',
                'platform_area': 1600.0
            },
            'breakwater_params': {}
        },
        {
            'project_name': '广东珠海防波堤及网箱项目',
            'project_type': '防波堤',
            'sales_person': '黄志强',
            'confirm_date': '2025-10-25',
            'location': '珠海',
            'coordinates': '113°35E，22°10N',
            'description': '为养殖区建设浮动防波堤，消波减浪，保护内部网箱养殖区域。',
            'sea_conditions': {
                'water_depth': 12.0,
                'water_level_diff': 1.2,
                'max_wave_height': 2.5,
                'max_flow_speed': 0.6,
                'flow_direction': '往复流',
                'seabed_type': '沙质硬底',
                'common_wind_direction': '南风',
                'max_wind_direction': '台风',
                'max_wind_speed': 42.0
            },
            'cage_params': {},
            'platform_params': {},
            'breakwater_params': {
                'pipe_diameter': 'DN800,双层',
                'spec_type': '浮动式防波堤',
                'bracket_spacing': '2000mm',
                'wave_reduction_rate': '60%以上'
            }
        },
        {
            'project_name': '山东烟台海洋牧场平台项目',
            'project_type': '平台',
            'sales_person': '刘海洋',
            'confirm_date': '2025-05-18',
            'location': '烟台',
            'coordinates': '121°20E，37°33N',
            'description': '现代化海洋牧场综合平台，包含水下监测、水面养殖、科研监测等功能。',
            'sea_conditions': {
                'water_depth': 35.0,
                'water_level_diff': 1.8,
                'max_wave_height': 6.0,
                'max_flow_speed': 1.0,
                'flow_direction': '东北西南往复流',
                'seabed_type': '泥沙质',
                'common_wind_direction': '西北风',
                'max_wind_direction': '北风',
                'max_wind_speed': 32.0
            },
            'cage_params': {},
            'platform_params': {
                'pipe_diameter': 'DN630，双层加强',
                'size_spec': '八边形，直径50m',
                'shape_requirement': '三层结构，科研办公+养殖+住宿',
                '附属设施': '水下观测室、科研实验室、观景台、直升机起降平台',
                'bearing_capacity': '100人',
                'docking_ships': '可停靠2艘工作船',
                'platform_area': 1960.0
            },
            'breakwater_params': {}
        },
        {
            'project_name': '广西北海小型网箱养殖项目',
            'project_type': '网箱',
            'sales_person': '赵铭',
            'confirm_date': '2025-12-01',
            'location': '北海',
            'coordinates': '109°07E，21°28N',
            'description': '近海小型网箱养殖项目，适合近岸风浪较小海域。',
            'sea_conditions': {
                'water_depth': 8.0,
                'water_level_diff': 2.0,
                'max_wave_height': 1.5,
                'max_flow_speed': 0.5,
                'flow_direction': '往复流',
                'seabed_type': '泥沙质',
                'common_wind_direction': '东风',
                'max_wind_direction': '西南风',
                'max_wind_speed': 20.0
            },
            'cage_params': {
                'pipe_diameter': 'DN315,单层',
                'perimeter': 50.0,
                'diameter': 15.9,
                'bracket_spacing': '1000mm',
                'walkway_width': '1.0m',
                'mooring_sleeve': '无',
                'anchor_point_count': 6,
                'net_demand': '聚乙烯网衣，网目15mm，网深4m',
                'cage_count': 4,
                'cage_type': '方形、普通型'
            },
            'platform_params': {},
            'breakwater_params': {}
        },
        {
            'project_name': '广东汕头南澳岛深水网箱项目',
            'project_type': '网箱',
            'sales_person': '陈建华',
            'confirm_date': '2025-07-22',
            'location': '汕头',
            'coordinates': '117°02E，23°26N',
            'description': '大型深水抗风浪网箱养殖项目，养殖鰤鱼、石斑鱼等高价值鱼类。',
            'sea_conditions': {
                'water_depth': 28.0,
                'water_level_diff': 1.6,
                'max_wave_height': 5.0,
                'max_flow_speed': 1.8,
                'flow_direction': '往复流',
                'seabed_type': '岩礁底质',
                'common_wind_direction': '东南风',
                'max_wind_direction': '台风',
                'max_wind_speed': 48.0
            },
            'cage_params': {
                'pipe_diameter': 'DN500,双层双侧加强',
                'perimeter': 140.0,
                'diameter': 44.6,
                'bracket_spacing': '1540mm',
                'walkway_width': '2.2m',
                'mooring_sleeve': '有，加强型',
                'anchor_point_count': 14,
                'net_demand': '超高分子量聚乙烯网衣，网目35mm，网深10m，配撑网架和盖网',
                'cage_count': 10,
                'cage_type': '圆形、深海抗风浪'
            },
            'platform_params': {},
            'breakwater_params': {}
        }
    ]

    for data in mock_projects:
        if project_exists(data['project_name']):
            print(f"  模拟项目已存在: {data['project_name']}，跳过")
            continue

        project_id = insert_project(data)
        print(f"  添加模拟项目: {data['project_name']} (ID: {project_id})")


if __name__ == '__main__':
    init_sample_data()
