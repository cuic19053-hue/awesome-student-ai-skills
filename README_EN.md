# Awesome Student AI Skills

[![Awesome](https://awesome.re/badge.svg)](https://awesome.re)
[![Agent Skills](https://img.shields.io/badge/Agent_Skills-Compatible-6e3bf0)](https://agentskills.io/specification)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](./LICENSE)

> *“A robust domain knowledge engine for 35 types of Chinese university proposal documents. One prompt to automatically gather information, render charts (Mermaid/matplotlib), and generate perfectly formatted Word documents.”*

[简体中文](./README.md) | [English](./README_EN.md)

---

## 📖 Table of Contents

- [What is this?](#what-is-this)
- [How to Use](#how-to-use)
- [Architecture & Design](#architecture--design)
- [List of 35 Skills](#list-of-35-skills)
- [Contributing](#contributing)
- [License](#license)

---

## 💡 What is this?

This is **not just another prompt repository**. It's a structured framework that encapsulates complex domain workflows (such as scholarship applications, research proposals, business plans) into an **Agent Router and CLI utilities**. 

By feeding these 35 `SKILL.md` files into any Agent-compatible AI tool (like Claude Code, Cursor, or our CLI), the AI automatically acts as a domain expert:
1. **Interactive Information Gathering**: Asks the user exactly what is missing based on strict schemas.
2. **Fact-checking & Honesty Enforcement**: Refuses to hallucinate fake awards or experiences.
3. **Automated Data Visualization**: Generates Mermaid syntax for Gantt charts / Flowcharts, and uses Matplotlib for budget pie charts.
4. **Document Assembly**: Compiles everything into a perfectly formatted `.docx` file ready for submission.

---

## 🚀 How to Use

This project follows the **Agent Skills** specification. It is a combination of an **Expert Prompt Library + Automated Python Formatting Scripts**. You don't need to write any code, you just need an AI tool that supports local Agent capabilities.

### Core Workflow
1. **Prepare Environment**: Download an AI Agent IDE that supports local Python execution (e.g., **WorkBuddy, Codex, Claude Code, Trae Work**).
2. **Clone the Project**: Clone this project locally and run `pip install -r utils/requirements.txt` in your terminal (to install underlying dependencies like `python-docx`).
3. **Load the Skill**: In your AI tool, feed the root `SKILL.md` (or a specific subskill like `subskills/innovation_research/SKILL.md`) into the AI as the **System Prompt**.
4. **Start the Conversation**: Simply say to the AI: *"I want to write an innovation research proposal."*

### What will the AI do in the background?
- 🧠 **Interactive Inquiry**: The AI acts as a "mentor", strictly asking for your pain points and resume according to the requirements, never fabricating information.
- ⚙️ **Automatic Routing**: The AI automatically invokes the `utils/dispatcher.py` decision tree to help you determine the most suitable proposal type.
- 🖨️ **1-Click Word Generation**: Once information gathering is complete, the AI automatically executes the `subskills/xxx/build.py` script locally, rendering the collected JSON data directly into a fully formatted `.docx` physical file (complete with standard fonts, tables, and even signature blocks) for you!

---

## 🧠 Architecture & Design

Our `utils/` folder provides 7 core engineering modules shared across all 35 subskills:

| Module | Lines | Function |
|--------|-------|----------|
| `dispatcher.py` | 837 | 5-level decision tree router + keyword matching + interactive CLI |
| `docx_common.py` | 897 | Shared docx generator (margins/fonts/tables/signatures/pagination) |
| `school_template.py` | 760 | Format adapters for 5 specific universities (PKU, THU, WHU, ZJU, etc.) |
| `pdf_export.py` | 1036 | docx → PDF conversion engines |
| `plagiarism_checker.py`| 742 | n-gram duplication check + report generation |
| `review_simulator.py` | 1089 | Simulates committee reviews & scoring based on `review_criteria.json` |

Read our [Architecture Design Document (ZH)](./ARCHITECTURE.md) and [Agent Prompt Design (ZH)](./AGENT_DESIGN.md) for more details.

---

## 📋 List of 35 Skills

The repository currently supports 35 highly specialized proposal types across 9 categories. Here are a few notable ones:

*   🔬 **Research (大创/挑战杯)**: `innovation_research`, `entrepreneurship_training`, `challenge_cup`
*   🏆 **Scholarships (奖学金)**: `national_scholarship`, `motivation_scholarship`, `enterprise_scholarship`
*   🌾 **Social Practice (三下乡)**: `social_survey`, `volunteer_teaching`, `policy_lecture`
*   ✈️ **Study Abroad (公派留学)**: `csc_scholarship`, `exchange_program`

*See the [Chinese README](./README.md) for the full list of all 35 skills.*

---

## 🤝 Contributing

We welcome Issues and PRs! If you find:
- A school's specific template formatting needs tweaking.
- Outdated review criteria (e.g. new "Internet+" 2026 rules).
- Factual errors in the AI's output instructions.

Please let us know. Be sure to read `references/writing_guide.md` before contributing to align with our absolute "Honesty First" baseline.

---

## 📄 License

MIT License — feel free to use, modify, and build upon this project. We only ask that you retain the original authorship and disclaimer. See [LICENSE](./LICENSE).
