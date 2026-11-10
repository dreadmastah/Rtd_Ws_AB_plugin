# CMD verification

From Windows CMD:

```cmd
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R2\verify.py
certutil -hashfile D:\WSRTD_N1_DATA_PLUGIN_FORMING_R2\artifacts\WSRTD_Data_Forming_R2.dll SHA256
```

Optional isolated regression commands (create only output-root disposable test directories and own harness processes; no Broker or feed connection):

```cmd
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R2\tests\run_tests.py
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R2\independent\test_receiver.py
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R2\independent\test_native.py
```

Rerunning overwrites test receipts and invalidates their manifest entries; preserve delivered evidence before an authorized new run. No install or live startup command is supplied. prepare.py is not a deployment tool. Candidate requires its isolated fixture authority and rejects the original N1 directory.
