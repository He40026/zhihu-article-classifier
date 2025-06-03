import os
import shutil
import requests
import time
import json
import yaml
import re
import signal
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict

# 轻量级模式配置 - 设置为False可避免pandas等重型依赖
ENABLE_ADVANCED_FEATURES = True  # 是否启用高级功能（需要pandas、openpyxl等依赖）

# 条件导入pandas（仅在启用高级功能时）
if ENABLE_ADVANCED_FEATURES:
    try:
        import pandas as pd
        PANDAS_AVAILABLE = True
    except ImportError:
        print("警告: pandas未安装或导入失败，将使用轻量级模式")
        PANDAS_AVAILABLE = False
        ENABLE_ADVANCED_FEATURES = False
else:
    PANDAS_AVAILABLE = False


# AI配置参数
OPENAI_API_KEY = "sk-sdadadawdada"  # OpenAI API密钥（必需项）
OPENAI_BASE_URL = "https://api.vveai.com/v1"  # OpenAI Base API URL，可以自定义（如使用代理或其他兼容的API服务）
OPENAI_MODEL = "gpt-4.1"

DEEPSEEK_API_KEY = "sk-test"  # DeepSeek API密钥（必需项）
DEEPSEEK_BASE_URL = "https://api.deepseek.com"  # DeepSeek API Base URL
DEEPSEEK_MODEL = "deepseek-chat"  # DeepSeek 模型名称


# AI服务配置管理
CURRENT_AI_PROVIDER = "auto"  # 当前使用的AI服务提供商: "auto", "openai", "deepseek"
PREFERRED_AI_PROVIDER = "deepseek"  # 首选的AI服务提供商

# 应用配置
SOURCE_DIR = "D:\Desktop\Zhihu-Collection-Downloader-main\docs\我的收藏夹"  # Markdown文件存放路径，默认为根目录
BASE_DIR = "D:\Desktop\Zhihu-Collection-Downloader-main\docs\分类"  # 分类存储路径，默认为根目录
CATEGORIES = ["知识学习", "科技互联网", "人文社科", "哲学思辨", "专业技术", "情感生活", "文娱艺术", "轻松娱乐"]  # 优化后的分类体系（8个清晰互斥的类别）

# API配置参数
API_TIMEOUT = 30  # API请求超时时间（秒）
ENABLE_DEBUG_OUTPUT = True  # 是否启用调试输出（显示发送给AI的内容）

# 中途停止控制
ENABLE_GRACEFUL_STOP = True  # 是否启用优雅停止机制
ENABLE_PAUSE_RESUME = True  # 是否启用暂停/继续功能
SAVE_PROGRESS_INTERVAL = 10  # 每处理多少个文件保存一次进度

# 新增功能配置
ENABLE_CONTENT_ANALYSIS = True  # 是否启用内容分析功能
ENABLE_TAG_EXTRACTION = True  # 是否启用标签提取功能
ENABLE_RESULT_EXPORT = ENABLE_ADVANCED_FEATURES  # 是否启用结果导出功能（依赖pandas）
EXPORT_FORMAT = ["csv", "excel"] if ENABLE_ADVANCED_FEATURES else []  # 导出格式，可选: "csv", "excel"
MAX_CONTENT_LENGTH = 2000  # 分析的文章内容最大字符数，避免API调用过长

# 动态API配置（将根据当前提供商动态设置）
API_URL = ""
COMMON_HEADERS = {}

# 预定义标签体系 - 解决标签杂乱问题
PREDEFINED_TAGS = {
    "知识学习": [
        "学习方法", "教育", "读书", "思维训练", "记忆技巧", "学习经验", "知识管理",
        "自我提升", "技能学习", "在线教育", "培训", "考试", "学术研究", "终身学习"
    ],
    "科技互联网": [
        "人工智能", "机器学习", "编程", "软件开发", "互联网", "科技趋势", "数据科学",
        "云计算", "区块链", "移动开发", "前端开发", "后端开发", "产品经理", "科技评测",
        "网络安全", "大数据", "物联网", "AR/VR", "量子计算", "开源项目"
    ],
    "人文社科": [
        "历史", "文学", "社会学", "心理学", "政治", "经济学", "地理", "人类学",
        "语言学", "文化", "社会现象", "传统文化", "国际关系", "法律", "新闻传播"
    ],
    "哲学思辨": [
        "哲学", "逻辑思维", "人生感悟", "价值观", "世界观", "认知科学", "批判思维",
        "道德伦理", "存在主义", "理性思考", "辩证法", "思想实验", "人性思考"
    ],
    "专业技术": [
        "工程技术", "医学", "金融", "法律实务", "建筑", "设计", "制造业", "能源",
        "环保", "农业", "生物技术", "化学", "物理", "数学", "统计学", "项目管理",
        "质量管理", "供应链", "创业", "商业模式", "市场营销", "品牌建设"
    ],
    "情感生活": [
        "恋爱", "婚姻", "家庭", "亲子教育", "人际关系", "情感咨询", "心理健康",
        "社交技巧", "个人成长", "情绪管理", "压力缓解", "生活方式", "健康养生",
        "美食", "旅行", "运动健身", "时尚", "美容护肤"
    ],
    "文娱艺术": [
        "电影", "音乐", "文学作品", "艺术", "绘画", "摄影", "戏剧", "舞蹈",
        "书评", "影评", "游戏", "动漫", "文化创意", "设计美学", "收藏"
    ],
    "轻松娱乐": [
        "搞笑", "段子", "趣闻", "八卦", "网络梗", "生活趣事", "宠物", "美食分享",
        "旅行见闻", "日常生活", "休闲娱乐", "兴趣爱好", "放松心情", "治愈系"
    ]
}

# 标签规范化映射 - 将相似标签统一
TAG_NORMALIZATION = {
    "AI": "人工智能", "ML": "机器学习", "深度学习": "机器学习", "神经网络": "机器学习",
    "Python": "编程", "Java": "编程", "JavaScript": "编程", "代码": "编程", "算法": "编程",
    "前端": "前端开发", "后端": "后端开发", "全栈": "软件开发", "APP": "移动开发", "小程序": "移动开发",
    "创新": "科技趋势", "技术": "专业技术", "工作": "专业技术", "职场": "专业技术",
    "管理": "项目管理", "领导力": "项目管理", "读书笔记": "读书", "书籍": "读书",
    "学习笔记": "学习方法", "效率": "学习方法", "时间管理": "学习方法",
    "思考": "哲学思辨", "感悟": "人生感悟", "生活感悟": "人生感悟", "心理": "心理学",
    "沟通": "社交技巧", "交流": "社交技巧", "关系": "人际关系", "爱情": "恋爱",
    "健康": "健康养生", "养生": "健康养生", "锻炼": "运动健身", "健身": "运动健身",
    "电影推荐": "电影", "观影": "电影", "音乐推荐": "音乐", "歌曲": "音乐",
    "游戏评测": "游戏", "玩家": "游戏", "幽默": "搞笑", "有趣": "趣闻", "生活": "日常生活"
}

#---------------------------------------------------分割线-------------------------------------------------

