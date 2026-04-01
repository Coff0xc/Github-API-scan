import sqlite3
import os

def view_database():
    db_path = 'leaked_keys.db'
    
    if not os.path.exists(db_path):
        print(f"数据库文件 {db_path} 不存在")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("=" * 50)
        print("API密钥泄露数据库查看器")
        print("=" * 50)
        
        # 获取所有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            print(f"\n表: {table_name}")
            print("-" * 30)
            
            # 获取表结构
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            print("列:", " | ".join(column_names))
            
            # 获取记录数
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            count = cursor.fetchone()[0]
            print(f"总记录数: {count}")
            
            # 查看数据
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 10;")
            rows = cursor.fetchall()
            
            if rows:
                print("\n前10条记录:")
                for i, row in enumerate(rows, 1):
                    print(f"{i}. {row}")
            
            print("\n" + "=" * 50)
        
        # 提供交互查询
        while True:
            print("\n输入SQL查询语句(输入'quit'退出):")
            query = input("> ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                break
                
            try:
                cursor.execute(query)
                if query.upper().startswith('SELECT'):
                    results = cursor.fetchall()
                    if results:
                        for row in results:
                            print(row)
                    else:
                        print("无结果")
                else:
                    conn.commit()
                    print("执行成功")
            except Exception as e:
                print(f"查询错误: {e}")
        
        conn.close()
        
    except Exception as e:
        print(f"数据库错误: {e}")

if __name__ == "__main__":
    view_database()