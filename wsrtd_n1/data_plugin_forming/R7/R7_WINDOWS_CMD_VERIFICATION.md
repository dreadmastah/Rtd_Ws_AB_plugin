# Windows CMD read-only verification

```cmd
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R7\verify.py
certutil -hashfile D:\WSRTD_N1_DATA_PLUGIN_FORMING_R7\artifacts\WSRTD_Data_Forming_R7.dll SHA256
type D:\WSRTD_N1_DATA_PLUGIN_FORMING_R7\R7_FINAL_DISPOSITION.json
```

Expected DLL hash: ad0f27ece55ddaaea8bbfc42a85554d99b872cf11382a61e79775d67647f36d6

These commands do not rerun tests, install plugins, launch AmiBroker, alter sources or access Binance feeds. Test TLS credentials are disposable and excluded from the manifest. All live approval fields remain unbound.