class AIServiceManager:
    """AI服务管理器 - 管理OpenAI和DeepSeek服务的切换"""
    
    def __init__(self):
        self.current_provider = CURRENT_AI_PROVIDER
        self.preferred_provider = PREFERRED_AI_PROVIDER
        self.session = None
        self._initialize_service()
    
    def _initialize_service(self):
        """初始化AI服务"""
        try:
            provider = self._get_best_available_provider()
            self._setup_provider(provider)
            print(f"[AI服务] 初始化成功，使用 {provider.upper()} 服务")
        except Exception as e:
            print(f"[错误] AI服务初始化失败: {e}")
            raise
    
    def _setup_provider(self, provider: str):
        """设置当前使用的AI服务提供商"""
        global API_URL, COMMON_HEADERS
        
        self.current_provider = provider
        
        if provider == "openai":
            API_URL = f"{OPENAI_BASE_URL}/chat/completions"
            COMMON_HEADERS = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
        elif provider == "deepseek":
            API_URL = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
            COMMON_HEADERS = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
        else:
            raise ValueError(f"不支持的AI服务提供商: {provider}")
        
        # 创建新的会话
        self.session = requests.Session()
        self.session.headers.update(COMMON_HEADERS)
    
    def _test_provider_connection(self, provider: str) -> Tuple[bool, str]:
        """测试指定提供商的连接"""
        if provider == "openai":
            if not OPENAI_API_KEY.strip() or OPENAI_API_KEY == "sk-your-openai-api-key-here":
                return False, "OpenAI API密钥未配置"
            api_key = OPENAI_API_KEY
            base_url = OPENAI_BASE_URL
            model = OPENAI_MODEL
        elif provider == "deepseek":
            if not DEEPSEEK_API_KEY.strip() or DEEPSEEK_API_KEY == "sk-your-deepseek-api-key-here":
                return False, "DeepSeek API密钥未配置"
            api_key = DEEPSEEK_API_KEY
            base_url = DEEPSEEK_BASE_URL
            model = DEEPSEEK_MODEL
        else:
            return False, f"不支持的提供商: {provider}"
        
        # 构建测试请求
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        test_payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 5,
            "temperature": 0.1
        }
        
        try:
            url = f"{base_url}/v1/chat/completions" if provider == "deepseek" else f"{base_url}/chat/completions"
            response = requests.post(url, headers=headers, json=test_payload, timeout=10)
            
            if response.status_code == 200:
                return True, f"{provider} 连接成功"
            elif response.status_code == 401:
                return False, f"{provider} API密钥无效"
            elif response.status_code == 429:
                return False, f"{provider} API调用频率限制"
            else:
                return False, f"{provider} 连接失败: HTTP {response.status_code}"
        except requests.exceptions.Timeout:
            return False, f"{provider} 连接超时"
        except requests.exceptions.ConnectionError:
            return False, f"{provider} 网络连接错误"
        except Exception as e:
            return False, f"{provider} 测试失败: {str(e)}"
    
    def _get_best_available_provider(self) -> str:
        """获取最佳可用的AI服务提供商"""
        # 如果指定了特定提供商且不是auto，直接检查该提供商
        if self.current_provider != "auto":
            is_available, _ = self._test_provider_connection(self.current_provider)
            if is_available:
                return self.current_provider
            else:
                print(f"[警告] 指定的提供商 {self.current_provider} 不可用，尝试自动选择")
        
        # 自动模式：优先使用preferred_provider
        is_available, _ = self._test_provider_connection(self.preferred_provider)
        if is_available:
            return self.preferred_provider
        
        # 如果preferred不可用，尝试其他提供商
        all_providers = ["openai", "deepseek"]
        for provider in all_providers:
            if provider != self.preferred_provider:
                is_available, _ = self._test_provider_connection(provider)
                if is_available:
                    return provider
        
        raise RuntimeError("没有可用的AI服务提供商")
    
    def switch_provider(self, provider: str):
        """切换AI服务提供商"""
        if provider not in ["auto", "openai", "deepseek"]:
            raise ValueError(f"不支持的AI服务提供商: {provider}")
        
        old_provider = self.current_provider
        self.current_provider = provider
        
        try:
            if provider == "auto":
                actual_provider = self._get_best_available_provider()
                self._setup_provider(actual_provider)
                print(f"[切换] 已切换到自动模式，当前使用: {actual_provider.upper()}")
            else:
                is_available, message = self._test_provider_connection(provider)
                if not is_available:
                    raise RuntimeError(f"无法切换到 {provider}: {message}")
                self._setup_provider(provider)
                print(f"[切换] 已切换到: {provider.upper()}")
        except Exception as e:
            # 切换失败，恢复原来的提供商
            self.current_provider = old_provider
            self._setup_provider(old_provider)
            raise e
    
    def set_preferred_provider(self, provider: str):
        """设置首选提供商"""
        if provider not in ["openai", "deepseek"]:
            raise ValueError(f"不支持的AI服务提供商: {provider}")
        
        self.preferred_provider = provider
        print(f"[配置] 首选AI服务提供商已设置为: {provider.upper()}")
    
    def get_current_provider_info(self) -> Tuple[str, str]:
        """获取当前使用的AI服务提供商信息"""
        if self.current_provider == "openai":
            return "openai", OPENAI_MODEL
        elif self.current_provider == "deepseek":
            return "deepseek", DEEPSEEK_MODEL
        else:
            return "未知", "未知"
    
    def get_provider_status(self) -> Dict[str, Tuple[bool, str]]:
        """获取所有提供商的状态"""
        providers = ["openai", "deepseek"]
        status = {}
        
        for provider in providers:
            status[provider] = self._test_provider_connection(provider)
        
        return status
    
    def show_status(self):
        """显示AI服务状态"""
        print("\n=== AI服务状态 ===")
        print(f"当前设置: {self.current_provider}")
        print(f"首选提供商: {self.preferred_provider}")
        
        # 获取当前实际使用的提供商
        try:
            actual_provider = self._get_best_available_provider()
            print(f"实际使用: {actual_provider.upper()}")
        except:
            print("实际使用: 无可用服务")
        
        print()
        
        # 检查所有提供商状态
        provider_status = self.get_provider_status()
        
        for provider, (is_available, message) in provider_status.items():
            status_icon = "✅" if is_available else "❌"
            print(f"{status_icon} {provider.upper()}: {message}")
            
            if provider == "openai":
                api_key_preview = OPENAI_API_KEY[:10] + "..." if len(OPENAI_API_KEY) > 10 else OPENAI_API_KEY
                print(f"   模型: {OPENAI_MODEL}")
                print(f"   API密钥: {api_key_preview}")
            elif provider == "deepseek":
                api_key_preview = DEEPSEEK_API_KEY[:10] + "..." if len(DEEPSEEK_API_KEY) > 10 else DEEPSEEK_API_KEY
                print(f"   模型: {DEEPSEEK_MODEL}")
                print(f"   API密钥: {api_key_preview}")
            print()
    
    def interactive_setup(self):
        """交互式设置向导"""
        print("\n=== AI服务配置向导 ===")
        
        # 显示当前状态
        self.show_status()
        
        while True:
            print("\n请选择操作:")
            print("1. 切换AI服务提供商")
            print("2. 设置首选提供商")
            print("3. 测试连接")
            print("4. 显示状态")
            print("0. 返回")
            
            choice = input("\n请输入选项 (0-4): ").strip()
            
            if choice == "1":
                self._switch_provider_menu()
            elif choice == "2":
                self._set_preferred_menu()
            elif choice == "3":
                self._test_connections()
            elif choice == "4":
                self.show_status()
            elif choice == "0":
                break
            else:
                print("无效选项，请重新选择")
    
    def _switch_provider_menu(self):
        """切换提供商菜单"""
        print("\n=== 切换AI服务提供商 ===")
        print("1. 自动选择 (推荐)")
        print("2. 固定使用 OpenAI")
        print("3. 固定使用 DeepSeek")
        
        choice = input("\n请选择 (1-3): ").strip()
        
        try:
            if choice == "1":
                self.switch_provider("auto")
                print("✅ 已设置为自动选择模式")
            elif choice == "2":
                self.switch_provider("openai")
                print("✅ 已设置为固定使用 OpenAI")
            elif choice == "3":
                self.switch_provider("deepseek")
                print("✅ 已设置为固定使用 DeepSeek")
            else:
                print("无效选项")
        except Exception as e:
            print(f"❌ 切换失败: {e}")
    
    def _set_preferred_menu(self):
        """设置首选提供商菜单"""
        print("\n=== 设置首选提供商 ===")
        print("(自动模式下优先使用)")
        print("1. OpenAI")
        print("2. DeepSeek")
        
        choice = input("\n请选择 (1-2): ").strip()
        
        if choice == "1":
            self.set_preferred_provider("openai")
            print("✅ 首选提供商已设置为 OpenAI")
        elif choice == "2":
            self.set_preferred_provider("deepseek")
            print("✅ 首选提供商已设置为 DeepSeek")
        else:
            print("无效选项")
    
    def _test_connections(self):
        """测试所有连接"""
        print("\n=== 测试API连接 ===")
        
        provider_status = self.get_provider_status()
        
        for provider, (is_available, message) in provider_status.items():
            status_icon = "✅" if is_available else "❌"
            print(f"{status_icon} {provider.upper()}: {message}")
        
        # 显示当前最佳提供商
        try:
            best_provider = self._get_best_available_provider()
            print(f"\n🔥 当前最佳可用提供商: {best_provider.upper()}")
        except Exception as e:
            print(f"\n⚠️  {e}")

