import os
import re
import shutil
import requests
import time
from concurrent.futures import ThreadPoolExecutor

# 配置参数
DEEPSEEK_API_KEY = "这里填你的API密钥"  # API密钥（必需项）
SOURCE_DIR = "./"  # Markdown文件存放路径，默认为根目录
BASE_DIR = "./"  # 分类存储路径，默认为根目录
CATEGORIES = ["自然科学", "人文社科", "学习成长", "哲学思辨", "工程技术", "财经投资", "时事时政", "情感生活", "体育健康", "文娱艺术", "搞笑趣闻", "外貌穿搭"]  # 分类收藏夹（根据需求设置）

# API配置
API_URL = "https://api.deepseek.com/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    "Content-Type": "application/json"
}


def classify_title(title):
    """使用DeepSeek API进行分类"""
    SYSTEM_PROMPT = f"""将以下知乎标题分类到且仅能分类到以下类别之一：{', '.join(CATEGORIES)}。
直接返回中文类别名称，不要任何其他内容或格式。"""

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": title}],
        "temperature": 0.1,
        "max_tokens": 200
    }

    try:
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=30)
        response.encoding = 'utf-8'  # 显式设置响应编码
        response.raise_for_status()
        result = response.json()['choices'][0]['message']['content'].strip()
        return result if result in CATEGORIES else "其他"
    except Exception as e:
        print(f"分类失败：{str(e)}")
        return "其他"


def process_file(filename):
    """处理单个文件"""
    src_path = os.path.join(SOURCE_DIR, filename)
    if not filename.endswith(".md"):
        return

    title = os.path.splitext(filename)[0]

    try:
        # 获取分类
        category = classify_title(title)
        # 创建目标目录
        dest_dir = os.path.join(BASE_DIR, category)
        os.makedirs(dest_dir, exist_ok=True)
        # 移动文件
        shutil.move(src_path, os.path.join(dest_dir, filename))
        print(f"已移动：{title} -> {category}")
    except Exception as e:
        print(f"处理失败：{filename} - {str(e)}")
    finally:
        time.sleep(0.1)  # 控制请求频率


def main():
    # 初始化目录
    os.makedirs(BASE_DIR, exist_ok=True)
    for category in CATEGORIES:
        os.makedirs(os.path.join(BASE_DIR, category), exist_ok=True)

    # 获取文件列表
    files = [f for f in os.listdir(SOURCE_DIR) if f.endswith(".md")]
    print(f"发现 {len(files)} 个待处理文件")

    # 使用线程池并行处理（注意API的并发限制）
    with ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(process_file, files)

    input("分类完成，按任意键退出...")


if __name__ == "__main__":
    main()
