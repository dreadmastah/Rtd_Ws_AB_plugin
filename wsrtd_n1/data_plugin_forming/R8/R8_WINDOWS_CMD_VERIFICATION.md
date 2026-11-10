# Read-only Windows CMD verification

```cmd
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R8\verify.py
type D:\WSRTD_N1_DATA_PLUGIN_FORMING_R8\R8_FINAL_DISPOSITION.json
```

No test rerun, live dispatch, Broker restart or DLL install occurs. No R8 DLL was rebuilt; R7 remains preserved. Do not invoke capture.py as live execution; writer-custody gate is closed.
