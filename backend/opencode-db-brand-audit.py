import sqlite3
c = sqlite3.connect(r'C:\Users\SAVIOUR\Documents\TeachFlow\backend\teachflow.db')
print("=== product_plans: names/descriptions containing TeachFlow ===")
for r in c.execute("SELECT id, name, description, product_type FROM product_plans"):
    if any('teachflow' in str(x).lower() for x in r):
        print(" ", r)
print("=== count of all plans ===", c.execute("SELECT COUNT(*) FROM product_plans").fetchone())
print("=== templates with TeachFlow in name ===")
for r in c.execute("SELECT id, name, family FROM template_definitions"):
    if any('teachflow' in str(x).lower() for x in r):
        print(" ", r)
print("=== any other table with TeachFlow strings ===")
for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
    textcols = [col for col in cols if col in ('name','description','filename','school_name','teacher_name','full_name','product_name','notes','details','config_key','config_value','message','error_message')]
    for col in textcols:
        try:
            for r in c.execute(f"SELECT {col} FROM {t} WHERE {col} LIKE '%TeachFlow%' LIMIT 3"):
                print(f"  {t}.{col}: {r[0][:90]}")
        except Exception:
            pass
