# zhihu-article-classifier

基于DeepSeek API的自动化Markdown文件分类工具，主要用于知乎文章收藏，可将指定目录中的文件按标题智能分类到预定义类别，并自动移动到对应子目录。

## 快速开始🚀

### 1.安装步骤⚙️

1. **克隆仓库**

    ```bash
    git clone https://github.com/He40026/zhihu-article-classifier.git
    cd zhihu-article-classifier
    ```

2. **安装依赖**

    ```bash
    pip install -r requirements.txt
    ```

### 2.下载需要的知乎文章到本地markdown文件📂

如下载收藏夹，推荐使用

[zanghuaren/ZhiHu-Collection-To-Markdown](https://github.com/zanghuaren/ZhiHu-Collection-To-Markdown)

[He40026/Zhihu-Collection-Downloader](https://github.com/He40026/Zhihu-Collection-Downloader)

### 3.获取DeepSeek的API🔍

打开[deepseek官网](https://www.deepseek.com/),从页面右上角进入`API开放平台`,注册并登录,创建一个API key

### 4.配置程序参数🔧

根据需要填写`main.py`配置参数.

```python
# 配置参数
DEEPSEEK_API_KEY = "这里填你的API密钥"  # API密钥（必需项）
SOURCE_DIR = "./"  # Markdown文件存放路径，默认为根目录
BASE_DIR = "./"  # 分类存储路径，默认为根目录
CATEGORIES = ["自然科学", "人文社科", "学习成长", "哲学思辨", "工程技术", "财经投资", "时事时政", "情感生活", "体育健康", "文娱艺术", "搞笑趣闻", "外貌穿搭"]  # 分类收藏夹名称（根据需求设置）
```

- **将API key填入`DEEPSEEK_API_KEY`（必需项）。**
- 将刚刚下好的Markdown文件存放路径填入`SOURCE_DIR`。
- 将分类存放路径填入`BASE_DIR`。**注意，第一步里存放图片的文件夹必须在也必须在`BASE_DIR`里，如果不在可以手动复制过来，否则图片会无法加载**。
- 根据需求设置分类收藏夹`CATEGORIES`。DeepSeek-v3会根据每个文件的标题，从分类收藏夹中智能匹配最相关分类，**因此分类效果很大程度上受收藏夹名称影响**。

### 5.运行程序

```bash
python main.py
```

速度视API运行速度而定

亲测效果还行，分类结果基本正确，约95%的文章被正确分类，剩余部分可通过手动快速完成调整

费用方面，对一千篇文章分类花费不到0.2元

***项目仅限个人学习研究使用,请遵守有关法规及协议***
