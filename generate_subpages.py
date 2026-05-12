"""
generate_subpages.py
Reads the already-built index.html (or Sunwave_Dashboard.html) and generates
one sub-page per dashboard section, then rewrites index.html as a redirect.

Run from the repo root:  python generate_subpages.py
"""
import json, os

SUB_NAV = [
    ('billing',       'Billing',        'billing'),
    ('census',        'Census',         'census'),
    ('marketing',     'Marketing',      'marketing'),
    ('opportunities', 'Opportunities',  'opportunities'),
    ('referral',      'Referrals',      'referral'),
    ('crmtask',       'CRM Tasks',      'crmtask'),
    ('ur',            'UR',             'ur'),
    ('clinical',      'Clinical',       'clinical'),
    ('operations',    'Operations',     'operations'),
    ('fieldexplorer', 'Field Explorer', 'fieldexplorer'),
]

def make_nav(active_id):
    parts = []
    for sid, lbl, folder in SUB_NAV:
        cls = 'tab-btn active' if sid == active_id else 'tab-btn'
        parts.append(f'<a href="../{folder}/" class="{cls}">{lbl}</a>')
    parts.append('<a href="../crm/" class="tab-btn">CRM</a>')
    return ''.join(parts)

# Read source from Sunwave_Dashboard.html (full combined, never overwritten to redirect)
src_file = 'Sunwave_Dashboard.html' if os.path.exists('Sunwave_Dashboard.html') else 'index.html'
with open(src_file, 'r', encoding='utf-8') as f:
    base = f.read()

print(f'Source: {src_file}  ({len(base)//1024} KB)')

TAIL = '</body>\n</html>'
if TAIL not in base:
    # handle \r\n endings
    TAIL = '</body>\r\n</html>'
if TAIL not in base:
    raise RuntimeError('Could not find </body></html> in source file')

for sid, lbl, folder in SUB_NAV:
    nav = make_nav(sid)
    inject = (
        f'<script>(function(){{'
        f'var bar=document.getElementById("tabBar");'
        f'if(bar)bar.innerHTML={json.dumps(nav)};'
        f'if(typeof showPage==="function")showPage("{sid}");'
        f'}})();</script>\n'
        f'</body>\n</html>'
    )
    content = base.replace(TAIL, inject, 1)
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, 'index.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  {folder}/index.html  ({os.path.getsize(out)//1024} KB)')

redirect = (
    '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
    '<meta charset="UTF-8">\n'
    '<meta http-equiv="refresh" content="0;url=billing/">\n'
    '<title>Sunwave Dashboard</title>\n'
    '</head>\n<body>\n'
    '<p>Redirecting to <a href="billing/">Sunwave Dashboard</a>…</p>\n'
    '</body>\n</html>\n'
)
with open('index.html', 'w', encoding='utf-8') as f:
    f.write(redirect)
print('  index.html  (redirect → billing/)')
print('Done.')
