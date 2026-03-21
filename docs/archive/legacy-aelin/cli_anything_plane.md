# CLI-Anything 作为「工具工厂 plane」的设计草案

> 目的：先把方案写清楚，后续按本设计逐步实现。本文只讨论架构与交互，不涉及具体代码实现细节。

## 一、定位与分层

在当前 Aelin 能力分层中：

1. **基础能力（LLM）**：对话、思考与规划。
2. **工具（tools）**：一次调用完成一件原子任务（如 gws 某个命令、device 截图）。
3. **plane（外部系统）**：独立的 agent / 系统，具备自己的长链路能力，Aelin 像“用户”一样把活交给它，再监督结果（如 pinchtab）。
4. **Aelin 自身的 plan 能力**：在 1–3 层之上做高层规划与分工。

**CLI-Anything 本体**的定位：

- 对开发者来说：是一个“为某个复杂软件自动设计/生成 CLI 封装”的流水线。
- 对 Aelin 来说：如果只在开发期使用，它只是开发工具；如果希望“终端用户也能一键接入任意软件”，那它就应该被包装成一个 **plane**。

**CLI-Anything 产物（生成的 xxx-cli）**的定位：

- 本质是一组结构化良好的命令行工具（通常带 `--help` / `--json` 等）。
- 在 Aelin 中，这些命令应当被视为 **工具层（level 2）的原子工具**，类似 gws 的子命令。

结论：

- CLI-Anything 作为“工具工厂”适合被设计成一个 plane。
- 它生成出来的一批 CLI Harness，再被挂载为 Aelin 的 tools + skills。

## 二、目标能力

从用户视角，希望最终可以做到：

1. 用户给出某个本地软件（比如：安装路径、可执行文件、或标准名称）。
2. Aelin 理解需求后，将“为该软件生成 CLI 工具”的任务 **委派给 CLI-Anything plane**。
3. CLI-Anything plane 自动完成：
   - 分析软件交互模式；
   - 设计合理的命令结构；
   - 实现对应 CLI（Click 等）；
   - 生成测试与文档（SKILL 描述）；
   - 产出可调用的 CLI 包。
4. Aelin 接收 plane 的产出，并将其注册为：
   - 一组新的 Aelin tools（命令级别封装）；
   - 对应的一份 / 多份 skill 元数据（供 LLM 理解工具能力）。
5. 之后，普通用户就可以直接通过 Aelin 使用这组新工具，而 **无需关心 CLI-Anything 的内部细节**。

## 三、运行模式划分：开发期 vs 运行期

### 3.1 开发期模式（当前可行、优先落地）

特征：

- CLI-Anything 仅供开发者/维护者使用，不暴露在最终用户工作流中。
- 典型流程：
  1. 开发者在本地运行 CLI-Anything，为目标软件生成 `xxx-cli`。
  2. 对生成的 CLI 包进行 Review / 手工微调。
  3. 在 Aelin 仓库中为这套 CLI 写好：
     - tool 封装（后端 tool 实现）；
     - skill 描述（SKILL.md 或等价结构）；
     - 必要的配置/文档。
  4. 发布新版本 Aelin。

优点：

- 安全简单，变更可控。
- 与当前 gws 集成方式高度一致（gws 即是“现成 CLI → tool 封装”的范式）。

缺点：

- 普通用户无法“随手接入任意软件”；必须等维护者打包后发新版。

### 3.2 运行期 plane 模式（未来增强）

特征：

- 将 CLI-Anything 包装成真正的 plane，接入 Aelin 的 plane 体系。
- 允许终端用户在运行时发起“为某个软件生成 CLI”的需求。

运行过程示意：

1. 用户在 Aelin 中发起请求：
   - 示例：「帮我把 `D:\Tools\FooApp\foo.exe` 接入成可用工具」。
2. Aelin 识别到这是「软件接入」类任务，选择 **CLI-Anything plane**：
   - 整理需求（软件路径、期望权限：只读 / 可写、主要要做的任务类型等）。
   - 构造 plane 任务描述并下发。
3. CLI-Anything plane 内部执行完整流水线：
   - 软件分析、操作流程设计；
   - CLI 实现与测试生成；
   - 文档 & skill 元数据生成；
   - 最终产出：一组可执行 CLI 命令及其描述。
4. Aelin 定期轮询 / 订阅 plane 进度：
   - 通过 plane trace（步骤列表）反馈给用户；
   - 可以支持中途终止、重试等控制。
5. plane 完成后，将结果注册为新工具集：
   - 更新 Aelin 的 tool catalog；
   - 记录并持久化对应的 skill 元数据；
   - 允许用户在后续对话中直接使用这些新工具。

特点：

- CLI-Anything 在这个模式下是真正的 plane：它是一个“工具工厂系统”，有自己的内部规划与执行链路。

## 四、与现有 plane / tool 体系的关系

从 Aelin 的角度，可以把 CLI-Anything 相关的角色拆成三层：

