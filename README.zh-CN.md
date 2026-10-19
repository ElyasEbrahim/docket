[English](README.md) | **简体中文**

# Docket（暂定名）

[![CI](https://github.com/ElyasEbrahim/docket/actions/workflows/ci.yml/badge.svg)](https://github.com/ElyasEbrahim/docket/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**为 Postgres 提供可持久保存、可版本化、经过校准的 AI 判断。** 你只需定义一次语义判断（例如 *"这条投诉是否与催收有关？"*），Docket 会把结果作为数据保存下来：带版本、用你自己的标注校准，并如实给出不确定性。它适用于任何 Postgres，也适用于任何判断模型。

> **状态：第 0 阶段（验证）。** Docket 产品本身尚未开发。本仓库目前包含设计文档（[REPORT.md](REPORT.md)、[架构决策记录](docs/adr/)），以及一套可运行的基准测试工具，并已在真实数据上测量了问题（[实验结论](docs/phase0/FINDINGS-jev-1.13.md)）。进度通过 [Issues](https://github.com/ElyasEbrahim/docket/issues) 和 [Milestones](https://github.com/ElyasEbrahim/docket/milestones) 跟踪。

> 注：除本 README 外，其余文档目前仅有英文版。

## 要解决的问题

[pg-jev](https://github.com/realZachi/pg-jev) 让你用自然语言筛选数据行，例如 `WHERE jev(tickets, 'the customer threatens to cancel')`，背后由 TypeSafe 的 Jev 判断模型完成。这很适合探索。但要在生产中依赖这些结果，它们必须稳定、可比较、可信，而现在还做不到：

- 数据库会话结束后结果就消失，每个新会话都要把整张表重新判断一遍；
- 有人新增一个标签选项、换模型或换后端时，结果会变；
- 只是再问一次，或者把这一行和不同的行放在同一批里发送，结果也会变；
- `0.7` 的分数并不代表 70%，基于 AI 标签的 `count(*)` 也没有误差范围；
- 无法在 Supabase、Neon、RDS 等托管数据库上运行。

如今模型调用的成本大约只有**每百万行 6–25 美元**（取决于文本长度和每次请求的行数），瓶颈已经不是成本，而是这些结果能否被信任、能否被审计。

## 第 0 阶段测到了什么

用 2,000 条真实的消费者投诉文本，通过 pg-jev 交给 jev-1.13.0 判断，API 费用合计约 0.30 美元。

| 发现 | 结果 |
| --- | --- |
| 分数过于自信 | 9 选 1 分类的 ECE 为 **0.089**；是/否判断的 ECE 为 **0.24–0.38** |
| 约 100 条标注就能修正大部分偏差 | 用 100 条标注校准，可消除 **45–85%** 的误差 |
| 再问一次，答案会变 | 3 次完全相同的运行中，**4.8%** 的行的首选答案发生变化 |
| 同批的"邻居"会改变答案 | 同样的行换一种分批方式，约 **16.5%** 的答案改变（约为随机波动的 5 倍） |
| 每次只判断一行更好 | 逐行判断：准确率 **+2.4 个百分点**，macro-F1 +0.05，token 用量为 1.8 倍 |
| 新增选项会带走答案 | 新增一个"其他"类选项后，**2.5%** 的答案转到了它 |
| 分数很粗糙 | 概率以 0.01 为刻度，并且有大量恰好为 0 的值 |

面向一般读者的文章：[*Same row, different answer*](docs/notes/2026-10-same-row-different-answer.md)（英文）。详细结果、方法和局限：[docs/phase0/FINDINGS-jev-1.13.md](docs/phase0/FINDINGS-jev-1.13.md)（英文）。

## Docket 将会是什么

1. **持久保存的判断。** 结果写入只追加的记录表（ledger），并提供一个可以 join、可以建索引的视图。新增或修改的行会被自动判断，每次请求只判断一行。
2. **版本管理。** 修改问题、标签、模型或分批方式都会产生新版本；新版本先和旧版本比较，确认无误后再替换。
3. **用你自己的标注来校准。** 每个判断只需约 100–200 条人工标注，就能把原始分数变成名副其实的概率。
4. **如实的数字。** 阈值附带明确的保证（如"精确率 ≥ 95%"），计数附带置信区间（预测驱动推断，prediction-powered inference）。
5. **随处可运行。** 纯 SQL 加一个外部 worker，不需要超级用户权限，也不需要不受信任的扩展。可在 Supabase、Neon 和 RDS 上运行。

架构与 SQL 草图：[REPORT.md §4](REPORT.md#4-the-recommended-project-docket)。已做出的架构决策：[docs/adr/](docs/adr/)。

## 快速开始：第 0 阶段测试工具

需要 Docker，所有组件都在容器中运行。

```bash
make up            # Postgres 16 + pg-jev v0.2.1、pg-jev 的模拟 API、一个模拟后端
make test          # 测试工具的单元测试
make smoke         # 用模拟 API 运行 pg-jev README 中的示例查询
make fetch load    # 2,000 条 CFPB 投诉文本（CC0 镜像）→ Postgres
make bench         # 在模拟后端上运行全部实验 → results/<run_id>/report.md
```

如果要调用真实的 Jev API，把 `.env.example` 复制为 `.env`，填入你的 TypeSafe 密钥，然后运行：

```bash
make bench BACKEND=jev ARGS=--yes   # 会先显示预估费用；超过 1 美元会拒绝执行
```

更多命令（重复性检验、标注学习曲线、分批影响）：[harness/README.md](harness/README.md)（英文）。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| [REPORT.md](REPORT.md) | 项目报告：pg-jev 剖析、前沿研究综述、候选方案、设计、评估计划、风险 |
| [ROADMAP.md](ROADMAP.md) | 分阶段计划及每阶段的完成标准 |
| [CHANGELOG.md](CHANGELOG.md) | 按日期记录的变更 |
| [docs/adr/](docs/adr/) | 架构决策记录 |
| [docs/phase0/](docs/phase0/) | 第 0 阶段的结论、状态、待提交给上游的问题草稿 |
| [docs/notes/](docs/notes/) | 面向公众的文章 |
| [harness/](harness/) | 基准测试工具：`jevbench` 命令行、模拟后端、测试 |
| [results/](results/) | 结论中引用的各次运行报告 |
| `docker-compose.yml`、`Makefile` | 测试环境及其命令 |

## 参考来源

- [realZachi/pg-jev](https://github.com/realZachi/pg-jev)：本项目所基于的 Postgres 扩展（PostgreSQL 许可证）。
- winkrun，《不用向量索引，Postgres 也能做语义过滤：pg-jev 上手》（2026 年 10 月 4 日）。文中列出的 pg-jev 注意事项直接影响了本项目的设计；本仓库不转载原文。
- 完整参考文献：[REPORT.md § Sources](REPORT.md#sources)。

## 参与贡献

本项目由一人维护。欢迎提交 Issue 和问题；目前不接受 Pull Request。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[Apache-2.0](LICENSE)。Copyright 2026 ElyasEbrahim。