# 创建全局AI服务管理器
ai_service_manager = AIServiceManager()

# 创建全局的 requests.Session 对象
def create_api_session():
    """创建配置好的API会话对象"""
    return ai_service_manager.session

API_SESSION = create_api_session()

# 全局停止控制变量
stop_processing = threading.Event()
pause_processing = threading.Event()
progress_save_lock = threading.Lock()

class GracefulStopHandler:
    """优雅停止处理器"""
    
    def __init__(self):
        self.stop_requested = False
        self.pause_requested = False
        
    def signal_handler(self, signum, frame):
        """处理Ctrl+C信号"""
        print(f"\n[警告] 接收到停止信号 (信号: {signum})")
        print("正在优雅停止处理...")
        print("请稍等，正在完成当前文件的处理...")
        stop_processing.set()
        self.stop_requested = True
        
    def setup_signal_handlers(self):
        """设置信号处理器"""
        if ENABLE_GRACEFUL_STOP:
            signal.signal(signal.SIGINT, self.signal_handler)
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, self.signal_handler)

# 全局停止处理器实例
stop_handler = GracefulStopHandler()



@dataclass
class ProcessResult:
    """处理结果数据类"""
    filename: str
    original_title: str
    category: str
    tags: List[str]
    process_time: float
    success: bool
    error_message: Optional[str] = None
    content_preview: Optional[str] = None
    # Frontmatter元数据字段
    title: Optional[str] = None
    url: Optional[str] = None
    author: Optional[str] = None
    author_badge: Optional[str] = None
    created: Optional[str] = None
    modified: Optional[str] = None
    upvote_num: Optional[int] = None
    comment_num: Optional[int] = None
    # 统计分析字段
    word_count: Optional[int] = None
    content_summary: Optional[str] = None
    processing_status: Optional[str] = None