1. **工具产物（Tools）**  
   - 生成后的 `xxx-cli` 的具体子命令，比如：
     - `office-cli open-document --path ...`
     - `blender-cli render --scene ...`
   - 这些在后端会被封装为 Aelin tools，并带上统一的元数据（名称、说明、参数 schema、返回格式）。

2. **工具工厂 plane（CLI-Anything Plane）**  
   - 专门处理“生成一批新工具”的长流程任务；
   - 对 Aelin 来说，它提供的是：
     - `create_cli_for_software(software_spec, capability_constraints) -> ToolBundleSpec`
   - 其内部的 7 阶段（分析、设计、实现、测试、文档、发布等）不会暴露为单个 tool，而是通过 **plane trace** 呈现。

3. **Aelin 自身的 orchestrator 能力**  
   - 当用户提出“接入某个软件”的需求时：
     - Aelin 决定是否使用 CLI-Anything plane；
     - 处理 plane 完成后的工具注册与解释；
     - 在后续普通对话中自然使用这些工具。

这样划分，保证了：

- 运行期真正暴露给用户的是「工具」和「plane」，而不是“纯技术实现细节”。
- CLI-Anything 同时可以服务于：
  - 开发者（开发期，不暴露给用户）；
  - 终端用户（运行期，通过 plane 间接使用）。

## 五、元数据与 skill 设计

为了让 LLM 能够安全且高效地使用由 CLI-Anything 生成的工具，需要统一的元数据/skill 规范。

### 5.1 工具元数据（Tool Catalog）

每个 CLI 子命令需要至少包含：

- `id`：工具唯一标识（例如：`cli_anything.office.open_document`）。
- `title`：简短人类可读名称。
- `description`：该工具能完成什么任务，输入输出是什么。
- `input_schema`：参数名称、类型、是否必填、合法范围等。
- `output_schema`：返回结构（尤其推荐 `--json` 输出）与字段含义。
- `safety_notes`：副作用说明（只读 / 写入 / 删除 等）。

CLI-Anything plane 生成产物时，应同时生成这一份结构化元数据，供 Aelin 直接挂载。

### 5.2 skill 描述（类似 SKILL.md）

在工具级元数据之上，还需要一份面向 LLM “知识注入”的 skill 描述，用来：

- 解释整个工具族（例如“Office 工具集”）的大图景与适用场景；
- 给出常见使用示例（示例 user query → 工具调用序列）；
- 描述限制与注意事项（如：「不要在用户明确禁止的文件夹中进行写入操作」）。

CLI-Anything 在生成 CLI 时，通常会生成 `SKILL.md` 或类 SKILL 文档；  
Aelin 可以直接读取/转换为内部的 skill 结构，并在启动时注入到 LLM 初始上下文中。

## 六、安全与边界

将 CLI-Anything 暴露为 plane 时，需要明确安全策略：

1. **软件白名单 / 黑名单**  
   - 默认只允许为“安全已知的软件”生成 CLI（例如开源办公套件、图形工具等）。
   - 对未知或高风险软件要求额外确认，或完全拒绝。

2. **权限范围约束**  
   - 在任务描述中显式区分：只读 / 可写 / 高危操作（如删除、系统配置修改）。
   - CLI-Anything plane 生成工具时，必须在元数据和 skill 中标注副作用。

3. **运行环境隔离**  
   - 理想情况：在隔离环境（容器/沙箱）中运行 CLI-Anything 和目标软件的分析与测试。
   - 防止恶意软件通过此流程获得更高权限。

4. **人工审阅（可选）**  
   - 对于高能力 plane，可以加入“人工审核”环节：  
     - plane 先生成候选 CLI & skill，  
     - 由维护者审阅后再正式挂载到全局工具集。

## 七、后续落地建议

短期（可行路线）：

1. 继续采用“开发期模式”使用 CLI-Anything：
   - 手动为一些典型软件生成 CLI；
   - 在 Aelin 中封装成工具 + skill（类似 gws）。
2. 在此基础上，抽象出一套“**通过 CLI 封装接入工具**”的统一规范：
   - 目录结构、配置文件、tool 定义方式；
   - skill 的读取与注入方式。

中期（设计 CLI-Anything plane）：

1. 设计 plane 接口（后端）：  
   - 输入：软件描述（路径 + 名称 + 权限需求 + 目标任务类型）；  
   - 输出：工具元数据 + skill 文本 + CLI 安装位置等。
2. 在 trace 系统中预留 plane 链路展示能力：  
   - 未来可以展示 CLI-Anything 7 阶段的每一步。

远期（真正开放给终端用户）：

1. 在安全策略完善的前提下，开放「一键接入软件」的用户入口；
2. Aelin 通过 CLI-Anything plane 为用户动态生成并挂载新工具；
3. 在 UI 上提供：
   - 新接入工具列表；
   - 对应 plane 链路追踪；
   - 清理/卸载这些动态工具的能力。

---

本设计文档的目标是：先把「CLI-Anything 作为工具工厂 plane」的角色讲清楚。  
后续在真正开始实现时，可以据此拆解为多个 PR 与里程碑逐步推进。 

