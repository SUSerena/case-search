"""
用户认证模块
密码加密、登录状态管理、login_required 装饰器
"""
import re
import functools
from flask import session, redirect, url_for, request
from werkzeug.security import generate_password_hash, check_password_hash

from utils.db import (
    create_user, get_user_by_username, get_user_by_phone,
    get_user_by_id, update_last_login, add_access_log
)


def hash_password(password):
    """密码加密"""
    return generate_password_hash(password)


def verify_password(password, password_hash):
    """验证密码"""
    return check_password_hash(password_hash, password)


def is_logged_in():
    """检查是否已登录"""
    return 'user_id' in session


def current_user():
    """获取当前登录用户信息，未登录返回 None"""
    if not is_logged_in():
        return None
    return get_user_by_id(session['user_id'])


def login_required(view):
    """登录验证装饰器"""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    """管理员验证装饰器"""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login'))
        user = get_user_by_id(session['user_id'])
        if not user or user.get('role') != 'admin':
            return redirect(url_for('index'))
        return view(*args, **kwargs)
    return wrapped


def do_login(username_or_phone, password):
    """
    执行登录验证
    支持用户名或手机号登录
    返回: (success: bool, message: str, user: dict|None)
    """
    # 尝试用户名登录
    user = get_user_by_username(username_or_phone)
    if not user:
        # 尝试手机号登录
        user = get_user_by_phone(username_or_phone)

    if not user:
        return False, '用户不存在', None

    # 检查审核状态
    status = user.get('status', 'approved')
    if status == 'pending':
        return False, '您的账号正在等待管理员审核，请耐心等待', None
    if status == 'disabled':
        return False, '您的账号已被禁用，请联系管理员', None

    if not verify_password(password, user['password_hash']):
        return False, '密码错误', None

    # 登录成功，写入 session
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user.get('role', 'user')

    # 更新最后登录时间
    update_last_login(user['id'])

    # 记录访问日志
    add_access_log(
        user['id'], user['phone'], user['username'],
        request.remote_addr or '',
        request.headers.get('User-Agent', ''),
        'login'
    )

    return True, '登录成功', user


def do_register(username, phone, password):
    """
    执行注册
    返回: (success: bool, message: str, user: dict|None)
    """
    # 手机号格式校验
    if not re.match(r'^1[3-9]\d{9}$', phone):
        return False, '手机号格式不正确（需为11位有效手机号）', None

    if len(username) < 2:
        return False, '用户名至少2个字符', None

    if len(password) < 6:
        return False, '密码至少6个字符', None

    # 检查用户名是否已存在
    if get_user_by_username(username):
        return False, '用户名已存在', None

    # 检查手机号是否已注册
    if get_user_by_phone(phone):
        return False, '该手机号已注册', None

    # 创建用户（status 默认 pending，待管理员审核）
    password_hash = hash_password(password)
    user_id = create_user(username, phone, password_hash, status='pending')

    # 记录访问日志
    add_access_log(
        user_id, phone, username,
        request.remote_addr or '',
        request.headers.get('User-Agent', ''),
        'register'
    )

    # 不自动登录，返回提示信息
    return True, '注册成功，您的账号正在等待管理员审核，审核通过后即可登录使用', None


def do_logout():
    """登出"""
    if is_logged_in():
        user = get_user_by_id(session['user_id'])
        if user:
            add_access_log(
                user['id'], user.get('phone', ''), user.get('username', ''),
                request.remote_addr or '',
                request.headers.get('User-Agent', ''),
                'logout'
            )
    session.clear()
