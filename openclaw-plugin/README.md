# ATLAS Memory v9.4.0

商业级 OpenClaw 语义记忆插件。

**架构（四层）：**
- **INJECT** — 每次提问前从 Qdrant 检索相关记忆注入上下文（LRU 缓存 + 时间衰减 + 2.5s 超时）
- **CAPTURE** — 对话结束时提取事实存入 Qdrant（Qwen3.5 质量过滤≥7 + 冲突检测）
- **LEARN** — 拦截搜索工具调用，自动学习网页内容
- **EVOLVE** — 定期去重、清理过期记忆、Obsidian Bridge 导出

**依赖服务：**
- Qdrant `http://127.0.0.1:6333` — 向量存储（768-dim Cosine）
- Ollama `nomic-embed-text:latest` — 文本嵌入
- omlx `Qwen3.5-9B-OptiQ-4bit` — 提取 / 冲突检测

**安装文档：** [setup/SETUP.md](../setup/SETUP.md)