class ProgressManager:
    """进度管理器 - 处理进度保存和恢复"""
    
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.progress_file = os.path.join(base_dir, ".classification_progress.json")
        self.processed_files = set()
        self.failed_files = set()
        
    def load_progress(self) -> Tuple[set, set]:
        """加载之前的进度"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.processed_files = set(data.get('processed_files', []))
                    self.failed_files = set(data.get('failed_files', []))
                    print(f"[文件] 加载进度: 已处理 {len(self.processed_files)} 个文件，失败 {len(self.failed_files)} 个文件")
                    return self.processed_files, self.failed_files
            except Exception as e:
                print(f"[警告] 加载进度失败: {e}")
        return set(), set()
    
    def save_progress(self, processed_files: set, failed_files: set):
        """保存当前进度"""
        try:
            with progress_save_lock:
                progress_data = {
                    'processed_files': list(processed_files),
                    'failed_files': list(failed_files),
                    'last_save_time': datetime.now().isoformat(),
                    'total_processed': len(processed_files) + len(failed_files)
                }
                with open(self.progress_file, 'w', encoding='utf-8') as f:
                    json.dump(progress_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[警告] 保存进度失败: {e}")
    
    def clear_progress(self):
        """清除进度文件"""
        if os.path.exists(self.progress_file):
            try:
                os.remove(self.progress_file)
                print("[删除] 已清除进度文件")
            except Exception as e:
                print(f"[警告] 清除进度文件失败: {e}")


class UserInputHandler:
    """用户输入处理器 - 处理运行时用户交互"""
    
    def __init__(self):
        self.input_thread = None
        self.running = False
        
    def start_input_monitoring(self):
        """开始监听用户输入"""
        if not ENABLE_PAUSE_RESUME:
            return
            
        self.running = True
        self.input_thread = threading.Thread(target=self._input_loop, daemon=True)
        self.input_thread.start()
        print("[提示] 处理过程中可以按以下键操作:")
        print("   - 'p' + Enter: 暂停处理")
        print("   - 'r' + Enter: 继续处理")
        print("   - 'q' + Enter: 优雅停止")
        print("   - Ctrl+C: 强制停止")
        print()
    
    def stop_input_monitoring(self):
        """停止监听用户输入"""
        self.running = False
        
    def _input_loop(self):
        """输入监听循环"""
        while self.running:
            try:
                user_input = input().strip().lower()
                if user_input == 'p':
                    print("[暂停] 暂停处理中...")
                    pause_processing.set()
                elif user_input == 'r':
                    print("[继续] 继续处理...")
                    pause_processing.clear()
                elif user_input == 'q':
                    print("[停止] 用户请求停止...")
                    stop_processing.set()
                    break
                elif user_input == 'help' or user_input == 'h':
                    print("可用命令: p(暂停), r(继续), q(停止), help(帮助)")
            except EOFError:
                break
            except Exception:
                continue


class ResultManager:
    """结果管理器"""
    
    def __init__(self):
        self.results: List[ProcessResult] = []
        self.start_time = datetime.now()
    
    def add_result(self, result: ProcessResult):
        """添加处理结果"""
        self.results.append(result)
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        total_files = len(self.results)
        success_count = sum(1 for r in self.results if r.success)
        failure_count = total_files - success_count
        
        # 分类统计
        category_stats = {}
        for result in self.results:
            if result.success:
                category = result.category
                if category not in category_stats:
                    category_stats[category] = 0
                category_stats[category] += 1
        
        # 处理时间统计
        if self.results:
            process_times = [r.process_time for r in self.results]
            avg_time = sum(process_times) / len(process_times)
            max_time = max(process_times)
            min_time = min(process_times)
        else:
            avg_time = max_time = min_time = 0
        
        total_time = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "total_files": total_files,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": success_count / total_files if total_files > 0 else 0,
            "category_distribution": category_stats,
            "processing_time": {
                "total_time": total_time,
                "average_per_file": avg_time,
                "max_time": max_time,
                "min_time": min_time
            }
        }
    
    def export_results(self, output_dir: str = "./"):
        """导出结果"""
        if not ENABLE_RESULT_EXPORT or not self.results:
            return
        
        if not PANDAS_AVAILABLE:
            # 轻量级模式：导出简单的文本报告
            self._export_text_report(output_dir)
            return
        
        # 准备导出数据
        export_data = []
        for result in self.results:
            export_data.append({
                # 基础列
                "文件名": result.filename,
                "标题": result.title or result.original_title,
                "URL": result.url or "",
                "分类结果": result.category,
                "提取的标签": ", ".join(result.tags) if result.tags else "",
                
                # 元数据列
                "作者": result.author or "",
                "作者认证": result.author_badge or "",
                "创建时间": result.created or "",
                "修改时间": result.modified or "",
                "点赞数": result.upvote_num if result.upvote_num is not None else "",
                "评论数": result.comment_num if result.comment_num is not None else "",
                
                # 统计分析列
                "字数统计": result.word_count if result.word_count is not None else "",
                "内容摘要": result.content_summary or "",
                "处理时间": round(result.process_time, 3),
                "处理状态": "成功" if result.success else "失败",
                "错误信息": result.error_message or ""
            })
        
        df = pd.DataFrame(export_data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 导出CSV
        if "csv" in EXPORT_FORMAT:
            csv_path = os.path.join(output_dir, f"分类结果_{timestamp}.csv")
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"CSV结果已导出到: {csv_path}")
        
        # 导出Excel
        if "excel" in EXPORT_FORMAT:
            excel_path = os.path.join(output_dir, f"分类结果_{timestamp}.xlsx")
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='分类结果', index=False)
                
                # 添加统计信息工作表
                stats = self.get_statistics()
                stats_data = []
                stats_data.append(["统计项目", "数值"])
                stats_data.append(["总文件数", stats["total_files"]])
                stats_data.append(["成功处理", stats["success_count"]])
                stats_data.append(["失败处理", stats["failure_count"]])
                stats_data.append(["成功率", f"{stats['success_rate']:.2%}"])
                stats_data.append(["总处理时间(秒)", f"{stats['processing_time']['total_time']:.2f}"])
                stats_data.append(["平均处理时间(秒)", f"{stats['processing_time']['average_per_file']:.3f}"])
                
                stats_df = pd.DataFrame(stats_data[1:], columns=stats_data[0])
                stats_df.to_excel(writer, sheet_name='统计信息', index=False)
                
                # 添加分类分布工作表
                if stats["category_distribution"]:
                    category_data = [(k, v) for k, v in stats["category_distribution"].items()]
                    category_df = pd.DataFrame(category_data, columns=["分类", "文章数量"])
                    category_df.to_excel(writer, sheet_name='分类分布', index=False)
            
            print(f"Excel结果已导出到: {excel_path}")
    
    def _export_text_report(self, output_dir: str = "./"):
        """轻量级模式：导出文本报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(output_dir, f"分类结果_{timestamp}.txt")
        
        stats = self.get_statistics()
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=== 知乎文章分类结果报告 ===\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # 统计信息
            f.write("=== 统计摘要 ===\n")
            f.write(f"总文件数: {stats['total_files']}\n")
            f.write(f"成功处理: {stats['success_count']}\n")
            f.write(f"失败处理: {stats['failure_count']}\n")
            f.write(f"成功率: {stats['success_rate']:.2%}\n")
            f.write(f"总处理时间: {stats['processing_time']['total_time']:.2f} 秒\n")
            f.write(f"平均处理时间: {stats['processing_time']['average_per_file']:.3f} 秒/文件\n\n")
            
            # 分类分布
            if stats['category_distribution']:
                f.write("=== 分类分布 ===\n")
                for category, count in sorted(stats['category_distribution'].items(), key=lambda x: x[1], reverse=True):
                    f.write(f"{category}: {count} 篇\n")
                f.write("\n")
            
            # 详细结果
            f.write("=== 详细处理结果 ===\n")
            for result in self.results:
                f.write(f"文件: {result.filename}\n")
                f.write(f"标题: {result.title or result.original_title}\n")
                f.write(f"分类: {result.category}\n")
                if result.tags:
                    f.write(f"标签: {', '.join(result.tags)}\n")
                f.write(f"状态: {'成功' if result.success else '失败'}\n")
                if result.error_message:
                    f.write(f"错误: {result.error_message}\n")
                f.write(f"处理时间: {result.process_time:.3f} 秒\n")
                f.write("-" * 50 + "\n")
        
        print(f"文本报告已导出到: {report_path}")


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """解析YAML frontmatter，返回元数据字典和正文内容"""
    frontmatter_data = {}
    body_content = content
    
    # 检查是否有frontmatter（以---开始和结束）
    if content.startswith('---\n'):
        try:
            # 查找第二个---的位置
            end_marker = content.find('\n---\n', 4)
            if end_marker != -1:
                # 提取frontmatter部分
                frontmatter_str = content[4:end_marker]
                # 解析YAML
                frontmatter_data = yaml.safe_load(frontmatter_str) or {}
                # 提取正文内容
                body_content = content[end_marker + 5:].strip()
            else:
                # 没有找到结束标记，查找单独的---行
                end_marker = content.find('\n---', 4)
                if end_marker != -1:
                    frontmatter_str = content[4:end_marker]
                    frontmatter_data = yaml.safe_load(frontmatter_str) or {}
                    body_content = content[end_marker + 4:].strip()
        except yaml.YAMLError as e:
            print(f"YAML解析错误: {e}")
            # 如果解析失败，返回空字典和原始内容
            frontmatter_data = {}
            body_content = content
    
    return frontmatter_data, body_content


