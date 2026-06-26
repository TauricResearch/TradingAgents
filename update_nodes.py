import os
import glob
import re

base_dir = os.path.dirname(os.path.abspath(__file__))
directories = [
    os.path.join(base_dir, 'tradingagents', 'agents', 'analysts'),
    os.path.join(base_dir, 'tradingagents', 'agents', 'researchers'),
    os.path.join(base_dir, 'tradingagents', 'agents', 'risk_mgmt'),
]

for d in directories:
    for filepath in glob.glob(os.path.join(d, '*.py')):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Inject imports
        if 'strip_think_tags' not in content:
            content = content.replace(
                'from tradingagents.agents.utils.agent_utils import (',
                'from tradingagents.agents.utils.agent_utils import (\n    strip_think_tags,\n    get_strict_data_instruction,'
            )
            if 'from tradingagents.agents.utils.agent_utils import' not in content:
                content = 'from tradingagents.agents.utils.agent_utils import strip_think_tags, get_strict_data_instruction\n' + content

        # Inject strip_think_tags
        content = re.sub(r'report = result\.content', 'report = strip_think_tags(result.content)', content)
        content = re.sub(r'"bull_history":\s*result\.content', '"bull_history": strip_think_tags(result.content)', content)
        content = re.sub(r'"bear_history":\s*result\.content', '"bear_history": strip_think_tags(result.content)', content)
        content = re.sub(r'"aggressive_history":\s*result\.content', '"aggressive_history": strip_think_tags(result.content)', content)
        content = re.sub(r'"conservative_history":\s*result\.content', '"conservative_history": strip_think_tags(result.content)', content)
        content = re.sub(r'"neutral_history":\s*result\.content', '"neutral_history": strip_think_tags(result.content)', content)

        # Inject get_strict_data_instruction for analysts only
        if 'analysts' in d:
            content = content.replace('+ get_language_instruction()', '+ get_strict_data_instruction() + get_language_instruction()')

        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f'Updated {filepath}')
