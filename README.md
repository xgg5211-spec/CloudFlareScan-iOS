# CloudFlareScan iOS (TrollStore 巨魔专版)

本项目是基于 `xiaolin-007/CloudFlareScan` 针对 iOS 系统（结合 TrollStore 巨魔商店）进行深度适配与打包的版本。

## 🌟 iOS 适配特性
1. **TCP 并发优化**：解决 iOS 系统对 Socket 句柄限制（防止高并发导致进程被系统闪退强杀）。
2. **一键复制到剪贴板**：方便直接在 iPhone 上把测速最优 IP 粘贴到 Shadowrocket / Loon / Surge / Quantumult X 中。
3. **触控与高分屏适配**：布局重新针对 iPhone 竖屏进行对齐与优化。

## 📦 如何使用 GitHub Actions 自动编译生成 .ipa 安装包：
1. 将本项目代码上传到你的 GitHub 仓库（或直接 Fork 仓库）。
2. 点击仓库顶部的 **Actions** 选项卡。
3. 在左侧选择 **Build iOS IPA for TrollStore** 工作流，点击右上角的 **Run workflow**。
4. 等待 15~20 分钟（GitHub 免费的 macOS 虚拟机正在为你编译 IPA）。
5. 编译完成后，在 Actions 页面底部的 **Artifacts** 区域直接下载 `CloudFlareScan_TrollStore_IPA`。
6. 解压得到 `.ipa` 文件，使用 **TrollStore（巨魔商店）** 导入安装即可永不掉签！
