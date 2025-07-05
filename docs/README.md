# TradingAgents Documentation

## 📚 Documentation Structure

This documentation is organized into language-specific directories to serve different user communities:

### 🇺🇸 English Documentation (`en-US/`)
**Status**: ✅ Included in version control

Contains comprehensive guides for English-speaking users:
- **Configuration Guide** (`configuration_guide.md`) - Detailed instructions for modifying system configurations and agent prompts
- **Quick Reference** (`quick_reference.md`) - Quick lookup card for common modifications and file locations
- **Prompt Templates** (`prompt_templates.md`) - Ready-to-use prompt templates for various agent roles

### 🇨🇳 Chinese Documentation (`zh-CN/`)
**Status**: ✅ Included in version control

Contains comprehensive guides in Chinese for Chinese-speaking users:
- **主文档** (`README.md`) - 中文版系统概览和快速开始
- **配置指南** (`configuration_guide.md`) - 详细的配置修改和新功能设置指南
- **架构指南** (`architecture_guide.md`) - 系统架构和技术实现详解
- **快速开始指南** (`quick_start_guide.md`) - 5分钟快速设置和使用教程
- **快速参考** (`quick_reference.md`) - 新手友好的快速查找卡片
- **提示词模板库** (`prompt_templates.md`) - 可直接使用的提示词模板

## 🎯 Quick Start

### For English Users
Navigate to [`en-US/`](en-US/) directory for:
- System configuration instructions
- Prompt customization guides
- Template libraries
- Troubleshooting tips

### For Chinese Users
Navigate to [`zh-CN/`](zh-CN/) directory for:
- 系统配置说明
- 中国A股市场功能
- 百炼(DashScope)集成指南
- 数据库配置说明
- 提示词定制指南
- 架构技术文档
- 故障排除技巧

## 📖 Available Guides

| Guide | English | Chinese | Description |
|-------|---------|---------|-------------|
| **Main Documentation** | [📖 View](en-US/) | [📖 查看](zh-CN/README.md) | System overview and quick start |
| **Configuration Guide** | [📖 View](en-US/configuration_guide.md) | [📖 查看](zh-CN/configuration_guide.md) | Complete guide for modifying configurations and new features |
| **Architecture Guide** | [🏗️ View](en-US/architecture_guide.md) | [🏗️ 查看](zh-CN/architecture_guide.md) | System architecture and technical implementation |
| **Quick Start Guide** | [🚀 View](en-US/quick_start_guide.md) | [🚀 查看](zh-CN/quick_start_guide.md) | 5-minute setup and usage tutorial |
| **Quick Reference** | [📋 View](en-US/quick_reference.md) | [📋 查看](zh-CN/quick_reference.md) | Quick lookup for common modifications |
| **Prompt Templates** | [🎯 View](en-US/prompt_templates.md) | [🎯 查看](zh-CN/prompt_templates.md) | Ready-to-use prompt templates |

## 🔧 Key Topics Covered

### Configuration Management
- LLM provider settings (DashScope, OpenAI, Google, Anthropic)
  - **DashScope (Alibaba Cloud)**: Full support for Qwen model series ⭐ **Recommended for Chinese users**
  - **Current Setup**: DashScope as primary option with intelligent fallback
- Market selection and data sources
  - **US Stock Market**: Yahoo Finance integration
  - **China A-Share Market**: TongDaXin API integration ⭐ **New Feature**
- Database and caching systems
  - **MongoDB**: Persistent data storage
  - **Redis**: High-performance caching
  - **Intelligent Cache**: Automatic fallback mechanisms
- Debate and discussion parameters
- API configuration and limits

### Agent Customization
- Market Analyst prompts
- Fundamentals Analyst prompts
- News and Social Media Analyst prompts
- Bull/Bear Researcher prompts
- Trader decision prompts
- Reflection system prompts

### Advanced Features
- **Multi-market support**: US stocks and China A-shares
- **Database integration**: MongoDB and Redis for enterprise deployment
- **Intelligent caching**: Adaptive cache management with fallback
- **Multi-LLM support**: DashScope, OpenAI, Google, Anthropic
- **TongDaXin integration**: Real-time A-share data access
- Risk management templates
- Performance optimization
- Custom prompt creation
- Environment-specific configurations

## 🚀 Getting Started

1. **Choose Your Language**: Select the appropriate documentation directory
2. **Start with Quick Reference**: Get familiar with key file locations
3. **Read Configuration Guide**: Understand the system architecture
4. **Use Prompt Templates**: Copy and customize templates for your needs
5. **Test Changes**: Always test modifications in a safe environment

## 🛠️ Development Workflow

### For Contributors
1. **English Documentation**: 
   - Modify files in `en-US/` directory
   - Commit changes to version control
   - These will be available to all users

2. **Chinese Documentation**: 
   - Modify files in `zh-CN/` directory
   - Keep changes local (not committed)
   - Use for local development and testing

### Version Control Policy
- ✅ **Include**: `en-US/` directory and all English documentation
- ✅ **Include**: `zh-CN/` directory and all Chinese documentation
- ✅ **Include**: This README file for navigation
- 🎯 **Rationale**: Both language versions provide value to the global community

## 📝 Contributing

When contributing to documentation:

1. **Update English docs** for features that should be shared with the international community
2. **Update Chinese docs** for features that benefit Chinese-speaking users
3. **Maintain consistency** between language versions when possible
4. **Test all examples** before documenting them
5. **Consider localization** - some features may be more relevant to specific regions

## 🔗 Related Resources

- **Project Repository**: Main TradingAgents codebase
- **Configuration Files**: `tradingagents/default_config.py`, `main.py`
- **Agent Files**: `tradingagents/agents/` directory
- **Test Files**: `tests/` directory (local only)

## 📞 Support

For questions about:
- **Configuration**: See Configuration Guide
- **Prompts**: See Prompt Templates
- **Quick Help**: See Quick Reference
- **Issues**: Submit to project repository

---

💡 **Note**: This documentation structure allows for both community sharing (English) and local customization (Chinese) while maintaining clean version control.
