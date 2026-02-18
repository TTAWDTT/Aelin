## Aelin
Aelin是一个chat agent方向的作品，使用适当的网络追踪、本地化存储，取代传统的session级别、短期记忆级别的网络搜索，以此来改善针对特定信息的深度交互窘境。    

Aelin适配了几乎所有LLM提供商的几乎所有LLM（具体条目见[提供商与模型目录](https://models.dev/api.json)），并支持自定义配置，您可以在其中利用LLM api调用Claude、ChatGPT、Gemini、Deepseek、Kimi等任意模型进行交互，LLM将基于我们为Aelin设计的agent架构执行搜索与回答。    

Aelin暂未使用任何agent框架（截至写该文档时还未使用，后续可能改为使用Claude SDK，以简便地适配部分agent skills），具有极高的灵活性。    

Aelin的幕后是一个multi-agent系统，其遵循Anthropic在2026年初提出的多agent系统最佳实践（[https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)），实现了基于上下文边界来扩展的多agent系统（仿照Claude code），并支持基于此系统的并行、分支等操作。    

总之，Aelin虽然并未集成目前业界所有LLM集成系统的广阔能力（如skills，mcps），但她的一切设计几乎遵循了最优实践，并专精于深度的信息讨论。    
![[shy.gif]]
## 开发者们
Aelin由三名开发者共同开发，在开发过程中，我们确有使用codex等vibe coding工具来提高工作效率。但一切设计灵感都来源于真实的开发者的想法。  

我们的开发者如下：
- [TTAWDTT](https://github.com/TTAWDTT): Frontend engineer & agent builder 
- [tjhorrypotter](https://github.com/yixiaogithub66): Backend engineer & web tester
- [Anthology-92304](https://github.com/Anthology-92304): UI&UX designer & web tester

***附：我们正在尝试融合openviking或是rag作为检索手段，同时正在尝试desk界面与chat界面的更好融合~***