# Windows CMD verification

Read-only artifact integrity (does not install or run the feed):

```cmd
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R5\verify.py
certutil -hashfile D:\WSRTD_N1_DATA_PLUGIN_FORMING_R5\artifacts\WSRTD_Data_Forming_R5.dll SHA256
type D:\WSRTD_N1_DATA_PLUGIN_FORMING_R5\R5_FINAL_DISPOSITION.json
```

Expected DLL SHA-256: 98fdf9d713e9200294ad5c111ed459de96d5b416e30a49726347b7f506b2f84b

Do not copy into AmiBroker Plugins. Do not launch this candidate against protected ports or installed SQLite. Test receipts already exist; verification does not rerun tests or rewrite them.
