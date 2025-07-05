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
**Status**: 🚫 Excluded from version control (local development only)

Contains detailed guides in Chinese for local development and customization:
- **配置指南** (`configuration_guide.md`) - 详细的配置修改和提示词定制指南
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
Navigate to `zh-CN/` directory (local development) for:
- 系统配置说明
- 提示词定制指南
- 模板库
- 故障排除技巧

## 📖 Available Guides

| Guide | English | Chinese | Description |
|-------|---------|---------|-------------|
| **Configuration Guide** | [📖 View](en-US/configuration_guide.md) | 📖 View (Local) | Complete guide for modifying configurations and prompts |
| **Quick Reference** | [🚀 View](en-US/quick_reference.md) | 🚀 View (Local) | Quick lookup for common modifications |
| **Prompt Templates** | [🎯 View](en-US/prompt_templates.md) | 🎯 View (Local) | Ready-to-use prompt templates |

## 🔧 Key Topics Covered

### Configuration Management
- LLM provider settings (OpenAI, Google, Anthropic)
  - **Google Models**: Full support for Gemini 2.0/2.5 series ⭐ **Currently Configured**
  - **Current Setup**: Using `gemini-2.0-flash` for both deep and quick thinking
- Debate and discussion parameters
- Cache and performance settings
- API configuration and limits

### Agent Customization
- Market Analyst prompts
- Fundamentals Analyst prompts
- News and Social Media Analyst prompts
- Bull/Bear Researcher prompts
- Trader decision prompts
- Reflection system prompts

### Advanced Features
- Multi-language support
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
- 🚫 **Exclude**: `zh-CN/` directory (configured in `.gitignore`)
- ✅ **Include**: This README file for navigation

## 📝 Contributing

When contributing to documentation:

1. **Update English docs** for features that should be shared with the community
2. **Keep Chinese docs local** for development and customization purposes
3. **Maintain consistency** between language versions when possible
4. **Test all examples** before documenting them

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
