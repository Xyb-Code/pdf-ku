# 独立桌面发行版

最终用户只接收 Windows 的 `PDF简作.exe` 或 Mac 的 `.dmg`，无需 Python、pip、Homebrew、Ghostscript 或在线下载组件。以下步骤仅供开发/构建机器使用。

## 当前交付状态

- Windows：可在当前 Windows 环境构建、执行自检并交付 exe。
- macOS：已准备跨平台代码、原生引擎编译、App/DMG 构建及自检流程。必须在 Mac 或 GitHub macOS runner 执行；尚未在当前 Windows 环境生成/验证 Mac 安装包。
- 不把脚本、源码或重命名的 Windows 文件称为 Mac App。

## 无需给用户配置环境

Windows 包内包含 Python/Tk、界面资源、拖放组件、PDF 库及 Ghostscript DLL。Mac App 包内包含对应架构的全部运行时、拖放组件及 Ghostscript dylib，资源通过 App 内相对路径读取；用户偏好和日志写入用户目录，程序不写自身 App 包。

Mac 支持两种原生构建：Apple Silicon `arm64` 和 Intel `x86_64`，构建目标 macOS 13 或以上。分别使用两台对应架构的 runner，避免要求用户安装 Rosetta。最低版本和完整功能仍需原生构建/测试后确认。

## 开发者本地构建

Windows：安装构建依赖并运行项目根目录 `build.ps1`。

Mac（开发机器需 Python 3.12、Tk 和 Xcode 命令行工具）：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python packaging/build_macos.py
```

Mac 构建脚本下载并核验官方 Ghostscript 10.08.0 源码 SHA-256，使用随源码提供的第三方库编译。若生成库引用非系统的外部运行库则直接失败，避免把 Homebrew 路径带给最终用户。生成 App 后从项目外目录、清除 Python/Ghostscript 环境变量运行实际压缩与拖放初始化自检，成功才生成 DMG。

## 自动构建

项目仓库为 [Xyb-Code/pdf-ku](https://github.com/Xyb-Code/pdf-ku)，配置见 `.github/workflows/build-desktop.yml`。在 main 分支提交程序或打包配置后自动构建，也可以手动运行 `Build standalone desktop apps`。不自动发布 Release，也不把本地 PDF 上传到 GitHub。它分别生成 Windows、Mac Apple Silicon、Mac Intel 三份制品，并附带校验和及运行时自检报告。构建状态和制品位于仓库的 Actions 页面。

## 正式 Mac 分发

没有 Developer ID 签名和 Apple 公证的安装包会标记 `-unnotarized`，不能承诺首次下载后无系统拦截。正式分发时由构建负责人提供签名身份和已配置的 notarytool 凭证，不让最终用户操作命令行或关闭系统安全设置：

```sh
.venv/bin/python packaging/build_macos.py \
  --sign-identity 'Developer ID Application: YOUR NAME (TEAMID)' \
  --notary-profile 'YOUR_NOTARYTOOL_PROFILE'
```

脚本会签名 App、提交公证并附加票据，再创建、签名、公证及附加 DMG 票据。当前 GitHub workflow 默认构建内部测试用未公证版本；正式分发的签名凭证只应配置在受控的构建环境中。
