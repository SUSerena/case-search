"""
Excel/Word项目信息表解析器
解析"项目信息表"格式的Excel文件，提取结构化数据
"""
import pandas as pd
import re
import os
from utils.db import insert_project, add_drawing, add_photo, add_materials
from utils.location import detect_location


def parse_project_excel(file_path):
    """
    解析项目信息表 Excel 文件
    返回项目数据字典
    """
    try:
        df = pd.read_excel(file_path, sheet_name=0, header=None)
    except Exception as e:
        raise Exception(f"读取Excel失败: {e}")

    data = {
        'project_name': '',
        'project_type': '',
        'sales_person': '',
        'confirm_date': '',
        'location': '',
        'coordinates': '',
        'description': '',
        'sea_conditions': {},
        'cage_params': {},
        'platform_params': {},
        'breakwater_params': {}
    }

    # 遍历每一行，根据字段标签提取值
    for i in range(len(df)):
        row = df.iloc[i].tolist()
        # 转换为字符串列表
        cells = [str(x).strip() if pd.notna(x) else '' for x in row]

        # 项目名称
        if '项目名称' in cells[0]:
            # 找后续列中的值
            for j in range(1, len(cells)):
                if cells[j] and cells[j] != 'NaT':
                    data['project_name'] = cells[j]
                    break

        # 业务人员
        elif '业务人员' in cells[0]:
            for j in range(1, len(cells)):
                if cells[j] and cells[j] != 'NaT':
                    data['sales_person'] = cells[j]
                    break

        # 项目类型
        elif '项目类型' in cells[0]:
            for j in range(1, len(cells)):
                if cells[j] and cells[j] != 'NaT':
                    data['project_type'] = cells[j]
                    break

        # 海域坐标
        elif '海域坐标' in cells[0]:
            for j in range(1, len(cells)):
                if cells[j] and cells[j] != 'NaT' and '陆地施工' not in cells[j]:
                    data['coordinates'] = cells[j]
                    break

        # 满潮水深
        elif '满潮水深' in cells[0]:
            if len(cells) > 1 and cells[1] and cells[1] != 'NaT':
                data['sea_conditions']['water_depth'] = _extract_max_depth(cells[1])
            # 流向
            if len(cells) > 3 and cells[3] and '流向' in str(cells[3]):
                if len(cells) > 4 and cells[4]:
                    data['sea_conditions']['flow_direction'] = cells[4]

        # 水位差
        elif '水位差' in cells[0]:
            if len(cells) > 1 and cells[1] and cells[1] != 'NaT':
                data['sea_conditions']['water_level_diff'] = _extract_number(cells[1])
            # 底质
            if len(cells) > 3 and cells[3] and '底质' in str(cells[3]):
                if len(cells) > 4 and cells[4]:
                    data['sea_conditions']['seabed_type'] = cells[4]

        # 最大波高
        elif '最大波高' in cells[0]:
            if len(cells) > 1 and cells[1] and cells[1] != 'NaT':
                data['sea_conditions']['max_wave_height'] = _extract_number(cells[1])
            # 最大流速
            if len(cells) > 3 and cells[3] and '最大流速' in str(cells[3]):
                if len(cells) > 4 and cells[4]:
                    data['sea_conditions']['max_flow_speed'] = _extract_number(cells[4])

        # 常风向
        elif '常风向' in cells[0]:
            if len(cells) > 1 and cells[1] and cells[1] != 'NaT':
                data['sea_conditions']['common_wind_direction'] = cells[1]
            # 最大风向
            if len(cells) > 3 and cells[3] and '最大风向' in str(cells[3]):
                if len(cells) > 4 and cells[4]:
                    data['sea_conditions']['max_wind_direction'] = cells[4]

        # 最大风速（单独一行的情况）
        elif '最大风速' in cells[0] and len(cells[0]) < 10:
            if len(cells) > 1 and cells[1] and cells[1] != 'NaT':
                data['sea_conditions']['max_wind_speed'] = _extract_number(cells[1])
        elif len(cells) > 3 and cells[3] and '最大风速' in str(cells[3]):
            if len(cells) > 4 and cells[4] and cells[4] != 'NaT':
                data['sea_conditions']['max_wind_speed'] = _extract_number(cells[4])

        # 网箱管径
        # 需要先识别哪一行是网箱类管径行
        pass

    # 专门解析网箱/平台/防波堤参数区域（从"项目信息"之后的行开始）
    in_project_info = False
    for i in range(len(df)):
        row = df.iloc[i].tolist()
        cells = [str(x).strip() if pd.notna(x) else '' for x in row]

        if '项目信息' in cells[0]:
            in_project_info = True
            continue

        if not in_project_info:
            continue

        # 到达确认时间行则停止
        if '确认时间' in ''.join(cells):
            # 提取确认时间
            for j in range(len(cells)):
                if cells[j] and '确认时间' not in cells[j] and cells[j] != 'NaT':
                    try:
                        data['confirm_date'] = cells[j].split()[0] if ' ' in cells[j] else cells[j]
                    except:
                        pass
            break

        # 管径行（列0=网箱标签, 列1=网箱值; 列2=平台标签, 列3=平台值; 列4=防波堤标签, 列5=防波堤值）
        if cells[0] == '管径*':
            # 网箱管径（列1）
            if len(cells) > 1 and cells[1] and cells[1] != 'NaT':
                data['cage_params']['pipe_diameter'] = cells[1]
            # 平台管径（列3）
            if len(cells) > 3 and cells[3] and cells[3] != 'NaT':
                data['platform_params']['pipe_diameter'] = cells[3]
            # 防波堤管径（列5）
            if len(cells) > 5 and cells[5] and cells[5] != 'NaT':
                data['breakwater_params']['pipe_diameter'] = cells[5]

        # 周长/直径
        elif '周长' in cells[0] and '直径' in cells[0]:
            # 网箱周长/直径（列1）
            if len(cells) > 1 and cells[1] and cells[1] != 'NaT':
                data['cage_params']['_perimeter_text'] = cells[1]
                perim = _extract_perimeter(cells[1])
                if perim:
                    data['cage_params']['perimeter'] = perim
                dia = _extract_diameter(cells[1])
                if dia:
                    data['cage_params']['diameter'] = dia
                cnt = _extract_cage_count(cells[1])
                if cnt:
                    data['cage_params']['cage_count'] = cnt
                ctype = _extract_cage_type(cells[1])
                if ctype:
                    data['cage_params']['cage_type'] = ctype
            # 平台尺寸规格（列3）
            if len(cells) > 3 and cells[3] and cells[3] != 'NaT':
                data['platform_params']['size_spec'] = cells[3]
            # 防波堤规格选型（列5）
            if len(cells) > 5 and cells[5] and cells[5] != 'NaT':
                data['breakwater_params']['spec_type'] = cells[5]

        # 支架间距
        elif cells[0] == '支架间距':
            # 网箱（列1）
            if len(cells) > 1 and cells[1] and cells[1] != 'NaT':
                data['cage_params']['bracket_spacing'] = cells[1]
            # 防波堤（列5）
            if len(cells) > 5 and cells[5] and cells[5] != 'NaT':
                data['breakwater_params']['bracket_spacing'] = cells[5]

        # 过道宽度
        elif '过道宽度' in cells[0]:
            if len(cells) > 1 and cells[1] and cells[1] != 'NaT':
                data['cage_params']['walkway_width'] = cells[1]

        # 系缆加强套管
        elif '系缆加强套管' in cells[0]:
            if len(cells) > 1 and cells[1] and cells[1] != 'NaT':
                data['cage_params']['mooring_sleeve'] = cells[1]

        # 锚点数量
        elif '锚点数量' in cells[0]:
            if len(cells) > 1 and cells[1] and cells[1] != 'NaT':
                data['cage_params']['anchor_point_count'] = _extract_number(cells[1])

        # 网衣需求
        elif '网衣需求' in cells[0]:
            if len(cells) > 1 and cells[1] and cells[1] != 'NaT':
                data['cage_params']['net_demand'] = cells[1]

        # 造型要求（平台类，列2是标签，列3是值）
        elif len(cells) > 2 and cells[2] == '造型要求':
            if len(cells) > 3 and cells[3] and cells[3] != 'NaT':
                data['platform_params']['shape_requirement'] = cells[3]

        # 附属设施（平台类，列2是标签，列3是值）
        elif len(cells) > 2 and '附属设施' in str(cells[2]):
            if len(cells) > 3 and cells[3] and cells[3] != 'NaT':
                data['platform_params']['附属设施'] = cells[3]

        # 承载力要求（平台类，列2是标签，列3是值）
        elif len(cells) > 2 and '承载力' in str(cells[2]):
            if len(cells) > 3 and cells[3] and cells[3] != 'NaT':
                data['platform_params']['bearing_capacity'] = cells[3]

        # 靠泊船只（平台类，列2是标签，列3是值）
        elif len(cells) > 2 and '靠泊船只' in str(cells[2]):
            if len(cells) > 3 and cells[3] and cells[3] != 'NaT':
                data['platform_params']['docking_ships'] = cells[3]

        # 减波率要求（防波堤类，列4是标签，列5是值）
        elif len(cells) > 4 and '减波率' in str(cells[4]):
            if len(cells) > 5 and cells[5] and cells[5] != 'NaT':
                data['breakwater_params']['wave_reduction_rate'] = cells[5]

        # 其他特殊要求 - 合并到描述
        elif '其他特殊要求' in cells[0]:
            descs = []
            for j in range(1, len(cells)):
                if cells[j] and cells[j] != 'NaT' and '其他特殊要求' not in cells[j]:
                    descs.append(cells[j])
            if descs:
                data['description'] = '\n'.join(descs)

    # 从项目名称中提取地点信息
    loc = _extract_location(data['project_name'])
    if loc:
        data['location'] = loc

    # 智能识别地域信息（城市、省份、海域）
    text_for_detect = data['project_name'] + ' ' + (data.get('description') or '') + ' ' + (data.get('location') or '')
    city, province, sea_area = detect_location(text_for_detect)
    if city:
        # 如果已有location但更精确，保留原location；否则用识别到的city
        if not data.get('location') or len(data['location']) < 2:
            data['location'] = city
    if province:
        data['province'] = province
    if sea_area:
        data['sea_area'] = sea_area

    return data


