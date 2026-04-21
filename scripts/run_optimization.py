#!/usr/bin/env python3
"""
夜间自优化循环执行脚本
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.optimization.self_optimization import SelfOptimizationLoop
from src.core.storage import get_default_storage
from src.core.scoring import get_default_scoring_engine


def setup_logging():
    """配置日志"""
    log_dir = Path("/Volumes/data/openclaw_workspace/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "optimization.log"),
            logging.StreamHandler()
        ]
    )


async def main():
    """主函数"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("启动夜间自优化循环")
    
    try:
        # 创建优化循环
        storage = get_default_storage()
        scoring_engine = get_default_scoring_engine()
        optimization_loop = SelfOptimizationLoop(storage, scoring_engine)
        
        # 运行优化
        stats = await optimization_loop.run_full_optimization()
        
        logger.info(f"优化完成: 总计{stats['total_memories']}条记忆, "
                   f"升级{stats['upgraded_to_qmd']}条, "
                   f"遗忘{stats['forgotten']}条, "
                   f"降权{stats['demoted']}条")
        
        # 检查是否需要调度下一次优化
        if "--schedule" in sys.argv:
            logger.info("进入调度模式，等待下一次优化")
            await optimization_loop.schedule_nightly_optimization()
        
    except Exception as e:
        logger.error(f"优化循环执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())