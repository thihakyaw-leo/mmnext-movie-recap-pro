import pathlib

p = pathlib.Path('tests/test_narrator_pipeline.py')
t = p.read_text(encoding='utf-8')

# Add _wait_for helper after imports section
import_section_end = t.find('from mmnext.ui.app_context import AppContext')
insert_pos = t.find('\n', import_section_end) + 1

wait_for_func = '''def _wait_for(predicate, timeout_ms: int = 300000) -> bool:
    import time
    waited = 0
    while waited < timeout_ms:
        if predicate():
            return True
        time.sleep(0.25)
        waited += 250
    return False


'''

t = t[:insert_pos] + wait_for_func + t[insert_pos:]

# Fix context -> ctx typo
t = t.replace(
    'assert ctx.transcript_state == "complete", context.transcript_message',
    'assert ctx.transcript_state == "complete", ctx.transcript_message'
)

p.write_text(t, encoding='utf-8')
print("Done")
print("Lines:", len(t.splitlines()))