def parse_materials_excel(file_path):
    """
    解析材料统计表
    返回材料列表
    """
    try:
        df = pd.read_excel(file_path, sheet_name=0, header=None)
    except Exception as e:
        raise Exception(f"读取材料统计Excel失败: {e}")

    materials = []
    current_category = ''

    # 找到表头行（包含"货品编码"或"材料名称"的行）
    header_row = -1
    for i in range(min(10, len(df))):
        row_str = ' '.join([str(x) for x in df.iloc[i].tolist()])
        if '材料名称' in row_str or '货品编码' in row_str:
            header_row = i
            break

    if header_row < 0:
        return materials

    # 从表头下一行开始读取
    for i in range(header_row + 1, len(df)):
        row = df.iloc[i].tolist()
        cells = [x if pd.notna(x) else '' for x in row]

        # 检测分类行（只有第一列有值，且不是货品编码）
        first_col = str(cells[0]).strip() if cells[0] else ''
        has_content = any(str(c).strip() for c in cells[1:] if str(c).strip() and str(c) != 'nan')

        # 如果只有第一列有内容，可能是分类标题
        if first_col and not has_content and len(first_col) < 20:
            # 检查是不是纯数字编码（货品编码）
            if not re.match(r'^\d+$', first_col):
                current_category = first_col
                continue

        # 正常数据行：有材料名称
        material_name = ''
        if len(cells) > 1:
            material_name = str(cells[1]).strip() if cells[1] else ''

        if not material_name:
            continue

        material = {
            'category': current_category,
            'material_name': material_name,
            'model': str(cells[2]).strip() if len(cells) > 2 and cells[2] else '',
            'unit': str(cells[3]).strip() if len(cells) > 3 and cells[3] else '',
            'quantity': None,
            'unit_weight': None,
            'total_weight': None
        }

        # 数量（总计列，通常是第8列 index=8）
        if len(cells) > 8 and cells[8]:
            try:
                material['quantity'] = float(cells[8])
            except (ValueError, TypeError):
                pass

        # 单重
        if len(cells) > 9 and cells[9]:
            try:
                material['unit_weight'] = float(cells[9])
            except (ValueError, TypeError):
                pass

        # 总重
        if len(cells) > 10 and cells[10]:
            try:
                material['total_weight'] = float(cells[10])
            except (ValueError, TypeError):
                pass

        materials.append(material)

    return materials


