from pathlib import Path
import difflib
root=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R5')
a=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3\native\plugin.cpp').read_text()
b=(root/'native/plugin.cpp').read_text()
print(''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True))))
