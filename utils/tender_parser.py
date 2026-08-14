"""
招标文件智能分析模块
从招标文件（Word/PDF/TXT）中自动提取项目关键信息
"""
import re
import os
from utils.location import detect_location


def parse_tender_document(file_path):
    """
    解析招标文件，提取关键信息
    返回: dict 项目信息
    """
    # 读取文本内容
    text = _read_document_text(file_path)
    if not text:
        return None

    result = {
        'project_name': '',
        'project_type': '',
        'location': '',
        'province': '',
        'sea_area': '',
        'project_scale': '',
        'construction_period': '',
        'budget': '',
        'description': '',
        'sea_conditions': {},
        'cage_params': {},
        'platform_params': {},
        'breakwater_params': {}
    }

    # 1. 提取项目名称
    result['project_name'] = _extract_project_name(text)

    # 2. 识别项目类型
    result['project_type'] = _extract_project_type(text)

    # 3. 识别地域信息
    city, province, sea_area = detect_location(text)
    if city:
        result['location'] = city
    if province:
        result['province'] = province
    if sea_area:
        result['sea_area'] = sea_area

    # 4. 提取项目规模
    result['project_scale'] = _extract_project_scale(text)

    # 5. 提取工期
    result['construction_period'] = _extract_construction_period(text)

    # 6. 提取预算/投资
    result['budget'] = _extract_budget(text)

    # 7. 提取海况参数
    result['sea_conditions'] = _extract_sea_conditions(text)

    # 8. 提取技术参数
    result['cage_params'] = _extract_cage_params(text)
    result['platform_params'] = _extract_platform_params(text)
    result['breakwater_params'] = _extract_breakwater_params(text)

    # 9. 生成项目概述
    result['description'] = _generate_summary(text, result)

    return result


def _read_document_text(file_path):
    """读取文档文本内容，支持txt/docx/pdf"""
    if not file_path or not os.path.exists(file_path):
        return ''

    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == '.txt':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()

        elif ext == '.docx':
            try:
                from docx import Document
                doc = Document(file_path)
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                # 也读取表格中的内容
                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            if cell.text.strip():
                                paragraphs.append(cell.text)
                return '\n'.join(paragraphs)
            except ImportError:
                return ''

        elif ext == '.pdf':
            try:
                # 尝试用多种方式读取PDF
                text = ''
                # 方法1: PyPDF2
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(file_path)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + '\n'
                except ImportError:
                    pass

                if not text:
                    # 方法2: pdfplumber
                    try:
                        import pdfplumber
                        with pdfplumber.open(file_path) as pdf:
                            for page in pdf.pages:
                                page_text = page.extract_text()
                                if page_text:
                                    text += page_text + '\n'
                    except ImportError:
                        pass

                return text
            except Exception:
                return ''

        elif ext in ['.doc']:
            # .doc格式较复杂，暂不支持
            return ''

    except Exception:
        return ''

    return ''


