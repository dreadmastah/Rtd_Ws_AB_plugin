from pathlib import Path
p=Path(__file__).with_name('test_external.py');s=p.read_text();a,b=s.split('rows=[]\n',1)
Path(__file__).with_name('external_fixture.py').write_text(a)
p.write_text('from external_fixture import *\nrows=[]\n'+b)
