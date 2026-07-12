#!/bin/bash

###############################################################################
# Info-Spider 数据拉取和报告生成脚本 (AI-Native 方式)
#
# 功能：使用 Claude Code Subagents 自动化数据拉取和报告生成（一体化）
#
# 使用方法:
#   ./scripts/fetch_with_skills.sh [目标任务] [自定义报告要求]
#
# 参数:
#   目标任务        - 可选，要抓取的任务列表，空格分隔
#                     例如: "github_tweets product_hunt_daily"
#                     默认: "github_tweets product_hunt_daily"
#   自定义报告要求  - 可选，对报告生成的额外要求
#                     例如: "重点关注AI相关内容"
#
# 示例:
#   # 使用默认任务
#   ./scripts/fetch_with_skills.sh
#
#   # 指定特定任务
#   ./scripts/fetch_with_skills.sh "github_tweets"
#
#   # 指定多个任务
#   ./scripts/fetch_with_skills.sh "github_tweets reddit_ai"
#
#   # 指定任务和报告要求
#   ./scripts/fetch_with_skills.sh "github_tweets" "重点关注AI工具趋势"
###############################################################################

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 配置
REPORTS_DIR="$PROJECT_ROOT/reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$PROJECT_ROOT/logs/fetch_with_skills.log"
export IS_SANDBOX=1

# Session 相关变量
SESSION_ID=""
SESSION_DIR=""

# 创建必要目录
mkdir -p "$REPORTS_DIR" "$PROJECT_ROOT/logs"

# 日志函数
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a "$LOG_FILE"
}

