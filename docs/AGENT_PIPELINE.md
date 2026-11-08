# 代理管道

Grok Bot 和 Muse 只读这份发现文件，再把处置状态写回来。它们不运行扫描，不拿明文 Key，不拿 `DASHBOARD_TOKEN`。

## 发现文件

```bash
python main_v2.2.py --authorized --findings-json findings.json
```

`findings.json` 的 `schema` 是 `findings.v1`。每条只有这些字段：

| 字段 | 含义 |
|---|---|
| `fingerprint` | 密钥的 SHA-256，64 位十六进制。用来回写状态 |
| `platform` | 平台名 |
| `preview` | 脱敏预览 |
| `repo` | `owner/name`，Gist 为 `gist:用户`。解析不出时为空 |
| `path` | 文件路径。解析不出时为空 |
| `commit` | 提交或分支名。链接里是分支时，这里就是分支名 |
| `location` | 原始链接 |
| `disposition` | `open`、`notified`、`rotated`、`false_positive` |
| `found_time` | 入库时间 |

同一份数据也可以从本机面板读取：`GET /api/findings`。这个接口没有 reveal。

## 状态写回

代理只改 `disposition`，其他字段留着也没关系。保存成 `dispositions.json`：

```json
{
  "updates": [
    {"fingerprint": "<64 hex>", "disposition": "notified"}
  ]
}
```

写回数据库：

```bash
python main_v2.2.py --authorized --apply-dispositions dispositions.json --findings-json findings.json
```

单条也可以：

```bash
python main_v2.2.py --authorized --set-disposition <fingerprint> rotated
```

## 代理怎么用

Grok Bot 的定时任务读 `findings.json` 或 `GET /api/findings`，按 `repo` 归并，起草给维护者的说明，等人确认后再把对应指纹标成 `notified`。

Muse 读同一份文件，生成你自己的待办。不要把数据库、`DB_ENCRYPTION_KEY` 或 `DASHBOARD_TOKEN` 交给它。那个令牌可以打开面板上的明文查看。
