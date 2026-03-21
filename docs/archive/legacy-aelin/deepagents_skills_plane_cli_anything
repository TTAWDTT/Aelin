# CLI-Anything Plane Skill for DeepAgents

本技能为未来接入 CLI-Anything（如 HKUDS/CLI-Anything）类 plane 预留，说明
如何通过命令行界面执行复杂的本地或远程任务。

## 能力概览

- 在受控的 shell/终端环境中执行命令行程序。
- 适合需要脚本化、多步骤的自动化任务，例如：
  - 执行一系列 CLI 工具获取信息。
  - 调用本地脚本对文件进行批处理。
  - 启动特定的 CLI 客户端再在其中进行交互。

## goal 模板示例

对于 CLI plane，goal 应包含：

- 要使用的程序或工具名称（如 `ffmpeg`、`git`、某自定义 CLI）。
- 输入 / 输出的文件或路径。
- 期望的结果（生成文件、更新状态、输出报告等）。

示例：

- 「使用本机安装的 `ffmpeg`，把 `~/Videos/input.mp4` 转成 720p 的 H.264 MP4 文件，保存为 `~/Videos/output_720p.mp4`。」  
- 「在当前项目目录中运行测试命令 `pytest -q`，并简要总结失败用例。」  
- 「调用某自定义 CLI 工具，批量重命名指定目录下的图片文件，并生成一份重命名日志。」  

## 使用约定

1. 与其他 plane 一样，通过 `plane` 工具调用：
   - `plane = "cli_anything"`（实际名字可以在接入时确定）。
   - `action` 之一：
     - `delegate`：创建新的 CLI 任务。
     - `status`：查询任务状态。
     - `continue`：在任务需要多轮执行时继续运行。
     - `close`：在任务完成或不再需要时关闭任务。

2. 在构造 `goal` 时应特别注意安全与范围：
   - 明确限定所允许访问的目录或资源。
   - 避免使用会造成破坏性效果的命令（如 `rm -rf /`），即使在受控环境中也应保持谨慎。

3. 对于仅需要少量一次性命令执行的场景，优先考虑使用 DeepAgents 自带的 todo / filesystem 能力；
   只有在需要复杂 CLI 交互或依赖现有 CLI 程序时，才委派给 CLI-Anything plane。