# 错误处理
error_exit() {
    local error_msg="$1"
    log "❌ ERROR: $error_msg"

    # 更新 meta.json 标记失败
    if [ -n "$TASK_ID" ] && [ -d "$TASK_DIR" ]; then
        if [ -f "$TASK_DIR/meta.json" ]; then
            # 使用 jq 更新或直接 sed
            temp_file=$(mktemp)
            sed 's/"status": "in_progress"/"status": "failed"/' "$TASK_DIR/meta.json" > "$temp_file"
            echo "{\"error\": \"$error_msg\"}" >> "$temp_file"
            mv "$temp_file" "$TASK_DIR/meta.json"
        fi
    fi

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

# 生成 UUID
generate_session_id() {
    # 尝试使用 uuidgen，如果不可用则回退到 Python
    if command -v uuidgen &>/dev/null; then
        uuidgen | tr '[:upper:]' '[:lower:]'
    else
        python3 -c 'import uuid; print(str(uuid.uuid4))'
    fi
}

# 创建 Session 目录
setup_session() {
    SESSION_ID=$(generate_session_id)
    SESSION_DIR="$REPORTS_DIR/session_$SESSION_ID"
    mkdir -p "$SESSION_DIR"

    log "🆔 Session ID: $SESSION_ID"
    log "📁 Session 目录: $SESSION_DIR"

    # 创建 session 日志文件
    local session_log="$SESSION_DIR/session.log"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Session started: $SESSION_ID" > "$session_log"

    log "✅ Session 目录已创建"
}

# 创建 Task 目录和初始 meta.json
setup_task() {
    TASK_ID=$(generate_task_id)
    TASK_DIR="$REPORTS_DIR/$TASK_ID"
    mkdir -p "$TASK_DIR"

    log "🆔 临时 Task ID: $TASK_ID"
    log "📁 Task 目录: $TASK_DIR"

    # 创建初始 meta.json（不含 session_id）
    cat > "$TASK_DIR/meta.json" <<EOF
{
  "task_id": "$TASK_ID",
  "session_id": null,
  "timestamp": "$(date -Iseconds)",
  "status": "in_progress",
  "tasks": [],
  "reports": [],
  "stats": {
    "total_fetched": 0,
    "total_generated": 0,
    "start_time": "$(date -Iseconds)",
    "end_time": null
  },
  "config": {
    "target_tasks": "",
    "custom_requirements": ""
  }
}
EOF

    log "✅ Task 目录已创建"
}

# 使用 Claude 一体化执行数据拉取和报告生成
fetch_and_generate_with_claude() {
    local target_tasks="${1:-github_tweets product_hunt_daily}"  # 默认任务列表
    local custom_prompt="$2"

    log "🤖 使用 Claude 一体化执行数据拉取和报告生成..."
    log "📋 目标任务: $target_tasks"

    local prompt="请使用 @agent-info-spider-helper 和 @agent-report-generator 完成以下完整流程：

**第一阶段：数据拉取**
使用 @agent-info-spider-helper 执行以下任务：
1. 检查 Actor 服务器状态并确保其运行
2. 拉取以下任务的数据：
   ${target_tasks}
3. 记录每个任务的执行状态和提取的数据条数

**第二阶段：报告生成**
使用 @agent-report-generator 执行以下任务：
1. 分析刚刚拉取的最新数据
2. 生成完整的 Markdown 分析报告
3. 将报告保存到文件: ${SESSION_DIR}目录中



请完整执行所有步骤并返回详细报告。"

    # 如果有自定义要求，追加到提示词
    if [ -n "$custom_prompt" ]; then
        log "📌 自定义报告要求: $custom_prompt"
        prompt="${prompt}

**额外报告要求**:
${custom_prompt}"
    fi

    # 执行 Claude 命令，捕获输出
    log "🚀 开始执行..."
    echo ""

    local json_output_file="$SESSION_DIR/claude_stream.json"

    # 使用新的参数：--output-format stream-json --print --verbose --session-id
    # JSON 流输出到 json_output_file，同时通过 --print 打印到标准输出
    claude -p "$prompt" \
        --dangerously-skip-permissions \
        --output-format stream-json \
        --print \
        --verbose \
        --session-id "$SESSION_ID" \
        > "$json_output_file" 2>&1

    # 同时追加到主日志
    cat "$json_output_file" | tee -a "$LOG_FILE" > /dev/null

    echo ""
    log "📊 执行完成"
    log "📁 JSON 输出: $json_output_file"

    # 显示目录内容
    show_session_summary
}

# 显示 Session 摘要
show_session_summary() {
    log ""
    log "========================================"
    log "📋 Session 摘要"
    log "========================================"
    log "🆔 Session ID: $SESSION_ID"
    log "📁 Session 目录: $SESSION_DIR"
    log ""

    # 显示文件列表
    log "📂 生成的文件："
    ls -lh "$SESSION_DIR" | tail -n +2 | awk '{printf "  %-40s %10s\n", $9, $5}' || true
    log ""
}

# 显示所有 Sessions
show_all_sessions() {
    log ""
    log "========================================"
    log "📋 所有 Sessions"
    log "========================================"

    for session_dir in $(ls -td "$REPORTS_DIR"/session_* 2>/dev/null); do
        local session_name=$(basename "$session_dir")
        local session_log="$session_dir/session.log"

        log ""
        log "🆔 Session: $session_name"
        log "   目录: $session_dir"

        # 显示文件列表
        if ls "$session_dir"/* &>/dev/null; then
            log "   文件:"
            for file in "$session_dir"/*; do
                local filename=$(basename "$file")
                local filesize=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "?")
                log "     - $filename (${filesize} bytes)"
            done
        fi
    done
}

# 主函数：一键执行完整流程
main() {
    # 解析命令行参数
    local target_tasks="$1"
    local custom_report_prompt="$2"

    log "========================================"
    log "🎯 Info-Spider 一体化数据拉取与报告生成"
    log "========================================"

    # 检查环境
    check_claude

    # 检查并启动服务器
    if ! check_server; then
        start_server
    fi

    # 设置 Session
    setup_session

    # 执行一体化流程
    log ""
    log "📍 开始一体化执行"
    log ""
    fetch_and_generate_with_claude "$target_tasks" "$custom_report_prompt"

    # 显示所有 Sessions
    show_all_sessions

    log ""
    log "========================================"
    log "✅ 全部完成！"
    log "========================================"
    log "🆔 Session ID: $SESSION_ID"
    log "📁 Session 目录: $SESSION_DIR"
    log "📝 日志文件: $LOG_FILE"
}

# 执行主函数
main "$@"
