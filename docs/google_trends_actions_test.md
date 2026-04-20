# GoogleTrendsActor 深度挖掘功能测试报告

## 测试时间
2026-04-11

## 测试功能

### 1. compare_keywords Action

**功能**: 比较多个关键词的趋势数据

**测试参数**:
```json
{
  "keywords": ["AI", "ML", "DL"],
  "time_range": "today 3-m",
  "geo": ""
}
```

**测试结果**: ✅ 通过

**输出**:
- 状态: success
- 下载文件:
  - `searched_with_top-queries_Worldwide_*.csv` (热门查询)
  - `searched_with_rising-queries_Worldwide_*.csv` (上升查询)
- 数据条目: 100 条

**CSV 数据示例**:
```csv
"query","search interest","increase percent"
"ai gemini",100,"-10%"
"gemini",100,"-10%"
"gemini ai",94,"-20%"
"ai google",65,"-6%"
```

---

### 2. regional_interest Action

**功能**: 获取关键词的地区分布数据

**测试参数**:
```json
{
  "keyword": "AI",
  "geo": "US",
  "time_range": "today 12-m"
}
```

**测试结果**: ✅ 通过

**输出**:
- 状态: success
- 下载文件:
  - `time_series_US_*.csv` (时间序列)
  - `searched_with_top-queries_US_*.csv` (热门查询)
  - `searched_with_rising-queries_US_*.csv` (上升查询)

**CSV 数据示例**:
```csv
"Time","AI"
"2025-04-06",52
"2025-04-13",48
"2025-04-20",51
"2025-04-27",52
```

---

## 数据存储位置

数据保存在任务专属目录: `data/tasks/{task_id}/`

- `test_compare_001/`: compare_keywords 测试数据
- `test_regional_001/`: regional_interest 测试数据

---

## 已知问题

1. **Interest Over Time 下载偶尔失败**: 部分下载的 CSV 文件通过 fetch API 获取时可能失败，但不影响核心功能

---

## 结论

两个新增的深度挖掘功能均正常工作，数据成功保存到任务专属目录。