def normalize_tags(tags: List[str], category: str) -> List[str]:
    """标签规范化：将AI生成的标签转换为预定义标签"""
    if not tags:
        return []
    
    normalized_tags = []
    available_tags = PREDEFINED_TAGS.get(category, [])
    
    for tag in tags:
        tag = tag.strip()
        if not tag:
            continue
            
        # 1. 首先检查是否直接匹配预定义标签
        if tag in available_tags:
            normalized_tags.append(tag)
            continue
            
        # 2. 检查标签规范化映射
        if tag in TAG_NORMALIZATION:
            normalized_tag = TAG_NORMALIZATION[tag]
            if normalized_tag in available_tags:
                normalized_tags.append(normalized_tag)
                continue
        
        # 3. 模糊匹配：检查是否包含预定义标签的关键词
        matched = False
        for predefined_tag in available_tags:
            if (tag in predefined_tag or predefined_tag in tag or
                any(keyword in tag for keyword in predefined_tag.split()) or
                any(keyword in predefined_tag for keyword in tag.split())):
                normalized_tags.append(predefined_tag)
                matched = True
                break
        
        # 4. 如果没有匹配到，检查其他分类的标签（可能分类不准确）
        if not matched:
            for cat, cat_tags in PREDEFINED_TAGS.items():
                for predefined_tag in cat_tags:
                    if (tag in predefined_tag or predefined_tag in tag or
                        any(keyword in tag for keyword in predefined_tag.split()) or
                        any(keyword in predefined_tag for keyword in tag.split())):
                        normalized_tags.append(predefined_tag)
                        matched = True
                        break
                if matched:
                    break
    
    # 去重并限制数量
    normalized_tags = list(dict.fromkeys(normalized_tags))  # 保持顺序去重
    return normalized_tags[:5]  # 最多5个标签


def clean_content(content: str) -> str:
    """清理和规范化内容"""
    if not content:
        return ""
    
    # 基本内容清理，保留有意义的行
    lines = content.split('\n')
    clean_lines = []
    
    for line in lines:
        # 保留包含中文或英文字符的有意义行
        if re.search(r'[\u4e00-\u9fff]|[a-zA-Z]{3,}', line):  # 包含中文或3个以上英文字符
            clean_lines.append(line)
    
    return '\n'.join(clean_lines)


def read_markdown_with_frontmatter(file_path: str) -> Tuple[str, Dict[str, Any]]:
    """读取Markdown文件内容并解析frontmatter"""
    try:
        # 尝试不同的编码方式
        encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin1']
        raw_content = ""
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    raw_content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if not raw_content:
            print(f"警告: 无法读取文件 {file_path}，尝试的所有编码都失败")
            return "", {}
        
        # 解析frontmatter
        frontmatter_data, body_content = parse_frontmatter(raw_content)
        
        # 清理内容
        body_content = clean_content(body_content)
        
        # 移除markdown格式标记，只保留文本内容
        content = re.sub(r'#+\s*', '', body_content)  # 标题
        content = re.sub(r'\*\*(.*?)\*\*', r'\1', content)  # 粗体
        content = re.sub(r'\*(.*?)\*', r'\1', content)  # 斜体
        content = re.sub(r'`(.*?)`', r'\1', content)  # 代码
        content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)  # 链接
        content = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', content)  # 图片
        content = re.sub(r'\n+', '\n', content)  # 多个换行合并
        
        # 最终清理
        content = content.strip()
        
        # 限制内容长度
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "..."
        
        if ENABLE_DEBUG_OUTPUT and content:
            tqdm.write(f"DEBUG - 清理后内容长度: {len(content)}")
            tqdm.write(f"DEBUG - 清理后内容预览: {content[:100]}...")
        
        return content, frontmatter_data
    except Exception as e:
        print(f"读取文件内容失败: {file_path} - {str(e)}")
        return "", {}


def read_markdown_content(file_path: str) -> str:
    """读取Markdown文件内容（向后兼容）"""
    content, _ = read_markdown_with_frontmatter(file_path)
    return content


