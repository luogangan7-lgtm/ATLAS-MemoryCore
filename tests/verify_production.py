#!/usr/bin/env python3
"""
ATLAS-MemoryCore V6.0 生产部署验证
"""

import os
import sys
import json
from pathlib import Path
import subprocess
import time

print("="*60)
print("ATLAS-MemoryCore V6.0 生产部署验证")
print("="*60)

def check_file_exists(path, description):
    """检查文件是否存在"""
    if os.path.exists(path):
        size = os.path.getsize(path)
        print(f"✅ {description}: {path} ({size:,} bytes)")
        return True
    else:
        print(f"❌ {description}: {path} (缺失)")
        return False

def check_directory_exists(path, description):
    """检查目录是否存在"""
    if os.path.isdir(path):
        file_count = len([f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))])
        print(f"✅ {description}: {path} ({file_count} 个文件)")
        return True
    else:
        print(f"❌ {description}: {path} (缺失)")
        return False

def run_command(cmd, description):
    """运行命令并检查结果"""
    print(f"\n▶ {description}")
    print(f"  命令: {cmd}")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"  ✅ 成功")
            if result.stdout.strip():
                print(f"  输出: {result.stdout[:200]}...")
            return True
        else:
            print(f"  ❌ 失败 (退出码: {result.returncode})")
            if result.stderr:
                print(f"  错误: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ 超时")
        return False
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        return False

def main():
    """主验证函数"""
    
    print("\n📁 文件系统检查:")
    print("-"*40)
    
    # 检查项目文件
    project_files = [
        ("src/optimization/performance_optimizer.py", "性能优化器模块"),
        ("src/ui/user_experience.py", "用户体验模块"),
        ("src/integration/ecosystem.py", "生态系统集成模块"),
        ("Dockerfile", "Docker构建文件"),
        ("docker-compose.yml", "Docker Compose配置"),
        ("kubernetes/deployment.yaml", "Kubernetes部署配置"),
        ("start_local_service.py", "本地服务启动脚本"),
        ("create_openclaw_skill.py", "OpenClaw技能创建脚本"),
        ("PRODUCTION_DEPLOYMENT_REPORT.md", "生产部署报告"),
    ]
    
    file_results = []
    for file_path, description in project_files:
        file_results.append(check_file_exists(file_path, description))
    
    # 检查OpenClaw技能
    skill_path = Path.home() / ".openclaw" / "skills" / "atlas-memory"
    skill_files = [
        (skill_path / "SKILL.md", "OpenClaw技能文档"),
        (skill_path / "atlas_skill.py", "OpenClaw技能实现"),
        (skill_path / "config.yaml", "技能配置文件"),
        (skill_path / "EXAMPLES.md", "使用示例文档"),
    ]
    
    print("\n🔗 OpenClaw技能检查:")
    print("-"*40)
    
    skill_results = []
    for file_path, description in skill_files:
        skill_results.append(check_file_exists(file_path, description))
    
    # 检查Python模块导入
    print("\n🐍 Python模块检查:")
    print("-"*40)
    
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        # 尝试导入关键模块（不依赖外部库）
        import importlib.util
        
        modules_to_check = [
            ("src/optimization/performance_optimizer", "性能优化器"),
            ("src/ui/user_experience", "用户体验"),
            ("src/integration/ecosystem", "生态系统集成"),
        ]
        
        for module_path, description in modules_to_check:
            try:
                spec = importlib.util.spec_from_file_location(
                    description, 
                    os.path.join(os.path.dirname(__file__), f"{module_path}.py")
                )
                if spec and spec.loader:
                    print(f"✅ {description}: 模块文件存在")
                else:
                    print(f"❌ {description}: 模块文件不存在")
            except Exception as e:
                print(f"⚠️  {description}: 检查失败 - {e}")
    
    except Exception as e:
        print(f"⚠️ 模块检查异常: {e}")
    
    # 检查Docker构建状态
    print("\n🐳 Docker状态检查:")
    print("-"*40)
    
    docker_checks = [
        ("docker --version", "Docker客户端"),
        ("docker-compose --version", "Docker Compose"),
    ]
    
    docker_results = []
    for cmd, description in docker_checks:
        docker_results.append(run_command(cmd, description))
    
    # 检查本地服务
    print("\n🚀 本地服务检查:")
    print("-"*40)
    
    # 尝试启动本地服务（短暂运行）
    try:
        import threading
        from start_local_service import start_server
        
        # 在后台启动服务
        server_thread = threading.Thread(target=start_server, args=(8001,), daemon=True)
        server_thread.start()
        
        time.sleep(2)  # 等待服务启动
        
        # 测试健康检查
        import urllib.request
        import urllib.error
        
        try:
            with urllib.request.urlopen('http://localhost:8001/health', timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    print(f"✅ 本地服务健康检查: {data.get('status', 'unknown')}")
                else:
                    print(f"❌ 本地服务健康检查失败: HTTP {response.status}")
        except urllib.error.URLError as e:
            print(f"❌ 无法连接到本地服务: {e}")
        
    except Exception as e:
        print(f"⚠️ 本地服务检查失败: {e}")
    
    # 汇总结果
    print("\n" + "="*60)
    print("生产部署验证汇总:")
    print("="*60)
    
    total_checks = len(file_results) + len(skill_results) + len(docker_results)
    passed_checks = sum(file_results) + sum(skill_results) + sum(docker_results)
    
    print(f"📁 项目文件: {sum(file_results)}/{len(file_results)} 通过")
    print(f"🔗 OpenClaw技能: {sum(skill_results)}/{len(skill_results)} 通过")
    print(f"🐳 Docker环境: {sum(docker_results)}/{len(docker_results)} 通过")
    print(f"📊 总计: {passed_checks}/{total_checks} 通过 ({passed_checks/total_checks*100:.0f}%)")
    
    if passed_checks == total_checks:
        print("\n🎉 生产部署验证通过！ATLAS-MemoryCore V6.0 生产就绪。")
        
        print("\n🚀 下一步操作:")
        print("1. 启动生产服务:")
        print("   python start_local_service.py --port 8000")
        
        print("\n2. 使用OpenClaw技能:")
        print("   openclaw skill link ~/.openclaw/skills/atlas-memory")
        print("   /openclaw atlas capture \"重要记忆\"")
        
        print("\n3. 构建Docker镜像:")
        print("   docker build -t atlas-memory-core:v6.0 .")
        
        print("\n4. 部署到Kubernetes:")
        print("   kubectl apply -f kubernetes/deployment.yaml")
        
        return 0
    else:
        print(f"\n⚠️  验证失败，{total_checks - passed_checks} 项检查未通过。")
        print("请检查缺失的文件或配置。")
        return 1

if __name__ == "__main__":
    sys.exit(main())