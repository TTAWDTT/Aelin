# DeepAgents Skill Matrix Report

Total skills tested: 23
Prompt-chain passes: 23
Env smokes passed: 4
Env smokes blocked: 4

| Skill | Prompt Chain | Env Smoke | Tool Calls |
| --- | --- | --- | --- |
| anthropic-canvas-design | PASS | not_checked | 0 |
| anthropic-docx | PASS | passed | 0 |
| anthropic-pdf | PASS | blocked | 0 |
| anthropic-pptx | PASS | passed | 0 |
| anthropic-skill-creator | PASS | not_checked | 0 |
| anthropic-xlsx | PASS | warning | 0 |
| callstack-github | PASS | passed | 0 |
| chrome-cdp | PASS | blocked | 0 |
| codebase-documenter | PASS | not_checked | 0 |
| exploratory-data-analysis | PASS | not_checked | 0 |
| file_tools | PASS | not_checked | 0 |
| firecrawl-browser | PASS | blocked | 0 |
| firecrawl-cli | PASS | blocked | 0 |
| google_workspace | PASS | warning | 0 |
| kaizen | PASS | not_checked | 0 |
| literature-review | PASS | not_checked | 0 |
| paper-slide-deck | PASS | passed | 0 |
| project-bootstrapper | PASS | not_checked | 0 |
| scientific-critical-thinking | PASS | not_checked | 0 |
| scientific-writing | PASS | not_checked | 0 |
| solid | PASS | not_checked | 0 |
| trailofbits-modern-python | PASS | not_checked | 0 |
| translation | PASS | not_checked | 0 |

## anthropic-canvas-design

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `design philosophy creation, canvas`
- Markers hit: `design philosophy creation, canvas`
- Env smoke: `not_checked`

### Answer

```text
Based on my reading of the `/skills/aelin/anthropic-canvas-design/SKILL.md` file, the two high-level steps in its workflow are:

1. **Design Philosophy Creation** - Creating a visual philosophy/aesthetic movement as a .md file that serves as the foundation for the artwork.

2. **Canvas Creation** - Expressing the design philosophy visually by creating the actual artwork as a .pdf or .png file.

This is explicitly stated in lines 9-12 of the document: "Complete this in two steps: 1. Design Philosophy Creation (.md file) 2. Express by creating it on a canvas (.pdf file or .png file)"
```

## anthropic-docx

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `soffice.py, --convert-to docx`
- Markers hit: `soffice.py, --convert-to docx`
- Env smoke: `passed`
- Env command: `python backend/deepagents_skills/anthropic-docx/scripts/accept_changes.py --help`

### Answer

```text
Based on the skill documentation, the exact command for converting a legacy .doc file to .docx is:

```bash
python scripts/office/soffice.py --headless --convert-to docx document.doc
```
```

### Env Output

```text
usage: accept_changes.py [-h] input_file output_file

Accept all tracked changes in a DOCX file

positional arguments:
  input_file   Input DOCX file with tracked changes
  output_file  Output DOCX file (clean, no tracked changes)

options:
  -h, --help   show this help message and exit
```

## anthropic-pdf

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `pdfplumber`
- Markers hit: `pdfplumber`
- Env smoke: `blocked`
- Env command: `python backend/deepagents_skills/anthropic-pdf/scripts/extract_form_structure.py --help`

### Answer

```text
根据我读取的 `/skills/aelin/anthropic-pdf/SKILL.md` 文件，该技能推荐使用 **pdfplumber** 这个Python库来从PDF中提取表格。

具体来说：

1. 在文件的第79-119行，专门有一个章节介绍 **pdfplumber - Text and Table Extraction**（pdfplumber - 文本和表格提取）

2. 在第91-100行展示了如何使用pdfplumber提取表格的示例代码：
   ```python
   with pdfplumber.open("document.pdf") as pdf:
       for i, page in enumerate(pdf.pages):
           tables = page.extract_tables()
           for j, table in enumerate(tables):
               print(f"Table {j+1} on page {i+1}:")
               for row in table:
                   print(row)
   ```

3. 在第102-119行还展示了更高级的表格提取功能，包括使用pandas处理提取的表格数据

4. 在文件的快速参考表（第296-307行）中明确列出：
   - 提取表格（Extract tables）的最佳工具是：pdfplumber
   - 对应的命令/代码是：`page.extract_tables()`

所以，anthropic-pdf技能推荐使用 **pdfplumber** 这个Python库来从PDF文件中提取表格。
```