def _extract_project_name(text):
    """提取项目名称"""
    # 常见模式
    patterns = [
        r'项目名称[：:]\s*([^\n，。；;]{3,50})',
        r'工程名称[：:]\s*([^\n，。；;]{3,50})',
        r'招标项目[：:]\s*([^\n，。；;]{3,50})',
        r'项目概况[：:].*?([\u4e00-\u9fa5A-Za-z0-9]{3,30}(项目|工程))',
        r'([\u4e00-\u9fa5]{3,20}(深水网箱|网箱|平台|防波堤|渔旅|海洋牧场|养殖).*?(项目|工程))',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            # 清理
            name = re.sub(r'[（(].*?[）)]', '', name).strip()
            if len(name) >= 3 and len(name) <= 50:
                return name

    # 返回前30字作为默认
    first_line = text.strip().split('\n')[0][:30] if text.strip() else '未命名项目'
    return first_line


def _extract_project_type(text):
    """识别项目类型"""
    types = []
    if re.search(r'网箱|养殖|渔排', text):
        types.append('网箱')
    if re.search(r'平台|海洋牧场|综合体|渔旅|休闲', text):
        types.append('平台')
    if re.search(r'防波堤|消波|减波', text):
        types.append('防波堤')

    if not types:
        return '网箱'

    return '＋'.join(types)


def _extract_project_scale(text):
    """提取项目规模"""
    patterns = [
        r'总投资[：:]\s*([^\n，。；;]+)',
        r'项目规模[：:]\s*([^\n，。；;]+)',
        r'建设规模[：:]\s*([^\n，。；;]+)',
        r'总占地面积[：:]\s*([^\n，。；;]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

    return ''


def _extract_construction_period(text):
    """提取工期"""
    patterns = [
        r'工期[：:]\s*([^\n，。；;]+)',
        r'建设工期[：:]\s*([^\n，。；;]+)',
        r'施工工期[：:]\s*([^\n，。；;]+)',
        r'计划工期[：:]\s*([^\n，。；;]+)',
        r'交货期[：:]\s*([^\n，。；;]+)',
        r'(\d+)\s*个?月',
        r'(\d+)\s*天',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

    return ''


def _extract_budget(text):
    """提取预算/投资金额"""
    patterns = [
        r'预算金额[：:]\s*([^\n，。；;]+)',
        r'招标控制价[：:]\s*([^\n，。；;]+)',
        r'最高限价[：:]\s*([^\n，。；;]+)',
        r'总投资[：:]\s*([\d,.]+\s*[万亿]?元)',
        r'投资概算[：:]\s*([^\n，。；;]+)',
        r'合同金额[：:]\s*([^\n，。；;]+)',
        r'([\d,.]+\s*[万亿]?元)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            budget = match.group(1).strip()
            if len(budget) <= 30:
                return budget

    return ''


def _extract_sea_conditions(text):
    """提取海况参数"""
    sea = {}

    # 水深
    match = re.search(r'水深[：: ]\s*(\d+\.?\d*)\s*米?', text)
    if match:
        sea['water_depth'] = float(match.group(1))

    # 波高
    match = re.search(r'波高[：: ]\s*(\d+\.?\d*)\s*米?', text)
    if match:
        sea['max_wave_height'] = float(match.group(1))
    match = re.search(r'最大波高[：: ]\s*(\d+\.?\d*)\s*米?', text)
    if match:
        sea['max_wave_height'] = float(match.group(1))

    # 流速
    match = re.search(r'流速[：: ]\s*(\d+\.?\d*)\s*[米m]/s?', text)
    if match:
        sea['max_flow_speed'] = float(match.group(1))

    # 水位差/潮差
    match = re.search(r'潮差[：: ]\s*(\d+\.?\d*)\s*米?', text)
    if match:
        sea['water_level_diff'] = float(match.group(1))
    match = re.search(r'水位差[：: ]\s*(\d+\.?\d*)\s*米?', text)
    if match:
        sea['water_level_diff'] = float(match.group(1))

    # 风速
    match = re.search(r'风速[：: ]\s*(\d+\.?\d*)\s*[米m]/s?', text)
    if match:
        sea['max_wind_speed'] = float(match.group(1))

    # 底质
    match = re.search(r'底质[：:]\s*([^\n，。；;]+)', text)
    if match:
        sea['seabed_type'] = match.group(1).strip()

    return sea


def _extract_cage_params(text):
    """提取网箱参数"""
    cage = {}

    # 管径
    match = re.search(r'(?:网箱)?.*?管径[：:]\s*(DN?\d+[^，。\n]*)', text, re.IGNORECASE)
    if match:
        cage['pipe_diameter'] = match.group(1).strip()

    # 周长
    match = re.search(r'周长[：: ]\s*(\d+\.?\d*)\s*米?', text)
    if match:
        cage['perimeter'] = float(match.group(1))

    # 直径
    match = re.search(r'直径[：: ]\s*(\d+\.?\d*)\s*米?', text)
    if match:
        cage['diameter'] = float(match.group(1))

    # 网箱数量
    match = re.search(r'(\d+)\s*口[网箱]', text)
    if match:
        cage['cage_count'] = int(match.group(1))
    match = re.search(r'共(\d+)\s*[口个]', text)
    if match:
        cage['cage_count'] = int(match.group(1))

    # 网衣
    match = re.search(r'网衣[：:]\s*([^\n，。；;]{3,50})', text)
    if match:
        cage['net_demand'] = match.group(1).strip()

    return cage


def _extract_platform_params(text):
    """提取平台参数"""
    platform = {}

    # 面积
    match = re.search(r'面积[：: ]\s*(\d+\.?\d*)\s*(?:m2|㎡|平方米|平方)', text)
    if match:
        platform['platform_area'] = float(match.group(1))

    # 尺寸
    match = re.search(r'尺寸[：:]\s*([^\n，。；;]+)', text)
    if match:
        platform['size_spec'] = match.group(1).strip()

    return platform


def _extract_breakwater_params(text):
    """提取防波堤参数"""
    breakwater = {}

    match = re.search(r'减波率[：: ]\s*(\d+%?)', text)
    if match:
        breakwater['wave_reduction_rate'] = match.group(1)

    return breakwater


def _generate_summary(text, result):
    """生成项目概述"""
    parts = []

    if result.get('project_scale'):
        parts.append(f"项目规模：{result['project_scale']}")

    if result.get('construction_period'):
        parts.append(f"建设工期：{result['construction_period']}")

    if result.get('budget'):
        parts.append(f"投资预算：{result['budget']}")

    # 从文本中提取第一段项目描述
    desc_patterns = [
        r'项目概况[：:](.*?)(?:\n\s*\n|招标范围|投标人资格)',
        r'工程概况[：:](.*?)(?:\n\s*\n|招标范围|投标人资格)',
        r'项目简介[：:](.*?)(?:\n\s*\n|招标范围)',
    ]

    for pattern in desc_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            desc = match.group(1).strip()
            desc = re.sub(r'\s+', ' ', desc)
            if len(desc) > 50:
                desc = desc[:200] + '...'
            parts.insert(0, desc)
            break

    return '\n'.join(parts) if parts else ''


def get_supported_formats():
    """返回支持的招标文件格式"""
    return [
        {'ext': '.docx', 'name': 'Word文档', 'desc': 'Word 2007+格式'},
        {'ext': '.pdf', 'name': 'PDF文档', 'desc': 'PDF格式'},
        {'ext': '.txt', 'name': '文本文件', 'desc': '纯文本格式'},
        {'ext': '.doc', 'name': 'Word 97-2003', 'desc': '旧版Word格式（兼容性有限）'},
    ]
