import pathlib

p = pathlib.Path('tests/test_narrator_pipeline.py')
t = p.read_text(encoding='utf-8')
lines = t.splitlines(keepends=True)
for i, line in enumerate(lines[380:440], start=381):
    print(f'{i}: {repr(line)}')
