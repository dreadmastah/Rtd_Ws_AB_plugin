from pathlib import Path
S=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R7\capture_readonly.py');R=Path(__file__).resolve().parent
s=S.read_text().replace('R7_FULL_PREFIX_ADMISSION_STATUS.json','R8_HISTORY_ADMISSION_BOUNDARY.json')
(R/'capture_readonly.py').write_text(s)
