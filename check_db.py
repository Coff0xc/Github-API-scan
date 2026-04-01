import sqlite3

try:
    conn = sqlite3.connect('leaked_keys.db')
    cursor = conn.cursor()
    
    # 获取所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("数据库中的表:")
    for table in tables:
        print(f"- {table[0]}")
    
    # 如果有表，查看第一个表的结构
    if tables:
        first_table = tables[0][0]
        cursor.execute(f"PRAGMA table_info({first_table});")
        columns = cursor.fetchall()
        print(f"\n表 {first_table} 的结构:")
        for col in columns:
            print(f"- {col[1]} ({col[2]})")
        
        # 查看前几行数据
        cursor.execute(f"SELECT * FROM {first_table} LIMIT 5;")
        rows = cursor.fetchall()
        print(f"\n表 {first_table} 的前5行数据:")
        for row in rows:
            print(row)
    
    conn.close()
    print("\n数据库检查完成")
    
except Exception as e:
    print(f"错误: {e}")