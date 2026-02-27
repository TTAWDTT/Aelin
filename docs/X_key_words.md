# X (Twitter) 关键词搜索实现方案

**文档版本**: v1.0  
**创建日期**: 2026-02-27  
**适用范围**: Aelin Agent Loop 工具扩展  
**关联模块**: `backend/app/connectors/x.py`, `backend/app/services/aelin_tools.py`

---

## 1. 现状能力边界

### 1.1 当前已实现功能

| 功能 | 实现状态 | 技术方式 | 限制 |
|------|---------|---------|------|
| ✅ **用户时间线跟踪** | 已实现 | 模拟浏览器抓取用户推文 | 需登录态，限流严格 |
| ✅ **特定用户监控** | 已实现 | `@username` 方式跟踪 | 只能监控已知用户 |
| ✅ **网页通用搜索** | 已实现 | Bing/DuckDuckGo 搜索 | 非实时，延迟高 |
| ❌ **X平台内关键词搜索** | **未实现** | 无 X API 搜索接入 | 无法搜索全平台推文 |

### 1.2 明确的能力边界

**Aelin 当前无法做到**:

1. **实时搜索 X 全平台** - 无法搜索 "最近提到 'DeepSeek' 的所有推文"
2. **话题趋势发现** - 无法发现 "正在热议的话题"
3. **地理位置搜索** - 无法搜索 "来自北京的用户发的推文"
4. **高级筛选** - 无法 "搜索带图片的、点赞数>100的、最近一周的推文"

**技术限制原因**:

- **无 X API v2 接入**: 当前只有 Basic/Pro 级 API 才能使用 `recent/search` 端点
- **网页抓取限制**: X 的网页版搜索需要完整登录态，且反爬严格
- **Nitter 不稳定**: 公共 Nitter 实例多数已关闭或限流

---

## 2. 实现方案

### 2.1 方案对比

| 方案 | 实现难度 | 成本 | 稳定性 | 实时性 | 推荐度 |
|------|---------|------|--------|--------|--------|
| **A. X API v2 官方接入** | 中 | 中 ($100/月 Basic) | 高 | 高 | ⭐⭐⭐⭐⭐ |
| **B. SerpAPI 代理** | 低 | 中 ($50/月) | 中 | 中 | ⭐⭐⭐⭐ |
| **C. 自建 Nitter 实例** | 高 | 低 (服务器成本) | 低 | 中 | ⭐⭐ |
| **D. 网页抓取增强** | 高 | 低 | 极低 | 低 | ⭐ |

### 2.2 推荐方案：A + B 混合

**主方案: X API v2 官方接入**
- 使用 Basic 级别 ($100/月，500k read limit)
- 实时搜索，官方 SLA 保障
- 支持 `recent/search` 和 `counts` 端点

**备用方案: SerpAPI**
- 当 X API 限流或不可用时降级
- 支持 `engine=google` + `tbm=nws` 搜索新闻
- 支持 `engine=bing` + `news` 垂直搜索

---

## 3. 详细实现

### 3.1 新增工具定义

```yaml
# 在 aelin_tools.py 中新增
tool_name: x_search

description: |
  在 X (Twitter) 平台搜索公开推文。
  支持关键词搜索、时间范围、结果筛选。
  当需要了解 X 上关于某话题的讨论时使用此工具。

parameters:
  query:
    type: string
    required: true
    description: 搜索关键词，支持 AND/OR 逻辑，如 "DeepSeek AND release"
    maxLength: 500
  
  start_time:
    type: string
    format: date-time
    required: false
    description: 开始时间，ISO 8601 格式，如 "2026-02-01T00:00:00Z"
  
  end_time:
    type: string
    format: date-time
    required: false
    description: 结束时间，不填则到当前
  
  max_results:
    type: integer
    default: 20
    minimum: 5
    maximum: 100
    description: 返回结果数量
  
  sort_order:
    type: string
    enum: [recency, relevance]
    default: recency
    description: 排序方式，recency 最新优先，relevance 相关度优先

returns:
  - tweets: 推文列表
    - id: 推文ID
    - text: 文本内容
    - author: 作者信息
    - created_at: 发布时间
    - public_metrics: 公开指标（点赞、转发等）
  - meta: 元数据
    - oldest_id: 最旧推文ID
    - newest_id: 最新推文ID
    - result_count: 结果数量
```

