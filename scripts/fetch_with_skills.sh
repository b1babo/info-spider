#!/bin/bash

###############################################################################
# Info-Spider 数据拉取和报告生成脚本 (AI-Native 方式)
#
# 功能：使用 Claude Code Skills 自动化数据拉取和报告生成
###############################################################################

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 配置
REPORTS_DIR="$PROJECT_ROOT/reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$PROJECT_ROOT/logs/fetch_with_skills.log"

# 创建必要目录
mkdir -p "$REPORTS_DIR" "$PROJECT_ROOT/logs"

# 日志函数
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a "$LOG_FILE"
}

# 错误处理
error_exit() {
    log "❌ ERROR: $1"
    exit 1
}

# 检查 claude CLI 是否可用
check_claude() {
    if ! command -v claude &>/dev/null; then
        error_exit "Claude Code CLI 未安装。请访问 https://code.anthropic.com 安装"
    fi
    log "✅ Claude Code CLI 已就绪"
}

# 检查服务器状态
check_server() {
    log "🔍 检查 Actor 服务器状态..."
    if python main.py --server status &>/dev/null; then
        log "✅ Actor 服务器运行中"
        return 0
    else
        log "⚠️  Actor 服务器未运行"
        return 1
    fi
}

# 启动服务器
start_server() {
    log "🚀 启动 Actor 服务器..."
    python main.py --server start || error_exit "无法启动服务器"
    sleep 3
    log "✅ 服务器已启动"
}

# 使用 Claude + Skills 执行数据拉取
fetch_data_with_claude() {
    log "🤖 使用 Claude 执行数据拉取..."

    local prompt="请执行以下任务：

**步骤 1**: 检查 Info-Spider Actor 服务器状态，如果未运行则启动（使用：python main.py --server status 和 python main.py --server start）

**步骤 2**: 列出可用的任务模板（使用：python main.py --list-templates）

**步骤 3**: 对以下任务依次执行数据拉取：
   - github_tweets (Twitter 数据)
   - product_hunt_daily (Product Hunt 数据)

   对每个任务执行：
   a) 创建任务实例：python main.py --create-task <task_name>
   b) 执行数据提取：python main.py --task-id <task_id> --action scroll_and_extract --action-params '{\"scroll_times\":20,\"max\":100}'
   c) 关闭任务并保存：python main.py --task-id <task_id> --action close

**步骤 4**: 确认数据已保存到 data/tasks/ 目录

请逐步执行并报告每个步骤的结果。遇到错误请说明原因。"

    claude -p "$prompt" --output-format json > "reports/fetch_result_${TIMESTAMP}.json" 2>>"$LOG_FILE" || true

    log "📊 数据拉取完成"
}

# 使用 Claude + generate-report skill 生成报告
generate_report_with_claude() {
    log "📝 使用 Claude + /generate-report skill 生成报告..."

    local prompt="请使用 /generate-report skill 执行以下任务：

**任务**: 分析最新拉取的数据并生成报告

**步骤**:
1. 使用 /generate-report skill
2. 该 skill 会自动：
   - 分析 data/tasks/ 目录中的最新数据
   - 提取热度指标（点赞、转发、评论）
   - 提取热门关键词和话题标签
   - 生成结构化 Markdown 报告保存到 reports/ 目录
   - 生成 JSON 摘要文件

请完整执行 /generate-report skill 的所有步骤，确保报告生成成功。

报告应包含：
- 🔥 热门内容排行（Top 5-10）
- 🔑 热门关键词统计
- 📈 趋势分析
- 📝 内容摘要"

    claude -p "$prompt" --output-format json > "reports/report_generation_${TIMESTAMP}.json" 2>>"$LOG_FILE" || true

    log "✅ 报告生成完成"
}

# 主函数：一键执行完整流程
main() {
    log "========================================"
    log "🎯 Info-Spider 自动化数据拉取与报告生成"
    log "========================================"

    # 检查环境
    check_claude

    # 检查并启动服务器
    if ! check_server; then
        start_server
    fi

    # 方式 1: 分步执行（推荐用于调试）
    log ""
    log "📍 方式 1: 分步执行"
    log ""
    fetch_data_with_claude
    sleep 2
    generate_report_with_claude

    # 显示最新报告
    log ""
    log "========================================"
    log "📋 最新报告文件："
    log "========================================"
    ls -t "$REPORTS_DIR"/report_*.md 2>/dev/null | head -1 | while read -r report; do
        log "📄 $report"
        echo ""
        head -30 "$report"
        echo ""
        echo "... (报告内容已截断，完整内容请查看文件)"
    done

    log ""
    log "✅ 全部完成！"
    log "📁 报告目录: $REPORTS_DIR"
    log "📝 日志文件: $LOG_FILE"
}

# 执行主函数
main "$@"
