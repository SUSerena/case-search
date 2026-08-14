"""
智能匹配算法模块
基于海况参数、技术规格等多维数据计算项目相似度
"""
import re
import math
from utils.location import sea_area_similarity


def extract_number(text):
    """从文本中提取第一个数值"""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    text = str(text)
    # 匹配数字（含小数）
    match = re.search(r'(\d+\.?\d*)', text)
    if match:
        return float(match.group(1))
    return None


def extract_pipe_diameter(text):
    """提取管径数值 (DNxxx 或 xxxmm 等)"""
    if not text:
        return None
    text = str(text).upper()
    match = re.search(r'DN\s*(\d+)', text)
    if match:
        return float(match.group(1))
    match = re.search(r'(\d+)\s*MM', text)
    if match:
        return float(match.group(1))
    match = re.search(r'(\d+)', text)
    if match:
        return float(match.group(1))
    return None


def numeric_similarity(val1, val2, weight=1.0):
    """
    数值相似度计算
    采用归一化距离公式: score = 1 / (1 + |v1 - v2| / max_avg)
    返回 0-1 之间的相似度
    """
    if val1 is None or val2 is None:
        return 0.0, 0.0  # 相似度, 有效权重

    if val1 == 0 and val2 == 0:
        return 1.0, weight

    avg = (abs(val1) + abs(val2)) / 2.0
    if avg == 0:
        avg = 1.0
    diff = abs(val1 - val2)
    score = 1.0 / (1.0 + diff / avg)
    return score, weight


def text_similarity(text1, text2, weight=1.0):
    """
    文本相似度（关键词匹配）
    基于共同关键词比例计算
    """
    if not text1 or not text2:
        return 0.0, 0.0

    t1 = str(text1).strip().lower()
    t2 = str(text2).strip().lower()

    if t1 == t2:
        return 1.0, weight

    # 分词（简单的按非字符分割 + 2-gram）
    def get_tokens(text):
        tokens = set()
        # 按常见分隔符切分
        parts = re.split(r'[，,。.\s、/\\()（）\[\]【】]+', text)
        for p in parts:
            if p:
                tokens.add(p)
        # 2-gram 中文
        for i in range(len(text) - 1):
            tokens.add(text[i:i + 2])
        return tokens

    tokens1 = get_tokens(t1)
    tokens2 = get_tokens(t2)

    if not tokens1 or not tokens2:
        return 0.0, weight

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2

    score = len(intersection) / len(union) if union else 0
    return score, weight


def category_match(type1, type2):
    """
    项目类型匹配
    完全匹配: 1.0
    部分包含: 0.5
    不匹配: 0.0
    """
    if not type1 or not type2:
        return 0.0
    t1 = str(type1).strip()
    t2 = str(type2).strip()
    if t1 == t2:
        return 1.0
    # 检查包含关系（如 "平台＋网箱" 包含 "网箱"）
    if t1 in t2 or t2 in t1:
        return 0.6
    return 0.0