### 3.2 后端实现结构

```
backend/app/
├── connectors/
│   ├── x.py                      # 现有：用户时间线抓取
│   └── x_search.py               # 新增：关键词搜索
├── services/
│   ├── x_search_service.py       # 新增：搜索业务逻辑
│   └── aelin_tools.py            # 修改：添加 x_search 工具
└── models/
    └── x_search_result.py        # 新增：搜索结果模型
```

### 3.3 核心实现代码（关键函数）

```python
# backend/app/connectors/x_search.py

class XSearchConnector:
    """X (Twitter) 关键词搜索连接器"""
    
    def __init__(self, bearer_token: str):
        self.bearer_token = bearer_token
        self.base_url = "https://api.twitter.com/2"
        
    async def search_recent(
        self,
        query: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_results: int = 20,
        sort_order: str = "recency"
    ) -> XSearchResult:
        """
        搜索最近7天的推文
        
        Basic 级别限制：
        - 500K reads / month
        - 1 request / second (App)
        - 450 requests / 15 min (User)
        """
        
        params = {
            "query": query,
            "max_results": min(max_results, 100),
            "tweet.fields": "created_at,author_id,public_metrics,text",
            "expansions": "author_id",
            "user.fields": "username,name,profile_image_url"
        }
        
        if start_time:
            params["start_time"] = start_time.isoformat()
        if end_time:
            params["end_time"] = end_time.isoformat()
        if sort_order == "relevance":
            params["sort_order"] = "relevancy"
            
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/tweets/search/recent",
                params=params,
                headers={"Authorization": f"Bearer {self.bearer_token}"}
            )
            
            # 限流处理
            if response.status_code == 429:
                reset_time = response.headers.get("x-rate-limit-reset")
                wait_seconds = 60
                if reset_time:
                    wait_seconds = max(0, int(reset_time) - int(time.time()))
                raise RateLimitError(f"X API限流，需等待 {wait_seconds} 秒")
                
            response.raise_for_status()
            data = response.json()
            
            return self._parse_search_result(data)
```

### 3.4 工具注册（aelin_tools.py 修改）

```python
# 在 AelinToolHub 中添加 x_search 工具

def tool_definitions(self) -> list[dict[str, Any]]:
    return [
        # ... 现有工具 ...
        {
            "type": "function",
            "function": {
                "name": "x_search",
                "description": "在 X (Twitter) 平台搜索公开推文。支持关键词搜索、时间范围、结果筛选。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词，支持AND/OR逻辑，如'DeepSeek AND release'",
                            "maxLength": 500
                        },
                        "start_time": {
                            "type": "string",
                            "format": "date-time",
                            "description": "开始时间，ISO 8601格式"
                        },
                        "end_time": {
                            "type": "string",
                            "format": "date-time",
                            "description": "结束时间，不填则到当前"
                        },
                        "max_results": {
                            "type": "integer",
                            "default": 20,
                            "minimum": 5,
                            "maximum": 100,
                            "description": "返回结果数量"
                        },
                        "sort_order": {
                            "type": "string",
                            "enum": ["recency", "relevance"],
                            "default": "recency",
                            "description": "排序方式，recency最新优先，relevance相关度优先"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]
```

### 3.5 配置项（settings.py 添加）

```python
# X 关键词搜索配置
x_search_enabled: bool = True  # 是否启用X搜索
x_search_default_max_results: int = 20  # 默认返回结果数
x_search_rate_limit_per_hour: int = 100  # 每小时请求限制（Basic级别）
x_search_cache_ttl_seconds: int = 300  # 搜索结果缓存时间（5分钟）
```

### 3.6 使用示例

```python
# 用户查询示例：
"最近X上大家对DeepSeek 4.0有什么看法？"

# Aelin 自动调用 x_search 工具：
tool_call = {
    "name": "x_search",
    "arguments": {
        "query": "DeepSeek 4.0 OR DeepSeek-4 OR DeepSeek V4",
        "start_time": "2026-02-20T00:00:00Z",  # 最近7天
        "max_results": 50,
        "sort_order": "recency"
    }
}

# 返回结果示例：
{
    "ok": True,
    "tweets": [
        {
            "id": "1234567890",
            "text": "DeepSeek 4.0 的推理能力真的强...",
            "author": {
                "username": "tech_lead",
                "name": "技术大佬",
                "profile_image_url": "https://..."
            },
            "created_at": "2026-02-25T08:30:00Z",
            "public_metrics": {
                "retweet_count": 234,
                "like_count": 1892,
                "reply_count": 56
            }
        }
    ],
    "meta": {
        "oldest_id": "1234567880",
        "newest_id": "1234567899",
        "result_count": 50
    }
}
```

