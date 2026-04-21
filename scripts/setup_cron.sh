#!/bin/bash
# 设置夜间自优化循环的 Cron 任务

set -e

echo "设置 ATLAS-MemoryCore 夜间优化 Cron 任务"

# 项目路径
PROJECT_ROOT="/Volumes/data/openclaw_workspace/projects/atlas-memory-core"
VENV_PATH="$PROJECT_ROOT/venv"
LOG_DIR="/Volumes/data/openclaw_workspace/logs"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 检查虚拟环境
if [ ! -d "$VENV_PATH" ]; then
    echo "创建虚拟环境..."
    cd "$PROJECT_ROOT"
    python3 -m venv venv
    source venv/bin/activate
    pip install -e .
else
    echo "虚拟环境已存在"
fi

# 创建 Cron 任务文件
CRON_FILE="/tmp/atlas_memory_cron"
cat > "$CRON_FILE" << EOF
# ATLAS-MemoryCore 夜间自优化循环
# 每天凌晨3点运行
0 3 * * * cd $PROJECT_ROOT && $VENV_PATH/bin/python scripts/run_optimization.py >> $LOG_DIR/cron_optimization.log 2>&1

# 每周日凌晨2点运行完整优化（包含调度）
0 2 * * 0 cd $PROJECT_ROOT && $VENV_PATH/bin/python scripts/run_optimization.py --schedule >> $LOG_DIR/cron_weekly.log 2>&1

# 每小时检查一次服务状态
0 * * * * cd $PROJECT_ROOT && $VENV_PATH/bin/python -c "from src.core.storage import get_default_storage; import sys; storage = get_default_storage(); print('Qdrant连接正常' if storage.client else 'Qdrant连接失败')" >> $LOG_DIR/health_check.log 2>&1
EOF

echo "Cron 任务配置:"
echo "--------------"
cat "$CRON_FILE"
echo "--------------"

# 询问是否安装
read -p "是否安装到当前用户的 Crontab？(y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # 备份现有 crontab
    if crontab -l > /tmp/crontab_backup 2>/dev/null; then
        echo "现有 Crontab 已备份到 /tmp/crontab_backup"
    fi
    
    # 合并并安装
    (crontab -l 2>/dev/null || true; cat "$CRON_FILE") | crontab -
    
    echo "Cron 任务安装完成"
    echo "当前用户的 Crontab:"
    crontab -l
else
    echo "Cron 任务已保存到 $CRON_FILE"
    echo "手动安装命令:"
    echo "  crontab $CRON_FILE"
fi

# 创建 systemd 服务（可选）
SYSTEMD_SERVICE="/tmp/atlas-memory-optimize.service"
cat > "$SYSTEMD_SERVICE" << EOF
[Unit]
Description=ATLAS-MemoryCore Optimization Service
After=network.target

[Service]
Type=oneshot
User=$(whoami)
WorkingDirectory=$PROJECT_ROOT
Environment="PATH=$VENV_PATH/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV_PATH/bin/python scripts/run_optimization.py
StandardOutput=append:$LOG_DIR/systemd_optimization.log
StandardError=append:$LOG_DIR/systemd_optimization.error.log

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "Systemd 服务文件已保存到 $SYSTEMD_SERVICE"
echo "安装 systemd 服务:"
echo "  sudo cp $SYSTEMD_SERVICE /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable atlas-memory-optimize.service"
echo "  sudo systemctl start atlas-memory-optimize.service"

echo ""
echo "设置完成！"