def _extract_number(text):
    """从文本中提取第一个数值"""
    if not text:
        return None
    text = str(text)
    match = re.search(r'(\d+\.?\d*)', text)
    if match:
        return float(match.group(1))
    return None


def _extract_max_depth(text):
    """从水深描述中提取最大水深值，如'最低潮5m，满潮7-8m' -> 8.0"""
    if not text:
        return None
    text = str(text)
    # 提取所有数字
    numbers = re.findall(r'(\d+\.?\d*)', text)
    if not numbers:
        return None
    # 返回最大值
    return max(float(n) for n in numbers)


def _extract_perimeter(text):
    """提取周长数值，如'90m周长'、'周长90m'"""
    if not text:
        return None
    text = str(text)
    # 匹配 xxx m周长 or 周长xxx m or xxxm周长
    patterns = [
        r'(\d+\.?\d*)\s*[mM米]\s*周长',
        r'周长\s*(\d+\.?\d*)\s*[mM米]?',
        r'C\s*(\d+\.?\d*)',
    ]
    for p in patterns:
        match = re.search(p, text)
        if match:
            return float(match.group(1))
    return None


def _extract_diameter(text):
    """提取直径数值"""
    if not text:
        return None
    text = str(text)
    patterns = [
        r'直径\s*(\d+\.?\d*)\s*[mM米]?',
        r'(\d+\.?\d*)\s*[mM米]\s*直径',
    ]
    for p in patterns:
        match = re.search(p, text)
        if match:
            return float(match.group(1))
    return None