---

## 4. 技术要点

### 4.1 X API 限制说明

| 限制项 | Basic 级别 | 当前配置 |
|--------|-----------|---------|
| 月读取次数 | 500K | 100K（保守使用） |
| 每秒请求数 (App) | 1 | 0.5（更保守） |
| 每 15 分钟 (User) | 450 | 100 |
| 搜索历史范围 | 最近 7 天 | 最近 7 天 |

### 4.2 错误处理策略

```python
# 限流处理
if response.status_code == 429:
    # 读取 x-rate-limit-reset 头部
    # 计算等待时间
    # 可选择：
    #   A. 立即抛出异常，让上层重试
    #   B. 自动等待后重试（需异步）

# 认证失败
if response.status_code == 401:
    # Bearer Token 无效或过期
    # 记录错误，提示管理员检查配置

# 参数错误
if response.status_code == 400:
    # 查询语法错误（如 AND/OR 使用不当）
    # 返回友好提示给用户
```

### 4.3 缓存策略

```python
# 搜索结果缓存
# - 缓存键：hash(query + start_time + end_time + sort_order)
# - 缓存时间：5 分钟（300秒）
# - 原因：X 内容相对静态，且 API 有限流

# 用户元数据缓存
# - 缓存键：user_id 或 username
# - 缓存时间：1 小时（3600秒）
# - 原因：用户信息变动不频繁
```

---

## 5. 接入步骤

### Step 1: 获取 X API 访问权限

1. 访问 [X Developer Portal](https://developer.twitter.com/)
2. 创建 Project 和 App
3. 申请 **Basic** 级别访问（$100/月）
4. 获取 Bearer Token 和 API Key/Secret

### Step 2: 配置环境变量

```bash
# .env 或环境配置
X_BEARER_TOKEN=your_bearer_token_here
X_API_KEY=your_api_key_here
X_API_SECRET=your_api_secret_here
```

### Step 3: 更新 settings.py

```python
# backend/app/settings.py

# X 搜索配置
x_search_enabled: bool = True
x_bearer_token: str = ""  # 从环境变量读取
x_api_key: str = ""     # 可选
x_api_secret: str = ""  # 可选
x_search_default_max_results: int = 20
x_search_rate_limit_per_hour: int = 100
x_search_cache_ttl_seconds: int = 300
```

### Step 4: 部署并测试

```bash
# 重启服务
systemctl restart aelin-backend

# 测试 API 连通性
curl "https://api.twitter.com/2/tweets/search/recent?query=test" \
  -H "Authorization: Bearer $X_BEARER_TOKEN"
```

---

## 6. 风险与应对

| 风险 | 影响 | 应对策略 |
|------|------|---------|
| X API 涨价或关闭 | 高 | 同时接入 SerpAPI 作为备选 |
| API 限流导致响应慢 | 中 | 实施缓存 + 异步任务 |
| 查询语法错误率高 | 中 | 增加查询预处理 + 用户提示 |
| 成本超预算 | 中 | 设置每小时调用上限 |

---

## 7. 总结

X 关键词搜索是 Aelin 目前 **明确缺失但用户需求强烈** 的能力。

**推荐实施路径**:
1. **短期 (1-2周)**: 接入 X API v2 Basic，实现基础关键词搜索
2. **中期 (1月)**: 接入 SerpAPI 作为备选，实现双源容错
3. **长期 (2月+)**: 增加查询预处理、语义理解、结果排序优化

**预期效果**:
- 用户可直接询问 "X 上大家对 DeepSeek 4.0 怎么看？"
- Aelin 自动调用 `x_search` 获取实时讨论
- 结合现有 `context_get` 整合分析，给出全面回答

---

**下一步行动**: 请确认是否启动 X API 接入，或需要我提供具体的代码实现。