### Env Output

```text
Traceback (most recent call last):
  File "D:\Github\Aelin\backend\deepagents_skills\anthropic-pdf\scripts\extract_form_structure.py", line 17, in <module>
    import pdfplumber
ModuleNotFoundError: No module named 'pdfplumber'
```

## anthropic-pptx

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `markitdown, presentation.pptx`
- Markers hit: `markitdown, presentation.pptx`
- Env smoke: `passed`
- Env command: `python backend/deepagents_skills/anthropic-pptx/scripts/thumbnail.py --help`

### Answer

```text
Based on the skill file, the exact command recommended for text extraction from a presentation is:

**`python -m markitdown presentation.pptx`**

This command is shown in the "Quick Reference" table (line 13) and again in the "Reading Content" section (line 23) for text extraction from a .pptx file.
```

### Env Output

```text
usage: thumbnail.py [-h] [--cols COLS] input [output_prefix]

Create thumbnail grids from PowerPoint slides.

positional arguments:
  input          Input PowerPoint file (.pptx)
  output_prefix  Output prefix for image files (default: thumbnails)

options:
  -h, --help     show this help message and exit
  --cols COLS    Number of columns (default: 3, max: 6)
```

## anthropic-skill-creator

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `evaluation, rewrite`
- Markers hit: `evaluation, rewrite`
- Env smoke: `not_checked`

### Answer

```text
Based on my reading of the skill creator documentation, I can now answer your question.

After writing a draft skill, the anthropic-skill-creator emphasizes:

1. **Evaluation-related phase**: The skill emphasizes running test cases and evaluating results both qualitatively and quantitatively. This includes:
   - Creating test prompts and running `claude-with-access-to-the-skill` on them
   - Helping the user evaluate results qualitatively and quantitatively
   - Drafting quantitative evals if they don't exist
   - Using the `eval-viewer/generate_review.py` script to show results
   - Grading each run and aggregating into benchmarks

2. **Rewrite-related phase**: The skill emphasizes rewriting the skill based on feedback from the user's evaluation of results (and any glaring flaws from quantitative benchmarks). This includes:
   - Improving the skill based on user feedback
   - Generalizing from feedback rather than overfitting to specific examples
   - Keeping the prompt lean and removing unproductive parts
   - Explaining the "why" behind instructions
   - Looking for repeated work across test cases to bundle into scripts

The process is iterative: after evaluation, you rewrite the skill, then repeat the evaluation with the improved version until satisfied. The documentation specifically states in the high-level process overview: "Rewrite the skill based on feedback from the user's evaluation of the results (and also if there are any glaring flaws that become apparent from the quantitative benchmarks)" and "Repeat until you're satisfied."
```

## anthropic-xlsx

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `zero formula errors, professional font`
- Markers hit: `zero formula errors, professional font`
- Env smoke: `warning`
- Env command: `python backend/deepagents_skills/anthropic-xlsx/scripts/recalc.py`

### Answer

```text
Based on the skill documentation I've read, here are the answers to your questions:

## Required Font Rule:
The skill requires using **a consistent, professional font (e.g., Arial, Times New Roman) for all deliverables** unless otherwise instructed by the user. This is specified in the "Professional Font" section (lines 11-13).

## Formula-Error Rule:
The skill mandates that **every Excel model MUST be delivered with ZERO formula errors**. Specifically, it lists these error types that must be eliminated: `#REF!`, `#DIV/0!`, `#VALUE!`, `#N/A`, `#NAME?`. This is specified in the "Zero Formula Errors" section (lines 14-16).

Additionally, the skill provides a workflow for recalculating formulas and fixing errors using the `scripts/recalc.py` script, which helps identify and resolve these formula errors before delivering the final Excel file.
```

### Env Output

```text
Usage: python recalc.py <excel_file> [timeout_seconds]

Recalculates all formulas in an Excel file using LibreOffice

Returns JSON with error details:
  - status: 'success' or 'errors_found'
  - total_errors: Total number of Excel errors found
  - total_formulas: Number of formulas in the file
  - error_summary: Breakdown by error type with locations
    - #VALUE!, #DIV/0!, #REF!, #NAME?, #NULL!, #NUM!, #N/A
```

## callstack-github

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `gh pr merge, --squash`
- Markers hit: `gh pr merge, --squash`
- Env smoke: `passed`
- Env command: `gh --version`

### Answer

```text
Based on the skill file, the exact gh CLI command template for squash-merging a PR is:

```bash
gh pr merge <PR_NUMBER> --squash --title "feat: add feature (#<PR_NUMBER>)"
```

This is shown on line 23 of the skill file.
```

### Env Output

```text
gh version 2.87.3 (2026-02-23)
https://github.com/cli/cli/releases/tag/v2.87.3
```

## chrome-cdp

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `scripts/cdp.mjs list`
- Markers hit: `scripts/cdp.mjs list`
- Env smoke: `blocked`
- Env command: `node backend/deepagents_skills/chrome-cdp/scripts/cdp.mjs list`

### Answer

```text
According to the Chrome CDP skill documentation, the exact command it recommends for listing open pages is:

```bash
scripts/cdp.mjs list
```
```

### Env Output

```text
No DevToolsActivePort found. Enable remote debugging at chrome://inspect/#remote-debugging
```

## codebase-documenter

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `architecture.md, development.md`
- Markers hit: `architecture.md, development.md`
- Env smoke: `not_checked`

### Answer

```text
Based on the codebase-documenter skill file, two markdown files that should appear under the `docs/` output are:

1. `ARCHITECTURE.md` - System architecture documentation
2. `DEVELOPMENT.md` - Development guide

The skill shows the following structure in the Output section:
```
docs/
├── README.md              # Overview and quick start
├── ARCHITECTURE.md        # System architecture
├── DEVELOPMENT.md         # Development guide
├── API.md                 # API documentation
├── DEPLOYMENT.md          # Deployment guide
└── CONTRIBUTING.md        # Contribution guidelines
```
```

## exploratory-data-analysis

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `.fastq`
- Markers hit: `.fastq`
- Env smoke: `not_checked`

### Answer

```text
Looking through the skill documentation, I can see several example file extensions mentioned in the analysis flow examples. Let me check the specific analysis flow example mentioned in the question. Looking at the examples in the skill documentation:

1. In the "Step 1: File Type Detection" section (lines 92-98), there's an example with `.fastq`
2. In "Example 1: Analyzing a FASTQ file" (lines 268-289), the example uses `.fastq`
3. In "Example 2: Analyzing a CSV dataset" (lines 291-313), the example uses `.csv`
4. In "Example 3: Analyzing microscopy data" (lines 315-338), the example uses `.nd2`

However, the question specifically asks about "what example file extension appears in the analysis flow example?" Looking at the "Step 1: File Type Detection" section which shows the analysis flow example, the file extension used is `.fastq`.

The analysis flow example in the skill documentation shows:
```
User: "Analyze data.fastq"
→ Extension: .fastq
→ Category: bioinformatics_genomics
→ Format: FASTQ Format (sequence data with quality scores)
→ Reference: references/bioinformatics_genomics_formats.md
```

The example file extension that appears in the analysis flow example is **`.fastq`**.
```

## file_tools

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `attachment_search`
- Markers hit: `attachment_search`
- Env smoke: `not_checked`

### Answer

```text
当用户说“总结这个 PDF”时，推荐第一步调用 `attachment_search` 工具。
```

## firecrawl-browser

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `scrape, first`
- Markers hit: `scrape, first`
- Env smoke: `blocked`
- Env command: `firecrawl interact --help`

### Answer

```text
Based on the documentation in `/skills/aelin/firecrawl-browser/SKILL.md`, **you must scrape a page first** before using interact. 

Specifically, the documentation states:

1. **"Always scrape first — `interact` requires a scrape ID from a previous `firecrawl scrape` call"** (line 73)
2. **"Scrape a page first, then use natural language prompts or code to click, fill forms, navigate, and extract data"** (line 11)
3. The quick start shows the workflow: `firecrawl scrape "<url>"` first, then `firecrawl interact --prompt "..."`

The scrape command creates a browser session and saves a scrape ID, which the interact command uses to access that same browser session for performing actions like clicking, filling forms, or navigating.
```

### Env Output

```text
'firecrawl' is not recognized as an internal or external command,
operable program or batch file.
```

## firecrawl-cli

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `search, scrape, map, crawl, interact`
- Markers hit: `search, scrape, map, crawl, interact`
- Env smoke: `blocked`
- Env command: `firecrawl --help`

### Answer

```text
Based on the firecrawl-cli skill documentation, the five workflow escalation steps in order are:

