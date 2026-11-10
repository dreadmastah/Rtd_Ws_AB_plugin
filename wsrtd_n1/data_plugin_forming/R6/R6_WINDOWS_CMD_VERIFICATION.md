# Read-only verification from Windows CMD

```cmd
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R6\verify.py
certutil -hashfile D:\WSRTD_N1_DATA_PLUGIN_FORMING_R6\artifacts\WSRTD_Data_Forming_R6.dll SHA256
type D:\WSRTD_N1_DATA_PLUGIN_FORMING_R6\R6_FINAL_DISPOSITION.json
```

Expected DLL SHA-256: b47b74935d90b383573234f595b27c94cb909812780eef45f15c4a884b5ae0e9

These commands do not launch a producer, install a DLL, run AmiBroker or rewrite test receipts. Do not install the fixture DLL into the running host.
