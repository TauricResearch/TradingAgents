#!/usr/bin/env python3
"""
TradingAgents 全量合并脚本
将中文版本的所有新功能合并到主项目中
"""

import os
import shutil
from pathlib import Path
import difflib

class FullMerger:
    """全量合并器"""
    
    def __init__(self, source_dir="TradingAgentsCN", target_dir="."):
        self.source_dir = Path(source_dir)
        self.target_dir = Path(target_dir)
        
        # 需要特殊处理的冲突文件
        self.conflict_files = [
            "tradingagents/dataflows/cache_manager.py",
            "tradingagents/dataflows/optimized_us_data.py", 
            "tradingagents/dataflows/interface.py",
            "tradingagents/default_config.py"
        ]
        
        # 要忽略的文件和目录
        self.ignore_patterns = [
            "__pycache__",
            "*.pyc",
            ".git",
            "test_env",
            "env",
            "data_cache",
            "*.csv",
            "eval_results",
            "results",
            "finnhub_data",
            "enhanced_analysis_reports"
        ]
    
    def should_ignore(self, path: Path) -> bool:
        """检查是否应该忽略此路径"""
        path_str = str(path)
        for pattern in self.ignore_patterns:
            if pattern in path_str:
                return True
        return False
    
    def merge_new_files(self) -> int:
        """合并新增文件"""
        print("📄 合并新增文件...")
        
        source_tradingagents = self.source_dir / "tradingagents"
        target_tradingagents = self.target_dir / "tradingagents"
        
        if not source_tradingagents.exists():
            print(f"❌ 源目录不存在: {source_tradingagents}")
            return 0
        
        merged_count = 0
        
        # 遍历源目录中的所有文件
        for source_file in source_tradingagents.rglob("*"):
            if source_file.is_file() and not self.should_ignore(source_file):
                # 计算相对路径
                rel_path = source_file.relative_to(self.source_dir)
                target_file = self.target_dir / rel_path
                
                # 检查是否为新文件
                if not target_file.exists():
                    # 创建目标目录
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # 复制文件
                    shutil.copy2(source_file, target_file)
                    print(f"  ✅ 新增: {rel_path}")
                    merged_count += 1
        
        return merged_count
    
    def handle_conflict_files(self) -> int:
        """处理冲突文件"""
        print("\n⚠️ 处理冲突文件...")
        
        handled_count = 0
        
        for conflict_file in self.conflict_files:
            source_file = self.source_dir / conflict_file
            target_file = self.target_dir / conflict_file
            
            if source_file.exists() and target_file.exists():
                print(f"  🔄 处理冲突: {conflict_file}")
                
                # 创建备份
                backup_file = target_file.with_suffix(target_file.suffix + ".backup")
                shutil.copy2(target_file, backup_file)
                print(f"    💾 备份创建: {backup_file.name}")
                
                # 生成差异报告
                diff_file = target_file.with_suffix(target_file.suffix + ".diff")
                self._generate_diff_report(source_file, target_file, diff_file)
                print(f"    📋 差异报告: {diff_file.name}")
                
                # 对于某些文件，尝试智能合并
                if self._smart_merge(source_file, target_file, conflict_file):
                    print(f"    ✅ 智能合并成功")
                else:
                    print(f"    ⚠️ 需要手动合并")
                
                handled_count += 1
            elif source_file.exists():
                # 源文件存在但目标文件不存在，直接复制
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target_file)
                print(f"  ✅ 直接复制: {conflict_file}")
                handled_count += 1
        
        return handled_count
    
    def _generate_diff_report(self, source_file: Path, target_file: Path, diff_file: Path):
        """生成差异报告"""
        try:
            with open(source_file, 'r', encoding='utf-8') as f:
                source_lines = f.readlines()
            with open(target_file, 'r', encoding='utf-8') as f:
                target_lines = f.readlines()
            
            diff = difflib.unified_diff(
                target_lines, source_lines,
                fromfile=f"current/{target_file.name}",
                tofile=f"chinese_version/{source_file.name}",
                lineterm=''
            )
            
            with open(diff_file, 'w', encoding='utf-8') as f:
                f.write(f"# 文件差异报告\n")
                f.write(f"# 当前文件: {target_file}\n")
                f.write(f"# 中文版文件: {source_file}\n")
                f.write(f"# 生成时间: {os.popen('date /t').read().strip()}\n\n")
                f.writelines(diff)
                
        except Exception as e:
            print(f"    ❌ 生成差异报告失败: {e}")
    
    def _smart_merge(self, source_file: Path, target_file: Path, conflict_file: str) -> bool:
        """智能合并某些文件"""
        try:
            if "default_config.py" in conflict_file:
                return self._merge_default_config(source_file, target_file)
            elif "cache_manager.py" in conflict_file:
                # cache_manager.py 已经是英文版本，保持当前版本
                print(f"    📝 保持当前英文版本的 cache_manager.py")
                return True
            elif "optimized_us_data.py" in conflict_file:
                # optimized_us_data.py 已经是英文版本，保持当前版本
                print(f"    📝 保持当前英文版本的 optimized_us_data.py")
                return True
            else:
                return False
        except Exception as e:
            print(f"    ❌ 智能合并失败: {e}")
            return False
    
    def _merge_default_config(self, source_file: Path, target_file: Path) -> bool:
        """合并默认配置文件"""
        try:
            # 读取两个文件
            with open(source_file, 'r', encoding='utf-8') as f:
                source_content = f.read()
            with open(target_file, 'r', encoding='utf-8') as f:
                target_content = f.read()
            
            # 简单策略：如果中文版本有新的配置项，添加到目标文件
            # 这里可以根据需要实现更复杂的合并逻辑
            
            # 检查中文版本是否有新的配置项
            if "data_cache_dir" in source_content and "data_cache_dir" not in target_content:
                # 添加缓存目录配置
                lines = target_content.split('\n')
                for i, line in enumerate(lines):
                    if '"data_dir":' in line:
                        # 在data_dir后面添加data_cache_dir
                        cache_dir_line = '    "data_cache_dir": os.path.join('
                        cache_dir_line += '\n        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),'
                        cache_dir_line += '\n        "dataflows/data_cache",'
                        cache_dir_line += '\n    ),'
                        lines.insert(i + 1, cache_dir_line)
                        break
                
                # 写回文件
                with open(target_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))
                
                print(f"    ✅ 添加了 data_cache_dir 配置")
                return True
            
            return True
            
        except Exception as e:
            print(f"    ❌ 合并默认配置失败: {e}")
            return False
    
    def update_dependencies(self) -> bool:
        """更新依赖项"""
        print("\n📦 更新依赖项...")
        
        source_pyproject = self.source_dir / "pyproject.toml"
        target_pyproject = self.target_dir / "pyproject.toml"
        
        if not source_pyproject.exists():
            print("  ⚠️ 源项目没有 pyproject.toml")
            return False
        
        try:
            # 读取源文件的依赖项
            with open(source_pyproject, 'r', encoding='utf-8') as f:
                source_content = f.read()
            
            # 提取新的依赖项
            new_deps = []
            if 'pymongo' in source_content:
                new_deps.append('"pymongo>=4.0.0"')
            if 'beautifulsoup4' in source_content:
                new_deps.append('"beautifulsoup4>=4.9.0"')
            if 'dashscope' in source_content:
                new_deps.append('"dashscope>=1.0.0"')
            
            if new_deps:
                # 读取目标文件
                with open(target_pyproject, 'r', encoding='utf-8') as f:
                    target_lines = f.readlines()
                
                # 找到dependencies部分并添加新依赖
                in_dependencies = False
                for i, line in enumerate(target_lines):
                    if 'dependencies = [' in line:
                        in_dependencies = True
                    elif in_dependencies and ']' in line:
                        # 在]前添加新依赖
                        for dep in new_deps:
                            target_lines.insert(i, f'    {dep},\n')
                            i += 1
                        break
                
                # 写回文件
                with open(target_pyproject, 'w', encoding='utf-8') as f:
                    f.writelines(target_lines)
                
                print(f"  ✅ 添加了新依赖: {', '.join(new_deps)}")
                return True
            
            return True
            
        except Exception as e:
            print(f"  ❌ 更新依赖项失败: {e}")
            return False
    
    def create_merge_summary(self, new_files: int, conflict_files: int) -> str:
        """创建合并摘要"""
        summary_file = "MERGE_SUMMARY.md"
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("# TradingAgents 中文版功能全量合并摘要\n\n")
            f.write(f"合并时间: {os.popen('date /t').read().strip()}\n")
            f.write(f"合并分支: full-merge-chinese-features\n\n")
            
            f.write("## 📊 合并统计\n\n")
            f.write(f"- 新增文件: {new_files} 个\n")
            f.write(f"- 处理冲突文件: {conflict_files} 个\n\n")
            
            f.write("## 🆕 主要新增功能\n\n")
            f.write("### 中国市场数据支持\n")
            f.write("- `chinese_finance_utils.py` - 中国财经数据聚合工具\n")
            f.write("- `tdx_utils.py` - 通达信API数据获取\n")
            f.write("- `optimized_china_data.py` - 优化的A股数据提供器\n")
            f.write("- `china_market_analyst.py` - 中国市场分析师\n\n")
            
            f.write("### 数据库集成\n")
            f.write("- `database_config.py` - 数据库配置管理\n")
            f.write("- `database_manager.py` - 统一数据库管理器\n")
            f.write("- `mongodb_storage.py` - MongoDB存储支持\n")
            f.write("- `db_cache_manager.py` - 数据库缓存管理\n\n")
            
            f.write("### 高级缓存系统\n")
            f.write("- `adaptive_cache.py` - 自适应缓存策略\n")
            f.write("- `integrated_cache.py` - 集成缓存管理\n\n")
            
            f.write("### LLM适配器扩展\n")
            f.write("- `llm_adapters/` - LLM适配器框架\n")
            f.write("- `dashscope_adapter.py` - 阿里云DashScope支持\n\n")
            
            f.write("### API和服务层\n")
            f.write("- `api/` - 统一API接口\n")
            f.write("- `stock_data_service.py` - 股票数据服务\n")
            f.write("- `realtime_news_utils.py` - 实时新闻工具\n\n")
            
            f.write("## ⚠️ 需要注意的变更\n\n")
            f.write("### 新增依赖项\n")
            f.write("- `pymongo` - MongoDB数据库支持\n")
            f.write("- `beautifulsoup4` - 网页数据解析\n")
            f.write("- `dashscope` - 阿里云LLM支持 (可选)\n\n")
            
            f.write("### 配置文件变更\n")
            f.write("- 添加了数据库相关配置\n")
            f.write("- 扩展了缓存配置选项\n")
            f.write("- 新增了中国市场数据源配置\n\n")
            
            f.write("## 🧪 测试建议\n\n")
            f.write("1. **基础功能测试**: 确保原有功能正常工作\n")
            f.write("2. **新功能测试**: 测试中国市场数据获取\n")
            f.write("3. **缓存系统测试**: 验证缓存性能和稳定性\n")
            f.write("4. **数据库集成测试**: 测试MongoDB连接和存储\n")
            f.write("5. **LLM适配器测试**: 验证多LLM支持\n\n")
            
            f.write("## 📝 后续工作\n\n")
            f.write("1. 更新文档以反映新功能\n")
            f.write("2. 添加新功能的使用示例\n")
            f.write("3. 完善测试覆盖率\n")
            f.write("4. 优化性能和稳定性\n\n")
            
            f.write("## 🔄 如果需要分批PR\n\n")
            f.write("如果原项目认为全量合并过于复杂，可以按以下顺序分批提交：\n\n")
            f.write("1. **基础设施**: config/, database相关文件\n")
            f.write("2. **中国市场数据**: chinese_finance_utils.py, tdx_utils.py等\n")
            f.write("3. **高级缓存**: adaptive_cache.py, integrated_cache.py等\n")
            f.write("4. **LLM适配器**: llm_adapters/目录\n")
            f.write("5. **API服务**: api/目录和相关服务文件\n")
        
        return summary_file
    
    def run_full_merge(self) -> bool:
        """执行全量合并"""
        print("🚀 开始全量合并中文版功能...")
        print("=" * 50)
        
        # 检查源目录
        if not self.source_dir.exists():
            print(f"❌ 源目录不存在: {self.source_dir}")
            return False
        
        try:
            # 1. 合并新增文件
            new_files = self.merge_new_files()
            
            # 2. 处理冲突文件
            conflict_files = self.handle_conflict_files()
            
            # 3. 更新依赖项
            self.update_dependencies()
            
            # 4. 创建合并摘要
            summary_file = self.create_merge_summary(new_files, conflict_files)
            
            print(f"\n✅ 全量合并完成!")
            print(f"📊 合并统计:")
            print(f"   新增文件: {new_files} 个")
            print(f"   处理冲突文件: {conflict_files} 个")
            print(f"📋 合并摘要: {summary_file}")
            
            return True
            
        except Exception as e:
            print(f"❌ 合并过程中出现错误: {e}")
            return False

def main():
    """主函数"""
    merger = FullMerger()
    
    if merger.run_full_merge():
        print(f"\n🎯 下一步操作:")
        print("1. 检查合并结果和差异文件")
        print("2. 手动处理需要合并的冲突文件")
        print("3. 运行测试确保功能正常")
        print("4. 提交更改: git add . && git commit -m 'feat: merge Chinese version features'")
        print("5. 推送分支: git push origin full-merge-chinese-features")
        print("6. 创建PR到原项目")
    else:
        print(f"\n❌ 合并失败，请检查错误信息")

if __name__ == "__main__":
    main()