1. **Search** - No specific URL yet. Find pages, answer questions, discover sources.
2. **Scrape** - Have a URL. Extract its content directly.
3. **Map + Scrape** - Large site or need a specific subpage. Use `map --search` to find the right URL, then scrape it.
4. **Crawl** - Need bulk content from an entire site section (e.g., all /docs/).
5. **Interact** - Scrape first, then interact with the page (pagination, modals, form submissions, multi-step navigation).
```

### Env Output

```text
'firecrawl' is not recognized as an internal or external command,
operable program or batch file.
```

## google_workspace

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `auth_status`
- Markers hit: `auth_status`
- Env smoke: `warning`
- Env command: `gws auth status`

### Answer

```text
根据文档内容，在尝试写操作前，应该先调用 **`auth_status`** action 来检查：

1. 用户是否已登录
2. 是否具备所需 scope（如 `documents`、`drive` 等）

这是文档第28-31行明确说明的安全使用约定。
```

### Env Output

```text
{
  "auth_method": "none",
  "client_config": "C:\\Users\\CodexSandboxOffline\\.config\\gws\\client_secret.json",
  "client_config_exists": false,
  "credential_source": "none",
  "encrypted_credentials": "C:\\Users\\CodexSandboxOffline\\.config\\gws\\credentials.enc",
  "encrypted_credentials_exists": false,
  "keyring_backend": "keyring",
  "plain_credentials": "C:\\Users\\CodexSandboxOffline\\.config\\gws\\credentials.json",
  "plain_credentials_exists": false,
  "storage": "none",
  "token_cache_exists": false
}
```

## kaizen

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `make it work, make it clear, make it robust`
- Markers hit: `make it work, make it clear, make it robust`
- Env smoke: `not_checked`

### Answer

```text
Based on the kaizen skill documentation, I can see the `calculateTotal` example with three iterations. Looking at the code comments in the documentation:

From the code example in lines 56-82:

1. **Iteration 1**: "Make it work" (line 56)
2. **Iteration 2**: "Make it clear (refactor)" (line 65)  
3. **Iteration 3**: "Make it robust (add validation)" (line 72)

The labels for the three iterations in the `calculateTotal` example are:

1. **Iteration 1**: "Make it work"
2. **Iteration 2**: "Make it clear" (with refactor)
3. **Iteration 3**: "Make it robust" (with validation)
```

## literature-review

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `generate_schematic.py, figures/output.png`
- Markers hit: `generate_schematic.py, figures/output.png`
- Env smoke: `not_checked`

### Answer

```text
Perfect! I found it. Based on the literature-review skill file, the Python command example it gives for generating a schematic figure is:

```bash
python scripts/generate_schematic.py "your diagram description" -o figures/output.png
```

This command is found in the "Visual Enhancement with Scientific Schematics" section of the skill documentation (line 44). The skill mandates that every literature review must include at least 1-2 AI-generated figures using this command or similar methods through the scientific-schematics skill.
```

## paper-slide-deck

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `gemini api, gemini web`
- Markers hit: `gemini api, gemini web`
- Env smoke: `passed`
- Env command: `python backend/deepagents_skills/paper-slide-deck/scripts/generate-slides.py --help`

### Answer

```text
根据我读取的文件内容，在Step 5中提供给用户的两种图像生成方式是：

1. **Gemini API（推荐）** - 使用官方的Google API通过Python脚本生成图像，需要GOOGLE_API_KEY环境变量
2. **Gemini Web（基于浏览器）** - 使用逆向工程的网页API，不需要API密钥但可能不稳定

这两种方式在Step 5的"Image Generation Method Selection"部分有详细说明，用户需要在生成图像之前选择其中一种方法。
```

### Env Output

```text
usage: generate-slides.py [-h] [--model MODEL] slide_deck_dir

Generate slide images using Gemini API

positional arguments:
  slide_deck_dir  Directory containing prompts/ folder

options:
  -h, --help      show this help message and exit
  --model MODEL   Gemini model to use (default: gemini-3-pro-image-preview)
```

## project-bootstrapper

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `src/, tests/, docs/`
- Markers hit: `src/, tests/, docs/`
- Env smoke: `not_checked`

### Answer

```text
Based on the project-bootstrapper skill documentation, three standard directories it says should be set up for project structure are:

1. **`src/`** - For source code
2. **`tests/`** - For test files  
3. **`docs/`** - For documentation

The documentation also mentions `scripts/` and `.github/` as additional standard directories, but the three explicitly listed in the "Standard directories" section are `src/`, `tests/`, and `docs/`.
```

## scientific-critical-thinking

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `grade, cochrane`
- Markers hit: `grade, cochrane`
- Env smoke: `not_checked`

### Answer

```text
Based on my reading of the skill file, I can see that the `/skills/aelin/scientific-critical-thinking/SKILL.md` explicitly mentions two evidence-quality frameworks:

