# zhihu-article-classifier
借助DeepSeek的API对文章进行分类

## 1.下载需要的知乎文章到本地markdown文件

如下载收藏夹，推荐使用
[zanghuaren/ZhiHu-Collection-To-Markdown](https://github.com/zanghuaren/ZhiHu-Collection-To-Markdown)

## 2.获取DeepSeek的API

**打开[deepseek官网](https://www.deepseek.com/),从页面右上角进入“API开放平台”,注册并登录,创建一个API key**

## 3.配置程序参数

**将API key填入“DEEPSEEK_API_KEY“（必需项）**

**将下载好的markdown文件放入SOURCE_DIR路径**

**根据需求设置分类收藏夹列表CATEGORIES**

DeepSeek-v3会根据每个文件的标题,从分类收藏夹中智能匹配最相关分类,**因此分类效果很大程度上受收藏夹名称影响**

**其余参数可根据需求自行调整**

## 4.等待程序运行完成
速度视API运行速度而定,高峰期可能会慢点.笔者在00：00(UTC+8)实测约8min/100个问题.

亲测效果还行,分类结果基本正确,约95%的文章被正确分类,剩余部分可通过手动快速完成调整.

开销方面,对一千篇文章分类花费不到0.2元

***项目仅限个人学习研究使用,请遵守有关法规及《知乎协议》,禁止用于未经授权的商业用途***
