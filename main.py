import os
import shutil
import requests
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


# 配置参数
DEEPSEEK_API_KEY = "这里填你的API密钥"  # API密钥（必需项）
SOURCE_DIR = "./"  # Markdown文件存放路径，默认为根目录
BASE_DIR = "./"  # 分类存储路径，默认为根目录
CATEGORIES = ["自然科学", "人文社科", "学习成长", "哲学思辨", "工程技术", "财经投资", "时事时政", "情感生活", "体育健康", "文娱艺术", "搞笑趣闻", "外貌穿搭"]  # 分类收藏夹（根据需求设置）

# API配置
API_URL = "https://api.deepseek.com/v1/chat/completions"
COMMON_HEADERS = {  # 更名为 COMMON_HEADERS，因为 Session 也会用
    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    "Content-Type": "application/json"
}

# 创建全局的 requests.Session 对象
API_SESSION = requests.Session()
API_SESSION.headers.update(COMMON_HEADERS)


@retry(
    stop=stop_after_attempt(5),  # 最多尝试5次
    wait=wait_exponential(multiplier=1, min=2, max=10),  # 指数退避：2s, 4s, 8s, 10s (第四次重试后等待10s)
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError))  # 对这些异常类型重试
)
def classify_title_with_retry(title: str) -> str:
    """使用DeepSeek API进行分类（带重试）"""
    SYSTEM_PROMPT = f"""将以下知乎标题分类到且仅能分类到以下类别之一：{', '.join(CATEGORIES)}。
直接返回中文类别名称，不要任何其他内容或格式。"""

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": title}],
        "temperature": 0.1,
        "max_tokens": 200  # 类别名称通常很短，200应该足够
    }

    response = API_SESSION.post(API_URL, json=payload, timeout=15)  # 使用 session，单次超时15秒
    response.encoding = 'utf-8'
    response.raise_for_status()  # 如果状态码是 4xx 或 5xx，将引发 HTTPError，tenacity会处理重试

    data = response.json()
    if data and 'choices' in data and data['choices'] and 'message' in data['choices'][0] and 'content' in data['choices'][0]['message']:
        result = data['choices'][0]['message']['content'].strip()
        return result if result in CATEGORIES else "其他"
    else:
        # API返回了成功状态码，但响应体结构不符合预期
        # print(f"警告：API响应格式不符合预期，标题：{title}, 响应: {data}") # 可以取消注释用于调试
        return "其他"


def classify_title(title: str) -> str:
    """封装带重试的分类函数，处理最终的异常"""
    try:
        return classify_title_with_retry(title)
    except requests.exceptions.HTTPError as e:
        # 特殊处理一些不应重试的HTTP错误，比如400 Bad Request
        if e.response is not None and e.response.status_code == 400:
            tqdm.write(f"分类失败 (400 Bad Request, 不重试): {title} - {str(e)}")  # 使用 tqdm.write 避免扰乱进度条
            return "其他"
        # 对于 tenacity 重试多次后仍然失败的 HTTPError
        tqdm.write(f"分类失败 (多次重试后 HTTPError): {title} - {str(e)}")
        return "其他"
    except Exception as e:  # 捕获 tenacity 重试多次后的其他所有异常
        tqdm.write(f"分类失败 (多次重试后): {title} - {str(e)}")
        return "其他"


def process_file(filename: str) -> str:
    """处理单个文件，返回处理结果字符串"""
    src_path = os.path.join(SOURCE_DIR, filename)
    if not filename.endswith(".md"):
        return f"跳过非Markdown文件: {filename}"  # 返回信息

    title = os.path.splitext(filename)[0]
    category = "其他"  # 默认分类

    try:
        category = classify_title(title)

        dest_dir = os.path.join(BASE_DIR, category)
        os.makedirs(dest_dir, exist_ok=True)

        dest_file_path = os.path.join(dest_dir, filename)
        shutil.move(src_path, dest_file_path)
        return f"成功: {title} -> {category}"  # 返回成功信息
    except Exception as e:
        # 此处的异常更多是文件操作失败，API调用失败已在classify_title中处理
        tqdm.write(f"文件处理失败: {filename} (目标分类: {category}) - {str(e)}")
        # 考虑是否将文件移至一个专门的“处理失败”目录
        return f"失败: {filename} - {str(e)} (分类尝试: {category})"
    # finally:
    #     time.sleep(0.1) # 已移除


def main():
    # 初始化目录
    os.makedirs(BASE_DIR, exist_ok=True)
    all_target_categories = CATEGORIES + ["其他"]  # 包括“其他”文件夹
    for category_name in all_target_categories:
        os.makedirs(os.path.join(BASE_DIR, category_name), exist_ok=True)

    # 获取文件列表
    try:
        files = [f for f in os.listdir(SOURCE_DIR) if os.path.isfile(os.path.join(SOURCE_DIR, f)) and f.endswith(".md")]
    except FileNotFoundError:
        print(f"错误：源目录 {SOURCE_DIR} 未找到。请检查 SOURCE_DIR 配置。")
        input("按任意键退出...")
        return

    if not files:
        print(f"在 {SOURCE_DIR} 中没有找到 .md 文件。")
        input("按任意键退出...")
        return

    print(f"发现 {len(files)} 个 .md 待处理文件，将从 {SOURCE_DIR} 移动到 {BASE_DIR} 下的分类目录。")

    # 建议的 max_workers 值，可以根据机器性能和网络情况调整
    # 如果文件非常多，API响应稳定，可以尝试更高的值如 50, 100, 甚至 200
    # 如果遇到问题（如API错误增多，或本地资源耗尽），则降低此值
    num_workers = 50  # 初始值，你可以调整
    print(f"使用 {num_workers} 个工作线程进行处理...")

    processed_results = []
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # executor.map 会保持原始顺序，所以 tqdm 可以正确显示进度
        # list() 会立即执行所有任务并等待它们完成
        processed_results = list(tqdm(executor.map(process_file, files), total=len(files), desc="文件分类中"))

    success_count = 0
    failure_count = 0
    # 打印总结信息（可选，如果 tqdm.write 已经输出了足够的错误信息）
    print("\n--- 处理结果总结 ---")
    for result in processed_results:
        if result:  # process_file 总是返回字符串
            if result.startswith("成功:"):
                success_count += 1
            elif result.startswith("失败:") or "失败 (" in result:  # 覆盖 classify_title 返回的错误信息
                failure_count += 1
                # tqdm.write(result) # 如果希望在最后统一打印失败信息
            # "跳过" 的信息一般不需要特别统计

    print(f"\n分类完成！成功处理 {success_count} 个文件，失败 {failure_count} 个文件。")
    if failure_count > 0:
        print("请检查上面由 tqdm.write 输出的失败详情。")
    input("按任意键退出...")


if __name__ == "__main__":
    main()