@retry(
    stop=stop_after_attempt(3),  # 减少重试次数到3次，避免过度重试
    wait=wait_exponential(multiplier=2, min=3, max=15),  # 更长的等待时间：3s, 6s, 12s
    retry=retry_if_exception_type((
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.HTTPError,
        requests.exceptions.ProxyError,
        requests.exceptions.ChunkedEncodingError,
        requests.exceptions.RequestException
    ))  # 扩展重试的异常类型
)
def classify_with_content_and_tags(title: str, content: str = "") -> Tuple[str, List[str]]:
    """使用AI API进行分类和标签提取（带重试）"""
    
    # 获取当前使用的AI服务信息
    current_provider, current_model = ai_service_manager.get_current_provider_info()
    
    # 构建系统提示
    analysis_text = f"标题: {title}"
    if ENABLE_CONTENT_ANALYSIS and content:
        analysis_text += f"\n\n内容: {content}"
    
    if ENABLE_TAG_EXTRACTION:
        SYSTEM_PROMPT = f"""你是一个文章分类器。请将文章分类到以下类别之一：{', '.join(CATEGORIES)}

对于标签提取，请尽量使用准确描述文章内容的关键词，避免过于宽泛或模糊的标签。

严格按照以下JSON格式返回，不要添加任何解释、分析或其他文字：
{{
    "category": "分类名称",
    "tags": ["标签1", "标签2", "标签3"]
}}

要求：
- 只输出上述JSON格式
- 不要任何解释文字
- category必须是提供的类别之一
- tags提取3-5个具体、准确的关键词
- 标签应该具体描述文章主题，避免太宽泛的词汇"""
    else:
        SYSTEM_PROMPT = f"""你是一个文章分类器。将文章分类到以下类别之一：{', '.join(CATEGORIES)}

只返回分类名称，不要任何其他内容。"""

    payload = {
        "model": current_model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": analysis_text}],
        "temperature": 0.1,
        "max_tokens": 150  # 减少max_tokens，强制AI简洁回应
    }

    try:
        # 调试输出：显示发送给AI的内容
        if ENABLE_DEBUG_OUTPUT:
            tqdm.write(f"[AI请求] 使用 {current_provider.upper()} - {current_model}")
            tqdm.write(f"DEBUG - 发送给AI的内容长度: {len(analysis_text)}")
            tqdm.write(f"DEBUG - 内容预览: {analysis_text[:200]}...")
        
        response = ai_service_manager.session.post(API_URL, json=payload, timeout=API_TIMEOUT)
        response.encoding = 'utf-8'
        
        # 详细的响应状态检查
        tqdm.write(f"[检查] API响应状态: {response.status_code}")
        if response.status_code != 200:
            tqdm.write(f"[错误] 非200响应: {response.text[:500]}")
            response.raise_for_status()

        # 尝试解析JSON响应
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            tqdm.write(f"[错误] 响应JSON解析失败: {e}")
            tqdm.write(f"[内容] 原始响应内容: {response.text[:500]}")
            raise
        
        # 检查响应结构
        if not data:
            tqdm.write(f"[错误] 空的响应数据")
            return "其他", []
            
        if 'choices' not in data:
            tqdm.write(f"[错误] 响应中没有'choices'字段: {data}")
            return "其他", []
            
        if not data['choices']:
            tqdm.write(f"[错误] choices数组为空: {data}")
            return "其他", []
            
        if 'message' not in data['choices'][0]:
            tqdm.write(f"[错误] 第一个choice中没有'message'字段: {data['choices'][0]}")
            return "其他", []
            
        if 'content' not in data['choices'][0]['message']:
            tqdm.write(f"[错误] message中没有'content'字段: {data['choices'][0]['message']}")
            return "其他", []

        result_text = data['choices'][0]['message']['content'].strip()
        
        # 总是输出AI的原始回复
        tqdm.write(f"[AI] AI原始回复: {result_text}")
        
        if ENABLE_TAG_EXTRACTION:
            try:
                # 首先尝试直接解析整个文本
                result_json = json.loads(result_text)
                category = result_json.get("category", "其他")
                tags = result_json.get("tags", [])
                
                tqdm.write(f"[成功] JSON解析成功: category={category}, tags={tags}")
                
                # 验证分类是否有效
                if category not in CATEGORIES:
                    tqdm.write(f"[警告] 无效分类 '{category}'，使用'其他'代替")
                    category = "其他"
                
                return category, tags
                
            except json.JSONDecodeError as e:
                tqdm.write(f"[警告] 直接JSON解析失败: {e}，尝试提取JSON片段")
                
                # 如果直接解析失败，尝试提取JSON部分
                try:
                    # 尝试提取```json```代码块中的内容
                    json_match = re.search(r'```json\s*\n(.*?)\n```', result_text, re.DOTALL)
                    if json_match:
                        json_text = json_match.group(1).strip()
                        tqdm.write(f"[提取] 提取到json代码块: {json_text}")
                        result_json = json.loads(json_text)
                        category = result_json.get("category", "其他")
                        tags = result_json.get("tags", [])
                        if category not in CATEGORIES:
                            category = "其他"
                        tqdm.write(f"[成功] 代码块解析成功: category={category}, tags={tags}")
                        return category, tags
                    
                    # 尝试提取花括号内的JSON内容
                    json_match = re.search(r'\{[^{}]*"category"[^{}]*\}', result_text)
                    if json_match:
                        json_text = json_match.group(0)
                        tqdm.write(f"[提取] 提取到JSON片段: {json_text}")
                        result_json = json.loads(json_text)
                        category = result_json.get("category", "其他")
                        tags = result_json.get("tags", [])
                        if category not in CATEGORIES:
                            category = "其他"
                        tqdm.write(f"[成功] 片段解析成功: category={category}, tags={tags}")
                        return category, tags
                    
                    # 尝试使用正则表达式提取分类和标签
                    category_match = re.search(r'"category":\s*"([^"]+)"', result_text)
                    tags_match = re.search(r'"tags":\s*\[(.*?)\]', result_text)
                    
                    if category_match:
                        category = category_match.group(1)
                        if category not in CATEGORIES:
                            category = "其他"
                        
                        tags = []
                        if tags_match:
                            tags_str = tags_match.group(1)
                            # 提取标签
                            tag_matches = re.findall(r'"([^"]+)"', tags_str)
                            tags = tag_matches[:5]  # 最多5个标签
                        
                        tqdm.write(f"[成功] 正则提取成功: category={category}, tags={tags}")
                        return category, tags
                    
                    # 如果所有JSON提取都失败，检查是否直接返回了分类名称
                    for cat in CATEGORIES:
                        if cat in result_text:
                            tqdm.write(f"[成功] 找到分类名称: {cat}")
                            return cat, []
                    
                    tqdm.write(f"[错误] 所有解析方法都失败，返回'其他'")
                    return "其他", []
                    
                except Exception as e:
                    tqdm.write(f"[错误] JSON提取过程出错: {type(e).__name__}: {str(e)}")
                    return "其他", []
        else:
            # 只进行分类
            category = result_text if result_text in CATEGORIES else "其他"
            tqdm.write(f"[成功] 仅分类模式: {category}")
            return category, []
            
    except Exception as e:
        tqdm.write(f"[错误] classify_with_content_and_tags 发生异常: {type(e).__name__}: {str(e)}")
        # 重新抛出异常，让重试机制处理
        raise


def classify_title_with_content(title: str, content: str = "") -> Tuple[str, List[str]]:
    """封装带重试的分类函数，处理最终的异常"""
    tqdm.write(f"[分类] 开始分类: {title[:50]}...")
    
    try:
        result = classify_with_content_and_tags(title, content)
        tqdm.write(f"[成功] 分类成功: {title[:50]} -> {result[0]} (标签: {result[1]})")
        return result
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        
        # 详细的错误分析
        if "RetryError" in error_type:
            tqdm.write(f"[错误] 重试失败 (RetryError): {title[:50]}")
            tqdm.write(f"   原始错误: {error_msg}")
            # 尝试从RetryError中提取原始异常
            if hasattr(e, 'last_attempt') and hasattr(e.last_attempt, 'exception'):
                original_error = e.last_attempt.exception()
                tqdm.write(f"   根本原因: {type(original_error).__name__}: {str(original_error)}")
        elif isinstance(e, requests.exceptions.ProxyError):
            tqdm.write(f"[错误] 代理连接错误: {title[:50]} - {error_msg}")
            tqdm.write("  [建议] 检查代理设置或禁用代理")
        elif isinstance(e, requests.exceptions.Timeout):
            tqdm.write(f"[错误] 请求超时: {title[:50]} - {error_msg}")
            tqdm.write(f"  [建议] 当前超时设置为{API_TIMEOUT}秒，可考虑增加超时时间")
        elif isinstance(e, requests.exceptions.ConnectionError):
            tqdm.write(f"[错误] 连接错误: {title[:50]} - {error_msg}")
            tqdm.write("  [建议] 检查网络连接或API端点")
        elif isinstance(e, requests.exceptions.HTTPError):
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
                if status_code == 400:
                    tqdm.write(f"[错误] 400 Bad Request (不重试): {title[:50]} - {error_msg}")
                elif status_code == 401:
                    tqdm.write(f"[错误] 401 Unauthorized: {title[:50]} - API密钥可能无效")
                    tqdm.write("  [建议] 检查OPENAI_API_KEY配置")
                elif status_code == 429:
                    tqdm.write(f"[错误] 429 Rate Limit: {title[:50]} - API调用频率过高")
                    tqdm.write("  [建议] 降低并发数或增加重试间隔")
                else:
                    tqdm.write(f"[错误] HTTP {status_code}: {title[:50]} - {error_msg}")
            else:
                tqdm.write(f"[错误] HTTPError (无响应对象): {title[:50]} - {error_msg}")
        else:
            tqdm.write(f"[错误] 未知错误 ({error_type}): {title[:50]} - {error_msg}")
            # 打印异常的详细信息
            import traceback
            tqdm.write(f"   异常跟踪: {traceback.format_exc()}")
        
        return "其他", []


