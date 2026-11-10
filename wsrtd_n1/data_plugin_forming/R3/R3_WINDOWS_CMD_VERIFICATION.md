# Windows CMD

```cmd
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3\verify.py
certutil -hashfile D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3\artifacts\WSRTD_Data_Forming_R3.dll SHA256
```

Optionalnewisolatedregression (rewrites R3receipts; invalidatesmanifest, preservesR2/production):

```cmd
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3\tests\test_durable.py
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3\tests\test_pipeline.py
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3\tests\test_native_inherited.py
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3\tests\test_integrated_scale.py
```

Noinstallation/livecommands. prepare.py/stage_native.py are one-time derivation helpers; do not rerun over finalsource.