def _extract_cage_count(text):
    """提取网箱数量，如'3口'、'18口'"""
    if not text:
        return None
    text = str(text)
    match = re.search(r'(\d+)\s*口', text)
    if match:
        return int(match.group(1))
    # "3个"
    match = re.search(r'(\d+)\s*个', text)
    if match:
        return int(match.group(1))
    return None


def _extract_cage_type(text):
    """提取网箱类型，如'圆形'、'方形'、'韩式'"""
    if not text:
        return ''
    text = str(text)
    types = []
    if '圆形' in text:
        types.append('圆形')
    if '方形' in text:
        types.append('方形')
    if '韩式' in text:
        types.append('韩式')
    if '九宫格' in text:
        types.append('九宫格')
    return '、'.join(types) if types else ''


def _extract_location(project_name):
    """从项目名称中提取地点"""
    if not project_name:
        return ''
    # 常见地名模式
    # 提取"连云港"、"青岛"、"大连"等地名
    # 简单方法：取前2-4个字符中包含地名的部分
    locations = ['连云港', '青岛', '大连', '烟台', '威海', '日照', '宁波', '温州',
                 '福州', '厦门', '深圳', '珠海', '湛江', '北海', '三亚', '舟山',
                 '台州', '泉州', '汕头', '阳江', '茂名', '海口', '儋州', '文昌',
                 '秦皇岛', '葫芦岛', '丹东', '营口', '盘锦', '锦州', '朝阳',
                 '上海', '天津', '广州', '杭州', '南京', '苏州']
    for loc in locations:
        if loc in project_name:
            return loc
    # 默认提取前3个字符作为地点候选
    if len(project_name) >= 3:
        return project_name[:3]
    return project_name


def import_project_from_excel(excel_path, drawings_dir=None, photos_dir=None):
    """
    从Excel文件导入项目，自动关联图纸和照片
    返回: 项目ID
    """
    # 解析项目信息
    project_data = parse_project_excel(excel_path)

    if not project_data['project_name']:
        raise Exception("未能识别出项目名称")

    # 检查是否已存在
    from utils.db import project_exists
    if project_exists(project_data['project_name']):
        raise Exception(f"项目 '{project_data['project_name']}' 已存在")

    # 插入项目
    project_id = insert_project(project_data)

    # 关联图纸
    if drawings_dir and os.path.isdir(drawings_dir):
        project_keywords = project_data['project_name'][:4]  # 取项目名前几个字作为关键词
        for f in os.listdir(drawings_dir):
            fpath = os.path.join(drawings_dir, f)
            if os.path.isfile(fpath):
                # 判断是否相关（文件名包含项目关键词）
                fname_lower = f.lower()
                if any(kw in f for kw in [project_data['project_name'][:4], project_data['location'][:2]] if kw):
                    ftype = 'pdf' if f.lower().endswith('.pdf') else \
                            ('image' if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')) else 'other')
                    fsize = os.path.getsize(fpath)
                    # 识别图纸类型
                    dtype = ''
                    if '框架' in f:
                        dtype = '框架图'
                    elif '锚固' in f:
                        dtype = '锚固图'
                    elif '平面' in f or '布局' in f:
                        dtype = '总平面图'
                    elif '材料' in f:
                        dtype = '材料统计'

                    add_drawing(project_id, f, fpath, ftype, fsize, dtype)

    # 关联照片
    if photos_dir and os.path.isdir(photos_dir):
        for f in os.listdir(photos_dir):
            fpath = os.path.join(photos_dir, f)
            if os.path.isfile(fpath) and f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                fsize = os.path.getsize(fpath)
                add_photo(project_id, f, fpath, 'image', fsize, '项目照片')

    return project_id