def process_file(filename: str, result_manager: ResultManager) -> Tuple[str, bool]:
    """处理单个文件，返回处理结果字符串和是否应该停止的标志"""
    start_time = time.time()
    src_path = os.path.join(SOURCE_DIR, filename)
    
    # 添加文件处理开始分隔线
    tqdm.write("\n" + "="*80)
    tqdm.write(f"[文件] 开始处理文件: {filename}")
    tqdm.write("="*80)
    
    # 检查停止信号
    if stop_processing.is_set():
        tqdm.write("[停止] 收到停止信号，跳过此文件")
        tqdm.write("="*80 + "\n")
        return f"停止: {filename} - 用户请求停止", True
    
    # 检查暂停信号
    while pause_processing.is_set() and not stop_processing.is_set():
        time.sleep(0.5)  # 等待恢复
    
    # 再次检查停止信号（可能在暂停期间设置了停止）
    if stop_processing.is_set():
        tqdm.write("[停止] 暂停期间收到停止信号，跳过此文件")
        tqdm.write("="*80 + "\n")
        return f"停止: {filename} - 用户请求停止", True
    
    if not filename.endswith(".md"):
        result = ProcessResult(
            filename=filename,
            original_title=filename,
            category="跳过",
            tags=[],
            process_time=time.time() - start_time,
            success=False,
            error_message="非Markdown文件",
            processing_status="跳过"
        )
        result_manager.add_result(result)
        tqdm.write("[跳过] 跳过非Markdown文件")
        tqdm.write("="*80 + "\n")
        return f"跳过非Markdown文件: {filename}", False

    title = os.path.splitext(filename)[0]
    category = "其他"
    tags = []
    content = ""
    frontmatter_data = {}
    
    # 初始化所有字段
    fm_title = None
    fm_url = None
    fm_author = None
    fm_author_badge = None
    fm_created = None
    fm_modified = None
    fm_upvote_num = None
    fm_comment_num = None
    word_count = None
    content_summary = ""

    try:
        # 在关键步骤前检查停止信号
        if stop_processing.is_set():
            return f"停止: {filename} - 用户请求停止", True
        # 读取文件内容和frontmatter
        if ENABLE_CONTENT_ANALYSIS:
            content, frontmatter_data = read_markdown_with_frontmatter(src_path)
        else:
            # 即使不启用内容分析，也解析frontmatter获取元数据
            _, frontmatter_data = read_markdown_with_frontmatter(src_path)
        
        # 提取frontmatter字段
        if frontmatter_data:
            fm_title = frontmatter_data.get('title', '')
            fm_url = frontmatter_data.get('url', '')
            fm_author = frontmatter_data.get('author', '')
            fm_author_badge = frontmatter_data.get('author_badge', '')
            fm_created = frontmatter_data.get('created', '')
            fm_modified = frontmatter_data.get('modified', '')
            
            # 处理数字字段，确保安全转换
            try:
                upvote_raw = frontmatter_data.get('upvote_num')
                fm_upvote_num = int(upvote_raw) if upvote_raw is not None else None
            except (ValueError, TypeError):
                fm_upvote_num = None
                
            try:
                comment_raw = frontmatter_data.get('comment_num')
                fm_comment_num = int(comment_raw) if comment_raw is not None else None
            except (ValueError, TypeError):
                fm_comment_num = None
        
        # 计算字数统计和内容摘要
        if content:
            word_count = len(content.replace(' ', '').replace('\n', ''))
            content_summary = content[:200] + "..." if len(content) > 200 else content
        
        # 使用frontmatter中的title（如果存在）或者文件名作为分类依据
        classification_title = fm_title if fm_title else title
        
        # 在分类前检查停止信号
        if stop_processing.is_set():
            return f"停止: {filename} - 用户请求停止", True
        
        tqdm.write(f"[标题] 分类标题: {classification_title}")
        if content:
            tqdm.write(f"[内容] 内容长度: {len(content)} 字符")
        else:
            tqdm.write("[内容] 无内容分析")
        
        # 进行分类和标签提取
        try:
            category, raw_tags = classify_title_with_content(classification_title, content)
            tqdm.write(f"[结果] AI分类结果: category='{category}', raw_tags={raw_tags}")
        except Exception as e:
            tqdm.write(f"[错误] 分类过程异常: {type(e).__name__}: {str(e)}")
            # 重新抛出异常让外层处理
            raise
        
        # 验证分类结果
        if not category:
            tqdm.write(f"[警告] 空分类结果，使用'其他'")
            category = "其他"
        elif category not in CATEGORIES + ["其他"]:
            tqdm.write(f"[警告] 无效分类 '{category}'，使用'其他'")
            category = "其他"
        
        # 在移动文件前检查停止信号
        if stop_processing.is_set():
            return f"停止: {filename} - 用户请求停止", True
        
        # 标签规范化
        if ENABLE_TAG_EXTRACTION and raw_tags:
            tags = normalize_tags(raw_tags, category)
            tqdm.write(f"[标签] 标签规范化: {raw_tags} -> {tags}")
        else:
            tags = []

        tqdm.write(f"[移动] 准备移动文件到分类: {category}")
        
        # 移动文件
        try:
            dest_dir = os.path.join(BASE_DIR, category)
            os.makedirs(dest_dir, exist_ok=True)
            dest_file_path = os.path.join(dest_dir, filename)
            
            tqdm.write(f"[路径] 目标路径: {dest_file_path}")
            shutil.move(src_path, dest_file_path)
            tqdm.write(f"[成功] 文件移动成功: {filename} -> {category}")
            
        except Exception as e:
            tqdm.write(f"[错误] 文件移动失败: {type(e).__name__}: {str(e)}")
            raise
        
        # 记录成功结果
        result = ProcessResult(
            filename=filename,
            original_title=title,
            category=category,
            tags=tags,
            process_time=time.time() - start_time,
            success=True,
            content_preview=content_summary,
            # Frontmatter字段
            title=fm_title,
            url=fm_url,
            author=fm_author,
            author_badge=fm_author_badge,
            created=fm_created,
            modified=fm_modified,
            upvote_num=fm_upvote_num,
            comment_num=fm_comment_num,
            # 统计字段
            word_count=word_count,
            content_summary=content_summary,
            processing_status="成功"
        )
        result_manager.add_result(result)
        
        display_title = fm_title if fm_title else title
        tqdm.write(f"[成功] 处理成功: {display_title} -> {category}")
        if tags:
            tqdm.write(f"[标签] 标签: {', '.join(tags)}")
        tqdm.write(f"[时间] 处理时间: {time.time() - start_time:.3f} 秒")
        tqdm.write("="*80 + "\n")
        return f"成功: {display_title} -> {category} (标签: {', '.join(tags) if tags else '无'})", False
        
    except Exception as e:
        # 记录失败结果
        result = ProcessResult(
            filename=filename,
            original_title=title,
            category=category,
            tags=tags,
            process_time=time.time() - start_time,
            success=False,
            error_message=str(e),
            content_preview=content_summary,
            # Frontmatter字段（即使失败也尝试保存已解析的数据）
            title=fm_title,
            url=fm_url,
            author=fm_author,
            author_badge=fm_author_badge,
            created=fm_created,
            modified=fm_modified,
            upvote_num=fm_upvote_num,
            comment_num=fm_comment_num,
            # 统计字段
            word_count=word_count,
            content_summary=content_summary,
            processing_status="失败"
        )
        result_manager.add_result(result)
        
        tqdm.write(f"[错误] 文件处理失败: {filename}")
        tqdm.write(f"[分类] 目标分类: {category}")
        tqdm.write(f"[警告] 错误信息: {str(e)}")
        tqdm.write(f"[时间] 处理时间: {time.time() - start_time:.3f} 秒")
        tqdm.write("="*80 + "\n")
        return f"失败: {filename} - {str(e)} (分类尝试: {category})", False


