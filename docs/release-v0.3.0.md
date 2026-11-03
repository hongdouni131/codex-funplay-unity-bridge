# Codex-Funplay Bridge v0.3.0

本版将此前本地开发的UI Agent v2扩展纳入Windows安装器，包含22个自有MCP工具：4通用、5 v1 UI Agent、13 v2 UI Agent。

## 新增能力

- 只读Sprite导入审计与精确查询，支持Single/Multiple子Sprite及字符串local file ID。
- 本机HTML候选页：中文用途与提示、推荐与风险原因、并排比较、Simple/Sliced目标尺寸预览、Spec节点映射和写入范围。
- Unity原生布局测量；提交后重新核对素材身份与依赖，只合并允许的Sprite字段。
- v2校验、完整计划、授权后单次生成新Prefab、保存后契约审计。
- 生成结果诊断和受限Spec修订；旧Prefab不原地修改，新Spec仍需Validate/Prepare/授权后生成到新路径。

## 安装与升级

分发附件仅需 `Codex-Funplay-Bridge-Setup.exe` 和对应 `.exe.sha256`。先校验SHA256，再运行向导。目标电脑仍需通过Windows `py`启动器提供 **Python 3.11** 和依赖下载网络；本版不增加多Python版本发现。安装器内嵌Bridge wheel与部署模板，不包含Unity、Funplay或UI Agent Package。

升级已有项目时先记录URL、名称与超时，备份配置；选择同一Unity根目录，验证并允许替换Bridge管理文件。部署写入项目级虚拟环境与tools配置，不自动修改Codex全局配置。随后重载对应MCP服务，检查`unity_bridge_info.bridge_version == "0.3.0"`、八项capability及22工具；详见[部署说明](setup.md)。重载会丢弃旧进程计划/候选会话，应重新Prepare，未知写入不自动重放。

## 与Package的关系

[UI Agent Tools](https://github.com/hongdouni131/ui-agent-tools) `com.hongdouni.ui-agent-tools` `0.1.0`单独安装，首发为MIT许可Package源码、测试和三项Sample。Package安装不会自动注册MCP，Bridge部署也不会安装Package。UI Agent配对基线为Unity 2022.3.62f3c1；多Unity版本与实体硬件未纳入本轮。

没有Package时仍可用四个通用Funplay工具；依赖Package的API调用返回不可用。`unity_list_tools`返回Funplay原生工具，22工具是Bridge MCP自有注册，两者不同。候选页提交是素材选择，不是生成授权。

## 验证与限制

本轮结果、文件大小与SHA256见[发布验证](release-validation.md)。此前完整单元回归160/160，安装器自检已验证临时项目部署及安装后stdio MCP；随后使用同一EXE内嵌wheel/模板升级真实验证项目，独立安装版及完整重启后的常驻会话均完成只读配对（16节点审计0finding、诊断0issue）。这不是交互向导点击验收或所有项目的生成保证；源码真实生成闭环属于此前独立证据。

安装器未代码签名。MIT许可见仓库[LICENSE](../LICENSE)。旧v0.2.0公开附件保持历史身份，本版不替换旧Tag附件。