def calculate_similarity(query, project):
    """
    计算查询条件与历史项目的综合相似度

    query: 查询参数字典
        - project_type: 项目类型
        - water_depth: 水深 (m)
        - max_wave_height: 最大波高 (m)
        - max_flow_speed: 最大流速 (m/s)
        - water_level_diff: 水位差 (m)
        - max_wind_speed: 最大风速 (m/s)
        - seabed_type: 底质类型
        - pipe_diameter: 管径
        - perimeter: 周长 (m)
        - diameter: 直径 (m)
        - cage_count: 网箱数量
        - platform_area: 平台面积 (m2)
        - keywords: 关键词/描述

    project: 历史项目数据字典

    返回: 0-100 的相似度分数
    """
    scores = []
    weights = []

    # 1. 项目类型匹配（权重最高，硬性筛选）
    if query.get('project_type'):
        type_score = category_match(query['project_type'], project.get('project_type'))
        scores.append(type_score * 100)
        weights.append(18)  # 权重18%

        # 如果类型完全不匹配，直接给很低的分
        if type_score == 0:
            return 5.0  # 基础分，完全不同类型

    # 2. 海域/地域匹配（新增）
    q_sea = query.get('sea_area') or query.get('province') or query.get('location')
    p_sea = project.get('sea_area')
    if q_sea and p_sea:
        # 优先用海域直接匹配
        if query.get('sea_area') and p_sea:
            sea_score = sea_area_similarity(query['sea_area'], p_sea)
            scores.append(sea_score * 100)
            weights.append(6)
        # 城市匹配
        elif query.get('location') and project.get('location'):
            loc_score, _ = text_similarity(query['location'], project['location'], weight=1)
            if loc_score > 0:
                scores.append(loc_score * 100)
                weights.append(4)

    # 3. 水深匹配
    q_depth = extract_number(query.get('water_depth'))
    p_depth = project.get('water_depth')
    if p_depth is None:
        p_depth = extract_number(p_depth)
    score, w = numeric_similarity(q_depth, p_depth, weight=15)
    if w > 0:
        scores.append(score * 100)
        weights.append(w)

    # 3. 最大波高匹配
    q_wave = extract_number(query.get('max_wave_height'))
    p_wave = project.get('max_wave_height')
    score, w = numeric_similarity(q_wave, p_wave, weight=12)
    if w > 0:
        scores.append(score * 100)
        weights.append(w)

    # 4. 最大流速匹配
    q_flow = extract_number(query.get('max_flow_speed'))
    p_flow = project.get('max_flow_speed')
    score, w = numeric_similarity(q_flow, p_flow, weight=10)
    if w > 0:
        scores.append(score * 100)
        weights.append(w)

    # 5. 水位差匹配
    q_wl = extract_number(query.get('water_level_diff'))
    p_wl = project.get('water_level_diff')
    score, w = numeric_similarity(q_wl, p_wl, weight=5)
    if w > 0:
        scores.append(score * 100)
        weights.append(w)

    # 6. 最大风速匹配
    q_wind = extract_number(query.get('max_wind_speed'))
    p_wind = project.get('max_wind_speed')
    score, w = numeric_similarity(q_wind, p_wind, weight=5)
    if w > 0:
        scores.append(score * 100)
        weights.append(w)

    # 7. 底质类型匹配
    if query.get('seabed_type') and project.get('seabed_type'):
        score, w = text_similarity(query['seabed_type'], project['seabed_type'], weight=5)
        if w > 0:
            scores.append(score * 100)
            weights.append(w)

    # 8. 管径匹配
    if query.get('pipe_diameter'):
        q_pipe = extract_pipe_diameter(query['pipe_diameter'])
        # 尝试网箱管径和平台管径
        p_pipe_options = [
            project.get('cage_pipe_dia'),
            project.get('platform_pipe_dia'),
            project.get('breakwater_pipe_dia')
        ]
        best_pipe_score = 0
        for p_opt in p_pipe_options:
            p_pipe = extract_pipe_diameter(p_opt)
            score, _ = numeric_similarity(q_pipe, p_pipe, weight=1)
            if score > best_pipe_score:
                best_pipe_score = score
        if best_pipe_score > 0:
            scores.append(best_pipe_score * 100)
            weights.append(8)

    # 9. 周长/直径匹配
    q_perim = extract_number(query.get('perimeter'))
    p_perim = project.get('perimeter')
    score, w = numeric_similarity(q_perim, p_perim, weight=8)
    if w > 0:
        scores.append(score * 100)
        weights.append(w)

    q_dia = extract_number(query.get('diameter'))
    p_dia = project.get('diameter')
    score, w = numeric_similarity(q_dia, p_dia, weight=6)
    if w > 0:
        scores.append(score * 100)
        weights.append(w)

    # 10. 网箱数量匹配
    q_count = extract_number(query.get('cage_count'))
    p_count = project.get('cage_count')
    score, w = numeric_similarity(q_count, p_count, weight=5)
    if w > 0:
        scores.append(score * 100)
        weights.append(w)

    # 11. 平台面积匹配
    q_area = extract_number(query.get('platform_area'))
    p_area = project.get('platform_area')
    score, w = numeric_similarity(q_area, p_area, weight=6)
    if w > 0:
        scores.append(score * 100)
        weights.append(w)

    # 12. 关键词/描述文本匹配
    if query.get('keywords'):
        # 和项目多个字段做匹配
        text_fields = [
            project.get('project_name', ''),
            project.get('description', ''),
            project.get('net_demand', ''),
            project.get('size_spec', ''),
            project.get('cage_type', ''),
            project.get('spec_type', '')
        ]
        combined_text = ' '.join(str(t) for t in text_fields if t)
        score, w = text_similarity(query['keywords'], combined_text, weight=5)
        if w > 0:
            scores.append(score * 100)
            weights.append(w)

    # 加权平均
    if not scores or not weights:
        return 20.0  # 默认基础分

    total_weight = sum(weights)
    if total_weight == 0:
        return 20.0

    weighted_sum = sum(s * w for s, w in zip(scores, weights))
    final_score = weighted_sum / total_weight

    return round(final_score, 1)


def match_projects(query, all_projects, top_n=10):
    """
    对所有历史项目进行相似度匹配，返回排序后的结果

    query: 查询参数字典
    all_projects: 所有历史项目列表
    top_n: 返回前N个

    返回: 按相似度从高到低排序的项目列表，每个项目增加 similarity 字段
    """
    results = []
    for proj in all_projects:
        sim = calculate_similarity(query, proj)
        proj_copy = dict(proj)
        proj_copy['similarity'] = sim
        results.append(proj_copy)

    # 按相似度降序排序
    results.sort(key=lambda x: x['similarity'], reverse=True)

    return results[:top_n]
