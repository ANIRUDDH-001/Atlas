import os
import re

for root, _, files in os.walk('app'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as fp:
                content = fp.read()
            
            # Replace things like timestamp::date -> DATE(timestamp)
            new_content = re.sub(r'([a-zA-Z0-9_\.]*timestamp)::date', r'DATE(\1)', content)
            
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as fp:
                    fp.write(new_content)
                print(f"Fixed {path}")