def main():
    print("=== 知乎文章智能分类器 增强版 ===")
    print(f"运行模式: {'高级功能模式' if ENABLE_ADVANCED_FEATURES else '轻量级模式'}")
    print(f"Pandas支持: {'可用' if PANDAS_AVAILABLE else '不可用'}")
    print(f"内容分析: {'启用' if ENABLE_CONTENT_ANALYSIS else '禁用'}")
    print(f"标签提取: {'启用' if ENABLE_TAG_EXTRACTION else '禁用'}")
    print(f"结果导出: {'启用' if ENABLE_RESULT_EXPORT else '禁用'}")
    print(f"优雅停止: {'启用' if ENABLE_GRACEFUL_STOP else '禁用'}")
    print(f"暂停/继续: {'启用' if ENABLE_PAUSE_RESUME else '禁用'}")
    if ENABLE_RESULT_EXPORT:
        export_modes = []
        if PANDAS_AVAILABLE and "csv" in EXPORT_FORMAT:
            export_modes.append("CSV")
        if PANDAS_AVAILABLE and "excel" in EXPORT_FORMAT:
            export_modes.append("Excel")
        if not PANDAS_AVAILABLE:
            export_modes.append("文本报告")
        print(f"导出格式: {', '.join(export_modes) if export_modes else '无'}")
    print(f"内容长度限制: {MAX_CONTENT_LENGTH} 字符")
    print(f"Frontmatter解析: 启用")
    print()
    
    if not PANDAS_AVAILABLE and ENABLE_ADVANCED_FEATURES:
        print("[警告] 注意: 因为pandas导入失败，已自动切换到轻量级模式")
        print("   - 将不提供CSV/Excel导出功能")
        print("   - 使用文本报告代替详细统计")
        print("   - 建议检查并重新安装依赖: pip install -r requirements.txt")
        print()
    
    # 设置信号处理器
    stop_handler.setup_signal_handlers()
    
    # 初始化进度管理器
    progress_manager = ProgressManager(BASE_DIR)
    
    # 初始化用户输入处理器
    input_handler = UserInputHandler()
    
    # 初始化结果管理器
    result_manager = ResultManager()
    
    # 初始化目录
    os.makedirs(BASE_DIR, exist_ok=True)
    all_target_categories = CATEGORIES + ["其他"]
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

    # 检查是否有之前的进度
    processed_files, failed_files = progress_manager.load_progress()
    
    # 过滤掉已处理的文件
    remaining_files = [f for f in files if f not in processed_files and f not in failed_files]
    
    if len(remaining_files) < len(files):
        print(f"[进度] 进度恢复: 总共 {len(files)} 个文件，已处理 {len(processed_files)} 个，失败 {len(failed_files)} 个")
        print(f"还需处理 {len(remaining_files)} 个文件")
        
        if remaining_files:
            choice = input("是否继续处理剩余文件？(Y/n): ").strip().lower()
            if choice in ['n', 'no', '否']:
                print("取消处理")
                return
        else:
            print("[完成] 所有文件都已处理完成！")
            # 显示统计信息
            if result_manager.results:
                stats = result_manager.get_statistics()
                print(f"成功: {stats['success_count']}, 失败: {stats['failure_count']}")
            input("按任意键退出...")
            return
    
    print(f"发现 {len(remaining_files)} 个 .md 待处理文件，将从 {SOURCE_DIR} 移动到 {BASE_DIR} 下的分类目录。")

    if not remaining_files:
        print("没有需要处理的文件")
        input("按任意键退出...")
        return

    # 启动用户输入监听
    input_handler.start_input_monitoring()
    
    # 使用单线程处理以支持更好的停止控制
    print("开始处理文件...")
    
    try:
        processed_count = 0
        current_processed = set(processed_files)
        current_failed = set(failed_files)
        
        with tqdm(total=len(remaining_files), desc="文件分类中") as pbar:
            for filename in remaining_files:
                # 检查停止信号
                if stop_processing.is_set():
                    print(f"\n[警告] 收到停止信号，已处理 {processed_count} 个文件")
                    break
                
                # 处理文件
                result_msg, should_stop = process_file(filename, result_manager)
                processed_count += 1
                
                # 更新进度显示
                pbar.set_postfix_str(f"当前: {filename[:30]}...")
                pbar.update(1)
                
                # 根据结果更新集合
                if "成功:" in result_msg:
                    current_processed.add(filename)
                elif "失败:" in result_msg:
                    current_failed.add(filename)
                
                # 定期保存进度
                if processed_count % SAVE_PROGRESS_INTERVAL == 0:
                    progress_manager.save_progress(current_processed, current_failed)
                    tqdm.write(f"[保存] 进度已保存 ({processed_count}/{len(remaining_files)})")
                
                # 如果收到停止信号就退出
                if should_stop:
                    print(f"\n[警告] 处理中断，已处理 {processed_count} 个文件")
                    break
                
                # 短暂休息，允许响应停止信号
                time.sleep(0.01)
        
        # 最终保存进度
        progress_manager.save_progress(current_processed, current_failed)
        
    except KeyboardInterrupt:
        print(f"\n[警告] 用户中断，已处理 {processed_count} 个文件")
    except Exception as e:
        print(f"\n[错误] 处理过程中发生错误: {e}")
    finally:
        # 停止用户输入监听
        input_handler.stop_input_monitoring()
        
        # 保存最终进度
        if 'current_processed' in locals() and 'current_failed' in locals():
            progress_manager.save_progress(current_processed, current_failed)

    # 获取统计信息
    stats = result_manager.get_statistics()
    
    # 打印总结信息
    print("\n" + "="*50)
    print("处理结果总结")
    print("="*50)
    print(f"总文件数: {stats['total_files']}")
    print(f"成功处理: {stats['success_count']}")
    print(f"失败处理: {stats['failure_count']}")
    print(f"成功率: {stats['success_rate']:.2%}")
    print(f"总处理时间: {stats['processing_time']['total_time']:.2f} 秒")
    print(f"平均处理时间: {stats['processing_time']['average_per_file']:.3f} 秒/文件")
    
    # 分类分布
    if stats['category_distribution']:
        print("\n分类分布:")
        for category, count in sorted(stats['category_distribution'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {category}: {count} 篇")
    
    # 导出结果
    if ENABLE_RESULT_EXPORT:
        print(f"\n正在导出结果...")
        result_manager.export_results(BASE_DIR)
    
    # 处理完成或中断后的清理
    if stop_processing.is_set():
        print(f"\n[停止] 处理已停止")
        print("进度已保存，下次运行时可以从中断处继续")
    else:
        print(f"\n[完成] 分类完成！")
        # 完成后清除进度文件
        try:
            choice = input("是否清除进度文件？(Y/n): ").strip().lower()
            if choice not in ['n', 'no', '否']:
                progress_manager.clear_progress()
        except:
            pass
    
    if stats['failure_count'] > 0:
        print("请检查上面由 tqdm.write 输出的失败详情。")
    
    input("按任意键退出...")


if __name__ == "__main__":
    main()