1. **GRADE** (Grading of Recommendations Assessment, Development and Evaluation)
2. **Cochrane Risk of Bias (ROB)**

These are mentioned in:
- Line 3 of the description: "applying evidence grading frameworks (GRADE, Cochrane Risk of Bias)"
- Line 14: "using GRADE and Cochrane ROB frameworks"
- Line 24: "Applying GRADE or Cochrane risk of bias assessments"
- Line 251: "Risk of bias assessment (use appropriate tool: Cochrane ROB, Newcastle-Ottawa, etc.)"
- Line 256: "GRADE Considerations (if applicable)"

The two evidence-quality frameworks explicitly mentioned in the skill file are **GRADE** and **Cochrane Risk of Bias (ROB)**.
```

## scientific-writing

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `graphical abstract, bullet points`
- Markers hit: `graphical abstract, bullet points`
- Env smoke: `not_checked`

### Answer

```text
Based on my reading of the scientific writing skill documentation:

1. **Visual element every scientific paper must include**: The skill states that **every scientific paper MUST include a graphical abstract** (plus 1-2 additional AI-generated figures). This is explicitly marked as "⚠️ MANDATORY" in the documentation.

2. **Writing format forbidden in final manuscripts**: The skill explicitly forbids **bullet points** in final manuscripts. It states: "**Critical Principle: Always write in full paragraphs with flowing prose. Never submit bullet points in the final manuscript.**" and later reinforces: "**CRITICAL: Always write in full paragraphs, never submit bullet points in scientific papers.**"

The skill emphasizes a two-stage process where bullet points can be used in outlines during the planning phase, but the final manuscript must be converted to complete, flowing paragraphs.
```

## solid

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `red, green, refactor`
- Markers hit: `red, green, refactor`
- Env smoke: `not_checked`

### Answer

```text
Based on the SOLID skill documentation, the three mandatory TDD phases listed are:

1. **RED** - Write a failing test that describes the behavior
2. **GREEN** - Write the SIMPLEST code to make it pass  
3. **REFACTOR** - Clean up, remove duplication (Rule of Three)

These are presented in the "Red-Green-Refactor" cycle that the skill describes as "not optional" for Test-Driven Development.
```

## trailofbits-modern-python

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `uv pip install, uv add`
- Markers hit: `uv pip install, uv add`
- Env smoke: `not_checked`

### Answer

```text
Based on the skill documentation I've read, specifically from the "Anti-Patterns to Avoid" table (lines 26-38), the skill says to avoid:

**Avoid:** `uv pip install`
**Use Instead:** `uv add` and `uv sync`

This is clearly stated in the table row:
- **Avoid:** `uv pip install`
- **Use Instead:** `uv add` and `uv sync`

The skill emphasizes that you should always use `uv add` and `uv remove` to manage dependencies, and never manually edit pyproject.toml to add dependencies.
```

## translation

- Prompt chain: PASS
- Capability summary: `tools=5; skills=23; memory_files=0`
- Expected markers: `natural`
- Markers hit: `natural`
- Env smoke: `not_checked`

### Answer

```text
根据翻译技能的说明文件，翻译模式有三种：

1. **Literal（字面翻译）**：逐字准确，保留原始结构，适用于技术文档、法律文本
2. **Natural（自然翻译）**：听起来像母语，适应习语和表达，适用于营销、创意内容
3. **Technical（技术翻译）**：特定领域术语，一致的词汇表使用，适用于软件、医疗、法律

短语"Keep structure but sound natural"的意思是"保持结构但听起来自然"。这描述的是在保留原文结构的同时，让翻译结果听起来自然流畅。

查看三种模式：
- **Literal模式**：强调"保留原始结构"，但可能不够自然
- **Natural模式**：强调"听起来像母语"，但可能会改变结构以适应目标语言
- **Technical模式**：强调术语一致性，不直接涉及结构vs自然的平衡

"Keep structure but sound natural"这个要求正好介于Literal和Natural之间，但更偏向于在保持结构的基础上实现自然表达。从描述来看，这最接近**Literal模式**，因为Literal模式明确提到"Preserves original structure"（保留原始结构），同时翻译技能应该会尽量让结果可读。

因此，对于"Keep structure but sound natural"这个要求，应该使用**Literal模式**。
```
