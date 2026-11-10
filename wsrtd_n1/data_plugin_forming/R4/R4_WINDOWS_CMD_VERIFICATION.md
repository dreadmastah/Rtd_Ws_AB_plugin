# CMD verification

```cmd
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R4\verify.py
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3\verify.py
```

Optionalnewoffline test (creates onlyR4disposableledgers/databases; overwritesR4testreceipt, requiringnewmanifest):

```cmd
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R4\tests\test_r4.py
```

No liveproducer/receiverconnect/install/start command is included because those gates remainblocked. Do not rerun prepare.py overaccepted artifacts.
