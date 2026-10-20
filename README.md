# PDF 简作

本地中文桌面工具，仅提供 PDF 压缩、合并、拆分，无 PDF 浏览功能，无需上传文件。

## 启动

Windows 已打包版本：直接双击 `dist\PDF简作.exe`，无需安装 Python 或其他依赖。

macOS 已完成代码适配和独立 App/DMG 构建配置，尚待在 Mac 环境构建验证；当前目录没有可交付的 Mac 安装包。详细状态与自动构建配置见 [独立桌面发行说明](packaging/README.md)。Mac 最终用户只需打开 DMG，将 App 拖到“应用程序”，双击运行，不执行下面的开发者安装步骤。

开发者从源码运行（最终用户无需操作）：

1. 安装 Python 3.10 或更高版本，勾选 Python Launcher 和 tkinter。
2. 首次双击 `安装依赖.bat`，联网安装 PyMuPDF；然后运行 `powershell -ExecutionPolicy Bypass -File prepare_engine.ps1` 提取官方 Ghostscript 引擎到项目目录。
3. 双击 `启动.bat`。

## 操作

界面参考 PDF24 的拖放导入及 Stirling PDF 的质量/大小两种设置方式：左侧切换工具，中间管理文件队列，右侧调整当前操作的参数。支持拖入 PDF、Ctrl+O 导入、Ctrl 多选、Delete 移除、Ctrl+Enter 开始、Esc 取消；合并时可拖动行或用上下按钮调整顺序。

拆分选项仅在拆分模式显示；“每 N 页”和“指定页码”独立切换，不会误用隐藏的旧页码。高级选项默认折叠，启用后显示数量。完成后在底部显示大小对比并启用“打开结果”，不再弹出成功提示。上次输出目录、压缩档位、目标大小及灰度设置会保存在日志目录旁的 `settings.json`。

- 压缩：支持多个文件逐个压缩。
- 合并：按列表顺序合并，上移/下移调整顺序；可选择合并后压缩。
- 拆分：每 N 页一份，或输入 `1-3,4-6,7` 这样的范围；可选择拆分后压缩。批量文件使用同一拆分规则。
- 无损只清理冗余对象并压缩数据流。轻度、标准、强力、极限使用 Ghostscript 10.08.0 的 pdfwrite 深度重写，彩色/灰度图片分别降至 240 / 150 / 96 / 72 DPI，质量档位依次降低。强制重新编码已有 JPEG/JPX，避免大图片直接透传；同时处理重复图片、字体压缩及子集化。通常保留文字搜索能力，极少数特殊内容可能被引擎转换。
- 勾选“尽量压到每份”并输入 `1` MB：从 150 DPI 开始逐档尝试，直到达到目标或到达最低 48 DPI；每次从同一源文件重新处理，避免连续叠加有损编码。合并时目标作用于合并结果；拆分及批量压缩时目标作用于每一份输出。
- “转为灰度”可减少彩色扫描件体积，会丢失颜色。勾选后会执行灰度转换，不再以彩色原文件作为回退结果。
- “目标未达成时允许整页转为图片”默认关闭。仅启用目标大小并勾选此项时，才在普通深度压缩失败后尝试整页重建；会失去文字搜索、复制、交互表单和链接。只需要观看扫描件内容、可接受低清晰度时可选。
- 达不到目标大小时仍输出尝试中最小的有效结果，并明确提示未达标。不能保证任意百兆 PDF 都能压到 1 MB，页数、图片噪声及可接受清晰度都会影响结果。
- 压缩比例由内容决定，无法保证固定百分比。默认比较原文件、无损和有损结果并保留最小版本；要求转灰度时会保留已转灰度的版本。
- 每次在输出目录建立独立文件夹，不覆盖原文件或旧结果。失败时提示已完成文件数量和目录。
- 不支持需要密码才能打开的 PDF。拆分/合并主要保留页面内容，不保证保留书签、附件、文档级表单关联；处理签名文件会使原数字签名失效，请保留原件。

## 调试与取消

PDF 运算在独立进程中执行，窗口显示当前阶段和累计耗时。可点击“取消处理”，关闭窗口也会终止当前任务。取消后可能保留部分结果和 `.work_` 临时目录，原文件保持不变。

点击左侧“调试日志”可查看日志。Windows 路径为 `%LOCALAPPDATA%\PDF简作\logs`，Mac 路径为 `~/Library/Application Support/PDF简作/logs`：

- `ui.log`：操作参数、界面异常、取消操作、子进程异常退出代码。
- `worker.log`：文件路径、页数、压缩阶段、输入输出大小、耗时和完整异常堆栈。单个日志最多 5 MB，保留 3 个历史备份。
- `worker-fault.log`：原生异常及运行期间每 60 秒的调用栈，用于定位长时间停留的步骤。

日志只保存在本机，包含文件路径。反馈问题时可提供这些日志。新版使用磁盘临时文件比较输出大小，避免在内存中同时保留多个完整 PDF，并减少高成本的数据流比较。

开发自检：`dist\PDF简作.exe --self-check 自检输出目录` 会隐藏窗口，生成一个测试 PDF，通过实际界面流程启动工作进程并执行压缩，写入 `selfcheck.json` 和日志。它只处理合成测试文件。

压缩实现参考 [Ghostscript pdfwrite 参数](https://ghostscript.readthedocs.io/en/gs10.08.0/VectorDevices.html) 和 [Ghostscript DLL API](https://ghostscript.readthedocs.io/en/gs10.08.0/API.html)。Ghostscript DLL 在同一个可终止的工作进程中运行，取消时不会遗留独立的压缩子进程。

`python benchmark_compression.py` 可复现带纸张噪声背景的 10 页合成扫描件测试。输入使用未压缩图片流，超过 100 MiB；结果写入 `compression_benchmark.json`。这是特定合成样本的结果，不代表所有真实 PDF 的压缩率。

## 可选：打包为 Windows exe

在项目目录运行：

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File build.ps1
```

结果位于 `dist\PDF简作.exe`，包含 Ghostscript 引擎，用户无需另外安装。打包脚本会自动提取引擎，不运行系统安装程序。

Ghostscript 来自 [Artifex 官方 10.08.0 发布](https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/tag/gs10080)，使用 AGPLv3，许可随程序打包。源码见 [GhostPDL](https://github.com/ArtifexSoftware/ghostpdl/tree/gs10080)。PyMuPDF 亦提供 AGPL/商业许可，分发时请遵守相应许可。
